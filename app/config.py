"""Application configuration loaded from environment variables.

The module exposes the :class:`Settings` model and a cached ``get_settings``
factory used by the API, database, AI agent, and Meta client. The Meta
access token, phone number ID, WABA ID, and webhook verify token are not
part of this module — see ``app/meta_credentials.py`` for those, which are
hot-reloaded from ``meta_secrets.py`` instead of ``.env``.
"""

import logging
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("app.config")


class Settings(BaseSettings):
    """Typed runtime configuration for the complete application."""
    app_name: str = "WhatsApp Real Estate AI MVP - Meta Cloud API"
    app_base_url: str = "http://localhost:8000"
    admin_api_key: str = "change-me-now"
    database_url: str = "sqlite:///./data/real_estate_agent.db"

    meta_app_secret: str = ""
    meta_validate_signature: bool = True
    meta_graph_api_version: str = "v26.0"
    meta_test_template_name: str = "itqan_lead_outreach"
    meta_test_template_language: str = "ar"
    meta_template_parameter_count: int = Field(default=1, ge=0, le=1)

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    human_sales_name: str = "Sales Team"
    human_sales_phone: str = "+201000000000"
    company_name: str = "ITQAN Real Estate"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("*", mode="before")
    @classmethod
    def _clean_string_env(cls, value):
        """Strip surrounding quotes/whitespace/newlines that sneak in from .env files
        (e.g. GEMINI_API_KEY="abc123\\n" or KEY='abc123')."""
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ("'", '"'):
            cleaned = cleaned[1:-1].strip()
        # Strip stray leading "--" some people paste from CLI examples, and any embedded newlines.
        cleaned = cleaned.replace("\r", "").replace("\n", "")
        if cleaned.startswith("--"):
            cleaned = cleaned.lstrip("-").strip()
        return cleaned

    @model_validator(mode="after")
    def _validate_required_keys(self):
        """Warn about optional integrations that cannot work when unconfigured."""
        if not self.gemini_api_key:
            logger.warning(
                "GEMINI_API_KEY is empty — the AI agent will fall back to a static reply for every message."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings instance for the current process."""
    return Settings()
