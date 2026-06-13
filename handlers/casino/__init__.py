from aiogram import Router

from .base import setup, init_db, refund_orphaned_games
from . import menu
from . import profile
from . import games_pvp
from . import games_solo
from . import games_rps
from . import blackjack
from . import admin

router = Router()
router.include_router(menu.router)
router.include_router(profile.router)
router.include_router(games_pvp.router)
router.include_router(games_solo.router)
router.include_router(games_rps.router)
router.include_router(blackjack.router)
router.include_router(admin.router)
