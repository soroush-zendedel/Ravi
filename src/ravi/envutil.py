"""Helpers for reading/writing Ravi .env and project paths."""

from __future__ import annotations

import os
import secrets
import shutil
from pathlib import Path

DEFAULT_UI_USERNAME = "admin"

PLACEHOLDER_MASTER_KEYS = {
    "",
    "sk-ravi-change-me-to-a-secure-key",
    "sk-ravi-master-key-here",
    "your_secure_key_here",
    "change_me",
}
PLACEHOLDER_POSTGRES = {
    "",
    "change_me_to_a_strong_password",
    "your_secure_postgres_password_here",
    "change_me",
}


def find_project_root() -> Path:
    env_root = os.environ.get("RAVI_HOME")
    if env_root:
        p = Path(env_root).resolve()
        if (p / "docker-compose.yml").is_file():
            return p

    cwd = Path.cwd().resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "docker-compose.yml").is_file() and (
            candidate / "config.yaml"
        ).is_file():
            return candidate

    pkg = Path(__file__).resolve().parent
    for candidate in [pkg.parent.parent, pkg.parent.parent.parent]:
        if (candidate / "docker-compose.yml").is_file():
            return candidate

    raise FileNotFoundError(
        "Could not find Ravi project root (docker-compose.yml + config.yaml). "
        "Run from the Ravi repo or set RAVI_HOME."
    )


def env_path(root: Path) -> Path:
    return root / ".env"


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        result[key] = value
    return result


def write_env_value(path: Path, key: str, value: str) -> None:
    lines: list[str] = []
    found = False
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines(keepends=True):
            stripped = raw.lstrip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                lines.append(f"{key}={value}\n")
                found = True
            else:
                lines.append(raw if raw.endswith("\n") else raw + "\n")
    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{key}={value}\n")
    path.write_text("".join(lines), encoding="utf-8")


def delete_env_key(path: Path, key: str) -> bool:
    if not path.is_file():
        return False
    lines: list[str] = []
    found = False
    for raw in path.read_text(encoding="utf-8").splitlines(keepends=True):
        stripped = raw.lstrip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
            found = True
            continue
        lines.append(raw if raw.endswith("\n") else raw + "\n")
    if found:
        path.write_text("".join(lines), encoding="utf-8")
    return found


def generate_master_key() -> str:
    return "sk-ravi-" + secrets.token_hex(24)


def generate_postgres_password() -> str:
    return secrets.token_urlsafe(24)


def is_placeholder_master_key(value: str | None) -> bool:
    if value is None:
        return True
    v = value.strip()
    if v in PLACEHOLDER_MASTER_KEYS:
        return True
    if len(v) < 16 or "change-me" in v.lower() or "change_me" in v.lower():
        return True
    return False


def is_placeholder_postgres(value: str | None) -> bool:
    if value is None:
        return True
    v = value.strip()
    return v in PLACEHOLDER_POSTGRES or "change_me" in v.lower() or len(v) < 8


def is_real_secret(value: str | None, placeholders: set[str] | None = None) -> bool:
    if not value or not value.strip():
        return False
    v = value.strip()
    if placeholders and v in placeholders:
        return False
    low = v.lower()
    if any(
        x in low
        for x in (
            "change_me",
            "change-me",
            "your_",
            "example",
            "placeholder",
            "xxx",
            "todo",
        )
    ):
        return False
    return len(v) >= 8



def example_path(root: Path) -> Path:
    return root / ".env.example"



def example_path(root: Path) -> Path:
    return root / ".env.example"


def ensure_env_file(root: Path) -> Path:
    """Create `.env` from `.env.example` and merge any missing keys from the template."""
    path = env_path(root)
    example = example_path(root)
    if not path.is_file():
        if example.is_file():
            path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            path.write_text(
                "# Ravi .env\nLITELLM_MASTER_KEY=\nPOSTGRES_PASSWORD=\n",
                encoding="utf-8",
            )
    elif example.is_file():
        merge_missing_from_example(path, example)
    return path


def merge_missing_from_example(env_file: Path, example: Path) -> list[str]:
    """Append keys that exist in the template but not in `.env`."""
    current = parse_env(env_file)
    added: list[str] = []
    example_lines = example.read_text(encoding="utf-8").splitlines()
    to_append: list[str] = []
    pending_comments: list[str] = []
    for raw in example_lines:
        stripped = raw.strip()
        if not stripped:
            pending_comments.append(raw)
            continue
        if stripped.startswith("#"):
            pending_comments.append(raw)
            continue
        if "=" not in raw:
            pending_comments = []
            continue
        key = raw.split("=", 1)[0].strip()
        if key and key not in current:
            if to_append and to_append[-1] != "":
                to_append.append("")
            to_append.extend(pending_comments)
            to_append.append(raw)
            added.append(key)
            current[key] = raw.split("=", 1)[1].strip() if "=" in raw else ""
        pending_comments = []
    if to_append:
        existing = env_file.read_text(encoding="utf-8").rstrip()
        block = "\n".join(to_append)
        env_file.write_text(
            existing + "\n\n# --- merged from .env.example ---\n" + block + "\n",
            encoding="utf-8",
        )
    return added


def ensure_secrets(root: Path) -> dict[str, str]:
    """Ensure .env exists with real master key + postgres password."""
    path = ensure_env_file(root)
    env = parse_env(path)

    master = env.get("LITELLM_MASTER_KEY")
    if is_placeholder_master_key(master):
        master = generate_master_key()
        write_env_value(path, "LITELLM_MASTER_KEY", master)
        env["LITELLM_MASTER_KEY"] = master

    pg = env.get("POSTGRES_PASSWORD")
    if is_placeholder_postgres(pg):
        pg = generate_postgres_password()
        write_env_value(path, "POSTGRES_PASSWORD", pg)
        env["POSTGRES_PASSWORD"] = pg

    if not (env.get("UI_USERNAME") or "").strip():
        write_env_value(path, "UI_USERNAME", DEFAULT_UI_USERNAME)
        env["UI_USERNAME"] = DEFAULT_UI_USERNAME

    return parse_env(path)


def proxy_base_url() -> str:
    return os.environ.get("RAVI_URL", "http://127.0.0.1:4000").rstrip("/")


def get_default_model(env: dict[str, str]) -> str | None:
    return (env.get("RAVI_DEFAULT_MODEL") or "").strip() or None


def set_default_model(root: Path, model: str) -> None:
    write_env_value(env_path(root), "RAVI_DEFAULT_MODEL", model)


DEFAULT_WELCOME = (
    "Hello! I am Ravi, your local AI gateway. "
    "Ask me anything — I am ready when you are."
)


def get_welcome_message(env: dict[str, str]) -> str:
    msg = (env.get("RAVI_WELCOME_MESSAGE") or "").strip()
    return msg or DEFAULT_WELCOME


def set_welcome_message(root: Path, message: str) -> None:
    write_env_value(env_path(root), "RAVI_WELCOME_MESSAGE", message)
