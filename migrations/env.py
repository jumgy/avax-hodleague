from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import Base
from models.rarity_models import *
from models.card_models import *
from models.token_models import *
from models.tournament_models import *
from models.user_models import *
from models.pack_models import *
from models.pack_probability_models import *
from models.user_pack_models import *
from models.user_card_models import *
from models.tournament_deck_models import *
from models.reward_models import *
from models.audit_models import *

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def get_url():
    # Получаем URL из переменных среды
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        # Заменяем asyncpg на psycopg2 для синхронной работы alembic
        if "postgresql+asyncpg://" in db_url:
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        return db_url
    
    # Fallback для локальной разработки
    user = os.getenv("POSTGRES_USER", "fantasy_user")
    password = os.getenv("POSTGRES_PASSWORD", "fantasy_pass")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "fantasy_db")
    
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"

def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()