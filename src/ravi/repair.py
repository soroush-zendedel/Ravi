"""Interactive repair helper — optional LLM-guided fixes with user confirmation."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel

from ravi import envutil as eu
from ravi import media as rmedia
from ravi import settings as rsettings
from ravi.bootstrap import BootstrapReport, problems_summary

console = Console()

REPAIR_PERSONA = (
    "You are Ravi Repair — calm, brief, practical. "
    "Explain issues in plain English in short sentences. "
    "Propose at most 3 shell commands. Never suggest destructive rm -rf of home dirs."
)


def _proxy_chat(env: dict, messages: list[dict], model: str | None = None) -> str:
    key = env.get("LITELLM_MASTER_KEY")
    if not key:
        return ""
    base = eu.proxy_base_url()
    use_model = model or eu.get_default_model(env) or "gpt-3.5-turbo"
    try:
        with httpx.Client(timeout=90.0) as client:
            r = client.post(
                f"{base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": use_model,
                    "messages": messages,
                    "max_tokens": 600,
                },
            )
        if r.status_code >= 400:
            return ""
        data = r.json()
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
    except Exception:
        return ""


def _extract_commands(text: str) -> list[str]:
    cmds: list[str] = []
    in_fence = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or s.startswith("$ "):
            cmd = s[2:] if s.startswith("$ ") else s
            if cmd and not cmd.startswith("#"):
                cmds.append(cmd)
        elif s.startswith("sudo ") or s.startswith("ravi ") or s.startswith("docker "):
            cmds.append(s)
    # unique preserve order
    seen = set()
    out = []
    for c in cmds:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:5]


def _run_cmd_confirmed(cmd: str) -> str:
    console.print(f"[cyan]Proposed:[/] {cmd}")
    if not console.input("Run this command? [y/N] ").strip().lower().startswith("y"):
        return "skipped by user"
    try:
        p = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        tail = ((p.stdout or "") + (p.stderr or ""))[-800:]
        return f"exit {p.returncode}\n{tail}"
    except Exception as e:
        return f"error: {e}"


def offer_repair(root: Path, report: BootstrapReport) -> None:
    """Ask user whether to try LLM-assisted repair; never crashes the CLI."""
    if not report.has_problems:
        return

    env = report.env or (
        eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {}
    )
    summary = problems_summary(report)

    console.print(
        Panel(
            summary,
            title="[yellow]Startup issues[/]",
            border_style="yellow",
        )
    )

    try:
        ans = console.input(
            "Should the language model try to help fix these issues? [y/N] "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if not ans.startswith("y"):
        console.print("[dim]Skipped repair assistant.[/]")
        return

    # If LLM is off or proxy down, fall back to static hints
    static = []
    for c in report.errors + report.warnings:
        if c.hint:
            static.append(f"• {c.label}: {c.hint}")

    llm_on = (env.get("RAVI_LLM") or "on").lower() not in ("off", "0", "false")
    advice = ""
    if llm_on:
        messages = [
            {"role": "system", "content": REPAIR_PERSONA},
            {
                "role": "user",
                "content": (
                    "Ravi startup found these issues on the user machine:\n"
                    f"{summary}\n\n"
                    "Give a short diagnosis and up to 3 safe commands "
                    "(prefer `ravi share`, `ravi local pull`, `docker …`). "
                    "Use plain English."
                ),
            },
        ]
        advice = _proxy_chat(env, messages)

    if not advice:
        advice = "Automated repair is unavailable right now. Try:\n" + (
            "\n".join(static) if static else "• ravi share\n• ravi local pull\n• Start Docker"
        )

    console.print(Panel(advice, title="[cyan]Ravi Repair[/]", border_style="cyan"))
    try:
        rmedia.maybe_speak(advice[:400], env)
    except Exception:
        pass

    cmds = _extract_commands(advice)
    if not cmds and static:
        # map hints to simple commands
        for c in report.errors + report.warnings:
            if c.hint and c.hint.startswith("ravi "):
                cmds.append(c.hint)
    if not cmds:
        return

    console.print("[dim]Commands will only run if you confirm each one.[/]")
    results = []
    for cmd in cmds:
        try:
            results.append(f"$ {cmd}\n{_run_cmd_confirmed(cmd)}")
        except Exception as e:
            results.append(f"$ {cmd}\nerror: {e}")

    # Short wrap-up
    wrap = "Repair steps finished. Re-run `ravi start` if the stack was down."
    if llm_on:
        wrap_llm = _proxy_chat(
            env,
            [
                {"role": "system", "content": REPAIR_PERSONA},
                {
                    "role": "user",
                    "content": "Summarize these command results in 2 short sentences:\n"
                    + "\n".join(results)[:1500],
                },
            ],
        )
        if wrap_llm:
            wrap = wrap_llm
    console.print(Panel(wrap, title="[green]Summary[/]", border_style="green"))
    try:
        rmedia.maybe_speak(wrap[:300], env)
    except Exception:
        pass
