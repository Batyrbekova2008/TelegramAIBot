import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config.settings import config
from config.database import create_tables
from handlers.messages import router as messages_router
from handlers.mcp_handlers import router as mcp_router
from handlers.ollama_handlers import router as ollama_router
from services.mcp_aggregator import MCPAggregator
from utils.logging_setup import setup_logging, get_logger, bind_request_context, new_request_id

setup_logging(json_logs=True, log_file="bot.log")
log = get_logger("main")


async def main():
    create_tables()

    bot = Bot(
        token=config.TELEGRAM_TOKEN.get_secret_value(),
        default_bot_properties=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    aggregator = MCPAggregator()
    asyncio.create_task(aggregator.connect_all())

    dp = Dispatcher()
    dp["mcp_aggregator"] = aggregator

    dp.include_router(mcp_router)
    dp.include_router(ollama_router)
    dp.include_router(messages_router)

    await bot.delete_webhook(drop_pending_updates=True)
    log.info("bot_started", token_prefix=config.TELEGRAM_TOKEN.get_secret_value()[:10])

    try:
        await dp.start_polling(bot)
    finally:
        await aggregator.close_all()
        log.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
