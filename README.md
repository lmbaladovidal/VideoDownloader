# 🎬 YouTube Video & Audio Downloader

Aplicación de escritorio nativa para Windows construida en **Python + PyQt6** con integración de **yt-dlp** y **FFmpeg**. Permite descargar videos de YouTube en diferentes resoluciones o extraer únicamente el audio en múltiples formatos, incluyendo soporte para **recortar fragmentos de tiempo** directamente desde los servidores sin necesidad de descargar el video completo.

---

## ✨ Características principales

- **Vista previa completa**: al pegar o analizar un enlace muestra miniatura 16:9, título, canal, duración, visualizaciones y fecha de publicación.
- **Descarga de Video (con audio)**:
  - Detecta dinámicamente las resoluciones reales disponibles en el video (`4K 2160p`, `2K 1440p`, `1080p Full HD`, `720p HD`, `480p`, `360p`, etc.) con sus FPS y tamaño estimado.
  - Contenedores soportados: **MP4**, **MKV**, **WebM**.
- **Extracción y conversión de Solo Audio**:
  - Formatos: **MP3**, **M4A (AAC)**, **WAV (Sin pérdida)**, **FLAC (Sin pérdida)** y **OPUS**.
  - Selección de bitrate (**320 kbps**, **256 kbps**, **192 kbps**, **128 kbps** o calidad original).
- **✂ Recorte por fragmento de tiempo**:
  - Permite descargar solo una parte del video o audio indicando tiempos manuales (`Desde` / `Hasta`) o escribiendo frases en lenguaje natural como:
    - *«del principio hasta el minuto 5»*
    - *«primeros 3 minutos»*
    - *«del minuto 1:30 al 4:45»*
    - *«desde el minuto 10 hasta el final»*
- **Barra de progreso en tiempo real**:
  - Progreso monotónico sin retrocesos con transición dinámica de color (**Rojo → Naranja/Amarillo → Verde** al llegar al `100%`).
  - Indicadores de velocidad, tamaño descargado y tiempo restante, más botón de cancelación inmediata.
  - Al finalizar, el botón principal cambia a **«📂 Abrir Carpeta»** para abrir directamente el directorio de salida.
- **Historial de descargas persistente**:
  - Tabla de descargas recientes con botones para reproducir el archivo (`▶ Abrir`) o abrir su carpeta (`📂 Carpeta`).

---

## 🚀 Ejecución desde el código fuente

1. Crear y activar el entorno virtual:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   ```
2. Ejecutar la aplicación:
   ```powershell
   .\.venv\Scripts\python main.py
   ```
   *(O hacer doble clic sobre `run.bat`)*.

---

## 🧪 Ejecutar la suite de tests

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 📦 Generar ejecutable e instalador de Windows

Para compilar la versión portable (`dist/YouTubeDownloader/YouTubeDownloader.exe`) y el asistente de instalación en un único archivo (`Instalador/Instalar_YouTubeDownloader.exe`) con `FFmpeg` incluido:

```powershell
.\.venv\Scripts\python build_installer.py
```
