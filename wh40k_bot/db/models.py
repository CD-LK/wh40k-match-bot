from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(AsyncAttrs, DeclarativeBase):
    pass


class GameStatus(str, Enum):
    COLLECTING = "collecting"      # Собираем списки армий
    READY = "ready"                # Все списки собраны, ждём игру
    IN_PROGRESS = "in_progress"    # Игра идёт
    FINISHED = "finished"          # Игра завершена
    CANCELLED = "cancelled"        # Отменена


class Team(str, Enum):
    TEAM_A = "team_a"
    TEAM_B = "team_b"


class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Relationships
    participations: Mapped[List["GameParticipant"]] = relationship(back_populates="user")
    army_lists: Mapped[List["ArmyList"]] = relationship(back_populates="user")


class Game(Base):
    __tablename__ = "games"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[GameStatus] = mapped_column(String(50), default=GameStatus.COLLECTING)
    
    # Создатель игры (админ)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Лимит очков армии
    points_limit: Mapped[Optional[int]] = mapped_column(nullable=True)
    
    # Дедлайн для отправки списков
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(default=False)
    
    # Дата и время игры
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    game_reminder_sent: Mapped[bool] = mapped_column(default=False)  # Напоминание за 2 часа до игры
    
    # Миссия (JSON с данными о выбранной миссии)
    mission_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Результат
    winner_team: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Team enum value
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    participants: Mapped[List["GameParticipant"]] = relationship(
        back_populates="game", 
        cascade="all, delete-orphan"
    )
    
    @property
    def all_lists_submitted(self) -> bool:
        """Проверяет, все ли участники отправили списки"""
        return all(p.army_list_id is not None for p in self.participants)
    
    @property
    def submitted_count(self) -> int:
        return sum(1 for p in self.participants if p.army_list_id is not None)
    
    @property
    def total_participants(self) -> int:
        return len(self.participants)


class GameParticipant(Base):
    __tablename__ = "game_participants"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    
    # Команда (A или B)
    team: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Ссылка на сохранённый список армии
    army_list_id: Mapped[Optional[int]] = mapped_column(ForeignKey("army_lists.id", ondelete="SET NULL"), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Уведомления
    notified: Mapped[bool] = mapped_column(default=False)
    
    # Relationships
    game: Mapped["Game"] = relationship(back_populates="participants")
    user: Mapped["User"] = relationship(back_populates="participations")
    army_list: Mapped[Optional["ArmyList"]] = relationship()


class ArmyList(Base):
    """Сохранённый список армии пользователя"""
    __tablename__ = "army_lists"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    
    # Основная информация (извлекается из JSON)
    name: Mapped[str] = mapped_column(String(255))
    faction: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    detachment: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    total_points: Mapped[int] = mapped_column(default=0)
    
    # Версия datasources при создании/обновлении
    datasources_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Полный JSON для хранения
    json_data: Mapped[dict] = mapped_column(JSONB)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="army_lists")


# Database setup
async def create_db_engine(db_url: str):
    engine = create_async_engine(db_url, echo=False)
    return engine


async def create_session_maker(engine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
