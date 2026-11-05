# Ravi — Open Source AI Infrastructure

> *Powered by Openness. Built for Everyone.*

**Ravi** is an independent, modular, extensible, and open-source infrastructure for connecting, managing, routing, and utilizing various AI technologies — cloud models and local execution engines — through a single OpenAI-compatible API.

It is built on top of [LiteLLM](https://github.com/BerriAI/litellm) and ships with a critical patch for Cloudflare Workers AI message formatting, multi-key Gemini load balancing, Redis-backed routing, and a first-class CLI.

---

## Features

- **Unified AI Gateway** — OpenAI-compatible `/chat/completions`, `/models`, `/health`
- **Provider agnostic** — Cloudflare Workers AI, Google Gemini (multi-key pool), and ready for OpenAI / Anthropic / Ollama / vLLM
- **Cloudflare patch** — Fixes array-style content messages that break stock LiteLLM v1.106.6
- **CLI first** — `ravi start`, `ravi stop`, `ravi health`, `ravi models`, `ravi chat`, …
- **Independent deployment** — Docker Compose with dedicated volumes and network
- **MIT licensed**

---

## Requirements

- Docker Engine / Docker Desktop (with Compose v2)
- Python 3.10+ (only needed if you install the CLI via pip)
- API keys for the providers you want to use

---

## Quick Start

### 1. Clone / extract the project

```bash
cd ravi
```

### 2. Initialize (auto-generates secure master key & DB password)

```bash
ravi init
# Creates .env, generates LITELLM_MASTER_KEY + POSTGRES_PASSWORD
# Still edit .env to add CLOUDFLARE_* and GEMINI_API_KEY_n
```

### 3. Install the CLI (recommended)

```bash
pip install -e .
# or: pip install .
```

After installation the `ravi` command is available globally:

```bash
ravi --help
```

### 4. Start the stack

```bash
ravi start
# equivalent: docker compose up -d --build
```

Ravi listens on **http://127.0.0.1:4000**.

### 5. Verify

```bash
ravi health
ravi models
ravi chat "Hello Ravi!" --model cf-gpt-oss-20b
```

### 6. Use from any client

```bash
curl http://127.0.0.1:4000/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "cf-gpt-oss-20b",
    "messages": [{"role": "user", "content": "Hi"}]
  }'
```

Any OpenAI-compatible SDK works — just point `base_url` to `http://127.0.0.1:4000/v1` (or without `/v1` depending on the client) and use the master key.

---



## Provider keys (free tiers)

```bash
ravi providers                 # see free vs paid
ravi keys add gemini           # interactive, or: --key AIza...
ravi keys add groq --key gsk_...
ravi keys add cloudflare --token ... --account ACCOUNT_ID
ravi keys list
ravi use gemini-2.0-flash      # set default model
ravi chat "hello"              # uses default — no --model needed
ravi chat "hi" -m groq-llama-3.1-8b
```



## Local models (Ollama)

```bash
ravi local list                 # catalog of free local models
ravi local pull llama3.2:3b     # download once — kept forever
ravi local status               # what is installed + models dir
ravi init --local               # first-time setup with local model picker
ravi start                      # auto-init if needed → stack up → interactive chat
```

- Models live in Ollama's data volume (`ravi_ollama_data`) and optionally `./models`.
- If a local model is already installed, `ravi init` / `ravi start` picks it automatically (no prompt).
- Welcome line on chat is `RAVI_WELCOME_MESSAGE` in `.env` (editable).

## CLI Reference

| Command            | Description                                      |
|--------------------|--------------------------------------------------|
| `ravi --help`      | Show help                                        |
| `ravi version`     | Print version                                    |
| `ravi init`        | Create `.env` and **auto-generate** secure keys  |
| `ravi start`       | Start stack (also generates keys if missing)     |
| `ravi stop`        | Stop containers (`--volumes` to wipe data)       |
| `ravi restart`     | Restart the stack                                |
| `ravi status`      | `docker compose ps`                              |
| `ravi logs`        | Follow logs (`ravi logs litellm`)                |
| `ravi health`      | HTTP health check                                |
| `ravi models`      | List models from the running proxy               |
| `ravi config`      | Summarize models defined in `config.yaml`        |
| `ravi chat "…"`    | Quick test completion                            |
| `ravi ui`          | Open Admin UI in browser + show login credentials|
| `ravi show-key`    | Print master key / UI username & password        |

You can also set `RAVI_HOME` to the project root if you run the CLI from another directory.

---

## Project layout

```text
ravi/
├── README.md
├── LICENSE                 # MIT
├── pyproject.toml          # CLI package
├── .env.example
├── config.yaml             # LiteLLM model list + router settings
├── docker-compose.yml      # redis, postgres, litellm (ravi-*)
├── docker/
│   └── litellm/
│       └── transformation.py   # Cloudflare content-array patch
├── src/
│   └── ravi/
│       ├── __init__.py
│       └── cli.py          # Typer-based CLI
├── docs/
│   ├── architecture/
│   │   └── ravi.main.md    # Full design document
│   ├── api/
│   └── deployment/
├── scripts/                # Optional PowerShell helpers
└── tests/
```

---

## Architecture (short)

```text
Applications (DevOS, web apps, scripts, …)
                │
                ▼
        ┌───────────────┐
        │     RAVI      │  ← OpenAI-compatible API :4000
        │  (LiteLLM)    │
        └───────┬───────┘
                │
     ┌──────────┼──────────┐
     ▼          ▼          ▼
 Cloudflare   Gemini    (future:
 Workers AI   (pool)     Ollama, …)
```

See [docs/architecture/ravi.main.md](docs/architecture/ravi.main.md) for the complete design.

---

## Important notes

- **Volumes** are named `ravi_redis_data` and `ravi_postgres_data`. Never run `docker compose down -v` unless you intentionally want to wipe data (and you have a `pg_dump` backup).
- **Secrets** stay in `.env` only. They are never committed.
- After changing `config.yaml`, run `ravi restart`.
- The Cloudflare transformation patch is mounted over the LiteLLM image path so array-style `content: [{type: "text", text: "…"}]` messages work correctly.

---

## License

MIT License — see [LICENSE](LICENSE).

Copyright (c) 2026 Soroush Zendedel & Ravi Contributors
