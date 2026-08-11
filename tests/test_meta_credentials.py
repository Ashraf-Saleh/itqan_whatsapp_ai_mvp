"""Tests for the hot-reloaded meta_secrets.py loader."""

import os

import pytest

from app import meta_credentials as mc


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch, tmp_path):
    """Point the loader at an isolated file and clear its in-memory cache."""
    path = tmp_path / "meta_secrets.py"
    monkeypatch.setattr(mc, "CREDENTIALS_PATH", path)
    monkeypatch.setattr(mc, "_cache", {"mtime": None, "data": None})
    return path


def write_credentials(path, **overrides):
    values = {
        "ACCESS_TOKEN": "token-1",
        "PHONE_NUMBER_ID": "phone-1",
        "WABA_ID": "waba-1",
        "WEBHOOK_VERIFY_TOKEN": "verify-1",
    }
    values.update(overrides)
    source = "\n".join(f"{name} = {value!r}" for name, value in values.items())
    path.write_text(source, encoding="utf-8")


def test_missing_file_raises_clear_error(reset_cache):
    """A missing meta_secrets.py fails fast with MetaCredentialsError."""
    with pytest.raises(mc.MetaCredentialsError):
        mc.get_meta_credentials()


def test_syntax_error_raises_clear_error(reset_cache):
    """A file that isn't valid Python fails fast instead of raising SyntaxError."""
    reset_cache.write_text("ACCESS_TOKEN = 'unterminated", encoding="utf-8")
    with pytest.raises(mc.MetaCredentialsError):
        mc.get_meta_credentials()


def test_missing_variable_raises_clear_error(reset_cache):
    """A file missing a required constant fails validation."""
    reset_cache.write_text("ACCESS_TOKEN = 'token-1'\n", encoding="utf-8")
    with pytest.raises(mc.MetaCredentialsError):
        mc.get_meta_credentials()


def test_valid_file_returns_credentials(reset_cache):
    """A well-formed file returns a populated MetaCredentials instance."""
    write_credentials(reset_cache)
    credentials = mc.get_meta_credentials()
    assert credentials.access_token == "token-1"
    assert credentials.phone_number_id == "phone-1"
    assert credentials.waba_id == "waba-1"
    assert credentials.webhook_verify_token == "verify-1"


def test_hot_reload_picks_up_changes_without_restart(reset_cache):
    """Editing the file on disk is reflected on the next call, no cache-clear needed."""
    write_credentials(reset_cache)
    first = mc.get_meta_credentials()
    assert first.access_token == "token-1"

    # Ensure the mtime actually advances on filesystems with coarse resolution.
    current_mtime = os.stat(reset_cache).st_mtime
    write_credentials(reset_cache, ACCESS_TOKEN="token-2")
    new_mtime = current_mtime + 1
    os.utime(reset_cache, (new_mtime, new_mtime))

    second = mc.get_meta_credentials()
    assert second.access_token == "token-2"
