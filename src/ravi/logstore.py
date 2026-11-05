"""Programmatic event + chat logging (Postgres/Redis). LLM rewrite is optional/queued."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Soft deps — never crash CLI if DB is down

def _database_url() -> str | None:
    url = os.environ.get("DATABASE_URL") or os.environ.get("RAVI_DATABASE_URL")
    if url:
        return url
    user = os.environ.get("POSTGRES_USER", "ravi")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "ravi")
    if not password:
        # try local .env via env already loaded
        return None
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _redis_url() -> str:
    return os.environ.get("REDIS_URL") or os.environ.get("RAVI_REDIS_URL") or "redis://127.0.0.1:6379/0"


def smart_log_enabled(env: dict[str, str] | None = None) -> bool:
    env = env or {}
    val = (env.get("RAVI_SMART_LOG") or os.environ.get("RAVI_SMART_LOG") or "off").lower()
    return val in ("on", "1", "true", "yes")


def _connect():
    url = _database_url()
    if not url:
        return None
    try:
        import psycopg2

        return psycopg2.connect(url)
    except Exception:
        try:
            # host port from docker published 5432
            import psycopg2

            user = os.environ.get("POSTGRES_USER", "ravi")
            password = os.environ.get("POSTGRES_PASSWORD", "")
            return psycopg2.connect(
                host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
                port=int(os.environ.get("POSTGRES_PORT", "5432")),
                user=user,
                password=password,
                dbname=os.environ.get("POSTGRES_DB", "ravi"),
            )
        except Exception:
            return None


def log_event(
    event_type: str,
    message: str,
    *,
    category: str = "system",
    level: str = "info",
    tags: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    source: str = "cli",
    lang: str = "en",
    env: dict[str, str] | None = None,
) -> int | None:
    """Store a structured event. Returns row id or None if DB unavailable."""
    tags = tags or []
    payload = payload or {}
    conn = _connect()
    if conn is None:
        _fallback_file(event_type, message, category, level, tags, payload)
        _enqueue_rewrite_hint(event_type, message, category, tags)
        return None
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ravi_events
                        (source, event_type, tags, category, level, message, payload, lang)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    RETURNING id
                    """,
                    (
                        source,
                        event_type,
                        tags,
                        category,
                        level,
                        message,
                        json.dumps(payload),
                        lang,
                    ),
                )
                row = cur.fetchone()
                eid = int(row[0]) if row else None
        if smart_log_enabled(env) and eid is not None:
            enqueue_smart_log(eid)
        return eid
    except Exception as e:
        try:
            from ravi import sentryutil as rsent
            rsent.capture_exception(e, where="log_event")
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        _fallback_file(event_type, message, category, level, tags, payload)
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def log_chat_turn(
    role: str,
    content: str,
    *,
    model: str | None = None,
    session_id: str | None = None,
    meta: dict | None = None,
    env: dict[str, str] | None = None,
) -> int | None:
    conn = _connect()
    session_id = session_id or os.environ.get("RAVI_SESSION_ID") or "default"
    if conn is None:
        _fallback_file(
            "chat",
            f"{role}: {content[:200]}",
            "chat",
            "info",
            ["chat", role],
            {"model": model, "session_id": session_id},
        )
        return None
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ravi_chat_turns (session_id, model, role, content, meta)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    RETURNING id
                    """,
                    (
                        session_id,
                        model,
                        role,
                        content,
                        json.dumps(meta or {}),
                    ),
                )
                row = cur.fetchone()
                tid = int(row[0]) if row else None
        if smart_log_enabled(env) and tid is not None:
            enqueue_smart_chat(tid)
        return tid
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _fallback_file(
    event_type: str,
    message: str,
    category: str,
    level: str,
    tags: list[str],
    payload: dict,
) -> None:
    try:
        path = Path(os.environ.get("RAVI_HOME", ".")) / "logs" / "ravi-events.jsonl"
        # also try cwd
        for candidate in (
            Path("logs") / "ravi-events.jsonl",
            path,
        ):
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
                entry = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "event_type": event_type,
                    "category": category,
                    "level": level,
                    "tags": tags,
                    "message": message,
                    "payload": payload,
                }
                with candidate.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                return
            except Exception:
                continue
    except Exception:
        pass


def enqueue_smart_log(event_id: int) -> None:
    try:
        import redis

        r = redis.from_url(_redis_url())
        r.lpush("ravi:smartlog:events", str(event_id))
    except Exception:
        pass


def enqueue_smart_chat(turn_id: int) -> None:
    try:
        import redis

        r = redis.from_url(_redis_url())
        r.lpush("ravi:smartlog:chats", str(turn_id))
    except Exception:
        pass


def _enqueue_rewrite_hint(*_a, **_k) -> None:
    return


def log_cli_command(command: str, args: dict | None = None, *, env: dict | None = None) -> None:
    lang = (env or {}).get("RAVI_LANG") or os.environ.get("RAVI_LANG") or "en"
    log_event(
        "cli_command",
        f"CLI command executed: {command}",
        category="cli",
        tags=["cli", command.split()[0] if command else "ravi"],
        payload={"command": command, "args": args or {}},
        lang=lang,
        env=env,
    )



def fetch_events(limit: int = 20, *, unread_only: bool = False, smart: bool = False):
    """Return list of dicts from DB or []."""
    conn = _connect()
    if not conn:
        return _fetch_events_file(limit)
    try:
        with conn.cursor() as cur:
            where = "WHERE read_at IS NULL" if unread_only else ""
            msg = "COALESCE(llm_summary, message)" if smart else "message"
            cur.execute(
                f"""
                SELECT id, created_at, category, event_type, level, {msg},
                       tags, llm_tags, read_at, llm_summary
                FROM ravi_events
                {where}
                ORDER BY id ASC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r[0],
                    "created_at": r[1],
                    "category": r[2],
                    "event_type": r[3],
                    "level": r[4],
                    "message": r[5],
                    "tags": r[6],
                    "llm_tags": r[7],
                    "read_at": r[8],
                    "llm_summary": r[9],
                }
            )
        return out
    except Exception:
        return _fetch_events_file(limit)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _fetch_events_file(limit: int) -> list[dict]:
    import json
    from pathlib import Path as P

    for path in (P("logs/ravi-events.jsonl"), P(os.environ.get("RAVI_HOME", ".")) / "logs" / "ravi-events.jsonl"):
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for i, line in enumerate(lines):
            try:
                o = json.loads(line)
                if o.get("read"):
                    continue
                out.append(
                    {
                        "id": o.get("id", i),
                        "created_at": o.get("ts"),
                        "category": o.get("category"),
                        "event_type": o.get("event_type"),
                        "level": o.get("level"),
                        "message": o.get("message"),
                        "tags": o.get("tags"),
                        "llm_tags": [],
                        "read_at": None,
                        "llm_summary": o.get("llm_summary"),
                        "_file": str(path),
                        "_line": line,
                    }
                )
            except Exception:
                pass
        return out
    return []


