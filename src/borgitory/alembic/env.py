import os
import sys
from logging.config import fileConfig
from typing import Optional, Literal

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy.schema import SchemaItem

from alembic import context

# Add the project root and src directory to the Python path
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.join(os.path.abspath("."), "src"))

# Import the models and Base for autogenerate support
from borgitory.models.database import Base
from borgitory.config_module import DATABASE_URL

# Import all models to ensure they're registered with Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(
    object: SchemaItem,
    name: Optional[str],
    type_: Literal[
        "schema",
        "table",
        "column",
        "index",
        "unique_constraint",
        "foreign_key_constraint",
    ],
    reflected: bool,
    compare_to: Optional[SchemaItem],
) -> bool:
    """
    Filter function to exclude certain objects from autogenerate.

    This function is called for every object that Alembic considers
    for inclusion in a migration.
    """
    # Ignore anything related to apscheduler - it's managed by APScheduler
    if name and "apscheduler" in name.lower():
        return False

    # Specifically ignore apscheduler_jobs table and related objects
    if type_ == "table" and name == "apscheduler_jobs":
        return False

    # Ignore indexes on apscheduler tables
    if (
        type_ == "index"
        and name
        and ("apscheduler" in name.lower() or "ix_apscheduler" in name.lower())
    ):
        return False

    # Include all other objects
    return True


def get_database_url() -> str:
    """Get database URL, preferring environment variable over config."""
    # For local development, use local-data path if the file exists
    # Check multiple possible locations for the database
    possible_paths = [
        "local-data/borgitory.db",  # From project root
        "../../local-data/borgitory.db",  # From src/borgitory/
        os.path.join(os.getcwd(), "local-data", "borgitory.db"),  # Absolute from cwd
    ]

    for local_db_path in possible_paths:
        if os.path.exists(local_db_path):
            # Convert to absolute path for consistency
            abs_path = os.path.abspath(local_db_path)
            return f"sqlite:///{abs_path}"

    # Otherwise use environment variable or default config
    return os.getenv("DATABASE_URL", DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,  # Required for SQLite ALTER operations
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Override the sqlalchemy.url in alembic.ini with our dynamic URL
    config.set_main_option("sqlalchemy.url", get_database_url())

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=True,  # Required for SQLite ALTER operations
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
