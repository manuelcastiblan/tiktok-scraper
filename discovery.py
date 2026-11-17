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
        # Sin "ignoreerrors": si yt-dlp no puede listar el perfil queremos el
        # error visible, no un "0 encontrados" indistinguible de cuenta vacía.
    }

    encontrados = []
    try:
        opts.update(config.opciones_ytdlp_comunes())
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
def _opciones_perfil(headless: bool) -> dict:
    opts = {"headless": headless}
    if config.TIKTOKAPI_CANAL and config.TIKTOKAPI_BROWSER == "chromium":
        opts["channel"] = config.TIKTOKAPI_CANAL
    return opts


def _nombre_navegador() -> str:
    return _opciones_perfil(False).get("channel") or config.TIKTOKAPI_BROWSER


async def _contexto_persistente(playwright):
    """Contexto de Playwright sobre el perfil guardado en config.PERFIL_DIR."""
    motor = getattr(playwright, config.TIKTOKAPI_BROWSER)
    return await motor.launch_persistent_context(
        str(config.PERFIL_DIR), **_opciones_perfil(config.TIKTOKAPI_HEADLESS))


async def _contexto_con_canal(playwright):
    """Contexto efímero sobre un navegador instalado (canal chrome/msedge)."""
    navegador = await playwright.chromium.launch(
        **_opciones_perfil(config.TIKTOKAPI_HEADLESS))
    return await navegador.new_context()


async def _descubrir_hashtag_pagina(hashtag: str, maximo: int) -> list[dict]:
    """
    Descubre videos de un hashtag con la sesión guardada por `sesion`: abre la
    página pública del hashtag y lee las respuestas `api/challenge/item_list`
    que pide la propia página al hacer scroll. No firma peticiones (lo hace el
    sitio), así que no depende de que TikTokApi esté al día.
    """
    from playwright.async_api import async_playwright

    hashtag = hashtag.lstrip("#").strip()
    autores: dict[str, str] = {}  # video_id -> autor, en orden de aparición

    async def al_responder(resp):
        if "/api/challenge/item_list" not in resp.url:
            return
        try:
            datos = await resp.json()
        except Exception:
            return  # cuerpo vacío => TikTok no entregó la lista
        for item in datos.get("itemList") or []:
            vid = str(item.get("id", "")).strip()
            if vid:
                autores.setdefault(vid, (item.get("author") or {}).get("uniqueId", ""))

    async with async_playwright() as p:
        contexto = await _contexto_persistente(p)
        try:
            pagina = contexto.pages[0] if contexto.pages else await contexto.new_page()
            pagina.on("response", al_responder)
            await pagina.goto(f"https://www.tiktok.com/tag/{hashtag}",
                              wait_until="domcontentloaded", timeout=60000)
            await pagina.wait_for_timeout(5000)
            sin_avance, previo = 0, -1
            while len(autores) < maximo and sin_avance < 5:
                sin_avance = sin_avance + 1 if len(autores) == previo else 0
                previo = len(autores)
                await pagina.mouse.wheel(0, 4000)
                await pagina.wait_for_timeout(1500)
            if not autores:
                captcha = await pagina.locator(
                    '[class*=captcha], [id*=captcha]').count()
                if captcha:
                    raise RuntimeError(
                        "TikTok pide CAPTCHA otra vez: corre `sesion` y resuélvelo")
        finally:
            await contexto.close()

    return [{
        "video_id": vid,
        "url": _url_video(autor, vid),
        "fuente_tipo": "hashtag",
        "fuente_valor": hashtag,
        "descubierto_en": _ahora(),
    } for vid, autor in list(autores.items())[:maximo]]


