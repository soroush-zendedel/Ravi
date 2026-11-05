"""Wait until core Docker services are active before Ravi continues."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from ravi import envutil as eu


@dataclass
class ServiceState:
    name: str
    ok: bool
    detail: str = ""


CORE_SERVICES = ("redis", "db", "litellm")  # litellm may be named differently
OPTIONAL_SERVICES = ("worker", "llama", "ollama", "flower")


def _compose_ps(root: Path) -> str:
    try:
        p = subprocess.run(
            ["docker", "compose", "-f", str(root / "docker-compose.yml"), "ps", "--format", "json"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return p.stdout or ""
    except Exception as e:
        return str(e)


def list_running_names(root: Path) -> set[str]:
    import json

    raw = _compose_ps(root)
    names: set[str] = set()
    # docker compose ps --format json may be NDJSON or array
    raw = raw.strip()
    if not raw:
        # fallback
        p = subprocess.run(
            ["docker", "compose", "-f", str(root / "docker-compose.yml"), "ps", "--services", "--filter", "status=running"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {ln.strip() for ln in (p.stdout or "").splitlines() if ln.strip()}
    try:
        if raw.startswith("["):
            items = json.loads(raw)
        else:
            items = [json.loads(line) for line in raw.splitlines() if line.strip()]
        for it in items:
            if not isinstance(it, dict):
                continue
            state = (it.get("State") or it.get("Status") or "").lower()
            svc = it.get("Service") or it.get("Name") or ""
            if "run" in state or state == "running":
                # strip project prefix from Name
                names.add(svc)
                n = it.get("Name") or ""
                if n:
                    names.add(n)
    except Exception:
        pass
    return names


def compose_up_all(root: Path, *, build: bool = False) -> tuple[bool, str]:
    """Start core stack. Flower is NOT included (on-demand). Errors UI only if RAVI_SENTRY=on."""
    cmd = [
        "docker",
        "compose",
        "-f",
        str(root / "docker-compose.yml"),
        "--profile",
        "llama",
        "up",
        "-d",
    ]
    # Flower + GlitchTip are on-demand (ravi workers web / ravi errors show)
    # to avoid idle RAM use. RAVI_SENTRY only enables the SDK at runtime.
    if build:
        cmd.append("--build")
    try:
        p = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=600)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode == 0, out[-2000:]
    except Exception as e:
        return False, str(e)


def proxy_healthy(timeout: float = 2.0) -> bool:
    try:
        import httpx

        r = httpx.get(f"{eu.proxy_base_url()}/health", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def redis_ok() -> bool:
    try:
        import socket

        s = socket.create_connection(("127.0.0.1", 6379), timeout=1.5)
        s.close()
        return True
    except Exception:
        return False


def postgres_ok() -> bool:
    try:
        import socket

        s = socket.create_connection(("127.0.0.1", 5432), timeout=1.5)
        s.close()
        return True
    except Exception:
        return False


def collect_status(root: Path) -> list[ServiceState]:
    running = list_running_names(root)
    states: list[ServiceState] = []

    def has(svc: str) -> bool:
        if svc in running:
            return True
        return any(svc in n for n in running)

    states.append(ServiceState("redis", redis_ok() or has("redis"), "port 6379" if redis_ok() else "checking container"))
    states.append(
        ServiceState(
            "postgres",
            postgres_ok() or has("db") or has("postgres"),
            "port 5432" if postgres_ok() else "checking container",
        )
    )
    # litellm / proxy
    litellm_name = has("litellm") or has("proxy") or has("ravi-proxy")
    states.append(
        ServiceState(
            "proxy",
            proxy_healthy() or litellm_name,
            "healthy" if proxy_healthy() else "starting",
        )
    )
    states.append(ServiceState("worker", has("worker") or has("ravi-worker"), "celery worker"))
    states.append(ServiceState("llama", has("llama") or has("ravi-llama"), "llama.cpp (optional until model mounted)"))
    states.append(ServiceState("flower", has("flower") or has("ravi-flower"), "http://127.0.0.1:5555"))
    return states


def wait_until_active(
    root: Path,
    *,
    timeout_sec: int = 120,
    poll: float = 2.0,
    on_progress=None,
) -> tuple[bool, list[ServiceState]]:
    """
    Block until core services look up, or timeout.
    Returns (active, last_states).
    """
    deadline = time.time() + timeout_sec
    last: list[ServiceState] = []
    while time.time() < deadline:
        last = collect_status(root)
        try:
            last = last + check_connections(root)
        except Exception:
            pass
        core_ok = all(
            s.ok for s in last if s.name in ("redis", "db", "proxy")
        )
        basic = all(s.ok for s in last if s.name in ("redis", "db"))
        links_ok = all(
            s.ok for s in last if s.name in ("redis↔cli", "postgres↔ready")
        ) if any(s.name == "redis↔cli" for s in last) else True
        if on_progress:
            on_progress(last, core_ok and links_ok)
        if core_ok and links_ok:
            return True, last
        if basic and proxy_healthy() and links_ok:
            return True, last
        time.sleep(poll)
    return False, last


def set_status_flag(root: Path, status: str) -> None:
    """Persist RAVI_STATUS to .env and current process env (on|off)."""
    status = "on" if str(status).lower() in ("on", "1", "true", "yes", "active") else "off"
    try:
        eu.write_env_value(eu.env_path(root), "RAVI_STATUS", status)
    except Exception:
        pass
    try:
        import os

        os.environ["RAVI_STATUS"] = status
    except Exception:
        pass


def get_status(root: Path | None = None) -> str:
    """Read RAVI_STATUS from environment, then .env (default off)."""
    import os

    v = (os.environ.get("RAVI_STATUS") or "").strip().lower()
    if v in ("on", "off"):
        return v
    if root is not None:
        try:
            env = eu.parse_env(eu.env_path(root))
            v = (env.get("RAVI_STATUS") or "off").strip().lower()
            if v in ("on", "1", "true", "yes", "active"):
                return "on"
        except Exception:
            pass
    return "off"



def check_connections(root: Path) -> list[ServiceState]:
    """Verify inter-service connectivity from the host perspective."""
    results: list[ServiceState] = []
    # Redis PING via socket already covered; try redis-cli in container
    try:
        p = subprocess.run(
            ["docker", "exec", "ravi-redis", "redis-cli", "ping"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ok = p.returncode == 0 and "PONG" in (p.stdout or "").upper()
        results.append(ServiceState("redis↔cli", ok, (p.stdout or p.stderr or "")[:40]))
    except Exception as e:
        results.append(ServiceState("redis↔cli", False, str(e)[:60]))

    try:
        p = subprocess.run(
            [
                "docker",
                "exec",
                "ravi-postgres",
                "pg_isready",
                "-U",
                "ravi",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ok = p.returncode == 0
        results.append(ServiceState("postgres↔ready", ok, (p.stdout or p.stderr or "")[:50]))
    except Exception as e:
        results.append(ServiceState("postgres↔ready", False, str(e)[:60]))

    # worker can reach redis (best-effort)
    try:
        p = subprocess.run(
            [
                "docker",
                "exec",
                "ravi-worker",
                "python",
                "-c",
                "import socket; s=socket.create_connection(('redis',6379),2); s.close(); print('ok')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        ok = p.returncode == 0 and "ok" in (p.stdout or "")
        results.append(ServiceState("worker↔redis", ok, (p.stdout or p.stderr or "")[:40]))
    except Exception as e:
        results.append(ServiceState("worker↔redis", False, str(e)[:60]))

    results.append(
        ServiceState("proxy↔health", proxy_healthy(), eu.proxy_base_url() + "/health")
    )
    return results


def full_stack_active(root: Path) -> tuple[bool, list[ServiceState]]:
    states = collect_status(root) + check_connections(root)
    # require redis, postgres, proxy health
    need = {"redis", "db", "proxy"}
    by_name = {s.name: s for s in states}
    ok = all(by_name.get(n) and by_name[n].ok for n in need)
    # connection checks that exist must not hard-fail postgres/redis links if named
    for n in ("redis↔cli", "postgres↔ready"):
        if n in by_name and not by_name[n].ok:
            ok = False
    return ok, states
