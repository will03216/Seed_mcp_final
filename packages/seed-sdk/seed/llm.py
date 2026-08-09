"""Seed LLM — text generation over the BytePlus Ark Responses API.

Separate from the audio providers: the Ark Responses API uses a different host,
bearer-token auth, and the OpenAI-style ``/responses`` request/response shape.
It also supports MCP-tool passthrough (the model calls remote MCP servers on
your behalf), gated behind the ``ark-beta-mcp: true`` header.

Docs: https://console.byteplus.com/ark/  (model detail pages under /model/).

Two call modes, hidden behind ``generate()``:
  - ``stream=False`` (default): one POST returns an aggregated response object;
    ``LLMResult.text`` holds the concatenated assistant output.
  - ``stream=True``: SSE deltas are consumed internally and still returned as a
    single ``LLMResult`` (use ``stream_generate()`` to iterate deltas live).
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .config import (
    ARK_RESPONSES_URL,
    ARK_TIMEOUT,
    resolve_llm_model,
)
from .credentials import load_ark_key
from .exceptions import APIError, ValidationError
from .http import request_with_retry, stream_sse

# Server-side MCP tools must be enabled with this beta header.
_ARK_MCP_HEADER = {"ark-beta-mcp": "true"}


@dataclass
class LLMParams:
    """Validated inputs for a Seed LLM (Ark Responses) request."""

    prompt: str
    model: str | None = None
    system: str | None = None
    tools: list[dict[str, Any]] | None = None
    mcp_servers: list[dict[str, Any]] | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    stream: bool = False

    def validate(self) -> None:
        if not self.prompt or not self.prompt.strip():
            raise ValidationError("prompt is required and cannot be empty.")
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise ValidationError("temperature must be between 0.0 and 2.0.")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise ValidationError("max_output_tokens must be greater than 0.")
        for server in self.mcp_servers or []:
            if not server.get("server_url"):
                raise ValidationError("Each mcp_server requires a 'server_url'.")

    def _resolved_tools(self) -> list[dict[str, Any]]:
        """Merge explicit `tools` with the `mcp_servers` convenience shorthand."""
        tools: list[dict[str, Any]] = list(self.tools or [])
        for server in self.mcp_servers or []:
            tool: dict[str, Any] = {
                "type": "mcp",
                "server_label": server.get("server_label", "mcp"),
                "server_url": server["server_url"],
                "require_approval": server.get("require_approval", "never"),
            }
            if server.get("allowed_tools"):
                tool["allowed_tools"] = server["allowed_tools"]
            if server.get("headers"):
                tool["headers"] = server["headers"]
            tools.append(tool)
        return tools

    def to_payload(self) -> dict[str, Any]:
        input_items: list[dict[str, Any]] = []
        if self.system:
            input_items.append(
                {"role": "system", "content": [{"type": "input_text", "text": self.system}]}
            )
        input_items.append(
            {"role": "user", "content": [{"type": "input_text", "text": self.prompt}]}
        )

        payload: dict[str, Any] = {
            "model": resolve_llm_model(self.model),
            "stream": self.stream,
            "input": input_items,
        }
        tools = self._resolved_tools()
        if tools:
            payload["tools"] = tools
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.max_output_tokens is not None:
            payload["max_output_tokens"] = self.max_output_tokens
        return payload

    @property
    def uses_mcp(self) -> bool:
        return any(t.get("type") == "mcp" for t in self._resolved_tools())


@dataclass
class LLMResult:
    """Normalised result of a Seed LLM generation."""

    model: str
    text: str = ""
    output: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    provider: str = "byteplus-ark"
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "model": self.model,
            "provider": self.provider,
            "text": self.text,
        }
        if self.tool_calls:
            out["tool_calls"] = self.tool_calls
        if self.usage:
            out["usage"] = self.usage
        return out


def _extract_text(response: dict[str, Any]) -> str:
    """Pull assistant text out of a Responses object.

    Prefers the top-level ``output_text`` convenience field; otherwise walks
    ``output[].content[]`` collecting every ``output_text`` chunk.
    """
    convenience = response.get("output_text")
    if isinstance(convenience, str) and convenience:
        return convenience
    if isinstance(convenience, list):
        joined = "".join(t for t in convenience if isinstance(t, str))
        if joined:
            return joined

    parts: list[str] = []
    for item in response.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for chunk in item.get("content", []) or []:
            if isinstance(chunk, dict) and chunk.get("type") == "output_text":
                text = chunk.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "".join(parts)


def _extract_tool_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Summarise MCP / tool-call items in a response for observability."""
    calls: list[dict[str, Any]] = []
    for item in response.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        itype = item.get("type", "")
        if "mcp" in itype or "tool" in itype or itype.endswith("_call"):
            calls.append(
                {
                    "type": itype,
                    "name": item.get("name"),
                    "server_label": item.get("server_label"),
                    "status": item.get("status"),
                }
            )
    return calls


