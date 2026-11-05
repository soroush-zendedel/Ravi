# Deployment

## Local (Docker Compose)

See the main [README](../../README.md) for the recommended flow using the `ravi` CLI.
Run `ravi init` before starting Compose. It creates `.env` and generates the required LiteLLM key and PostgreSQL password. Direct Compose use also requires a non-empty `POSTGRES_PASSWORD` in `.env`; Compose reports a clear configuration error if it is missing.

```bash
cp .env.example .env
# edit .env
ravi start
```

## Production notes

- Bind the proxy only to a private network or put it behind a reverse proxy with TLS.
- Do not expose Postgres (5432) or Redis (6379) publicly.
- Use strong passwords and rotate the master key.
- Prefer named volumes or external managed databases for persistence.
- Monitor container health and LiteLLM logs.

More detailed guides will be added in future releases.


## Windows (Docker Desktop)

1. Install Docker Desktop and enable file sharing for the drive that holds models.
2. Set a host path in `.env`:

```env
RAVI_MODELS_DIR=D:/ravi-models
```

3. Ensure the folder exists and is shared in Docker Desktop → Settings → Resources → File sharing.
4. Containers mount that folder read-only at `/models`. The `ravi` CLI on the host still works when containers are stopped (`ravi stop` / `ravi llm off`).

The llama.cpp profile is enabled only when the selected GGUF file exists inside the mounted models directory. Ollama models persist in the declared `ravi_ollama_data` volume. The Laya server needs its selected checkpoint downloaded before it starts.

