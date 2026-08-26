"""tgstat-opensource — FastAPI приложение (полноценный аналог tgstat.ru)

Эндпоинты API:
- GET /api/channels                     — список каналов
- GET /api/channels/{id}                — детали канала
- GET /api/channels/{id}/stats          — статистика по дням
- GET /api/channels/{id}/subscribers    — история подписчиков
- GET /api/channels/{id}/posts          — посты канала
- GET /api/rankings                     — рейтинг каналов
- GET /api/search/mentions              — поиск упоминаний
- GET /api/search                       — поиск каналов
- GET /api/search/posts                 — поиск постов
- GET /api/top/posts                    — топ публикаций
- GET /api/categories                   — категории с количеством
- POST /api/collect                     — запустить сбор

Страницы (HTML):
- GET /                                 — главная
- GET /catalog                          — каталог каналов
- GET /channel/{id}                     — страница канала
- GET /top                              — рейтинги
- GET /search                           — поиск
"""

import os
import logging
from datetime import datetime, date, timedelta
from typing import Optional
from pathlib import Path
from secrets import compare_digest

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy import select, func

from db import get_database_url, init_db, get_session_factory
from db.schema import Channel, ChannelStats, Post, Mention, DailyStats, create_async_engine_from_url

# ── Эмуляция (демо-данные, пока БД пуста) ─────────────────────────
from api.emulation import (
    generate_all_channels,
    generate_channel_detail,
    generate_daily_stats,
    generate_subscribers,
    generate_posts,
    generate_rankings,
    search_channels_emulated,
    search_posts_emulated,
    search_mentions_emulated,
    generate_top_posts,
    CATEGORY_LIST,
)

load_dotenv()

# ── Пути ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
WEB_DIR = BASE_DIR / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

logger = logging.getLogger("tgstat.api")

app = FastAPI(title="tgstat-opensource", version="0.2.0")

# ── Static files ────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
    category: Optional[str] = None
    language: Optional[str] = None
    country: Optional[str] = None

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
    participants_count: Optional[int] = None

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
    category: Optional[str] = None


# ── Database helpers ────────────────────────────────────────────────

def _db_url():
    return get_database_url()


async def _count_rows(session, model):
    result = await session.execute(select(func.count(model.id)))
    return result.scalar() or 0


async def _get_session():
    """Context-manager для сессии БД."""
    db_url = _db_url()
    engine = create_async_engine_from_url(db_url)
    return get_session_factory(engine)(), engine


# ── Эмуляция (проверка пустоты БД) ─────────────────────────────────
# Если в таблице channels 0 строк — возвращаем демо-данные.
# Как только появятся реальные данные — эмуляция отключается автоматически.
# Для принудительного отключения: EmulationCheck.force_real = True


class EmulationCheck:
    _cache: Optional[bool] = None
    _cache_time: Optional[datetime] = None
    force_real = False  # установите True, чтобы отключить эмуляцию

    @classmethod
    async def should_emulate(cls) -> bool:
        if cls.force_real:
            return False
        if cls._cache is not None and cls._cache_time and datetime.utcnow() - cls._cache_time < timedelta(seconds=30):
            return cls._cache
        try:
            db_url = _db_url()
            engine = create_async_engine_from_url(db_url)
            async with get_session_factory(engine)() as session:
                count = await _count_rows(session, Channel)
            await engine.dispose()
            empty = count == 0
            cls._cache = empty
            cls._cache_time = datetime.utcnow()
            return empty
        except Exception as e:
            logger.exception("Не удалось проверить БД для эмуляции: %s", e)
            raise HTTPException(status_code=503, detail="Database unavailable")

    @classmethod
    def invalidate_cache(cls):
        cls._cache = None
        cls._cache_time = None


def _require_collect_token(
    x_api_token: Optional[str] = None,
    authorization: Optional[str] = None,
) -> None:
    """Защита POST /api/collect: нужен COLLECT_API_TOKEN в env."""
    expected = os.getenv("COLLECT_API_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail="Сбор через API отключён. Задайте COLLECT_API_TOKEN в .env",
        )
    provided = (x_api_token or "").strip()
    if not provided and authorization:
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()
        else:
            provided = auth
    if not provided or not compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Неверный или отсутствующий токен")


# ── Эндпоинты API ──────────────────────────────────────────────────

