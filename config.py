"""
Configuración central del scraper de TikTok.

Todo se puede sobreescribir con variables de entorno (útil para correr en
servidores o cambiar rutas sin tocar código). Los valores por defecto están
pensados para investigación en ciencias sociales sobre política latinoamericana.
"""
import os
from pathlib import Path

# ── Rutas ─────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
DATA_DIR   = Path(os.environ.get("TT_DATA_DIR", BASE_DIR / "data"))
VIDEO_DIR  = Path(os.environ.get("TT_VIDEO_DIR", BASE_DIR / "videos"))
SUB_DIR    = Path(os.environ.get("TT_SUB_DIR", BASE_DIR / "subtitulos"))

# Entradas
CUENTAS_CSV   = Path(os.environ.get("TT_CUENTAS_CSV", DATA_DIR / "cuentas.csv"))
HASHTAGS_CSV  = Path(os.environ.get("TT_HASHTAGS_CSV", DATA_DIR / "hashtags.csv"))

# Estado / salidas
COLA_CSV      = Path(os.environ.get("TT_COLA_CSV", DATA_DIR / "cola_videos.csv"))
RESULTADOS_CSV = Path(os.environ.get("TT_RESULTADOS_CSV", DATA_DIR / "tiktok_videos.csv"))

# ── Descubrimiento ────────────────────────────────────────────────────
# Máximo de videos a recolectar por cada cuenta o hashtag.
MAX_POR_FUENTE = int(os.environ.get("TT_MAX_POR_FUENTE", 100))

# msToken de TikTok para TikTokApi (búsqueda por hashtag). Se obtiene de las
# cookies del navegador (cookie "msToken" en tiktok.com). Si se deja vacío,
# TikTokApi intentará generar uno con Playwright, con menor tasa de éxito.
MS_TOKEN = os.environ.get("TT_MS_TOKEN", "").strip()

# Navegador que usa Playwright para firmar las peticiones de TikTokApi.
# "webkit" evade mejor la detección de bots de TikTok que "chromium".
TIKTOKAPI_BROWSER = os.environ.get("TT_TIKTOKAPI_BROWSER", "webkit")

# Si TikTok sigue detectando el bot, poner TT_HEADLESS=0 abre una ventana
# real del navegador (más lento pero mucho más difícil de detectar).
TIKTOKAPI_HEADLESS = os.environ.get("TT_HEADLESS", "1") == "1"

# ── Extracción (yt-dlp) ───────────────────────────────────────────────
# Reusar cookies del navegador para peticiones autenticadas (como tu scraper
# de X con el perfil de Firefox). Opciones: "firefox", "chrome", "safari", "".
COOKIES_NAVEGADOR = os.environ.get("TT_COOKIES_NAVEGADOR", "firefox").strip()

DESCARGAR_VIDEO   = os.environ.get("TT_DESCARGAR_VIDEO", "1") == "1"
IDIOMAS_SUBTITULOS = os.environ.get("TT_IDIOMAS_SUBS", "es,en").split(",")

# ── Transcripción (faster-whisper) ────────────────────────────────────
TRANSCRIBIR       = os.environ.get("TT_TRANSCRIBIR", "1") == "1"
# tiny | base | small | medium | large-v3  (más grande = más preciso y lento)
MODELO_WHISPER    = os.environ.get("TT_MODELO_WHISPER", "small")
# Pista de idioma; None => autodetección. Para contenido en español: "es".
IDIOMA_WHISPER    = os.environ.get("TT_IDIOMA_WHISPER", "es") or None
WHISPER_DEVICE    = os.environ.get("TT_WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE   = os.environ.get("TT_WHISPER_COMPUTE", "int8")

# ── Cortesía / anti-bloqueo ───────────────────────────────────────────
# Segundos de espera aleatoria entre peticiones (min, max), como en tu
# scraper de X para no gatillar detección de bots.
ESPERA_MIN = float(os.environ.get("TT_ESPERA_MIN", 3))
ESPERA_MAX = float(os.environ.get("TT_ESPERA_MAX", 7))

# Guardar el CSV de resultados cada N videos para no perder progreso.
GUARDAR_CADA = int(os.environ.get("TT_GUARDAR_CADA", 5))

# Reintentos de yt-dlp por video.
REINTENTOS = int(os.environ.get("TT_REINTENTOS", 3))


def crear_directorios():
    """Crea las carpetas necesarias si no existen."""
    for d in (DATA_DIR, VIDEO_DIR, SUB_DIR):
        d.mkdir(parents=True, exist_ok=True)
