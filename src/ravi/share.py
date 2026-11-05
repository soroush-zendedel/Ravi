"""Docker host-path sharing for RAVI_MODELS_DIR (Linux / Windows)."""

from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path


def is_windows() -> bool:
    return platform.system().lower().startswith("win")


def is_linux() -> bool:
    return platform.system().lower() == "linux"


def is_elevated() -> bool:
    if is_windows():
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except Exception:
        return False


def elevation_hint() -> str:
    if is_windows():
        return (
            "Re-run from an elevated PowerShell / CMD (Run as administrator):\n"
            "  ravi share"
        )
    return (
        "Re-run with sudo so Ravi can adjust permissions / Docker access:\n"
        "  sudo ravi share\n"
        "  sudo -E ravi share"
    )


def resolve_models_dir(raw: str, root: Path) -> Path:
    raw = (raw or "./models").strip() or "./models"
    p = Path(raw)
    if not p.is_absolute():
        p = (root / p).resolve()
    else:
        p = p.expanduser().resolve()
    return p


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def linux_prepare(path: Path) -> list[str]:
    """Make path traversable for the Docker engine user where possible."""
    notes: list[str] = []
    ensure_dir(path)
    try:
        # u+rwx,g+rx,o+rx so container engines can traverse bind mounts
        mode = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
        os.chmod(path, mode)
        notes.append(f"Permissions set on {path} (755-style).")
    except Exception as e:
        notes.append(f"Could not chmod {path}: {e}")

    # SELinux: label for container use when chcon exists
    if shutil.which("chcon"):
        try:
            subprocess.run(
                ["chcon", "-Rt", "container_file_t", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            notes.append("SELinux context container_file_t applied (if SELinux is enforcing).")
        except Exception as e:
            notes.append(f"chcon skipped: {e}")

    # Docker group check
    try:
        import grp

        docker_gid = grp.getgrnam("docker").gr_gid
        notes.append(f"Docker group gid={docker_gid}. Ensure your user is in the docker group.")
    except Exception:
        notes.append("Docker group not found — install Docker Engine if needed.")

    notes.append(
        "Linux Docker bind-mounts do not use Docker Desktop 'File sharing'. "
        "A readable host path is enough; this command prepared that path."
    )
    return notes


def _docker_desktop_settings_candidates() -> list[Path]:
    home = Path.home()
    return [
        home / "AppData/Roaming/Docker/settings.json",
        home / "AppData/Roaming/Docker/settings-store.json",
        home / ".docker/desktop/settings.json",
        home / "Library/Group Containers/group.com.docker/settings.json",
        home / ".docker/daemon.json",
    ]


def windows_prepare(path: Path) -> list[str]:
    notes: list[str] = []
    ensure_dir(path)
    # Normalize to forward-slash style often preferred in compose
    drive = path.drive
    notes.append(f"Models directory ready: {path}")

    # Try Docker Desktop shared folders list
    patched = False
    for settings in _docker_desktop_settings_candidates():
        if not settings.is_file():
            continue
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except Exception:
            continue

        # Common keys across Desktop versions
        changed = False
        for key in ("filesharingDirectories", "FileSharingDirectories"):
            dirs = data.get(key)
            if isinstance(dirs, list):
                entry = str(path)
                # also add drive root e.g. D:/
                drive_root = f"{path.drive}/" if path.drive else None
                for item in (entry, drive_root):
                    if item and item not in dirs:
                        dirs.append(item)
                        changed = True
                data[key] = dirs

        # nested structures in newer Desktop
        if isinstance(data.get("filesharing"), dict):
            dirs = data["filesharing"].get("directories") or data["filesharing"].get(
                "Directories"
            )
            if isinstance(dirs, list):
                if str(path) not in dirs:
                    dirs.append(str(path))
                    changed = True

        if changed:
            backup = settings.with_suffix(settings.suffix + ".ravi.bak")
            if not backup.is_file():
                backup.write_text(settings.read_text(encoding="utf-8"), encoding="utf-8")
            settings.write_text(json.dumps(data, indent=2), encoding="utf-8")
            notes.append(f"Updated Docker Desktop settings: {settings}")
            notes.append(f"Backup: {backup}")
            notes.append("Restart Docker Desktop for file sharing changes to apply.")
            patched = True
            break

    if not patched:
        notes.append(
            "Could not auto-edit Docker Desktop settings.json. "
            "Add the folder manually: Docker Desktop → Settings → Resources → File sharing."
        )
        notes.append(f"Share at least: {path} (or the whole drive {path.drive}\\)")

    notes.append(
        "In `.env` prefer forward slashes, e.g. RAVI_MODELS_DIR=D:/ravi-models"
    )
    return notes


def macos_prepare(path: Path) -> list[str]:
    notes: list[str] = []
    ensure_dir(path)
    notes.append(f"Models directory ready: {path}")
    notes.append(
        "Docker Desktop on macOS: Settings → Resources → File sharing — "
        f"ensure {path} (or its parent) is listed, then Apply & Restart."
    )
    # Best-effort same settings patch as Windows paths under ~/Library
    for settings in _docker_desktop_settings_candidates():
        if not settings.is_file():
            continue
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except Exception:
            continue
        changed = False
        for key in ("filesharingDirectories", "FileSharingDirectories"):
            dirs = data.get(key)
            if isinstance(dirs, list) and str(path) not in dirs:
                dirs.append(str(path))
                data[key] = dirs
                changed = True
        if changed:
            backup = settings.with_suffix(settings.suffix + ".ravi.bak")
            if not backup.is_file():
                backup.write_text(settings.read_text(encoding="utf-8"), encoding="utf-8")
            settings.write_text(json.dumps(data, indent=2), encoding="utf-8")
            notes.append(f"Updated {settings} (restart Docker Desktop).")
            break
    return notes


def run_share(root: Path, models_dir_value: str) -> tuple[bool, list[str]]:
    """
    Prepare host path for Docker bind-mount.
    Returns (ok, message_lines).
    """
    lines: list[str] = []
    path = resolve_models_dir(models_dir_value, root)
    lines.append(f"Target models path: {path}")

    if not is_elevated():
        lines.append("Administrator / root privileges are recommended.")
        lines.append(elevation_hint())
        # still create directory without elevation if possible
        try:
            ensure_dir(path)
            lines.append("Directory created without elevation.")
        except Exception as e:
            lines.append(f"Cannot create directory without elevation: {e}")
            return False, lines

    try:
        if is_windows():
            lines.extend(windows_prepare(path))
        elif is_linux():
            lines.extend(linux_prepare(path))
        else:
            lines.extend(macos_prepare(path))
        return True, lines
    except Exception as e:
        lines.append(f"Share setup failed: {e}")
        return False, lines
