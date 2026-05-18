"""Alembic environment.

Migrations live in deploy/backup_auth/alembic/. backup_auth and admin_panel
share the same MySQL database, so this is the single source of truth for
schema changes. admin_panel does NOT run alembic separately — deploy script
must run alembic from this directory.
"""

from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config, pool
from alembic import context

# Make `app` importable (the alembic script is launched from
# deploy/backup_auth/, so we add that dir to sys.path).
HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE_ROOT = os.path.dirname(HERE)
if SERVICE_ROOT not in sys.path:
    sys.path.insert(0, SERVICE_ROOT)

from app.database import Base  # noqa: E402
from app import models  # noqa: F401,E402  (register models on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_db_url() -> str:
    """Read APP_DB_URL from env (same var backup_auth/admin_panel use)."""
    url = os.getenv("APP_DB_URL", "").strip()
    if not url:
        raise RuntimeError("APP_DB_URL must be set for alembic to run.")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg_section = config.get_section(config.config_ini_section) or {}
    cfg_section["sqlalchemy.url"] = _resolve_db_url()
    connectable = engine_from_config(cfg_section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
