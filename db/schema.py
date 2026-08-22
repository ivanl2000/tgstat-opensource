"""tgstat-opensource — База данных (SQLAlchemy модели)

Таблицы:
- Channel        — каналы, которые мы отслеживаем
- ChannelStats   — снимки подписчиков канала по датам (история)
- Post           — посты из каналов
- Mention        — упоминания каналов в других каналах
- DailyStats     — агрегированная дневная статистика
"""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime, Float, Date,
    ForeignKey, Text, Boolean, UniqueConstraint, create_engine, select, func
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


class Base(DeclarativeBase):
    pass


class Channel(Base):
    __tablename__ = "channels"

    id = Column(BigInteger, primary_key=True, autoincrement=False)
    username = Column(String(128), nullable=True, index=True)
    title = Column(String(256), nullable=True)
    description = Column(Text, nullable=True)
    participants_count = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_scraped = Column(DateTime, nullable=True)

    posts = relationship("Post", back_populates="channel", lazy="dynamic")
    daily_stats = relationship("DailyStats", back_populates="channel", lazy="dynamic")
    subscriber_history = relationship("ChannelStats", back_populates="channel", lazy="dynamic")

    def __repr__(self):
        return f"<Channel {self.username or self.id}: {self.title}>"


class ChannelStats(Base):
    """Снимок подписчиков канала на конкретную дату (история изменения)."""

    __tablename__ = "channel_stats"
    __table_args__ = (
        UniqueConstraint("channel_id", "date", name="uq_channel_stats_channel_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("channels.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    participants_count = Column(Integer, nullable=True)
    sources_total = Column(Integer, nullable=True)      # всего источников (подписчиков-источников)
    _add = Column(Integer, nullable=True, default=0)    # прирост за период (дельт)

    channel = relationship("Channel", back_populates="subscriber_history")

    def __repr__(self):
        return f"<ChannelStats {self.date} @{self.channel_id}: {self.participants_count}>"


class Post(Base):
    __tablename__ = "posts"

    id = Column(BigInteger, primary_key=True, autoincrement=False)
    channel_id = Column(BigInteger, ForeignKey("channels.id"), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    text = Column(Text, nullable=True)
    views = Column(Integer, nullable=True)
    forwards = Column(Integer, nullable=True)
    has_media = Column(Boolean, default=False)
    media_type = Column(String(32), nullable=True)

    channel = relationship("Channel", back_populates="posts")

    def __repr__(self):
        return f"<Post #{self.id} @{self.channel_id}: {len(self.text or '')} chars>"


class Mention(Base):
    __tablename__ = "mentions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target_channel_id = Column(BigInteger, ForeignKey("channels.id"), nullable=False, index=True)
    source_channel_id = Column(BigInteger, ForeignKey("channels.id"), nullable=True)
    source_post_id = Column(BigInteger, ForeignKey("posts.id"), nullable=True)
    date = Column(DateTime, nullable=False)
    text = Column(Text, nullable=True)
    mention_type = Column(String(32), default="link")  # link, forward, text

    def __repr__(self):
        return f"<Mention #{self.target_channel_id} in #{self.source_channel_id}>"


class DailyStats(Base):
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("channels.id"), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    posts_count = Column(Integer, default=0)
    total_views = Column(BigInteger, default=0)
    avg_views = Column(Float, nullable=True)
    total_forwards = Column(BigInteger, default=0)
    avg_forwards = Column(Float, nullable=True)
    mentions_count = Column(Integer, default=0)
    engagement_rate = Column(Float, nullable=True)  # (views+forwards)/subscribers * 100
    participants_count = Column(Integer, nullable=True)  # подписчики, зафиксированные на эту дату

    channel = relationship("Channel", back_populates="daily_stats")

    def __repr__(self):
        return f"<DailyStats {self.date.date()} @{self.channel_id}>"


# --- Engine helpers ---

def create_engine_sync(url: str, echo: bool = False):
    """Синхронный engine для миграций / тестов."""
    return create_engine(url, echo=echo)


def create_async_engine_from_url(url: str, echo: bool = False):
    """Асинхронный engine."""
    return create_async_engine(url, echo=echo)