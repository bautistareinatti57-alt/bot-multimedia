"""Punto de entrada del bot de descargas."""

from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import Settings
from handlers.media import help_command, received_url, select_format, start
from services.downloader import MediaDownloader


def configure_logging(level: str) -> None:
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=getattr(logging, level, logging.INFO),
        stream=sys.stdout,
    )
    # Evita registrar URLs de la API de Telegram, que contienen el token del bot.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra excepciones no controladas sin exponer detalles al usuario."""
    logging.getLogger(__name__).exception("Excepción no controlada al procesar una actualización", exc_info=context.error)


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    application = (
        Application.builder()
        .token(settings.bot_token)
        .concurrent_updates(True)
        # Las subidas de vídeo pueden tardar más que los valores predeterminados.
        .connect_timeout(30)
        .read_timeout(120)
        .write_timeout(120)
        .pool_timeout(30)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["downloader"] = MediaDownloader(settings.download_dir, settings.max_concurrent_downloads)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ayuda", help_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(select_format, pattern=r"^download:"))
    # En grupos solo procesamos mensajes que sean enlaces, para no interrumpir la conversación.
    application.add_handler(
        MessageHandler(filters.Regex(r"^\s*https?://\S+\s*$") & ~filters.COMMAND, received_url)
    )
    application.add_error_handler(error_handler)

    logger.info("Bot iniciado; máximo de descargas concurrentes: %s", settings.max_concurrent_downloads)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
