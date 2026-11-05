# API

Ravi exposes an **OpenAI-compatible** HTTP API via LiteLLM.

## Base URL

```
http://127.0.0.1:4000
```

## Authentication

```
Authorization: Bearer <LITELLM_MASTER_KEY>
```

## Main endpoints

| Method | Path                 | Description                |
|--------|----------------------|----------------------------|
| GET    | `/health`            | Health check               |
| GET    | `/models`            | List available models      |
| POST   | `/chat/completions`  | Chat completion            |
| POST   | `/completions`       | Text completion (legacy)   |
| POST   | `/embeddings`        | Embeddings (if configured) |

## Example

```bash
curl http://127.0.0.1:4000/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "cf-gpt-oss-20b",
    "messages": [
      {"role": "user", "content": "Hello"}
    ]
  }'
```

Model names are defined in `config.yaml` under `model_list[].model_name`.

For full LiteLLM API details see the upstream documentation.
