"""
Capa de DESCUBRIMIENTO: produce URLs de videos a partir de dos fuentes.

- Cuentas  → se enumeran con yt-dlp (--flat-playlist sobre https://tiktok.com/@user).
             Robusto y sin necesidad de Playwright; encaja con tu patrón de
             lista-de-cuentas en CSV.
- Hashtags → se buscan con TikTokApi (Playwright), que sí sabe firmar las
             peticiones internas de TikTok (msToken) que yt-dlp no maneja bien.

Ambas fuentes vuelcan a la misma cola (data/cola_videos.csv), deduplicada por id.
"""
import asyncio
from datetime import datetime, timezone

import pandas as pd
import yt_dlp

from . import config, storage


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _url_video(autor: str, video_id: str) -> str:
    return f"https://www.tiktok.com/@{autor}/video/{video_id}"


# ── Cuentas (yt-dlp) ──────────────────────────────────────────────────
def descubrir_cuenta(usuario: str, maximo: int) -> list[dict]:
    """Lista los últimos `maximo` videos de una cuenta usando yt-dlp."""
    usuario = usuario.lstrip("@").strip()
    url_perfil = f"https://www.tiktok.com/@{usuario}"
    opts = {
        "quiet": True,
        "extract_flat": True,      # solo metadata de la lista, no descarga
        "playlistend": maximo,
        "ignoreerrors": True,
    }
    if config.COOKIES_NAVEGADOR:
        opts["cookiesfrombrowser"] = (config.COOKIES_NAVEGADOR,)

    encontrados = []
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url_perfil, download=False)
        for entry in (info or {}).get("entries", []) or []:
            if not entry:
                continue
            vid = str(entry.get("id", "")).strip()
            if not vid:
                continue
            url = entry.get("url") or _url_video(usuario, vid)
            encontrados.append({
                "video_id": vid,
                "url": url,
                "fuente_tipo": "cuenta",
                "fuente_valor": usuario,
                "descubierto_en": _ahora(),
            })
    except Exception as e:
        print(f"   ❌ Error descubriendo cuenta @{usuario}: {e}")
    return encontrados


# ── Hashtags (TikTokApi) ──────────────────────────────────────────────
async def _descubrir_hashtag_async(hashtag: str, maximo: int) -> list[dict]:
    from TikTokApi import TikTokApi  # import perezoso: solo si se usan hashtags

    hashtag = hashtag.lstrip("#").strip()
    ms_tokens = [config.MS_TOKEN] if config.MS_TOKEN else None
    encontrados = []
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=ms_tokens,
            num_sessions=1,
            sleep_after=3,
            browser=config.TIKTOKAPI_BROWSER,
            headless=config.TIKTOKAPI_HEADLESS,
        )
        tag = api.hashtag(name=hashtag)
        async for video in tag.videos(count=maximo):
            d = video.as_dict
            vid = str(d.get("id", "")).strip()
            autor = (d.get("author") or {}).get("uniqueId", "")
            if not vid:
                continue
            encontrados.append({
                "video_id": vid,
                "url": _url_video(autor, vid),
                "fuente_tipo": "hashtag",
                "fuente_valor": hashtag,
                "descubierto_en": _ahora(),
            })
    return encontrados


def descubrir_hashtag(hashtag: str, maximo: int) -> list[dict]:
    try:
        return asyncio.run(_descubrir_hashtag_async(hashtag, maximo))
    except Exception as e:
        print(f"   ❌ Error descubriendo #{hashtag}: {e}")
        print("      (Revisa TT_MS_TOKEN y que Playwright esté instalado: "
              "`playwright install chromium`)")
        return []


# ── Orquestación del descubrimiento ───────────────────────────────────
def _leer_columna(csv_path, columnas_posibles) -> list[str]:
    if not csv_path.exists():
        return []
    df = pd.read_csv(csv_path)
    for col in columnas_posibles:
        if col in df.columns:
            return [str(v).strip() for v in df[col].dropna() if str(v).strip()]
    # Si no hay encabezado reconocible, usar la primera columna
    return [str(v).strip() for v in df.iloc[:, 0].dropna() if str(v).strip()]


def ejecutar_descubrimiento(maximo: int | None = None) -> int:
    """Descubre videos de todas las cuentas y hashtags y los agrega a la cola."""
    config.crear_directorios()
    maximo = maximo or config.MAX_POR_FUENTE
    total_nuevos = 0

    cuentas = _leer_columna(config.CUENTAS_CSV, ["usuario", "cuenta", "user"])
    hashtags = _leer_columna(config.HASHTAGS_CSV, ["hashtag", "tag", "termino"])

    print(f"🔎 Descubrimiento: {len(cuentas)} cuentas, {len(hashtags)} hashtags "
          f"(máx {maximo} por fuente)\n")

    for usuario in cuentas:
        print(f"👤 Cuenta @{usuario} ...")
        videos = descubrir_cuenta(usuario, maximo)
        nuevos = storage.agregar_a_cola(videos)
        total_nuevos += nuevos
        print(f"   ✅ {len(videos)} encontrados, {nuevos} nuevos en la cola")

    for hashtag in hashtags:
        print(f"#️⃣  Hashtag #{hashtag} ...")
        videos = descubrir_hashtag(hashtag, maximo)
        nuevos = storage.agregar_a_cola(videos)
        total_nuevos += nuevos
        print(f"   ✅ {len(videos)} encontrados, {nuevos} nuevos en la cola")

    print(f"\n📥 Total de videos nuevos agregados a la cola: {total_nuevos}")
    return total_nuevos
