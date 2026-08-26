"""tgstat-opensource — Инициализация БД (асинхронная)"""

import os
import re
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from .schema import Base, Channel, ChannelStats, Post, Mention, DailyStats

load_dotenv()

DEFAULT_URL = "sqlite+aiosqlite:///data/tgstat.db"


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_URL)


def _ensure_sqlite_dir(url: str) -> None:
    """Создать каталог для файла SQLite, если URL указывает на локальный путь."""
    match = re.match(r"sqlite(?:\+\w+)?:///(.+)", url)
    if not match:
        return
    db_path = Path(match.group(1))
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)


async def init_db(engine=None):
    """Создать таблицы, если их нет."""
    url = get_database_url()
    _ensure_sqlite_dir(url)
    engine = engine or create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def get_session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)