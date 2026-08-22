"""tgstat-opensource — FastAPI приложение

Эндпоинты:
- GET  /api/channels            — список каналов
- GET  /api/channels/{id}       — детали канала
- GET  /api/channels/{id}/stats — статистика по дням
- GET  /api/channels/{id}/posts — посты канала
- GET  /api/rankings            — рейтинг каналов
- GET  /api/search/mentions     — поиск упоминаний
- POST /api/collect             — запустить сбор вручную
"""

import os
import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_database_url, init_db, get_session_factory
from db.schema import Channel, Post, Mention, DailyStats, create_async_engine_from_url

load_dotenv()
logger = logging.getLogger("tgstat.api")

app = FastAPI(title="tgstat-opensource", version="0.1.0")


# ── Lifespan ────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("🗄️  База данных инициализирована")


# ── Pydantic схемы ─────────────────────────────────────────────────

class ChannelOut(BaseModel):
    id: int
    username: Optional[str]
    title: Optional[str]
    description: Optional[str]
    participants_count: Optional[int]
    first_seen: Optional[datetime]
    last_scraped: Optional[datetime]
    posts_count: int = 0

    class Config:
        from_attributes = True


class PostOut(BaseModel):
    id: int
    channel_id: int
    date: datetime
    text: Optional[str]
    views: Optional[int]
    forwards: Optional[int]
    has_media: bool
    media_type: Optional[str]

    class Config:
        from_attributes = True


class DailyStatsOut(BaseModel):
    date: date
    posts_count: int
    total_views: int
    avg_views: Optional[float]
    total_forwards: int
    avg_forwards: Optional[float]
    mentions_count: int
    engagement_rate: Optional[float]

    class Config:
        from_attributes = True


class RankingItem(BaseModel):
    channel_id: int
    username: Optional[str]
    title: Optional[str]
    participants_count: Optional[int]
    avg_views: float
    avg_er: Optional[float]
    posts_7d: int


# ── Эндпоинты ──────────────────────────────────────────────────────

@app.get("/api/channels", response_model=list[ChannelOut])
async def list_channels():
    """Список отслеживаемых каналов."""
    db_url = get_database_url()
    engine = create_async_engine_from_url(db_url)
    async with get_session_factory(engine)() as session:
        result = await session.execute(
            select(Channel).order_by(Channel.last_scraped.desc().nullslast())
        )
        channels = result.scalars().all()

        out = []
        for ch in channels:
            cnt = await session.execute(
                select(func.count(Post.id)).where(Post.channel_id == ch.id)
            )
            posts_count = cnt.scalar() or 0
            out.append(ChannelOut(
                **{k: getattr(ch, k) for k in
                   ["id", "username", "title", "description", "participants_count",
                    "first_seen", "last_scraped"]},
                posts_count=posts_count
            ))

    await engine.dispose()
    return out


@app.get("/api/channels/{channel_id}", response_model=ChannelOut)
async def get_channel(channel_id: int):
    """Детали канала."""
    db_url = get_database_url()
    engine = create_async_engine_from_url(db_url)
    async with get_session_factory(engine)() as session:
        ch = await session.get(Channel, channel_id)
        if not ch:
            raise HTTPException(404, "Канал не найден")
        cnt = await session.execute(
            select(func.count(Post.id)).where(Post.channel_id == ch.id)
        )
        posts_count = cnt.scalar() or 0
    await engine.dispose()
    return ChannelOut(
        **{k: getattr(ch, k) for k in
           ["id", "username", "title", "description", "participants_count",
            "first_seen", "last_scraped"]},
        posts_count=posts_count
    )


@app.get("/api/channels/{channel_id}/stats", response_model=list[DailyStatsOut])
async def get_channel_stats(channel_id: int, days: int = Query(30, ge=1, le=365)):
    """Статистика канала по дням."""
    db_url = get_database_url()
    engine = create_async_engine_from_url(db_url)
    cutoff = datetime.utcnow() - timedelta(days=days)
    async with get_session_factory(engine)() as session:
        result = await session.execute(
            select(DailyStats)
            .where(DailyStats.channel_id == channel_id, DailyStats.date >= cutoff)
            .order_by(DailyStats.date.asc())
        )
        stats = result.scalars().all()
    await engine.dispose()
    return [DailyStatsOut.model_validate(s) for s in stats]


