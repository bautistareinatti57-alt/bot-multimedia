"""Configuración centralizada de la aplicación."""

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} debe ser un número positivo.")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    download_dir: Path
    max_upload_bytes: int
    max_concurrent_downloads: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        # Se mantiene BOT_TOKEN como alias sencillo para instalaciones existentes.
        token = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("Falta TELEGRAM_BOT_TOKEN (o BOT_TOKEN) en el archivo .env.")

        download_dir = Path(os.getenv("DOWNLOAD_DIR", "downloads"))
        if not download_dir.is_absolute():
            download_dir = BASE_DIR / download_dir
        download_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            bot_token=token,
            download_dir=download_dir,
            max_upload_bytes=_positive_int("MAX_UPLOAD_MB", 50) * 1024 * 1024,
            max_concurrent_downloads=_positive_int("MAX_CONCURRENT_DOWNLOADS", 3),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
