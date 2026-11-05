"""Runtime state: local | cloud | both."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ravi import envutil as eu
from ravi import profiles as rprof
from ravi.providers import PROVIDERS, get_provider


def get_state(root: Path) -> str:
    env = eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {}
    s = (env.get("RAVI_STATE") or "local").strip().lower()
    if s not in ("local", "cloud", "both"):
        return "local"
    return s


def set_state_flag(root: Path, state: str) -> None:
    eu.ensure_env_file(root)
    eu.write_env_value(eu.env_path(root), "RAVI_STATE", state)


def free_local_runtime(root: Path) -> list[str]:
    """Stop local LLM containers and mark local LLM off to free RAM."""
    notes = []
    try:
        eu.write_env_value(eu.env_path(root), "RAVI_LLM", "off")
    except Exception as e:
        notes.append(f"env: {e}")
    for svc in ("llama", "ollama", "worker"):
        try:
            p = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(root / "docker-compose.yml"),
                    "stop",
                    svc,
                ],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=60,
            )
            notes.append(f"stop {svc}: {'ok' if p.returncode == 0 else 'skip'}")
        except Exception as e:
            notes.append(f"stop {svc}: {e}")
    return notes


def ensure_cloud_model(root: Path, console, ask_input) -> dict[str, Any]:
    """
    Ensure a cloud model + key exist. Interactive if missing.
    Returns {ok, model, provider, notes}.
    """
    env = eu.parse_env(eu.env_path(root))
    model = (env.get("RAVI_CLOUD_MODEL") or env.get("RAVI_DEFAULT_MODEL") or "").strip()
    notes = []

    # Detect any cloud key present
    key_map = [
        ("gemini", "GEMINI_API_KEY_1", "gemini-3.5-flash"),
        ("gemini", "GEMINI_API_KEY", "gemini-3.5-flash"),
        ("groq", "GROQ_API_KEY", "groq-llama-3.1-8b"),
        ("openrouter", "OPENROUTER_API_KEY", "openrouter-llama-3.3-70b-free"),
        ("openai", "OPENAI_API_KEY", "gpt-4o-mini"),
        ("anthropic", "ANTHROPIC_API_KEY", "claude-3-5-haiku"),
        ("cloudflare", "CLOUDFLARE_API_TOKEN", "cf-gpt-oss-20b"),
    ]
    available = []
    for prov, env_key, default_model in key_map:
        val = (env.get(env_key) or "").strip()
        if val and not val.startswith("your_") and "change_me" not in val and "YOUR_" not in val:
            available.append((prov, env_key, default_model, val))

    if available and model and not model.startswith("local-") and not model.startswith("qwen3-4b"):
        # already have cloud-ish default
        eu.write_env_value(eu.env_path(root), "RAVI_CLOUD_MODEL", model)
        eu.write_env_value(eu.env_path(root), "RAVI_DEFAULT_MODEL", model)
        return {"ok": True, "model": model, "provider": available[0][0], "notes": notes}

    if available:
        # pick first available provider default model
        prov, env_key, default_model, _ = available[0]
        eu.write_env_value(eu.env_path(root), "RAVI_CLOUD_MODEL", default_model)
        eu.write_env_value(eu.env_path(root), "RAVI_DEFAULT_MODEL", default_model)
        notes.append(f"Using existing {prov} key → model {default_model}")
        return {"ok": True, "model": default_model, "provider": prov, "notes": notes}

    # Interactive selection
    console.print("[bold cyan]Cloud setup[/] — no API key found yet.")
    providers = [
        ("1", "gemini", "GEMINI_API_KEY_1", "gemini-3.5-flash", "Google Gemini (free tier)"),
        ("2", "groq", "GROQ_API_KEY", "groq-llama-3.1-8b", "Groq (free tier)"),
        ("3", "openrouter", "OPENROUTER_API_KEY", "openrouter-llama-3.3-70b-free", "OpenRouter free"),
        ("4", "openai", "OPENAI_API_KEY", "gpt-4o-mini", "OpenAI"),
        ("5", "anthropic", "ANTHROPIC_API_KEY", "claude-3-5-haiku", "Anthropic"),
    ]
    for num, _p, _k, _m, label in providers:
        console.print(f"  {num}. {label}")
    choice = (ask_input("Choose provider [1-5]: ") or "1").strip()
    selected = providers[0]
    for row in providers:
        if row[0] == choice:
            selected = row
            break
    _, prov, env_key, default_model, label = selected
    key = (ask_input(f"Paste API key for {label}: ") or "").strip()
    if not key:
        return {"ok": False, "error": "No API key entered.", "notes": notes}
    eu.write_env_value(eu.env_path(root), env_key, key)
    eu.write_env_value(eu.env_path(root), "RAVI_CLOUD_MODEL", default_model)
    eu.write_env_value(eu.env_path(root), "RAVI_DEFAULT_MODEL", default_model)
    notes.append(f"Saved {env_key} and model {default_model}")
    return {"ok": True, "model": default_model, "provider": prov, "notes": notes}


def apply_cloud(root: Path, console, ask_input) -> dict[str, Any]:
    notes = free_local_runtime(root)
    setup = ensure_cloud_model(root, console, ask_input)
    if not setup.get("ok"):
        return setup
    set_state_flag(root, "cloud")
    # light profile-ish flags for cloud-only
    try:
        eu.write_env_value(eu.env_path(root), "RAVI_VOICE", "off")
        eu.write_env_value(eu.env_path(root), "RAVI_IMAGE", "off")
        eu.write_env_value(eu.env_path(root), "RAVI_VIDEO", "off")
    except Exception:
        pass
    notes.extend(setup.get("notes") or [])
    return {
        "ok": True,
        "state": "cloud",
        "model": setup.get("model"),
        "notes": notes,
    }


def apply_local(root: Path) -> dict[str, Any]:
    set_state_flag(root, "local")
    try:
        eu.write_env_value(eu.env_path(root), "RAVI_LLM", "on")
    except Exception:
        pass
    # custom if snapshot exists else medium
    snap = rprof.load_custom_snapshot(root)
    if snap:
        result = rprof.apply_profile(root, "custom")
        result["state"] = "local"
        result["fallback"] = "custom"
        return result
    result = rprof.apply_profile(root, "medium")
    result["state"] = "local"
    result["fallback"] = "medium"
    return result


def apply_both(root: Path, console, ask_input) -> dict[str, Any]:
    """Local orchestrator + cloud responder."""
    set_state_flag(root, "both")
    try:
        eu.write_env_value(eu.env_path(root), "RAVI_LLM", "on")
    except Exception:
        pass
    setup = ensure_cloud_model(root, console, ask_input)
    notes = list(setup.get("notes") or [])
    if not setup.get("ok"):
        return setup
    # ensure medium-ish local side
    snap = rprof.load_custom_snapshot(root)
    if not snap:
        rprof.apply_profile(root, "medium")
        notes.append("Local side: medium profile")
    eu.write_env_value(eu.env_path(root), "RAVI_STATE", "both")
    return {
        "ok": True,
        "state": "both",
        "model": setup.get("model"),
        "notes": notes,
        "description": (
            "User messages go to a local planner first; it builds context for the "
            "cloud model; the cloud answer is returned to you."
        ),
    }


def both_system_prompt() -> str:
    return (
        "You are Ravi's local planner in BOTH mode. "
        "Rewrite the user's request into a clear, self-contained prompt for a cloud model. "
        "Keep the user's language. Do not answer the user yourself — only produce the "
        "improved prompt text for the cloud model."
    )
