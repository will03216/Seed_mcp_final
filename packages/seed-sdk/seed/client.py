"""SeedClient — high-level entry point for Seed Audio generation.

Thin orchestration over a pluggable AudioProvider (fal today, BytePlus later).
All transport/auth/response-shape specifics live in seed/providers/*.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .config import (
    DEFAULT_LLM_MODEL,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_PROVIDER,
    DEFAULT_SAMPLE_RATE,
    LLM_MODELS,
    MODELS,
    VOICES,
    __version__,
)
from .credentials import credentials_configured
from .exceptions import ValidationError
from .llm import LLMParams, LLMResult, SeedLLM
from .providers import AudioProvider, get_provider
from .types import AudioParams, TaskResult


class SeedClient:
    """Generate audio with BytePlus Seed models.

    Args:
        fal_key: Explicit fal.ai API key (otherwise resolved from the env/file chain).
        byteplus_key: Explicit BytePlus X-Api-Key (new console). Resolved from
            BYTEPLUS_SEED_API_KEY otherwise.
        byteplus_app_id: Explicit BytePlus App ID (legacy console auth).
        byteplus_access_key: Explicit BytePlus Access Key (legacy console auth).
        provider: "fal" (default) or "byteplus". Falls back to SEED_PROVIDER.
        profile: Credentials profile in ~/.seed/credentials.
    """

    def __init__(
        self,
        *,
        fal_key: str | None = None,
        byteplus_key: str | None = None,
        byteplus_app_id: str | None = None,
        byteplus_access_key: str | None = None,
        ark_key: str | None = None,
        provider: str | None = None,
        profile: str = "default",
    ) -> None:
        self._fal_key = fal_key
        self._byteplus_key = byteplus_key
        self._byteplus_app_id = byteplus_app_id
        self._byteplus_access_key = byteplus_access_key
        self._ark_key = ark_key
        self._provider_name = (provider or DEFAULT_PROVIDER).strip().lower()
        self._profile = profile
        self._provider: AudioProvider | None = None
        self._llm: SeedLLM | None = None

    def provider(self) -> AudioProvider:
        if self._provider is None:
            self._provider = get_provider(
                self._provider_name,
                fal_key=self._fal_key,
                byteplus_key=self._byteplus_key,
                byteplus_app_id=self._byteplus_app_id,
                byteplus_access_key=self._byteplus_access_key,
                profile=self._profile,
            )
        return self._provider

    # -- generation -------------------------------------------------------
    def submit_audio(
        self,
        prompt: str,
        *,
        voice: str | None = None,
        audio_urls: list[str] | None = None,
        image_url: str | None = None,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        speed: float = 1.0,
        volume: float = 1.0,
        pitch: int | None = None,
    ) -> TaskResult:
        """Submit a Seed Audio generation job. Returns immediately with a request_id."""
        params = AudioParams(
            prompt=prompt,
            voice=voice,
            audio_urls=audio_urls,
            image_url=image_url,
            output_format=output_format,
            sample_rate=sample_rate,
            speed=speed,
            volume=volume,
            pitch=pitch,
        )
        params.validate()
        return self.provider().submit(params)

    def check_task(self, request_id: str) -> TaskResult:
        """Poll a submitted job. Returns audio_url once status == 'completed'."""
        if not request_id or not request_id.strip():
            raise ValidationError("request_id is required.")
        return self.provider().status(request_id)

    # -- LLM (Ark Responses) ---------------------------------------------
    def llm(self) -> SeedLLM:
        if self._llm is None:
            self._llm = SeedLLM(api_key=self._ark_key, profile=self._profile)
        return self._llm

    def generate_text(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        stream: bool = False,
    ) -> LLMResult:
        """Generate text with a Seed LLM (e.g. seed-2-0-pro-260328).

        Pass `mcp_servers` (a list of {server_label, server_url, ...}) to let the
        model call remote MCP servers, or `tools` for raw Ark tool specs.
        """
        params = LLMParams(
            prompt=prompt,
            model=model,
            system=system,
            tools=tools,
            mcp_servers=mcp_servers,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            stream=stream,
        )
        return self.llm().generate(params)

    def stream_text(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Iterator[str]:
        """Yield assistant text deltas as they arrive from a Seed LLM."""
        params = LLMParams(
            prompt=prompt,
            model=model,
            system=system,
            tools=tools,
            mcp_servers=mcp_servers,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            stream=True,
        )
        return self.llm().stream_generate(params)

    # -- metadata ---------------------------------------------------------
    def list_voices(self) -> dict[str, Any]:
        return {"voices": list(VOICES), "count": len(VOICES)}

    def list_models(self) -> dict[str, Any]:
        return {
            "default_model": DEFAULT_MODEL,
            "provider": self._provider_name,
            "models": [{"model_id": mid, **caps} for mid, caps in MODELS.items()],
        }

    def list_llm_models(self) -> dict[str, Any]:
        return {
            "default_model": DEFAULT_LLM_MODEL,
            "provider": "byteplus-ark",
            "models": [{"model_id": mid, **caps} for mid, caps in LLM_MODELS.items()],
        }

    def ping(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "provider": self._provider_name,
            "credentials": credentials_configured(profile=self._profile),
        }
