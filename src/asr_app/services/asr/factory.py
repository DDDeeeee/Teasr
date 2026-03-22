from __future__ import annotations

from .base import AsrCredentials, AsrProvider


def create_provider(provider_name: str, credentials: AsrCredentials) -> AsrProvider:
    """Create an ASR provider by name. Imports are lazy to avoid loading unused SDKs."""

    if provider_name == "aliyun":
        from .providers.aliyun import AliyunProvider

        return AliyunProvider(credentials)

    if provider_name == "openai":
        from .providers.openai_asr import OpenAIProvider

        return OpenAIProvider(credentials)

    if provider_name == "doubao":
        from .providers.doubao import DoubaoProvider

        return DoubaoProvider(credentials)

    raise ValueError(f"Unknown ASR provider: {provider_name}")
