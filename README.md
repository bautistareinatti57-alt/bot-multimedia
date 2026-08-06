# Bot descargador multimedia para Telegram

Bot asíncrono en Python que descarga contenido público de TikTok, Instagram, YouTube, Facebook, Threads, X/Twitter, Pinterest, Reddit, Vimeo, clips de Twitch, Snapchat Spotlight, SoundCloud y cualquier otro sitio admitido por [yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

## Características

- Detecta automáticamente el sitio desde un enlace.
- Permite elegir entre video en la mejor calidad disponible y audio MP3.
- Descarga listas de reproducción cuando el extractor las expone.
- Muestra avance, limita descargas simultáneas y mantiene el bot reactivo.
- Envía los archivos al chat y limpia el directorio temporal incluso si hay errores.
- Mensajes, botones y comandos totalmente en español.

## Requisitos

- Python 3.14 o superior.
- [FFmpeg](https://ffmpeg.org/download.html) instalado y disponible en `PATH` (necesario para unir video/audio y generar MP3).
- Un token creado con [@BotFather](https://t.me/BotFather).

## Instalación

```powershell
cd telegram_media_bot
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` y añade el valor real de `TELEGRAM_BOT_TOKEN` (también se acepta `BOT_TOKEN`). Después inicia el bot:

```powershell
python bot.py
```

### Comprobar FFmpeg en Windows

Después de instalarlo, abre una terminal nueva y ejecuta `ffmpeg -version`. Si el comando no se reconoce, añade la carpeta que contiene `ffmpeg.exe` a la variable de entorno `PATH` y reinicia el bot.

## Uso

Usa `/start` para ver la bienvenida y `/ayuda` para las instrucciones. Envía una URL pública, pulsa **Descargar video** o **Descargar audio (MP3)** y el bot enviará el resultado.

## Configuración

| Variable | Descripción | Predeterminado |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` / `BOT_TOKEN` | Token del bot, obligatorio. | — |
| `DOWNLOAD_DIR` | Directorio temporal de trabajos. | `downloads` |
| `MAX_UPLOAD_MB` | Tamaño máximo que el bot intenta subir. | `50` |
| `MAX_CONCURRENT_DOWNLOADS` | Descargas a la vez. | `3` |
| `LOG_LEVEL` | Nivel de registros. | `INFO` |

El límite real de envío depende de la configuración y las restricciones vigentes de la API de Telegram. Si un archivo lo supera, el bot informa el motivo y lo elimina de todos modos.

## Notas de uso responsable

Descarga únicamente contenido público que tengas derecho a guardar. Las restricciones, cuentas privadas, DRM y cambios en las plataformas pueden impedir una descarga. Mantén `yt-dlp` actualizado para incorporar correcciones de extractores.
