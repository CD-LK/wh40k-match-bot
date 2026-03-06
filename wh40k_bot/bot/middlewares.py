from functools import wraps
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

from wh40k_bot.config import config


class DatabaseMiddleware(BaseMiddleware):
    """Middleware для инъекции сессии БД"""
    
    def __init__(self, session_maker: async_sessionmaker):
        self.session_maker = session_maker
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async with self.session_maker() as session:
            data["session"] = session
            return await handler(event, data)


class AdminMiddleware(BaseMiddleware):
    """Middleware для проверки прав админа"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id
        
        data["is_admin"] = config.is_admin(user_id) if user_id else False
        
        return await handler(event, data)


def admin_required(handler: Callable) -> Callable:
    """Декоратор для проверки прав админа"""
    @wraps(handler)
    async def wrapper(event: TelegramObject, **kwargs):
        is_admin = kwargs.get("is_admin", False)
        
        if not is_admin:
            if isinstance(event, Message):
                await event.answer("⛔ У вас нет прав для выполнения этой команды")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Нет прав", show_alert=True)
            return
        
        return await handler(event, **kwargs)
    
    return wrapper
