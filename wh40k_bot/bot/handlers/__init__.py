from aiogram import Router

from wh40k_bot.bot.handlers.callbacks import router as callbacks_router
from wh40k_bot.bot.handlers.commands import router as commands_router


def setup_routers() -> Router:
    """Настройка всех роутеров"""
    router = Router()
    router.include_router(commands_router)
    router.include_router(callbacks_router)
    return router
