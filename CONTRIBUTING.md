# Contributing to Ravi

Thank you for your interest in contributing!

## Development setup

1. Fork and clone the repository.
2. Create a virtual environment and install in editable mode:

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```

3. Copy `.env.example` → `.env` and configure keys for local testing.
4. Start the stack with `ravi start`.

## Guidelines

- Keep the core focused on **integration and orchestration**. Prefer reusing mature tools (LiteLLM, Ollama, etc.) over re-implementing them.
- Do not commit secrets, real API keys, or `.env` files.
- Follow existing code style (Ruff is available under the `dev` extra).
- For architecture changes, discuss them against `docs/architecture/ravi.main.md`.

## Pull requests

- Describe the problem and the solution clearly.
- Include tests when practical.
- Update the changelog for user-visible changes.

## License

By contributing you agree that your contributions are licensed under the MIT License.