@app.get("/api/channels/{channel_id}/posts", response_model=list[PostOut])
async def get_channel_posts(channel_id: int, limit: int = Query(50, ge=1, le=500)):
    """Последние посты канала."""
    db_url = get_database_url()
    engine = create_async_engine_from_url(db_url)
    async with get_session_factory(engine)() as session:
        result = await session.execute(
            select(Post)
            .where(Post.channel_id == channel_id)
            .order_by(Post.date.desc())
            .limit(limit)
        )
        posts = result.scalars().all()
    await engine.dispose()
    return [PostOut.model_validate(p) for p in posts]


@app.get("/api/rankings", response_model=list[RankingItem])
async def get_rankings(sort_by: str = Query("avg_views", regex="^(avg_views|avg_er|posts_7d|participants_count)$")):
    """Рейтинг каналов."""
    db_url = get_database_url()
    engine = create_async_engine_from_url(db_url)
    cutoff = datetime.utcnow() - timedelta(days=7)
    async with get_session_factory(engine)() as session:
        # Средние просмотры за 7 дней
        stats = await session.execute(
            select(
                DailyStats.channel_id,
                func.avg(DailyStats.avg_views).label("avg_views"),
                func.avg(DailyStats.engagement_rate).label("avg_er"),
                func.sum(DailyStats.posts_count).label("posts_7d"),
            )
            .where(DailyStats.date >= cutoff)
            .group_by(DailyStats.channel_id)
            .order_by(func.avg(DailyStats.avg_views).desc().nullslast())
            .limit(100)
        )

        rows = []
        for row in stats:
            ch = await session.get(Channel, row.channel_id)
            rows.append(RankingItem(
                channel_id=row.channel_id,
                username=ch.username if ch else None,
                title=ch.title if ch else None,
                participants_count=ch.participants_count if ch else None,
                avg_views=round(row.avg_views or 0, 1),
                avg_er=round(row.avg_er, 2) if row.avg_er else None,
                posts_7d=row.posts_7d or 0,
            ))

    await engine.dispose()

    # Сортируем
    reverse = True
    rows.sort(key=lambda r: getattr(r, sort_by) or 0, reverse=reverse)
    return rows


@app.get("/api/search/mentions")
async def search_mentions(query: str = Query(..., min_length=2), limit: int = Query(50, le=200)):
    """Поиск упоминаний канала по тексту."""
    db_url = get_database_url()
    engine = create_async_engine_from_url(db_url)
    async with get_session_factory(engine)() as session:
        result = await session.execute(
            select(Mention)
            .where(Mention.text.ilike(f"%{query}%"))
            .order_by(Mention.date.desc())
            .limit(limit)
        )
        mentions = result.scalars().all()
    await engine.dispose()
    return [
        {
            "id": m.id,
            "target_channel_id": m.target_channel_id,
            "source_channel_id": m.source_channel_id,
            "date": m.date.isoformat(),
            "text": m.text[:300] if m.text else None,
            "mention_type": m.mention_type,
        }
        for m in mentions
    ]


@app.post("/api/collect")
async def trigger_collect(channel_username: str):
    """Запустить сбор данных для канала (асинхронно)."""
    from collector import Collector
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    phone = os.getenv("TELEGRAM_PHONE")

    if not all([api_id, api_hash, phone]):
        raise HTTPException(400, "Telegram API не настроен. Заполните .env")

    collector = Collector(api_id, api_hash, phone)
    if not await collector.start():
        raise HTTPException(500, "Не удалось подключиться к Telegram")

    try:
        entity = await collector.resolve_channel(channel_username)
        if not entity:
            raise HTTPException(404, f"Канал @{channel_username} не найден")

        db_url = get_database_url()
        engine = create_async_engine_from_url(db_url)
        async with get_session_factory(engine)() as session:
            await collector.add_channel(entity, session)
            await session.commit()
        await engine.dispose()

        await collector.collect_posts(entity.id, limit=200, offset_days=7)
        await collector.calculate_daily_stats(entity.id)
        return {"status": "ok", "channel": entity.username, "title": entity.title}
    finally:
        await collector.stop()


# ── Веб-интерфейс ──────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Главная страница — дашборд."""
    from pathlib import Path
    web_dir = Path(__file__).parent.parent / "web"
    index_path = web_dir / "dashboard.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>tgstat-opensource</h1><p>Дашборд скоро будет</p>")


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host=host, port=port)