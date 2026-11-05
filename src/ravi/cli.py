"""Ravi CLI — friendly control plane for your local AI infrastructure."""

from __future__ import annotations

import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

import httpx
import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ravi import __version__
from ravi import envutil as eu
from ravi import local as loc
from ravi.configedit import (
    ensure_ollama_model,
    ensure_provider_models,
    existing_model_names,
    load_config,
)
from ravi.providers import PROVIDERS, get_provider, provider_ids
from ravi.stages import StageRunner, banner, run_command_with_logs
from ravi import settings as rsettings
from ravi import media as rmedia
from ravi import share as rshare
from ravi.bootstrap import run_bootstrap
from ravi.repair import offer_repair
from ravi import logstore as rlog
from ravi import sentryutil as rsent
from ravi import profiles as rprof
from ravi import state as rstate
from ravi import orchestrator as rorch
from ravi.laya_client import laya_enabled
from ravi import laya_download as layadl
from ravi import laya_service as layasvc
from ravi import executor as rexec
from ravi.ready import compose_up_all, wait_until_active, set_status_flag, collect_status

app = typer.Typer(
    name="ravi",
    help=(
        "[bold cyan]Ravi[/] — Open Source AI Infrastructure\n\n"
        "[dim]Powered by Openness. Built for Everyone.[/]\n\n"
        "Spin up a local AI gateway, plug in free-tier keys, "
        "and chat without wrestling YAML."
    ),
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()

keys_app = typer.Typer(
    help="Manage provider API keys (stored in .env — never committed).",
    no_args_is_help=True,
)
app.add_typer(keys_app, name="keys")

local_app = typer.Typer(
    help="Local models via Ollama — download once, keep forever.",
    no_args_is_help=True,
)
app.add_typer(local_app, name="local")



@local_app.command("laya")
def local_laya(
    action: str = typer.Argument("status", help="status | pull"),
    model: str = typer.Option("laya-english", "--model", "-m"),
) -> None:
    """Manage local Laya weights under models/laya/ (same idea as GGUF)."""
    root = _root()
    if action == "status":
        table = Table(title="Laya local weights", border_style="cyan")
        table.add_column("Id")
        table.add_column("HF repo")
        table.add_column("Present")
        table.add_column("Path")
        for row in layadl.catalog(root):
            mid = row["id"]
            present = layadl.is_present(root, mid)
            dest = layadl.laya_root(root) / str(row.get("local_dir"))
            table.add_row(mid, row.get("hf_repo", ""), "yes" if present else "no", str(dest))
        console.print(table)
        _say("Pull: [cyan]ravi local laya pull -m laya-english[/]")
        return
    if action == "pull":
        _say(f"Downloading Laya [cyan]{model}[/] into models/laya/ ...")
        try:
            dest = layadl.pull(root, model)
            _ok(f"Saved -> {dest}")
            _say("Then: [cyan]docker compose --profile laya up -d laya[/]")
        except Exception as e:
            _err(str(e))
            raise typer.Exit(1)
        return
    _err("Use: ravi local laya status | ravi local laya pull")
    raise typer.Exit(1)


config_app = typer.Typer(
    help="Runtime settings: backend, language, context, threads.",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")

workers_app = typer.Typer(
    help="Celery workers and Flower monitor (queues, tasks, web UI).",
    no_args_is_help=True,
)
app.add_typer(workers_app, name="workers")

errors_app = typer.Typer(
    help="Sentry error reporting and web UI.",
    no_args_is_help=True,
)
app.add_typer(errors_app, name="errors")

profile_app = typer.Typer(
    help="Resource profiles: small / medium / large / extra / custom.",
    no_args_is_help=False,
)
app.add_typer(profile_app, name="profile")

state_app = typer.Typer(
    help="Runtime state: local | cloud | both.",
    no_args_is_help=False,
)
app.add_typer(state_app, name="state")

RAVI_BANNER = """
[cyan]  ____             _[/]
[cyan] |  _ \\ __ ___   _(_)[/]
[cyan] | |_) / _` \\ \\ / / |[/]
[cyan] |  _ < (_| |\\ V /| |[/]
[cyan] |_| \\_\\__,_| \\_/ |_|[/]  [dim]v{version}[/]
""".format(version=__version__)


def _ok(msg: str) -> None:
    console.print(f"[green]✓[/] {msg}")


def _warn(msg: str) -> None:
    console.print(f"[yellow]![/] {msg}")


def _err(msg: str) -> None:
    console.print(f"[red]✗[/] {msg}")


def _say(msg: str) -> None:
    console.print(msg)


def _root() -> Path:
    try:
        return eu.find_project_root()
    except FileNotFoundError as e:
        _err(str(e))
        raise typer.Exit(1)


def _compose_cmd(*args: str, root: Path) -> list[str]:
    return ["docker", "compose", "-f", str(root / "docker-compose.yml"), *args]


def _run(
    cmd: list[str],
    *,
    root: Path,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=root,
        env=__import__("os").environ.copy(),
        check=check,
        capture_output=capture,
        text=True,
    )


def _ensure_docker() -> None:
    if shutil.which("docker") is None:
        _err("Docker is not installed or not in PATH.")
        raise typer.Exit(1)
    try:
        subprocess.run(
            ["docker", "info"], check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError:
        _err("Docker daemon is not running. Start Docker and try again.")
        raise typer.Exit(1)


def _try_clipboard(text: str) -> bool:
    for cmd in (
        ["pbcopy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["wl-copy"],
        ["clip.exe"],
    ):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(
                    cmd, input=text, text=True, check=True, capture_output=True
                )
                return True
            except Exception:
                continue
    return False


def _mask(value: str, show: int = 4) -> str:
    if len(value) <= show * 2:
        return "*" * len(value)
    return value[:show] + "…" + value[-show:]


def _provider_ready(env: dict[str, str], provider_id: str) -> bool:
    p = get_provider(provider_id)
    if not p:
        return False
    for key in p.env_keys:
        if key == "CLOUDFLARE_AI_BASE_URL":
            val = env.get(key, "")
            if not val or "YOUR_ACCOUNT_ID" in val:
                return False
            continue
        placeholders = {
            "your_cloudflare_api_token_here",
            "your_gemini_api_key_1",
            "your_gemini_api_key_here",
        }
        if not eu.is_real_secret(env.get(key), placeholders):
            return False
    return True


def _ready_models(root: Path, env: dict[str, str]) -> list[str]:
    cfg = load_config(root / "config.yaml")
    names = sorted(existing_model_names(cfg))
    ready: list[str] = []
    for name in names:
        if name.startswith("cf-") or name.startswith("cloudflare"):
            if _provider_ready(env, "cloudflare"):
                ready.append(name)
        elif name.startswith("gemini"):
            if _provider_ready(env, "gemini"):
                ready.append(name)
        elif name.startswith("groq-"):
            if _provider_ready(env, "groq"):
                ready.append(name)
        elif name.startswith("openrouter"):
            if _provider_ready(env, "openrouter"):
                ready.append(name)
        elif name.startswith("gpt-") or name.startswith("o1"):
            if _provider_ready(env, "openai"):
                ready.append(name)
        elif name.startswith("claude"):
            if _provider_ready(env, "anthropic"):
                ready.append(name)
        elif name.startswith("local-"):
            # Local/Ollama models — ready if Ollama answers or we trust offline config
            if loc.ollama_reachable() or True:
                ready.append(name)
    return ready


def _resolve_chat_model(
    root: Path,
    env: dict[str, str],
    explicit: str | None,
) -> str:
    if explicit:
        return explicit
    default = eu.get_default_model(env)
    if default:
        return default
    ready = _ready_models(root, env)
    if ready:
        for preferred in (
            "qwen3-4b-instruct-2507-q4km",
            "local-qwen2.5-7b",
            "local-qwen2.5-3b",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-3.5-flash-lite",
            "groq-llama-3.1-8b",
            "cf-gpt-oss-20b",
            "openrouter-llama-3.3-70b-free",
        ):
            if preferred in ready:
                return preferred
        return ready[0]
    _err(
        "No default model and no provider keys configured yet.\n"
        "  • [bold]ravi keys add gemini[/]   — free Google key\n"
        "  • [bold]ravi keys add groq[/]     — free Groq key\n"
        "  • [bold]ravi keys add cloudflare[/]\n"
        "  • then [bold]ravi use <model>[/]  — set default"
    )
    raise typer.Exit(1)





def _startup_checks(root: Path, *, interactive_repair: bool = True) -> dict:
    """Run local path/model checks. Never raises — shows Rich status and optional repair."""
    from rich.table import Table

    try:
        report = run_bootstrap(root)
    except Exception as e:
        _warn(f"Startup check failed softly: {e}")
        return {}

    table = Table(title="Startup checks", border_style="cyan", show_header=True)
    table.add_column("Status", width=6)
    table.add_column("Item")
    table.add_column("Detail")
    for c in report.checks:
        if c.ok:
            icon = "[green]OK[/]"
        elif c.severity == "error":
            icon = "[red]ERR[/]"
        else:
            icon = "[yellow]WARN[/]"
        table.add_row(icon, c.label, c.detail[:80])
    console.print(table)

    if report.has_problems and interactive_repair:
        try:
            offer_repair(root, report)
        except Exception as e:
            _warn(f"Repair assistant skipped: {e}")
    return report.env or {}



def _handle_tool_calls(root: Path, env: dict, key: str, base: str, chosen: str, messages: list, tools: list) -> str:
    """Loop tool calls (laya_decide / run_shell) then return final assistant text."""
    import json

    for _ in range(4):
        payload = {
            "model": chosen,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "max_tokens": 1024,
        }
        try:
            with httpx.Client(timeout=120.0) as client:
                r = client.post(
                    f"{base}/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                )
        except Exception as e:
            return f"(tool loop error: {e})"
        if r.status_code >= 400:
            # model may not support tools — fall back without tools
            payload.pop("tools", None)
            payload.pop("tool_choice", None)
            with httpx.Client(timeout=120.0) as client:
                r = client.post(
                    f"{base}/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                )
            if r.status_code >= 400:
                return f"(HTTP {r.status_code}) {r.text[:300]}"
            data = r.json()
            return (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                or ""
            )

        data = r.json()
        msg = (data.get("choices", [{}])[0].get("message") or {})
        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""
        if not tool_calls:
            return content

        messages.append(msg)
        for tc in tool_calls:
            fn = (tc.get("function") or {})
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            tool_result = ""
            if name == "laya_decide":
                state = args.get("state") or ""
                mode = (args.get("mode") or "request").lower()
                _say(f"[dim]tool · laya_decide ({mode})[/]")
                if mode == "command":
                    dec = rexec.evaluate_command(root, env, state, proxy_key=key)
                    tool_result = (
                        f"policy={dec.policy_action} risk={dec.risk_level} "
                        f"reason={dec.reason} laya={dec.laya}"
                    )
                else:
                    d = rorch.run_decision(root, env, user_text_en=state, proxy_key=key)
                    tool_result = str(d)
            elif name == "run_shell":
                cmd = args.get("command") or ""
                _say(f"[cyan]tool · run_shell[/] {cmd}")

                def _confirm(c: str, dec: rexec.CommandDecision) -> bool:
                    console.print(
                        Panel(
                            f"[bold]{c}[/]\n\n"
                            f"Risk: [yellow]{dec.risk_level}[/]\n"
                            f"{dec.reason}\n\n"
                            "Laya recommends confirming before execution.",
                            title="[yellow]Confirm command[/]",
                            border_style="yellow",
                        )
                    )
                    try:
                        return console.input("Run this command? [y/N] ").strip().lower().startswith("y")
                    except Exception:
                        return False

                out = rexec.run_command_safe(
                    root, env, cmd, proxy_key=key, confirm_fn=_confirm
                )
                tool_result = (
                    f"code={out['code']} ok={out['ok']} "
                    f"decision={out['decision'].policy_action}/{out['decision'].risk_level}\n"
                    f"stdout:\n{(out.get('stdout') or '')[:2000]}\n"
                    f"stderr:\n{(out.get('stderr') or '')[:1000]}"
                )
            else:
                tool_result = f"Unknown tool: {name}"

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or name,
                    "content": tool_result[:6000],
                }
            )
    return content or "(tool loop ended without final answer)"



def _run_interactive_chat(
    root: Path,
    env: dict,
    *,
    model: str | None = None,
    send_welcome: bool = True,
) -> None:
    """Enter terminal chat; optionally send RAVI_WELCOME_MESSAGE first."""
    env = rsettings.ensure_default_env(root)
    chosen = _resolve_chat_model(root, env, model)
    key = env.get("LITELLM_MASTER_KEY")
    base = eu.proxy_base_url()
    lang = rsettings.get(env, "RAVI_LANG", "en")
    # model language list from catalog when possible
    model_langs = ["en"]
    try:
        from ravi.download import get_catalog_model, load_catalog
        for m in load_catalog(root):
            # match by id / local name
            if chosen.endswith(m.id) or m.id in chosen or (
                m.ollama_tags and any(t in chosen for t in m.ollama_tags)
            ):
                model_langs = list(getattr(m, "languages", None) or ["en"])
                break
    except Exception:
        pass
    sys_prompt = rmedia.build_system_prompt(root, env, model_langs)
    if not key:
        _err("No master key. Run [bold]ravi init[/].")
        raise typer.Exit(1)

    def _once(user_msg: str, *, label: str | None = None) -> None:
        url = f"{base}/chat/completions"
        # BOTH mode: local planner → cloud model
        state = (env.get("RAVI_STATE") or "local").lower()
        use_model = chosen
        final_user = user_msg
        if state == "both":
            cloud_model = (
                env.get("RAVI_CLOUD_MODEL")
                or env.get("RAVI_DEFAULT_MODEL")
                or chosen
            )
            planner_payload = {
                "model": chosen if not str(chosen).startswith("gpt") else chosen,
                "messages": [
                    {"role": "system", "content": rstate.both_system_prompt()},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 512,
            }
            try:
                with httpx.Client(timeout=120.0) as client:
                    pr = client.post(
                        f"{base}/chat/completions",
                        json=planner_payload,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                    )
                if pr.status_code < 400:
                    final_user = (
                        pr.json()
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", user_msg)
                        or user_msg
                    )
                    use_model = cloud_model
                    _say("[dim]both · planned for cloud[/]")
            except Exception:
                use_model = cloud_model
        elif state == "cloud":
            use_model = (
                env.get("RAVI_CLOUD_MODEL")
                or env.get("RAVI_DEFAULT_MODEL")
                or chosen
            )
        # Laya + Orchestrator (when RAVI_LAYA=on)
        decision_meta = None
        try:
            if laya_enabled(env):
                lang = (env.get("RAVI_LANG") or "en").lower()
                text_for_laya = final_user
                # Non-English → translate to English for English Laya weights
                variant = (env.get("RAVI_LAYA_VARIANT") or "english").lower()
                if lang != "en" and variant in ("english", "en"):
                    try:
                        tr_payload = {
                            "model": use_model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": (
                                        "Translate the user message to clear English. "
                                        "Output only the translation, no quotes."
                                    ),
                                },
                                {"role": "user", "content": final_user},
                            ],
                            "max_tokens": 512,
                        }
                        with httpx.Client(timeout=60.0) as client:
                            tr = client.post(
                                f"{base}/chat/completions",
                                json=tr_payload,
                                headers={
                                    "Authorization": f"Bearer {key}",
                                    "Content-Type": "application/json",
                                },
                            )
                        if tr.status_code < 400:
                            text_for_laya = (
                                tr.json()
                                .get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", final_user)
                                or final_user
                            )
                            _say("[dim]laya · translated for decision[/]")
                    except Exception:
                        pass
                decision_meta = rorch.run_decision(
                    root, env, user_text_en=text_for_laya, proxy_key=key
                )
                sys_prompt = rorch.enrich_system_prompt(sys_prompt, decision_meta)
                sys_prompt += (
                    "\n\nYou can call tools: laya_decide (risk/intent analysis) and "
                    "run_shell (execute commands). For git push, deletes, sudo, "
                    "package installs, or long jobs: call laya_decide first, then "
                    "run_shell — the CLI will ask the user to confirm when risky."
                )

                if decision_meta.get("policy_action") == "ask_clarification":
                    _say("[yellow]orchestrator · clarification suggested[/]")
                elif decision_meta.get("policy_action") == "require_approval":
                    _say("[yellow]orchestrator · approval / caution[/]")
                if decision_meta.get("fallback"):
                    _say("[dim]laya · offline heuristic[/]")
        except Exception as e:
            _say(f"[dim]laya skipped: {e}[/]")

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        if label:
            _say(f"[dim]{label}[/]")
        try:
            content = ""
            if laya_enabled(env):
                tools = [rexec.laya_tool_spec(), rexec.run_shell_tool_spec()]
                content = _handle_tool_calls(
                    root,
                    env,
                    key,
                    base,
                    use_model,
                    [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": final_user},
                    ],
                    tools,
                )
            else:
                payload = {
                    "model": use_model,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": final_user},
                    ],
                    "max_tokens": 1024,
                }
                with httpx.Client(timeout=180.0) as client:
                    r = client.post(url, json=payload, headers=headers)
                if r.status_code >= 400:
                    _err(f"HTTP {r.status_code}")
                    console.print(r.text[:800])
                    return
                data = r.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
            console.print(
                Panel(
                    content or "[dim](empty)[/]",
                    title=f"[cyan]Ravi[/] · {chosen}",
                    border_style="cyan",
                )
            )
            try:
                rmedia.maybe_speak(content or "", env)
            except Exception:
                pass
            try:
                rlog.log_chat_turn("user", user_msg, model=chosen, env=env)
                rlog.log_chat_turn("assistant", content or "", model=chosen, env=env)
            except Exception:
                pass
        except httpx.ConnectError:
            _err("Proxy not reachable. Is the stack up?")
            raise typer.Exit(1)

    console.print(
        Panel(
            f"Model  [bold cyan]{chosen}[/]\n"
            "[dim]Empty line or Ctrl+C to leave · "
            "ravi use <model> to switch default[/]",
            title="[bold cyan]Ravi chat[/]",
            border_style="cyan",
        )
    )

    if send_welcome:
        welcome = eu.get_welcome_message(env)
        short = welcome[:80] + ("…" if len(welcome) > 80 else "")
        _say(f"[dim]welcome →[/] {short}")
        try:
            _once(welcome, label="(greeting)")
        except typer.Exit:
            return

    while True:
        try:
            line = console.input("[bold cyan]you>[/] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print(
                "\n[dim]bye — Ravi is still running in the background.[/]"
            )
            break
        if not line:
            console.print(
                "[dim]bye — Ravi is still running in the background.[/]"
            )
            break
        _once(line)


def _activate_local_model(root: Path, ollama_name: str) -> str:
    """Register ollama model in config, set default, return ravi model name."""
    ravi_name = loc.litellm_model_id(ollama_name)
    added = ensure_ollama_model(root / "config.yaml", ollama_name, ravi_name)
    if added:
        _ok(f"Registered [cyan]{ravi_name}[/] → ollama/{ollama_name}")
    eu.set_default_model(root, ravi_name)
    eu.write_env_value(eu.env_path(root), "RAVI_LOCAL_MODEL", ollama_name)
    _ok(f"Default model → [bold cyan]{ravi_name}[/]")
    return ravi_name


@app.command()
def version() -> None:
    """Show Ravi version."""
    console.print(RAVI_BANNER)
    console.print(
        f"  [bold cyan]Ravi[/] [dim]{__version__}[/]  ·  Open Source AI Infrastructure"
    )


@app.command()
def init(
    force: bool = typer.Option(
        False, "--force", "-f", help="Regenerate master key even if already set"
    ),
    local: bool = typer.Option(
        False,
        "--local",
        "-l",
        help="Set up a local model (default: Qwen3 8B Q4_K_M via multi-mirror)",
    ),
) -> None:
    """Create .env, generate secrets, optionally configure a local model."""
    banner()
    root = _root()
    try:
        _startup_checks(root, interactive_repair=True)
    except Exception as e:
        _warn(f"Startup checks skipped: {e}")
    try:
        rlog.log_cli_command("ravi init", env=eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {})
    except Exception:
        pass
    env_file = eu.ensure_env_file(root)

    runner = StageRunner("Ravi · init")
    runner.add("envfile", "Create .env from template")
    runner.add("secrets", "Generate master key & database password")
    runner.add("local", "Local model (optional)")
    runner.add("summary", "Show credentials")

    with runner:
        runner.start_step("envfile")
        runner.done("envfile", str(env_file.name))

        runner.start_step("secrets")
        if force:
            new_key = eu.generate_master_key()
            eu.write_env_value(env_file, "LITELLM_MASTER_KEY", new_key)
            runner.log(f"Regenerated master key")
        before = eu.parse_env(env_file)
        env = eu.ensure_secrets(root)
        bits = []
        if before.get("LITELLM_MASTER_KEY") != env.get("LITELLM_MASTER_KEY"):
            bits.append("master key")
        if before.get("POSTGRES_PASSWORD") != env.get("POSTGRES_PASSWORD"):
            bits.append("postgres password")
        runner.done("secrets", ", ".join(bits) if bits else "already set")

        # Local
        if local:
            runner.start_step("local", "detecting")
            auto = loc.pick_auto(root)
            if auto and auto.source == "installed":
                runner.log(f"Found {auto.ollama_name}")
                _activate_local_model(root, auto.ollama_name)
                runner.done("local", auto.ollama_name)
            else:
                ok, msg = loc.ensure_ollama_running()
                runner.log(msg)
                if not ok:
                    runner.skip("local", "Ollama not ready — use ravi local pull later")
                else:
                    installed = loc.installed_model_names()
                    if installed:
                        choice = installed[0]
                        _activate_local_model(root, choice)
                        runner.done("local", choice)
                    else:
                        from ravi.download import get_catalog_model, download_model
                        cat = get_catalog_model(None)
                        runner.detail("local", f"pulling {cat.id}")
                        def _log(msg: str) -> None:
                            runner.log(msg)
                        try:
                            source, path = download_model(root, cat, log=_log)
                            tag = cat.ollama_tags[0] if cat.ollama_tags else cat.id
                            _activate_local_model(root, tag)
                            runner.done("local", f"{cat.id} via {source}")
                        except Exception as e:
                            runner.fail("local", str(e))
        else:
            auto = loc.pick_auto(root)
            if auto and auto.source == "installed":
                runner.start_step("local", "auto-detected")
                _activate_local_model(root, auto.ollama_name)
                runner.done("local", auto.ollama_name)
            else:
                runner.skip("local", "use --local or ravi local pull")

        runner.start_step("summary")
        runner.done("summary", "ok")

    env = eu.parse_env(eu.env_path(root))
    username = env.get("UI_USERNAME") or eu.DEFAULT_UI_USERNAME
    password = (env.get("UI_PASSWORD") or "").strip() or env["LITELLM_MASTER_KEY"]
    default = eu.get_default_model(env) or "(not set)"

    console.print(
        Panel(
            f"[bold]UI Username[/]   {username}\n"
            f"[bold]UI Password[/]   {password}\n"
            f"[bold]Master Key[/]    {env['LITELLM_MASTER_KEY']}\n"
            f"[bold]Default model[/] {default}\n\n"
            f"Admin UI   {eu.proxy_base_url()}/ui\n"
            f"API        {eu.proxy_base_url()}\n\n"
            "[dim]Next[/]\n"
            "  [cyan]ravi start[/]              → stack + interactive chat\n"
            "  [cyan]ravi local pull[/]         → download Qwen3-4B-Instruct-2507 Q4_K_M (default)\n"
            "  [cyan]ravi keys add gemini[/]    → free cloud key",
            title="[bold cyan]Ravi[/] is ready",
            border_style="green",
        )
    )


@app.command()
def start(
    build: bool = typer.Option(True, "--build/--no-build"),
    detach: bool = typer.Option(True, "--detach/--attach", "-d/-a"),
    chat_after: bool = typer.Option(
        True,
        "--chat/--no-chat",
        help="Open interactive chat after start (default: yes)",
    ),
    welcome: bool = typer.Option(
        True,
        "--welcome/--no-welcome",
        help="Send RAVI_WELCOME_MESSAGE as first turn in chat",
    ),
) -> None:
    """Start the stack (auto-init if needed), show staged progress, then chat."""
    banner()
    root = _root()

    # Local files + models path first (never crash)
    try:
        env = _startup_checks(root, interactive_repair=True)
    except Exception as e:
        _warn(f"Startup checks skipped: {e}")
        env = {}
    try:
        rlog.log_cli_command("ravi start", env=env or {})
    except Exception:
        pass

    try:
        _ensure_docker()
    except typer.Exit:
        _warn("Docker is not ready. You can still use config/local commands.")
        return
    except Exception as e:
        _warn(f"Docker check: {e}")
        return

    runner = StageRunner("Ravi · start")
    runner.add("env", "Prepare environment (.env + secrets)")
    runner.add("local", "Detect / wire local models (if ON)")
    runner.add("compose", "Start all containers (full stack)")
    runner.add("health", "Wait until services are active")
    runner.add("chat", "Open interactive chat")

    with runner:
        # 1. Environment
        runner.start_step("env", "writing secrets if needed")
        try:
            env = eu.ensure_secrets(root)
            env = rsettings.ensure_default_env(root)
            runner.done("env", "ready")
        except Exception as e:
            runner.fail("env", str(e))
            _warn(str(e))
            env = eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {}

        # 2. Local model auto-wire when LLM is ON
        runner.start_step("local", "scanning models dir")
        try:
            llm_on = (env.get("RAVI_LLM") or "on").lower() not in ("off", "0", "false")
            if not llm_on:
                runner.skip("local", "RAVI_LLM=off")
            else:
                auto = loc.pick_auto(root)
                if auto:
                    cur = eu.get_default_model(env)
                    if not cur or not str(cur).startswith("local-"):
                        _activate_local_model(root, auto.ollama_name)
                        env = eu.parse_env(eu.env_path(root))
                    runner.done("local", f"{auto.ollama_name} ({auto.source})")
                else:
                    runner.skip("local", "none found (optional)")
        except Exception as e:
            runner.skip("local", f"skipped: {e}")

        # 3. Bring up ALL stack containers (redis, postgres, proxy, worker, llama…)
        set_status_flag(root, "off")
        runner.start_step("compose", "docker compose up -d (full stack)")
        try:
            ok, out = compose_up_all(root, build=build)
            for line in (out or "").splitlines()[-15:]:
                runner.log(line)
            if ok:
                runner.done("compose", "containers requested")
                try:
                    rlog.log_event(
                        "compose_up",
                        "Full container stack start requested",
                        category="docker",
                        tags=["compose", "start"],
                        env=env,
                    )
                except Exception:
                    pass
            else:
                runner.fail("compose", out or "compose failed")
                _warn("Compose reported errors — attempting guided repair if possible.")
                try:
                    offer_repair(root, run_bootstrap(root))
                    ok2, out2 = compose_up_all(root, build=False)
                    if not ok2:
                        _warn("Still failing after repair attempt.")
                        return
                except Exception:
                    return
        except Exception as e:
            runner.fail("compose", str(e))
            _warn(str(e))
            try:
                offer_repair(root, run_bootstrap(root))
            except Exception:
                pass
            return

        # 4. Wait until core services are active (status inactive → active)
        runner.start_step("health", "waiting until services are active")
        runner.progress_bar("Service readiness")

        def _prog(states, core_ok):
            detail = ", ".join(
                f"{s.name}={'ok' if s.ok else '…'}" for s in states
            )
            runner.detail("health", detail[:80])

        healthy, last_states = wait_until_active(
            root, timeout_sec=150, poll=2.0, on_progress=_prog
        )
        if healthy:
            set_status_flag(root, "on")
            runner.done("health", "active")
            try:
                rlog.log_event(
                    "stack_active",
                    "Core services are active; Ravi continuing normal operation",
                    category="docker",
                    tags=["active", "ready"],
                    env=env,
                )
            except Exception:
                pass
            # Laya: use local weights if present; else ask to download once
            try:
                def _ask_laya() -> bool:
                    try:
                        return console.input(
                            "Laya weights missing. Download permanently into models dir? [y/N] "
                        ).strip().lower().startswith("y")
                    except Exception:
                        return False

                lr = layasvc.ensure_at_startup(
                    root, ask_download=_ask_laya, say=lambda m: _say(m)
                )
                if lr.get("message"):
                    _say(f"[dim]{lr['message']}[/]")
            except Exception as e:
                _warn(f"Laya ensure skipped: {e}")
        else:
            set_status_flag(root, "off")
            detail = ", ".join(
                f"{s.name}:{'up' if s.ok else 'down'}" for s in last_states
            )
            runner.fail("health", detail or "timeout")
            _warn("Services did not become active in time.")
            try:
                offer_repair(root, run_bootstrap(root))
                healthy2, _ = wait_until_active(root, timeout_sec=90, poll=2.0)
                if healthy2:
                    set_status_flag(root, "on")
                    healthy = True
                    runner.done("health", "active after repair")
                else:
                    _warn("Still inactive. You can retry: ravi start")
            except Exception as e:
                _warn(f"Repair skipped: {e}")

        if chat_after and detach:
            runner.start_step("chat", "entering terminal chat")
            runner.done("chat", "ready")
        else:
            runner.skip("chat", "disabled")

    default = eu.get_default_model(eu.parse_env(eu.env_path(root))) or "(not set)"
    console.print(
        Panel(
            f"[green]Ravi is up[/]\n\n"
            f"API        {eu.proxy_base_url()}\n"
            f"Admin UI   {eu.proxy_base_url()}/ui\n"
            f"Default    [cyan]{default}[/]\n"
            f"Models dir {loc.models_dir(root)}",
            title="[bold cyan]Ravi[/]",
            border_style="green",
        )
    )

    try:
        boot = run_bootstrap(root)
        if boot.has_problems:
            offer_repair(root, boot)
    except Exception as e:
        _warn(f"Post-start checks: {e}")

    if chat_after and detach and healthy:
        env = eu.parse_env(eu.env_path(root))
        try:
            _run_interactive_chat(root, env, send_welcome=welcome)
        except typer.Exit:
            pass


@app.command()
def stop(
    volumes: bool = typer.Option(
        False, "--volumes", "-v", help="Also wipe volumes (destructive)"
    ),
) -> None:
    """Stop Ravi containers."""
    _ensure_docker()
    root = _root()
    _say("[yellow]Stopping Ravi…[/]")
    cmd = _compose_cmd("down", root=root)
    if volumes:
        if not typer.confirm("This deletes Postgres & Redis data. Continue?"):
            raise typer.Abort()
        cmd.append("-v")
    try:
        _run(cmd, root=root)
        try:
            set_status_flag(root, "off")
        except Exception:
            pass
        _ok(
            "Stopped. Containers are down — RAM freed.\n"
            "CLI remains available. Run [bold]ravi start[/] to resume chat."
        )
    except subprocess.CalledProcessError as e:
        try:
            set_status_flag(root, "off")
        except Exception:
            pass
        _err(str(e))
        raise typer.Exit(e.returncode)
def restart() -> None:
    """Restart the stack."""
    stop(volumes=False)
    start(build=False, detach=True)


@app.command()
def status() -> None:
    """Show container status."""
    _ensure_docker()
    root = _root()
    _run(_compose_cmd("ps", root=root), root=root, check=False)


@app.command()
def logs(
    service: Optional[str] = typer.Argument(None),
    follow: bool = typer.Option(True, "--follow/--no-follow", "-f"),
    tail: int = typer.Option(100, "--tail", "-n"),
) -> None:
    """Follow container logs."""
    _ensure_docker()
    root = _root()
    cmd = _compose_cmd("logs", f"--tail={tail}", root=root)
    if follow:
        cmd.append("-f")
    if service:
        cmd.append(service)
    try:
        _run(cmd, root=root, check=False)
    except KeyboardInterrupt:
        pass


@app.command()
def health(
    base_url: Optional[str] = typer.Option(None, "--url"),
    timeout: float = typer.Option(10.0, "--timeout"),
) -> None:
    """Check API health."""
    base = (base_url or eu.proxy_base_url()).rstrip("/")
    url = f"{base}/health"
    _say(f"Checking [bold]{url}[/] …")
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url)
        if r.status_code == 200:
            _ok("Healthy")
            try:
                console.print_json(data=r.json())
            except Exception:
                console.print(r.text[:400])
        else:
            _warn(f"Status {r.status_code}")
            console.print(r.text[:400])
            raise typer.Exit(1)
    except httpx.ConnectError:
        _err("Cannot connect. Try [bold]ravi start[/].")
        raise typer.Exit(1)


