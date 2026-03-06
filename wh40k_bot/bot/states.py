from aiogram.fsm.state import State, StatesGroup


class SubmitArmyList(StatesGroup):
    """Состояния для отправки списка армии"""
    waiting_for_list = State()  # Ожидаем выбор списка
    selecting_list = State()    # Выбор списка для игры


class CreateGame(StatesGroup):
    """Состояния для создания игры"""
    waiting_for_title = State()      # Ожидаем название (опционально)
    waiting_for_deadline = State()   # Ожидаем дедлайн


class UploadArmyList(StatesGroup):
    """Состояния для загрузки списка армии"""
    waiting_for_file = State()  # Ожидаем JSON файл
