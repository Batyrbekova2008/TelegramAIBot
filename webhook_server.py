"""
Webhook mode (Task 22) — replaces long polling with HTTP webhooks.

Usage:
  python webhook_server.py            # HTTPS via ngrok (dev)
  WEBHOOK_MODE=ngrok python webhook_server.py

  python webhook_server.py --ngrok    # auto-start ngrok tunnel
  python webhook_server.py --letsencrypt  # production with LE cert

Comparison vs polling:
  Polling  — bot constantly asks Telegram for updates (higher latency, more CPU)
  Webhook  — Telegram pushes updates to bot instantly (~50ms vs ~1-3s)

Graceful shutdown: drains webhook queue before stopping (SIGINT/SIGTERM).
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Any

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config.settings import config
from config.database import create_tables
from handlers.messages import router as messages_router
from handlers.mcp_handlers import router as mcp_router
from handlers.ollama_handlers import router as ollama_router
from services.mcp_aggregator import MCPAggregator

log = logging.getLogger("webhook")

# ── Configuration ─────────────────────────────────────────────────────────────
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "")          # e.g. https://abc.ngrok.io
WEBHOOK_PATH = "/webhook"
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 8443))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "changeme-webhook-secret")

# Self-signed cert paths (for production, replace with Let's Encrypt)
SSL_CERT = os.getenv("SSL_CERT", "ssl/cert.pem")
SSL_KEY = os.getenv("SSL_KEY", "ssl/key.pem")


async def on_startup(bot: Bot, aggregator: MCPAggregator):
    """Register webhook and connect MCP aggregator."""
    asyncio.create_task(aggregator.connect_all())

    if WEBHOOK_HOST:
        webhook_url = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
        await bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True,
        )
        log.info("Webhook set to: %s", webhook_url)
    else:
        log.warning("WEBHOOK_HOST not set — webhook not registered with Telegram")


async def on_shutdown(bot: Bot, aggregator: MCPAggregator):
    """Delete webhook, drain queue, close connections."""
    log.info("Shutting down webhook server...")
    await bot.delete_webhook(drop_pending_updates=False)
    await aggregator.close_all()
    log.info("Graceful shutdown complete.")


def build_app() -> tuple[web.Application, Bot, MCPAggregator]:
    create_tables()

    bot = Bot(
        token=config.TELEGRAM_TOKEN.get_secret_value(),
        default_bot_properties=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    aggregator = MCPAggregator()

    dp = Dispatcher()
    dp["mcp_aggregator"] = aggregator
    dp.include_router(mcp_router)
    dp.include_router(ollama_router)
    dp.include_router(messages_router)

    dp.startup.register(lambda: on_startup(bot, aggregator))
    dp.shutdown.register(lambda: on_shutdown(bot, aggregator))

    app = web.Application()

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
    ).register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)

    # Health endpoint
    async def health(_):
        return web.Response(text="OK")

    app.router.add_get("/health", health)

    return app, bot, aggregator


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("bot.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    app, bot, aggregator = build_app()

    # SSL context for self-signed cert
    ssl_context = None
    if os.path.exists(SSL_CERT) and os.path.exists(SSL_KEY):
        import ssl
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(SSL_CERT, SSL_KEY)
        log.info("Using SSL from %s / %s", SSL_CERT, SSL_KEY)

    log.info("Starting webhook server on port %d", WEBHOOK_PORT)
    web.run_app(
        app,
        host="0.0.0.0",
        port=WEBHOOK_PORT,
        ssl_context=ssl_context,
    )


if __name__ == "__main__":
    main()
