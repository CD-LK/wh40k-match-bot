from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wh40k_bot.db.models import ArmyList, Game, GameParticipant, GameStatus, Team, User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_or_create(
        self, 
        telegram_id: int, 
        username: Optional[str] = None,
        first_name: Optional[str] = None
    ) -> User:
        """Получить пользователя или создать нового"""
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name
            )
            self.session.add(user)
            await self.session.flush()
        else:
            # Обновляем данные если изменились
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
            await self.session.flush()
        
        return user
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_username(self, username: str) -> Optional[User]:
        """Получить пользователя по username"""
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_all(self) -> List[User]:
        """Получить всех пользователей"""
        stmt = select(User).order_by(User.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class GameRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        created_by: int,
        participant_ids: List[int],
        title: Optional[str] = None,
        deadline: Optional[datetime] = None,
        scheduled_at: Optional[datetime] = None,
        points_limit: Optional[int] = None
    ) -> Game:
        """Создать новую игру с участниками"""
        game = Game(
            title=title,
            created_by=created_by,
            deadline=deadline,
            scheduled_at=scheduled_at,
            points_limit=points_limit,
            status=GameStatus.COLLECTING
        )
        self.session.add(game)
        await self.session.flush()
        
        # Добавляем участников
        for user_id in participant_ids:
            participant = GameParticipant(
                game_id=game.id,
                user_id=user_id
            )
            self.session.add(participant)
        
        await self.session.flush()
        
        # Перезагружаем с relationships
        return await self.get_by_id(game.id)
    
    async def get_by_id(self, game_id: int) -> Optional[Game]:
        stmt = (
            select(Game)
            .options(
                selectinload(Game.participants).selectinload(GameParticipant.user),
                selectinload(Game.participants).selectinload(GameParticipant.army_list)
            )
            .where(Game.id == game_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_active_games(self) -> List[Game]:
        """Получить все активные игры (не завершённые и не отменённые)"""
        stmt = (
            select(Game)
            .options(selectinload(Game.participants).selectinload(GameParticipant.user))
            .where(Game.status.in_([GameStatus.COLLECTING, GameStatus.READY, GameStatus.IN_PROGRESS]))
            .order_by(Game.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_games_needing_reminder(self, now: datetime, hours_before: int) -> List[Game]:
        """Получить игры, для которых нужно отправить напоминание"""
        from datetime import timedelta
        reminder_time = now + timedelta(hours=hours_before)
        
        stmt = (
            select(Game)
            .options(selectinload(Game.participants).selectinload(GameParticipant.user))
            .where(
                Game.status == GameStatus.COLLECTING,
                Game.deadline != None,
                Game.deadline <= reminder_time,
                Game.reminder_sent == False
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_expired_games(self, now: datetime) -> List[Game]:
        """Получить игры с истёкшим дедлайном"""
        stmt = (
            select(Game)
            .options(selectinload(Game.participants).selectinload(GameParticipant.user))
            .where(
                Game.status == GameStatus.COLLECTING,
                Game.deadline != None,
                Game.deadline < now
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def update_status(self, game_id: int, status: GameStatus) -> None:
        stmt = update(Game).where(Game.id == game_id).values(status=status)
        await self.session.execute(stmt)
    
    async def set_reminder_sent(self, game_id: int) -> None:
        stmt = update(Game).where(Game.id == game_id).values(reminder_sent=True)
        await self.session.execute(stmt)
    
    async def set_game_reminder_sent(self, game_id: int) -> None:
        stmt = update(Game).where(Game.id == game_id).values(game_reminder_sent=True)
        await self.session.execute(stmt)
    
    async def get_games_needing_game_reminder(self, now: datetime, hours_before: int) -> List[Game]:
        """Получить игры, для которых нужно отправить напоминание о начале игры"""
        from datetime import timedelta
        reminder_time = now + timedelta(hours=hours_before)
        
        stmt = (
            select(Game)
            .options(selectinload(Game.participants).selectinload(GameParticipant.user))
            .where(
                Game.status.in_([GameStatus.READY, GameStatus.IN_PROGRESS]),
                Game.scheduled_at != None,
                Game.scheduled_at <= reminder_time,
                Game.game_reminder_sent == False
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def set_winner(self, game_id: int, winner_team: Team) -> None:
        stmt = (
            update(Game)
            .where(Game.id == game_id)
            .values(
                winner_team=winner_team.value,
                status=GameStatus.FINISHED,
                finished_at=datetime.utcnow()
            )
        )
        await self.session.execute(stmt)
    
    async def cancel(self, game_id: int) -> None:
        await self.update_status(game_id, GameStatus.CANCELLED)


class ParticipantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_game_and_user(
        self, 
        game_id: int, 
        telegram_id: int
    ) -> Optional[GameParticipant]:
        stmt = (
            select(GameParticipant)
            .join(User)
            .options(selectinload(GameParticipant.game), selectinload(GameParticipant.user))
            .where(
                GameParticipant.game_id == game_id,
                User.telegram_id == telegram_id
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_pending_for_user(self, telegram_id: int) -> List[GameParticipant]:
        """Получить игры, где пользователь ещё не отправил список"""
        stmt = (
            select(GameParticipant)
            .join(User)
            .join(Game)
            .options(selectinload(GameParticipant.game), selectinload(GameParticipant.user))
            .where(
                User.telegram_id == telegram_id,
                GameParticipant.army_list_id == None,
                Game.status == GameStatus.COLLECTING
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_submitted_for_user(self, telegram_id: int) -> List[GameParticipant]:
        """Получить игры, где пользователь уже отправил список (но сбор ещё идёт)"""
        stmt = (
            select(GameParticipant)
            .join(User)
            .join(Game)
            .options(selectinload(GameParticipant.game), selectinload(GameParticipant.user))
            .where(
                User.telegram_id == telegram_id,
                GameParticipant.army_list_id != None,
                Game.status == GameStatus.COLLECTING
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_by_id(self, participant_id: int) -> Optional[GameParticipant]:
        """Получить участника по ID"""
        stmt = (
            select(GameParticipant)
            .options(
                selectinload(GameParticipant.user),
                selectinload(GameParticipant.army_list),
                selectinload(GameParticipant.game)
            )
            .where(GameParticipant.id == participant_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_all_active_for_user(self, telegram_id: int) -> List[GameParticipant]:
        """Получить все активные игры пользователя (не завершённые и не отменённые)"""
        stmt = (
            select(GameParticipant)
            .join(User)
            .join(Game)
            .options(
                selectinload(GameParticipant.game).selectinload(Game.participants).selectinload(GameParticipant.user),
                selectinload(GameParticipant.user)
            )
            .where(
                User.telegram_id == telegram_id,
                Game.status.in_([GameStatus.COLLECTING, GameStatus.READY, GameStatus.IN_PROGRESS])
            )
            .order_by(Game.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def submit_army_list(
        self,
        participant_id: int,
        army_list_id: int
    ) -> None:
        stmt = (
            update(GameParticipant)
            .where(GameParticipant.id == participant_id)
            .values(
                army_list_id=army_list_id,
                submitted_at=datetime.utcnow()
            )
        )
        await self.session.execute(stmt)
    
    async def clear_army_list(self, participant_id: int) -> None:
        """Очистить список армии для переотправки"""
        stmt = (
            update(GameParticipant)
            .where(GameParticipant.id == participant_id)
            .values(
                army_list_id=None,
                submitted_at=None
            )
        )
        await self.session.execute(stmt)
    
    async def set_team(self, participant_id: int, team: Team) -> None:
        stmt = (
            update(GameParticipant)
            .where(GameParticipant.id == participant_id)
            .values(team=team.value)
        )
        await self.session.execute(stmt)
    
    async def set_notified(self, participant_id: int) -> None:
        stmt = (
            update(GameParticipant)
            .where(GameParticipant.id == participant_id)
            .values(notified=True)
        )
        await self.session.execute(stmt)


class ArmyListRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        user_id: int,
        name: str,
        faction: Optional[str],
        detachment: Optional[str],
        total_points: int,
        json_data: dict,
        datasources_version: Optional[str] = None
    ) -> ArmyList:
        """Создать новый список армии"""
        army_list = ArmyList(
            user_id=user_id,
            name=name,
            faction=faction,
            detachment=detachment,
            total_points=total_points,
            json_data=json_data,
            datasources_version=datasources_version
        )
        self.session.add(army_list)
        await self.session.flush()
        return army_list
    
    async def get_by_id(self, army_list_id: int) -> Optional[ArmyList]:
        stmt = select(ArmyList).where(ArmyList.id == army_list_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_user(self, user_id: int) -> List[ArmyList]:
        """Получить все списки армий пользователя"""
        stmt = (
            select(ArmyList)
            .where(ArmyList.user_id == user_id)
            .order_by(ArmyList.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_by_user_telegram_id(self, telegram_id: int) -> List[ArmyList]:
        """Получить все списки армий пользователя по telegram_id"""
        stmt = (
            select(ArmyList)
            .join(User)
            .where(User.telegram_id == telegram_id)
            .order_by(ArmyList.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def delete(self, army_list_id: int) -> bool:
        """Удалить список армии"""
        stmt = select(ArmyList).where(ArmyList.id == army_list_id)
        result = await self.session.execute(stmt)
        army_list = result.scalar_one_or_none()
        
        if army_list:
            await self.session.delete(army_list)
            return True
        return False
    
    async def get_stats(self, army_list_id: int) -> dict:
        """Получить статистику списка армии (победы, поражения, всего игр)"""
        from wh40k_bot.db.models import Game, GameParticipant, GameStatus, Team
        
        # Получаем все завершённые игры с этим списком
        stmt = (
            select(GameParticipant)
            .join(Game)
            .options(selectinload(GameParticipant.game))
            .where(
                GameParticipant.army_list_id == army_list_id,
                Game.status == GameStatus.FINISHED
            )
        )
        result = await self.session.execute(stmt)
        participations = list(result.scalars().all())
        
        total = len(participations)
        wins = 0
        losses = 0
        draws = 0
        
        for p in participations:
            game = p.game
            if game.winner_team:
                if p.team == game.winner_team:
                    wins += 1
                else:
                    losses += 1
            else:
                draws += 1
        
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0
        }
