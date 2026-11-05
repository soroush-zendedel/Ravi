# Changelog

All notable changes to Ravi will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-11-04

### Added

- Initial standalone release of Ravi as an independent MIT-licensed project.
- Docker Compose stack: `ravi-redis`, `ravi-postgres`, `ravi-proxy` (LiteLLM v1.106.6).
- Cloudflare Workers AI transformation patch for array-style message content.
- Multi-key Google Gemini model pool in `config.yaml`.
- Python CLI (`ravi`) with commands: `init`, `start`, `stop`, `restart`, `status`, `logs`, `health`, `models`, `config`, `chat`, `ui`, `show-key`, `version`.
- First-run auto-generation of `LITELLM_MASTER_KEY` and `POSTGRES_PASSWORD` into `.env`.
- `ravi ui` opens the LiteLLM Admin UI and shows login credentials (username `admin`, password = master key).
- Project documentation and architecture design document.

### Notes

- Extracted and cleaned from the previous monorepo; all personal-site / DevOS website assets removed.
