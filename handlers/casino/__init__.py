from aiogram import Router

from .base import setup, init_db
from . import menu
from . import profile
from . import games_pvp
from . import games_solo
from . import blackjack
from . import admin

router = Router()
router.include_router(menu.router)
router.include_router(profile.router)
router.include_router(games_pvp.router)
router.include_router(games_solo.router)
router.include_router(blackjack.router)
router.include_router(admin.router)
