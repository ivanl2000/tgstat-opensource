"""
Слой эмуляции данных для tgstat-opensource.

Пока Telegram API недоступен и БД пуста — возвращаем сгенерированные
демо-данные, чтобы интерфейс выглядел живым.

Для ОТКЛЮЧЕНИЯ эмуляции и перехода на реальные данные:
  - В файле api/main.py импортируйте USE_EMULATION = False
  - Или просто добавьте реальные данные через collector — код сам
    переключится, т.к. проверяет пустоту БД по строкам.

Генерация детерминированная: одни и те же каналы при каждом запуске.
"""

import random
import math
from datetime import datetime, date, timedelta
from typing import Optional

random.seed(42)

# ── Демо-каналы ─────────────────────────────────────────────────────

DEMO_CHANNELS = [
    {"id": 10001, "username": "bbcrussian", "title": "BBC News | Русская служба",
     "description": "Новости, аналитика и репортажи от BBC. 📰", "category": "Новости и СМИ",
     "language": "ru", "country": "UK", "participants": 1_250_000},
    {"id": 10002, "username": "nadvorsarh", "title": "На Дворцовой",
     "description": "Главные новости Петербурга и области.", "category": "Новости и СМИ",
     "language": "ru", "country": "RU", "participants": 890_000},
    {"id": 10003, "username": "rianovosti", "title": "РИА Новости",
     "description": "Официальный канал агентства РИА Новости.", "category": "Новости и СМИ",
     "language": "ru", "country": "RU", "participants": 2_100_000},
    {"id": 10004, "username": "tass_agency", "title": "ТАСС",
     "description": "Новости России и мира. Оперативно и достоверно.", "category": "Новости и СМИ",
     "language": "ru", "country": "RU", "participants": 1_800_000},
    {"id": 10005, "username": "meduza_news", "title": "Meduza",
     "description": "Новости, репортажи и расследования.", "category": "Новости и СМИ",
     "language": "ru", "country": "LV", "participants": 950_000},
    {"id": 20001, "username": "kino_news", "title": "Кино наизнанку",
     "description": "Всё о кино: новинки, трейлеры, рецензии, инсайды.", "category": "Развлечения",
     "language": "ru", "country": "RU", "participants": 520_000},
    {"id": 20002, "username": "memes_best", "title": "Лучшие Мемы",
     "description": "Ежедневная подборка лучших мемов и юмора со всего интернета.", "category": "Развлечения",
     "language": "ru", "country": "RU", "participants": 1_400_000},
    {"id": 20003, "username": "kinobaza", "title": "КиноБаза",
     "description": "Фильмы, сериалы, рейтинги и рецензии.", "category": "Развлечения",
     "language": "ru", "country": "RU", "participants": 680_000},
    {"id": 30001, "username": "code_mind", "title": "Code & Mind",
     "description": "IT, программирование, стартапы, технологии.", "category": "Технологии",
     "language": "ru", "country": "RU", "participants": 360_000},
    {"id": 30002, "username": "tech_news_pro", "title": "Техно Новости",
     "description": "Новости IT, гаджетов и технологий будущего.", "category": "Технологии",
     "language": "ru", "country": "US", "participants": 720_000},
    {"id": 30003, "username": "aitoday", "title": "AI Today",
     "description": "Новости искусственного интеллекта, ML и Data Science.", "category": "Технологии",
     "language": "en", "country": "US", "participants": 1_100_000},
    {"id": 40001, "username": "business_rus", "title": "Бизнес-секреты",
     "description": "Предпринимательство, финансы, инвестиции.", "category": "Бизнес",
     "language": "ru", "country": "RU", "participants": 450_000},
    {"id": 40002, "username": "investpro", "title": "ИнвестПро",
     "description": "Аналитика фондового рынка, советы инвесторам.", "category": "Бизнес",
     "language": "ru", "country": "RU", "participants": 280_000},
    {"id": 40003, "username": "marketingzone", "title": "Marketing Zone",
     "description": "Маркетинг, SMM, реклама, кейсы.", "category": "Бизнес",
     "language": "ru", "country": "RU", "participants": 310_000},
    {"id": 50001, "username": "sport_live", "title": "Спорт LIVE",
     "description": "Главные спортивные события в реальном времени.", "category": "Спорт",
     "language": "ru", "country": "RU", "participants": 870_000},
    {"id": 50002, "username": "football_rus", "title": "Футбол России",
     "description": "РПЛ, сборная, еврокубки — всё о футболе.", "category": "Спорт",
     "language": "ru", "country": "RU", "participants": 650_000},
    {"id": 50003, "username": "mma_today", "title": "MMA Today",
     "description": "UFC, Bellator, ONE — новости смешанных единоборств.", "category": "Спорт",
     "language": "ru", "country": "US", "participants": 390_000},
    {"id": 60001, "username": "edu_pulse", "title": "Образовательный Пульс",
     "description": "Курсы, лекции, учебные материалы, гранты.", "category": "Образование",
     "language": "ru", "country": "RU", "participants": 190_000},
    {"id": 60002, "username": "book_world", "title": "Книжный Мир",
     "description": "Литература, новинки издательств, книжные подборки.", "category": "Образование",
     "language": "ru", "country": "RU", "participants": 230_000},
    {"id": 70001, "username": "health_daily", "title": "Здоровый День",
     "description": "Медицина, здоровый образ жизни, фитнес, питание.", "category": "Здоровье",
     "language": "ru", "country": "RU", "participants": 410_000},
    {"id": 70002, "username": "psy_simple", "title": "Психология Просто",
     "description": "Психология, саморазвитие, отношения.", "category": "Здоровье",
     "language": "ru", "country": "RU", "participants": 540_000},
    {"id": 80001, "username": "travel_east", "title": "Восток — дело тонкое",
     "description": "Путешествия по Азии: Турция, ОАЭ, Таиланд.", "category": "Путешествия",
     "language": "ru", "country": "TR", "participants": 330_000},
    {"id": 80002, "username": "trip_ideas", "title": "Trip Ideas",
     "description": "Идеи для путешествий, советы туристам.", "category": "Путешествия",
     "language": "ru", "country": "RU", "participants": 270_000},
    {"id": 90001, "username": "fashion_alert", "title": "Fashion Alert",
     "description": "Мода, стиль, бренды, показы.", "category": "Стиль и мода",
     "language": "ru", "country": "FR", "participants": 180_000},
    {"id": 100001, "username": "science_digest", "title": "Science Digest",
     "description": "Наука, открытия, исследования, космос.", "category": "Технологии",
     "language": "en", "country": "US", "participants": 620_000},
    {"id": 110001, "username": "auto_street", "title": "Auto Street",
     "description": "Автомобили, обзоры, тест-драйвы, автоспорт.", "category": "Авто",
     "language": "ru", "country": "RU", "participants": 480_000},
    {"id": 120001, "username": "gaming_pulse", "title": "Gaming Pulse",
     "description": "Игровая индустрия, обзоры, геймплей.", "category": "Развлечения",
     "language": "en", "country": "US", "participants": 890_000},
    {"id": 130001, "username": "crypto_up", "title": "Crypto Up",
     "description": "Криптовалюты, DeFi, NFT, блокчейн.", "category": "Бизнес",
     "language": "ru", "country": "RU", "participants": 560_000},
    {"id": 140001, "username": "lifehacker_ru", "title": "Лайфхакер",
     "description": "Советы, лайфхаки, продуктивность.", "category": "Образование",
     "language": "ru", "country": "RU", "participants": 780_000},
    {"id": 140002, "username": "psychology_ru", "title": "Психология",
     "description": "Канал о психологии и саморазвитии.", "category": "Здоровье",
     "language": "ru", "country": "RU", "participants": 1_050_000},
]

