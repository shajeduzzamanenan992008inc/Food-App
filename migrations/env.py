from logging.config import fileConfig

from alembic import context
from flask import current_app


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

migrate_config = current_app.extensions["migrate"]
target_metadata = migrate_config.db.metadata
config.set_main_option("sqlalchemy.url", str(migrate_config.db.engine.url).replace("%", "%%"))


def run_migrations_offline():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **migrate_config.configure_args,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with migrate_config.db.engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            **migrate_config.configure_args,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
