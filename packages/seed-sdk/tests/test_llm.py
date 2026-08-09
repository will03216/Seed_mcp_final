"""Tests for the Seed LLM (BytePlus Ark Responses API) client."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from seed.config import resolve_llm_model
from seed.exceptions import APIError, AuthError, ValidationError
from seed.llm import LLMParams, SeedLLM, _extract_text


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setenv("ARK_API_KEY", "ark-key")
    return SeedLLM()


def _payload(mock):
    return mock.call_args.kwargs["payload"]


def _headers(mock):
    return mock.call_args.kwargs["headers"]


# ---------------------------------------------------------------------------
# Model resolution (id + alias)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("given,expected", [
    ("pro", "seed-2-0-pro-260328"),
    ("turbo", "dola-seed-2-1-turbo-260628"),
    ("seed-2-0-pro-260328", "seed-2-0-pro-260328"),
    ("some-future-model", "some-future-model"),
    ("", "seed-2-0-pro-260328"),
    (None, "seed-2-0-pro-260328"),
])
def test_resolve_llm_model(given, expected):
    assert resolve_llm_model(given) == expected


# ---------------------------------------------------------------------------
# Payload shape (matches the documented curl)
# ---------------------------------------------------------------------------

def test_payload_basic():
    p = LLMParams(prompt="hi", model="turbo")
    payload = p.to_payload()
    assert payload["model"] == "dola-seed-2-1-turbo-260628"
    assert payload["stream"] is False
    assert payload["input"] == [
        {"role": "user", "content": [{"type": "input_text", "text": "hi"}]}
    ]
    assert "tools" not in payload


def test_payload_with_system():
    p = LLMParams(prompt="hi", system="be terse")
    assert p.to_payload()["input"][0] == {
        "role": "system", "content": [{"type": "input_text", "text": "be terse"}]
    }


def test_mcp_servers_become_tools():
    p = LLMParams(
        prompt="check repo",
        mcp_servers=[{"server_label": "deepwiki", "server_url": "https://mcp.deepwiki.com/mcp"}],
    )
    assert p.to_payload()["tools"] == [
        {
            "type": "mcp",
            "server_label": "deepwiki",
            "server_url": "https://mcp.deepwiki.com/mcp",
            "require_approval": "never",
        }
    ]
    assert p.uses_mcp is True


def test_optional_params_included():
    p = LLMParams(prompt="hi", temperature=0.7, max_output_tokens=256)
    payload = p.to_payload()
    assert payload["temperature"] == 0.7
    assert payload["max_output_tokens"] == 256


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_empty_prompt_raises():
    with pytest.raises(ValidationError, match="prompt is required"):
        LLMParams(prompt="  ").validate()


def test_bad_temperature_raises():
    with pytest.raises(ValidationError, match="temperature"):
        LLMParams(prompt="hi", temperature=3.0).validate()


def test_mcp_server_requires_url():
    with pytest.raises(ValidationError, match="server_url"):
        LLMParams(prompt="hi", mcp_servers=[{"server_label": "x"}]).validate()


# ---------------------------------------------------------------------------
# Auth headers
# ---------------------------------------------------------------------------

def test_bearer_auth_header(llm):
    resp = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}]}
    with patch("seed.llm.request_with_retry", return_value=resp) as mock:
        llm.generate(LLMParams(prompt="hi"))
    assert _headers(mock)["Authorization"] == "Bearer ark-key"
    assert "ark-beta-mcp" not in _headers(mock)


def test_mcp_beta_header_present_with_tools(llm):
    resp = {"output": []}
    with patch("seed.llm.request_with_retry", return_value=resp) as mock:
        llm.generate(LLMParams(
            prompt="hi",
            mcp_servers=[{"server_label": "d", "server_url": "https://x/mcp"}],
        ))
    assert _headers(mock)["ark-beta-mcp"] == "true"


def test_missing_ark_key_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("BYTEPLUS_ARK_API_KEY", raising=False)
    monkeypatch.setattr("seed.credentials.CREDENTIALS_PATH", tmp_path / "credentials")
    with pytest.raises(AuthError, match="ARK_API_KEY"):
        SeedLLM().generate(LLMParams(prompt="hi"))


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def test_generate_extracts_text(llm):
    resp = {
        "output": [
            {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "Hello "},
                         {"type": "output_text", "text": "world"}]},
        ],
        "usage": {"total_tokens": 12},
    }
    with patch("seed.llm.request_with_retry", return_value=resp):
        result = llm.generate(LLMParams(prompt="hi"))
    assert result.text == "Hello world"
    assert result.usage == {"total_tokens": 12}
    assert result.model == "seed-2-0-pro-260328"


def test_generate_prefers_output_text_convenience(llm):
    resp = {"output_text": "convenient", "output": []}
    with patch("seed.llm.request_with_retry", return_value=resp):
        result = llm.generate(LLMParams(prompt="hi"))
    assert result.text == "convenient"


def test_generate_captures_tool_calls(llm):
    resp = {
        "output": [
            {"type": "mcp_call", "name": "read_wiki", "server_label": "deepwiki", "status": "completed"},
            {"type": "message", "content": [{"type": "output_text", "text": "done"}]},
        ],
    }
    with patch("seed.llm.request_with_retry", return_value=resp):
        result = llm.generate(LLMParams(prompt="hi"))
    assert result.text == "done"
    assert result.tool_calls == [
        {"type": "mcp_call", "name": "read_wiki", "server_label": "deepwiki", "status": "completed"}
    ]


def test_generate_raises_on_error(llm):
    with patch("seed.llm.request_with_retry", return_value={"error": {"message": "boom"}}), \
         pytest.raises(APIError, match="boom"):
        llm.generate(LLMParams(prompt="hi"))


def test_extract_text_from_list_convenience():
    assert _extract_text({"output_text": ["a", "b"]}) == "ab"


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------

def test_stream_generate_yields_deltas(llm):
    events = [
        {"type": "response.output_text.delta", "delta": "Hel"},
        {"type": "response.output_text.delta", "delta": "lo"},
        {"type": "response.completed", "response": {"output": [], "usage": {"total_tokens": 3}}},
    ]
    with patch("seed.llm.stream_sse", return_value=iter(events)):
        deltas = list(llm.stream_generate(LLMParams(prompt="hi")))
    assert deltas == ["Hel", "lo"]


def test_streamed_generate_aggregates(llm):
    events = [
        {"type": "response.output_text.delta", "delta": "Hel"},
        {"type": "response.output_text.delta", "delta": "lo"},
        {"type": "response.completed", "response": {"output": [], "usage": {"total_tokens": 3}}},
    ]
    with patch("seed.llm.stream_sse", return_value=iter(events)):
        result = llm.generate(LLMParams(prompt="hi", stream=True))
    assert result.text == "Hello"
    assert result.usage == {"total_tokens": 3}