@keys_app.command("list")
def keys_list() -> None:
    """Show which provider keys are configured."""
    root = _root()
    env = eu.ensure_secrets(root)

    table = Table(title="Provider keys", show_header=True, border_style="cyan")
    table.add_column("Provider", style="bold")
    table.add_column("Free?", justify="center")
    table.add_column("Status")
    table.add_column("Models unlocked")

    for pid, p in PROVIDERS.items():
        ready = _provider_ready(env, pid)
        status = "[green]ready[/]" if ready else "[dim]missing key[/]"
        free = "✓" if p.free_tier else "—"
        models = ", ".join(p.models[:3]) + ("…" if len(p.models) > 3 else "")
        table.add_row(p.name, free, status, models if ready else "[dim]—[/]")

    console.print(table)
    console.print(
        "\n[dim]Add a free key:[/]  [cyan]ravi keys add gemini[/]  ·  "
        "[cyan]ravi keys add groq[/]  ·  [cyan]ravi keys add cloudflare[/]"
    )


@keys_app.command("add")
def keys_add(
    provider: str = typer.Argument(
        ..., help="Provider id: gemini, cloudflare, groq, openrouter, openai, anthropic"
    ),
    key: Optional[str] = typer.Option(
        None, "--key", "-k", help="API key (prompted if omitted)"
    ),
    account_id: Optional[str] = typer.Option(
        None, "--account", help="Cloudflare Account ID"
    ),
    token: Optional[str] = typer.Option(
        None, "--token", help="Cloudflare API token (alias for --key)"
    ),
    set_default: bool = typer.Option(
        True,
        "--set-default/--no-set-default",
        help="Set a sensible default model for this provider",
    ),
) -> None:
    """Add a provider API key (especially free-tier ones)."""
    root = _root()
    pid = provider.lower().strip()
    p = get_provider(pid)
    if not p:
        _err(
            f"Unknown provider [bold]{provider}[/].\n"
            f"Try one of: {', '.join(provider_ids())}"
        )
        raise typer.Exit(1)

    eu.ensure_secrets(root)
    path = eu.env_path(root)

    console.print(
        Panel(
            f"[bold]{p.name}[/]\n{p.description}\n\n"
            f"[dim]Get a key:[/] {p.signup_url}\n"
            f"[dim]{p.notes}[/]",
            title=f"[cyan]Ravi[/] · {pid}",
            border_style="cyan",
        )
    )

    if pid == "cloudflare":
        api_token = token or key
        if not api_token:
            api_token = typer.prompt("Cloudflare API token", hide_input=True)
        if not account_id:
            account_id = typer.prompt("Cloudflare Account ID")
        api_token = api_token.strip()
        account_id = account_id.strip()
        base = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"
        )
        eu.write_env_value(path, "CLOUDFLARE_API_TOKEN", api_token)
        eu.write_env_value(path, "CLOUDFLARE_AI_BASE_URL", base)
        _ok("Saved CLOUDFLARE_API_TOKEN and CLOUDFLARE_AI_BASE_URL")
    else:
        primary = p.env_keys[0]
        value = key
        if not value:
            value = typer.prompt(f"{p.name} API key", hide_input=True)
        value = value.strip()
        if not value:
            _err("Empty key — nothing saved.")
            raise typer.Exit(1)
        eu.write_env_value(path, primary, value)
        _ok(f"Saved [bold]{primary}[/] → {_mask(value)}")

    added = ensure_provider_models(root / "config.yaml", pid)
    if added:
        _ok(f"Added models to config.yaml: {', '.join(added)}")
        _warn("Restart the proxy so new models load: [bold]ravi restart[/]")

    if set_default and p.models:
        choice = p.models[0]
        eu.set_default_model(root, choice)
        _ok(f"Default model → [cyan]{choice}[/]")
        _say('  Chat with:  [bold]ravi chat "hello"[/]')

    _say(
        f"\n[dim]Models for {p.name}:[/] {', '.join(p.models)}\n"
        f"[dim]Switch default:[/] ravi use <model>"
    )


