"""
Almacenamiento incremental y reanudable (patrón de tus scrapers de X/LinkedIn).

- La COLA (cola_videos.csv) es la lista de URLs descubiertas pendientes de extraer.
- Los RESULTADOS (tiktok_videos.csv) tienen una fila por video ya procesado.

Reanudar = al iniciar, se leen los video_id ya presentes en resultados y se saltan.
"""
import pandas as pd

from . import config

# Columnas de la cola de descubrimiento
COLS_COLA = ["video_id", "url", "fuente_tipo", "fuente_valor", "descubierto_en"]

# Columnas del dataset final (una fila por video)
COLS_RESULTADOS = [
    "video_id", "url", "autor", "autor_nombre", "descripcion", "hashtags",
    "fecha", "duracion_seg", "vistas", "likes", "comentarios", "compartidos",
    "guardados", "musica", "transcripcion", "fuente_transcripcion",
    "ruta_video", "resolucion", "fuente_tipo", "fuente_valor", "extraido_en",
]


def cargar_cola() -> pd.DataFrame:
    """Devuelve la cola de videos descubiertos (vacía si no existe)."""
    if config.COLA_CSV.exists():
        return pd.read_csv(config.COLA_CSV, dtype={"video_id": str})
    return pd.DataFrame(columns=COLS_COLA)


def guardar_cola(df: pd.DataFrame):
    config.COLA_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.COLA_CSV, index=False)


def agregar_a_cola(nuevos: list[dict]) -> int:
    """
    Agrega videos a la cola evitando duplicados por video_id.
    Devuelve cuántos se agregaron realmente.
    """
    cola = cargar_cola()
    existentes = set(cola["video_id"].astype(str))
    filtrados = [n for n in nuevos if str(n["video_id"]) not in existentes]
    if filtrados:
        cola = pd.concat([cola, pd.DataFrame(filtrados)], ignore_index=True)
        cola = cola.drop_duplicates(subset="video_id", keep="first")
        guardar_cola(cola)
    return len(filtrados)


def cargar_resultados() -> pd.DataFrame:
    """Devuelve el dataset de resultados (vacío si no existe)."""
    if config.RESULTADOS_CSV.exists():
        return pd.read_csv(config.RESULTADOS_CSV, dtype={"video_id": str})
    return pd.DataFrame(columns=COLS_RESULTADOS)


def ids_procesados() -> set[str]:
    """Conjunto de video_id ya extraídos (para reanudar sin repetir)."""
    df = cargar_resultados()
    return set(df["video_id"].astype(str)) if not df.empty else set()


def guardar_resultados(df: pd.DataFrame):
    config.RESULTADOS_CSV.parent.mkdir(parents=True, exist_ok=True)
    # Mantener orden de columnas estable
    for c in COLS_RESULTADOS:
        if c not in df.columns:
            df[c] = None
    df = df[COLS_RESULTADOS]
    df.to_csv(config.RESULTADOS_CSV, index=False)
