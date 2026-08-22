"""tgstat-opensource — Коллектор данных с Telegram (на базе Telethon)"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import Channel as TLChannel, Message
from dotenv import load_dotenv

from db import get_database_url, init_db, get_session_factory
from db.schema import Channel, Post, Mention, DailyStats, create_async_engine_from_url

load_dotenv()
logger = logging.getLogger("tgstat.collector")


class Collector:
    """Собирает данные из Telegram и сохраняет в БД."""

    def __init__(self, api_id: str, api_hash: str, phone: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.client = TelegramClient(f"session_{phone}", api_id, api_hash)

    async def start(self) -> bool:
        """Подключиться к Telegram."""
        try:
            await self.client.start(phone=self.phone)
            me = await self.client.get_me()
            logger.info("✅ Подключён как %s (@%s)", me.first_name, me.username)
            return True
        except SessionPasswordNeededError:
            logger.error("❌ Требуется 2FA. Запустите вручную для ввода пароля.")
            return False
        except Exception as e:
            logger.error("❌ Ошибка подключения: %s", e)
            return False

    async def stop(self):
        await self.client.disconnect()
        logger.info("🔌 Соединение закрыто")

    # ── Работа с каналами ──────────────────────────────────────────

    async def resolve_channel(self, identifier: str) -> Optional[TLChannel]:
        """Превратить username/ссылку/id в объект канала."""
        try:
            entity = await self.client.get_entity(identifier)
            if isinstance(entity, TLChannel):
                return entity
            logger.warning("«%s» — не канал, а %s", identifier, type(entity).__name__)
        except Exception as e:
            logger.warning("Не удалось найти канал «%s»: %s", identifier, e)
        return None

    async def add_channel(self, channel: TLChannel, session) -> Channel:
        """Добавить канал в БД или обновить информацию."""
        existing = await session.get(Channel, channel.id)
        if existing:
            existing.title = channel.title
            existing.username = channel.username
            existing.participants_count = getattr(channel, "participants_count", None)
            existing.last_scraped = datetime.utcnow()
            return existing

        db_channel = Channel(
            id=channel.id,
            username=channel.username,
            title=channel.title,
            description=getattr(channel, "about", None),
            participants_count=getattr(channel, "participants_count", None),
            first_seen=datetime.utcnow(),
        )
        session.add(db_channel)
        return db_channel

    # ── Сбор сообщений ─────────────────────────────────────────────

    async def collect_posts(self, channel_id: int, limit: int = 200,
                            offset_days: int = 7) -> list[Post]:
        """Собрать посты из канала и сохранить в БД."""
        entity = await self.client.get_entity(channel_id)
        posts = []
        cutoff = datetime.utcnow() - timedelta(days=offset_days)

        db_url = get_database_url()
        engine = create_async_engine_from_url(db_url)
        async with get_session_factory(engine)() as session:
            async for message in self.client.iter_messages(entity, limit=limit):
                if message.date < cutoff:
                    break
                if not isinstance(message, Message):
                    continue

                # Проверяем, есть ли уже
                existing = await session.get(Post, message.id)
                if existing:
                    continue

                post = Post(
                    id=message.id,
                    channel_id=channel_id,
                    date=message.date,
                    text=message.text or "",
                    views=getattr(message, "views", None),
                    forwards=getattr(message, "forwards", None),
                    has_media=bool(message.media),
                    media_type=self._media_type(message),
                )
                session.add(post)
                posts.append(post)

            await session.commit()
            logger.info("📥 Собрано %d новых постов из канала #%d", len(posts), channel_id)

        await engine.dispose()
        return posts

    # ── Поиск упоминаний ────────────────────────────────────────────

    async def find_mentions(self, target_username: str, limit: int = 1000) -> list:
        """Поиск сообщений, упоминающих канал (по username)."""
        mentions = []
        db_url = get_database_url()
        engine = create_async_engine_from_url(db_url)
        async with get_session_factory(engine)() as session:
            async for dialog in self.client.iter_dialogs():
                if not isinstance(dialog.entity, TLChannel):
                    continue
                if dialog.entity.username and dialog.entity.username.lower() == target_username.lower():
                    continue  # пропускаем сам канал

                async for msg in self.client.iter_messages(dialog.entity, limit=limit // 50):
                    if not msg.text:
                        continue
                    if f"@{target_username}" in msg.text or f"t.me/{target_username}" in msg.text:
                        mention = Mention(
                            target_channel_id=0,  # заполним позже
                            source_channel_id=dialog.id,
                            source_post_id=msg.id,
                            date=msg.date,
                            text=msg.text[:500],
                            mention_type="link",
                        )
                        session.add(mention)
                        mentions.append(mention)

            await session.commit()
            logger.info("🔗 Найдено %d упоминаний @%s", len(mentions), target_username)

        await engine.dispose()
        return mentions

    # ── Расчёт дневной статистики ───────────────────────────────────

    async def calculate_daily_stats(self, channel_id: int):
        """Посчитать дневную статистику за последние N дней."""
        db_url = get_database_url()
        engine = create_async_engine_from_url(db_url)
        async with get_session_factory(engine)() as session:
            channel_db = await session.get(Channel, channel_id)
            if not channel_db:
                logger.warning("Канал #%d не найден в БД", channel_id)
                return

            subscribers = channel_db.participants_count or 0

            from sqlalchemy import cast, Date

            # Получаем все дни, за которые есть посты
            result = await session.execute(
                select(
                    cast(Post.date, Date).label("day"),
                    func.count(Post.id).label("cnt"),
                    func.sum(Post.views).label("total_views"),
                    func.avg(Post.views).label("avg_views"),
                    func.sum(Post.forwards).label("total_forwards"),
                    func.avg(Post.forwards).label("avg_forwards"),
                )
                .where(Post.channel_id == channel_id)
                .group_by(cast(Post.date, Date))
            )

            for row in result:
                existing = await session.execute(
                    select(DailyStats).where(
                        DailyStats.channel_id == channel_id,
                        cast(DailyStats.date, Date) == row.day
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                er = None
                if subscribers > 0 and row.total_views:
                    er = (row.total_views + (row.total_forwards or 0)) / subscribers * 100

                ds = DailyStats(
                    channel_id=channel_id,
                    date=row.day,
                    posts_count=row.cnt,
                    total_views=row.total_views or 0,
                    avg_views=row.avg_views,
                    total_forwards=row.total_forwards or 0,
                    avg_forwards=row.avg_forwards,
                    engagement_rate=round(er, 2) if er else None,
                )
                session.add(ds)

            await session.commit()
            logger.info("📊 Статистика за %d дней обновлена для канала #%d", result.rowcount, channel_id)

        await engine.dispose()

    # ── Хелперы ────────────────────────────────────────────────────

    @staticmethod
    def _media_type(message) -> Optional[str]:
        if message.photo:
            return "photo"
        if message.video:
            return "video"
        if message.document:
            return "document"
        if message.audio:
            return "audio"
        if message.voice:
            return "voice"
        if message.sticker:
            return "sticker"
        if message.poll:
            return "poll"
        return None


# ── CLI entry point ──────────────────────────────────────────────────

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    phone = os.getenv("TELEGRAM_PHONE")

    if not all([api_id, api_hash, phone]):
        print("❌ Заполните .env: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE")
        return

    # Инициализация БД
    await init_db()
    logger.info("🗄️  База данных готова")

    collector = Collector(api_id, api_hash, phone)
    if not await collector.start():
        return

    try:
        chats = input("\nUsername каналов через запятую (например: @channel1, @channel2): ").strip()
        usernames = [c.strip().lstrip("@") for c in chats.split(",") if c.strip()]

        for username in usernames:
            entity = await collector.resolve_channel(username)
            if entity:
                logger.info("📡 Канал: %s (%s)", entity.title, entity.username)
                db_url = get_database_url()
                engine = create_async_engine_from_url(db_url)
                async with get_session_factory(engine)() as session:
                    await collector.add_channel(entity, session)
                    await session.commit()
                await engine.dispose()

                await collector.collect_posts(entity.id, limit=200, offset_days=7)
                await collector.calculate_daily_stats(entity.id)

    finally:
        await collector.stop()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())