@keys_app.command("remove")
def keys_remove(
    provider: str = typer.Argument(..., help="Provider id to clear keys for"),
) -> None:
    """Remove stored keys for a provider from .env."""
    root = _root()
    pid = provider.lower().strip()
    p = get_provider(pid)
    if not p:
        _err(f"Unknown provider: {provider}")
        raise typer.Exit(1)
    path = eu.env_path(root)
    removed = 0
    for k in p.env_keys:
        if eu.delete_env_key(path, k):
            removed += 1
            _ok(f"Removed {k}")
    if removed == 0:
        _warn("No keys found for that provider.")


@keys_app.command("set")
def keys_set(
    name: str = typer.Argument(..., help="Env var name, e.g. GEMINI_API_KEY_1"),
    value: str = typer.Argument(..., help="Value to store"),
) -> None:
    """Set any .env variable by name (escape hatch)."""
    root = _root()
    eu.ensure_secrets(root)
    eu.write_env_value(eu.env_path(root), name, value)
    _ok(f"Set {name} → {_mask(value)}")


@app.command("providers")
def providers_cmd() -> None:
    """List supported providers (highlighting free tiers)."""
    table = Table(title="Ravi providers", border_style="cyan", show_header=True)
    table.add_column("Id", style="cyan")
    table.add_column("Name")
    table.add_column("Free", justify="center")
    table.add_column("How to add")

    for p in PROVIDERS.values():
        table.add_row(
            p.id,
            p.name,
            "[green]yes[/]" if p.free_tier else "[dim]paid[/]",
            f"ravi keys add {p.id}",
        )
    console.print(table)
    console.print(
        "\n[dim]Free-tier favourites:[/] [cyan]gemini[/], [cyan]groq[/], "
        "[cyan]cloudflare[/], [cyan]openrouter[/]"
    )


