from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from wh40k_bot.bot.keyboards import (
    army_list_actions_keyboard,
    army_lists_keyboard,
    confirm_keyboard,
    game_management_keyboard,
    my_games_keyboard,
    team_assignment_keyboard,
    winner_select_keyboard,
)
from wh40k_bot.bot.middlewares import admin_required
from wh40k_bot.bot.states import SubmitArmyList, UploadArmyList
from wh40k_bot.bot.utils import format_army_lists, format_game_info, format_game_result
from wh40k_bot.config import config
from wh40k_bot.db import ParticipantRepository, Team
from wh40k_bot.services import GameService, ArmyListService, format_army_list_full

router = Router()


@router.callback_query(F.data.startswith("select_game:"))
async def select_game(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Выбор игры для просмотра"""
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    is_admin = config.is_admin(callback.from_user.id)
    
    await callback.message.edit_text(
        format_game_info(game, detailed=True),
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game) if is_admin else None
    )
    await callback.answer()


@router.callback_query(F.data.startswith("view_my_game:"))
async def view_my_game(callback: CallbackQuery, session: AsyncSession):
    """Просмотр игры пользователем"""
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    # Проверяем что пользователь участник
    participant = None
    for p in game.participants:
        if p.user.telegram_id == callback.from_user.id:
            participant = p
            break
    
    if not participant:
        await callback.answer("Вы не участвуете в этой игре", show_alert=True)
        return
    
    status_value = game.status.value if hasattr(game.status, 'value') else game.status
    
    # Формируем информацию об игре
    title = game.title or f"Игра #{game.id}"
    lines = [f"🎮 <b>{title}</b>\n"]
    
    # Статус игры
    status_text = {
        "collecting": "📝 Сбор списков",
        "ready": "✅ Готово к игре",
        "in_progress": "⚔️ Игра идёт",
    }
    lines.append(f"Статус: {status_text.get(status_value, status_value)}")
    
    if game.scheduled_at:
        lines.append(f"🕐 Дата игры: {game.scheduled_at.strftime('%d.%m.%Y %H:%M')} UTC")
    
    if game.deadline and status_value == "collecting":
        lines.append(f"⏰ Дедлайн списков: {game.deadline.strftime('%d.%m.%Y %H:%M')} UTC")
    
    # Ваш статус
    lines.append("")
    if participant.army_list_id:
        lines.append("✅ <b>Вы отправили список</b>")
    else:
        lines.append("⏳ <b>Вы ещё не выбрали список</b>")
    
    # Участники
    lines.append(f"\n👥 <b>Участники ({game.submitted_count}/{game.total_participants}):</b>")
    for p in game.participants:
        name = p.user.username or p.user.first_name or f"User {p.user.telegram_id}"
        if p.user.username:
            name = f"@{name}"
        status_icon = "✅" if p.army_list_id else "⏳"
        you_marker = " (вы)" if p.user.telegram_id == callback.from_user.id else ""
        lines.append(f"  {status_icon} {name}{you_marker}")
    
    # Кнопки действий
    buttons = []
    
    if status_value == "collecting":
        if not participant.army_list_id:
            buttons.append([
                InlineKeyboardButton(
                    text="📝 Выбрать список",
                    callback_data=f"submit_list:{game.id}"
                )
            ])
        else:
            buttons.append([
                InlineKeyboardButton(
                    text="🔄 Изменить список",
                    callback_data=f"resubmit_list:{game.id}"
                )
            ])
    
    # Показать списки если они собраны
    if status_value in ["ready", "in_progress"]:
        buttons.append([
            InlineKeyboardButton(
                text="📋 Посмотреть все списки",
                callback_data=f"view_all_lists:{game.id}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Назад к играм",
            callback_data="back_to_mygames"
        )
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("submit_list:"))
async def start_submit_list(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Начать отправку списка для выбранной игры"""
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    status_value = game.status.value if hasattr(game.status, 'value') else game.status
    if status_value != "collecting":
        await callback.answer("Приём списков закрыт", show_alert=True)
        return
    
    # Проверяем есть ли списки армий
    army_service = ArmyListService(session)
    army_lists = await army_service.get_user_army_lists(callback.from_user.id)
    
    if not army_lists:
        await callback.message.edit_text(
            "📭 У вас нет сохранённых списков армий.\n\n"
            "Отправьте JSON файл списка армии из game-datacards\n"
            "(List → Export as Datasource)"
        )
        await callback.answer()
        return
    
    title = game.title or f"Игра #{game.id}"
    await callback.message.edit_text(
        f"📋 Выберите список армии для игры <b>{title}</b>:",
        parse_mode="HTML",
        reply_markup=army_lists_keyboard(army_lists, for_submit=True, game_id=game_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("select_army_list:"))
async def select_army_list_for_game(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Выбор списка армии для игры"""
    from datetime import datetime
    
    parts = callback.data.split(":")
    game_id = int(parts[1])
    army_list_id = int(parts[2])
    
    # Получаем игру для проверки лимита
    game_service = GameService(session)
    game = await game_service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    # Проверяем статус игры
    status_value = game.status.value if hasattr(game.status, 'value') else game.status
    if status_value != "collecting":
        await callback.answer("Приём списков для этой игры закрыт", show_alert=True)
        return
    
    # Проверяем дедлайн
    if game.deadline and datetime.utcnow() > game.deadline:
        await callback.message.edit_text(
            f"❌ <b>Дедлайн истёк!</b>\n\n"
            f"⏰ Дедлайн был: {game.deadline.strftime('%d.%m.%Y %H:%M')} UTC\n\n"
            f"Приём списков для этой игры закрыт.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад к играм", callback_data="back_to_mygames")]
            ])
        )
        await callback.answer("Дедлайн истёк", show_alert=True)
        return
    
    # Валидируем список перед прикреплением
    army_service = ArmyListService(session)
    is_valid, messages = await army_service.validate_army_list_for_game(army_list_id)
    
    if not is_valid:
        error_text = "❌ <b>Список армии не прошёл валидацию:</b>\n\n" + "\n".join(f"• {e}" for e in messages[:10])
        await callback.message.edit_text(
            error_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить список", callback_data=f"refresh_army_list:{army_list_id}")],
                [InlineKeyboardButton(text="◀️ Выбрать другой", callback_data=f"submit_list:{game_id}")]
            ])
        )
        await callback.answer("Валидация не пройдена", show_alert=True)
        return
    
    # Проверяем лимит очков
    army_list = await army_service.get_army_list(army_list_id)
    if game.points_limit and army_list.total_points > game.points_limit:
        await callback.message.edit_text(
            f"❌ <b>Армия превышает лимит очков!</b>\n\n"
            f"🎯 Лимит игры: {game.points_limit} pts\n"
            f"⚔️ Ваша армия: {army_list.total_points} pts\n"
            f"📛 Превышение: {army_list.total_points - game.points_limit} pts\n\n"
            f"Выберите другую армию или уменьшите текущую.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Выбрать другой", callback_data=f"submit_list:{game_id}")]
            ])
        )
        await callback.answer("Армия превышает лимит", show_alert=True)
        return
    
    # Если есть предупреждения — показываем их
    if messages:
        warning_text = "\n".join(messages)
        await callback.answer(warning_text[:200], show_alert=True)
    
    result = await game_service.submit_army_list(
        telegram_id=callback.from_user.id,
        game_id=game_id,
        army_list_id=army_list_id
    )
    
    if not result.success:
        await callback.answer(result.error, show_alert=True)
        return
    
    await callback.message.edit_text("✅ Список армии отправлен!")
    await callback.answer()
    
    # Если все отправили — рассылаем всем
    if result.all_submitted:
        game = result.game
        
        # Формируем текст со всеми списками
        lists_text = format_army_lists(game)
        
        # Добавляем информацию о дате игры если есть
        scheduled_info = ""
        if game.scheduled_at:
            scheduled_info = f"\n\n🕐 <b>Дата игры:</b> {game.scheduled_at.strftime('%d.%m.%Y %H:%M')} UTC"
        
        # Рассылаем всем участникам
        for participant in game.participants:
            try:
                await bot.send_message(
                    chat_id=participant.user.telegram_id,
                    text=lists_text + scheduled_info,
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Failed to notify {participant.user.telegram_id}: {e}")
        
        # Уведомляем админа
        try:
            await bot.send_message(
                chat_id=game.created_by,
                text=f"✅ Все списки собраны для игры <b>{game.title or f'#{game.id}'}</b>!",
                parse_mode="HTML",
                reply_markup=game_management_keyboard(game)
            )
        except:
            pass


@router.callback_query(F.data.startswith("resubmit_list:"))
async def resubmit_list(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Переотправить список армии"""
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    success = await service.clear_army_list_for_resubmit(callback.from_user.id, game_id)
    
    if not success:
        await callback.answer("Переотправка недоступна", show_alert=True)
        return
    
    # Показываем выбор списков
    army_service = ArmyListService(session)
    army_lists = await army_service.get_user_army_lists(callback.from_user.id)
    
    if not army_lists:
        await callback.message.edit_text(
            "🔄 Ваш предыдущий список удалён.\n\n"
            "📭 У вас нет сохранённых списков армий.\n"
            "Отправьте JSON файл списка армии."
        )
        await callback.answer()
        return
    
    game = await service.get_game(game_id)
    title = game.title or f"Игра #{game.id}"
    
    await callback.message.edit_text(
        f"🔄 Ваш предыдущий список удалён.\n\n"
        f"📋 Выберите новый список армии для игры <b>{title}</b>:",
        parse_mode="HTML",
        reply_markup=army_lists_keyboard(army_lists, for_submit=True, game_id=game_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("game_status:"))
@admin_required
async def game_status(callback: CallbackQuery, session: AsyncSession, **kwargs):
    """Показать статус списков"""
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    await callback.message.edit_text(
        format_game_info(game, detailed=True),
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("assign_teams:"))
@admin_required
async def assign_teams(callback: CallbackQuery, session: AsyncSession, **kwargs):
    """Показать интерфейс распределения по командам"""
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"👥 <b>Распределение по командам</b>\n\n"
        f"Нажимайте 🅰️ или 🅱️ для назначения команды:",
        parse_mode="HTML",
        reply_markup=team_assignment_keyboard(game)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("random_teams:"))
@admin_required
async def random_teams(callback: CallbackQuery, session: AsyncSession, **kwargs):
    """Случайно распределить участников по командам"""
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    await service.auto_assign_teams(game_id)
    await session.commit()
    
    game = await service.get_game(game_id)
    
    await callback.message.edit_reply_markup(
        reply_markup=team_assignment_keyboard(game)
    )
    await callback.answer("🎲 Команды распределены случайно!")


@router.callback_query(F.data.startswith("set_team:"))
@admin_required
async def set_team(callback: CallbackQuery, session: AsyncSession, **kwargs):
    """Назначить команду участнику"""
    parts = callback.data.split(":")
    game_id = int(parts[1])
    participant_id = int(parts[2])
    team_letter = parts[3]
    
    team = Team.TEAM_A if team_letter == "A" else Team.TEAM_B
    
    repo = ParticipantRepository(session)
    await repo.set_team(participant_id, team)
    await session.commit()
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    await callback.message.edit_reply_markup(
        reply_markup=team_assignment_keyboard(game)
    )
    await callback.answer(f"Назначен в команду {team_letter}")


@router.callback_query(F.data.startswith("teams_done:"))
@admin_required
async def teams_done(callback: CallbackQuery, session: AsyncSession, **kwargs):
    """Завершить распределение команд"""
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    # Проверяем, что все распределены
    unassigned = [p for p in game.participants if not p.team]
    if unassigned:
        names = [p.user.username or p.user.first_name for p in unassigned]
        await callback.answer(
            f"Не распределены: {', '.join(names)}", 
            show_alert=True
        )
        return
    
    await callback.message.edit_text(
        format_game_info(game, detailed=True),
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game)
    )
    await callback.answer("✅ Команды распределены!")


@router.callback_query(F.data.startswith("start_game:"))
@admin_required
async def start_game(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Начать игру"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.mission_service import (
        generate_random_mission, get_mission_images, 
        format_mission_info, MissionResult
    )
    
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    # Проверяем, есть ли участники без команды
    unassigned = [p for p in game.participants if not p.team]
    auto_assigned = False
    
    if unassigned:
        # Автоматически распределяем по командам
        await service.auto_assign_teams(game_id)
        await session.commit()
        game = await service.get_game(game_id)
        auto_assigned = True
    
    # Генерируем миссию
    mission = generate_random_mission()
    if mission:
        game.mission_data = mission.to_dict()
        await session.commit()
    
    success = await service.start_game(game_id)
    
    if not success:
        await callback.answer("Не удалось начать игру", show_alert=True)
        return
    
    game = await service.get_game(game_id)
    
    auto_text = "\n\n<i>⚠️ Команды были распределены автоматически</i>" if auto_assigned else ""
    
    # Отправляем миссию всем участникам
    if mission:
        primary_img, deployment_img, terrain_img = get_mission_images(mission)
        mission_text = format_mission_info(mission)
        
        for participant in game.participants:
            try:
                # Отправляем текст миссии
                await bot.send_message(
                    chat_id=participant.user.telegram_id,
                    text=f"🎮 <b>Игра началась!</b>\n\n{mission_text}",
                    parse_mode="HTML"
                )
                
                # Отправляем изображения миссии
                media_group = []
                if primary_img:
                    media_group.append(InputMediaPhoto(
                        media=BufferedInputFile(primary_img, "primary_mission.png"),
                        caption="📋 Primary Mission"
                    ))
                if deployment_img:
                    media_group.append(InputMediaPhoto(
                        media=BufferedInputFile(deployment_img, "deployment.png"),
                        caption="🗺 Deployment"
                    ))
                if terrain_img:
                    media_group.append(InputMediaPhoto(
                        media=BufferedInputFile(terrain_img, "terrain_layout.png"),
                        caption="🏔 Terrain Layout"
                    ))
                
                if media_group:
                    await bot.send_media_group(
                        chat_id=participant.user.telegram_id,
                        media=media_group
                    )
            except Exception as e:
                print(f"Error sending mission to {participant.user.telegram_id}: {e}")
    
    await callback.message.edit_text(
        f"▶️ <b>Игра началась!</b>{auto_text}\n\n{format_game_info(game, detailed=True)}",
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game)
    )
    await callback.answer("Игра началась!")


@router.callback_query(F.data.startswith("record_result:"))
@admin_required
async def record_result(callback: CallbackQuery, session: AsyncSession, **kwargs):
    """Показать выбор победителя"""
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    # Показываем состав команд
    team_a = [p for p in game.participants if p.team == Team.TEAM_A.value]
    team_b = [p for p in game.participants if p.team == Team.TEAM_B.value]
    
    team_a_names = ", ".join(p.user.username or p.user.first_name or "?" for p in team_a)
    team_b_names = ", ".join(p.user.username or p.user.first_name or "?" for p in team_b)
    
    await callback.message.edit_text(
        f"🏆 <b>Кто победил?</b>\n\n"
        f"🅰️ Команда A: {team_a_names}\n"
        f"🅱️ Команда B: {team_b_names}",
        parse_mode="HTML",
        reply_markup=winner_select_keyboard(game_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_winner:"))
@admin_required
async def set_winner(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Установить победителя"""
    parts = callback.data.split(":")
    game_id = int(parts[1])
    winner_letter = parts[2]
    
    winner_team = Team.TEAM_A if winner_letter == "A" else Team.TEAM_B
    
    service = GameService(session)
    success = await service.set_winner(game_id, winner_team)
    
    if not success:
        await callback.answer("Не удалось записать результат", show_alert=True)
        return
    
    game = await service.get_game(game_id)
    
    # Уведомляем всех участников
    result_text = format_game_result(game)
    
    for participant in game.participants:
        try:
            await bot.send_message(
                chat_id=participant.user.telegram_id,
                text=result_text,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Failed to notify {participant.user.telegram_id}: {e}")
    
    await callback.message.edit_text(
        f"✅ <b>Результат записан!</b>\n\n{format_game_info(game, detailed=True)}",
        parse_mode="HTML"
    )
    await callback.answer("Результат записан!")


@router.callback_query(F.data.startswith("cancel_game:"))
@admin_required
async def cancel_game_confirm(callback: CallbackQuery, **kwargs):
    """Подтверждение отмены игры"""
    game_id = int(callback.data.split(":")[1])
    
    await callback.message.edit_text(
        "❓ <b>Вы уверены, что хотите отменить игру?</b>",
        parse_mode="HTML",
        reply_markup=confirm_keyboard("cancel_game", game_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_cancel_game:"))
@admin_required
async def cancel_game(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Отменить игру"""
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    # Уведомляем участников
    title = game.title or f"Игра #{game.id}"
    for participant in game.participants:
        try:
            await bot.send_message(
                chat_id=participant.user.telegram_id,
                text=f"❌ Игра <b>{title}</b> отменена.",
                parse_mode="HTML"
            )
        except:
            pass
    
    success = await service.cancel_game(game_id)
    
    if not success:
        await callback.answer("Не удалось отменить игру", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"❌ <b>Игра отменена</b>\n\n{format_game_info(game)}",
        parse_mode="HTML"
    )
    await callback.answer("Игра отменена")


@router.callback_query(F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery, session: AsyncSession):
    """Отмена текущего действия"""
    await callback.message.edit_text("❌ Действие отменено")
    await callback.answer()


@router.callback_query(F.data.startswith("view_all_lists:"))
async def view_all_lists(callback: CallbackQuery, session: AsyncSession):
    """Просмотр всех списков армий с возможностью генерации карточек"""
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    # Проверяем что пользователь участник
    is_participant = any(p.user.telegram_id == callback.from_user.id for p in game.participants)
    if not is_participant:
        await callback.answer("Вы не участвуете в этой игре", show_alert=True)
        return
    
    lists_text = format_army_lists(game)
    
    # Создаём кнопки для каждого участника с армией
    buttons = []
    for p in game.participants:
        if p.army_list_id and p.army_list:
            name = p.user.username or p.user.first_name or f"User {p.user.telegram_id}"
            army_name = p.army_list.name[:20]
            
            # Кнопки карточек и стратагем в одном ряду
            buttons.append([
                InlineKeyboardButton(
                    text=f"🎴 {name}",
                    callback_data=f"user_army_cards:{game.id}:{p.id}"
                ),
                InlineKeyboardButton(
                    text=f"⚔️ Стратагемы",
                    callback_data=f"user_stratagems:{game.id}:{p.id}"
                )
            ])
    
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад к игре", callback_data=f"view_my_game:{game.id}")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        lists_text + "\n\n<i>Нажмите для просмотра карточек:</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_mygames")
async def back_to_mygames(callback: CallbackQuery, session: AsyncSession):
    """Вернуться к списку игр"""
    service = GameService(session)
    all_games = await service.get_all_active_games_for_user(callback.from_user.id)
    
    if not all_games:
        await callback.message.edit_text("📭 У вас нет активных игр.")
        await callback.answer()
        return
    
    pending = sum(1 for p in all_games if not p.army_list_id and (p.game.status.value if hasattr(p.game.status, 'value') else p.game.status) == "collecting")
    ready = sum(1 for p in all_games if (p.game.status.value if hasattr(p.game.status, 'value') else p.game.status) in ["ready", "in_progress"])
    
    text = f"🎮 <b>Ваши активные игры ({len(all_games)}):</b>\n\n"
    if pending > 0:
        text += f"⏳ Ожидают ваш список: {pending}\n"
    if ready > 0:
        text += f"⚔️ Готовы к игре: {ready}\n"
    text += "\nНажмите на игру для подробностей:"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=my_games_keyboard(all_games)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("user_army_cards:"))
async def user_army_cards(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Показать карточки армии участника (для других игроков)"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.card_generator import (
        generate_army_cards, generate_army_rules_card, 
        generate_detachment_rules_card, extract_enhancements_info
    )
    from wh40k_bot.services.datasource_service import find_faction_file, load_faction_data
    
    parts = callback.data.split(":")
    game_id = int(parts[1])
    participant_id = int(parts[2])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    # Проверяем что пользователь участник игры
    is_participant = any(p.user.telegram_id == callback.from_user.id for p in game.participants)
    if not is_participant:
        await callback.answer("Вы не участвуете в этой игре", show_alert=True)
        return
    
    # Получаем участника чьи карточки смотрим
    target_participant = None
    for p in game.participants:
        if p.id == participant_id:
            target_participant = p
            break
    
    if not target_participant or not target_participant.army_list_id:
        await callback.answer("Список армии не найден", show_alert=True)
        return
    
    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(target_participant.army_list_id)
    
    if not army_list:
        await callback.answer("Список армии не найден", show_alert=True)
        return
    
    user = target_participant.user
    user_name = user.username or user.first_name or f"User {user.telegram_id}"
    
    await callback.answer("🎴 Генерирую карточки...")
    status_msg = await callback.message.answer(f"⏳ Генерация карточек для {user_name}...")
    
    try:
        all_cards = []
        
        # Загружаем данные фракции
        faction_data = None
        if army_list.faction:
            faction_file = find_faction_file(army_list.faction)
            if faction_file:
                faction_data = load_faction_data(faction_file)
        
        # Army Rules
        if faction_data:
            army_rules_card = generate_army_rules_card(faction_data)
            if army_rules_card:
                all_cards.append(army_rules_card)
        
        # Объединённая карточка Detachment (rules + enhancements)
        if army_list.detachment:
            enhancements = extract_enhancements_info(army_list.json_data)
            det_card = generate_detachment_rules_card(faction_data, army_list.detachment, enhancements)
            if det_card:
                all_cards.append(det_card)
        
        # Юниты
        unit_cards = generate_army_cards(army_list.json_data)
        all_cards.extend(unit_cards)
        
        if not all_cards:
            await status_msg.edit_text("❌ Не удалось сгенерировать карточки")
            return
        
        await status_msg.edit_text(f"📤 Отправляю {len(all_cards)} карточек...")
        
        for i in range(0, len(all_cards), 10):
            batch = all_cards[i:i+10]
            media_group = [InputMediaPhoto(media=BufferedInputFile(c, f"card_{i+j}.png")) 
                          for j, c in enumerate(batch)]
            try:
                await bot.send_media_group(chat_id=callback.from_user.id, media=media_group)
            except Exception as e:
                print(f"Error sending batch: {e}")
        
        await status_msg.edit_text(
            f"✅ Отправлено {len(all_cards)} карточек для <b>{user_name}</b> ({army_list.name})", 
            parse_mode="HTML"
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка генерации: {e}")


@router.callback_query(F.data.startswith("user_stratagems:"))
async def user_stratagems(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Показать стратагемы армии участника (для других игроков)"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.card_generator import generate_stratagems_cards
    from wh40k_bot.services.datasource_service import find_faction_file, load_faction_data
    
    parts = callback.data.split(":")
    game_id = int(parts[1])
    participant_id = int(parts[2])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    # Проверяем что пользователь участник игры
    is_participant = any(p.user.telegram_id == callback.from_user.id for p in game.participants)
    if not is_participant:
        await callback.answer("Вы не участвуете в этой игре", show_alert=True)
        return
    
    # Получаем участника чьи стратагемы смотрим
    target_participant = None
    for p in game.participants:
        if p.id == participant_id:
            target_participant = p
            break
    
    if not target_participant or not target_participant.army_list_id:
        await callback.answer("Список армии не найден", show_alert=True)
        return
    
    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(target_participant.army_list_id)
    
    if not army_list:
        await callback.answer("Список армии не найден", show_alert=True)
        return
    
    if not army_list.faction or not army_list.detachment:
        await callback.answer("Фракция или детачмент не указаны", show_alert=True)
        return
    
    user = target_participant.user
    user_name = user.username or user.first_name or f"User {user.telegram_id}"
    
    await callback.answer("⚔️ Генерирую стратагемы...")
    status_msg = await callback.message.answer(f"⏳ Генерация стратагем для {user_name}...")
    
    try:
        # Загружаем данные фракции
        faction_file = find_faction_file(army_list.faction)
        if not faction_file:
            await status_msg.edit_text("❌ Фракция не найдена в datasources")
            return
        
        faction_data = load_faction_data(faction_file)
        if not faction_data:
            await status_msg.edit_text("❌ Не удалось загрузить данные фракции")
            return
        
        # Генерируем карточки стратагем
        stratagem_cards = generate_stratagems_cards(faction_data, army_list.detachment)
        
        if not stratagem_cards:
            await status_msg.edit_text(
                f"❌ Стратагемы для детачмента <b>{army_list.detachment}</b> не найдены",
                parse_mode="HTML"
            )
            return
        
        await status_msg.edit_text(f"📤 Отправляю {len(stratagem_cards)} стратагем...")
        
        # Отправляем альбомами по 10
        for i in range(0, len(stratagem_cards), 10):
            batch = stratagem_cards[i:i+10]
            media_group = [InputMediaPhoto(media=BufferedInputFile(c, f"stratagem_{i+j}.png")) 
                          for j, c in enumerate(batch)]
            try:
                await bot.send_media_group(chat_id=callback.from_user.id, media=media_group)
            except Exception as e:
                print(f"Error sending batch: {e}")
        
        await status_msg.edit_text(
            f"✅ Отправлено {len(stratagem_cards)} стратагем для <b>{user_name}</b>\n"
            f"Детачмент: {army_list.detachment}",
            parse_mode="HTML"
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка генерации: {e}")


# === Обработчики для списков армий ===

@router.callback_query(F.data == "upload_army_list")
async def upload_army_list_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос на загрузку списка армии"""
    await callback.message.edit_text(
        "📤 <b>Загрузка списка армии</b>\n\n"
        "Отправьте JSON файл списка армии.\n\n"
        "<i>Как получить файл:</i>\n"
        "1. Откройте game-datacards\n"
        "2. List → Export as Datasource\n"
        "3. Отправьте полученный .json файл сюда",
        parse_mode="HTML"
    )
    await state.set_state(UploadArmyList.waiting_for_file)
    await callback.answer()


@router.callback_query(F.data.startswith("view_army_list:"))
async def view_army_list(callback: CallbackQuery, session: AsyncSession):
    """Просмотр списка армии"""
    army_list_id = int(callback.data.split(":")[1])
    
    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(army_list_id)
    
    if not army_list:
        await callback.answer("Список не найден", show_alert=True)
        return
    
    # Получаем статистику
    stats = await army_service.get_army_list_stats(army_list_id)
    
    # Формируем текст
    text = format_army_list_full(army_list)
    
    # Добавляем статистику
    text += "\n\n📊 <b>Статистика:</b>\n"
    if stats["total"] > 0:
        text += f"  🎮 Всего игр: {stats['total']}\n"
        text += f"  ✅ Побед: {stats['wins']}\n"
        text += f"  ❌ Поражений: {stats['losses']}\n"
        if stats["draws"] > 0:
            text += f"  ➖ Ничьих: {stats['draws']}\n"
        text += f"  📈 Винрейт: {stats['win_rate']}%"
    else:
        text += "  <i>Ещё не использовался в играх</i>"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=army_list_actions_keyboard(army_list_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_army_list:"))
async def delete_army_list_confirm(callback: CallbackQuery):
    """Подтверждение удаления списка армии"""
    army_list_id = int(callback.data.split(":")[1])
    
    await callback.message.edit_text(
        "❓ <b>Удалить этот список армии?</b>\n\n"
        "⚠️ Это действие нельзя отменить.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_army:{army_list_id}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"view_army_list:{army_list_id}")
            ]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("refresh_army_list:"))
async def refresh_army_list(callback: CallbackQuery, session: AsyncSession):
    """Обновить список армии из datasources"""
    army_list_id = int(callback.data.split(":")[1])
    
    army_service = ArmyListService(session)
    
    success, changes = await army_service.update_army_list_from_datasources(
        callback.from_user.id,
        army_list_id
    )
    
    if not success:
        await callback.answer("❌ " + "; ".join(changes), show_alert=True)
        return
    
    # Показываем изменения
    army_list = await army_service.get_army_list(army_list_id)
    stats = await army_service.get_army_list_stats(army_list_id)
    
    text = format_army_list_full(army_list)
    
    # Добавляем статистику
    text += "\n\n📊 <b>Статистика:</b>\n"
    if stats["total"] > 0:
        text += f"  🎮 Всего игр: {stats['total']}\n"
        text += f"  ✅ Побед: {stats['wins']}\n"
        text += f"  ❌ Поражений: {stats['losses']}\n"
        if stats["draws"] > 0:
            text += f"  ➖ Ничьих: {stats['draws']}\n"
        text += f"  📈 Винрейт: {stats['win_rate']}%"
    else:
        text += "  <i>Ещё не использовался в играх</i>"
    
    # Добавляем информацию об обновлении
    text += "\n\n🔄 <b>Результат обновления:</b>\n"
    for change in changes[:10]:  # Максимум 10 изменений
        text += f"  {change}\n"
    
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=army_list_actions_keyboard(army_list_id)
        )
    except Exception:
        # Если сообщение не изменилось - просто отвечаем
        pass
    
    await callback.answer("✅ Обновлено!")


@router.callback_query(F.data.startswith("show_army_cards:"))
async def show_army_cards(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Показать карточки юнитов для списка армии"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.card_generator import (
        generate_army_cards, generate_army_rules_card, 
        generate_detachment_rules_card, extract_enhancements_info
    )
    from wh40k_bot.services.datasource_service import find_faction_file, load_faction_data
    
    army_list_id = int(callback.data.split(":")[1])
    
    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(army_list_id)
    
    if not army_list:
        await callback.answer("Список не найден", show_alert=True)
        return
    
    await callback.answer("🎴 Генерирую карточки...")
    
    status_msg = await callback.message.answer("⏳ Генерация карточек юнитов...")
    
    try:
        all_cards = []
        
        # Загружаем данные фракции для Army Rules
        faction_data = None
        if army_list.faction:
            faction_file = find_faction_file(army_list.faction)
            if faction_file:
                faction_data = load_faction_data(faction_file)
        
        # 1. Army Rules карточка
        if faction_data:
            army_rules_card = generate_army_rules_card(faction_data)
            if army_rules_card:
                all_cards.append(army_rules_card)
        
        # 2. Объединённая карточка Detachment (rules + enhancements)
        if army_list.detachment:
            enhancements = extract_enhancements_info(army_list.json_data)
            det_card = generate_detachment_rules_card(faction_data, army_list.detachment, enhancements)
            if det_card:
                all_cards.append(det_card)
        
        # 3. Карточки юнитов
        unit_cards = generate_army_cards(army_list.json_data)
        all_cards.extend(unit_cards)
        
        if not all_cards:
            await status_msg.edit_text("❌ Не удалось сгенерировать карточки")
            return
        
        await status_msg.edit_text(f"📤 Отправляю {len(all_cards)} карточек...")
        
        # Отправляем альбомами по 10 карточек
        for i in range(0, len(all_cards), 10):
            batch = all_cards[i:i+10]
            
            media_group = []
            for j, card_bytes in enumerate(batch):
                photo = BufferedInputFile(card_bytes, filename=f"card_{i+j+1}.png")
                media_group.append(InputMediaPhoto(media=photo))
            
            try:
                await bot.send_media_group(
                    chat_id=callback.from_user.id,
                    media=media_group
                )
            except Exception as e:
                print(f"Error sending batch {i//10 + 1}: {e}")
                continue
        
        await status_msg.edit_text(
            f"✅ Отправлено {len(all_cards)} карточек для <b>{army_list.name}</b>", 
            parse_mode="HTML"
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка генерации: {e}")


@router.callback_query(F.data.startswith("show_stratagems:"))
async def show_stratagems(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Показать карточки стратагем для детачмента армии"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.card_generator import generate_stratagems_cards
    from wh40k_bot.services.datasource_service import find_faction_file, load_faction_data
    
    army_list_id = int(callback.data.split(":")[1])
    
    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(army_list_id)
    
    if not army_list:
        await callback.answer("Список не найден", show_alert=True)
        return
    
    if not army_list.detachment:
        await callback.answer("Детачмент не определён", show_alert=True)
        return
    
    await callback.answer("🎴 Генерирую стратагемы...")
    
    status_msg = await callback.message.answer("⏳ Генерация карточек стратагем...")
    
    try:
        # Загружаем данные фракции
        faction_data = None
        if army_list.faction:
            faction_file = find_faction_file(army_list.faction)
            if faction_file:
                faction_data = load_faction_data(faction_file)
        
        if not faction_data:
            await status_msg.edit_text("❌ Не удалось загрузить данные фракции")
            return
        
        cards = generate_stratagems_cards(faction_data, army_list.detachment)
        
        if not cards:
            await status_msg.edit_text(f"❌ Стратагемы для детачмента '{army_list.detachment}' не найдены")
            return
        
        await status_msg.edit_text(f"📤 Отправляю {len(cards)} стратагем...")
        
        # Отправляем альбомами
        for i in range(0, len(cards), 10):
            batch = cards[i:i+10]
            
            media_group = []
            for j, card_bytes in enumerate(batch):
                photo = BufferedInputFile(card_bytes, filename=f"stratagem_{i+j+1}.png")
                media_group.append(InputMediaPhoto(media=photo))
            
            try:
                await bot.send_media_group(
                    chat_id=callback.from_user.id,
                    media=media_group
                )
            except Exception as e:
                print(f"Error sending stratagems batch: {e}")
                continue
        
        await status_msg.edit_text(
            f"✅ Отправлено {len(cards)} стратагем для <b>{army_list.detachment}</b>", 
            parse_mode="HTML"
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка генерации: {e}")


@router.callback_query(F.data.startswith("game_army_cards:"))
@admin_required
async def game_army_cards(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Показать меню выбора армии для просмотра карточек"""
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    # Создаём клавиатуру с участниками
    buttons = []
    for p in game.participants:
        if p.army_list_id:
            user = p.user
            name = user.username or user.first_name or f"User {user.telegram_id}"
            
            # Кнопка для карточек юнитов
            buttons.append([
                InlineKeyboardButton(
                    text=f"🎴 {name}",
                    callback_data=f"show_participant_cards:{game.id}:{p.id}"
                ),
                InlineKeyboardButton(
                    text=f"⚔️ Стратагемы",
                    callback_data=f"show_participant_stratagems:{game.id}:{p.id}"
                )
            ])
    
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_view_game:{game.id}")
    ])
    
    await callback.message.edit_text(
        f"🎴 <b>Карточки армий для игры</b>\n\n"
        f"Выберите участника для просмотра карточек:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("show_participant_cards:"))
@admin_required
async def show_participant_cards(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Показать карточки армии участника игры"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.card_generator import (
        generate_army_cards, generate_army_rules_card, 
        generate_detachment_rules_card, extract_enhancements_info
    )
    from wh40k_bot.services.datasource_service import find_faction_file, load_faction_data
    
    parts = callback.data.split(":")
    game_id = int(parts[1])
    participant_id = int(parts[2])
    
    # Получаем участника
    repo = ParticipantRepository(session)
    participant = await repo.get_by_id(participant_id)
    
    if not participant or not participant.army_list_id:
        await callback.answer("Список армии не найден", show_alert=True)
        return
    
    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(participant.army_list_id)
    
    if not army_list:
        await callback.answer("Список армии не найден", show_alert=True)
        return
    
    user = participant.user
    user_name = user.username or user.first_name or f"User {user.telegram_id}"
    
    await callback.answer("🎴 Генерирую карточки...")
    status_msg = await callback.message.answer(f"⏳ Генерация карточек для {user_name}...")
    
    try:
        all_cards = []
        
        # Загружаем данные фракции
        faction_data = None
        if army_list.faction:
            faction_file = find_faction_file(army_list.faction)
            if faction_file:
                faction_data = load_faction_data(faction_file)
        
        # Army Rules
        if faction_data:
            army_rules_card = generate_army_rules_card(faction_data)
            if army_rules_card:
                all_cards.append(army_rules_card)
        
        # Объединённая карточка Detachment (rules + enhancements)
        if army_list.detachment:
            enhancements = extract_enhancements_info(army_list.json_data)
            det_card = generate_detachment_rules_card(faction_data, army_list.detachment, enhancements)
            if det_card:
                all_cards.append(det_card)
        
        # Юниты
        unit_cards = generate_army_cards(army_list.json_data)
        all_cards.extend(unit_cards)
        
        if not all_cards:
            await status_msg.edit_text("❌ Не удалось сгенерировать карточки")
            return
        
        await status_msg.edit_text(f"📤 Отправляю {len(all_cards)} карточек...")
        
        for i in range(0, len(all_cards), 10):
            batch = all_cards[i:i+10]
            media_group = [InputMediaPhoto(media=BufferedInputFile(c, f"card_{i+j}.png")) 
                          for j, c in enumerate(batch)]
            try:
                await bot.send_media_group(chat_id=callback.from_user.id, media=media_group)
            except Exception as e:
                print(f"Error sending batch: {e}")
        
        await status_msg.edit_text(
            f"✅ Отправлено {len(all_cards)} карточек для <b>{user_name}</b> ({army_list.name})", 
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("show_participant_stratagems:"))
@admin_required
async def show_participant_stratagems(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Показать стратагемы детачмента участника"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.card_generator import generate_stratagems_cards
    from wh40k_bot.services.datasource_service import find_faction_file, load_faction_data
    
    parts = callback.data.split(":")
    game_id = int(parts[1])
    participant_id = int(parts[2])
    
    repo = ParticipantRepository(session)
    participant = await repo.get_by_id(participant_id)
    
    if not participant or not participant.army_list_id:
        await callback.answer("Список армии не найден", show_alert=True)
        return
    
    army_service = ArmyListService(session)
    army_list = await army_service.get_army_list(participant.army_list_id)
    
    if not army_list or not army_list.detachment:
        await callback.answer("Детачмент не определён", show_alert=True)
        return
    
    user = participant.user
    user_name = user.username or user.first_name or f"User {user.telegram_id}"
    
    await callback.answer("🎴 Генерирую стратагемы...")
    status_msg = await callback.message.answer(f"⏳ Генерация стратагем для {user_name}...")
    
    try:
        faction_data = None
        if army_list.faction:
            faction_file = find_faction_file(army_list.faction)
            if faction_file:
                faction_data = load_faction_data(faction_file)
        
        if not faction_data:
            await status_msg.edit_text("❌ Не удалось загрузить данные фракции")
            return
        
        cards = generate_stratagems_cards(faction_data, army_list.detachment)
        
        if not cards:
            await status_msg.edit_text(f"❌ Стратагемы для '{army_list.detachment}' не найдены")
            return
        
        await status_msg.edit_text(f"📤 Отправляю {len(cards)} стратагем...")
        
        for i in range(0, len(cards), 10):
            batch = cards[i:i+10]
            media_group = [InputMediaPhoto(media=BufferedInputFile(c, f"strat_{i+j}.png")) 
                          for j, c in enumerate(batch)]
            try:
                await bot.send_media_group(chat_id=callback.from_user.id, media=media_group)
            except Exception as e:
                print(f"Error sending stratagems: {e}")
        
        await status_msg.edit_text(
            f"✅ Отправлено {len(cards)} стратагем для <b>{user_name}</b> ({army_list.detachment})", 
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("confirm_delete_army:"))
async def delete_army_list(callback: CallbackQuery, session: AsyncSession):
    """Удаление списка армии"""
    army_list_id = int(callback.data.split(":")[1])
    
    army_service = ArmyListService(session)
    success = await army_service.delete_army_list(callback.from_user.id, army_list_id)
    
    if not success:
        await callback.answer("Не удалось удалить список", show_alert=True)
        return
    
    await callback.answer("Список удалён!")
    
    # Показываем оставшиеся списки
    army_lists = await army_service.get_user_army_lists(callback.from_user.id)
    
    if not army_lists:
        await callback.message.edit_text(
            "📭 У вас нет сохранённых списков армий.\n\n"
            "Отправьте JSON файл списка армии.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Загрузить список", callback_data="upload_army_list")]
            ])
        )
    else:
        await callback.message.edit_text(
            f"📋 <b>Ваши списки армий ({len(army_lists)}):</b>",
            parse_mode="HTML",
            reply_markup=army_lists_keyboard(army_lists)
        )


@router.callback_query(F.data == "back_to_army_lists")
async def back_to_army_lists(callback: CallbackQuery, session: AsyncSession):
    """Вернуться к списку армий"""
    army_service = ArmyListService(session)
    army_lists = await army_service.get_user_army_lists(callback.from_user.id)
    
    if not army_lists:
        await callback.message.edit_text(
            "📭 У вас нет сохранённых списков армий.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Загрузить список", callback_data="upload_army_list")]
            ])
        )
    else:
        await callback.message.edit_text(
            f"📋 <b>Ваши списки армий ({len(army_lists)}):</b>",
            parse_mode="HTML",
            reply_markup=army_lists_keyboard(army_lists)
        )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    """Пустой обработчик для информационных кнопок"""
    await callback.answer()


