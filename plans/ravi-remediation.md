# Ravi Remediation Record

## Scope and implementation approach

This pass follows the existing Ravi architecture: LiteLLM remains the cloud gateway, local inference stays on llama.cpp or Ollama, and optional services remain separately selectable through Compose profiles. Existing model aliases, local model download flows, provider integrations, and the LiteLLM version were preserved where they remain useful. The changes add configuration validation and dedicated images rather than replacing the project's current stack.

## Changes by finding

| Finding | Implementation | Reasoning |
|---|---|---|
| Invalid Laya Compose command and fake responses | Replaced the inline Python stub with an image for official `laya-serve`; registered both local checkpoint paths and added readiness checks. | Keeps inference in a maintained model server and prevents an empty placeholder response from looking successful. |
| Database host mismatch | Standardized LiteLLM, worker, and GlitchTip on the existing `db` service; added health-based database dependencies and aligned the worker fallback. | Preserves the service name already used by LiteLLM and Ravi status reporting while correcting dependent services. |
| Missing Ollama volume | Declared `ravi_ollama_data` at the Compose root. | Maintains downloaded Ollama models across container recreation. |
| Missing `restart` CLI entry | Registered the existing restart function with Typer. | Makes the advertised command discoverable without changing its current start/stop behavior. |
| llama.cpp starts without weights | Added a model-resolving entrypoint, made llama an optional profile, and enabled that profile from CLI startup only when a GGUF is available. | The server receives a concrete model path and does not restart indefinitely when no weights are installed. |
| Runtime dependency installation in Celery | Added a worker extra in `pyproject.toml` and a dedicated worker image. Added a separate Celery Beat service and an optional `smartlog` profile. | Installs packages once at image build time and gives the configured periodic drain task a scheduler process. |
| Nonfunctional Laya endpoint | Added the official `laya[serve]` image and mapped Ravi's existing local download directories through `LAYA_EXTRA_MODELS`. | Uses the existing weight downloads and request contract instead of inventing a separate inference API. |
| Retired and unchecked Gemini endpoints | Added current Gemini aliases, kept old Ravi aliases mapped to active upstream IDs, updated provider defaults, and added `ravi config validate` plus bootstrap checks. | Existing client-facing model names remain available while requests use active endpoints; unverified IDs receive a warning. |
| LiteLLM patch bound to Python 3.13 | Derived an image from the existing pinned LiteLLM image and added a package-location discovery step before startup. | Avoids coupling the mount target to one Python minor-version path without changing LiteLLM itself. |
| Implicit `.env` prerequisite | Clarified `ravi init` and direct Compose requirements in deployment documentation. | Keeps fail-fast secret handling and makes the setup prerequisite explicit. |

## Additional consistency work

- Made worker, worker scheduler, and Ollama volumes/profiles agree with their CLI lifecycle.
- Updated named runtime profiles so model-dependent services are skipped when their selected weights are absent.
- Anchored relative `RAVI_MODELS_DIR` values to the project root and read them from `.env`, matching Compose's mount resolution.
- Updated the README and deployment guide to describe the new service lifecycle.

## Static review and execution limits

Source and configuration were reviewed for the Compose dependencies, named volumes, canonical database hostname, image build configuration, model selection, Gemini identifier handling, CLI registration, and relative model-directory resolution.

No test files were added or run. No application, Docker, or Compose command was run.

## Gemini source reference

The active and retired model identifiers were checked against Google's current Gemini API catalog and model deprecation documentation while preparing the configuration update:

- [Gemini API models](https://ai.google.dev/gemini-api/docs/models)
- [Gemini 2.0 Flash model page and shutdown notice](https://ai.google.dev/gemini-api/docs/models/gemini-2.0-flash)

## Remaining verification

This work is a static source edit. Compose parsing, image builds, CLI invocation, model loading, provider requests, and the existing test suite still require a future execution pass. They were not run because the project owner explicitly requested that no code be executed in this turn.
