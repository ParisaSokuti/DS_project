from alembic import context
from sqlalchemy import engine_from_config, pool
from logging.config import fileConfig
import logging
import os
import sys

# Add the parent directory to the path to import models
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Import your SQLAlchemy models here
try:
    from backend.database.models import Base
    target_metadata = Base.metadata
except ImportError:
    # Fallback if models are not available
    target_metadata = None

# Alembic Config object
config = context.config

# Interpret the config file for logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger('alembic.env')

def get_url():
    """Get database URL from environment or config"""
    url = os.getenv('DATABASE_URL')
    if url:
        return url
    return config.get_main_option("sqlalchemy.url")

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,  # Enable batch operations for better compatibility
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section)
    configuration['sqlalchemy.url'] = get_url()
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=True,
            transaction_per_migration=True,  # Each migration in its own transaction
            include_object=include_object,  # Custom filter function
        )

        with context.begin_transaction():
            context.run_migrations()

def include_object(object, name, type_, reflected, compare_to):
    """
    Filter function to include/exclude objects from autogenerate
    """
    # Exclude temporary tables
    if type_ == "table" and name.startswith("temp_"):
        return False
    
    # Exclude alembic version table
    if type_ == "table" and name == "alembic_version":
        return False
    
    # Include everything else
    return True

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