@router.callback_query(F.data == "update_datasources")
@admin_required
async def update_datasources(callback: CallbackQuery, **kwargs):
    """Обновить datasources из git"""
    import subprocess
    import os
    
    datasources_path = "/app/datasources"
    
    # Проверяем существует ли директория
    if not os.path.exists(datasources_path):
        await callback.answer("❌ Директория datasources не найдена", show_alert=True)
        return
    
    await callback.answer("🔄 Обновляю...")
    
    try:
        # Проверяем есть ли .git
        git_dir = os.path.join(datasources_path, ".git")
        
        if os.path.exists(git_dir):
            # Есть git - делаем pull
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=datasources_path,
                capture_output=True,
                text=True,
                timeout=60
            )
        else:
            # Нет git - клонируем заново
            # Удаляем содержимое и клонируем
            result = subprocess.run(
                ["git", "clone", "https://github.com/game-datacards/datasources.git", "."],
                cwd=datasources_path,
                capture_output=True,
                text=True,
                timeout=120
            )
        
        if result.returncode == 0:
            output = result.stdout.strip() or "Already up to date"
            await callback.message.edit_text(
                f"✅ <b>Datasources обновлены!</b>\n\n"
                f"<code>{output[:500]}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Обновить ещё раз", callback_data="update_datasources")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")]
                ])
            )
        else:
            error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            await callback.message.edit_text(
                f"❌ <b>Ошибка обновления</b>\n\n"
                f"<code>{error[:500]}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="update_datasources")]
                ])
            )
    except subprocess.TimeoutExpired:
        await callback.message.edit_text(
            "❌ <b>Timeout</b>\n\nОбновление заняло слишком много времени.",
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ <b>Ошибка:</b> {e}",
            parse_mode="HTML"
        )


