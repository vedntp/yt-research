"""API-key lookup and native secret-store helpers."""

from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError, NoKeyringError

ENV_VAR = "YT_RESEARCH_API_KEY"
SERVICE_NAME = "yt-research"
ACCOUNT_NAME = "youtube-data-api"


class CredentialError(RuntimeError):
    """Base class for actionable credential failures."""


class MissingCredentialError(CredentialError):
    """Raised when no API key is configured."""


class CredentialStoreError(CredentialError):
    """Raised when the operating system secret store is unavailable."""


def _store_error(action: str, exc: Exception) -> CredentialStoreError:
    return CredentialStoreError(
        f"Could not {action} the API key using the system secret store. "
        f"Set {ENV_VAR} in your environment instead."
    )


def get_api_key() -> str:
    """Return the configured API key, preferring the environment override."""

    environment_value = os.environ.get(ENV_VAR, "").strip()
    if environment_value:
        return environment_value

    try:
        stored_value = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
    except (KeyringError, NoKeyringError) as exc:
        raise _store_error("read", exc) from exc

    if stored_value and stored_value.strip():
        return stored_value.strip()
    raise MissingCredentialError(
        f"No YouTube API key is configured. Run `yt-research auth set` or set {ENV_VAR}."
    )


def credential_source() -> str | None:
    """Return ``environment`` or ``keyring`` without revealing the secret."""

    if os.environ.get(ENV_VAR, "").strip():
        return "environment"
    try:
        value = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
    except (KeyringError, NoKeyringError) as exc:
        raise _store_error("read", exc) from exc
    return "keyring" if value and value.strip() else None


def store_api_key(api_key: str) -> None:
    """Store an API key in the operating system secret store."""

    api_key = api_key.strip()
    if not api_key:
        raise CredentialError("The API key cannot be empty.")
    try:
        keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, api_key)
    except (KeyringError, NoKeyringError) as exc:
        raise _store_error("store", exc) from exc


def delete_api_key() -> bool:
    """Delete a stored key and report whether one existed."""

    try:
        existing = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
        if existing is None:
            return False
        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
    except (KeyringError, NoKeyringError) as exc:
        raise _store_error("delete", exc) from exc
    return True
