# Ejercicio en clase: ¿cómo comunican los políticos colombianos en TikTok?

Cada estudiante corre el scraper sobre 6 cuentas de políticos, 5 videos por
cuenta (30 videos), y responde unas preguntas con el dataset que obtiene.
La corrida tarda entre 6 y 12 minutos según el computador.

## 1. Instalación (una sola vez)

Requisitos: Python 3.11 a 3.14 y git. No hace falta cuenta de TikTok ni ffmpeg.

**Windows (PowerShell)**

```powershell
git clone https://github.com/manuelcastiblan/tiktok-scraper tiktok_scraper
python -m venv venv_tiktok
venv_tiktok\Scripts\pip install -r tiktok_scraper\requirements.txt curl_cffi
```

**Mac / Linux (Terminal)**

```bash
git clone https://github.com/manuelcastiblan/tiktok-scraper tiktok_scraper
python3 -m venv venv_tiktok
venv_tiktok/bin/pip install -r tiktok_scraper/requirements.txt curl_cffi
```

La carpeta debe llamarse `tiktok_scraper` (con guion bajo) y los comandos se
corren desde la carpeta que la contiene, no desde adentro.

## 2. Definir las fuentes

Reemplaza el contenido de `tiktok_scraper/data/cuentas.csv` por:

```
usuario
carlosfgalan
ficogutierrez
palomavalencial
jotapehernandez
sergiofajardov
claudialopezcl
```

Y deja `tiktok_scraper/data/hashtags.csv` solo con el encabezado (los hashtags
exigen resolver un CAPTCHA y no entran en este ejercicio):

```
hashtag
```

## 3. Correr el scraper

**Windows (PowerShell)**

```powershell
$env:TT_COOKIES_NAVEGADOR = ""; venv_tiktok\Scripts\python -m tiktok_scraper.run all --max-por-fuente 5 --modelo-whisper base
```

**Mac / Linux**

```bash
TT_COOKIES_NAVEGADOR="" venv_tiktok/bin/python -m tiktok_scraper.run all --max-por-fuente 5 --modelo-whisper base
```

Qué va a pasar:

1. **Descubrir**: lista los 5 videos más recientes de cada cuenta y los pone en
   `data/cola_videos.csv`.
2. **Extraer**: por cada video baja el `.mp4` a `videos/`, guarda métricas y
   transcribe el audio con Whisper. La primera vez descarga el modelo (unos
   150 MB).
3. El resultado queda en `tiktok_scraper/data/tiktok_videos.csv`, una fila por
   video.

Si se corta, se vuelve a correr el mismo comando: retoma donde iba.

Avisos normales: `No video formats found!` es una publicación de fotos (no
tiene video y se salta); algunas transcripciones quedan vacías porque el video
solo tiene música.

## 4. Preguntas

Abre `tiktok_videos.csv` en Excel o con pandas.

1. ¿Qué cuenta tiene más vistas promedio por video? ¿Y más likes?
2. Calcula el *engagement* de cada video: `(likes + comentarios + compartidos) / vistas`.
   ¿El orden de las cuentas cambia frente al de vistas? ¿Por qué?
3. ¿Hay relación entre la duración (`duracion_seg`) y las vistas?
4. Lee la `transcripcion` del video más visto y del menos visto de una misma
   cuenta. ¿En qué se diferencian el tema, el tono y a quién le hablan?
5. ¿Qué hashtags se repiten entre cuentas? ¿Qué dicen de la agenda de cada una?
6. Límites del dato: son 5 videos por cuenta, los más recientes. ¿Qué no se
   puede concluir con esta muestra? ¿Qué fuentes agregarías?

Para quien use pandas:

```python
import pandas as pd
df = pd.read_csv("tiktok_scraper/data/tiktok_videos.csv")
df["engagement"] = (df.likes + df.comentarios + df.compartidos) / df.vistas
print(df.groupby("autor")[["vistas", "likes", "engagement", "duracion_seg"]].mean().round(3))
```

## Si algo falla

- `No module named tiktok_scraper`: estás dentro de la carpeta; sube un nivel.
- Una cuenta da `0 encontrados` o `Unable to extract secondary user ID`:
  vuelve a correr; si sigue, actualiza con
  `pip install -U yt-dlp` (usando el pip del `venv_tiktok`).
- Muy lento: usa `--modelo-whisper tiny` o agrega `--limite 15`. No uses
  `--sin-video`: sin el video no hay transcripción.
