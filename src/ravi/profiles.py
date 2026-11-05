"""Named runtime profiles (small / medium / large / extra / custom)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

from ravi import envutil as eu

PROFILE_KEYS = [
    "RAVI_LLM",
    "RAVI_VOICE",
    "RAVI_IMAGE",
    "RAVI_VIDEO",
    "RAVI_SMART_LOG",
    "RAVI_SENTRY",
    "RAVI_LAYA",
    "RAVI_LAYA_VARIANT",
    "RAVI_LAYA_MODEL",
]


def profiles_path(root: Path) -> Path:
    return root / "config" / "profiles.yaml"


def custom_snapshot_path(root: Path) -> Path:
    return root / ".ravi-profile-custom.json"


def load_profiles(root: Path) -> dict[str, Any]:
    path = profiles_path(root)
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("profiles") or {}


def current_env_slice(root: Path) -> dict[str, str]:
    env = eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {}
    return {k: env.get(k, "" if k == "RAVI_LAYA_MODEL" else "off") for k in PROFILE_KEYS}


def save_custom_snapshot(root: Path, extra: dict | None = None) -> None:
    """Persist user's mix so `ravi profile custom` can restore it."""
    data = current_env_slice(root)
    if extra:
        data.update(extra)
    data["_active_before"] = (
        eu.parse_env(eu.env_path(root)).get("RAVI_PROFILE") or "custom"
    )
    custom_snapshot_path(root).write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


def load_custom_snapshot(root: Path) -> dict[str, str] | None:
    path = custom_snapshot_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: str(v) for k, v in data.items() if not k.startswith("_")}
    except Exception:
        return None


def apply_env_flags(root: Path, flags: dict[str, str]) -> None:
    path = eu.env_path(root)
    try:
        eu.ensure_env_file(root)
    except Exception:
        pass
    for k, v in flags.items():
        if k in PROFILE_KEYS or k == "RAVI_PROFILE":
            try:
                eu.write_env_value(path, k, str(v))
            except Exception:
                # sandbox / permission issues must not crash profile switch
                pass


def _compose(root: Path, *args: str) -> tuple[int, str]:
    cmd = ["docker", "compose", "-f", str(root / "docker-compose.yml"), *args]
    try:
        p = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True, timeout=180
        )
        return p.returncode, ((p.stdout or "") + (p.stderr or ""))[-800:]
    except Exception as e:
        return 1, str(e)


def stop_services(root: Path, names: list[str]) -> list[str]:
    notes = []
    for name in names:
        code, out = _compose(root, "stop", name)
        notes.append(f"stop {name}: {'ok' if code == 0 else out[:80]}")
    return notes


