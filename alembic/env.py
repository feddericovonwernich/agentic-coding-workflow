"""
Alembic environment configuration for database migrations.

Handles both online and offline migration modes with proper async support
and integration with the application's database configuration.
"""

import asyncio
import os
from logging.config import fileConfig
from typing import Union

from sqlalchemy import pool, engine_from_config
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Import application configuration
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    from src.database.config import get_database_config
except ImportError:
    # Fallback if running in isolated environment
    def get_database_config():
        class FallbackConfig:
            def get_alembic_url(self):
                return os.getenv(
                    'DATABASE_URL',
                    'postgresql://postgres:password@localhost/agentic_workflow'
                ).replace('+asyncpg', '')
        return FallbackConfig()

# This is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object here for 'autogenerate' support
# For now, we'll set target_metadata to None since we don't have models yet
# In future tasks, this will be imported from the models module
target_metadata = None

# Other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_database_url() -> str:
    """
    Get database URL for migrations.
    
    Prioritizes environment variable, then application config, then alembic.ini.
    Returns sync URL (without +asyncpg) for Alembic compatibility.
    """
    # Check environment variable first
    env_url = os.getenv('DATABASE_URL')
    if env_url:
        # Ensure sync driver for Alembic
        return env_url.replace('+asyncpg', '')
    
    # Try application configuration
    try:
        app_config = get_database_config()
        return app_config.get_alembic_url()
    except Exception:
        pass
    
    # Fallback to alembic.ini configuration
    return config.get_main_option('sqlalchemy.url')


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

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
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations with the provided connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,  # For better SQLite compatibility if needed
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in async 'online' mode.
    
    Creates an async engine and runs migrations within an async context.
    """
    # Get database URL and ensure it's async-compatible
    database_url = get_database_url()
    if '+asyncpg' not in database_url:
        database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://')
    
    # Create async engine configuration
    configuration = config.get_section(config.config_ini_section, {})
    configuration['sqlalchemy.url'] = database_url
    
    # Create async engine
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a connection
    with the context. We support both sync and async modes.
    """
    # Check if we should run in async mode
    if os.getenv('ALEMBIC_ASYNC', 'true').lower() == 'true':
        asyncio.run(run_async_migrations())
    else:
        # Synchronous mode fallback
        database_url = get_database_url()
        
        configuration = config.get_section(config.config_ini_section, {})
        configuration['sqlalchemy.url'] = database_url
        
        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            do_run_migrations(connection)


# Determine run mode and execute
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()