@app.command("use")
def use_model(
    model: str = typer.Argument(..., help="Model name to set as default"),
) -> None:
    """Set the default model for ravi chat (no --model needed)."""
    root = _root()
    env = eu.ensure_secrets(root)
    ready = _ready_models(root, env)
    cfg_names = existing_model_names(load_config(root / "config.yaml"))

    if model not in cfg_names:
        _warn(
            f"[bold]{model}[/] is not in config.yaml yet.\n"
            "It may still work if LiteLLM recognizes it — saving as default anyway."
        )
    elif model not in ready:
        _warn(
            f"[bold]{model}[/] is configured but its provider key looks missing.\n"
            "Add the key with [cyan]ravi keys add …[/], or chat may fail."
        )

    eu.set_default_model(root, model)
    _ok(f"Default model → [bold cyan]{model}[/]")
    _say('Try:  [bold]ravi chat "hello Ravi"[/]')


@app.command("models")
def models_cmd(
    all_models: bool = typer.Option(
        False, "--all", "-a", help="Show every model in config.yaml"
    ),
    remote: bool = typer.Option(
        False, "--remote", "-r", help="Query the running proxy"
    ),
) -> None:
    """List models. By default shows ones whose keys are ready."""
    root = _root()
    env = eu.ensure_secrets(root)
    default = eu.get_default_model(env)

    if remote:
        key = env.get("LITELLM_MASTER_KEY")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.get(f"{eu.proxy_base_url()}/models", headers=headers)
            r.raise_for_status()
            data = r.json()
            rows = data.get("data") or []
            table = Table(title="Proxy models", border_style="cyan")
            table.add_column("ID", style="cyan")
            for m in rows:
                mid = m.get("id") or str(m)
                mark = " [green]← default[/]" if mid == default else ""
                table.add_row(mid + mark)
            console.print(table)
            return
        except Exception as e:
            _err(f"Proxy not reachable: {e}")
            raise typer.Exit(1)

    ready = _ready_models(root, env)
    cfg = load_config(root / "config.yaml")
    all_names = sorted(existing_model_names(cfg))

    table = Table(
        title="Models" + (" (all in config)" if all_models else " (ready to use)"),
        border_style="cyan",
    )
    table.add_column("Model", style="cyan")
    table.add_column("Status")
    table.add_column("")

    show = all_names if all_models else ready
    if not show and not all_models:
        _warn("No models ready — add a free key first.")
        _say("  [cyan]ravi keys add gemini[/]")
        _say("  [cyan]ravi keys add groq[/]")
        return

    for name in show:
        status = "[green]ready[/]" if name in ready else "[dim]needs key[/]"
        star = "[bold yellow]★ default[/]" if name == default else ""
        table.add_row(name, status, star)

    console.print(table)
    if default:
        console.print(
            f"\nDefault: [bold cyan]{default}[/]  ·  change with [cyan]ravi use <model>[/]"
        )
    else:
        console.print("\nNo default yet. Pick one: [cyan]ravi use <model>[/]")


@app.command()
def chat(
    message: Optional[str] = typer.Argument(
        None, help="Message to send (interactive if omitted)"
    ),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Override default model"
    ),
    base_url: Optional[str] = typer.Option(None, "--url"),
    master_key: Optional[str] = typer.Option(None, "--key", "-k"),
) -> None:
    """Chat with Ravi. Uses default model when --model is omitted."""
    root = _root()
    env = eu.ensure_secrets(root)
    env = rsettings.ensure_default_env(root)
    chosen = _resolve_chat_model(root, env, model)
    key = master_key or env.get("LITELLM_MASTER_KEY")
    lang = rsettings.get(env, "RAVI_LANG", "en")
    model_langs = ["en"]
    try:
        from ravi.download import load_catalog
        for m in load_catalog(root):
            if chosen.endswith(m.id) or m.id in chosen:
                model_langs = list(getattr(m, "languages", None) or ["en"])
                break
    except Exception:
        pass
    sys_prompt = rmedia.build_system_prompt(root, env, model_langs)

    base = (base_url or eu.proxy_base_url()).rstrip("/")

    if not key:
        _err("No master key. Run [bold]ravi init[/].")
        raise typer.Exit(1)

    def _once(user_msg: str) -> None:
        url = f"{base}/chat/completions"
        payload = {
            "model": chosen,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 1024,
        }
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        _say(
            f"[dim]{chosen}[/]  ←  {user_msg[:60]}{'…' if len(user_msg) > 60 else ''}"
        )
        try:
            with httpx.Client(timeout=120.0) as client:
                r = client.post(url, json=payload, headers=headers)
            if r.status_code >= 400:
                _err(f"HTTP {r.status_code}")
                console.print(r.text[:800])
                raise typer.Exit(1)
            data = r.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            console.print(
                Panel(
                    content or "[dim](empty response)[/]",
                    title=f"[cyan]Ravi[/] · {chosen}",
                    border_style="cyan",
                )
            )
        except httpx.ConnectError:
            _err("Cannot connect. Is Ravi running?  [bold]ravi start[/]")
            raise typer.Exit(1)

    if message:
        _once(message)
        return

    console.print(
        Panel(
            f"Talking through [bold cyan]{chosen}[/]\n"
            f"[dim]Empty line or Ctrl+C to leave.  "
            f"Switch model: ravi use <name>[/]",
            title="[bold cyan]Ravi chat[/]",
            border_style="cyan",
        )
    )
    while True:
        try:
            line = console.input("[bold cyan]you>[/] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]bye[/]")
            break
        if not line:
            console.print("[dim]bye[/]")
            break
        try:
            _once(line)
        except typer.Exit:
            break


@app.command()
def ui(
    base_url: Optional[str] = typer.Option(None, "--url"),
    no_open: bool = typer.Option(False, "--no-open"),
    copy: bool = typer.Option(True, "--copy/--no-copy"),
) -> None:
    """Open the LiteLLM Admin UI and show login credentials."""
    root = _root()
    env = eu.ensure_secrets(root)
    username = env.get("UI_USERNAME") or eu.DEFAULT_UI_USERNAME
    master = env["LITELLM_MASTER_KEY"]
    password = (env.get("UI_PASSWORD") or "").strip() or master
    base = (base_url or eu.proxy_base_url()).rstrip("/")
    ui_url = f"{base}/ui"

    try:
        with httpx.Client(timeout=2.0) as client:
            ready = client.get(f"{base}/health").status_code == 200
    except Exception:
        ready = False
    if not ready:
        _warn("Proxy not healthy yet — [bold]ravi start[/] if needed.\n")

    clipped = _try_clipboard(password) if copy else False
    console.print(
        Panel(
            f"[bold]Admin UI[/]    {ui_url}\n\n"
            f"[bold]Username[/]    {username}\n"
            f"[bold]Password[/]    {password}\n\n"
            + (
                "[green]Password copied to clipboard.[/]"
                if clipped
                else "[dim]Password = your LITELLM_MASTER_KEY[/]"
            ),
            title="[bold cyan]Ravi[/] · Admin UI",
            border_style="cyan",
        )
    )
    if no_open:
        return
    if webbrowser.open(ui_url):
        _ok(f"Opened {ui_url}")
    else:
        _warn(f"Open manually: {ui_url}")


