"""
Application configuration using pydantic-settings.
Loads settings from environment variables / .env file.
API key is NEVER logged or exposed.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    app_name: str = "Smartlead Weekly Mailbox Analytics"
    app_env: str = "development"
    log_level: str = "INFO"

    # ---- Smartlead API ----
    # SECURITY: Never log, never expose through any endpoint
    smartlead_api_key: str
    api_base_url: str = "https://server.smartlead.ai/api/v1"

    # ---- API Client Behaviour ----
    smartlead_max_concurrency: int = 2
    smartlead_request_timeout: int = 30
    smartlead_max_retries: int = 5
    smartlead_request_interval: float = 0.35
    smartlead_max_retry_delay: float = 65.0

    # ---- Campaign Filtering ----
    # By default, skip ARCHIVED and DRAFTED campaigns to conserve API quota and avoid rate limits.
    smartlead_include_archived: bool = False
    smartlead_include_drafted: bool = False

    # ---- Database ----
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/smartlead_reports"

    # ---- Scheduler ----
    report_day: str = "MONDAY"
    report_hour: int = 9
    report_minute: int = 0

    # ---- Feature Flags ----
    dry_run: bool = False

    @field_validator("smartlead_api_key")
    @classmethod
    def api_key_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "SMARTLEAD_API_KEY must be set in your .env file. "
                "See .env.example for reference."
            )
        return v.strip()

    @field_validator("smartlead_max_concurrency")
    @classmethod
    def concurrency_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("SMARTLEAD_MAX_CONCURRENCY must be >= 1")
        if v > 20:
            raise ValueError(
                "SMARTLEAD_MAX_CONCURRENCY > 20 may trigger API rate limits. "
                "Keep it <= 10 to be safe."
            )
        return v

    @field_validator("report_hour")
    @classmethod
    def validate_hour(cls, v: int) -> int:
        if not 0 <= v <= 23:
            raise ValueError("REPORT_HOUR must be 0-23")
        return v

    @field_validator("report_minute")
    @classmethod
    def validate_minute(cls, v: int) -> int:
        if not 0 <= v <= 59:
            raise ValueError("REPORT_MINUTE must be 0-59")
        return v

    def safe_repr(self) -> dict:
        """Return a safe representation of settings (no secrets)."""
        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "log_level": self.log_level,
            "api_base_url": self.api_base_url,
            "smartlead_max_concurrency": self.smartlead_max_concurrency,
            "smartlead_request_timeout": self.smartlead_request_timeout,
            "smartlead_max_retries": self.smartlead_max_retries,
            "smartlead_request_interval": self.smartlead_request_interval,
            "smartlead_include_archived": self.smartlead_include_archived,
            "smartlead_include_drafted": self.smartlead_include_drafted,
            "database_url": self._mask_db_url(),
            "report_day": self.report_day,
            "report_hour": self.report_hour,
            "report_minute": self.report_minute,
            "dry_run": self.dry_run,
        }

    def _mask_db_url(self) -> str:
        """Mask credentials in the database URL for safe logging."""
        try:
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(self.database_url)
            masked = parsed._replace(
                netloc=f"****:****@{parsed.hostname}:{parsed.port}"
            )
            return urlunparse(masked)
        except Exception:
            return "****"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
