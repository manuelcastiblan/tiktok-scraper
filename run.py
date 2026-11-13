"""
Orquestador / CLI del scraper de TikTok.

Uso:
    # 1) Descubrir videos de cuentas y hashtags y llenar la cola
    python -m tiktok_scraper.run descubrir --max-por-fuente 100

    # 2) Extraer (metadata + transcripción + video) todo lo pendiente en la cola
    python -m tiktok_scraper.run extraer

    # Todo de una:
    python -m tiktok_scraper.run all --max-por-fuente 100

Flags útiles de `extraer` / `all`:
    --sin-video           No descargar el .mp4 (solo metadata + transcripción)
    --sin-transcripcion   No transcribir
    --modelo-whisper base Cambiar el modelo de Whisper
    --limite 50           Procesar como máximo 50 videos en esta corrida
"""
import argparse
import random
import time

from tqdm import tqdm

from . import config, discovery, extract, storage


def cmd_descubrir(args):
    discovery.ejecutar_descubrimiento(maximo=args.max_por_fuente)


def cmd_extraer(args):
    config.crear_directorios()
    cola = storage.cargar_cola()
    if cola.empty:
        print("⚠️ La cola está vacía. Corre primero `descubrir`.")
        return

    ya = storage.ids_procesados()
    pendientes = cola[~cola["video_id"].astype(str).isin(ya)].reset_index(drop=True)
    if args.limite:
        pendientes = pendientes.head(args.limite)

    resultados = storage.cargar_resultados()
    filas = resultados.to_dict("records") if not resultados.empty else []

    total = len(pendientes)
    print(f"🎯 En cola: {len(cola)} | ya procesados: {len(ya)} | "
          f"a procesar ahora: {total}\n")
    if total == 0:
        print("✅ No hay videos pendientes.")
        return

    procesados = 0
    for i, fila in enumerate(tqdm(pendientes.to_dict("records"), desc="Extrayendo"), 1):
        url = fila["url"]
        dato = extract.extraer_video(
            url,
            fuente_tipo=fila.get("fuente_tipo", ""),
            fuente_valor=fila.get("fuente_valor", ""),
            descargar_video=not args.sin_video,
            transcribir_flag=not args.sin_transcripcion,
        )
        if dato and dato["video_id"]:
            filas.append(dato)
            procesados += 1
            desc = (dato["descripcion"] or "")[:60].replace("\n", " ")
            tqdm.write(f"   ✅ [{i}/{total}] {dato['video_id']} — {desc}")
        else:
            tqdm.write(f"   ⚠️ [{i}/{total}] sin datos: {url}")

        # Guardado incremental
        if procesados and procesados % config.GUARDAR_CADA == 0:
            storage.guardar_resultados(__import__("pandas").DataFrame(filas))
            tqdm.write(f"   💾 Progreso guardado ({procesados} videos)")

        # Espera aleatoria anti-bloqueo (como tu scraper de X)
        time.sleep(random.uniform(config.ESPERA_MIN, config.ESPERA_MAX))

    import pandas as pd
    storage.guardar_resultados(pd.DataFrame(filas))
    print(f"\n🎉 Listo. {procesados} videos extraídos. "
          f"Dataset: {config.RESULTADOS_CSV}")


def cmd_all(args):
    cmd_descubrir(args)
    cmd_extraer(args)


def _aplicar_overrides(args):
    """Permite fijar el modelo de Whisper desde la CLI."""
    if getattr(args, "modelo_whisper", None):
        config.MODELO_WHISPER = args.modelo_whisper


def main():
    p = argparse.ArgumentParser(
        prog="tiktok_scraper",
        description="Scraper de TikTok (cuentas + hashtags) para investigación.",
    )
    sub = p.add_subparsers(dest="comando", required=True)

    # descubrir
    pd_ = sub.add_parser("descubrir", help="Llenar la cola desde cuentas/hashtags")
    pd_.add_argument("--max-por-fuente", type=int, default=config.MAX_POR_FUENTE)
    pd_.set_defaults(func=cmd_descubrir)

    # extraer
    pe = sub.add_parser("extraer", help="Extraer videos pendientes de la cola")
    pe.add_argument("--sin-video", action="store_true")
    pe.add_argument("--sin-transcripcion", action="store_true")
    pe.add_argument("--modelo-whisper", type=str, default=None)
    pe.add_argument("--limite", type=int, default=None)
    pe.set_defaults(func=cmd_extraer)

    # all
    pa = sub.add_parser("all", help="Descubrir y luego extraer")
    pa.add_argument("--max-por-fuente", type=int, default=config.MAX_POR_FUENTE)
    pa.add_argument("--sin-video", action="store_true")
    pa.add_argument("--sin-transcripcion", action="store_true")
    pa.add_argument("--modelo-whisper", type=str, default=None)
    pa.add_argument("--limite", type=int, default=None)
    pa.set_defaults(func=cmd_all)

    args = p.parse_args()
    _aplicar_overrides(args)
    args.func(args)


if __name__ == "__main__":
    main()