class SeedLLM:
    """Client for Seed LLM text generation via the Ark Responses API."""

    provider = "byteplus-ark"

    def __init__(self, api_key: str | None = None, *, profile: str = "default") -> None:
        self._explicit_key = api_key
        self._profile = profile

    def _headers(self, params: LLMParams) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {load_ark_key(self._explicit_key, profile=self._profile)}",
        }
        if params.uses_mcp:
            headers.update(_ARK_MCP_HEADER)
        return headers

    def generate(self, params: LLMParams) -> LLMResult:
        """Run a generation and return an aggregated LLMResult.

        Works for both streaming and non-streaming requests — streamed deltas
        are consumed internally and collapsed into the final result.
        """
        params.validate()
        if params.stream:
            return self._generate_streamed(params)

        payload = params.to_payload()
        resp = request_with_retry(
            ARK_RESPONSES_URL,
            method="POST",
            headers=self._headers(params),
            payload=payload,
            timeout=ARK_TIMEOUT,
        )
        if resp.get("error"):
            raise APIError(f"Ark error: {resp['error']}")
        return LLMResult(
            model=payload["model"],
            text=_extract_text(resp),
            output=resp.get("output", []) or [],
            tool_calls=_extract_tool_calls(resp),
            usage=resp.get("usage"),
            provider=self.provider,
            raw=resp,
        )

    def stream_generate(self, params: LLMParams) -> Iterator[str]:
        """Yield assistant text deltas as they arrive (forces streaming)."""
        params.validate()
        payload = {**params.to_payload(), "stream": True}
        for event in stream_sse(
            ARK_RESPONSES_URL,
            method="POST",
            headers=self._headers(params),
            payload=payload,
            timeout=ARK_TIMEOUT,
        ):
            delta = _delta_text(event)
            if delta:
                yield delta

    def _generate_streamed(self, params: LLMParams) -> LLMResult:
        payload = {**params.to_payload(), "stream": True}
        text_parts: list[str] = []
        final: dict[str, Any] = {}
        for event in stream_sse(
            ARK_RESPONSES_URL,
            method="POST",
            headers=self._headers(params),
            payload=payload,
            timeout=ARK_TIMEOUT,
        ):
            if event.get("error"):
                raise APIError(f"Ark error: {event['error']}")
            delta = _delta_text(event)
            if delta:
                text_parts.append(delta)
            if isinstance(event.get("response"), dict):
                final = event["response"]

        # Prefer the completed response's own text if it carried one; otherwise
        # fall back to the concatenated deltas.
        text = _extract_text(final) or "".join(text_parts)
        return LLMResult(
            model=payload["model"],
            text=text,
            output=final.get("output", []) or [],
            tool_calls=_extract_tool_calls(final),
            usage=final.get("usage"),
            provider=self.provider,
            raw=final,
        )

    def configured(self) -> bool:
        from .credentials import credentials_configured

        return credentials_configured(profile=self._profile)["ark_api_key"]


def _delta_text(event: dict[str, Any]) -> str:
    """Extract incremental assistant text from an SSE event, if any."""
    etype = event.get("type", "")
    if etype.endswith("output_text.delta"):
        delta = event.get("delta")
        if isinstance(delta, str):
            return delta
    return ""
