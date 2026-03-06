from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from wh40k_bot.db import (
    Game,
    GameParticipant,
    GameRepository,
    GameStatus,
    ParticipantRepository,
    Team,
    UserRepository,
)


@dataclass
class GameCreationResult:
    game: Game
    users_to_notify: List[Tuple[int, str]]  # (telegram_id, display_name)


@dataclass
class SubmissionResult:
    success: bool
    game: Optional[Game] = None
    all_submitted: bool = False
    error: Optional[str] = None


class GameService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.game_repo = GameRepository(session)
        self.participant_repo = ParticipantRepository(session)
    
    async def create_game(
        self,
        created_by: int,
        participant_telegram_ids: List[int],
        participant_usernames: List[Optional[str]],
        participant_names: List[Optional[str]],
        title: Optional[str] = None,
        deadline_hours: Optional[int] = None,
        scheduled_at: Optional[datetime] = None,
        points_limit: Optional[int] = None
    ) -> GameCreationResult:
        """
        Создать новую игру.
        
        Args:
            created_by: Telegram ID создателя
            participant_telegram_ids: Список Telegram ID участников
            participant_usernames: Список username'ов участников
            participant_names: Список имён участников
            title: Название игры (опционально)
            deadline_hours: Дедлайн в часах от текущего момента
            scheduled_at: Дата и время игры
            points_limit: Лимит очков армии
        
        Returns:
            GameCreationResult с игрой и списком пользователей для уведомления
        """
        # Создаём/получаем пользователей
        user_ids = []
        users_to_notify = []
        
        for tg_id, username, name in zip(
            participant_telegram_ids, 
            participant_usernames, 
            participant_names
        ):
            user = await self.user_repo.get_or_create(tg_id, username, name)
            user_ids.append(user.id)
            display_name = username or name or f"User {tg_id}"
            users_to_notify.append((tg_id, display_name))
        
        # Вычисляем дедлайн
        deadline = None
        if deadline_hours:
            # Дедлайн от времени старта игры, если указан, иначе от текущего времени
            base_time = scheduled_at if scheduled_at else datetime.utcnow()
            deadline = base_time - timedelta(hours=deadline_hours)
        
        # Создаём игру
        game = await self.game_repo.create(
            created_by=created_by,
            participant_ids=user_ids,
            title=title,
            deadline=deadline,
            scheduled_at=scheduled_at,
            points_limit=points_limit
        )
        
        await self.session.commit()
        
        return GameCreationResult(game=game, users_to_notify=users_to_notify)
    
    async def submit_army_list(
        self,
        telegram_id: int,
        game_id: int,
        army_list_id: int
    ) -> SubmissionResult:
        """
        Отправить список армии.
        
        Args:
            telegram_id: Telegram ID пользователя
            game_id: ID игры
            army_list_id: ID сохранённого списка армии
        
        Returns:
            SubmissionResult с результатом операции
        """
        participant = await self.participant_repo.get_by_game_and_user(game_id, telegram_id)
        
        if not participant:
            return SubmissionResult(
                success=False, 
                error="Вы не участвуете в этой игре"
            )
        
        status_value = participant.game.status.value if hasattr(participant.game.status, 'value') else participant.game.status
        if status_value != "collecting":
            return SubmissionResult(
                success=False, 
                error="Приём списков для этой игры уже закрыт"
            )
        
        if participant.army_list_id:
            return SubmissionResult(
                success=False, 
                error="Вы уже отправили список для этой игры. Используйте /resubmit для замены."
            )
        
        # Сохраняем список
        await self.participant_repo.submit_army_list(
            participant_id=participant.id,
            army_list_id=army_list_id
        )
        
        await self.session.commit()
        
        # Перезагружаем игру для проверки
        game = await self.game_repo.get_by_id(game_id)
        
        # Если все отправили — меняем статус
        all_submitted = game.all_lists_submitted
        if all_submitted:
            await self.game_repo.update_status(game_id, GameStatus.READY)
            await self.session.commit()
            game = await self.game_repo.get_by_id(game_id)
        
        return SubmissionResult(
            success=True,
            game=game,
            all_submitted=all_submitted
        )
    
    async def get_pending_games_for_user(self, telegram_id: int) -> List[GameParticipant]:
        """Получить игры, где пользователь ещё не отправил список"""
        return await self.participant_repo.get_pending_for_user(telegram_id)
    
    async def clear_army_list_for_resubmit(self, telegram_id: int, game_id: int) -> bool:
        """Очистить список армии для переотправки"""
        participant = await self.participant_repo.get_by_game_and_user(game_id, telegram_id)
        
        if not participant:
            return False
        
        # Можно переотправить только пока статус COLLECTING
        status_value = participant.game.status.value if hasattr(participant.game.status, 'value') else participant.game.status
        if status_value != "collecting":
            return False
        
        await self.participant_repo.clear_army_list(participant.id)
        await self.session.commit()
        return True
    
    async def get_submitted_games_for_user(self, telegram_id: int) -> List[GameParticipant]:
        """Получить игры, где пользователь уже отправил список (но сбор ещё идёт)"""
        return await self.participant_repo.get_submitted_for_user(telegram_id)
    
    async def get_all_active_games_for_user(self, telegram_id: int) -> List[GameParticipant]:
        """Получить все активные игры пользователя"""
        return await self.participant_repo.get_all_active_for_user(telegram_id)
    
    async def get_game(self, game_id: int) -> Optional[Game]:
        """Получить игру по ID"""
        return await self.game_repo.get_by_id(game_id)
    
    async def get_active_games(self) -> List[Game]:
        """Получить все активные игры"""
        return await self.game_repo.get_active_games()
    
    async def assign_teams(
        self,
        game_id: int,
        team_a_telegram_ids: List[int],
        team_b_telegram_ids: List[int]
    ) -> bool:
        """Распределить участников по командам"""
        game = await self.game_repo.get_by_id(game_id)
        if not game:
            return False
        
        for participant in game.participants:
            tg_id = participant.user.telegram_id
            if tg_id in team_a_telegram_ids:
                await self.participant_repo.set_team(participant.id, Team.TEAM_A)
            elif tg_id in team_b_telegram_ids:
                await self.participant_repo.set_team(participant.id, Team.TEAM_B)
        
        await self.session.commit()
        return True
    
    async def auto_assign_teams(self, game_id: int) -> bool:
        """Автоматически распределить участников по командам случайным образом"""
        import random
        
        game = await self.game_repo.get_by_id(game_id)
        if not game:
            return False
        
        # Собираем участников без команды
        unassigned = [p for p in game.participants if not p.team]
        
        if not unassigned:
            return True  # Все уже распределены
        
        # Перемешиваем случайным образом
        random.shuffle(unassigned)
        
        # Делим пополам
        half = len(unassigned) // 2
        
        for i, participant in enumerate(unassigned):
            if i < half:
                await self.participant_repo.set_team(participant.id, Team.TEAM_A)
            else:
                await self.participant_repo.set_team(participant.id, Team.TEAM_B)
        
        await self.session.commit()
        return True
    
    async def set_winner(self, game_id: int, winner_team: Team) -> bool:
        """Установить победителя"""
        game = await self.game_repo.get_by_id(game_id)
        if not game:
            return False
        
        if game.status not in [GameStatus.READY, GameStatus.IN_PROGRESS]:
            return False
        
        await self.game_repo.set_winner(game_id, winner_team)
        await self.session.commit()
        return True
    
    async def cancel_game(self, game_id: int) -> bool:
        """Отменить игру"""
        game = await self.game_repo.get_by_id(game_id)
        if not game:
            return False
        
        if game.status == GameStatus.FINISHED:
            return False
        
        await self.game_repo.cancel(game_id)
        await self.session.commit()
        return True
    
    async def start_game(self, game_id: int) -> bool:
        """Начать игру (перевести в статус IN_PROGRESS)"""
        game = await self.game_repo.get_by_id(game_id)
        if not game or game.status != GameStatus.READY:
            return False
        
        await self.game_repo.update_status(game_id, GameStatus.IN_PROGRESS)
        await self.session.commit()
        return True


