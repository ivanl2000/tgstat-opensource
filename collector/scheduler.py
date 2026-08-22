"""tgstat-opensource — Планировщик сбора данных (запускать фоном)"""

import os
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
import yaml

from collector import Collector
from db import get_database_url, init_db, get_session_factory
from db.schema import Channel, create_async_engine_from_url

load_dotenv()
logger = logging.getLogger("tgstat.scheduler")


async def run_collection(collector: Collector, channel_username: str):
    """Собрать данные для одного канала."""
    entity = await collector.resolve_channel(channel_username)
    if not entity:
        logger.warning("⚠️  Канал @%s не найден, пропускаем", channel_username)
        return

    db_url = get_database_url()
    engine = create_async_engine_from_url(db_url)
    async with get_session_factory(engine)() as session:
        await collector.add_channel(entity, session)
        await session.commit()
    await engine.dispose()

    logger.info("📡 %s: сбор постов…", entity.title)
    await collector.collect_posts(entity.id, limit=200, offset_days=7)

    logger.info("📊 %s: расчёт статистики…", entity.title)
    await collector.calculate_daily_stats(entity.id)

    logger.info("✅ %s: готово", entity.title)


async def scheduler_loop():
    """Бесконечный цикл: собирает данные по расписанию."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.local.yaml")
    if not os.path.exists(config_path):
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    api_id = os.getenv("TELEGRAM_API_ID") or cfg.get("telegram", {}).get("api_id")
    api_hash = os.getenv("TELEGRAM_API_HASH") or cfg.get("telegram", {}).get("api_hash")
    phone = os.getenv("TELEGRAM_PHONE") or cfg.get("telegram", {}).get("phone")

    if not all([api_id, api_hash, phone]):
        logger.error("❌ Telegram API не настроен")
        return

    channels = cfg.get("collector", {}).get("channels", [])
    if not channels:
        logger.warning("⚠️  Каналы не указаны в конфиге (collector.channels)")
        # Загружаем из БД
        db_url = get_database_url()
        engine = create_async_engine_from_url(db_url)
        async with get_session_factory(engine)() as session:
            result = await session.execute(select(Channel).where(Channel.is_active == True))
            channels = [f"@{ch.username}" for ch in result.scalars().all() if ch.username]
        await engine.dispose()

    interval = cfg.get("collector", {}).get("fetch_interval_minutes", 60)
    messages_per_run = cfg.get("collector", {}).get("messages_per_run", 200)
    history_depth = cfg.get("collector", {}).get("history_depth_days", 7)

    await init_db()
    collector = Collector(api_id, api_hash, phone)
    if not await collector.start():
        return

    try:
        while True:
            start = datetime.utcnow()
            logger.info("🔄 Запуск сбора для %d каналов…", len(channels))

            for ch_username in channels:
                try:
                    await run_collection(collector, ch_username.strip())
                except Exception as e:
                    logger.error("❌ Ошибка при сборе %s: %s", ch_username, e)

            elapsed = (datetime.utcnow() - start).total_seconds()
            logger.info("⏱️  Сбор завершён за %.1f сек. Следующий через %d мин.",
                        elapsed, interval)
            await asyncio.sleep(interval * 60)
    finally:
        await collector.stop()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    asyncio.run(scheduler_loop())


if __name__ == "__main__":
    main()