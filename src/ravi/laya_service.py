"""Start/stop Laya container using host models dir weights."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ravi import envutil as eu
from ravi import laya_download as layadl


def laya_on(env: dict[str, str]) -> bool:
    return (env.get("RAVI_LAYA") or "off").strip().lower() in (
        "on",
        "1",
        "true",
        "yes",
    )


def compose(root: Path, *args: str) -> tuple[int, str]:
    cmd = ["docker", "compose", "-f", str(root / "docker-compose.yml"), *args]
    try:
        p = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True, timeout=180
        )
        return p.returncode, ((p.stdout or "") + (p.stderr or ""))[-600:]
    except Exception as e:
        return 1, str(e)


def start(root: Path) -> tuple[bool, str]:
    code, out = compose(root, "--profile", "laya", "up", "-d", "laya")
    return code == 0, out


def stop(root: Path) -> tuple[bool, str]:
    code, out = compose(root, "stop", "laya")
    return code == 0, out


def ensure_at_startup(
    root: Path,
    *,
    ask_download=None,
    say=None,
) -> dict:
    """
    If RAVI_LAYA=on:
      - weights present -> start container from local files (no download)
      - missing -> ask user; on yes download permanently then start
    If off: stop container, do nothing else.
    """
    env = eu.parse_env(eu.env_path(root)) if eu.env_path(root).is_file() else {}
    info = layadl.detect(root)
    result = {"enabled": laya_on(env), "started": False, "downloaded": False, "info": info}

    if not laya_on(env):
        stop(root)
        result["message"] = "Laya is off"
        return result

    wanted = info["wanted"]
    if info["wanted_present"]:
        ok, out = start(root)
        result["started"] = ok
        result["message"] = (
            f"Laya weights found at {info['models_root']} — started container"
            if ok
            else f"Weights present but container failed: {out}"
        )
        return result

    # Missing weights
    msg = (
        f"Laya is ON but weights for {wanted} were not found under "
        f"{info['models_root']}. Download now and keep permanently on the host?"
    )
    if say:
        say(msg)
    approve = False
    if ask_download:
        try:
            approve = bool(ask_download())
        except Exception:
            approve = False
    if not approve:
        result["message"] = "Laya weights missing; download skipped"
        return result

    try:
        dest = layadl.pull(root, wanted)
        result["downloaded"] = True
        ok, out = start(root)
        result["started"] = ok
        result["message"] = f"Downloaded to {dest}; container {'up' if ok else 'failed: ' + out}"
    except Exception as e:
        result["message"] = f"Download failed: {e}"
    return result