@app.command("show-key")
def show_key() -> None:
    """Print master key and UI credentials."""
    root = _root()
    env = eu.ensure_secrets(root)
    username = env.get("UI_USERNAME") or eu.DEFAULT_UI_USERNAME
    master = env["LITELLM_MASTER_KEY"]
    password = (env.get("UI_PASSWORD") or "").strip() or master
    default = eu.get_default_model(env) or "(none)"
    console.print(f"UI Username : [bold]{username}[/]")
    console.print(f"UI Password : [bold]{password}[/]")
    console.print(f"Master Key  : [bold cyan]{master}[/]")
    console.print(f"Default model: [cyan]{default}[/]")
    console.print(f"Admin UI    : {eu.proxy_base_url()}/ui")


@app.command()
def config() -> None:
    """Summarize models defined in config.yaml."""
    root = _root()
    cfg = load_config(root / "config.yaml")
    models = cfg.get("model_list") or []
    env = eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {}
    default = eu.get_default_model(env)
    ready = set(_ready_models(root, env)) if env else set()

    table = Table(title=f"config.yaml · {len(models)} entries", border_style="cyan")
    table.add_column("#", style="dim")
    table.add_column("model_name", style="cyan")
    table.add_column("upstream")
    table.add_column("")

    for i, entry in enumerate(models, 1):
        name = entry.get("model_name", "?")
        upstream = (entry.get("litellm_params") or {}).get("model", "?")
        flags = []
        if name == default:
            flags.append("[yellow]★[/]")
        if name in ready:
            flags.append("[green]ready[/]")
        table.add_row(str(i), name, upstream, " ".join(flags))
    console.print(table)




# ---------------------------------------------------------------------------
# Local models (Ollama)
# ---------------------------------------------------------------------------

@local_app.command("status")
def local_status() -> None:
    """Show Ollama status, installed models, and models directory."""
    root = _root()
    ok, msg = loc.ensure_ollama_running()
    if ok:
        _ok(msg)
    else:
        _warn(msg)

    installed = loc.installed_model_names()
    table = Table(title="Installed local models", border_style="cyan")
    table.add_column("Ollama name", style="cyan")
    table.add_column("Ravi model id")
    env = eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {}
    default = eu.get_default_model(env)
    if not installed:
        console.print("[dim]No Ollama models yet. Try: ravi local pull[/]")
    else:
        for name in installed:
            rid = loc.litellm_model_id(name)
            star = " [yellow]★ default[/]" if rid == default or name == default else ""
            table.add_row(name, rid + star)
        console.print(table)

    md = loc.models_dir(root)
    _say(f"Models directory: [bold]{md}[/]")
    ggufs = loc.scan_gguf_files(root)
    if ggufs:
        _say("GGUF files found:")
        for g in ggufs:
            _say(f"  • {g}")


@local_app.command("list")
def local_list(
    all_models: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show every catalog model (ignore RAM filter)",
    ),
    min_ram: int | None = typer.Option(
        None, "--ram", help="Override detected RAM (GB) for filtering"
    ),
) -> None:
    """Show local models with capability tags (filtered by system RAM by default)."""
    from ravi.download import (
        load_catalog,
        catalog_meta,
        detect_system_ram_gb,
        filter_by_ram,
        list_local_ggufs,
        CAPABILITY_STYLE,
    )
    from rich.text import Text

    root = _root()
    models = load_catalog(root)
    meta = catalog_meta(root)
    labels = meta.get("capability_labels") or {}
    ram = min_ram if min_ram is not None else detect_system_ram_gb()

    if all_models or ram is None:
        shown = models
        filter_note = (
            "showing all models (--all)"
            if all_models
            else "RAM unknown — showing all"
        )
    else:
        shown = filter_by_ram(models, ram)
        filter_note = f"recommended for ~{ram} GB RAM (use --all for full catalog)"
        if not shown:
            shown = models
            filter_note = (
                f"no models fit ~{ram} GB after headroom — showing full catalog"
            )

    installed = set(loc.installed_model_names())
    on_disk = {p.name for p in list_local_ggufs(root)}

    table = Table(
        title="Local models",
        border_style="cyan",
        show_header=True,
        header_style="bold",
    )
    table.add_column("#", style="dim", justify="right", width=3)
    table.add_column("Id", style="cyan", no_wrap=True)
    table.add_column("Model")
    table.add_column("Size", justify="right")
    table.add_column("RAM", justify="right")
    table.add_column("Tags")
    table.add_column("Image")
    table.add_column("Audio")
    table.add_column("Status")

    for i, c in enumerate(shown, 1):
        tags = Text()
        for j, cap in enumerate(
            x for x in c.capabilities if x not in ("image_gen", "audio_asr", "audio_tts")
        ):
            if j:
                tags.append(" ")
            label = labels.get(cap, cap)
            style = CAPABILITY_STYLE.get(cap, "white")
            tags.append(f"{label}", style=style)

        # Image column
        if "image_gen" in c.capabilities:
            img = Text("gen", style="yellow bold")
        elif "vision" in c.capabilities:
            img = Text("vision", style="magenta")
        else:
            img = Text("—", style="dim")

        # Audio column
        audio_bits = []
        if "audio_asr" in c.capabilities:
            audio_bits.append("ASR")
        if "audio_tts" in c.capabilities:
            audio_bits.append("TTS")
        if audio_bits:
            audio = Text("+".join(audio_bits), style="green")
        else:
            audio = Text("—", style="dim")

        status = Text()
        if c.default:
            status.append("★ ", style="bold yellow")
        if c.hf_file and c.hf_file in on_disk:
            status.append("disk ", style="green")
        if any(t in installed for t in c.ollama_tags):
            status.append("ollama", style="green")
        if not status.plain.strip():
            status.append("—", style="dim")

        table.add_row(
            str(i),
            c.id,
            f"{c.name} [dim]{c.quant}[/]",
            c.size_label,
            c.ram_label,
            tags,
            img,
            audio,
            status,
        )

    console.print(table)
    console.print(f"\n[dim]Filter:[/] {filter_note}")
    console.print(
        "[dim]Image:[/]  [magenta]vision[/] = understands images · "
        "[yellow]gen[/] = generates images · [dim]—[/] = neither\n"
        "[dim]Audio:[/]  [green]ASR[/] = speech→text · [green]TTS[/] = text→speech · "
        "[dim]—[/] = neither"
    )
    if meta.get("capability_notes"):
        console.print(
            Panel(
                meta["capability_notes"],
                title="Notes",
                border_style="dim",
                expand=False,
            )
        )
    console.print(
        "\n[dim]Pull default[/]  [cyan]ravi local pull[/]\n"
        "[dim]Pull by id[/]    [cyan]ravi local pull qwen3-4b-instruct-2507-q4km[/]\n"
        "[dim]Show all[/]      [cyan]ravi local list --all[/]"
    )


@local_app.command("pull")
def local_pull(
    model: str | None = typer.Argument(
        None,
        help="Catalog id / Ollama tag / HF file. Default: qwen3-4b-instruct-2507-q4km.",
    ),
) -> None:
    """Download a local model via Ollama → Hugging Face mirrors (fallback chain)."""
    from ravi.download import get_catalog_model, download_model, find_local_gguf

    banner()
    root = _root()
    eu.ensure_secrets(root)
    cat = get_catalog_model(model)

    console.print(
        Panel(
            f"[bold]{cat.name}[/]  ·  {cat.quant}\n"
            f"Download  {cat.size_label}    RAM  {cat.ram_label}\n"
            f"{cat.desc}\n\n"
            f"[dim]HF[/]  {cat.hf_repo or '—'}\n"
            f"[dim]File[/] {cat.hf_file or '—'}\n"
            f"[dim]Ollama tags[/] {', '.join(cat.ollama_tags) or '—'}",
            title="[cyan]Ravi · local pull[/]",
            border_style="cyan",
        )
    )

    runner = StageRunner(f"Ravi · pull {cat.id}")
    runner.add("scan", "Scan local models directory")
    runner.add("mirrors", "Download (Ollama → Hugging Face mirrors)")
    runner.add("register", "Register in Ravi config")
    runner.add("default", "Set as default model")

    with runner:
        runner.start_step("scan", str(loc.models_dir(root)))
        existing = find_local_gguf(root, cat.hf_file) if cat.hf_file else None
        if existing:
            runner.done("scan", f"found {existing.name}")
            runner.start_step("mirrors", "using local file")
            runner.done("mirrors", "skipped — already on disk")
            source, path = "local-disk", existing
        else:
            runner.done("scan", "not found — will download")
            runner.start_step("mirrors")
            runner.progress_bar(f"Fetching {cat.name}")

            def _log(msg: str) -> None:
                runner.log(msg)

            def _prog(done: float, total: float | None, label: str) -> None:
                if total:
                    runner.set_progress(completed=done, total=total, description=label)
                else:
                    runner.set_progress(description=f"{label} {done/1e6:.0f} MB")

            try:
                source, path = download_model(
                    root, cat, log=_log, progress=_prog
                )
                runner.done("mirrors", f"via {source}")
            except Exception as e:
                runner.fail("mirrors", str(e))
                raise typer.Exit(1)

        runner.start_step("register")
        tag = cat.ollama_tags[0] if cat.ollama_tags else cat.id
        try:
            ravi_name = _activate_local_model(root, tag)
            if path:
                eu.write_env_value(
                    eu.env_path(root), "RAVI_LOCAL_GGUF", str(path)
                )
            runner.done("register", ravi_name)
            runner.start_step("default")
            runner.done("default", ravi_name)
        except Exception as e:
            runner.fail("register", str(e))
            raise typer.Exit(1)

    _ok(f"Ready: [bold cyan]{cat.name}[/] ({cat.quant}) via [cyan]{source}[/]")
    if path:
        _say(f"  File: {path}")
    _say("Next: [bold]ravi start[/]  or  [bold]ravi chat[/]")


