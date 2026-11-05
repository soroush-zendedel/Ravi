"""Optional Sentry integration — never breaks the app if disabled or offline."""

from __future__ import annotations

import os
from typing import Any


def sentry_enabled(env: dict[str, str] | None = None) -> bool:
    env = env or {}
    val = (
        env.get("RAVI_SENTRY")
        or os.environ.get("RAVI_SENTRY")
        or "on"
    ).strip().lower()
    return val in ("on", "1", "true", "yes")


def dsn(env: dict[str, str] | None = None) -> str:
    env = env or {}
    return (
        env.get("SENTRY_DSN")
        or os.environ.get("SENTRY_DSN")
        or ""
    ).strip()


def web_url(env: dict[str, str] | None = None) -> str:
    env = env or {}
    return (
        env.get("SENTRY_WEB_URL")
        or os.environ.get("SENTRY_WEB_URL")
        or "http://127.0.0.1:8000"
    ).strip()


_initialized = False


def init_sentry(env: dict[str, str] | None = None) -> bool:
    """Initialize sentry-sdk if enabled and DSN present. Soft-fail always."""
    global _initialized
    if _initialized:
        return True
    if not sentry_enabled(env):
        return False
    d = dsn(env)
    if not d:
        return False
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=d,
            traces_sample_rate=float(
                os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")
            ),
            environment=os.environ.get("RAVI_ENV", "local"),
            send_default_pii=False,
        )
        _initialized = True
        return True
    except Exception:
        return False


def capture_exception(exc: BaseException | None = None, **extra: Any) -> None:
    if not sentry_enabled():
        return
    try:
        init_sentry()
        import sentry_sdk

        if extra:
            with sentry_sdk.push_scope() as scope:
                for k, v in extra.items():
                    scope.set_extra(k, v)
                if exc is not None:
                    sentry_sdk.capture_exception(exc)
                else:
                    sentry_sdk.capture_message(str(extra.get("message") or "error"))
        else:
            if exc is not None:
                sentry_sdk.capture_exception(exc)
    except Exception:
        pass


def capture_message(message: str, *, level: str = "error", **extra: Any) -> None:
    if not sentry_enabled():
        return
    try:
        init_sentry()
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            for k, v in extra.items():
                scope.set_extra(k, v)
            sentry_sdk.capture_message(message, level=level)
    except Exception:
        pass
