"""Local model helpers — Ollama + GGUF multi-mirror."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ravi.download import (
    DEFAULT_MODEL_ID,
    LOCAL_CATALOG,
    CatalogModel,
    download_model,
    find_local_gguf,
    get_catalog_model,
    list_local_ggufs,
    models_dir,
    remove_all_ggufs,
    remove_gguf,
)

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"


def ollama_host() -> str:
    return (
        os.environ.get("OLLAMA_HOST")
        or os.environ.get("RAVI_OLLAMA_URL")
        or DEFAULT_OLLAMA_HOST
    ).rstrip("/")


def ollama_bin() -> str | None:
    return shutil.which("ollama")


def ollama_reachable(timeout: float = 2.0) -> bool:
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{ollama_host()}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


def list_ollama_models() -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{ollama_host()}/api/tags")
            r.raise_for_status()
            return list((r.json() or {}).get("models") or [])
    except Exception:
        return []


def installed_model_names() -> list[str]:
    names: list[str] = []
    for m in list_ollama_models():
        name = m.get("name") or m.get("model") or ""
        if name:
            names.append(name)
    # docker fallback
    if not names:
        try:
            p = subprocess.run(
                ["docker", "exec", "ravi-ollama", "ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if p.returncode == 0:
                for line in p.stdout.splitlines()[1:]:
                    parts = line.split()
                    if parts:
                        names.append(parts[0])
        except Exception:
            pass
    return names


def scan_gguf_files(root: Path) -> list[Path]:
    return list_local_ggufs(root)


def litellm_model_id(ollama_name: str) -> str:
    safe = ollama_name.replace(":", "-").replace("/", "-")
    return f"local-{safe}"


def litellm_upstream(ollama_name: str) -> str:
    return f"ollama/{ollama_name}"


def ensure_ollama_running() -> tuple[bool, str]:
    if ollama_reachable():
        return True, f"Ollama reachable at {ollama_host()}"
    if ollama_bin():
        return False, "Ollama is installed but not running. Start it with: ollama serve"
    # docker
    try:
        p = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "ravi-ollama"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if p.returncode == 0 and "true" in p.stdout.lower():
            return True, "Ollama via ravi-ollama container"
    except Exception:
        pass
    return (
        False,
        "Ollama not found. Run `ravi start --no-chat` (includes ollama) or install https://ollama.com",
    )


def ollama_rm(name: str) -> bool:
    bin_path = ollama_bin()
    cmds = []
    if bin_path:
        cmds.append([bin_path, "rm", name])
    cmds.append(["docker", "exec", "ravi-ollama", "ollama", "rm", name])
    for cmd in cmds:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if p.returncode == 0:
                return True
        except Exception:
            continue
    return False


@dataclass
class LocalChoice:
    ollama_name: str
    ravi_model_name: str
    source: str  # installed | catalog | gguf
    path: Path | None = None


def pick_auto(root: Path) -> LocalChoice | None:
    """Prefer existing default GGUF, then any GGUF, then Ollama installs."""
    default = get_catalog_model(None)
    if default.hf_file:
        gguf = find_local_gguf(root, default.hf_file)
        if gguf:
            tag = default.ollama_tags[0] if default.ollama_tags else default.id
            return LocalChoice(tag, litellm_model_id(tag), "gguf", gguf)

    ggufs = list_local_ggufs(root)
    if ggufs:
        stem = ggufs[0].stem
        return LocalChoice(stem, f"local-gguf-{stem}", "gguf", ggufs[0])

    installed = installed_model_names()
    if installed:
        from ravi import envutil as eu

        env = eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {}
        default_env = (env.get("RAVI_DEFAULT_MODEL") or "").strip()
        for name in installed:
            if default_env in (litellm_model_id(name), name, f"ollama/{name}"):
                return LocalChoice(name, litellm_model_id(name), "installed")
        for m in LOCAL_CATALOG:
            for tag in m.ollama_tags:
                for name in installed:
                    if name == tag or name.startswith(tag.split(":")[0]):
                        return LocalChoice(name, litellm_model_id(name), "installed")
        name = installed[0]
        return LocalChoice(name, litellm_model_id(name), "installed")
    return None


def pull_model(ollama_name: str) -> subprocess.CompletedProcess:
    bin_path = ollama_bin()
    if not bin_path:
        raise RuntimeError("Ollama CLI not found")
    return subprocess.run([bin_path, "pull", ollama_name], check=False)
