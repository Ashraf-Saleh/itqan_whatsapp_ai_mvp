"""Logging setup: console output plus a persisted rotating file under logs/.

Covers this app's own loggers (``app.*``) and uvicorn's request/error loggers,
which by default attach their own handlers with ``propagate=False`` and would
otherwise be invisible to a shared file handler.
"""

import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging() -> None:
    """Attach a console handler and a rotating file handler to every logger
    that matters, regardless of whether uvicorn already configured logging
    before this module is imported."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # force=True guarantees our console handler exists even if uvicorn (or
    # anything else) already called basicConfig / added root handlers first.
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, force=True)
    logging.getLogger().addHandler(file_handler)

    # uvicorn's default logging config gives "uvicorn" and "uvicorn.access"
    # their own console handlers with propagate=False, so the root file
    # handler alone would never see request lines - attach directly instead.
    # "uvicorn.error" is deliberately excluded: it propagates up to "uvicorn"
    # (propagate=False stops it there), so adding a handler to both would
    # log every uvicorn.error record twice.
    for name in ("uvicorn", "uvicorn.access"):
        logging.getLogger(name).addHandler(file_handler)
