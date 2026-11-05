"""Ravi runtime settings — backend, language, media toggles, hardware presets."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

from ravi import envutil as eu

DEFAULTS = {
    "RAVI_LLM_BACKEND": "llama",
    "RAVI_LANG": "en",
    "RAVI_VOICE": "on",
    "RAVI_IMAGE": "off",
    "RAVI_VIDEO": "off",
    "RAVI_CONTEXT": "",
    "RAVI_THREADS": "",
    "RAVI_DEFAULT_MODEL": "qwen3-4b-instruct-2507-q4km",
    "RAVI_VOICE_MODEL": "kokoro-82m-onnx-int8",
    "RAVI_IMAGE_MODEL": "sd15-q4_0",
    "RAVI_VIDEO_MODEL": "wan-video-placeholder",
    "RAVI_WELCOME_MESSAGE": "Hello! I am Ravi, your local AI gateway. Ask me anything.",
    "RAVI_LLM": "on",
    "RAVI_SMART_LOG": "off",
    "RAVI_STATUS": "off",
    "RAVI_MODELS_DIR": "./models",
    "RAVI_SENTRY": "on",
    "RAVI_PROFILE": "medium",
    "RAVI_STATE": "local",
    "RAVI_LAYA": "on",
    "RAVI_LAYA_VARIANT": "english",
    "RAVI_CONFIRMS": "medium",
    "RAVI_CONFIRMS_RISKS": "",
}

LANG_NAMES = {
    "en": "English",
    "fa": "Persian",
    "ar": "Arabic",
    "zh": "Chinese",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "tr": "Turkish",
    "hi": "Hindi",
    "pt": "Portuguese",
    "it": "Italian",
}


def _presets_path(root: Path) -> Path:
    return root / "config" / "hardware-presets.yaml"


def load_presets(root: Path) -> dict[str, Any]:
    p = _presets_path(root)
    if not p.is_file():
        return {"presets": [], "defaults": {}}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def detect_cpu_cores() -> int:
    try:
        return max(1, os.cpu_count() or 1)
    except Exception:
        return 1


def detect_ram_gb() -> int | None:
    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.is_file():
            for line in meminfo.read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return max(1, int(line.split()[1]) // (1024 * 1024))
    except Exception:
        pass
    try:
        p = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if p.returncode == 0 and p.stdout.strip().isdigit():
            return max(1, int(p.stdout.strip()) // (1024**3))
    except Exception:
        pass
    return None


def pick_hardware_preset(root: Path) -> dict[str, Any]:
    data = load_presets(root)
    presets = list(data.get("presets") or [])
    ram = detect_ram_gb() or 0
    cores = detect_cpu_cores()
    chosen = (
        presets[0]
        if presets
        else {"id": "fallback", "context": 8192, "threads": 4, "batch": 256, "gpu_layers": 0}
    )
    for row in presets:
        if ram >= int(row.get("min_ram_gb") or 0) and cores >= int(row.get("min_cores") or 0):
            chosen = row
    return {**chosen, "detected_ram_gb": ram or None, "detected_cores": cores}


def ensure_default_env(root: Path) -> dict[str, str]:
    eu.ensure_secrets(root)
    path = eu.env_path(root)
    env = eu.parse_env(path)
    presets = load_presets(root)
    file_defaults = presets.get("defaults") or {}

    mapping = {
        "RAVI_LLM_BACKEND": file_defaults.get("llm_backend", DEFAULTS["RAVI_LLM_BACKEND"]),
        "RAVI_LANG": file_defaults.get("language", DEFAULTS["RAVI_LANG"]),
        "RAVI_VOICE": file_defaults.get("voice", DEFAULTS["RAVI_VOICE"]),
        "RAVI_IMAGE": file_defaults.get("image", DEFAULTS["RAVI_IMAGE"]),
        "RAVI_VIDEO": file_defaults.get("video", DEFAULTS["RAVI_VIDEO"]),
        "RAVI_DEFAULT_MODEL": file_defaults.get("chat_model", DEFAULTS["RAVI_DEFAULT_MODEL"]),
        "RAVI_VOICE_MODEL": file_defaults.get("voice_model", DEFAULTS["RAVI_VOICE_MODEL"]),
        "RAVI_IMAGE_MODEL": file_defaults.get("image_model", DEFAULTS["RAVI_IMAGE_MODEL"]),
        "RAVI_VIDEO_MODEL": file_defaults.get("video_model", DEFAULTS["RAVI_VIDEO_MODEL"]),
        "RAVI_WELCOME_MESSAGE": DEFAULTS["RAVI_WELCOME_MESSAGE"],
        "RAVI_LLM": DEFAULTS["RAVI_LLM"],
        "RAVI_SMART_LOG": DEFAULTS["RAVI_SMART_LOG"],
        "RAVI_STATUS": DEFAULTS["RAVI_STATUS"],
        "RAVI_MODELS_DIR": DEFAULTS["RAVI_MODELS_DIR"],
        "RAVI_SENTRY": DEFAULTS["RAVI_SENTRY"],
        "RAVI_PROFILE": DEFAULTS["RAVI_PROFILE"],
        "RAVI_STATE": DEFAULTS["RAVI_STATE"],
        "RAVI_LAYA": DEFAULTS["RAVI_LAYA"],
        "RAVI_LAYA_VARIANT": DEFAULTS["RAVI_LAYA_VARIANT"],
        "RAVI_CONFIRMS": DEFAULTS["RAVI_CONFIRMS"],
    }
    for k, v in mapping.items():
        if not (env.get(k) or "").strip():
            try:
                eu.write_env_value(path, k, str(v))
            except Exception:
                pass
            env[k] = str(v)

    hw = pick_hardware_preset(root)
    if not (env.get("RAVI_CONTEXT") or "").strip():
        ctx = str(file_defaults.get("context") or hw.get("context") or 8192)
        try:
            eu.write_env_value(path, "RAVI_CONTEXT", ctx)
        except Exception:
            pass
        env["RAVI_CONTEXT"] = ctx
    if not (env.get("RAVI_THREADS") or "").strip():
        th = str(hw.get("threads") or detect_cpu_cores())
        try:
            eu.write_env_value(path, "RAVI_THREADS", th)
        except Exception:
            pass
        env["RAVI_THREADS"] = th

    return eu.parse_env(path)


def get(env: dict[str, str], key: str, default: str = "") -> str:
    return (env.get(key) or DEFAULTS.get(key) or default).strip()


def is_on(env: dict[str, str], key: str) -> bool:
    return get(env, key, "off").lower() in ("on", "1", "true", "yes")


def set_toggle(root: Path, key: str, value: str) -> None:
    eu.write_env_value(eu.env_path(root), key, value)


def language_system_prompt(lang_code: str, model_languages: list[str] | None) -> str:
    code = (lang_code or "en").lower()
    name = LANG_NAMES.get(code, code)
    supported = model_languages or ["en"]
    if code != "en" and code not in supported:
        return (
            f"The user prefers {name} ({code}), but this model is documented "
            f"for: {', '.join(supported)}. "
            "Reply in English and begin with: "
            '"This model supports English."'
        )
    if code == "en":
        return "Reply in English unless the user clearly requests another language."
    return f"Always reply in {name} ({code}). Match the user's language for all answers."


def snapshot(root: Path) -> dict[str, Any]:
    env = ensure_default_env(root)
    hw = pick_hardware_preset(root)
    return {
        "backend": get(env, "RAVI_LLM_BACKEND", "llama"),
        "language": get(env, "RAVI_LANG", "en"),
        "language_name": LANG_NAMES.get(get(env, "RAVI_LANG", "en"), "English"),
        "voice": get(env, "RAVI_VOICE", "off"),
        "image": get(env, "RAVI_IMAGE", "off"),
        "video": get(env, "RAVI_VIDEO", "off"),
        "context": get(env, "RAVI_CONTEXT", "8192"),
        "threads": get(env, "RAVI_THREADS", "4"),
        "default_model": get(env, "RAVI_DEFAULT_MODEL"),
        "voice_model": get(env, "RAVI_VOICE_MODEL"),
        "image_model": get(env, "RAVI_IMAGE_MODEL"),
        "video_model": get(env, "RAVI_VIDEO_MODEL"),
        "llm": get(env, "RAVI_LLM", "on"),
        "models_dir": get(env, "RAVI_MODELS_DIR", "./models"),
        "status": get(env, "RAVI_STATUS", "off"),
        "profile": get(env, "RAVI_PROFILE", "medium"),
        "state": get(env, "RAVI_STATE", "local"),
        "confirms": get(env, "RAVI_CONFIRMS", "medium"),
        "hardware": hw,
    }
