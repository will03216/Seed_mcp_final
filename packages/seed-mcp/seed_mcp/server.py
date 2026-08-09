"""Seed MCP Server — thin MCP adapter over seed-sdk.

Each tool is a minimal wrapper: validate inputs, call SeedClient, return dict.
All business logic (provider selection, retry, polling) lives in seed-sdk.

Seed Audio currently runs on fal.ai; set SEED_PROVIDER=byteplus once the native
BytePlus API ships — no tool changes required.

Environment variables (optional if ~/.seed/credentials is configured):
    FAL_KEY          fal.ai API key (required while SEED_PROVIDER=fal)
    SEED_PROVIDER    "fal" (default) | "byteplus"
    MCP_TRANSPORT    "stdio" (default) | "sse"
    MCP_AUTH_TOKEN   Bearer token for SSE transport auth (optional)
    PORT             HTTP port for SSE transport (default: 8000)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
except ImportError as exc:
    raise SystemExit("mcp package not found. Install it: pip install mcp") from exc

from seed import SeedClient
from seed.config import __version__
from seed.exceptions import SeedError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed_mcp")

mcp = FastMCP(
    name="seed",
    instructions=(
        "Tools for BytePlus Seed models — audio generation and LLM text generation. "
        "AUDIO: use seed_audio_generate to submit a job. If the response status is already "
        "'completed' (synchronous providers like BytePlus), the audio_url is right there. "
        "Otherwise (async providers like fal) poll seed_check_task every 5–10 seconds until "
        "status == 'completed', which carries the audio_url. "
        "Pick a preset voice with seed_list_voices, or clone a voice by "
        "passing up to 3 public reference audio URLs in audio_urls and referencing them "
        "in the prompt as @Audio1, @Audio2, @Audio3. audio_urls and image_url are mutually "
        "exclusive. Reference audio/image must be PUBLIC URLs — local file paths are not "
        "supported yet. "
        "LLM: use seed_llm_generate for text generation with a Seed LLM (default "
        "seed-2-0-pro-260328; pass model='turbo' for dola-seed-2-1-turbo-260628). It is "
        "synchronous and returns the text directly. Pass mcp_servers to let the model call "
        "remote MCP servers. List LLM models with seed_list_llm_models."
    ),
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _client() -> SeedClient:
    return SeedClient()


def _err(exc: Exception) -> dict[str, Any]:
    logger.error("Tool error: %s", exc)
    return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Audio generation
# ---------------------------------------------------------------------------

@mcp.tool()
def seed_audio_generate(
    prompt: str,
    voice: str = "",
    audio_urls: list[str] | None = None,
    image_url: str = "",
    output_format: str = "mp3",
    sample_rate: int = 24000,
    speed: float = 1.0,
    volume: float = 1.0,
    pitch: int | None = None,
) -> dict:
    """Submit a Seed Audio 1.0 generation job (text/voice/reference → audio).

    Asynchronous: returns a request_id. Poll seed_check_task until status == 'completed'.

    Args:
        prompt: Text to synthesize, or a description of the audio to generate.
                Reference cloned voices in order as @Audio1, @Audio2, @Audio3.
        voice: Optional preset voice id (see seed_list_voices). Omit when using audio_urls.
        audio_urls: Up to 3 PUBLIC reference audio URLs for voice cloning (≤30s, ≤10MB each).
                    Mutually exclusive with image_url.
        image_url: Optional PUBLIC reference image URL (jpeg/png/webp, ≤10MB).
                   Mutually exclusive with audio_urls.
        output_format: mp3 (default) | wav | pcm | ogg_opus
        sample_rate: 8000 | 16000 | 24000 (default) | 32000 | 44100 | 48000
        speed: Speech speed. 1.0 normal, 0.5 half, 2.0 double.
        volume: Volume. 1.0 normal, 0.5 half, 2.0 double.
        pitch: Pitch shift in semitones. 0 normal, -12 down an octave, 12 up an octave.

    Returns:
        dict with request_id and status. Poll seed_check_task every 5–10s.
    """
    try:
        result = _client().submit_audio(
            prompt,
            voice=voice or None,
            audio_urls=audio_urls or None,
            image_url=image_url or None,
            output_format=output_format,
            sample_rate=sample_rate,
            speed=speed,
            volume=volume,
            pitch=pitch,
        )
    except SeedError as exc:
        return _err(exc)

    # Synchronous providers (e.g. BytePlus) return the audio on submit; async
    # providers (e.g. fal) return a queued task to poll with seed_check_task.
    if result.succeeded and result.audio_url:
        message = "Audio is ready. Download or play the audio_url."
    else:
        message = (
            f"Job submitted. Poll with seed_check_task(request_id='{result.request_id}') "
            "every 5–10 seconds until status == 'completed'."
        )
    return {**result.to_dict(), "message": message}


@mcp.tool()
def seed_check_task(request_id: str) -> dict:
    """Check the status of a Seed Audio generation task.

    Poll every 5–10 seconds after submitting. When status == 'completed' the
    response includes audio_url (plus duration / sample_rate metadata).

    Args:
        request_id: The request ID returned by seed_audio_generate.

    Returns:
        dict with status, and audio_url when completed.
    """
    try:
        result = _client().check_task(request_id)
    except SeedError as exc:
        return _err(exc)

    out = result.to_dict()
    if result.audio_url:
        out["message"] = "Audio is ready. Download or play the audio_url."
    elif result.status == "failed":
        out["message"] = f"Task failed: {result.error or 'unknown error'}."
    else:
        out["message"] = (
            f"Still processing (status='{result.status}'). Poll again in 5–10 seconds."
        )
    return out


# ---------------------------------------------------------------------------
# LLM text generation (BytePlus Ark Responses API)
# ---------------------------------------------------------------------------

@mcp.tool()
def seed_llm_generate(
    prompt: str,
    model: str = "",
    system: str = "",
    mcp_servers: list[dict] | None = None,
    tools: list[dict] | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> dict:
    """Generate text with a Seed LLM via the BytePlus Ark Responses API.

    Synchronous: returns the assistant's text directly (no polling). The model
    can call remote MCP servers on your behalf when `mcp_servers` is supplied.

    Args:
        prompt: The user message / task for the model.
        model: Seed LLM model id or alias. Empty = server default
               (seed-2-0-pro-260328). Accepts 'pro' (seed-2-0-pro-260328),
               'turbo' (dola-seed-2-1-turbo-260628), or any full model id.
        system: Optional system instruction prepended to the conversation.
        mcp_servers: Optional list of remote MCP servers for the model to use,
               each {"server_label": str, "server_url": str,
               "require_approval": "never"|..., "allowed_tools"?: [...]}.
               Example: [{"server_label": "deepwiki",
                          "server_url": "https://mcp.deepwiki.com/mcp",
                          "require_approval": "never"}].
        tools: Optional raw Ark tool specs (advanced; merged with mcp_servers).
        temperature: Sampling temperature 0.0–2.0 (optional).
        max_output_tokens: Cap on generated tokens (optional).

    Returns:
        dict with model, text, and (when tools ran) tool_calls + usage.
    """
    try:
        result = _client().generate_text(
            prompt,
            model=model or None,
            system=system or None,
            tools=tools or None,
            mcp_servers=mcp_servers or None,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    except SeedError as exc:
        return _err(exc)

    out = result.to_dict()
    out["message"] = "Generation complete. Read the `text` field."
    return out


@mcp.tool()
def seed_list_voices() -> dict:
    """List the available Seed Audio preset voice ids."""
    return _client().list_voices()


@mcp.tool()
def seed_list_models() -> dict:
    """List available Seed Audio models and their capabilities."""
    return _client().list_models()


@mcp.tool()
def seed_list_llm_models() -> dict:
    """List available Seed LLM (text) models and their capabilities."""
    return _client().list_llm_models()


@mcp.tool()
def seed_ping() -> dict:
    """Check server liveness, active provider, and credential configuration."""
    return _client().ping()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    port = int(os.getenv("PORT", "8000"))
    auth_token = os.getenv("MCP_AUTH_TOKEN", "").strip()

    if transport == "sse":
        try:
            import uvicorn
        except ImportError as exc:
            raise SystemExit("SSE transport requires uvicorn: pip install uvicorn") from exc

        mcp_app = mcp.streamable_http_app()

        class _Gateway:
            """ASGI middleware: health check, bearer-token auth, host-header rewrite."""

            def __init__(self, app: Any) -> None:
                self._app = app

            async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
                if scope["type"] != "http":
                    await self._app(scope, receive, send)
                    return

                path = scope.get("path", "")

                if path == "/health":
                    body = json.dumps({"status": "ok", "version": __version__}).encode()
                    await send({"type": "http.response.start", "status": 200,
                                "headers": [(b"content-type", b"application/json")]})
                    await send({"type": "http.response.body", "body": body})
                    return

                if auth_token:
                    hdrs = {k.lower(): v for k, v in scope.get("headers", [])}
                    auth = hdrs.get(b"authorization", b"").decode()
                    if auth != f"Bearer {auth_token}":
                        body = json.dumps({"error": "Unauthorized"}).encode()
                        await send({"type": "http.response.start", "status": 401,
                                    "headers": [(b"content-type", b"application/json")]})
                        await send({"type": "http.response.body", "body": body})
                        return

                new_hdrs = [(k, v) for k, v in scope.get("headers", []) if k.lower() != b"host"]
                new_hdrs.append((b"host", b"localhost"))
                await self._app({**scope, "headers": new_hdrs}, receive, send)

        logger.info("Starting Seed MCP server v%s on :%d (streamable-http, auth=%s)",
                    __version__, port, bool(auth_token))
        uvicorn.run(_Gateway(mcp_app), host="0.0.0.0", port=port)
    else:
        logger.info("Starting Seed MCP server v%s (stdio)...", __version__)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    _main()
