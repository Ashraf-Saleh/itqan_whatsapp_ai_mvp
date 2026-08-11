"""Hot-reloaded Meta WhatsApp credentials.

Unlike the rest of the app's configuration (``app/config.py``), the four
Meta secrets — access token, phone number ID, WABA ID, and webhook verify
token — are read from ``meta_secrets.py`` at the repo root instead of
``.env``. That file is plain Python defining four module-level constants; it
is re-executed (via :func:`runpy.run_path`, not ``import``, so Python's
module cache never masks an edit) whenever its modification time changes, so
an operator can rotate a token by editing the file in place without
restarting the process.
"""

from __future__ import annotations

import runpy
from pathlib import Path

from pydantic import BaseModel, ValidationError

CREDENTIALS_PATH = Path(__file__).resolve().parent.parent / "meta_secrets.py"

REQUIRED_VARS = ("ACCESS_TOKEN", "PHONE_NUMBER_ID", "WABA_ID", "WEBHOOK_VERIFY_TOKEN")


class MetaCredentials(BaseModel):
    """Validated contents of ``meta_secrets.py``."""

    access_token: str
    phone_number_id: str
    waba_id: str
    webhook_verify_token: str


class MetaCredentialsError(RuntimeError):
    """Raised when meta_secrets.py is missing, unreadable, or invalid."""


_cache: dict[str, object] = {"mtime": None, "data": None}


def _load() -> MetaCredentials:
    try:
        namespace = runpy.run_path(str(CREDENTIALS_PATH))
    except FileNotFoundError as exc:
        raise MetaCredentialsError(
            f"Meta credentials file not found: {CREDENTIALS_PATH}. "
            "Copy meta_secrets.example.py to meta_secrets.py and fill in real values."
        ) from exc
    except SyntaxError as exc:
        raise MetaCredentialsError(f"{CREDENTIALS_PATH} has a syntax error: {exc}") from exc

    missing = [name for name in REQUIRED_VARS if name not in namespace]
    if missing:
        raise MetaCredentialsError(f"{CREDENTIALS_PATH} is missing required variable(s): {', '.join(missing)}")

    try:
        return MetaCredentials(
            access_token=namespace["ACCESS_TOKEN"],
            phone_number_id=namespace["PHONE_NUMBER_ID"],
            waba_id=namespace["WABA_ID"],
            webhook_verify_token=namespace["WEBHOOK_VERIFY_TOKEN"],
        )
    except ValidationError as exc:
        raise MetaCredentialsError(f"{CREDENTIALS_PATH} has invalid field values: {exc}") from exc


def get_meta_credentials() -> MetaCredentials:
    """Return the current Meta credentials, reloading if the file changed on disk."""
    try:
        mtime = CREDENTIALS_PATH.stat().st_mtime
    except OSError as exc:
        raise MetaCredentialsError(
            f"Meta credentials file not found: {CREDENTIALS_PATH}. "
            "Copy meta_secrets.example.py to meta_secrets.py and fill in real values."
        ) from exc
    if _cache["data"] is None or _cache["mtime"] != mtime:
        _cache["data"] = _load()
        _cache["mtime"] = mtime
    return _cache["data"]  # type: ignore[return-value]
