"""Low-level HTTP helpers: requests, retry, and response parsing.

Intentionally uses stdlib urllib only — zero extra dependencies.
"""
from __future__ import annotations

import json
import logging
import random
import time
from collections.abc import Iterator
from typing import Any
from urllib import error, request

from .config import MAX_RETRIES, POLL_TIMEOUT
from .exceptions import APIError

logger = logging.getLogger("seed")


def _do_request(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: int = POLL_TIMEOUT,
) -> dict[str, Any]:
    body = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        detail = exc.read().decode(errors="ignore")
        raise APIError(f"HTTP {exc.code}: {detail}", status_code=exc.code) from exc
    except error.URLError as exc:
        raise APIError(f"Network error: {exc.reason}") from exc


def request_with_retry(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: int = POLL_TIMEOUT,
    max_retries: int = MAX_RETRIES,
    correlation_id: str = "",
) -> dict[str, Any]:
    tag = f"[{correlation_id}] " if correlation_id else ""
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            return _do_request(url, method=method, headers=headers, payload=payload, timeout=timeout)
        except APIError as exc:
            last_exc = exc
            # 4xx errors are not retryable (bad request, auth failure, etc.)
            if exc.status_code is not None and 400 <= exc.status_code < 500:
                raise
            wait = (2 ** attempt) + random.random()
            logger.warning(
                "%sRetrying in %.1fs (attempt %d/%d): %s",
                tag, wait, attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(wait)

    raise APIError(f"Request failed after {max_retries} attempts: {last_exc}") from last_exc


def stream_sse(
    url: str,
    *,
    method: str = "POST",
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: int = POLL_TIMEOUT,
) -> Iterator[dict[str, Any]]:
    """POST and yield decoded JSON objects from a `text/event-stream` response.

    Each ``data: {...}`` line is parsed and yielded. The terminal
    ``data: [DONE]`` sentinel ends the stream. Non-JSON data lines are skipped.
    """
    body = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    return
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    continue
    except error.HTTPError as exc:
        detail = exc.read().decode(errors="ignore")
        raise APIError(f"HTTP {exc.code}: {detail}", status_code=exc.code) from exc
    except error.URLError as exc:
        raise APIError(f"Network error: {exc.reason}") from exc


def extract_nested(data: dict[str, Any], *keys: str) -> Any:
    """Safely walk a nested dict without raising; returns None if any key is missing."""
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
