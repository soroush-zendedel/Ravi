-- Ravi structured logs
CREATE TABLE IF NOT EXISTS ravi_events (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source        TEXT NOT NULL DEFAULT 'cli',
    event_type    TEXT NOT NULL,
    tags          TEXT[] DEFAULT '{}',
    category      TEXT DEFAULT 'system',
    level         TEXT DEFAULT 'info',
    message       TEXT NOT NULL,
    payload       JSONB DEFAULT '{}',
    lang          TEXT DEFAULT 'en',
    llm_summary   TEXT,
    llm_tags      TEXT[] DEFAULT '{}',
    llm_processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ravi_events_created ON ravi_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ravi_events_type ON ravi_events (event_type);
CREATE INDEX IF NOT EXISTS idx_ravi_events_category ON ravi_events (category);

CREATE TABLE IF NOT EXISTS ravi_chat_turns (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id    TEXT,
    model         TEXT,
    role          TEXT NOT NULL,
    content       TEXT NOT NULL,
    meta          JSONB DEFAULT '{}',
    llm_summary   TEXT,
    llm_processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ravi_chat_created ON ravi_chat_turns (created_at DESC);

ALTER TABLE ravi_events ADD COLUMN IF NOT EXISTS spoken_at TIMESTAMPTZ;
ALTER TABLE ravi_events ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ;
ALTER TABLE ravi_chat_turns ADD COLUMN IF NOT EXISTS spoken_at TIMESTAMPTZ;
ALTER TABLE ravi_chat_turns ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ;