CATEGORIES = {
    "Новости и СМИ": "#ff4757",
    "Развлечения": "#ff6b81",
    "Технологии": "#3498db",
    "Бизнес": "#2ed573",
    "Спорт": "#1e90ff",
    "Образование": "#a29bfe",
    "Здоровье": "#55efc4",
    "Путешествия": "#fdcb6e",
    "Стиль и мода": "#fd79a8",
    "Авто": "#e17055",
}

CATEGORY_LIST = sorted(CATEGORIES.keys())


# ── Кэш эмуляции ────────────────────────────────────────────────────
# (ключик: 'channels' / f'posts_{ch_id}' / f'stats_{ch_id}' / f'subs_{ch_id}')

_cache: dict = {}

def _get_or_create(key: str, factory):
    if key not in _cache:
        _cache[key] = factory()
    return _cache[key]


# ── Генерация данных ────────────────────────────────────────────────

def _make_participants(base: int, days_ago: int = 30) -> int:
    """Симулируем постепенный рост подписчиков."""
    grow = random.randint(-50, 200)
    return base - grow * (30 - days_ago) // 30


def generate_all_channels():
    """Возвращает список каналов в формате, идентичном ChannelOut."""
    channels = []
    for ch in DEMO_CHANNELS:
        participants = ch["participants"]
        first_seen = datetime.utcnow() - timedelta(days=random.randint(180, 720))
        last_scraped = datetime.utcnow() - timedelta(hours=random.randint(0, 6))
        posts_count = random.randint(100, 3000)

        channels.append({
            "id": ch["id"],
            "username": ch["username"],
            "title": ch["title"],
            "description": ch["description"],
            "participants_count": participants,
            "first_seen": first_seen,
            "last_scraped": last_scraped,
            "posts_count": posts_count,
            "category": ch["category"],
            "language": ch["language"],
            "country": ch["country"],
        })
    return channels


