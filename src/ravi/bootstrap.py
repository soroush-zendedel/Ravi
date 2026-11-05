"""Startup checks: models path, local assets, safe non-fatal diagnostics."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ravi import envutil as eu
from ravi import settings as rsettings
from ravi import share as rshare
from ravi import media as rmedia


@dataclass
class CheckResult:
    id: str
    label: str
    ok: bool
    detail: str = ""
    severity: str = "info"  # info | warn | error
    fixable: bool = False
    hint: str = ""


@dataclass
class BootstrapReport:
    checks: list[CheckResult] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    models_dir: Path | None = None

    @property
    def errors(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.ok and c.severity == "error"]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.ok and c.severity == "warn"]

    @property
    def has_problems(self) -> bool:
        return bool(self.errors or self.warnings)


def _check_env(root: Path) -> tuple[dict[str, str], CheckResult]:
    try:
        eu.ensure_env_file(root)
        env = rsettings.ensure_default_env(root)
        return env, CheckResult(
            id="env",
            label="Environment (.env)",
            ok=True,
            detail="ready",
        )
    except Exception as e:
        return {}, CheckResult(
            id="env",
            label="Environment (.env)",
            ok=False,
            severity="error",
            detail=str(e),
            fixable=True,
            hint="Recreate .env from .env.example and generate secrets.",
        )


def _check_models_dir(root: Path, env: dict[str, str]) -> tuple[Path | None, CheckResult]:
    raw = env.get("RAVI_MODELS_DIR") or "./models"
    try:
        path = rshare.resolve_models_dir(raw, root)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return path, CheckResult(
                id="models_dir",
                label="Models directory",
                ok=False,
                severity="error",
                detail=f"Cannot create/access {path}: {e}",
                fixable=True,
                hint="Run: sudo ravi share   (or fix permissions on RAVI_MODELS_DIR)",
            )
        if not os.access(path, os.R_OK):
            return path, CheckResult(
                id="models_dir",
                label="Models directory",
                ok=False,
                severity="error",
                detail=f"Not readable: {path}",
                fixable=True,
                hint="Run: sudo ravi share",
            )
        return path, CheckResult(
            id="models_dir",
            label="Models directory",
            ok=True,
            detail=str(path),
        )
    except Exception as e:
        return None, CheckResult(
            id="models_dir",
            label="Models directory",
            ok=False,
            severity="error",
            detail=str(e),
            fixable=True,
            hint="Check RAVI_MODELS_DIR in .env",
        )


def _check_local_models(root: Path, env: dict[str, str], models_dir: Path | None) -> list[CheckResult]:
    out: list[CheckResult] = []
    try:
        from ravi.download import list_local_ggufs, find_local_gguf, get_catalog_model

        ggufs = list_local_ggufs(root) if models_dir else []
        default = get_catalog_model(None, root)
        found_default = (
            find_local_gguf(root, default.hf_file) if default.hf_file else None
        )
        if found_default:
            out.append(
                CheckResult(
                    id="default_gguf",
                    label=f"Default model file ({default.hf_file})",
                    ok=True,
                    detail=str(found_default),
                )
            )
        else:
            out.append(
                CheckResult(
                    id="default_gguf",
                    label=f"Default model file ({default.hf_file or default.id})",
                    ok=False,
                    severity="warn",
                    detail="Not on disk yet — will download on `ravi local pull`",
                    fixable=True,
                    hint="ravi local pull",
                )
            )
        out.append(
            CheckResult(
                id="gguf_scan",
                label="Local GGUF scan",
                ok=True,
                detail=f"{len(ggufs)} file(s) under models dir",
            )
        )
    except Exception as e:
        out.append(
            CheckResult(
                id="gguf_scan",
                label="Local GGUF scan",
                ok=False,
                severity="warn",
                detail=str(e),
                fixable=False,
            )
        )
    return out


def _check_toggles(env: dict[str, str]) -> list[CheckResult]:
    rows = []
    for key, label in (
        ("RAVI_LLM", "Language model"),
        ("RAVI_VOICE", "Voice"),
        ("RAVI_IMAGE", "Image generation"),
        ("RAVI_VIDEO", "Video generation"),
    ):
        state = (env.get(key) or "off").lower()
        on = state in ("on", "1", "true", "yes")
        rows.append(
            CheckResult(
                id=key.lower(),
                label=label,
                ok=True,
                detail="ON" if on else "OFF",
                severity="info",
            )
        )
    return rows


def _check_docker() -> CheckResult:
    try:
        import shutil
        import subprocess

        if not shutil.which("docker"):
            return CheckResult(
                id="docker",
                label="Docker CLI",
                ok=False,
                severity="warn",
                detail="docker not found on PATH",
                fixable=False,
                hint="Install Docker Desktop / Engine to run the stack.",
            )
        p = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if p.returncode != 0:
            return CheckResult(
                id="docker",
                label="Docker daemon",
                ok=False,
                severity="warn",
                detail="Docker installed but daemon not reachable",
                fixable=True,
                hint="Start Docker Desktop / systemctl start docker",
            )
        return CheckResult(
            id="docker",
            label="Docker",
            ok=True,
            detail="reachable",
        )
    except Exception as e:
        return CheckResult(
            id="docker",
            label="Docker",
            ok=False,
            severity="warn",
            detail=str(e),
            fixable=False,
        )


def run_bootstrap(root: Path) -> BootstrapReport:
    """Never raises — all failures become CheckResult entries."""
    report = BootstrapReport()
    try:
        env, env_check = _check_env(root)
        report.env = env
        report.checks.append(env_check)

        models_dir, md_check = _check_models_dir(root, env)
        report.models_dir = models_dir
        report.checks.append(md_check)

        report.checks.extend(_check_local_models(root, env, models_dir))
        report.checks.extend(_check_toggles(env))
        report.checks.append(_check_docker())

        # Auto-wire local default model if file exists and LLM is on
        if rsettings.is_on(env, "RAVI_LLM") or (env.get("RAVI_LLM") or "on").lower() != "off":
            try:
                from ravi import local as loc
                from ravi.configedit import ensure_ollama_model

                auto = loc.pick_auto(root)
                if auto:
                    report.checks.append(
                        CheckResult(
                            id="auto_local",
                            label="Local model auto-detect",
                            ok=True,
                            detail=f"{auto.ollama_name} ({auto.source})",
                        )
                    )
            except Exception as e:
                report.checks.append(
                    CheckResult(
                        id="auto_local",
                        label="Local model auto-detect",
                        ok=False,
                        severity="warn",
                        detail=str(e),
                    )
                )
    except Exception as e:
        report.checks.append(
            CheckResult(
                id="bootstrap",
                label="Bootstrap",
                ok=False,
                severity="error",
                detail=str(e),
                fixable=True,
            )
        )

    # Laya local weights (non-fatal)
    try:
        from ravi import laya_download as layadl
        from ravi import laya_service as layasvc
        env = report.env or {}
        if layasvc.laya_on(env):
            info = layadl.detect(root)
            if info["wanted_present"]:
                report.checks.append(
                    CheckResult(
                        id="laya_weights",
                        label="Laya local weights",
                        ok=True,
                        detail=info["models_root"],
                    )
                )
            else:
                report.checks.append(
                    CheckResult(
                        id="laya_weights",
                        label="Laya local weights",
                        ok=False,
                        severity="warn",
                        detail=f"missing {info['wanted']} under {info['models_root']}",
                        fixable=True,
                        hint="ravi local laya pull -m laya-english",
                    )
                )
        else:
            report.checks.append(
                CheckResult(
                    id="laya",
                    label="Laya decision model",
                    ok=True,
                    detail="OFF",
                )
            )
    except Exception as e:
        report.checks.append(
            CheckResult(
                id="laya",
                label="Laya",
                ok=False,
                severity="warn",
                detail=str(e),
            )
        )

    return report


def problems_summary(report: BootstrapReport) -> str:
    lines = []
    for c in report.errors + report.warnings:
        lines.append(f"- [{c.severity}] {c.label}: {c.detail}")
        if c.hint:
            lines.append(f"  hint: {c.hint}")
    return "\n".join(lines) if lines else "No problems detected."
