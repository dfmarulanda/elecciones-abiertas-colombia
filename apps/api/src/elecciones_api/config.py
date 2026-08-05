"""Runtime configuration for the read-only API."""

import json
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CURSOR_SECRET = "development-only-change-me"  # noqa: S105 - local default only


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ELECCIONES_", extra="ignore", populate_by_name=True
    )

    cursor_secret: str = Field(
        default=DEFAULT_CURSOR_SECRET,
        validation_alias=AliasChoices("ELECCIONES_CURSOR_SECRET", "CURSOR_SECRET"),
    )
    cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("ELECCIONES_CORS_ORIGINS", "ALLOWED_ORIGINS"),
    )
    sentry_dsn: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ELECCIONES_SENTRY_DSN", "SENTRY_DSN"),
    )
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ELECCIONES_DATABASE_URL", "DATABASE_URL"),
    )
    historical_releases: str = Field(
        default="",
        validation_alias=AliasChoices("ELECCIONES_HISTORICAL_RELEASES", "HISTORICAL_RELEASES"),
    )
    historical_data_path: Path = Field(
        default=Path(__file__).resolve().parents[4] / "data",
        validation_alias=AliasChoices("ELECCIONES_HISTORICAL_DATA_PATH", "HISTORICAL_DATA_PATH"),
    )
    fixture_path: Path = Field(
        default=Path(__file__).resolve().parents[4] / "data/fixtures/fixture-release.json",
        validation_alias=AliasChoices("ELECCIONES_FIXTURE_PATH", "FIXTURE_DATA_PATH"),
    )
    artifact_hosts: str = Field(
        default="eleccionesabiertas.co",
        validation_alias=AliasChoices("ELECCIONES_ARTIFACT_HOSTS", "ARTIFACT_HOSTS"),
    )
    trusted_hosts: str = Field(
        default="localhost,127.0.0.1,testserver",
        validation_alias=AliasChoices("ELECCIONES_TRUSTED_HOSTS", "TRUSTED_HOSTS"),
    )
    official_document_hosts: str = Field(
        # example.invalid is restricted to the checked-in synthetic fixture.
        default="example.invalid",
        validation_alias=AliasChoices(
            "ELECCIONES_OFFICIAL_DOCUMENT_HOSTS", "OFFICIAL_DOCUMENT_HOSTS"
        ),
    )
    active_release_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ELECCIONES_ACTIVE_RELEASE", "ACTIVE_RELEASE"),
    )
    active_release_pointer: Path = Field(
        default=Path(__file__).resolve().parents[4] / "data/manifests/current-release.json",
        validation_alias=AliasChoices(
            "ELECCIONES_ACTIVE_RELEASE_POINTER", "ACTIVE_RELEASE_POINTER"
        ),
    )

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_artifact_hosts(self) -> set[str]:
        return {host.strip().lower() for host in self.artifact_hosts.split(",") if host.strip()}

    @property
    def allowed_trusted_hosts(self) -> list[str]:
        hosts = [host.strip().lower() for host in self.trusted_hosts.split(",") if host.strip()]
        if not hosts:
            raise ValueError("TRUSTED_HOSTS must contain at least one host")
        return hosts

    @property
    def allowed_official_document_hosts(self) -> set[str]:
        hosts = {
            host.strip().lower().rstrip(".")
            for host in self.official_document_hosts.split(",")
            if host.strip()
        }
        if not hosts:
            raise ValueError("OFFICIAL_DOCUMENT_HOSTS must contain at least one exact host")
        return hosts

    def selected_release_id(self) -> str:
        """Resolve the immutable release selected by the checked-in rollback pointer."""
        if self.active_release_id:
            return self.active_release_id
        try:
            pointer = json.loads(self.active_release_pointer.read_text(encoding="utf-8"))
            release_id = pointer["release_id"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(
                "ACTIVE_RELEASE or a valid ACTIVE_RELEASE_POINTER is required in database mode."
            ) from exc
        if not isinstance(release_id, str) or not release_id:
            raise ValueError("The active release pointer has no valid release_id.")
        return release_id

    @model_validator(mode="after")
    def secure_database_mode(self) -> "Settings":
        if (
            self.database_url or self.historical_releases
        ) and self.cursor_secret == DEFAULT_CURSOR_SECRET:
            raise ValueError(
                "CURSOR_SECRET must be configured when DATABASE_URL selects production mode."
            )
        return self
