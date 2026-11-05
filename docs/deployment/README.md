# Deployment

## Local (Docker Compose)

See the main [README](../../README.md) for the recommended flow using the `ravi` CLI.

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