def generate_channel_detail(channel_id: int):
    """Один канал детально."""
    all_channels = generate_all_channels()
    for ch in all_channels:
        if ch["id"] == channel_id:
            return ch
    return None


def generate_daily_stats(channel_id: int, days: int = 30):
    """Статистика канала по дням (DailyStatsOut)."""
    ch = generate_channel_detail(channel_id)
    if not ch:
        return []
    base_subs = ch["participants_count"]
    base_views = int(base_subs * random.uniform(0.1, 0.5))

    stats = []
    for d in range(days - 1, -1, -1):
        dt = date.today() - timedelta(days=d)
        participants = _make_participants(base_subs, d)
        noise = random.uniform(-0.4, 0.6)
        day_views = max(100, int(base_views * (1 + noise)))
        posts = max(1, int(random.gauss(8, 3)))
        avg_v = round(day_views / posts, 1)
        forwards = int(day_views * random.uniform(0.02, 0.15))
        er = round((day_views + forwards) / participants * 100, 2) if participants > 0 else 0

        stats.append({
            "date": dt.isoformat(),
            "posts_count": posts,
            "total_views": day_views,
            "avg_views": avg_v,
            "total_forwards": forwards,
            "avg_forwards": round(forwards / posts, 1),
            "mentions_count": random.randint(0, 15),
            "engagement_rate": er,
            "participants_count": participants,
        })
    return stats


def generate_subscribers(channel_id: int, days: int = 30):
    """История подписчиков (для графика)."""
    ch = generate_channel_detail(channel_id)
    if not ch:
        return []
    base = ch["participants_count"]
    # Начинаем с base - random прирост
    start = base - random.randint(-5000, 15000)
    data = []
    for d in range(days - 1, -1, -1):
        dt = date.today() - timedelta(days=d)
        progress = (days - d) / days
        subs = int(start + (base - start) * progress * random.uniform(0.9, 1.05))
        data.append({
            "date": dt.isoformat(),
            "participants_count": subs,
            "sources_total": subs,
            "delta": random.randint(-200, 500),
        })
    return data


