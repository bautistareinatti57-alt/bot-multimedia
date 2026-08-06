from __future__ import annotations

from html import escape
from urllib.parse import urlparse


def is_http_url(text: str) -> bool:
    parsed = urlparse(text.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def safe_html(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    return escape(compact[:limit] + ("…" if len(compact) > limit else ""))


def progress_text(percent: float | None, speed: str | None, eta: int | None) -> str:
    if percent is None:
        return "⬇️ Descargando…"
    filled = min(10, max(0, round(percent / 10)))
    bar = "█" * filled + "░" * (10 - filled)
    detail = f" · {speed}" if speed else ""
    if eta is not None:
        detail += f" · faltan ~{eta}s"
    return f"⬇️ Descargando\n[{bar}] {percent:.0f}%{detail}"
