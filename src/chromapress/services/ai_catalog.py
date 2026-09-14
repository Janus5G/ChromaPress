from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AiModelOption:
    id: str
    label: str
    description: str


@dataclass(frozen=True)
class AiProviderOption:
    id: str
    label: str
    description: str
    protocol: str
    requires_endpoint: bool
    requires_api_key: bool
    editable_model: bool
    models: tuple[AiModelOption, ...]


AI_PROVIDERS: tuple[AiProviderOption, ...] = (
    AiProviderOption(
        id="openai",
        label="OpenAI",
        description="Default ChromaPress coding provider.",
        protocol="openai_chat",
        requires_endpoint=False,
        requires_api_key=True,
        editable_model=False,
        models=(
            AiModelOption("gpt-5.6-sol", "GPT-5.6 Sol — Recommended", "Best default for complex professional coding, debugging and larger application changes."),
            AiModelOption("gpt-5.6-terra", "GPT-5.6 Terra — Balanced", "Balances coding capability and API cost for everyday application work."),
            AiModelOption("gpt-5.6-luna", "GPT-5.6 Luna — Fast / economical", "Best for quick iterations, smaller coding tasks and cost-sensitive high-volume use."),
        ),
    ),
    AiProviderOption(
        id="caffeine",
        label="Caffeine Inference (Early Access)",
        description="Optional configured endpoint using the ChromaPress compatible generation contract.",
        protocol="openai_chat_compatible",
        requires_endpoint=True,
        requires_api_key=True,
        editable_model=True,
        models=(AiModelOption("auto", "Automatic routing (preview)", "Lets the configured Caffeine endpoint choose routing when it supports automatic selection."),),
    ),
    AiProviderOption(
        id="openai-compatible",
        label="OpenAI-compatible endpoint",
        description="User-configured compatible endpoint. ChromaPress does not claim a vendor/model until the user configures one.",
        protocol="openai_chat_compatible",
        requires_endpoint=True,
        requires_api_key=True,
        editable_model=True,
        models=(AiModelOption("custom-model", "Custom model ID", "Enter the exact model ID exposed by your compatible endpoint."),),
    ),
    AiProviderOption(
        id="local",
        label="Local model endpoint",
        description="User-configured loopback OpenAI-compatible endpoint. API key is optional; cleartext HTTP is accepted only on loopback.",
        protocol="openai_chat_compatible",
        requires_endpoint=True,
        requires_api_key=False,
        editable_model=True,
        models=(AiModelOption("local-model", "Local model ID", "Enter the exact model ID exposed by your local endpoint."),),
    ),
)


def provider_by_id(provider_id: str) -> AiProviderOption:
    normalized = normalize_provider_id(provider_id)
    for provider in AI_PROVIDERS:
        if provider.id == normalized:
            return provider
    return AI_PROVIDERS[0]


def normalize_provider_id(value: str) -> str:
    raw = (value or "").strip()
    # Historical alpha stored the display-ish value "OpenAI-compatible" for
    # the OpenAI default. Preserve that one exact migration while the new
    # canonical provider id is lowercase "openai-compatible".
    if raw == "OpenAI-compatible":
        return "openai"
    text = raw.lower()
    aliases = {
        "openai": "openai",
        "caffeine": "caffeine",
        "caffeine inference": "caffeine",
        "openai-compatible": "openai-compatible",
        "openai compatible": "openai-compatible",
        "compatible": "openai-compatible",
        "local": "local",
        "local model": "local",
        "local endpoint": "local",
    }
    return aliases.get(text, "openai")


def normalized_model_id(provider_id: str, model_id: str) -> str:
    provider = provider_by_id(provider_id)
    candidate = (model_id or "").strip()
    if provider.editable_model and candidate:
        return candidate
    if any(model.id == candidate for model in provider.models):
        return candidate
    return provider.models[0].id
