"""Flujo de enlace, selección de formato, descarga y envío."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import ContextTypes

from config import Settings
from services.downloader import DownloadError, DownloadProgress, DownloadedMedia, MediaDownloader
from utils.formatting import is_http_url, progress_text, safe_html

logger = logging.getLogger(__name__)


def _downloader(context: ContextTypes.DEFAULT_TYPE) -> MediaDownloader:
    return context.application.bot_data["downloader"]


def _settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.application.bot_data["settings"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "¡Hola! 👋\n\nEnvíame un enlace público de TikTok, Instagram, YouTube, Facebook, X, Reddit, "
        "Pinterest, Twitch, SoundCloud o cualquier sitio compatible con yt-dlp.\n\n"
        "Después podrás elegir si quieres video o audio."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "📌 <b>Cómo usar el bot</b>\n\n1. Envía un enlace público.\n2. Elige video o audio.\n3. Espera el envío del archivo.\n\n"
        "Las listas de reproducción compatibles se descargan completas. El contenido privado, protegido o no "
        "compatible no se puede descargar.",
        parse_mode=ParseMode.HTML,
    )


async def received_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    url = (message.text or "").strip()
    if not is_http_url(url):
        await message.reply_text("Por favor, envíame un enlace válido que empiece con http:// o https://.")
        return

    checking = await message.reply_text("🔎 Analizando el enlace…")
    try:
        info = await _downloader(context).inspect(url)
    except DownloadError as exc:
        await checking.edit_text(f"⚠️ {exc}")
        return
    except Exception:
        logger.exception("Error inesperado al analizar el enlace")
        await checking.edit_text("⚠️ Ocurrió un error al analizar el enlace. Inténtalo de nuevo más tarde.")
        return

    job_id = uuid4().hex[:12]
    jobs = context.user_data.setdefault("jobs", {})
    jobs[job_id] = {"url": url, "title": info.title}
    buttons: list[InlineKeyboardButton] = []
    if info.has_video:
        buttons.append(InlineKeyboardButton("🎬 Descargar video", callback_data=f"download:{job_id}:video"))
    if info.has_audio:
        buttons.append(InlineKeyboardButton("🎵 Descargar audio (MP3)", callback_data=f"download:{job_id}:audio"))
    if not buttons:
        await checking.edit_text("⚠️ No encontré formatos de video ni audio para este enlace.")
        return
    playlist = f"\n📚 Lista de reproducción: {info.item_count or 'varios'} elementos." if info.is_playlist else ""
    await checking.edit_text(
        f"✅ <b>{safe_html(info.title)}</b>\n🌐 Plataforma: {safe_html(info.platform)}{playlist}\n\nElige el formato deseado:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup.from_column(buttons),
    )


async def select_format(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        _, job_id, mode = (query.data or "").split(":", 2)
    except ValueError:
        await query.edit_message_text("⚠️ La selección no es válida. Envía el enlace otra vez.")
        return
    job = context.user_data.get("jobs", {}).pop(job_id, None)
    if not job or mode not in {"video", "audio"}:
        await query.edit_message_text("⚠️ Esta selección ya venció. Envía el enlace otra vez.")
        return
    await query.edit_message_text("⏳ Preparando la descarga…")
    context.application.create_task(_download_and_send(query.message, context, job["url"], mode), update=update)


async def _download_and_send(message, context: ContextTypes.DEFAULT_TYPE, url: str, mode: str) -> None:
    loop = asyncio.get_running_loop()
    last_text = ""
    progress_active = True

    def report(progress: DownloadProgress) -> None:
        nonlocal last_text
        text = progress.message or progress_text(progress.percent, progress.speed, progress.eta)
        if text != last_text:
            last_text = text
            loop.call_soon_threadsafe(context.application.create_task, _edit_progress(message, text, lambda: progress_active))

    media: DownloadedMedia | None = None
    try:
        media = await _downloader(context).download(url, mode, report)
        progress_active = False
        await message.edit_text("📤 Enviando el archivo a Telegram…")
        settings = _settings(context)
        for index, file_path in enumerate(media.files, start=1):
            if file_path.stat().st_size > settings.max_upload_bytes:
                await message.reply_text(
                    f"⚠️ No envié «{file_path.name}»: pesa más del límite configurado de "
                    f"{settings.max_upload_bytes // 1024 // 1024} MB."
                )
                continue
            await _send_file(message, file_path, mode, media.title, index, len(media.files))
        await message.edit_text("✅ Proceso terminado. Los archivos temporales ya fueron eliminados.")
    except DownloadError as exc:
        progress_active = False
        await message.edit_text(f"⚠️ {exc}")
    except TelegramError:
        progress_active = False
        logger.exception("Telegram rechazó el archivo")
        await message.edit_text("⚠️ Telegram no pudo aceptar el archivo. Puede ser demasiado grande o tener un formato no permitido.")
    except Exception:
        progress_active = False
        logger.exception("Error inesperado durante la descarga")
        await message.edit_text("⚠️ Ocurrió un error inesperado durante la descarga.")
    finally:
        progress_active = False
        if media:
            _downloader(context).cleanup(media.job_dir)


async def _edit_progress(message, text: str, is_active) -> None:
    if not is_active():
        return
    try:
        await message.edit_text(text)
    except (BadRequest, TelegramError):
        pass


async def _send_file(message, path: Path, mode: str, title: str, index: int, total: int) -> None:
    caption = f"🎵 {safe_html(title, 850)}" if mode == "audio" else f"🎬 {safe_html(title, 850)}"
    if total > 1:
        caption += f"\nParte {index}/{total}"
    with path.open("rb") as media_file:
        if mode == "audio":
            await message.reply_audio(audio=media_file, title=title[:64], caption=caption, parse_mode=ParseMode.HTML)
        else:
            try:
                await message.reply_video(video=media_file, caption=caption, parse_mode=ParseMode.HTML, supports_streaming=True)
                return
            except RetryAfter as exc:
                # Telegram pidió bajar el ritmo: conserva el vídeo y reintenta.
                await asyncio.sleep(float(exc.retry_after) + 1)
            except (TimedOut, NetworkError):
                # Un corte o una subida lenta no significa que el vídeo sea incompatible.
                await asyncio.sleep(2)
            except BadRequest:
                # Solo los errores de formato se envían como documento de respaldo.
                media_file.seek(0)
                await message.reply_document(document=media_file, caption=caption, parse_mode=ParseMode.HTML)
                return

            # Reintento único tras un error transitorio de red o rate limit.
            media_file.seek(0)
            await message.reply_video(video=media_file, caption=caption, parse_mode=ParseMode.HTML, supports_streaming=True)
