import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from wh40k_bot.bot.keyboards import game_management_keyboard, pending_games_keyboard, resubmit_games_keyboard, my_games_keyboard, army_lists_keyboard, army_list_actions_keyboard
from wh40k_bot.bot.middlewares import admin_required
from wh40k_bot.bot.states import SubmitArmyList, UploadArmyList
from wh40k_bot.bot.utils import format_army_lists, format_game_info
from wh40k_bot.config import config
from wh40k_bot.db import GameStatus, UserRepository
from wh40k_bot.services import GameService, ArmyListService, format_army_list_full, format_army_list_short

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    """Команда /start"""
    # Регистрируем пользователя
    repo = UserRepository(session)
    await repo.get_or_create(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    await session.commit()
    
    text = [
        "⚔️ <b>WH40K Army List Bot</b>",
        "",
        "Бот для сбора списков армий перед матчами.",
        "",
        "<b>Доступные команды:</b>",
        "/mygames — ваши активные игры",
        "/mylists — ваши списки армий",
        "/submit — отправить список армии для игры",
        "/resubmit — переотправить список",
    ]
    
    # Добавляем админ-команды если это админ
    if message.from_user.id in config.admin_ids:
        text.extend([
            "",
            "<b>Админ-команды:</b>",
            "/admin — админ-панель",
            "/newgame — создать игру",
            "/games — список игр",
            "/game [id] — управление игрой",
            "/users — список пользователей",
        ])
    
    await message.answer("\n".join(text), parse_mode="HTML")


@router.message(Command("newgame"))
@admin_required
async def cmd_newgame(message: Message, session: AsyncSession, bot: Bot, **kwargs):
    """
    Создать новую игру.
    
    Формат с kwargs:
    /newgame --user @player1 --user @player2 --name "Битва за Терру" --start 15.02.2026 18:00 --points 2000 --delay 24
    
    Краткие флаги:
    -u = --user
    -n = --name
    -s = --start
    -p = --points
    -d = --delay
    
    Старый формат (для совместимости):
    /newgame @user1 @user2 "название" ДД.ММ.ГГГГ ЧЧ:ММ [очки] [дедлайн_часы]
    """
    from datetime import datetime
    import shlex
    
    text = message.text or ""
    
    # Определяем формат команды
    is_kwargs_format = '--' in text or ' -u ' in text or ' -n ' in text or ' -p ' in text or ' -d ' in text or ' -s ' in text
    
    if is_kwargs_format:
        # Новый kwargs формат
        result = await parse_newgame_kwargs(message, session)
    else:
        # Старый формат для совместимости
        result = await parse_newgame_legacy(message, session)
    
    if result is None:
        return
    
    participant_ids, participant_usernames, participant_names, title, scheduled_at, points_limit, deadline_hours, errors = result
    
    if errors:
        await message.answer(
            f"⚠️ Не удалось найти пользователей: {', '.join(errors)}\n\n"
            "Эти пользователи должны сначала написать боту /start"
        )
        if not participant_ids:
            return
    
    # Создаём игру
    service = GameService(session)
    result = await service.create_game(
        created_by=message.from_user.id,
        participant_telegram_ids=participant_ids,
        participant_usernames=participant_usernames,
        participant_names=participant_names,
        title=title,
        deadline_hours=deadline_hours,
        scheduled_at=scheduled_at,
        points_limit=points_limit
    )
    
    game = result.game
    
    # Отправляем подтверждение админу
    await message.answer(
        f"✅ Игра создана!\n\n{format_game_info(game, detailed=True)}",
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game)
    )
    
    # Уведомляем участников
    for tg_id, name in result.users_to_notify:
        try:
            await bot.send_message(
                chat_id=tg_id,
                text=(
                    f"🎮 <b>Вас добавили в игру!</b>\n\n"
                    f"{format_game_info(game)}\n\n"
                    f"Отправьте ваш список армии текстом.\n\n"
                    f"Используйте /submit для отправки списка."
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            await message.answer(
                f"⚠️ Не удалось уведомить {name}: {e}"
            )


async def parse_newgame_kwargs(message: Message, session: AsyncSession):
    """Парсинг kwargs формата: --user @p1 --user @p2 --name "X" --start DD.MM.YYYY HH:MM --points 2000 --delay 24"""
    from datetime import datetime
    import shlex
    
    text = message.text or ""
    
    # Убираем /newgame
    text = re.sub(r'^/newgame\s*', '', text)
    
    # Заменяем короткие флаги на длинные (учитываем начало строки и пробелы)
    text = re.sub(r'(^|\s)-u\s', r'\1--user ', text)
    text = re.sub(r'(^|\s)-n\s', r'\1--name ', text)
    text = re.sub(r'(^|\s)-s\s', r'\1--start ', text)
    text = re.sub(r'(^|\s)-p\s', r'\1--points ', text)
    text = re.sub(r'(^|\s)-d\s', r'\1--delay ', text)
    
    # Парсим аргументы
    users = []
    title = None
    scheduled_at = None
    points_limit = None
    deadline_hours = config.default_deadline_hours
    
    # Извлекаем --user
    user_matches = re.findall(r'--user\s+@?(\w+)', text)
    users = user_matches
    
    # Извлекаем --name (в кавычках или без)
    name_match = re.search(r'--name\s+"([^"]+)"', text) or re.search(r'--name\s+(\S+)', text)
    if name_match:
        title = name_match.group(1)
    
    # Извлекаем --start (дата и время)
    start_match = re.search(r'--start\s+(\d{2})\.(\d{2})\.(\d{4})\s+(\d{1,2}):(\d{2})', text)
    if start_match:
        day, month, year, hour, minute = start_match.groups()
        try:
            scheduled_at = datetime(int(year), int(month), int(day), int(hour), int(minute))
        except ValueError:
            await message.answer("❌ Неверный формат даты. Используйте --start ДД.ММ.ГГГГ ЧЧ:ММ")
            return None
    
    # Извлекаем --points
    points_match = re.search(r'--points\s+(\d+)', text)
    if points_match:
        points_limit = int(points_match.group(1))
    
    # Извлекаем --delay
    delay_match = re.search(r'--delay\s+(\d+)', text)
    if delay_match:
        deadline_hours = int(delay_match.group(1))
    
    if len(users) < 2:
        await message.answer(
            "❌ Укажите минимум 2 участников!\n\n"
            "<b>Формат:</b>\n"
            "<code>/newgame --user @p1 --user @p2 --name \"Название\" --start 15.02.2026 18:00 --points 2000 --delay 24</code>\n\n"
            "<b>Короткие флаги:</b>\n"
            "<code>-u</code> = --user (участник)\n"
            "<code>-n</code> = --name (название)\n"
            "<code>-s</code> = --start (дата и время)\n"
            "<code>-p</code> = --points (лимит очков)\n"
            "<code>-d</code> = --delay (дедлайн в часах)\n\n"
            "<b>Пример:</b>\n"
            "<code>/newgame -u @player1 -u @player2 -n \"Битва\" -p 2000</code>",
            parse_mode="HTML"
        )
        return None
    
    if len(users) > 10:
        await message.answer("❌ Максимум 10 участников!")
        return None
    
    # Получаем информацию о пользователях
    participant_ids = []
    participant_usernames = []
    participant_names = []
    errors = []
    
    user_repo = UserRepository(session)
    
    for username in users:
        user = await user_repo.get_by_username(username)
        if user:
            participant_ids.append(user.telegram_id)
            participant_usernames.append(user.username)
            participant_names.append(user.first_name)
        else:
            errors.append(f"@{username}")
    
    return participant_ids, participant_usernames, participant_names, title, scheduled_at, points_limit, deadline_hours, errors


async def parse_newgame_legacy(message: Message, session: AsyncSession):
    """Парсинг старого формата: /newgame @u1 @u2 "название" ДД.ММ.ГГГГ ЧЧ:ММ [очки] [дедлайн]"""
    from datetime import datetime
    
    # Парсим упоминания пользователей
    entities = message.entities or []
    mentions = []
    
    for entity in entities:
        if entity.type == "mention":
            # @username
            username = message.text[entity.offset + 1:entity.offset + entity.length]
            mentions.append({"type": "username", "value": username})
        elif entity.type == "text_mention":
            # Упоминание без username
            mentions.append({
                "type": "user",
                "user_id": entity.user.id,
                "first_name": entity.user.first_name,
                "username": entity.user.username
            })
    
    if len(mentions) < 2:
        await message.answer(
            "❌ Укажите минимум 2 участников!\n\n"
            "<b>Новый формат (рекомендуется):</b>\n"
            "<code>/newgame -u @p1 -u @p2 -n \"Название\" -p 2000 -d 24</code>\n\n"
            "<b>Старый формат:</b>\n"
            "<code>/newgame @user1 @user2 \"Название\" ДД.ММ.ГГГГ ЧЧ:ММ очки дедлайн</code>\n\n"
            "Используйте /help для подробностей.",
            parse_mode="HTML"
        )
        return None
    
    if len(mentions) > 10:
        await message.answer("❌ Максимум 10 участников!")
        return None
    
    # Парсим название и дедлайн
    text = message.text
    
    # Убираем команду и упоминания
    clean_text = re.sub(r'/newgame\s*', '', text)
    clean_text = re.sub(r'@\w+', '', clean_text).strip()
    
    title = None
    deadline_hours = config.default_deadline_hours
    scheduled_at = None
    points_limit = None
    
    # Ищем название в кавычках
    title_match = re.search(r'"([^"]+)"', clean_text)
    if title_match:
        title = title_match.group(1)
        clean_text = clean_text.replace(title_match.group(0), '').strip()
    
    # Ищем дату и время (ДД.ММ.ГГГГ ЧЧ:ММ)
    datetime_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})\s+(\d{1,2}):(\d{2})', clean_text)
    if datetime_match:
        day, month, year, hour, minute = datetime_match.groups()
        try:
            scheduled_at = datetime(int(year), int(month), int(day), int(hour), int(minute))
            clean_text = clean_text.replace(datetime_match.group(0), '').strip()
        except ValueError:
            await message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ ЧЧ:ММ")
            return None
    
    # Ищем числа (points_limit и deadline)
    numbers = re.findall(r'(\d+)', clean_text)
    if len(numbers) >= 2:
        num1, num2 = int(numbers[0]), int(numbers[1])
        if num1 > 100:
            points_limit = num1
            deadline_hours = num2
        else:
            deadline_hours = num1
            if num2 > 100:
                points_limit = num2
    elif len(numbers) == 1:
        num = int(numbers[0])
        if num > 100:
            points_limit = num
        else:
            deadline_hours = num
    
    # Получаем информацию о пользователях
    participant_ids = []
    participant_usernames = []
    participant_names = []
    errors = []
    
    user_repo = UserRepository(session)
    
    for mention in mentions:
        if mention["type"] == "user":
            participant_ids.append(mention["user_id"])
            participant_usernames.append(mention.get("username"))
            participant_names.append(mention.get("first_name"))
        else:
            # Ищем пользователя по username в нашей базе
            username = mention["value"]
            user = await user_repo.get_by_username(username)
            if user:
                participant_ids.append(user.telegram_id)
                participant_usernames.append(user.username)
                participant_names.append(user.first_name)
            else:
                errors.append(f"@{username}")
    
    return participant_ids, participant_usernames, participant_names, title, scheduled_at, points_limit, deadline_hours, errors


