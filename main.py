import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config.settings import config
from config.database import create_tables
from handlers.messages import router as messages_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

async def main():
    create_tables()

    bot = Bot(
        token=config.TELEGRAM_TOKEN.get_secret_value(),
        default_bot_properties=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher()
    dp.include_router(messages_router)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот іске қосылды!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