@app.get("/api/channels", response_model=list[ChannelOut])
async def list_channels():
    """Список отслеживаемых каналов."""
    if await EmulationCheck.should_emulate():
        channels = generate_all_channels()
        return [ChannelOut(**ch) for ch in channels]

    db_url = _db_url()
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
    if await EmulationCheck.should_emulate():
        ch = generate_channel_detail(channel_id)
        if not ch:
            raise HTTPException(404, "Канал не найден")
        return ChannelOut(**ch)

    db_url = _db_url()
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
    if await EmulationCheck.should_emulate():
        stats = generate_daily_stats(channel_id, days)
        return [DailyStatsOut(**s) for s in stats]

    db_url = _db_url()
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


@app.get("/api/channels/{channel_id}/subscribers")
async def get_channel_subscribers(channel_id: int, days: int = Query(30, ge=1, le=365)):
    """История подписчиков канала (для графика роста)."""
    if await EmulationCheck.should_emulate():
        return generate_subscribers(channel_id, days)

    db_url = _db_url()
    engine = create_async_engine_from_url(db_url)
    cutoff = date.today() - timedelta(days=days)
    async with get_session_factory(engine)() as session:
        result = await session.execute(
            select(ChannelStats)
            .where(
                ChannelStats.channel_id == channel_id,
                ChannelStats.date >= cutoff,
            )
            .order_by(ChannelStats.date.asc())
        )
        rows = result.scalars().all()
    await engine.dispose()
    return [
        {
            "date": r.date.isoformat(),
            "participants_count": r.participants_count,
            "sources_total": r.sources_total,
            "delta": r._add,
        }
        for r in rows
    ]


@app.get("/api/channels/{channel_id}/posts", response_model=list[PostOut])
async def get_channel_posts(channel_id: int, limit: int = Query(50, ge=1, le=500)):
    """Последние посты канала."""
    if await EmulationCheck.should_emulate():
        posts = generate_posts(channel_id, limit)
        return [PostOut(**p) for p in posts]

    db_url = _db_url()
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
async def get_rankings(sort_by: str = Query("avg_views", pattern="^(avg_views|avg_er|posts_7d|participants_count)$")):
    """Рейтинг каналов."""
    if await EmulationCheck.should_emulate():
        rankings = generate_rankings(sort_by)
        return [RankingItem(**r) for r in rankings]

    db_url = _db_url()
    engine = create_async_engine_from_url(db_url)
    cutoff = datetime.utcnow() - timedelta(days=7)
    async with get_session_factory(engine)() as session:
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

    reverse = True
    rows.sort(key=lambda r: getattr(r, sort_by) or 0, reverse=reverse)
    return rows


@app.get("/api/search/mentions")
async def search_mentions(query: str = Query(..., min_length=2), limit: int = Query(50, le=200)):
    """Поиск упоминаний канала по тексту."""
    if await EmulationCheck.should_emulate():
        return search_mentions_emulated(query, limit)

    db_url = _db_url()
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


# ── НОВЫЕ ЭНДПТОИНТЫ ──────────────────────────────────────────────

@app.get("/api/search")
async def search_channels(q: str = Query(..., min_length=1)):
    """Поиск каналов по названию/username/описанию."""
    if await EmulationCheck.should_emulate():
        return search_channels_emulated(q)

    db_url = _db_url()
    engine = create_async_engine_from_url(db_url)
    async with get_session_factory(engine)() as session:
        result = await session.execute(
            select(Channel).where(
                (Channel.title.ilike(f"%{q}%")) |
                (Channel.username.ilike(f"%{q}%")) |
                (Channel.description.ilike(f"%{q}%"))
            ).limit(50)
        )
        channels = result.scalars().all()
    await engine.dispose()

    return [
        {
            "id": ch.id,
            "username": ch.username,
            "title": ch.title,
            "description": ch.description,
            "participants_count": ch.participants_count,
        }
        for ch in channels
    ]


@app.get("/api/search/posts")
async def search_posts(q: str = Query(..., min_length=1), limit: int = Query(20, le=100)):
    """Поиск постов по тексту."""
    if await EmulationCheck.should_emulate():
        return search_posts_emulated(q, limit)

    db_url = _db_url()
    engine = create_async_engine_from_url(db_url)
    async with get_session_factory(engine)() as session:
        result = await session.execute(
            select(Post)
            .where(Post.text.ilike(f"%{q}%"))
            .order_by(Post.date.desc())
            .limit(limit)
        )
        posts = result.scalars().all()

        out = []
        for p in posts:
            ch = await session.get(Channel, p.channel_id)
            out.append({
                "id": p.id,
                "channel_id": p.channel_id,
                "channel_username": ch.username if ch else None,
                "channel_title": ch.title if ch else None,
                "date": p.date,
                "text": p.text[:300] if p.text else None,
                "views": p.views,
                "forwards": p.forwards,
            })
    await engine.dispose()
    return out


