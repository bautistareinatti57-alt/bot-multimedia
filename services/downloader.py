"""Adaptador asíncrono y seguro para yt-dlp."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import time
from typing import Any
from uuid import uuid4

import yt_dlp


class DownloadError(Exception):
    """Error entendible causado por el extractor o la descarga."""


@dataclass(slots=True)
class MediaInfo:
    title: str
    platform: str
    is_playlist: bool
    item_count: int | None
    has_video: bool
    has_audio: bool


@dataclass(slots=True)
class DownloadProgress:
    percent: float | None
    speed: str | None
    eta: int | None
    message: str | None = None


@dataclass(slots=True)
class DownloadedMedia:
    files: list[Path]
    title: str
    job_dir: Path
    mode: str


class MediaDownloader:
    def __init__(self, download_dir: Path, max_concurrent: int) -> None:
        self.download_dir = download_dir
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def inspect(self, url: str) -> MediaInfo:
        return await asyncio.to_thread(self._inspect_sync, url)

    def _inspect_sync(self, url: str) -> MediaInfo:
        url = self._normalize_url(url)
        options = {"quiet": True, "no_warnings": True, "skip_download": True}
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise DownloadError(self._friendly_error(str(exc))) from exc

        if not info:
            raise DownloadError("No se encontró contenido descargable en ese enlace.")
        entries = info.get("entries")
        first = next((entry for entry in entries or [] if entry), info)
        formats = first.get("formats", [])
        # Algunos extractores (por ejemplo Snapchat Spotlight) devuelven una URL
        # directa de vídeo sin poblar la lista de formatos.
        has_direct_media = bool(first.get("url"))
        has_video = has_direct_media or any(fmt.get("vcodec") not in (None, "none") for fmt in formats)
        has_audio = any(fmt.get("acodec") not in (None, "none") for fmt in formats)
        return MediaInfo(
            title=info.get("title") or first.get("title") or "Contenido sin título",
            platform=info.get("extractor_key") or "Sitio web",
            is_playlist=bool(entries),
            item_count=info.get("playlist_count") or (len(entries) if entries else None),
            has_video=has_video,
            has_audio=has_audio or has_video,
        )

    async def download(
        self, url: str, mode: str, progress_callback: Callable[[DownloadProgress], None] | None = None
    ) -> DownloadedMedia:
        async with self.semaphore:
            return await asyncio.to_thread(self._download_sync, url, mode, progress_callback)

    def _download_sync(
        self, url: str, mode: str, progress_callback: Callable[[DownloadProgress], None] | None
    ) -> DownloadedMedia:
        url = self._normalize_url(url)
        job_dir = self.download_dir / uuid4().hex
        job_dir.mkdir(parents=True, exist_ok=False)
        last_update = 0.0

        def hook(data: dict[str, Any]) -> None:
            nonlocal last_update
            if not progress_callback:
                return
            if data.get("status") == "finished":
                progress_callback(DownloadProgress(None, None, None, "⚙️ Descarga terminada. Procesando video…"))
                return
            if data.get("status") != "downloading":
                return
            now = time.monotonic()
            if now - last_update < 1:
                return
            last_update = now
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes", 0)
            percent = downloaded / total * 100 if total else None
            progress_callback(DownloadProgress(percent, data.get("_speed_str"), data.get("_eta")))

        def postprocessor_hook(data: dict[str, Any]) -> None:
            if progress_callback and data.get("status") == "started":
                progress_callback(DownloadProgress(None, None, None, "⚙️ Procesando video con FFmpeg…"))

        options: dict[str, Any] = {
            "outtmpl": str(job_dir / "%(title).120B [%(id)s].%(ext)s"),
            "noplaylist": False,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": False,
            "windowsfilenames": True,
            "progress_hooks": [hook],
            "postprocessor_hooks": [postprocessor_hook],
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
            "ignoreerrors": False,
        }
        if mode == "audio":
            options.update({
                "format": "bestaudio/best",
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
            })
        else:
            options.update({"format": "bestvideo*+bestaudio/best", "merge_output_format": "mp4"})

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                title = (info or {}).get("title") or "Contenido descargado"
        except (yt_dlp.utils.DownloadError, OSError) as exc:
            self.cleanup(job_dir)
            raise DownloadError(self._friendly_error(str(exc))) from exc

        files = [path for path in job_dir.iterdir() if path.is_file() and path.suffix.lower() not in {".part", ".ytdl"}]
        if not files:
            self.cleanup(job_dir)
            raise DownloadError("La descarga terminó, pero no se pudo localizar el archivo resultante.")
        return DownloadedMedia(files=files, title=title, job_dir=job_dir, mode=mode)

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Convierte enlaces de Snapchat con perfil al formato Spotlight de yt-dlp."""
        match = re.fullmatch(
            r"https?://(?:www\.)?snapchat\.com/@[^/?#]+/spotlight/([^/?#]+)(?:[?#].*)?",
            url,
            flags=re.IGNORECASE,
        )
        if match:
            return f"https://www.snapchat.com/spotlight/{match.group(1)}"
        return url

    @staticmethod
    def cleanup(job_dir: Path) -> None:
        shutil.rmtree(job_dir, ignore_errors=True)

    @staticmethod
    def _friendly_error(error: str) -> str:
        lowered = error.lower()
        if "private" in lowered or "login" in lowered or "sign in" in lowered:
            return "Este contenido es privado o requiere iniciar sesión en la plataforma."
        if "ffmpeg" in lowered:
            return (
                "No puedo procesar este video porque FFmpeg no está instalado o no está disponible en PATH. "
                "Instálalo y reinicia el bot para descargar videos de máxima calidad o convertir audio a MP3."
            )
        if "unsupported url" in lowered:
            return "Ese enlace no es compatible o no contiene contenido descargable."
        if "not available" in lowered or "removed" in lowered:
            return "El contenido no está disponible o fue eliminado."
        return "No pude descargar ese contenido. Comprueba que el enlace sea público e inténtalo otra vez."
