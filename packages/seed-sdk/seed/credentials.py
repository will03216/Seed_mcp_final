"""Credential loading with a priority chain.

Resolution order (first non-empty value wins):
  1. Explicit constructor arguments
  2. Environment variables  (FAL_KEY)
  3. ~/.seed/credentials  INI file  [default] section
  4. .env file in CWD  (loaded only when python-dotenv is installed)

When the BytePlus Seed API ships, BYTEPLUS_SEED_API_KEY slots into the same
chain — the labelled helper below is already wired for it.
"""
from __future__ import annotations

import configparser
import os
from pathlib import Path

from .exceptions import AuthError

CREDENTIALS_PATH = Path.home() / ".seed" / "credentials"
CONFIG_PATH = Path.home() / ".seed" / "config"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _read_ini(path: Path, section: str, key: str) -> str:
    if not path.exists():
        return ""
    parser = configparser.ConfigParser()
    parser.read(path)
    return parser.get(section, key, fallback="").strip()


def load_fal_key(explicit: str | None = None, *, profile: str = "default") -> str:
    """Return the fal.ai API key, or raise AuthError."""
    _load_dotenv()

    value = (
        (explicit or "").strip()
        or os.getenv("FAL_KEY", "").strip()
        or _read_ini(CREDENTIALS_PATH, profile, "fal_key")
    )

    if not value:
        raise AuthError(
            "FAL_KEY is not configured.\n"
            "Seed Audio currently runs on fal.ai. Set the key via one of:\n"
            "  export FAL_KEY=<key>\n"
            "  seed auth login\n"
            "  echo '[default]\\nfal_key=<key>' > ~/.seed/credentials\n"
            "Get a key at https://fal.ai/dashboard/keys"
        )
    return value


def load_byteplus_auth(
    explicit_key: str | None = None,
    explicit_app_id: str | None = None,
    explicit_access_key: str | None = None,
    *,
    profile: str = "default",
) -> dict[str, str]:
    """Return the BytePlus auth headers, or raise AuthError.

    Two modes (use one):
      - New console: single ``X-Api-Key`` header (BYTEPLUS_SEED_API_KEY).
      - Legacy console: ``X-Api-App-Id`` + ``X-Api-Access-Key``
        (BYTEPLUS_SEED_APP_ID / BYTEPLUS_SEED_ACCESS_KEY).
    The new-console key takes precedence when both are present.
    """
    _load_dotenv()

    key = (
        (explicit_key or "").strip()
        or os.getenv("BYTEPLUS_SEED_API_KEY", "").strip()
        or _read_ini(CREDENTIALS_PATH, profile, "byteplus_seed_api_key")
    )
    if key:
        return {"X-Api-Key": key}

    app_id = (
        (explicit_app_id or "").strip()
        or os.getenv("BYTEPLUS_SEED_APP_ID", "").strip()
        or _read_ini(CREDENTIALS_PATH, profile, "byteplus_seed_app_id")
    )
    access_key = (
        (explicit_access_key or "").strip()
        or os.getenv("BYTEPLUS_SEED_ACCESS_KEY", "").strip()
        or _read_ini(CREDENTIALS_PATH, profile, "byteplus_seed_access_key")
    )
    if app_id and access_key:
        return {"X-Api-App-Id": app_id, "X-Api-Access-Key": access_key}

    raise AuthError(
        "BytePlus Seed Audio credentials are not configured.\n"
        "Set ONE of:\n"
        "  export BYTEPLUS_SEED_API_KEY=<key>                 (new console)\n"
        "  export BYTEPLUS_SEED_APP_ID=<id> BYTEPLUS_SEED_ACCESS_KEY=<key>  (legacy)\n"
        "Get them from the Volcengine Speech console."
    )


def load_ark_key(explicit: str | None = None, *, profile: str = "default") -> str:
    """Return the BytePlus Ark API key for Seed LLM, or raise AuthError.

    Used by the Ark Responses API (Seed LLM). Accepts ``ARK_API_KEY`` (matching
    the BytePlus console docs) or the namespaced ``BYTEPLUS_ARK_API_KEY``.
    """
    _load_dotenv()

    value = (
        (explicit or "").strip()
        or os.getenv("ARK_API_KEY", "").strip()
        or os.getenv("BYTEPLUS_ARK_API_KEY", "").strip()
        or _read_ini(CREDENTIALS_PATH, profile, "ark_api_key")
    )

    if not value:
        raise AuthError(
            "ARK_API_KEY is not configured.\n"
            "Seed LLM runs on the BytePlus Ark Responses API. Set the key via one of:\n"
            "  export ARK_API_KEY=<key>\n"
            "  seed auth login\n"
            "  echo '[default]\\nark_api_key=<key>' > ~/.seed/credentials\n"
            "Get a key at https://console.byteplus.com/ark/"
        )
    return value


def write_credentials(
    fal_key: str = "",
    *,
    byteplus_seed_api_key: str = "",
    byteplus_seed_app_id: str = "",
    byteplus_seed_access_key: str = "",
    ark_api_key: str = "",
    profile: str = "default",
) -> None:
    """Persist credentials to ~/.seed/credentials."""
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)

    parser = configparser.ConfigParser()
    if CREDENTIALS_PATH.exists():
        parser.read(CREDENTIALS_PATH)

    if not parser.has_section(profile):
        parser.add_section(profile)

    for field, value in (
        ("fal_key", fal_key),
        ("byteplus_seed_api_key", byteplus_seed_api_key),
        ("byteplus_seed_app_id", byteplus_seed_app_id),
        ("byteplus_seed_access_key", byteplus_seed_access_key),
        ("ark_api_key", ark_api_key),
    ):
        if value:
            parser.set(profile, field, value)

    with CREDENTIALS_PATH.open("w") as f:
        parser.write(f)

    # Restrict permissions — credentials file should not be world-readable
    CREDENTIALS_PATH.chmod(0o600)


def clear_credentials(*, profile: str = "default") -> bool:
    """Remove a profile from ~/.seed/credentials. Returns True if file existed."""
    if not CREDENTIALS_PATH.exists():
        return False

    parser = configparser.ConfigParser()
    parser.read(CREDENTIALS_PATH)

    if parser.has_section(profile):
        parser.remove_section(profile)
        with CREDENTIALS_PATH.open("w") as f:
            parser.write(f)

    return True


def credentials_configured(*, profile: str = "default") -> dict[str, bool]:
    """Return which credentials are available (for `seed auth check`)."""
    _load_dotenv()
    return {
        "fal_key": bool(
            os.getenv("FAL_KEY", "").strip()
            or _read_ini(CREDENTIALS_PATH, profile, "fal_key")
        ),
        "byteplus_seed_api_key": bool(
            os.getenv("BYTEPLUS_SEED_API_KEY", "").strip()
            or _read_ini(CREDENTIALS_PATH, profile, "byteplus_seed_api_key")
        ),
        "byteplus_seed_app_id": bool(
            os.getenv("BYTEPLUS_SEED_APP_ID", "").strip()
            or _read_ini(CREDENTIALS_PATH, profile, "byteplus_seed_app_id")
        ),
        "byteplus_seed_access_key": bool(
            os.getenv("BYTEPLUS_SEED_ACCESS_KEY", "").strip()
            or _read_ini(CREDENTIALS_PATH, profile, "byteplus_seed_access_key")
        ),
        "ark_api_key": bool(
            os.getenv("ARK_API_KEY", "").strip()
            or os.getenv("BYTEPLUS_ARK_API_KEY", "").strip()
            or _read_ini(CREDENTIALS_PATH, profile, "ark_api_key")
        ),
    }
