"""
Capa de EXTRACCIÓN: por cada URL de la cola, usa yt-dlp para obtener
metadata + subtítulos (+ opcionalmente el video .mp4), y luego resuelve la
transcripción. Devuelve un dict listo para guardar como fila del dataset.

yt-dlp es el descargador más robusto para TikTok, por eso se usa aquí en vez
de reimplementar la firma de peticiones.
"""
from datetime import datetime, timezone
from pathlib import Path

import yt_dlp

from . import config, transcribe


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fecha_iso(info: dict) -> str:
    ts = info.get("timestamp")
    if ts:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    d = info.get("upload_date")  # formato YYYYMMDD
    if d and len(str(d)) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return ""


def _hashtags(info: dict) -> str:
    tags = info.get("hashtags") or info.get("tags") or []
    if not tags:
        # yt-dlp a veces no separa hashtags; extraerlos de la descripción
        desc = info.get("description", "") or ""
        tags = [t.strip("#") for t in desc.split() if t.startswith("#")]
    return "|".join(dict.fromkeys(t for t in tags if t))  # dedup preservando orden


def _autor_username(info: dict, url_original: str) -> str:
    # La URL canónica .../@usuario/video/123 es la fuente más confiable;
    # uploader_id suele venir como ID numérico en TikTok.
    for url in (info.get("webpage_url", ""), url_original):
        if url and "/@" in url:
            usuario = url.split("/@")[1].split("/")[0].split("?")[0]
            if usuario:
                return usuario
    return info.get("uploader") or ""


def _musica(info: dict) -> str:
    track = info.get("track") or ""
    artista = info.get("artist") or ""
    return " - ".join(p for p in (artista, track) if p)


def _opciones_ytdlp(descargar_video: bool) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": not descargar_video,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": config.IDIOMAS_SUBTITULOS,
        "subtitlesformat": "vtt",
        "outtmpl": {
            "default": str(config.VIDEO_DIR / "%(id)s.%(ext)s"),
            "subtitle": str(config.SUB_DIR / "%(id)s.%(ext)s"),
        },
        "retries": config.REINTENTOS,
        "ignoreerrors": True,
        "noplaylist": True,
    }
    if config.COOKIES_NAVEGADOR:
        opts["cookiesfrombrowser"] = (config.COOKIES_NAVEGADOR,)
    return opts


def _ruta_video_local(info: dict, video_id: str) -> str:
    # yt-dlp reporta la ruta final en requested_downloads
    for d in info.get("requested_downloads", []) or []:
        fp = d.get("filepath")
        if fp and Path(fp).exists():
            return fp
    # Fallback: buscar por id en la carpeta de videos
    for f in config.VIDEO_DIR.glob(f"{video_id}.*"):
        if f.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv"):
            return str(f)
    return ""


def extraer_video(url: str, fuente_tipo: str = "", fuente_valor: str = "",
                  descargar_video: bool | None = None,
                  transcribir_flag: bool | None = None) -> dict | None:
    """Extrae un video completo. Devuelve dict o None si falla."""
    descargar_video = config.DESCARGAR_VIDEO if descargar_video is None else descargar_video
    transcribir_flag = config.TRANSCRIBIR if transcribir_flag is None else transcribir_flag

    try:
        with yt_dlp.YoutubeDL(_opciones_ytdlp(descargar_video)) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        print(f"   ❌ yt-dlp falló en {url}: {e}")
        return None

    if not info:
        return None

    video_id = str(info.get("id", "")).strip()
    ruta_video = _ruta_video_local(info, video_id) if descargar_video else ""

    transcripcion, fuente_trans = "", "none"
    if transcribir_flag:
        media_para_whisper = Path(ruta_video) if ruta_video else None
        transcripcion, fuente_trans = transcribe.obtener_transcripcion(
            video_id, media_para_whisper)

    return {
        "video_id": video_id,
        "url": info.get("webpage_url", url),
        "autor": _autor_username(info, url),
        "autor_nombre": info.get("creator") or info.get("channel")
                        or info.get("uploader") or "",
        "descripcion": info.get("description") or info.get("title") or "",
        "hashtags": _hashtags(info),
        "fecha": _fecha_iso(info),
        "duracion_seg": info.get("duration"),
        "vistas": info.get("view_count"),
        "likes": info.get("like_count"),
        "comentarios": info.get("comment_count"),
        "compartidos": info.get("repost_count"),
        "guardados": info.get("favorite_count"),
        "musica": _musica(info),
        "transcripcion": transcripcion,
        "fuente_transcripcion": fuente_trans,
        "ruta_video": ruta_video,
        "resolucion": f'{info.get("width", "")}x{info.get("height", "")}'.strip("x"),
        "fuente_tipo": fuente_tipo,
        "fuente_valor": fuente_valor,
        "extraido_en": _ahora(),
    }