def _fabrica_pagina(url: str):
    """
    TikTokApi espera `networkidle` tras abrir la página, pero en Chrome TikTok
    nunca deja la red inactiva y la sesión muere por timeout (30 s). Abrimos
    nosotros la página y hacemos esa espera tolerante: como mucho 10 s.
    """
    async def crear(contexto):
        pagina = await contexto.new_page()
        await pagina.goto(url, wait_until="domcontentloaded", timeout=60000)
        esperar = pagina.wait_for_load_state

        async def esperar_tolerante(state="load", **_kw):
            try:
                await esperar(state, timeout=10000)
            except Exception:
                pass

        pagina.wait_for_load_state = esperar_tolerante
        return pagina
    return crear


def abrir_sesion(hashtag: str = "colombia"):
    """
    Abre el perfil persistente en una ventana VISIBLE sobre la página de un
    hashtag, para que una persona resuelva el CAPTCHA (y, si quiere, inicie
    sesión). Termina cuando se cierra la ventana; la sesión queda guardada.
    """
    from playwright.sync_api import sync_playwright

    config.PERFIL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"🪟 Abriendo {_nombre_navegador()} con el perfil {config.PERFIL_DIR}")
    print("   1) Resuelve el CAPTCHA si aparece (y entra a tu cuenta si quieres).")
    print("   2) Comprueba que se ven los videos del hashtag.")
    print("   3) Cierra la ventana para guardar la sesión.")
    with sync_playwright() as p:
        ctx = getattr(p, config.TIKTOKAPI_BROWSER).launch_persistent_context(
            str(config.PERFIL_DIR), **_opciones_perfil(False))
        pagina = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            pagina.goto(f"https://www.tiktok.com/tag/{hashtag.lstrip('#')}",
                        wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"   ⚠️ No se pudo cargar la página: {e}")
        try:
            ctx.wait_for_event("close", timeout=0)  # hasta que cierres la ventana
        except Exception:
            pass  # ventana ya cerrada
    print("✅ Sesión guardada. Ya puedes correr `descubrir`.")


async def _descubrir_hashtag_async(hashtag: str, maximo: int) -> list[dict]:
    from TikTokApi import TikTokApi  # import perezoso: solo si se usan hashtags

    hashtag = hashtag.lstrip("#").strip()
    ms_tokens = [config.MS_TOKEN] if config.MS_TOKEN else None
    encontrados = []
    extra = {}
    if "channel" in _opciones_perfil(True):
        # TikTokApi no sabe de canales: lanzamos nosotros el navegador instalado
        extra["browser_context_factory"] = _contexto_con_canal
    if extra:
        extra["page_factory"] = _fabrica_pagina(
            f"https://www.tiktok.com/tag/{hashtag}")
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=ms_tokens,
            num_sessions=1,
            sleep_after=3,
            browser=config.TIKTOKAPI_BROWSER,
            headless=config.TIKTOKAPI_HEADLESS,
            **extra,
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
        if config.PERFIL_DIR.is_dir():
            # Hay sesión guardada con `sesion`: leer la página directamente
            return asyncio.run(_descubrir_hashtag_pagina(hashtag, maximo))
        return asyncio.run(_descubrir_hashtag_async(hashtag, maximo))
    except Exception as e:
        print(f"   ❌ Error descubriendo #{hashtag}: {e}")
        print("      (Si dice 'empty response', TikTok pide CAPTCHA: corre el "
              "comando `sesion` y resuélvelo. Revisa también que Playwright "
              f"esté instalado: `playwright install {config.TIKTOKAPI_BROWSER}`)")
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


def _marca(videos: list) -> str:
    return "✅" if videos else "⚠️"


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
        print(f"   {_marca(videos)} {len(videos)} encontrados, {nuevos} nuevos en la cola")

    for hashtag in hashtags:
        print(f"#️⃣  Hashtag #{hashtag} ...")
        videos = descubrir_hashtag(hashtag, maximo)
        nuevos = storage.agregar_a_cola(videos)
        total_nuevos += nuevos
        print(f"   {_marca(videos)} {len(videos)} encontrados, {nuevos} nuevos en la cola")

    print(f"\n📥 Total de videos nuevos agregados a la cola: {total_nuevos}")
    return total_nuevos
