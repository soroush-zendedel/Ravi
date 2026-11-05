# Ravi Code Audit and Remediation Status

This English edition replaces the original Persian audit. Findings have been checked against the current source tree and updated to reflect the changes made in this remediation pass.

## Project overview

Ravi is an open-source AI infrastructure project based on LiteLLM. It includes a Python CLI, Docker Compose services, Cloudflare and Gemini providers, local inference through llama.cpp or Ollama, and optional Laya, smart-log, and Sentry integrations.

The codebase has a modular `src/ravi` package, configuration catalogs, deployment documentation, and tests. The audit identified configuration and lifecycle defects that could prevent optional services from starting or cause false success responses.

## Critical and high-priority findings

### 1. Laya command broke Compose parsing

The Laya service embedded a multi-line Python stub inside a folded YAML command. Its indentation and escaping made the Compose file fragile. The stub returned `stub: True` instead of performing inference.

**Resolution:** The embedded Python was removed. Laya now uses a dedicated image that installs the official `laya[serve]` package and starts `laya-serve`. Its registered checkpoint paths point to the locally downloaded Ravi model directories.

### 2. PostgreSQL service references disagreed

The database service is named `db`, while the worker and GlitchTip referred to a nonexistent `postgres` service in both `depends_on` and their connection strings. LiteLLM already used `db`.

**Resolution:** `db` remains the canonical Compose service name. Worker and GlitchTip now use `db` and wait for its health check. The Celery worker's fallback hostname also uses `db`.

### 3. Ollama's named volume was undeclared

The Ollama service referenced `ravi_ollama_data`, but the Compose-level volume list did not declare it.

**Resolution:** `ravi_ollama_data` is declared alongside the Redis and PostgreSQL volumes.

### 4. `ravi restart` was missing from the CLI

The `restart` function existed without the Typer command decorator, even though the README and CLI messages advertised it.

**Resolution:** `restart` is registered as a top-level Typer command.

### 5. llama.cpp had no model argument

The server command did not pass a GGUF file and could exit immediately when started without a model.

**Resolution:** llama.cpp is now an optional Compose profile. The CLI enables it only when an available GGUF file is inside the mounted model directory. The container entrypoint resolves the configured filename or selects a local GGUF, then starts `llama-server` with the model path. Missing files return a clear error without an automatic restart loop. The model-directory resolver also reads `.env` and anchors relative paths to the project root.

## Medium-priority findings

### Worker installed dependencies at container startup

The old worker used a generic Python image, mounted the entire source tree, and ran `pip install` on each start.

**Resolution:** A dedicated worker image installs the existing Ravi package and worker dependencies during image build. The source tree is no longer mounted into the running worker. Worker and scheduler services are optional under the `smartlog` profile; the scheduler is separate so its periodic queue-draining task can run.

### Laya was only a placeholder

The old service exposed a health route and a fake system-one response but never loaded a decision model.

**Resolution:** Laya now uses the official HTTP server with the local checkpoints managed by `ravi local laya pull`. The service preloads the selected checkpoint, exposes a health check, and returns actual model output. The existing Ravi client and offline heuristic fallback remain available when the service cannot be reached.

### Gemini model identifiers needed validation

The configuration included Gemini 2.0 endpoints that are no longer available. Gemini 3.5 Flash-Lite and Gemini 2.5 Flash remain active in the current configuration.

**Resolution:** Current Gemini 3.5 Flash and Gemini 2.5 Flash-Lite entries were added. Existing Ravi aliases named `gemini-2.0-flash` and `gemini-2.0-flash-lite` are retained for client compatibility and now route to supported upstream model IDs. Provider catalogs and defaults were updated. `ravi config validate` and startup checks report retired or unverified upstream identifiers.

### LiteLLM patch path depended on Python 3.13

The Compose file mounted the patch directly into a version-specific `.venv/lib/python3.13` path.

**Resolution:** The pinned LiteLLM base image is preserved, and a small derived image now copies the patch into the image. Its entrypoint discovers the installed LiteLLM package location at container startup, checks that the target module exists, and applies the patch before launching the proxy.

### `.env` was required without clear deployment guidance

Several services require generated secrets or read optional settings from `.env`.

**Resolution:** Deployment documentation now states that `ravi init` must run before Compose and explains the required PostgreSQL password for direct Compose usage. Secrets remain outside the repository.

## Static review status

The source, Compose configuration, and documentation were reviewed statically for the reported service names, volumes, commands, model paths, CLI registration, and provider identifiers. No test files were added or run, and no application code was executed, in accordance with the project owner's instruction.

Compose parsing, image builds, CLI invocation, model loading, provider requests, and the existing test suite remain unverified because they require executing project or service code.

## Operational constraints

- LiteLLM remains pinned to `v1.106.6`; no existing provider or supported package was removed.
- Ollama remains optional and its persistent volume is preserved.
- Compose profiles keep llama.cpp, Ollama, Laya, smart-log, Flower, and GlitchTip independently selectable.
- No Python code, tests, Docker builds, or containers were executed during this change.
- The edited configuration and code still need a later user-authorized validation run before deployment.
