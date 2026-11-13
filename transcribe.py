"""
Transcripción del audio de cada video.

Estrategia en dos pasos:
1. Si yt-dlp bajó subtítulos (auto-captions de TikTok), se parsea el .vtt.
2. Si no hay subtítulos, se transcribe el audio con faster-whisper (corre en CPU,
   ideal para Mac; requiere ffmpeg instalado).

Devuelve (texto, fuente) donde fuente ∈ {"subtitulos", "whisper", "none"}.
"""
import re
from pathlib import Path

from . import config

_MODELO = None  # se carga una sola vez (perezoso)


# ── Parseo de subtítulos .vtt ─────────────────────────────────────────
def parsear_vtt(ruta_vtt: Path) -> str:
    """Extrae solo el texto de un archivo .vtt, sin timestamps ni duplicados."""
    try:
        lineas = ruta_vtt.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return ""
    texto = []
    for ln in lineas:
        ln = ln.strip()
        if (not ln or ln.startswith("WEBVTT") or "-->" in ln
                or ln.isdigit() or ln.startswith(("NOTE", "Kind:", "Language:"))):
            continue
        ln = re.sub(r"<[^>]+>", "", ln)  # quitar tags de estilo/karaoke
        if ln and (not texto or texto[-1] != ln):  # evitar líneas repetidas seguidas
            texto.append(ln)
    return " ".join(texto).strip()


def buscar_subtitulos(video_id: str, carpeta: Path) -> str:
    """Busca cualquier .vtt asociado al video en la carpeta dada."""
    for idioma in config.IDIOMAS_SUBTITULOS + ["*"]:
        for vtt in carpeta.glob(f"{video_id}*.{idioma.strip()}.vtt"):
            texto = parsear_vtt(vtt)
            if texto:
                return texto
    for vtt in carpeta.glob(f"{video_id}*.vtt"):
        texto = parsear_vtt(vtt)
        if texto:
            return texto
    return ""


# ── Transcripción con faster-whisper ──────────────────────────────────
def _cargar_modelo():
    global _MODELO
    if _MODELO is None:
        from faster_whisper import WhisperModel  # import perezoso
        print(f"🧠 Cargando modelo Whisper '{config.MODELO_WHISPER}' "
              f"({config.WHISPER_DEVICE}/{config.WHISPER_COMPUTE})...")
        _MODELO = WhisperModel(
            config.MODELO_WHISPER,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE,
        )
    return _MODELO


def transcribir_audio(ruta_media: Path) -> str:
    """Transcribe un archivo de audio/video con Whisper. Requiere ffmpeg."""
    if not ruta_media or not Path(ruta_media).exists():
        return ""
    try:
        modelo = _cargar_modelo()
        segmentos, _info = modelo.transcribe(
            str(ruta_media),
            language=config.IDIOMA_WHISPER,
            vad_filter=True,  # ignora silencios; mejora calidad en videos cortos
        )
        return " ".join(s.text.strip() for s in segmentos).strip()
    except Exception as e:
        print(f"   ⚠️ Error transcribiendo con Whisper: {e}")
        return ""


def obtener_transcripcion(video_id: str, ruta_media: Path | None) -> tuple[str, str]:
    """
    Intenta subtítulos primero; si no hay, usa Whisper sobre el media local.
    Devuelve (texto, fuente).
    """
    texto = buscar_subtitulos(video_id, config.SUB_DIR)
    if texto:
        return texto, "subtitulos"

    if ruta_media:
        texto = transcribir_audio(Path(ruta_media))
        if texto:
            return texto, "whisper"

    return "", "none"
