"""Celery worker for optional LLM log summaries (profile: smartlog)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from celery import Celery

try:
    from ravi import sentryutil as rsent
    rsent.init_sentry()
except Exception:
    rsent = None

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
app = Celery("ravi", broker=REDIS_URL, backend=REDIS_URL)
app.conf.timezone = "UTC"
app.conf.beat_schedule = {
    "drain-smartlog": {
        "task": "ravi.worker.drain_queues",
        "schedule": 15.0,
    },
}


def _db():
    import psycopg2

    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        user=os.environ.get("POSTGRES_USER", "ravi"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        dbname=os.environ.get("POSTGRES_DB", "ravi"),
    )


def _llm_summarize(text: str, kind: str) -> tuple[str, list[str]]:
    """Return (tweet-length summary, tags). English unless RAVI_LANG set."""
    import httpx

    lang = os.environ.get("RAVI_LANG", "en")
    key = os.environ.get("LITELLM_MASTER_KEY", "")
    base = os.environ.get("RAVI_PROXY_URL", "http://litellm:4000")
    model = os.environ.get("RAVI_DEFAULT_MODEL", "gpt-3.5-turbo")
    if not key:
        return text[:240], [kind, "raw"]
    system = (
        "You are Ravi's log narrator. Write ONE short spoken-friendly sentence "
        "(max ~200 characters) that a text-to-speech voice can read aloud clearly. "
        "No markdown, no bullet points, no URLs, no code. Natural human report tone. "
        f"Language: {lang}. "
        "Then on a new line write TAGS: [\"tag1\", \"tag2\"]. "
        "Example:\n"
        "Ravi finished starting the local stack and the API is healthy.\n"
        "TAGS: [\"start\", \"docker\", \"ok\"]"
    )
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": f"Kind={kind}\n\n{text[:3000]}",
                        },
                    ],
                    "max_tokens": 200,
                },
            )
        if r.status_code >= 400:
            return text[:240], [kind, "error"]
        content = (
            r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        summary = content.strip()
        tags: list[str] = [kind]
        if "TAGS:" in summary:
            body, _, tagpart = summary.partition("TAGS:")
            summary = body.strip()
            try:
                tags = json.loads(tagpart.strip())
            except Exception:
                tags = [t.strip().strip("[]\"'") for t in tagpart.split(",") if t.strip()]
        return summary[:280], [str(t) for t in tags][:8]
    except Exception:
        return text[:240], [kind, "fallback"]


@app.task(name="ravi.worker.summarize_event")
def summarize_event(event_id: int) -> str:
    if (os.environ.get("RAVI_SMART_LOG") or "off").lower() not in (
        "on",
        "1",
        "true",
        "yes",
    ):
        return "smart log disabled"
    conn = _db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT event_type, category, message, payload FROM ravi_events WHERE id=%s",
                    (event_id,),
                )
                row = cur.fetchone()
                if not row:
                    return "missing"
                event_type, category, message, payload = row
                blob = f"{event_type}/{category}: {message}\n{payload}"
                summary, tags = _llm_summarize(blob, event_type)
                cur.execute(
                    """
                    UPDATE ravi_events
                    SET llm_summary=%s, llm_tags=%s, llm_processed_at=%s
                    WHERE id=%s
                    """,
                    (summary, tags, datetime.now(timezone.utc), event_id),
                )
        return summary
    except Exception as e:
        try:
            if rsent:
                rsent.capture_exception(e, task="summarize_event", event_id=event_id)
        except Exception:
            pass
        raise
    finally:
        conn.close()


@app.task(name="ravi.worker.summarize_chat")
def summarize_chat(turn_id: int) -> str:
    if (os.environ.get("RAVI_SMART_LOG") or "off").lower() not in (
        "on",
        "1",
        "true",
        "yes",
    ):
        return "smart log disabled"
    conn = _db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT role, content, model FROM ravi_chat_turns WHERE id=%s",
                    (turn_id,),
                )
                row = cur.fetchone()
                if not row:
                    return "missing"
                role, content, model = row
                summary, _tags = _llm_summarize(
                    f"Chat {role} via {model}: {content}", "chat"
                )
                cur.execute(
                    """
                    UPDATE ravi_chat_turns
                    SET llm_summary=%s, llm_processed_at=%s
                    WHERE id=%s
                    """,
                    (summary, datetime.now(timezone.utc), turn_id),
                )
        return summary
    except Exception as e:
        try:
            if rsent:
                rsent.capture_exception(e, task="summarize_chat", turn_id=turn_id)
        except Exception:
            pass
        raise
    finally:
        conn.close()


@app.task(name="ravi.worker.drain_queues")
def drain_queues() -> int:
    """Pull ids from Redis lists and summarize."""
    if (os.environ.get("RAVI_SMART_LOG") or "off").lower() not in (
        "on",
        "1",
        "true",
        "yes",
    ):
        return 0
    try:
        import redis

        r = redis.from_url(REDIS_URL)
    except Exception:
        return 0
    n = 0
    for _ in range(20):
        eid = r.rpop("ravi:smartlog:events")
        if not eid:
            break
        summarize_event.delay(int(eid))
        n += 1
    for _ in range(20):
        tid = r.rpop("ravi:smartlog:chats")
        if not tid:
            break
        summarize_chat.delay(int(tid))
        n += 1
    return n
