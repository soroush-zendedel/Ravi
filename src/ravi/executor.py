"""Shell / project command execution gated by Laya + user confirmation."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ravi.laya_client import load_schemas, systemone, laya_enabled
from datetime import datetime, timezone

# RAVI_CONFIRMS: how sensitive user approval is (when Laya is on)
# low    → confirm only if risk score >= 0.66
# medium → >= 0.33
# high   → >= 0.18  (ask more often)
CONFIRM_THRESHOLDS = {
    "low": 0.66,
    "medium": 0.33,
    "high": 0.18,
}

RISK_LEVEL_SCORE = {
    "safe": 0.05,
    "low": 0.20,
    "medium": 0.45,
    "high": 0.75,
    "critical": 0.95,
}


def confirms_mode(env: dict[str, str]) -> str:
    m = (env.get("RAVI_CONFIRMS") or "medium").strip().lower()
    if m in CONFIRM_THRESHOLDS:
        return m
    if m in ("custom", "risks", "percent", "pct"):
        return "custom"
    return "medium"


def confirms_threshold(env: dict[str, str]) -> float:
    """Return 0..1 threshold. Custom percent from RAVI_CONFIRMS_RISKS (0-100)."""
    mode = confirms_mode(env)
    if mode == "custom" or (env.get("RAVI_CONFIRMS_RISKS") or "").strip():
        raw = (env.get("RAVI_CONFIRMS_RISKS") or "").strip()
        if raw:
            try:
                pct = float(raw)
                return max(0.0, min(1.0, pct / 100.0))
            except ValueError:
                pass
    if mode in CONFIRM_THRESHOLDS:
        return CONFIRM_THRESHOLDS[mode]
    return CONFIRM_THRESHOLDS["medium"]


def risk_score_from_decision(
    risk_level: str,
    needs_approval: float,
    touches_remote: float,
    long_running: float,
    destructive: float,
) -> float:
    """Single 0..1 score combining Laya signals for threshold compare."""
    base = RISK_LEVEL_SCORE.get((risk_level or "medium").lower(), 0.45)
    return max(
        base,
        float(needs_approval or 0),
        float(touches_remote or 0) * 0.9,
        float(long_running or 0) * 0.7,
        float(destructive or 0),
    )


# Always require approval (even without Laya) for these patterns
HARD_DENY_PATTERNS = (
    "rm -rf /",
    "mkfs",
    ":(){",
    "dd if=",
    "shutdown",
    "reboot",
)

ALWAYS_CONFIRM_PREFIXES = (
    "git push",
    "git push --force",
    "git push -f",
    "git reset --hard",
    "git clean",
    "rm -rf",
    "sudo ",
    "docker system prune",
    "kubectl delete",
    "npm publish",
    "pip uninstall",
)


@dataclass
class CommandDecision:
    command: str
    policy_action: str  # allow | confirm | deny
    laya: dict[str, Any]
    reason: str
    risk_level: str = "medium"


def evaluate_command(
    root: Path,
    env: dict[str, str],
    command: str,
    *,
    proxy_key: str | None = None,
) -> CommandDecision:
    """Ask Laya (when on) whether a proposed CLI command needs approval."""
    cmd = (command or "").strip()
    low = cmd.lower()

    for bad in HARD_DENY_PATTERNS:
        if bad in low:
            return CommandDecision(
                command=cmd,
                policy_action="deny",
                laya={},
                reason=f"Blocked by hard safety rule ({bad!r}).",
                risk_level="critical",
            )

    force_confirm = any(low.startswith(p) or f" {p}" in low for p in ALWAYS_CONFIRM_PREFIXES)

    laya_raw: dict[str, Any] = {}
    risk = "medium"
    needs_approval = 0.5
    long_running = 0.2
    touches_remote = 0.2
    category = "other"

    if laya_enabled(env):
        schemas = load_schemas(root)
        questions = dict(schemas.get("command_risk_schema") or {})
        # also fold destructive from risk_schema
        risk_q = schemas.get("risk_schema") or {}
        for k, v in risk_q.items():
            if k not in questions:
                questions[k] = v
        state = (
            "Proposed shell command in Ravi CLI project context:\n"
            + cmd
            + "\nDecide risk for executing this on the developer machine."
        )
        laya_raw = systemone(
            root, env, state=state, questions=questions, proxy_key=proxy_key
        )
        answers = (laya_raw or {}).get("answers") or {}
        risk = (answers.get("risk_level") or {}).get("choice") or risk
        needs_approval = float((answers.get("needs_approval") or {}).get("noul") or needs_approval)
        long_running = float((answers.get("long_running") or {}).get("noul") or long_running)
        touches_remote = float((answers.get("touches_remote") or {}).get("noul") or touches_remote)
        category = (answers.get("category") or {}).get("choice") or category
        destructive = float((answers.get("destructive") or {}).get("noul") or 0)
    else:
        # heuristic without Laya
        if force_confirm or any(
            x in low for x in ("push", "reset --hard", "rm ", "sudo", "publish")
        ):
            needs_approval = 0.95
            risk = "high"
        destructive = 0.9 if risk in ("high", "critical") else 0.1

    # Combined risk score 0..1 vs RAVI_CONFIRMS threshold
    score = risk_score_from_decision(
        risk, needs_approval, touches_remote, long_running, destructive
    )
    thr = confirms_threshold(env)
    mode = confirms_mode(env)

    if risk == "critical" and any(b in low for b in HARD_DENY_PATTERNS):
        action = "deny"
        reason = f"Blocked hard rule (score={score:.2f})"
    elif score >= 0.98 and risk == "critical":
        action = "deny"
        reason = f"Critical risk denied (score={score:.2f})"
    elif force_confirm or score >= thr:
        action = "confirm"
        reason = (
            f"Confirm required (score={score:.2f} >= threshold={thr:.2f}, "
            f"mode={mode}, risk={risk}, category={category})"
        )
    else:
        action = "allow"
        reason = (
            f"Allowed without prompt (score={score:.2f} < {thr:.2f}, "
            f"mode={mode}, risk={risk})"
        )

    return CommandDecision(
        command=cmd,
        policy_action=action,
        laya=laya_raw,
        reason=reason,
        risk_level=risk,
    )


def _log_confirm(env: dict[str, str], command: str, decision: CommandDecision, outcome: str) -> None:
    """Persist confirmation events when logging is available."""
    try:
        from ravi import logstore as rlog

        rlog.log_event(
            "command_confirm",
            f"{outcome}: {command[:200]}",
            category="security",
            level="info",
            tags=["confirm", outcome, decision.risk_level],
            payload={
                "command": command,
                "outcome": outcome,  # required | approved | declined | denied | allowed
                "risk_level": decision.risk_level,
                "policy": decision.policy_action,
                "reason": decision.reason,
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            env=env,
        )
    except Exception:
        pass


def run_command_safe(
    root: Path,
    env: dict[str, str],
    command: str,
    *,
    cwd: Path | None = None,
    proxy_key: str | None = None,
    confirm_fn: Callable[[str, CommandDecision], bool] | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """
    Evaluate with Laya → optional user confirm → execute.
    Returns {ok, decision, stdout, stderr, code}.
    """
    decision = evaluate_command(root, env, command, proxy_key=proxy_key)
    if decision.policy_action == "deny":
        _log_confirm(env, command, decision, "denied")
        return {
            "ok": False,
            "decision": decision,
            "stdout": "",
            "stderr": decision.reason,
            "code": 126,
        }
    if decision.policy_action == "confirm":
        _log_confirm(env, command, decision, "required")
        approved = False
        if confirm_fn:
            approved = bool(confirm_fn(command, decision))
        if not approved:
            _log_confirm(env, command, decision, "declined")
            return {
                "ok": False,
                "decision": decision,
                "stdout": "",
                "stderr": "User declined execution.",
                "code": 130,
            }
        _log_confirm(env, command, decision, "approved")
    else:
        _log_confirm(env, command, decision, "allowed")

    try:
        p = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd or root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": p.returncode == 0,
            "decision": decision,
            "stdout": p.stdout or "",
            "stderr": p.stderr or "",
            "code": p.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "decision": decision,
            "stdout": "",
            "stderr": f"Timed out after {timeout}s (long-running).",
            "code": 124,
        }
    except Exception as e:
        return {
            "ok": False,
            "decision": decision,
            "stdout": "",
            "stderr": str(e),
            "code": 1,
        }


def laya_tool_spec() -> dict[str, Any]:
    """OpenAI-style tool definition so the LLM can call Laya explicitly."""
    return {
        "type": "function",
        "function": {
            "name": "laya_decide",
            "description": (
                "Ask Ravi's local Laya decision model to score a user request or "
                "proposed shell command (risk, approval need, intent). "
                "Use before running risky or long commands (e.g. git push)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "Text or proposed command to evaluate",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["request", "command"],
                        "description": "request=chat intent; command=shell risk",
                    },
                },
                "required": ["state"],
            },
        },
    }


def run_shell_tool_spec() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "Execute a shell command in the project directory. "
                "Ravi always runs Laya risk checks and may ask the user to confirm."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run, e.g. git status",
                    }
                },
                "required": ["command"],
            },
        },
    }