@local_app.command("remove")
def local_remove(
    model: str | None = typer.Argument(
        None, help="Catalog id, Ollama name, or GGUF filename"
    ),
    all_models: bool = typer.Option(
        False, "--all", help="Remove all local GGUF files and Ollama tags from catalog"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Remove a local model from disk and/or Ollama."""
    from ravi.download import (
        get_catalog_model,
        remove_gguf,
        remove_all_ggufs,
        list_local_ggufs,
        load_catalog,
    )

    root = _root()

    if all_models:
        if not yes and not typer.confirm("Delete ALL local GGUF files under models/?"):
            raise typer.Abort()
        removed = remove_all_ggufs(root)
        for m in load_catalog(root):
            for tag in m.ollama_tags:
                loc.ollama_rm(tag)
        _ok(f"Removed {len(removed)} GGUF file(s) and attempted Ollama rm for catalog tags.")
        return

    if not model:
        _err("Specify a model id or --all")
        raise typer.Exit(1)

    cat = None
    try:
        cat = get_catalog_model(model)
    except Exception:
        cat = None

    if not yes:
        label = cat.name if cat else model
        if not typer.confirm(f"Remove local model [bold]{label}[/]?"):
            raise typer.Abort()

    removed_files: list = []
    if cat and cat.hf_file:
        removed_files = remove_gguf(root, cat.hf_file)
    else:
        removed_files = remove_gguf(root, model)

    ollama_removed = False
    tags = cat.ollama_tags if cat else [model]
    for tag in tags:
        if loc.ollama_rm(tag):
            ollama_removed = True
            _ok(f"Ollama removed: {tag}")

    for p in removed_files:
        _ok(f"Deleted {p}")

    if not removed_files and not ollama_removed:
        _warn("Nothing removed — model not found on disk or in Ollama.")
    else:
        _ok("Done.")


@local_app.command("use")
def local_use(
    model: str = typer.Argument(..., help="Installed Ollama model name"),
) -> None:
    """Select an already-installed local model as Ravi default."""
    root = _root()
    eu.ensure_secrets(root)
    installed = loc.installed_model_names()
    if installed and model not in installed and not any(
        m.startswith(model) for m in installed
    ):
        _warn(f"{model} not in Ollama list. Pulling…")
        local_pull(model)
        return
    _activate_local_model(root, model)




# ---------------------------------------------------------------------------
# Config / media toggles
# ---------------------------------------------------------------------------

@config_app.command("show")
def config_show() -> None:
    """Show current Ravi settings."""
    root = _root()
    snap = rsettings.snapshot(root)
    hw = snap["hardware"]
    table = Table(title="Ravi settings", border_style="cyan")
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    rows = [
        ("LLM backend", f"{snap['backend']}  (llama.cpp default · ollama optional)"),
        ("Language", f"{snap['language']} ({snap['language_name']})"),
        ("Default model", snap["default_model"]),
        ("Stack status", snap.get("status") or "off"),
        ("Confirms", (eu.parse_env(eu.env_path(root)).get("RAVI_CONFIRMS") or "medium")),
        ("Smart log", (eu.parse_env(eu.env_path(root)).get("RAVI_SMART_LOG") or "off")),
        ("LLM loaded", snap.get("llm", "on")),
        ("Models dir", snap.get("models_dir", "./models")),
        ("Context", snap["context"]),
        ("Threads", snap["threads"]),
        ("Voice", snap["voice"]),
        ("Image gen", snap["image"]),
        ("Video gen", snap["video"]),
        ("Voice model", snap["voice_model"]),
        ("Image model", snap["image_model"]),
        ("Video model", snap["video_model"]),
        (
            "Hardware",
            f"RAM={hw.get('detected_ram_gb') or '?'} GB  "
            f"cores={hw.get('detected_cores')}  "
            f"preset={hw.get('id')}",
        ),
    ]
    for k, v in rows:
        table.add_row(k, str(v))
    console.print(table)
    console.print(
        "\n[dim]Switch backend[/]  [cyan]ravi config backend llama[/]  ·  "
        "[cyan]ravi config backend ollama[/]\n"
        "[dim]Language[/]        [cyan]ravi config lang fa[/]\n"
        "[dim]Context[/]         [cyan]ravi config set context 8192[/]"
    )


@config_app.command("backend")
def config_backend(
    name: str = typer.Argument(..., help="llama | ollama"),
) -> None:
    """Select local LLM backend (default: llama.cpp)."""
    root = _root()
    rsettings.ensure_default_env(root)
    key = name.strip().lower()
    if key in ("llama", "llama.cpp", "llamacpp"):
        key = "llama"
    elif key in ("ollama",):
        key = "ollama"
    else:
        _err("Use [bold]llama[/] or [bold]ollama[/].")
        raise typer.Exit(1)
    eu.write_env_value(eu.env_path(root), "RAVI_LLM_BACKEND", key)
    _ok(f"LLM backend → [bold cyan]{key}[/]")
    if key == "ollama":
        _say(
            "Ollama is optional. Start it with:\n"
            "  [cyan]docker compose --profile ollama up -d[/]\n"
            "  or install https://ollama.com"
        )
    else:
        _say(
            "Using [bold]llama.cpp[/] (default). Place GGUF files under [cyan]models/[/]\n"
            "  [cyan]ravi local pull[/]  downloads the default Qwen3-4B Instruct GGUF."
        )


@config_app.command("lang")
def config_lang(
    code: str = typer.Argument(..., help="Language code, e.g. en, fa, de, zh"),
) -> None:
    """Set chat language (stored in .env as RAVI_LANG)."""
    root = _root()
    rsettings.ensure_default_env(root)
    code = code.strip().lower()
    name = rsettings.LANG_NAMES.get(code, code)
    eu.write_env_value(eu.env_path(root), "RAVI_LANG", code)
    _ok(f"Language → [bold cyan]{code}[/] ({name})")
    _say("Chat replies will prefer this language when the model supports it.")


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="context | threads | model | welcome"),
    value: str = typer.Argument(...),
) -> None:
    """Set a runtime value in .env."""
    root = _root()
    rsettings.ensure_default_env(root)
    mapping = {
        "context": "RAVI_CONTEXT",
        "threads": "RAVI_THREADS",
        "model": "RAVI_DEFAULT_MODEL",
        "welcome": "RAVI_WELCOME_MESSAGE",
        "backend": "RAVI_LLM_BACKEND",
        "lang": "RAVI_LANG",
        "language": "RAVI_LANG",
    }
    env_key = mapping.get(key.lower()) or key.upper()
    if not env_key.startswith("RAVI_") and key.upper() not in mapping:
        env_key = key if key.startswith("RAVI_") else f"RAVI_{key.upper()}"
    eu.write_env_value(eu.env_path(root), env_key, value)
    _ok(f"{env_key} → [cyan]{value}[/]")


def _toggle_media(flag_key: str, model_key: str, state: str, label: str) -> None:
    root = _root()
    rsettings.ensure_default_env(root)
    state = state.strip().lower()
    if state not in ("on", "off"):
        _err("Use [bold]on[/] or [bold]off[/].")
        raise typer.Exit(1)
    rsettings.set_toggle(root, flag_key, state)
    env = eu.parse_env(eu.env_path(root))
    model = env.get(model_key, "")
    if state == "on":
        _ok(f"{label} [green]ON[/]  · model [cyan]{model}[/]")
        if label == "Image":
            _say(
                "[dim]Image weights load only while generating. "
                "Other models may be unloaded to free RAM.[/]"
            )
        if label == "Video":
            _say("[dim]Video is experimental and off by default.[/]")
        if label == "Voice":
            _say("[dim]Assistant replies will be spoken when TTS is available.[/]")
    else:
        _ok(f"{label} [yellow]OFF[/]  · marked idle (weights should leave RAM)")
        # best-effort: no dedicated media containers yet




@app.command()
def llm(
    state: str = typer.Argument(..., help="on | off"),
) -> None:
    """Load or unload the language model runtime (frees RAM when off)."""
    root = _root()
    rsettings.ensure_default_env(root)
    state = state.strip().lower()
    if state not in ("on", "off"):
        _err("Use [bold]on[/] or [bold]off[/].")
        raise typer.Exit(1)
    env = eu.parse_env(eu.env_path(root))
    if state == "off":
        msg = rmedia.unload_llm(root, env)
        _ok(msg)
        _say(
            "Docker services for the LLM were stopped if possible. "
            "The [bold]ravi[/] CLI stays installed. "
            "Use [cyan]ravi start[/] or [cyan]ravi llm on[/] later."
        )
    else:
        _ok(rmedia.load_llm(root))


@app.command()
def voice(
    state: str = typer.Argument(..., help="on | off"),
) -> None:
    """Enable or disable local voice (Kokoro ONNX TTS)."""
    _toggle_media("RAVI_VOICE", "RAVI_VOICE_MODEL", state, "Voice")


@app.command()
def image(
    state: str = typer.Argument(..., help="on | off"),
) -> None:
    """Enable or disable local image generation (stable-diffusion.cpp)."""
    _toggle_media("RAVI_IMAGE", "RAVI_IMAGE_MODEL", state, "Image")


@app.command()
def video(
    state: str = typer.Argument(..., help="on | off"),
) -> None:
    """Enable or disable experimental video generation (off by default)."""
    _toggle_media("RAVI_VIDEO", "RAVI_VIDEO_MODEL", state, "Video")



@app.command("share")
def share_cmd(
    force: bool = typer.Option(
        False, "--force", help="Continue even if not running as admin/sudo"
    ),
) -> None:
    """Prepare RAVI_MODELS_DIR for Docker file access (run as admin / sudo)."""
    banner()
    root = _root()
    env = rsettings.ensure_default_env(root)
    models = env.get("RAVI_MODELS_DIR") or "./models"

    if not rshare.is_elevated() and not force:
        _warn("Not running as administrator / root.")
        console.print(rshare.elevation_hint())
        _say("You can retry with [cyan]--force[/] to only create the folder.")
        raise typer.Exit(2)

    ok, lines = rshare.run_share(root, models)
    for line in lines:
        if ok:
            _say(line)
        else:
            _warn(line)
    # Persist absolute path back to .env when relative
    resolved = rshare.resolve_models_dir(models, root)
    eu.write_env_value(eu.env_path(root), "RAVI_MODELS_DIR", str(resolved).replace("\\\\", "/"))
    _ok(f"RAVI_MODELS_DIR → [cyan]{resolved}[/]")
    if ok:
        _ok("Share setup finished. Restart Docker Desktop if you are on Windows/macOS.")
    else:
        raise typer.Exit(1)





@app.command("events")
def events_cmd(
    limit: int = typer.Option(50, "--limit", "-n", help="Max events to show"),
    smart: bool = typer.Option(
        False, "--smart", help="Prefer LLM summaries when available"
    ),
    all_events: bool = typer.Option(
        False, "--all", help="Include already-read events (default: unread only for voice)"
    ),
    skip: bool = typer.Option(
        False,
        "--skip",
        help="Mark all unread events as read without speaking them",
    ),
) -> None:
    """Show structured Ravi events; speak unread ones when voice is on."""
    root = _root()
    env = rsettings.ensure_default_env(root)

    if skip:
        n = rlog.mark_events_read(all_unread=True)
        _ok(f"Marked {n} event(s) as read.")
        return

    unread = rlog.fetch_events(limit=limit, unread_only=not all_events, smart=smart)
    if all_events:
        rows = rlog.fetch_events(limit=limit, unread_only=False, smart=smart)
    else:
        rows = unread

    if not rows:
        _say("[dim]No events to show.[/]")
        return

    table = Table(title="Ravi events", border_style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("When")
    table.add_column("Cat")
    table.add_column("Type")
    table.add_column("Message")
    table.add_column("Read")
    for row in rows:
        when = str(row.get("created_at") or "")[:19]
        table.add_row(
            str(row.get("id")),
            when,
            str(row.get("category") or ""),
            str(row.get("event_type") or ""),
            str(row.get("message") or "")[:100],
            "yes" if row.get("read_at") else "no",
        )
    console.print(table)

    # Speak unread in order when voice is on
    voice_on = rsettings.is_on(env, "RAVI_VOICE")
    to_speak = [r for r in rows if not r.get("read_at")]
    if not voice_on or not to_speak:
        # still mark displayed unread as read if voice off? User asked: read when events used
        # mark as read after display when voice off too for those shown
        if to_speak and not voice_on:
            ids = [int(r["id"]) for r in to_speak if str(r.get("id")).isdigit()]
            rlog.mark_events_read(ids)
        return

    _say(
        f"[cyan]Voice ON[/] — reading {len(to_speak)} unread report(s). "
        "Press Enter to skip the rest."
    )
    for row in to_speak:
        spoken_text = str(row.get("llm_summary") or row.get("message") or "").strip()
        if not spoken_text:
            continue
        console.print(
            Panel(
                spoken_text,
                title=f"[cyan]Report[/] #{row.get('id')}",
                border_style="cyan",
            )
        )
        try:
            rmedia.maybe_speak(spoken_text, env)
        except Exception:
            pass
        try:
            eid = int(row["id"])
            rlog.mark_event_spoken(eid)
        except Exception:
            pass
        # non-blocking skip opportunity between items
        try:
            import select
            import sys

            _say("[dim]Enter=skip remaining · waiting 0.3s…[/]")
            # simple prompt
            line = console.input("[dim](Enter skip, or type ok)[/] ").strip().lower()
            if line in ("", "s", "skip", "q"):
                n = rlog.mark_events_read(all_unread=True)
                _ok(f"Skipped. Marked {n} remaining event(s) as read.")
                return
        except Exception:
            pass


@app.command("smartlog")
def smartlog_cmd(
    state: str = typer.Argument(..., help="on | off"),
) -> None:
    """Enable/disable LLM log rewriting. Worker stays up when turning off."""
    root = _root()
    rsettings.ensure_default_env(root)
    state = state.strip().lower()
    if state not in ("on", "off"):
        _err("Use on or off")
        raise typer.Exit(1)
    eu.write_env_value(eu.env_path(root), "RAVI_SMART_LOG", state)
    _ok(f"RAVI_SMART_LOG → [bold]{state}[/]")

    if state == "on":
        _say("Starting smartlog worker container…")
        try:
            cmd = [
                "docker",
                "compose",
                "-f",
                str(root / "docker-compose.yml"),
                "up",
                "-d",
                "worker",
            ]
            p = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
            if p.returncode == 0:
                _ok("Worker is up (profile: smartlog).")
            else:
                _warn(
                    "Could not start worker automatically.\n"
                    + (p.stderr or p.stdout or "")[:400]
                    + "\nTry: [cyan]docker compose --profile smartlog up -d worker[/]"
                )
        except Exception as e:
            _warn(f"Worker start failed: {e}")
        try:
            rlog.log_event(
                "smartlog_on",
                "Smart log rewriting enabled and worker start requested",
                category="system",
                tags=["smartlog", "on"],
                env=eu.parse_env(eu.env_path(root)),
            )
        except Exception:
            pass
    else:
        _say(
            "Smartlog processing is [yellow]paused[/]. "
            "Celery/worker containers are left running but will not summarize."
        )
        try:
            rlog.log_event(
                "smartlog_off",
                "Smart log rewriting disabled; worker left running idle",
                category="system",
                tags=["smartlog", "off"],
                env=eu.parse_env(eu.env_path(root)),
            )
        except Exception:
            pass








@workers_app.command("web")
def workers_web(
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open Flower in the default browser"
    ),
    ensure: bool = typer.Option(
        True, "--ensure/--no-ensure", help="Start Redis, workers, and Flower if needed"
    ),
) -> None:
    """Open Celery Flower — monitor all workers, tasks, and queues."""
    root = _root()
    env = rsettings.ensure_default_env(root)
    port = (env.get("FLOWER_PORT") or "5555").strip()
    url = f"http://127.0.0.1:{port}"

    if ensure:
        _say("Ensuring Redis, workers, and Flower are running…")
        try:
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(root / "docker-compose.yml"),
                    "--profile",
                    "flower",
                    "up",
                    "-d",
                    "redis",
                    "worker",
                    "flower",
                ],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=180,
            )
        except Exception as e:
            _warn(f"Could not start workers stack: {e}")

    ready = False
    try:
        import httpx
        import time

        for _ in range(25):
            try:
                r = httpx.get(url, timeout=1.5)
                if r.status_code < 500:
                    ready = True
                    break
            except Exception:
                time.sleep(0.4)
    except Exception:
        pass

    console.print(
        Panel(
            f"[bold]Workers monitor (Flower)[/]\n\n"
            f"URL       [cyan]{url}[/]\n"
            f"Shows     active workers · running / success / failed tasks · queues\n"
            f"Note      Smartlog is one consumer of these workers; more tasks can join later.\n\n"
            f"[dim]ravi workers on[/]   start workers\n"
            f"[dim]ravi workers off[/]  stop workers (Redis/Flower can stay up)",
            title="[bold cyan]Ravi · workers[/]",
            border_style="cyan",
        )
    )

    if not ready:
        _warn(f"Flower not responding yet. When Docker is up, open: {url}")
    elif open_browser:
        try:
            import webbrowser

            webbrowser.open(url)
            _ok(f"Opened {url}")
        except Exception:
            _say(f"Open manually: [cyan]{url}[/]")
    else:
        _ok(f"Flower URL: [cyan]{url}[/]")

    try:
        rlog.log_cli_command("ravi workers web", env=env)
    except Exception:
        pass


@workers_app.command("on")
def workers_on() -> None:
    """Start Celery worker containers (and Redis if needed)."""
    root = _root()
    env = rsettings.ensure_default_env(root)
    _say("Starting workers…")
    try:
        p = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(root / "docker-compose.yml"),
                "up",
                "-d",
                "redis",
                "worker",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if p.returncode == 0:
            _ok("Workers are on.")
        else:
            _warn((p.stderr or p.stdout or "failed")[:500])
    except Exception as e:
        _warn(str(e))
    try:
        rlog.log_event(
            "workers_on",
            "Celery workers started",
            category="workers",
            tags=["workers", "on"],
            env=env,
        )
    except Exception:
        pass


@workers_app.command("off")
def workers_off() -> None:
    """Stop Celery worker containers (does not remove volumes or Redis data)."""
    root = _root()
    env = rsettings.ensure_default_env(root)
    _say("Stopping workers…")
    try:
        p = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(root / "docker-compose.yml"),
                "stop",
                "worker",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if p.returncode == 0:
            _ok("Workers are off. Queues in Redis remain; Flower can still show history.")
        else:
            _warn((p.stderr or p.stdout or "failed")[:500])
    except Exception as e:
        _warn(str(e))
    try:
        rlog.log_event(
            "workers_off",
            "Celery workers stopped",
            category="workers",
            tags=["workers", "off"],
            env=env,
        )
    except Exception:
        pass


@workers_app.command("status")
def workers_status() -> None:
    """Show worker / Flower / Redis container status."""
    root = _root()
    try:
        from ravi.ready import collect_status

        states = collect_status(root)
        table = Table(title="Workers stack", border_style="cyan")
        table.add_column("Service")
        table.add_column("Status")
        table.add_column("Detail")
        for s in states:
            if s.name not in ("worker", "flower", "redis"):
                continue
            table.add_row(
                s.name,
                "[green]up[/]" if s.ok else "[red]down[/]",
                s.detail,
            )
        console.print(table)
    except Exception as e:
        _warn(str(e))
        subprocess.run(
            ["docker", "compose", "-f", str(root / "docker-compose.yml"), "ps"],
            cwd=str(root),
        )




@errors_app.command("show")
def errors_show(
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    """Start the errors web UI (if enabled) and open it in the browser."""
    root = _root()
    env = rsettings.ensure_default_env(root)
    if not rsent.sentry_enabled(env):
        _warn(
            "Error reporting is off (RAVI_SENTRY=off). "
            "Enable with: [cyan]ravi errors on[/]"
        )
        return

    url = rsent.web_url(env)
    _say("Starting errors UI container on demand (saves RAM when idle)…")
    try:
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(root / "docker-compose.yml"),
                "--profile",
                "errors",
                "up",
                "-d",
                "glitchtip",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except Exception as e:
        _warn(f"Could not start errors UI: {e}")

    # wait briefly
    ready = False
    try:
        import httpx
        import time

        for _ in range(30):
            try:
                r = httpx.get(url, timeout=1.5)
                if r.status_code < 500:
                    ready = True
                    break
            except Exception:
                time.sleep(0.5)
    except Exception:
        pass

    console.print(
        Panel(
            f"[bold]Ravi Errors[/] (Sentry-compatible)\n\n"
            f"URL     [cyan]{url}[/]\n"
            f"DSN     {(env.get('SENTRY_DSN') or '(set SENTRY_DSN for cloud or local ingest)')[:60]}\n"
            f"Mode    capture is [green]on[/] while RAVI_SENTRY=on\n\n"
            f"[dim]Structured Ravi logs remain separate (`ravi events`).[/]",
            title="[bold cyan]errors[/]",
            border_style="cyan",
        )
    )
    if open_browser:
        try:
            import webbrowser

            webbrowser.open(url)
            _ok(f"Opened {url}")
        except Exception:
            _say(f"Open manually: [cyan]{url}[/]")
    if not ready:
        _warn("UI may still be starting — refresh in a few seconds.")


@errors_app.command("on")
def errors_on() -> None:
    """Enable Sentry error capture (does not keep the web UI running)."""
    root = _root()
    rsettings.ensure_default_env(root)
    eu.write_env_value(eu.env_path(root), "RAVI_SENTRY", "on")
    rsent.init_sentry(eu.parse_env(eu.env_path(root)))
    _ok("RAVI_SENTRY → on (SDK capture enabled)")


@errors_app.command("off")
def errors_off() -> None:
    """Disable Sentry capture and stop the errors UI container to free RAM."""
    root = _root()
    rsettings.ensure_default_env(root)
    eu.write_env_value(eu.env_path(root), "RAVI_SENTRY", "off")
    try:
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(root / "docker-compose.yml"),
                "stop",
                "glitchtip",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        pass
    _ok("RAVI_SENTRY → off (no capture; errors UI stopped)")




@profile_app.callback(invoke_without_command=True)
def profile_root(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None,
        help="small | medium | large | extra | custom",
    ),
) -> None:
    """Switch resource profile or show the active one."""
    if ctx.invoked_subcommand is not None:
        return
    root = _root()
    rsettings.ensure_default_env(root)
    if not name:
        env = eu.parse_env(eu.env_path(root))
        active = env.get("RAVI_PROFILE") or "custom"
        console.print(
            Panel(
                f"Active profile: [bold cyan]{active}[/]\n\n"
                f"[dim]small[/]   CLI + LLM only (lightest)\n"
                f"[dim]medium[/]  LLM + voice + basic logs\n"
                f"[dim]large[/]   all features (web UIs on-demand)\n"
                f"[dim]extra[/]   everything + Flower & Errors web UIs\n"
                f"[dim]custom[/]  your last manual mix\n\n"
                f"Example: [cyan]ravi profile small[/]",
                title="[bold cyan]Ravi · profile[/]",
                border_style="cyan",
            )
        )
        return

    name = name.strip().lower()
    if name not in ("small", "medium", "large", "extra", "custom"):
        _err("Use: small | medium | large | extra | custom")
        raise typer.Exit(1)

    _say(f"Applying profile [bold cyan]{name}[/]…")
    result = rprof.apply_profile(root, name)
    if not result.get("ok"):
        _err(result.get("error") or "failed")
        raise typer.Exit(1)

    flags = result.get("flags") or {}
    table = Table(title=f"Profile · {name}", border_style="green")
    table.add_column("Setting")
    table.add_column("Value")
    for k, v in flags.items():
        table.add_row(k, str(v))
    console.print(table)
    if result.get("description"):
        _ok(result["description"])
    for note in result.get("notes") or []:
        _say(f"[dim]{note}[/]")
    try:
        rlog.log_event(
            "profile_change",
            f"Applied profile {name}",
            category="system",
            tags=["profile", name],
            payload=flags,
            env=eu.parse_env(eu.env_path(root)),
        )
    except Exception:
        pass
    _ok(f"Profile [bold cyan]{name}[/] is active.")


@profile_app.command("show")
def profile_show() -> None:
    """Show active profile and flag mix."""
    root = _root()
    env = rsettings.ensure_default_env(root)
    active = env.get("RAVI_PROFILE") or "custom"
    table = Table(title=f"Active · {active}", border_style="cyan")
    table.add_column("Key")
    table.add_column("Value")
    for k in rprof.PROFILE_KEYS:
        table.add_row(k, env.get(k, "off"))
    console.print(table)




@state_app.callback(invoke_without_command=True)
def state_root(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None, help="local | cloud | both"
    ),
) -> None:
    """Switch between local, cloud-only, or both (local planner + cloud)."""
    if ctx.invoked_subcommand is not None:
        return
    root = _root()
    rsettings.ensure_default_env(root)

    def _ask(prompt: str) -> str:
        return console.input(prompt)

    if not name:
        st = rstate.get_state(root)
        console.print(
            Panel(
                f"Active state: [bold cyan]{st}[/]\n\n"
                f"[dim]local[/]  local models + your profile (default medium)\n"
                f"[dim]cloud[/]  cloud APIs only — local RAM freed\n"
                f"[dim]both[/]   local planner builds context → cloud answers\n\n"
                f"Example: [cyan]ravi state cloud[/]",
                title="[bold cyan]Ravi · state[/]",
                border_style="cyan",
            )
        )
        return

    name = name.strip().lower()
    if name == "cloud":
        _say("Switching to [bold]cloud[/] — unloading local models…")
        result = rstate.apply_cloud(root, console, _ask)
    elif name == "local":
        _say("Switching to [bold]local[/]…")
        result = rstate.apply_local(root)
    elif name == "both":
        _say("Switching to [bold]both[/] (local planner + cloud)…")
        result = rstate.apply_both(root, console, _ask)
    else:
        _err("Use: local | cloud | both")
        raise typer.Exit(1)

    if not result.get("ok"):
        _err(result.get("error") or "failed")
        raise typer.Exit(1)

    for n in result.get("notes") or []:
        _say(f"[dim]{n}[/]")
    if result.get("description"):
        _say(result["description"])
    model = result.get("model")
    if model:
        _ok(f"Default cloud model → [cyan]{model}[/]")
    _ok(f"State → [bold cyan]{result.get('state') or name}[/]")
    try:
        rlog.log_event(
            "state_change",
            f"State set to {name}",
            category="system",
            tags=["state", name],
            env=eu.parse_env(eu.env_path(root)),
        )
    except Exception:
        pass




@app.command("laya")
def laya_cmd(
    state: str = typer.Argument(..., help="on | off | status"),
) -> None:
    """Toggle Laya decision model (medium+ default on; small keeps off)."""
    root = _root()
    env = rsettings.ensure_default_env(root)
    state = state.strip().lower()
    if state == "status":
        info = layadl.detect(root)
        on = layasvc.laya_on(env)
        table = Table(title="Laya", border_style="cyan")
        table.add_column("Key")
        table.add_column("Value")
        table.add_row("RAVI_LAYA", "on" if on else "off")
        table.add_row("variant", env.get("RAVI_LAYA_VARIANT") or "english")
        table.add_row("wanted", info["wanted"])
        table.add_row("weights present", "yes" if info["wanted_present"] else "no")
        table.add_row("models path", info["models_root"])
        console.print(table)
        return
    if state not in ("on", "off"):
        _err("Use: ravi laya on | off | status")
        raise typer.Exit(1)
    eu.write_env_value(eu.env_path(root), "RAVI_LAYA", state)
    if state == "off":
        layasvc.stop(root)
        _ok("Laya → off (container stopped, RAM freed)")
        return
    # on
    def _ask() -> bool:
        try:
            return console.input("Download Laya weights now? [y/N] ").strip().lower().startswith("y")
        except Exception:
            return False

    result = layasvc.ensure_at_startup(
        root,
        ask_download=_ask,
        say=lambda m: _say(m),
    )
    _ok(f"Laya → on · {result.get('message')}")





@app.command("confirms")
def confirms_cmd(
    action: str = typer.Argument(
        ...,
        help="low | medium | high | risks <0-100> | logs [n]",
    ),
    value: Optional[str] = typer.Argument(
        None,
        help="For risks: percent 0-100. For logs: how many rows (default 10).",
    ),
) -> None:
    """Confirmation sensitivity, custom risk %, and confirmation history."""
    root = _root()
    env = rsettings.ensure_default_env(root)
    action = (action or "").strip().lower()

    # --- logs ---
    if action in ("logs", "log", "history"):
        n = 10
        if value and str(value).isdigit():
            n = max(1, min(100, int(value)))
        rows = []
        try:
            # prefer DB events tagged confirm
            all_ev = rlog.fetch_events(limit=max(n * 5, 50), unread_only=False, smart=False)
            for ev in reversed(all_ev):  # newest first later
                if (ev.get("event_type") == "command_confirm") or (
                    "confirm" in (ev.get("tags") or [])
                ):
                    rows.append(ev)
            rows = list(reversed(rows))[:n]
        except Exception:
            rows = []

        if not rows:
            # fallback jsonl scan
            try:
                import json
                from pathlib import Path as P

                for path in (P("logs/ravi-events.jsonl"), root / "logs" / "ravi-events.jsonl"):
                    if not path.is_file():
                        continue
                    for line in path.read_text(encoding="utf-8").splitlines():
                        try:
                            o = json.loads(line)
                        except Exception:
                            continue
                        if o.get("event_type") == "command_confirm" or "confirm" in (
                            o.get("tags") or []
                        ):
                            rows.append(
                                {
                                    "created_at": o.get("ts"),
                                    "message": o.get("message"),
                                    "payload": o.get("payload") or {},
                                }
                            )
                    rows = rows[-n:]
                    break
            except Exception:
                pass

        if not rows:
            _say("No confirmation events logged yet.")
            return

        table = Table(title=f"Last {len(rows)} confirmations", border_style="cyan")
        table.add_column("#", style="dim")
        table.add_column("When")
        table.add_column("Outcome")
        table.add_column("Risk")
        table.add_column("Command")
        for i, ev in enumerate(rows, 1):
            payload = ev.get("payload") or {}
            if isinstance(payload, str):
                try:
                    import json

                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            cmd = str(payload.get("command") or ev.get("message") or "")[:60]
            table.add_row(
                str(i),
                str(ev.get("created_at") or "")[:19],
                str(payload.get("outcome") or "?"),
                str(payload.get("risk_level") or ""),
                cmd,
            )
        console.print(table)

        # Human summary via LLM when possible
        blob = "\n".join(
            f"{i}. {ev.get('created_at')}: {(ev.get('payload') or {}).get('outcome')} "
            f"{(ev.get('payload') or {}).get('command', ev.get('message'))}"
            for i, ev in enumerate(rows, 1)
        )
        summary = ""
        try:
            key = env.get("LITELLM_MASTER_KEY")
            model = eu.get_default_model(env) or "gpt-3.5-turbo"
            if key:
                with httpx.Client(timeout=60.0) as client:
                    r = client.post(
                        f"{eu.proxy_base_url()}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": (
                                        "You are Ravi. Summarize confirmation history for the user "
                                        "in short, warm, plain sentences. No markdown lists of more "
                                        "than 5 bullets. Language: "
                                        + (env.get("RAVI_LANG") or "en")
                                    ),
                                },
                                {
                                    "role": "user",
                                    "content": f"Recent command confirmations:\n{blob}",
                                },
                            ],
                            "max_tokens": 350,
                        },
                    )
                if r.status_code < 400:
                    summary = (
                        r.json()
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
        except Exception:
            summary = ""

        if not summary:
            summary = (
                f"You have {len(rows)} recent confirmation event(s). "
                "Use the table above for details."
            )

        console.print(Panel(summary, title="[cyan]Ravi · confirms[/]", border_style="cyan"))
        try:
            rmedia.maybe_speak(summary[:500], env)
        except Exception:
            pass

        # Optional Q&A
        try:
            q = console.input(
                "[dim]Ask about these reports (Enter to skip):[/] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            q = ""
        if q:
            try:
                key = env.get("LITELLM_MASTER_KEY")
                model = eu.get_default_model(env) or "gpt-3.5-turbo"
                with httpx.Client(timeout=90.0) as client:
                    r = client.post(
                        f"{eu.proxy_base_url()}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": (
                                        "You are Ravi. Answer clearly about the confirmation log. "
                                        "Be complete but easy to listen to aloud."
                                    ),
                                },
                                {
                                    "role": "user",
                                    "content": f"Log:\n{blob}\n\nQuestion: {q}",
                                },
                            ],
                            "max_tokens": 500,
                        },
                    )
                ans = (
                    r.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                    if r.status_code < 400
                    else ""
                )
                if ans:
                    console.print(Panel(ans, title="[cyan]Answer[/]", border_style="green"))
                    try:
                        rmedia.maybe_speak(ans[:500], env)
                    except Exception:
                        pass
            except Exception as e:
                _warn(str(e))
        return

    # --- risks N (custom percent) ---
    if action in ("risks", "risk", "percent", "pct"):
        if value is None or not str(value).replace(".", "", 1).isdigit():
            _err("Usage: ravi confirms risks <0-100>")
            raise typer.Exit(1)
        pct = float(value)
        if pct < 0 or pct > 100:
            _err("Percent must be between 0 and 100")
            raise typer.Exit(1)
        eu.write_env_value(eu.env_path(root), "RAVI_CONFIRMS", "custom")
        eu.write_env_value(eu.env_path(root), "RAVI_CONFIRMS_RISKS", str(pct))
        _ok(
            f"Custom threshold → confirm when risk score ≥ [bold cyan]{pct:g}%[/] "
            f"({pct/100:.2f})"
        )
        _say("Works with Laya when [cyan]ravi laya on[/].")
        return

    # --- presets ---
    aliases = {
        "low": "low",
        "l": "low",
        "medium": "medium",
        "med": "medium",
        "m": "medium",
        "high": "high",
        "h": "high",
        "strict": "high",
        "loose": "low",
    }
    level = aliases.get(action, action)
    if level not in ("low", "medium", "high"):
        _err(
            "Use:\n"
            "  ravi confirms low|medium|high\n"
            "  ravi confirms risks <0-100>\n"
            "  ravi confirms logs [n]"
        )
        raise typer.Exit(1)
    thr = {"low": "66%", "medium": "33%", "high": "18%"}[level]
    eu.write_env_value(eu.env_path(root), "RAVI_CONFIRMS", level)
    # clear custom percent when using preset
    try:
        eu.write_env_value(eu.env_path(root), "RAVI_CONFIRMS_RISKS", "")
    except Exception:
        pass
    _ok(f"RAVI_CONFIRMS → [bold cyan]{level}[/] (confirm when risk ≥ {thr})")
    _say(
        "[dim]low[/]    higher-risk only\n"
        "[dim]medium[/] balanced\n"
        "[dim]high[/]   ask more often\n"
        "[dim]custom[/] ravi confirms risks 5"
    )



@app.callback()
def main() -> None:
    """Ravi — Open Source AI Infrastructure."""
    pass


if __name__ == "__main__":
    app()