def generate_posts(channel_id: int, limit: int = 50):
    """Список постов канала."""
    ch = generate_channel_detail(channel_id)
    if not ch:
        return []

    post_texts = {
        10001: [
            "Президент России встретился с лидерами стран БРИКС.",
            "В Лондоне прошла встреча министров финансов G7.",
            "Новый закон о цифровых активах вступает в силу с января.",
            "Эксперты прогнозируют рост ВВП на 2.3% в следующем году.",
            "Климатический саммит в Париже: итоги недели.",
        ],
        30001: [
            "Python 3.14: что нового в релизе.",
            "Google представил новую модель Gemini Pro 2.",
            "Как микросервисы меняют архитектуру приложений.",
            "Топ-10 библиотек для Data Science в 2026 году.",
            "Ревью: Rust vs Go — что выбрать для бэкенда.",
        ],
        50001: [
            "Сборная России выиграла товарищеский матч.",
            "Результаты UFC 320: неожиданный чемпион.",
            "Трансферная новость дня: звёздный переход.",
            "Олимпийский комитет анонсировал новые виды спорта.",
            "Новый рекорд в марафонском беге.",
        ],
    }
    default_texts = [
        "Важное заявление от экспертов отрасли.",
        "Аналитика: тренды этой недели.",
        "Что происходит на рынке? Краткий обзор.",
        "Инсайд: подробности грядущих изменений.",
        "Сегодня в фокусе: главное событие дня.",
    ]
    texts = post_texts.get(channel_id, default_texts)

    posts = []
    for i in range(limit):
        dt = datetime.utcnow() - timedelta(hours=random.randint(0, 24 * 30))
        views = random.randint(500, ch["participants_count"] // 2)
        forwards = random.randint(0, int(views * 0.2))
        post_text = random.choice(texts)
        has_media = random.random() > 0.4
        media_type = None
        if has_media:
            media_type = random.choice(["photo", "video", "document"])
        posts.append({
            "id": 900000 + i,
            "channel_id": channel_id,
            "date": dt,
            "text": post_text,
            "views": views,
            "forwards": forwards,
            "has_media": has_media,
            "media_type": media_type,
        })
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


def generate_rankings(sort_by: str = "avg_views"):
    """Рейтинг каналов."""
    channels = generate_all_channels()
    rows = []
    for ch in channels:
        stats = generate_daily_stats(ch["id"], days=7)
        avg_views = sum(s["avg_views"] for s in stats) / max(len(stats), 1)
        avg_er = sum(s["engagement_rate"] for s in stats) / max(len(stats), 1)
        posts_7d = sum(s["posts_count"] for s in stats)
        rows.append({
            "channel_id": ch["id"],
            "username": ch["username"],
            "title": ch["title"],
            "participants_count": ch["participants_count"],
            "avg_views": round(avg_views, 1),
            "avg_er": round(avg_er, 2),
            "posts_7d": posts_7d,
            "category": ch["category"],
        })

    sort_field = sort_by if sort_by != "avg_er" else "avg_er"
    rows.sort(key=lambda r: r.get(sort_field, 0) or 0, reverse=True)
    return rows


def search_channels_emulated(query: str):
    """Поиск по каналам (полнотекстовый)."""
    q = query.lower()
    results = []
    for ch in generate_all_channels():
        if q in ch["title"].lower() or q in ch["username"].lower() or q in ch["description"].lower() or q in ch.get("category", "").lower():
            results.append(ch)
    return results


def search_posts_emulated(query: str, limit: int = 20):
    """Поиск по постам."""
    q = query.lower()
    results = []
    for ch in generate_all_channels():
        posts = generate_posts(ch["id"], limit=20)
        for p in posts:
            if q in (p.get("text") or "").lower():
                results.append({
                    **p,
                    "channel_title": ch["title"],
                    "channel_username": ch["username"],
                })
    return results[:limit]


def search_mentions_emulated(query: str, limit: int = 50):
    """Имитация упоминаний."""
    channels = generate_all_channels()
    mentions = []
    for src in channels:
        for tgt in channels:
            if src["id"] == tgt["id"]:
                continue
            if query.lower() in tgt["username"].lower():
                if random.random() > 0.9:
                    dt = datetime.utcnow() - timedelta(hours=random.randint(0, 168))
                    mentions.append({
                        "id": len(mentions) + 1,
                        "target_channel_id": tgt["id"],
                        "source_channel_id": src["id"],
                        "date": dt.isoformat(),
                        "text": f"Смотрите также @{tgt['username']} — отличный канал!",
                        "mention_type": "link",
                    })
                if len(mentions) >= limit:
                    break
        if len(mentions) >= limit:
            break
    mentions.sort(key=lambda m: m["date"], reverse=True)
    return mentions[:limit]


# ── Топ публикаций дня ──────────────────────────────────────────────

def generate_top_posts(limit: int = 10):
    """Лучшие публикации дня по просмотрам."""
    posts = []
    for ch in generate_all_channels():
        ch_posts = generate_posts(ch["id"], limit=5)
        for p in ch_posts:
            posts.append({
                **p,
                "channel_title": ch["title"],
                "channel_username": ch["username"],
            })
    posts.sort(key=lambda p: p["views"] or 0, reverse=True)
    return posts[:limit]


# ── Маркер: использовать эмуляцию ───────────────────────────────────

def should_use_emulation(db_session) -> bool:
    """Проверяем, пуста ли таблица channels."""
    from sqlalchemy import select, func
    from db.schema import Channel
    import asyncio
    try:
        result = db_session.execute(select(func.count(Channel.id)))
        count = result.scalar() or 0
        return count == 0
    except Exception:
        return True