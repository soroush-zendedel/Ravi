"""Orchestrator + policy: validate Laya output and decide chat flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ravi.laya_client import load_schemas, systemone, laya_enabled


def run_decision(
    root: Path,
    env: dict[str, str],
    *,
    user_text_en: str,
    proxy_key: str | None = None,
) -> dict[str, Any]:
    """
    Run fixed schemas through Laya and apply policy.
    Returns {
      laya_raw, decisions, policy_action, allow_answer, user_hint
    }
    """
    if not laya_enabled(env):
        return {
            "laya_raw": None,
            "decisions": {},
            "policy_action": "answer_directly",
            "allow_answer": True,
            "user_hint": None,
            "skipped": True,
        }

    schemas = load_schemas(root)
    # Combine fixed schemas (one forward pass)
    questions: dict[str, Any] = {}
    for key in ("intent_schema", "risk_schema", "routing_schema"):
        block = schemas.get(key) or {}
        questions.update(block)

    raw = systemone(
        root,
        env,
        state=user_text_en,
        questions=questions,
        proxy_key=proxy_key,
    )
    answers = (raw or {}).get("answers") or {}

    # --- Policy (independent of Laya forging) ---
    destructive = float((answers.get("destructive") or {}).get("noul") or 0)
    read_only = float((answers.get("read_only") or {}).get("noul") or 0)
    intent = (answers.get("intent") or {}).get("choice") or "other"
    route = (answers.get("route") or {}).get("choice") or "answer_directly"
    conf = float((answers.get("intent") or {}).get("confidence") or 0)

    action = "answer_directly"
    allow = True
    hint = None

    if destructive >= 0.80 or intent == "dangerous" or route == "refuse":
        action = "require_approval"
        allow = True  # still allow LLM to explain risks; tools blocked separately
        hint = (
            "This request may be destructive. Ravi will answer carefully and will not "
            "run irreversible actions without explicit approval."
        )
    elif route == "need_clarification" or (intent == "other" and conf < 0.45):
        action = "ask_clarification"
        hint = "The request looks ambiguous; ask a short clarifying question first."
    elif route == "use_tools":
        action = "use_tools"
    elif route == "require_approval":
        action = "require_approval"
        hint = "This action needs your confirmation before any side effects."
    elif read_only >= 0.90 or route == "answer_directly":
        action = "answer_directly"

    return {
        "laya_raw": raw,
        "decisions": {
            "intent": intent,
            "route": route,
            "destructive": destructive,
            "read_only": read_only,
            "confidence": conf,
        },
        "policy_action": action,
        "allow_answer": allow,
        "user_hint": hint,
        "skipped": False,
        "fallback": bool((raw or {}).get("fallback")),
    }


def enrich_system_prompt(base: str, decision: dict[str, Any]) -> str:
    """Attach orchestrator guidance for the final LLM reply. Never invent Laya scores."""
    if decision.get("skipped"):
        return base
    parts = [base]
    d = decision.get("decisions") or {}
    parts.append(
        "Orchestrator context (from Laya decision model — treat as advisory metadata, "
        "do not invent different scores):\n"
        f"- intent: {d.get('intent')}\n"
        f"- route: {d.get('route')}\n"
        f"- policy_action: {decision.get('policy_action')}\n"
        f"- destructive_score: {d.get('destructive')}\n"
        f"- read_only_score: {d.get('read_only')}"
    )
    if decision.get("user_hint"):
        parts.append(f"Policy note for your reply: {decision['user_hint']}")
    if decision.get("fallback"):
        parts.append(
            "Note: Laya server was unavailable; a conservative local heuristic was used."
        )
    return "\n\n".join(p for p in parts if p)
