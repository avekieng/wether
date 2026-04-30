import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database import init_db
from handlers import users, war, alliances, economy, misc
from services.background import start_background_tasks

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(users.router)
    dp.include_router(war.router)
    dp.include_router(alliances.router)
    dp.include_router(economy.router)
    dp.include_router(misc.router)

    await init_db()
    asyncio.create_task(start_background_tasks(bot))

    logger.info("Бот запущен!")
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
