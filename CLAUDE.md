# tiktok_scraper — guía para Claude

Scraper de TikTok para investigación en ciencias sociales (FLACSO): recolecta
videos de **cuentas** y **hashtags**, y por cada video extrae metadata +
métricas, transcripción del audio y el archivo `.mp4`. Probado de punta a punta
el 2026-08-10 (cuentas ✅, hashtags bloqueados hasta tener msToken, ver abajo).

## Entorno — SIEMPRE usar `venv_tiktok`

```bash
cd ~/Documents/flacso
venv_tiktok/bin/python -m tiktok_scraper.run <comando>
```

- `venv_tiktok/` = Python 3.13 con todo instalado (yt-dlp, TikTokApi, playwright,
  faster-whisper, pandas, curl_cffi). **No usar** `venv/` ni `venv2/` (el primero
  se cuelga al importar pandas) ni el Python del sistema (3.14, sin deps).
- ffmpeg instalado vía Homebrew (lo necesitan Whisper y yt-dlp).
- Playwright tiene chromium y webkit descargados.
- `curl_cffi` es obligatorio: sin él yt-dlp no impersona navegador y TikTok
  rechaza peticiones.

## Comandos

```bash
# 1) Descubrir videos (cuentas + hashtags) → llena data/cola_videos.csv
venv_tiktok/bin/python -m tiktok_scraper.run descubrir --max-por-fuente 50

# 2) Extraer lo pendiente de la cola → data/tiktok_videos.csv
venv_tiktok/bin/python -m tiktok_scraper.run extraer

# Ambos de una; flags útiles:
venv_tiktok/bin/python -m tiktok_scraper.run all --max-por-fuente 30 \
    --limite 10             # máx videos en esta corrida
#   --sin-video             # no bajar el .mp4
#   --sin-transcripcion     # no transcribir
#   --modelo-whisper medium # default: small (tiny = rápido pero regular)
```

## Arquitectura (2 fases + cola)

```
data/cuentas.csv  ─► discovery.descubrir_cuenta()  (yt-dlp --flat-playlist)
data/hashtags.csv ─► discovery.descubrir_hashtag() (TikTokApi + Playwright)
        └──► data/cola_videos.csv (dedup por video_id)
                └──► extract.extraer_video() (yt-dlp: metadata + subs + .mp4)
                        └──► transcribe.obtener_transcripcion()
                             (1º subtítulos .vtt, si no hay → faster-whisper)
                                └──► data/tiktok_videos.csv (1 fila/video)
```

- **Reanudable**: `extraer` salta todo `video_id` ya presente en
  `tiktok_videos.csv`. Guardado incremental cada 5 videos (`GUARDAR_CADA`).
- **Anti-bloqueo**: espera aleatoria 3–7 s entre videos; cookies de Firefox
  vía `cookiesfrombrowser` (patrón del scraper de X del usuario).

## Archivos

| Archivo | Rol |
|---|---|
| `config.py` | Toda la configuración; cada valor se sobreescribe con env var `TT_*` |
| `discovery.py` | Cuentas (yt-dlp) y hashtags (TikTokApi async) → cola |
| `extract.py` | yt-dlp por URL; mapea metadata al esquema del dataset |
| `transcribe.py` | Parseo de .vtt y fallback a faster-whisper (modelo cacheado global) |
| `storage.py` | Lectura/escritura de cola y resultados, dedup, ids procesados |
| `run.py` | CLI (`descubrir` / `extraer` / `all`) |
| `data/cuentas.csv` | Entrada: columna `usuario` (sin `@`) |
| `data/hashtags.csv` | Entrada: columna `hashtag` (sin `#`) |
| `videos/`, `subtitulos/` | `.mp4` y `.vtt` descargados, nombrados por video_id |

## Esquema de `data/tiktok_videos.csv`

`video_id, url, autor, autor_nombre, descripcion, hashtags, fecha, duracion_seg,
vistas, likes, comentarios, compartidos, guardados, musica, transcripcion,
fuente_transcripcion, ruta_video, resolucion, fuente_tipo, fuente_valor, extraido_en`

- `hashtags` separados por `|`; `fuente_transcripcion` ∈ {subtitulos, whisper, none};
  `fuente_tipo` ∈ {cuenta, hashtag}; `autor` = username (extraído de la URL
  canónica — NO usar `uploader_id`, que es un ID numérico).

## Problemas conocidos / gotchas

1. **Hashtags requieren `TT_MS_TOKEN`** (cookie `msToken` de tiktok.com, la
   copia el usuario desde las dev tools de Firefox; expira cada cierto tiempo).
   Sin token TikTok devuelve vacío SIEMPRE — ya se probó chromium, webkit y
   headless=False; no insistir por ese camino, pedir el token al usuario.
2. Cuentas con poco contenido o privadas devuelven 0–1 videos sin error
   (p. ej. @gustavopetro casi no publica; @petrogustavo no existe).
3. Whisper `tiny` transcribe regular; el default es `small`. Para análisis de
   discurso serio recomendar `medium` (más lento, corre en CPU).
4. TikTok cambia su web seguido: si la extracción falla masivamente, lo primero
   es actualizar yt-dlp (`venv_tiktok/bin/pip install -U yt-dlp`).
5. Los prints y comentarios van en español con emojis (convención del usuario).

## Extensiones previstas

- Comentarios de videos: crear `comments.py` con
  `TikTokApi.video(url).comments()` — misma cola/patrón, requiere msToken.
- El dataset conecta con el pipeline existente del usuario de análisis de
  texto/redes (ver notebooks `network_analysis_completo.ipynb`, `topicos.ipynb`).
