import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config.settings import config
from handlers.messages import router as messages_router

# Терминалға логтарды шығару
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

async def main():
    # .env файлындағы токенді оқып, ботты байланыстыру
    bot = Bot(
        token=config.TELEGRAM_TOKEN.get_secret_value(),
        default_bot_properties=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher()
    dp.include_router(messages_router)
    
    # Ескі кептеліп қалған хабарламаларды тазалау
    await bot.delete_webhook(drop_pending_updates=True)
    
    logging.info("Бот VS Code-пен сәтті байланысты! Іске қосылуда...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())