@router.callback_query(F.data == "back_to_admin")
@admin_required
async def back_to_admin(callback: CallbackQuery, **kwargs):
    """Вернуться в админ-панель"""
    text = [
        "🔧 <b>Админ-панель</b>",
        "",
        "<b>Управление играми:</b>",
        "/newgame — создать игру",
        "/games — список активных игр",
        "/game [id] — управление игрой",
        "/users — список пользователей",
        "",
        "<b>Данные:</b>",
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить datasources", callback_data="update_datasources")]
    ])
    
    await callback.message.edit_text("\n".join(text), parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("show_mission:"))
@admin_required
async def show_mission(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Показать текущую миссию игры"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.mission_service import (
        get_mission_images, format_mission_info, MissionResult
    )
    
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    if not game.mission_data:
        await callback.answer("Миссия не назначена", show_alert=True)
        return
    
    mission = MissionResult.from_dict(game.mission_data)
    mission_text = format_mission_info(mission)
    
    await callback.message.answer(mission_text, parse_mode="HTML")
    
    # Отправляем изображения
    primary_img, deployment_img, terrain_img = get_mission_images(mission)
    
    media_group = []
    if primary_img:
        media_group.append(InputMediaPhoto(
            media=BufferedInputFile(primary_img, "primary_mission.png"),
            caption="📋 Primary Mission"
        ))
    if deployment_img:
        media_group.append(InputMediaPhoto(
            media=BufferedInputFile(deployment_img, "deployment.png"),
            caption="🗺 Deployment"
        ))
    if terrain_img:
        media_group.append(InputMediaPhoto(
            media=BufferedInputFile(terrain_img, "terrain_layout.png"),
            caption="🏔 Terrain Layout"
        ))
    
    if media_group:
        await bot.send_media_group(
            chat_id=callback.from_user.id,
            media=media_group
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("regenerate_mission:"))
@admin_required
async def regenerate_mission(callback: CallbackQuery, session: AsyncSession, bot: Bot, **kwargs):
    """Перегенерировать миссию и отправить всем участникам"""
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from wh40k_bot.services.mission_service import (
        generate_random_mission, get_mission_images, 
        format_mission_info, MissionResult
    )
    
    game_id = int(callback.data.split(":")[1])
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    # Генерируем новую миссию
    mission = generate_random_mission()
    if not mission:
        await callback.answer("Не удалось сгенерировать миссию", show_alert=True)
        return
    
    # Сохраняем
    game.mission_data = mission.to_dict()
    await session.commit()
    
    mission_text = format_mission_info(mission)
    primary_img, deployment_img, terrain_img = get_mission_images(mission)
    
    # Отправляем всем участникам
    sent_count = 0
    for participant in game.participants:
        try:
            # Отправляем текст миссии
            await bot.send_message(
                chat_id=participant.user.telegram_id,
                text=f"🔄 <b>Миссия перегенерирована!</b>\n\n{mission_text}",
                parse_mode="HTML"
            )
            
            # Отправляем изображения миссии
            media_group = []
            if primary_img:
                media_group.append(InputMediaPhoto(
                    media=BufferedInputFile(primary_img, "primary_mission.png"),
                    caption="📋 Primary Mission"
                ))
            if deployment_img:
                media_group.append(InputMediaPhoto(
                    media=BufferedInputFile(deployment_img, "deployment.png"),
                    caption="🗺 Deployment"
                ))
            if terrain_img:
                media_group.append(InputMediaPhoto(
                    media=BufferedInputFile(terrain_img, "terrain_layout.png"),
                    caption="🏔 Terrain Layout"
                ))
            
            if media_group:
                await bot.send_media_group(
                    chat_id=participant.user.telegram_id,
                    media=media_group
                )
            
            sent_count += 1
        except Exception as e:
            print(f"Error sending mission to {participant.user.telegram_id}: {e}")
    
    await callback.message.edit_text(
        f"🔄 <b>Миссия перегенерирована!</b>\n\n"
        f"{mission_text}\n\n"
        f"✅ Отправлено {sent_count}/{len(game.participants)} участникам",
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game)
    )
    await callback.answer("Миссия перегенерирована!")
