"""Lightweight config.yaml model list helpers (comment-preserving append)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ravi.providers import MODEL_SNIPPETS


VERIFIED_GEMINI_MODEL_IDS = frozenset(
    {
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
    }
)
RETIRED_GEMINI_MODEL_IDS = frozenset(
    {
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-3.1-flash-lite-preview",
    }
)


@dataclass(frozen=True)
class ConfigIssue:
    severity: str
    message: str


def validate_config(cfg: dict[str, Any]) -> list[ConfigIssue]:
    """Check configured Gemini upstream IDs against Ravi's verified model catalog."""
    issues: list[ConfigIssue] = []
    for index, entry in enumerate(cfg.get("model_list") or []):
        if not isinstance(entry, dict):
            continue
        params = entry.get("litellm_params") or {}
        if not isinstance(params, dict):
            continue
        upstream = str(params.get("model") or "")
        if not upstream.startswith("gemini/"):
            continue

        model_id = upstream.removeprefix("gemini/")
        name = str(entry.get("model_name") or f"model_list[{index}]")
        if not model_id:
            issues.append(
                ConfigIssue("error", f"{name}: Gemini upstream model ID is empty.")
            )
        elif model_id in RETIRED_GEMINI_MODEL_IDS:
            issues.append(
                ConfigIssue(
                    "error",
                    f"{name}: Gemini model '{model_id}' is retired; update its upstream ID.",
                )
            )
        elif model_id not in VERIFIED_GEMINI_MODEL_IDS:
            issues.append(
                ConfigIssue(
                    "warn",
                    f"{name}: Gemini model '{model_id}' is not in Ravi's verified model catalog; confirm it against Google's current model list.",
                )
            )
    return issues


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def existing_model_names(cfg: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for entry in cfg.get("model_list") or []:
        if isinstance(entry, dict) and entry.get("model_name"):
            names.add(entry["model_name"])
    return names


def _snippet_to_yaml(snippet: dict) -> str:
    name = snippet["model_name"]
    params = snippet.get("litellm_params") or {}
    lines = [
        f"  - model_name: {name}",
        "    litellm_params:",
        f"      model: {params.get('model', '')}",
    ]
    if "api_base" in params:
        lines.append(f"      api_base: {params['api_base']}")
    if "api_key" in params:
        lines.append(f"      api_key: {params['api_key']}")
    return "\n".join(lines) + "\n"


def ensure_provider_models(config_path: Path, provider_id: str) -> list[str]:
    """Append curated models for a cloud provider if missing."""
    snippets = MODEL_SNIPPETS.get(provider_id, [])
    if not snippets:
        return []

    cfg = load_config(config_path)
    existing = existing_model_names(cfg)
    to_add = [s for s in snippets if s["model_name"] not in existing]
    if not to_add:
        return []

    text = config_path.read_text(encoding="utf-8")
    block = (
        f"\n  # --- added by `ravi keys add {provider_id}` ---\n"
        + "".join(_snippet_to_yaml(s) for s in to_add)
    )

    marker = "\ngeneral_settings:"
    if marker in text:
        text = text.replace(marker, block + marker, 1)
    else:
        text = text.rstrip() + "\n" + block

    config_path.write_text(text, encoding="utf-8")
    return [s["model_name"] for s in to_add]


def ensure_ollama_model(
    config_path: Path,
    ollama_name: str,
    ravi_name: str,
    api_base: str = "os.environ/OLLAMA_API_BASE",
) -> bool:
    """Register an Ollama model in config.yaml if missing. Returns True if added."""
    cfg = load_config(config_path)
    if ravi_name in existing_model_names(cfg):
        return False

    block = (
        f"\n  # --- local ollama: {ollama_name} ---\n"
        f"  - model_name: {ravi_name}\n"
        f"    litellm_params:\n"
        f"      model: ollama/{ollama_name}\n"
        f"      api_base: {api_base}\n"
    )
    text = config_path.read_text(encoding="utf-8")
    marker = "\ngeneral_settings:"
    if marker in text:
        text = text.replace(marker, block + marker, 1)
    else:
        text = text.rstrip() + "\n" + block
    config_path.write_text(text, encoding="utf-8")
    return True