@app.get("/api/top/posts")
async def top_posts(limit: int = Query(10, ge=1, le=100)):
    """Топ публикаций по просмотрам."""
    if await EmulationCheck.should_emulate():
        posts = generate_top_posts(limit)
        return posts

    db_url = _db_url()
    engine = create_async_engine_from_url(db_url)
    async with get_session_factory(engine)() as session:
        result = await session.execute(
            select(Post)
            .order_by(Post.views.desc().nullslast())
            .limit(limit)
        )
        posts = result.scalars().all()

        out = []
        for p in posts:
            ch = await session.get(Channel, p.channel_id)
            out.append({
                "id": p.id,
                "channel_id": p.channel_id,
                "channel_username": ch.username if ch else None,
                "channel_title": ch.title if ch else None,
                "date": p.date,
                "text": p.text[:300] if p.text else None,
                "views": p.views,
                "forwards": p.forwards,
                "has_media": p.has_media,
            })
    await engine.dispose()
    return out


@app.get("/api/categories")
async def list_categories():
    """Список категорий с количеством каналов в каждой."""
    if await EmulationCheck.should_emulate():
        channels = generate_all_channels()
        cat_counts = {}
        for ch in channels:
            cat = ch.get("category", "Разное")
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        icons = {
            "Новости и СМИ": "📰", "Развлечения": "🎭", "Технологии": "💻",
            "Бизнес": "💼", "Спорт": "⚽", "Образование": "📚",
            "Здоровье": "💊", "Путешествия": "✈️", "Стиль и мода": "👗",
            "Авто": "🚗",
        }
        return [
            {"name": cat, "count": cat_counts.get(cat, 0), "icon": icons.get(cat, "📂")}
            for cat in CATEGORY_LIST if cat in cat_counts
        ]

    db_url = _db_url()
    engine = create_async_engine_from_url(db_url)
    async with get_session_factory(engine)() as session:
        result = await session.execute(
            select(Channel.id)  # пока категории нет в схеме — все в "Другое"
        )
        count = len(result.scalars().all())
    await engine.dispose()
    return [{"name": "Другое", "count": count, "icon": "📂"}]


@app.post("/api/collect")
async def trigger_collect(
    channel_username: str,
    x_api_token: Optional[str] = Header(default=None, alias="X-API-Token"),
    authorization: Optional[str] = Header(default=None),
):
    """Запустить сбор данных для канала (требует COLLECT_API_TOKEN)."""
    _require_collect_token(x_api_token, authorization)

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

        db_url = _db_url()
        engine = create_async_engine_from_url(db_url)
        async with get_session_factory(engine)() as session:
            await collector.add_channel(entity, session)
            await session.commit()
        await engine.dispose()

        await collector.collect_posts(entity.id, limit=200, offset_days=7)
        await collector.calculate_daily_stats(entity.id)
        EmulationCheck.invalidate_cache()
        return {"status": "ok", "channel": entity.username, "title": entity.title}
    finally:
        await collector.stop()


# ── СТРАНИЦЫ (HTML) ───────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница."""
    return templates.TemplateResponse(
        request,
        "index.html",
        {"active_page": "index"},
    )


@app.get("/catalog", response_class=HTMLResponse)
async def catalog(request: Request):
    """Каталог каналов."""
    return templates.TemplateResponse(
        request,
        "catalog.html",
        {"active_page": "catalog"},
    )


@app.get("/channel/{channel_id}", response_class=HTMLResponse)
async def channel_page(request: Request, channel_id: int):
    """Страница канала."""
    return templates.TemplateResponse(
        request,
        "channel.html",
        {"channel_id": channel_id, "active_page": ""},
    )


@app.get("/top", response_class=HTMLResponse)
async def top_page(request: Request):
    """Топы / Рейтинги."""
    return templates.TemplateResponse(
        request,
        "top.html",
        {"active_page": "top"},
    )


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    """Поиск по каналам и постам."""
    return templates.TemplateResponse(
        request,
        "search.html",
        {"query": q, "active_page": ""},
    )


# ── Fallback для старых ссылок на dashboard.html ──────────────────
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_redirect():
    from pathlib import Path
    web_dir = Path(__file__).parent.parent / "web"
    index_path = web_dir / "dashboard.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>tgstat-opensource</h1><p>Используйте / для нового интерфейса</p>")


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host=host, port=port)