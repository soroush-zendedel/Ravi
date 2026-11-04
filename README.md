# Ravi — Open Source AI Infrastructure

> *Powered by Openness. Built for Everyone.*

Ravi is an independent, modular, extensible, and open-source infrastructure for connecting, managing, routing, and utilizing various AI technologies, cloud models, and local execution engines.

---

## Features

- **Unified AI Gateway**: Powered by LiteLLM for robust OpenAI-compatible API endpoints.
- **Provider Agnostic**: Seamlessly connect to Cloudflare Workers AI, Google Gemini, OpenAI, Anthropic, and more.
- **Local AI Support**: Ready for Ollama, vLLM, and llama.cpp integration.
- **Independent Deployment**: Easily run standalone via Docker Compose.
- **MIT Licensed**: Completely open source and free for everyone.

---

## Quick Start

1. Copy the example environment configuration:
   ```powershell
   copy .env.example .env
   ```
2. Fill in your API keys and configuration in `.env`.
3. Start Ravi using the provided helper script:
   ```powershell
   ./scripts/Start-Ravi.ps1
   ```
4. Access the API at `http://127.0.0.1:4000`.

---

## Documentation

For full architecture details, refer to [`docs/architecture/ravi.main.md`](docs/architecture/ravi.main.md).

---

## License

MIT License. See [`LICENSE`](LICENSE) for details.