def mark_events_read(ids: list[int] | None = None, *, all_unread: bool = False) -> int:
    conn = _connect()
    if not conn:
        return _mark_file_read(all_unread=True)
    try:
        with conn:
            with conn.cursor() as cur:
                if all_unread:
                    cur.execute(
                        "UPDATE ravi_events SET read_at = NOW(), spoken_at = COALESCE(spoken_at, NOW()) WHERE read_at IS NULL"
                    )
                    return cur.rowcount or 0
                if not ids:
                    return 0
                cur.execute(
                    "UPDATE ravi_events SET read_at = NOW(), spoken_at = COALESCE(spoken_at, NOW()) WHERE id = ANY(%s)",
                    (list(ids),),
                )
                return cur.rowcount or 0
    except Exception:
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def mark_event_spoken(event_id: int) -> None:
    conn = _connect()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE ravi_events SET spoken_at = NOW(), read_at = COALESCE(read_at, NOW()) WHERE id = %s",
                    (event_id,),
                )
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _mark_file_read(*, all_unread: bool = True) -> int:
    import json
    from pathlib import Path as P

    n = 0
    for path in (P("logs/ravi-events.jsonl"),):
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        for line in lines:
            try:
                o = json.loads(line)
                if not o.get("read"):
                    o["read"] = True
                    n += 1
                new_lines.append(json.dumps(o, ensure_ascii=False))
            except Exception:
                new_lines.append(line)
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return n
