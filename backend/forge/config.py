"""Centralized, environment-driven configuration.

Per the master spec, Forge favors *explicit* configuration over hidden defaults and
must keep secrets out of source control. All settings are read from the environment
(prefixed ``FORGE_``) or an optional ``.env`` file and validated at process start, so a
misconfigured deployment fails fast rather than at first use.
"""

from __future__ import annotations

import tempfile
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment. Controls fail-fast safety checks."""

    local = "local"
    development = "development"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    """Application settings, validated once at startup.

    The defaults are intentionally safe for zero-config local development (SQLite,
    a placeholder secret). Non-local environments must override the secret and
    database URL, which is enforced in :meth:`_enforce_production_safety`.
    """

    model_config = SettingsConfigDict(
        env_prefix="FORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.local

    # Security
    secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60

    # Persistence
    database_url: str = "sqlite+pysqlite:///./forge.db"

    # API / UI
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    api_v1_prefix: str = "/api/v1"

    # Observability
    log_level: str = "INFO"

    # Tool runtime (Phase 4)
    # Root directory under which each project gets an isolated, path-jailed workspace
    # that tools operate within. The container-backed sandbox (Phase 5) will supersede
    # this local environment for full process/network isolation.
    workspaces_root: str = Field(
        default_factory=lambda: str(Path(tempfile.gettempdir()) / "forge-workspaces")
    )

    # Sandbox backend selection (Phase 5): "auto" uses the container sandbox when a Docker
    # daemon is reachable and falls back to the local workspace sandbox; "local"/"docker"
    # force a specific backend.
    sandbox_backend: str = "auto"

    _INSECURE_SECRET = "dev-only-insecure-secret-change-me"

    @field_validator("sandbox_backend")
    @classmethod
    def _validate_sandbox_backend(cls, value: str) -> str:
        allowed = {"auto", "local", "docker"}
        if value not in allowed:
            raise ValueError(f"sandbox_backend must be one of {sorted(allowed)}")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        """Accept a comma-separated string from the environment."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def local_command_execution_enabled(self) -> bool:
        """Whether tools may spawn subprocesses in the local workspace environment.

        Command-spawning tools (terminal/git/package) require a *controlled* execution
        environment. Full process isolation is the container sandbox (Phase 5). Until it
        exists, we permit command execution only in ``local``/``development`` — where the
        operator implicitly accepts an unisolated local workspace — and refuse it in
        ``staging``/``production`` so unsafe host execution can never ship by default.
        """
        return self.environment in (Environment.local, Environment.development)

    def enforce_runtime_safety(self) -> None:
        """Fail fast when a non-local environment is dangerously misconfigured.

        This upholds the security invariant that production never runs with the
        placeholder signing key or an ephemeral SQLite database.
        """
        if self.environment in (Environment.staging, Environment.production):
            if self.secret_key == self._INSECURE_SECRET or len(self.secret_key) < 32:
                raise RuntimeError(
                    "FORGE_SECRET_KEY must be a strong, non-default value in "
                    f"{self.environment.value}."
                )
            if self.is_sqlite:
                raise RuntimeError(
                    "SQLite is not permitted outside local/development; set a "
                    "PostgreSQL FORGE_DATABASE_URL."
                )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    settings = Settings()
    settings.enforce_runtime_safety()
    return settings
