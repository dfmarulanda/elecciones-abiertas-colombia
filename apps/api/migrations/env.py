from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from elecciones_api.db import Base
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    """Prefer the environment over the checked-in local default.

    ``alembic.ini`` carries ``postgresql+psycopg://localhost/elecciones`` for
    development. Running a deployment migration against that literal would
    either fail or, far worse, migrate whatever happens to answer on localhost
    while production stays on an older schema. The same aliases the API accepts
    are honoured here so one variable configures both.
    """
    url = os.environ.get("ELECCIONES_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        return config.get_main_option("sqlalchemy.url", "")
    # Railway and most managed providers hand out `postgresql://`; the app and
    # these migrations both use the psycopg 3 driver explicitly.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


config.set_main_option("sqlalchemy.url", _database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
