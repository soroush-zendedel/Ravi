"""Curated AI providers — especially those with free tiers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Provider:
    id: str
    name: str
    free_tier: bool
    description: str
    signup_url: str
    # env keys this provider needs
    env_keys: list[str]
    # model_name values in config.yaml that become usable once keys are set
    models: list[str]
    # optional: how to build derived env values
    notes: str = ""


# Models that ship in config.yaml and light up when the matching key is present.
PROVIDERS: dict[str, Provider] = {
    "gemini": Provider(
        id="gemini",
        name="Google Gemini",
        free_tier=True,
        description="Google AI Studio — generous free tier, great for everyday chat.",
        signup_url="https://aistudio.google.com/apikey",
        env_keys=["GEMINI_API_KEY_1"],
        models=[
            "gemini-3.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-3.5-flash-lite",
        ],
        notes="You can add more keys as GEMINI_API_KEY_2 … _18 for higher rate limits.",
    ),
    "cloudflare": Provider(
        id="cloudflare",
        name="Cloudflare Workers AI",
        free_tier=True,
        description="Workers AI — free daily neurons, many open models.",
        signup_url="https://dash.cloudflare.com/?to=/:account/ai/workers-ai",
        env_keys=["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_AI_BASE_URL"],
        models=[
            "cf-gpt-oss-20b",
            "cf-gpt-oss-120b",
            "cf-gemma-4-26b",
            "cf-qwq-32b",
            "cf-deepseek-r1-32b",
            "cf-qwen3-30b",
            "cf-glm-4.7-flash",
            "cf-nemotron-120b",
        ],
        notes=(
            "Token needs Workers AI permission. "
            "Base URL: https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1"
        ),
    ),
    "groq": Provider(
        id="groq",
        name="Groq",
        free_tier=True,
        description="Ultra-fast inference — free tier with Llama, Mixtral, Gemma.",
        signup_url="https://console.groq.com/keys",
        env_keys=["GROQ_API_KEY"],
        models=[
            "groq-llama-3.3-70b",
            "groq-llama-3.1-8b",
            "groq-gemma2-9b",
            "groq-mixtral-8x7b",
        ],
        notes="Very fast. Rate-limited on free tier.",
    ),
    "openrouter": Provider(
        id="openrouter",
        name="OpenRouter",
        free_tier=True,
        description="One key, many models — includes free :free endpoints.",
        signup_url="https://openrouter.ai/keys",
        env_keys=["OPENROUTER_API_KEY"],
        models=[
            "openrouter-auto",
            "openrouter-llama-3.3-70b-free",
            "openrouter-gemma-2-9b-free",
        ],
        notes="Prefer models ending with :free for the free tier.",
    ),

    "ollama": Provider(
        id="ollama",
        name="Ollama (local)",
        free_tier=True,
        description="Run models fully offline on your machine — no API key.",
        signup_url="https://ollama.com",
        env_keys=[],  # no cloud key
        models=[],  # filled dynamically
        notes="Use `ravi local` to pull and select models. Weights stay on disk.",
    ),
    "openai": Provider(
        id="openai",
        name="OpenAI",
        free_tier=False,
        description="Official OpenAI API (paid).",
        signup_url="https://platform.openai.com/api-keys",
        env_keys=["OPENAI_API_KEY"],
        models=["gpt-4o-mini", "gpt-4o"],
        notes="Paid. Uncomment models in config.yaml if needed.",
    ),
    "anthropic": Provider(
        id="anthropic",
        name="Anthropic Claude",
        free_tier=False,
        description="Claude models (paid).",
        signup_url="https://console.anthropic.com/settings/keys",
        env_keys=["ANTHROPIC_API_KEY"],
        models=["claude-haiku-4.5"],
        notes="Paid. Uncomment models in config.yaml if needed.",
    ),
}


# Extra config.yaml snippets to inject when a free provider is activated
# and the model is not already present.
MODEL_SNIPPETS: dict[str, list[dict]] = {
    "gemini": [
        {
            "model_name": "gemini-3.5-flash",
            "litellm_params": {
                "model": "gemini/gemini-3.5-flash",
                "api_key": "os.environ/GEMINI_API_KEY_1",
            },
        },
        {
            "model_name": "gemini-2.5-flash-lite",
            "litellm_params": {
                "model": "gemini/gemini-2.5-flash-lite",
                "api_key": "os.environ/GEMINI_API_KEY_1",
            },
        },
        {
            "model_name": "gemini-2.0-flash",
            "litellm_params": {
                "model": "gemini/gemini-3.5-flash",
                "api_key": "os.environ/GEMINI_API_KEY_1",
            },
        },
        {
            "model_name": "gemini-2.0-flash-lite",
            "litellm_params": {
                "model": "gemini/gemini-3.5-flash-lite",
                "api_key": "os.environ/GEMINI_API_KEY_1",
            },
        },
        {
            "model_name": "gemini-2.5-flash",
            "litellm_params": {
                "model": "gemini/gemini-2.5-flash",
                "api_key": "os.environ/GEMINI_API_KEY_1",
            },
        },
    ],
    "groq": [
        {
            "model_name": "groq-llama-3.3-70b",
            "litellm_params": {
                "model": "groq/llama-3.3-70b-versatile",
                "api_key": "os.environ/GROQ_API_KEY",
            },
        },
        {
            "model_name": "groq-llama-3.1-8b",
            "litellm_params": {
                "model": "groq/llama-3.1-8b-instant",
                "api_key": "os.environ/GROQ_API_KEY",
            },
        },
        {
            "model_name": "groq-gemma2-9b",
            "litellm_params": {
                "model": "groq/gemma2-9b-it",
                "api_key": "os.environ/GROQ_API_KEY",
            },
        },
        {
            "model_name": "groq-mixtral-8x7b",
            "litellm_params": {
                "model": "groq/mixtral-8x7b-32768",
                "api_key": "os.environ/GROQ_API_KEY",
            },
        },
    ],
    "openrouter": [
        {
            "model_name": "openrouter-auto",
            "litellm_params": {
                "model": "openrouter/openrouter/auto",
                "api_key": "os.environ/OPENROUTER_API_KEY",
            },
        },
        {
            "model_name": "openrouter-llama-3.3-70b-free",
            "litellm_params": {
                "model": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
                "api_key": "os.environ/OPENROUTER_API_KEY",
            },
        },
        {
            "model_name": "openrouter-gemma-2-9b-free",
            "litellm_params": {
                "model": "openrouter/google/gemma-2-9b-it:free",
                "api_key": "os.environ/OPENROUTER_API_KEY",
            },
        },
    ],
}


def provider_ids() -> list[str]:
    return list(PROVIDERS.keys())


def free_providers() -> list[Provider]:
    return [p for p in PROVIDERS.values() if p.free_tier]


def get_provider(provider_id: str) -> Provider | None:
    return PROVIDERS.get(provider_id.lower().strip())