def start_services(root: Path, names: list[str], *, web_uis: bool = False) -> list[str]:
    notes = []
    env = eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {}
    services = list(names)
    backend = (env.get("RAVI_LLM_BACKEND") or "llama").strip().lower()
    llm_on = (env.get("RAVI_LLM") or "on").strip().lower() not in (
        "off",
        "0",
        "false",
        "no",
    )

    if not llm_on:
        for name in ("llama", "ollama"):
            if name in services:
                services.remove(name)
                notes.append(f"skip {name}: RAVI_LLM is off")
    elif backend == "ollama" and "llama" in services:
        services.remove("llama")
        if "ollama" not in services:
            services.append("ollama")
    elif backend not in ("llama", "llama.cpp", "llamacpp") and "llama" in services:
        services.remove("llama")
        notes.append("skip llama: another local backend is selected")

    if "llama" in services:
        from ravi.ready import _llama_model_available
        if not _llama_model_available(root, env):
            services.remove("llama")
            if (env.get("RAVI_LOCAL_MODEL") or "").strip():
                if "ollama" not in services:
                    services.append("ollama")
            else:
                notes.append("skip llama: no GGUF model is available")

    laya_on = (env.get("RAVI_LAYA") or "off").strip().lower() in (
        "on",
        "1",
        "true",
        "yes",
    )
    if "laya" in services and not laya_on:
        services.remove("laya")
        notes.append("skip laya: RAVI_LAYA is off")
    if "laya" in services:
        from ravi import laya_download as layadl

        if not layadl.detect(root).get("wanted_present"):
            services.remove("laya")
            notes.append("skip laya: selected local weights are missing")

    smartlog_on = (env.get("RAVI_SMART_LOG") or "off").strip().lower() in (
        "on",
        "1",
        "true",
        "yes",
    )
    if not smartlog_on:
        for name in ("worker", "worker-beat"):
            if name in services:
                services.remove(name)
                notes.append(f"skip {name}: RAVI_SMART_LOG is off")

    profiles: list[str] = []
    if web_uis or "flower" in services:
        profiles.extend(["--profile", "flower"])
    if web_uis or "glitchtip" in services:
        profiles.extend(["--profile", "errors"])
    if "laya" in services:
        profiles.extend(["--profile", "laya"])
    if "llama" in services:
        profiles.extend(["--profile", "llama"])
    if "ollama" in services:
        profiles.extend(["--profile", "ollama"])
    if "worker" in services or "worker-beat" in services:
        profiles.extend(["--profile", "smartlog"])
    # dedupe services list while preserving order
    seen = set()
    svc = []
    for s in services:
        if s not in seen:
            seen.add(s)
            svc.append(s)
    if not svc:
        notes.append("no configured services are available to start")
        return notes
    cmd_extra = profiles + ["up", "-d"] + svc
    code, out = _compose(root, *cmd_extra)
    notes.append(f"up {','.join(svc)}: {'ok' if code == 0 else out[:120]}")
    return notes


def apply_profile(root: Path, name: str) -> dict[str, Any]:
    """
    Apply a named profile. Before switching away from custom (or any profile),
    the previous flag mix is saved for `custom` restore when appropriate.
    """
    name = name.strip().lower()
    profiles = load_profiles(root)
    eu.ensure_env_file(root)
    env = eu.parse_env(eu.env_path(root))
    prev = (env.get("RAVI_PROFILE") or "custom").strip().lower()

    # Always snapshot current flags before change so custom can restore
    if name != "custom":
        save_custom_snapshot(root)

    result: dict[str, Any] = {"profile": name, "notes": []}

    if name == "custom":
        snap = load_custom_snapshot(root)
        if not snap:
            result["ok"] = False
            result["error"] = (
                "No custom snapshot yet. Change settings manually, then switch "
                "profiles once — Ravi will remember that mix as custom."
            )
            return result
        apply_env_flags(root, {**snap, "RAVI_PROFILE": "custom"})
        # Heuristic services for custom based on flags
        stop = []
        keep = ["redis", "db", "litellm", "llama"]
        if snap.get("RAVI_SMART_LOG", "off").lower() in ("on", "1", "true"):
            keep.extend(["worker", "worker-beat"])
        else:
            stop.extend(["worker", "worker-beat"])
        if snap.get("RAVI_SENTRY", "off").lower() not in ("on", "1", "true"):
            stop.append("glitchtip")
        stop.append("flower")  # web still on-demand unless user starts it
        result["notes"] += stop_services(root, stop)
        result["notes"] += start_services(root, keep, web_uis=False)
        result["ok"] = True
        result["flags"] = snap
        return result

    if name not in profiles:
        result["ok"] = False
        result["error"] = f"Unknown profile '{name}'. Use: small, medium, large, extra, custom"
        return result

    spec = profiles[name]
    flags = {k: str(spec[k]) for k in PROFILE_KEYS if k in spec}
    flags["RAVI_PROFILE"] = name
    apply_env_flags(root, flags)

    stop = list(spec.get("services_stop") or [])
    keep = list(spec.get("services_keep") or [])
    web = bool(spec.get("web_uis"))

    result["notes"] += stop_services(root, stop)
    result["notes"] += start_services(root, keep, web_uis=web)
    result["ok"] = True
    result["flags"] = flags
    result["description"] = spec.get("description") or name
    return result
