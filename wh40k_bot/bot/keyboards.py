from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from wh40k_bot.db import Game, GameParticipant, Team


def game_select_keyboard(games: List[Game]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора игры"""
    buttons = []
    for game in games:
        title = game.title or f"Игра #{game.id}"
        buttons.append([
            InlineKeyboardButton(
                text=f"🎮 {title} ({game.submitted_count}/{game.total_participants})",
                callback_data=f"select_game:{game.id}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def pending_games_keyboard(participations: List[GameParticipant]) -> InlineKeyboardMarkup:
    """Клавиатура со списком игр, ожидающих список армии"""
    buttons = []
    for p in participations:
        game = p.game
        title = game.title or f"Игра #{game.id}"
        deadline_str = ""
        if game.deadline:
            deadline_str = f" (до {game.deadline.strftime('%d.%m %H:%M')})"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"📋 {title}{deadline_str}",
                callback_data=f"submit_list:{game.id}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def resubmit_games_keyboard(participations: List[GameParticipant]) -> InlineKeyboardMarkup:
    """Клавиатура со списком игр для переотправки списка"""
    buttons = []
    for p in participations:
        game = p.game
        title = game.title or f"Игра #{game.id}"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"🔄 {title}",
                callback_data=f"resubmit_list:{game.id}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def my_games_keyboard(participations: List[GameParticipant]) -> InlineKeyboardMarkup:
    """Клавиатура со всеми активными играми пользователя"""
    buttons = []
    for p in participations:
        game = p.game
        title = game.title or f"Игра #{game.id}"
        
        # Определяем статус
        status_value = game.status.value if hasattr(game.status, 'value') else game.status
        
        if status_value == "collecting":
            if p.army_list_id:
                emoji = "✅"  # Отправил список
            else:
                emoji = "⏳"  # Ждём список
        elif status_value == "ready":
            emoji = "🎮"  # Готово к игре
        elif status_value == "in_progress":
            emoji = "⚔️"  # Игра идёт
        else:
            emoji = "📋"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji} {title}",
                callback_data=f"view_my_game:{game.id}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def army_lists_keyboard(army_lists: list, for_submit: bool = False, game_id: int = None) -> InlineKeyboardMarkup:
    """Клавиатура со списками армий пользователя"""
    buttons = []
    
    for al in army_lists:
        text = f"📋 {al.name} ({al.total_points} pts)"
        if for_submit and game_id:
            callback = f"select_army_list:{game_id}:{al.id}"
        else:
            callback = f"view_army_list:{al.id}"
        
        buttons.append([
            InlineKeyboardButton(text=text, callback_data=callback)
        ])
    
    if not for_submit:
        buttons.append([
            InlineKeyboardButton(text="➕ Загрузить новый список", callback_data="upload_army_list")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def army_list_actions_keyboard(army_list_id: int) -> InlineKeyboardMarkup:
    """Клавиатура действий со списком армии"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎴 Показать карточки", callback_data=f"show_army_cards:{army_list_id}"),
        ],
        [
            InlineKeyboardButton(text="⚔️ Стратагемы", callback_data=f"show_stratagems:{army_list_id}"),
        ],
        [
            InlineKeyboardButton(text="🔄 Обновить из datasources", callback_data=f"refresh_army_list:{army_list_id}"),
        ],
        [
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_army_list:{army_list_id}"),
        ],
        [
            InlineKeyboardButton(text="◀️ Назад к спискам", callback_data="back_to_army_lists")
        ]
    ])


def team_assignment_keyboard(game: Game) -> InlineKeyboardMarkup:
    """Клавиатура для распределения по командам"""
    buttons = []
    
    # Кнопка случайного распределения
    buttons.append([
        InlineKeyboardButton(
            text="🎲 Случайное распределение",
            callback_data=f"random_teams:{game.id}"
        )
    ])
    
    for participant in game.participants:
        user = participant.user
        name = user.username or user.first_name or f"User {user.telegram_id}"
        
        current_team = ""
        if participant.team == Team.TEAM_A.value:
            current_team = " [A]"
        elif participant.team == Team.TEAM_B.value:
            current_team = " [B]"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"🅰️",
                callback_data=f"set_team:{game.id}:{participant.id}:A"
            ),
            InlineKeyboardButton(
                text=f"👤 {name}{current_team}",
                callback_data=f"noop"
            ),
            InlineKeyboardButton(
                text=f"🅱️",
                callback_data=f"set_team:{game.id}:{participant.id}:B"
            ),
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text="✅ Готово",
            callback_data=f"teams_done:{game.id}"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def winner_select_keyboard(game_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для выбора победителя"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🏆 Команда A победила",
                callback_data=f"set_winner:{game_id}:A"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏆 Команда B победила",
                callback_data=f"set_winner:{game_id}:B"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"cancel_action"
            )
        ]
    ])


def game_management_keyboard(game: Game) -> InlineKeyboardMarkup:
    """Клавиатура управления игрой для админа"""
    buttons = []
    
    # game.status может быть enum или строкой
    status_value = game.status.value if hasattr(game.status, 'value') else game.status
    
    if status_value == "collecting":
        buttons.append([
            InlineKeyboardButton(
                text="📊 Статус списков",
                callback_data=f"game_status:{game.id}"
            )
        ])
    
    if status_value in ["collecting", "ready"]:
        buttons.append([
            InlineKeyboardButton(
                text="👥 Распределить команды",
                callback_data=f"assign_teams:{game.id}"
            )
        ])
    
    # Кнопка просмотра карточек армий участников (если все списки собраны)
    if game.all_lists_submitted:
        buttons.append([
            InlineKeyboardButton(
                text="🎴 Карточки армий",
                callback_data=f"game_army_cards:{game.id}"
            )
        ])
    
    if status_value == "ready":
        buttons.append([
            InlineKeyboardButton(
                text="▶️ Начать игру",
                callback_data=f"start_game:{game.id}"
            )
        ])
    
    # Кнопки для миссии (только когда игра идёт)
    if status_value == "in_progress":
        buttons.append([
            InlineKeyboardButton(
                text="🎲 Показать миссию",
                callback_data=f"show_mission:{game.id}"
            ),
            InlineKeyboardButton(
                text="🔄 Перегенерировать",
                callback_data=f"regenerate_mission:{game.id}"
            )
        ])
    
    if status_value in ["ready", "in_progress"]:
        buttons.append([
            InlineKeyboardButton(
                text="🏆 Записать результат",
                callback_data=f"record_result:{game.id}"
            )
        ])
    
    if status_value != "finished":
        buttons.append([
            InlineKeyboardButton(
                text="❌ Отменить игру",
                callback_data=f"cancel_game:{game.id}"
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_keyboard(action: str, game_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да",
                callback_data=f"confirm_{action}:{game_id}"
            ),
            InlineKeyboardButton(
                text="❌ Нет",
                callback_data=f"cancel_action"
            )
        ]
    ])