@router.message(Command("games"))
@admin_required
async def cmd_games(message: Message, session: AsyncSession, **kwargs):
    """Список всех активных игр"""
    service = GameService(session)
    games = await service.get_active_games()
    
    if not games:
        await message.answer("📭 Нет активных игр")
        return
    
    text = ["📋 <b>Активные игры:</b>\n"]
    
    for game in games:
        text.append(format_game_info(game))
        text.append("")
    
    await message.answer("\n".join(text), parse_mode="HTML")


@router.message(Command("admin"))
@admin_required
async def cmd_admin(message: Message, **kwargs):
    """Админ-панель"""
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
    
    await message.answer("\n".join(text), parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("game"))
@admin_required
async def cmd_game(message: Message, session: AsyncSession, **kwargs):
    """Управление конкретной игрой"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("Использование: /game [id]")
        return
    
    try:
        game_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return
    
    service = GameService(session)
    game = await service.get_game(game_id)
    
    if not game:
        await message.answer("❌ Игра не найдена")
        return
    
    await message.answer(
        format_game_info(game, detailed=True),
        parse_mode="HTML",
        reply_markup=game_management_keyboard(game)
    )


@router.message(Command("mygames"))
async def cmd_mygames(message: Message, session: AsyncSession):
    """Мои активные игры"""
    service = GameService(session)
    all_games = await service.get_all_active_games_for_user(message.from_user.id)
    
    if not all_games:
        await message.answer(
            "📭 У вас нет активных игр.\n"
            "Когда админ добавит вас в игру, вы получите уведомление."
        )
        return
    
    # Считаем статистику
    pending = sum(1 for p in all_games if not p.army_list_id and (p.game.status.value if hasattr(p.game.status, 'value') else p.game.status) == "collecting")
    ready = sum(1 for p in all_games if (p.game.status.value if hasattr(p.game.status, 'value') else p.game.status) in ["ready", "in_progress"])
    
    text = f"🎮 <b>Ваши активные игры ({len(all_games)}):</b>\n\n"
    if pending > 0:
        text += f"⏳ Ожидают ваш список: {pending}\n"
    if ready > 0:
        text += f"⚔️ Готовы к игре: {ready}\n"
    text += "\nНажмите на игру для подробностей:"
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=my_games_keyboard(all_games)
    )


@router.message(Command("submit"))
async def cmd_submit(message: Message, session: AsyncSession, state: FSMContext):
    """Начать отправку списка армии"""
    service = GameService(session)
    pending = await service.get_pending_games_for_user(message.from_user.id)
    
    if not pending:
        await message.answer("📭 У вас нет игр, ожидающих список армии.")
        return
    
    # Проверяем есть ли у пользователя сохранённые списки
    army_service = ArmyListService(session)
    army_lists = await army_service.get_user_army_lists(message.from_user.id)
    
    if not army_lists:
        await message.answer(
            "📭 У вас нет сохранённых списков армий.\n\n"
            "Сначала загрузите список командой /mylists\n"
            "или отправьте JSON файл прямо сейчас."
        )
        return
    
    if len(pending) == 1:
        # Если игра одна — сразу показываем выбор списка
        game = pending[0].game
        title = game.title or f"Игра #{game.id}"
        
        await message.answer(
            f"📋 Выберите список армии для игры <b>{title}</b>:",
            parse_mode="HTML",
            reply_markup=army_lists_keyboard(army_lists, for_submit=True, game_id=game.id)
        )
    else:
        # Если игр несколько — показываем выбор игры
        await message.answer(
            "📋 Выберите игру:",
            reply_markup=pending_games_keyboard(pending)
        )


@router.message(Command("mylists"))
async def cmd_mylists(message: Message, session: AsyncSession):
    """Показать сохранённые списки армий"""
    army_service = ArmyListService(session)
    army_lists = await army_service.get_user_army_lists(message.from_user.id)
    
    if not army_lists:
        await message.answer(
            "📭 У вас нет сохранённых списков армий.\n\n"
            "Отправьте JSON файл списка армии из game-datacards\n"
            "(List → Export as Datasource)",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Загрузить список", callback_data="upload_army_list")]
            ])
        )
        return
    
    await message.answer(
        f"📋 <b>Ваши списки армий ({len(army_lists)}):</b>\n\n"
        "Нажмите на список для подробностей:",
        parse_mode="HTML",
        reply_markup=army_lists_keyboard(army_lists)
    )


@router.message(F.document)
async def process_army_list_file(message: Message, session: AsyncSession, bot: Bot, state: FSMContext):
    """Обработка загруженного JSON файла со списком армии"""
    document = message.document
    
    # Проверяем что это JSON
    if not document.file_name.endswith('.json'):
        await message.answer("❌ Пожалуйста, отправьте JSON файл (.json)")
        return
    
    # Скачиваем файл
    try:
        file = await bot.get_file(document.file_id)
        file_content = await bot.download_file(file.file_path)
        json_str = file_content.read().decode('utf-8')
    except Exception as e:
        await message.answer(f"❌ Ошибка при скачивании файла: {e}")
        return
    
    # Создаём список армии
    army_service = ArmyListService(session)
    try:
        army_list = await army_service.create_army_list(message.from_user.id, json_str)
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return
    except Exception as e:
        await message.answer(f"❌ Ошибка при сохранении: {e}")
        return
    
    if not army_list:
        await message.answer("❌ Ошибка: пользователь не найден. Напишите /start")
        return
    
    await message.answer(
        f"✅ Список армии сохранён!\n\n"
        f"{format_army_list_full(army_list)}",
        parse_mode="HTML"
    )


@router.message(Command("users"))
@admin_required
async def cmd_users(message: Message, session: AsyncSession, **kwargs):
    """Список всех зарегистрированных пользователей"""
    repo = UserRepository(session)
    users = await repo.get_all()
    
    if not users:
        await message.answer("📭 Нет зарегистрированных пользователей")
        return
    
    text = [f"👥 <b>Зарегистрированные пользователи ({len(users)}):</b>\n"]
    
    for user in users:
        name = user.username or user.first_name or f"ID {user.telegram_id}"
        if user.username:
            name = f"@{name}"
        
        is_admin = config.is_admin(user.telegram_id)
        admin_badge = " 👑" if is_admin else ""
        
        registered = user.created_at.strftime("%d.%m.%Y")
        
        text.append(f"• {name}{admin_badge} <code>({user.telegram_id})</code> — с {registered}")
    
    await message.answer("\n".join(text), parse_mode="HTML")


@router.message(Command("resubmit"))
async def cmd_resubmit(message: Message, session: AsyncSession):
    """Переотправить список армии"""
    service = GameService(session)
    submitted = await service.get_submitted_games_for_user(message.from_user.id)
    
    if not submitted:
        await message.answer(
            "📭 Нет игр для переотправки.\n"
            "Переотправить можно только пока идёт сбор списков."
        )
        return
    
    await message.answer(
        "🔄 <b>Выберите игру для переотправки списка:</b>\n\n"
        "⚠️ Ваш текущий список будет удалён!",
        parse_mode="HTML",
        reply_markup=resubmit_games_keyboard(submitted)
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Справка"""
    is_admin = config.is_admin(message.from_user.id)
    
    text = [
        "📖 <b>Справка по WH40K Army List Bot</b>",
        "",
        "<b>Как это работает:</b>",
        "1. Загрузите список армии (JSON из game-datacards)",
        "2. Админ создаёт игру и указывает участников",
        "3. Каждый участник получает уведомление",
        "4. Участники выбирают список армии для игры",
        "5. Когда все выбрали — бот рассылает все списки всем",
        "6. После игры админ записывает результат",
        "",
        "<b>Команды для всех:</b>",
        "/start — начать работу с ботом",
        "/mygames — ваши активные игры",
        "/mylists — ваши списки армий",
        "/submit — отправить список армии для игры",
        "/resubmit — переотправить список армии",
        "/help — эта справка",
        "",
        "<i>💡 Для загрузки списка армии отправьте JSON файл</i>",
        "<i>из game-datacards (List → Export as Datasource)</i>",
    ]
    
    if is_admin:
        text.extend([
            "",
            "<b>Команды для админов:</b>",
            "/newgame — создать игру",
            "",
            "<b>Формат /newgame:</b>",
            "<code>/newgame -u @p1 -u @p2 -n \"Название\" -p 2000 -s 15.02.2026 18:00 -d 24</code>",
            "",
            "Флаги:",
            "  <code>-u</code> / <code>--user</code> — участник (минимум 2)",
            "  <code>-n</code> / <code>--name</code> — название игры",
            "  <code>-p</code> / <code>--points</code> — лимит очков",
            "  <code>-s</code> / <code>--start</code> — дата и время",
            "  <code>-d</code> / <code>--delay</code> — дедлайн (часы)",
            "",
            "/games — все активные игры",
            "/game [id] — управление игрой",
            "/users — список пользователей",
        ])
    
    await message.answer("\n".join(text), parse_mode="HTML")