class ReminderService:
    """Сервис для напоминаний о дедлайнах"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.game_repo = GameRepository(session)
    
    async def get_games_needing_reminder(self, hours_before: int = 2) -> List[Game]:
        """Получить игры, для которых нужно отправить напоминание о дедлайне"""
        now = datetime.utcnow()
        return await self.game_repo.get_games_needing_reminder(now, hours_before)
    
    async def mark_reminder_sent(self, game_id: int) -> None:
        """Отметить, что напоминание о дедлайне отправлено"""
        await self.game_repo.set_reminder_sent(game_id)
        await self.session.commit()
    
    async def get_expired_games(self) -> List[Game]:
        """Получить игры с истёкшим дедлайном"""
        now = datetime.utcnow()
        return await self.game_repo.get_expired_games(now)
    
    async def get_games_needing_game_reminder(self, hours_before: int = 2) -> List[Game]:
        """Получить игры, для которых нужно отправить напоминание о начале игры"""
        now = datetime.utcnow()
        return await self.game_repo.get_games_needing_game_reminder(now, hours_before)
    
    async def mark_game_reminder_sent(self, game_id: int) -> None:
        """Отметить, что напоминание об игре отправлено"""
        await self.game_repo.set_game_reminder_sent(game_id)
        await self.session.commit()
