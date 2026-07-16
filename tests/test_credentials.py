from __future__ import annotations

import keyring
import pytest
from keyring.errors import NoKeyringError

from yt_research.credentials import (
    ENV_VAR,
    CredentialStoreError,
    MissingCredentialError,
    credential_source,
    delete_api_key,
    get_api_key,
    store_api_key,
)


def test_environment_key_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, " environment-secret ")
    monkeypatch.setattr(keyring, "get_password", lambda *_: "stored-secret")

    assert get_api_key() == "environment-secret"
    assert credential_source() == "environment"


def test_keyring_is_used_when_environment_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setattr(keyring, "get_password", lambda *_: " stored-secret ")

    assert get_api_key() == "stored-secret"
    assert credential_source() == "keyring"


def test_missing_key_has_actionable_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setattr(keyring, "get_password", lambda *_: None)

    with pytest.raises(MissingCredentialError, match="auth set"):
        get_api_key()


def test_unavailable_keyring_recommends_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)

    def unavailable(*_: object) -> None:
        raise NoKeyringError("no backend")

    monkeypatch.setattr(keyring, "get_password", unavailable)

    with pytest.raises(CredentialStoreError, match=ENV_VAR):
        get_api_key()


def test_store_strips_key_without_printing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    stored: list[tuple[str, str, str]] = []
    monkeypatch.setattr(keyring, "set_password", lambda *args: stored.append(args))

    store_api_key(" secret-value ")

    assert stored[0][2] == "secret-value"


def test_delete_reports_whether_stored_key_existed(monkeypatch: pytest.MonkeyPatch) -> None:
    deleted: list[tuple[str, str]] = []
    monkeypatch.setattr(keyring, "get_password", lambda *_: "stored-secret")
    monkeypatch.setattr(keyring, "delete_password", lambda *args: deleted.append(args))

    assert delete_api_key() is True
    assert deleted
