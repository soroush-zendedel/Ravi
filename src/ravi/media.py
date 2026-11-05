"""Media toggles, RAM unload helpers, capability checks, prompt templates."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ravi import envutil as eu
from ravi import settings as rsettings


def prompts_dir(root: Path) -> Path:
    return root / "config" / "prompts"


def load_prompt(root: Path, name: str) -> str:
    path = prompts_dir(root) / f"{name}.md"
    if not path.is_file():
        return ""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def build_system_prompt(root: Path, env: dict[str, str], model_langs: list[str]) -> str:
    parts: list[str] = []
    lang = rsettings.get(env, "RAVI_LANG", "en")
    parts.append(rsettings.language_system_prompt(lang, model_langs))
    text_style = load_prompt(root, "text")
    if text_style:
        parts.append(text_style)
    if rsettings.is_on(env, "RAVI_VOICE"):
        voice_style = load_prompt(root, "voice")
        if voice_style:
            parts.append(voice_style)
    return "\n\n".join(p for p in parts if p)


def models_host_path(root: Path, env: dict[str, str] | None = None) -> Path:
    """Host path for GGUF / media weights (Windows-friendly via RAVI_MODELS_DIR)."""
    env = env or (eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {})
    raw = (env.get("RAVI_MODELS_DIR") or "").strip()
    if raw:
        # Support Windows paths; Docker Desktop converts them when mounted
        return Path(raw)
    return (root / "models").resolve()


def suggest_models_for(
    root: Path, capability: str, *, limit: int = 4
) -> list[str]:
    from ravi.download import load_catalog

    out: list[str] = []
    for m in load_catalog(root):
        if capability in (m.capabilities or []):
            out.append(f"{m.id} ({m.name})")
        if len(out) >= limit:
            break
    return out


def capability_error(root: Path, capability: str, model_id: str) -> str:
    suggestions = suggest_models_for(root, capability)
    lines = [
        f"This model cannot perform '{capability}'.",
        f"Active model: {model_id}",
        "Switch to a model that supports this capability.",
    ]
    if suggestions:
        lines.append("Suggestions:")
        for s in suggestions:
            lines.append(f"  - {s}")
    else:
        lines.append(
            "No model in the local catalog lists this capability. "
            "Try a cloud provider key (ravi keys add …) or enable another backend."
        )
    lines.append(
        "Commands: ravi local list --all  ·  ravi use <model>  ·  ravi image on"
    )
    return "\n".join(lines)


def docker_stop_stack(root: Path) -> tuple[bool, str]:
    """Stop all Ravi containers (free host RAM). CLI remains installed."""
    try:
        p = subprocess.run(
            ["docker", "compose", "-f", str(root / "docker-compose.yml"), "down"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if p.returncode == 0:
            return True, "Containers stopped. RAM released. Run `ravi start` to return."
        return False, (p.stderr or p.stdout or "docker compose down failed")[-500:]
    except Exception as e:
        return False, str(e)


def docker_stop_service(root: Path, service: str) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(root / "docker-compose.yml"),
                "stop",
                service,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if p.returncode == 0:
            return True, f"Service '{service}' stopped."
        return False, (p.stderr or p.stdout or "stop failed")[-400:]
    except Exception as e:
        return False, str(e)


def unload_llm(root: Path, env: dict[str, str]) -> str:
    """Turn off language model runtime to free RAM."""
    eu.write_env_value(eu.env_path(root), "RAVI_LLM", "off")
    backend = rsettings.get(env, "RAVI_LLM_BACKEND", "llama")
    notes = ["Language model marked OFF."]
    if backend == "ollama":
        ok, msg = docker_stop_service(root, "ollama")
        notes.append(msg if ok else f"Could not stop ollama: {msg}")
    else:
        ok, msg = docker_stop_service(root, "llama")
        notes.append(msg if ok else f"Could not stop llama: {msg}")
    return " ".join(notes)


def load_llm(root: Path) -> str:
    eu.write_env_value(eu.env_path(root), "RAVI_LLM", "on")
    return "Language model marked ON. Run `ravi start` if containers are down."


def maybe_speak(text: str, env: dict[str, str]) -> None:
    """Best-effort local TTS when voice is on (Kokoro / system fallback)."""
    if not rsettings.is_on(env, "RAVI_VOICE"):
        return
    # Placeholder: system say / espeak if present; full Kokoro wired later
    for cmd in (
        ["espeak", text[:500]],
        ["say", text[:500]],
        ["powershell", "-Command", f"Add-Type –AssemblyName System.Speech; "
         f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text[:200].replace(chr(39), '')}')"],
    ):
        try:
            subprocess.run(cmd, capture_output=True, timeout=30, check=False)
            return
        except Exception:
            continue


def assert_capability(
    root: Path, env: dict[str, str], capability: str, model_id: str
) -> None:
    """Raise SystemExit-style message string if capability missing or toggle off."""
    from ravi.download import load_catalog

    toggle_map = {
        "image_gen": "RAVI_IMAGE",
        "audio_tts": "RAVI_VOICE",
        "audio_asr": "RAVI_VOICE",
        "video": "RAVI_VIDEO",
    }
    tkey = toggle_map.get(capability)
    if tkey and not rsettings.is_on(env, tkey):
        raise RuntimeError(
            f"{capability} is turned OFF. Enable with the matching command "
            f"(ravi image on / ravi voice on / ravi video on)."
        )

    # Catalog check (local ids); cloud models may still work via LiteLLM
    cats = {m.id: m for m in load_catalog(root)}
    # strip local- prefix variants
    mid = model_id
    for m in cats.values():
        if mid == m.id or mid.endswith(m.id) or m.id in mid:
            if capability not in (m.capabilities or []) and capability not in (
                "chat",
            ):
                raise RuntimeError(capability_error(root, capability, model_id))
            return
    # unknown model — allow chat; block media with guidance
    if capability in ("image_gen", "audio_tts", "video"):
        raise RuntimeError(capability_error(root, capability, model_id))
