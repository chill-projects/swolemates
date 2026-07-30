from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "test", "production"] = "local"

    # Runtime log verbosity. Flipping this is a Railway variable change (container
    # restart, no rebuild) — diagnostics should never need a deployment. DEBUG adds
    # token aud/iss detail to auth rejections; INFO logs only the rejection reason.
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Railway injects DATABASE_URL. It arrives as postgresql://... which SQLAlchemy would
    # route to psycopg2; normalize_database_url() rewrites the scheme to psycopg 3.
    database_url: str = "postgresql://swolemates:swolemates@localhost:5432/swolemates"

    # Public origin of the deployed container. Used for OAuth resource metadata and to
    # build ui:// asset URLs, so it must match what Claude actually connects to.
    public_url: str = "http://localhost:8000"

    # WorkOS AuthKit. Empty in local dev, where dev_user_sub takes over instead.
    authkit_domain: str = ""
    workos_client_id: str = ""
    # The environment's own client ID. AuthKit stamps it as `aud` on tokens minted for
    # first-party apps (it ignores the SPA's RFC 8707 resource request), so it's an
    # accepted audience alongside PUBLIC_URL. Distinct from workos_client_id, which is
    # the Connect application the SPA authenticates as.
    workos_environment_client_id: str = ""

    # Local-only auth bypass so the dev loop doesn't need an OAuth round trip per call.
    # Ignored unless environment == "local"; see require_user() in app/auth.py.
    dev_user_sub: str = "dev_user_00000000"

    # Vite dev server. Not used in production, where the SPA is same-origin.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @model_validator(mode="after")
    def _production_requires_real_auth(self) -> "Settings":
        if self.environment != "production":
            return self

        missing = [
            name for name in ("authkit_domain", "workos_client_id") if not getattr(self, name)
        ]
        # public_url has a localhost default, so "not set" can't be detected by emptiness.
        # Left unset in production it becomes the OAuth token audience, every token fails
        # to validate, and the symptom is an unexplained login loop rather than a boot
        # error. Reject the default explicitly.
        if not self.public_url or "localhost" in self.public_url:
            missing.append("public_url (must be the real public origin, not localhost)")
        if missing:
            raise ValueError(f"environment=production requires {', '.join(missing)} to be set")
        return self

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    def normalize_database_url(self) -> str:
        """Return DATABASE_URL with an explicit psycopg 3 driver.

        Railway and most managed Postgres hand out bare `postgresql://` URLs, which
        SQLAlchemy would route to psycopg2. psycopg 3 serves both the async app engine
        and the sync engine Alembic runs on, so one normalized URL covers both.
        """
        url = self.database_url
        for prefix in (
            "postgresql+psycopg://",
            "postgresql+asyncpg://",
            "postgresql://",
            "postgres://",
        ):
            if url.startswith(prefix):
                url = url.removeprefix(prefix)
                break
        return f"postgresql+psycopg://{url}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
