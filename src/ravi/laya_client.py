"""Laya decision-model client (LiteLLM /v1/systemone or direct HTTP)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import yaml


def schemas_path(root: Path) -> Path:
    return root / "config" / "laya" / "schemas.yaml"


def load_schemas(root: Path) -> dict[str, Any]:
    path = schemas_path(root)
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def laya_enabled(env: dict[str, str]) -> bool:
    return (env.get("RAVI_LAYA") or "off").strip().lower() in (
        "on",
        "1",
        "true",
        "yes",
    )


def laya_model_name(env: dict[str, str]) -> str:
    # English-only by default (lower RAM); multilingual for large+
    variant = (env.get("RAVI_LAYA_VARIANT") or "english").strip().lower()
    if variant in ("multilingual", "multi", "full"):
        return env.get("RAVI_LAYA_MODEL") or "laya-multilingual"
    return env.get("RAVI_LAYA_MODEL") or "laya-english"


def laya_api_base(env: dict[str, str]) -> str:
    return (
        env.get("LAYA_API_BASE")
        or env.get("RAVI_LAYA_URL")
        or "http://127.0.0.1:8090"
    ).rstrip("/")


def systemone(
    root: Path,
    env: dict[str, str],
    *,
    state: str,
    questions: dict[str, Any],
    proxy_key: str | None = None,
) -> dict[str, Any]:
    """
    Call Laya via LiteLLM /v1/systemone when available, else direct Laya serve.
    Returns raw answers dict or empty on soft failure.
    """
    if not laya_enabled(env):
        return {}

    model = laya_model_name(env)
    payload = {
        "model": model,
        "state": state,
        "questions": questions,
    }
    headers = {"Content-Type": "application/json"}
    if proxy_key:
        headers["Authorization"] = f"Bearer {proxy_key}"

    # Prefer LiteLLM gateway systemone
    from ravi import envutil as eu

    proxy = eu.proxy_base_url()
    urls = [
        f"{proxy}/v1/systemone",
        f"{proxy}/systemone",
        f"{laya_api_base(env)}/v1/systemone",
        f"{laya_api_base(env)}/systemone",
    ]
    last_err = None
    for url in urls:
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.post(url, json=payload, headers=headers)
            if r.status_code < 400:
                data = r.json()
                # normalize
                if isinstance(data, dict):
                    if "answers" in data:
                        return data
                    return {"answers": data, "raw": data}
            last_err = f"{url} → HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)
            continue

    # Soft heuristic fallback so chat never hard-crashes without Laya server
    return {
        "answers": _heuristic_answers(state, questions),
        "fallback": True,
        "error": last_err,
    }


def _heuristic_answers(state: str, questions: dict[str, Any]) -> dict[str, Any]:
    """Minimal offline stand-in when Laya server is not running."""
    text = (state or "").lower()
    answers: dict[str, Any] = {}
    for qid, q in (questions or {}).items():
        qtype = (q.get("type") or "choice").lower()
        if qtype == "choice":
            criteria = list((q.get("criteria") or {}).keys()) or ["other"]
            choice = criteria[-1]
            for c in criteria:
                if c in text or any(w in text for w in c.split("_")):
                    choice = c
                    break
            if any(w in text for w in ("delete", "rm ", "remove", "format")):
                if "dangerous" in criteria:
                    choice = "dangerous"
                elif "destructive" in str(criteria):
                    choice = criteria[0]
            answers[qid] = {
                "choice": choice,
                "confidence": 0.4,
                "probabilities": {c: (0.6 if c == choice else 0.1) for c in criteria},
            }
        elif qtype == "noul":
            pos = any(
                w in text
                for w in ("delete", "remove", "drop", "wipe", "format", "kill")
            )
            if "read_only" in qid or "read-only" in (q.get("instructions") or "").lower():
                answers[qid] = {"noul": 0.2 if pos else 0.85}
            else:
                answers[qid] = {"noul": 0.85 if pos else 0.15}
        elif qtype == "score":
            answers[qid] = {"score": 1.0}
        else:
            answers[qid] = {"raw": None}
    return answers
