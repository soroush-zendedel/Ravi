# Security Policy

## Supported versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |

## Reporting a vulnerability

Please **do not** open public GitHub issues for security vulnerabilities.

Report privately to the maintainers (repository owner). Include:

- Description of the issue
- Steps to reproduce
- Potential impact
- Any suggested fix (optional)

We will acknowledge receipt and work on a fix as quickly as possible.

## Best practices for operators

- Never commit `.env` or real API keys.
- Use a strong, unique `LITELLM_MASTER_KEY` and `POSTGRES_PASSWORD`.
- Restrict network access to port 4000 (and 5432/6379) in production.
- Keep Docker images and the host system updated.
- Rotate provider API keys periodically.
