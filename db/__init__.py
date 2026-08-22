"""tgstat-opensource — Инициализация БД (асинхронная)"""

import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from .schema import Base, Channel, Post, Mention, DailyStats

load_dotenv()

DEFAULT_URL = "sqlite+aiosqlite:///data/tgstat.db"


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_URL)


async def init_db(engine=None):
    """Создать таблицы, если их нет."""
    url = get_database_url()
    engine = engine or create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def get_session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)