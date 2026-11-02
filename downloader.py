import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import certifi
import requests
import yt_dlp
from yt_dlp.downloader.external import FFmpegFD
from yt_dlp.utils import download_range_func, encodeArgument, Popen
from PyQt6.QtCore import QThread, pyqtSignal


# Ensure Windows subprocess calls inside yt-dlp (deno, ffmpeg, ffprobe) never flash console windows
if sys.platform == "win32" and not getattr(Popen, "_no_window_patched", False):
    _orig_yt_popen_init = Popen.__init__

    def _win32_no_window_popen_init(self, args, *p_args, **p_kwargs):
        p_kwargs["creationflags"] = p_kwargs.get("creationflags", 0) | 0x08000000
        _orig_yt_popen_init(self, args, *p_args, **p_kwargs)

    Popen.__init__ = _win32_no_window_popen_init
    Popen._no_window_patched = True


class DownloadCancelledError(Exception):
    """Raised when the user cancels an active download."""
    pass


def ensure_ffmpeg() -> Optional[str]:
    """
    Ensure ffmpeg, ffprobe, deno JS runtime, and SSL certificates are available in PATH/env
    (checking bundled dir first for standalone .exe, then PATH / static-ffmpeg / deno package).
    """
    try:
        ca_bundle = certifi.where()
        if ca_bundle and os.path.exists(ca_bundle):
            os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
            os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)
    except Exception:
        pass

    candidate_dirs = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate_dirs.append(Path(meipass) / "ffmpeg_bin")
        exe_dir = Path(sys.executable).resolve().parent
        candidate_dirs.append(exe_dir / "ffmpeg_bin")
        candidate_dirs.append(exe_dir / "_internal" / "ffmpeg_bin")

    for d in candidate_dirs:
        if (d / "ffmpeg.exe").exists() or (d / "ffmpeg.EXE").exists():
            d_str = str(d)
            if d_str not in os.environ.get("PATH", ""):
                os.environ["PATH"] = d_str + os.pathsep + os.environ.get("PATH", "")
            return d_str

    # Ensure deno JS runtime from Python deno package is on PATH in dev mode
    if not shutil.which("deno"):
        try:
            import deno
            deno_bin = deno.find_deno_bin()
            if deno_bin and os.path.exists(deno_bin):
                deno_dir = str(Path(deno_bin).resolve().parent)
                if deno_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = deno_dir + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        try:
            import static_ffmpeg
            static_ffmpeg.add_paths()
            ffmpeg_path = shutil.which("ffmpeg")
        except Exception:
            pass
    if ffmpeg_path:
        return str(Path(ffmpeg_path).resolve().parent)
    return None


def extract_info_with_fallbacks(url: str, base_opts: Dict[str, Any], download: bool) -> Any:
    """
    Runs yt_dlp.YoutubeDL.extract_info with resilient YouTube player_client configurations.
    1) Default + Android (uses bundled Deno + EJS for full 4K/8K formats, plus Android fallback)
    2) Android + iOS mobile clients (bypasses web 429 / bot-check challenges without cookies)
    """
    profiles = [
        {"youtube": {"player_client": ["default", "android"]}},
        {"youtube": {"player_client": ["android", "ios"]}},
    ]
    last_exc: Optional[Exception] = None
    for idx, ext_args in enumerate(profiles):
        opts = dict(base_opts)
        opts["extractor_args"] = ext_args
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=download)
                return info, ydl
        except DownloadCancelledError:
            raise
        except Exception as e:
            last_exc = e
            err_text = str(e).lower()
            # Retry on next profile if YouTube blocked or returned no formats
            if idx < len(profiles) - 1 and any(
                k in err_text
                for k in ("bot", "sign in", "429", "no video formats", "reload", "Unable to download webpage".lower())
            ):
                continue
            raise
    if last_exc:
        raise last_exc
    return None, None


def format_bytes(num_bytes: Optional[float]) -> str:
    if not num_bytes or num_bytes <= 0:
        return "—"
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "—"
    total_sec = int(round(seconds))
    hours, remainder = divmod(total_sec, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_views(views: Optional[int]) -> str:
    if views is None:
        return ""
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f} M visualizaciones"
    if views >= 1_000:
        return f"{views / 1_000:.1f} K visualizaciones"
    return f"{views} visualizaciones"


def parse_single_time(text: str, default_unit: str = "m") -> Optional[float]:
    """
    Parses a time token into seconds.
    Supports:
      - 'principio', 'inicio', 'comienzo', '0' -> 0.0
      - 'fin', 'final' -> None
      - 'HH:MM:SS' or 'MM:SS' (e.g. '05:00' -> 300.0, '1:02:30' -> 3750.0)
      - '1h 20m 10s', '5m', '5 min', '5 minutos', '90s', '90 seg'
      - Plain number (e.g. '5' -> 5 minutes if default_unit=='m' else 5 seconds)
    """
    s = text.strip().lower()
    if not s:
        return None

    if s in ("principio", "el principio", "inicio", "el inicio", "comienzo", "el comienzo", "start"):
        return 0.0
    if s in ("fin", "el fin", "final", "el final", "end"):
        return None
    if "media hora" in s:
        return 1800.0

    # Clean leading words like "minuto", "min", "el"
    s = re.sub(r"^(el\s+)?(minuto|minutos|min|segundo|segundos|seg|hora|horas)\s*", "", s).strip()

    # Format HH:MM:SS or MM:SS
    if ":" in s:
        parts = s.split(":")
        try:
            nums = [float(p.strip().replace(",", ".")) for p in parts]
            if len(nums) == 2:
                return nums[0] * 60.0 + nums[1]
            elif len(nums) == 3:
                return nums[0] * 3600.0 + nums[1] * 60.0 + nums[2]
        except ValueError:
            return None

    # Compound units like "1h 20m 30s", "5 min", "45 seg"
    unit_pattern = re.findall(
        r"(\d+(?:[.,]\d+)?)\s*(horas?|hs?|h|minutos?|mins?|m|segundos?|segs?|s)\b", s
    )
    if unit_pattern:
        total = 0.0
        for val_str, unit in unit_pattern:
            val = float(val_str.replace(",", "."))
            if unit.startswith("h"):
                total += val * 3600.0
            elif unit.startswith("m"):
                total += val * 60.0
            else:
                total += val
        return total

    # Plain number
    m_num = re.match(r"^(\d+(?:[.,]\d+)?)$", s)
    if m_num:
        val = float(m_num.group(1).replace(",", "."))
        if val == 0:
            return 0.0
        return val * 60.0 if default_unit == "m" else val

    return None


def parse_natural_time_range(text: str) -> Tuple[Optional[float], Optional[float], bool]:
    """
    Parses natural Spanish time range indications into (start_seconds, end_seconds, is_valid).
    Examples:
      - 'del principio hasta el minuto 5' -> (0.0, 300.0, True)
      - 'primeros 5 minutos' -> (0.0, 300.0, True)
      - 'del minuto 2 al 5:30' -> (120.0, 330.0, True)
      - 'de 01:20 a 04:00' -> (80.0, 240.0, True)
      - 'desde el minuto 3 hasta el final' -> (180.0, None, True)
      - 'hasta el minuto 4' -> (0.0, 240.0, True)
    """
    raw = text.strip().lower()
    if not raw:
        return None, None, False

    default_unit = "s" if ("seg" in raw and "min" not in raw) else "m"

    # Case 1: "primeros X minutos/segundos" / "primeras X horas" / "primera media hora"
    m_first = re.search(
        r"primer(?:os|as|a|o)?\s+(.+)$", raw
    )
    if m_first:
        dur = parse_single_time(m_first.group(1), default_unit=default_unit)
        if dur is not None and dur > 0:
            return 0.0, dur, True

    # Case 2: Range with explicit start and end ("del ... hasta/al ...", "desde ... hasta/a ...", "X a Y", "X - Y")
    m_range = re.search(
        r"(?:desde|del|de)?\s*(.+?)\s+(?:hasta\s+el|hasta\s+la|hasta|al|a|-|–|→)\s+(.+)$",
        raw,
    )
    if m_range:
        left_raw = m_range.group(1).strip()
        right_raw = m_range.group(2).strip()

        start_sec = parse_single_time(left_raw, default_unit=default_unit)
        end_sec = parse_single_time(right_raw, default_unit=default_unit)

        is_end_final = any(w in right_raw for w in ("final", "fin"))
        if start_sec is not None and (end_sec is not None or is_end_final):
            if end_sec is not None and end_sec <= start_sec:
                return start_sec, end_sec, False
            return start_sec, end_sec, True

    # Case 3: "hasta el minuto X" (implies from start 0.0)
    m_until = re.search(r"^hasta\s+(?:el\s+|la\s+)?(.+)$", raw)
    if m_until:
        end_sec = parse_single_time(m_until.group(1), default_unit=default_unit)
        if end_sec is not None and end_sec > 0:
            return 0.0, end_sec, True

    # Case 4: "desde el minuto X" / "a partir del minuto X" (implies until end)
    m_since = re.search(r"^(?:desde|a\s+partir\s+de(?:l)?)\s+(?:el\s+|la\s+)?(.+)$", raw)
    if m_since:
        start_sec = parse_single_time(m_since.group(1), default_unit=default_unit)
        if start_sec is not None and start_sec >= 0:
            return start_sec, None, True

    return None, None, False


RESOLUTION_LABELS = {
    4320: "4320p (8K Ultra HD)",
    2160: "2160p (4K Ultra HD)",
    1440: "1440p (2K QHD)",
    1080: "1080p (Full HD)",
    720: "720p (HD)",
    480: "480p (Estándar)",
    360: "360p (Media)",
    240: "240p (Baja)",
    144: "144p (Muy baja)",
}


class VideoInfoWorker(QThread):
    """Fetches YouTube video metadata, available resolutions, and thumbnail image in background."""

    info_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url.strip()

    def run(self) -> None:
        try:
            ffmpeg_dir = ensure_ffmpeg()
            ydl_opts: Dict[str, Any] = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "extract_flat": False,
            }
            if ffmpeg_dir:
                ydl_opts["ffmpeg_location"] = ffmpeg_dir

            info, _ydl = extract_info_with_fallbacks(self.url, ydl_opts, download=False)

            if not info:
                self.error_occurred.emit("No se pudo obtener información del video.")
                return

            if "entries" in info and info["entries"]:
                info = info["entries"][0]

            title = info.get("title") or "Video sin título"
            channel = info.get("channel") or info.get("uploader") or "Canal desconocido"
            duration_sec = info.get("duration")
            duration_str = format_duration(duration_sec) if duration_sec else "En vivo / Desconocido"
            views_str = format_views(info.get("view_count"))
            webpage_url = info.get("webpage_url") or self.url

            upload_date_raw = info.get("upload_date") or ""
            upload_date_str = ""
            if len(upload_date_raw) == 8:
                upload_date_str = f"{upload_date_raw[6:8]}/{upload_date_raw[4:6]}/{upload_date_raw[0:4]}"

            formats = info.get("formats") or []
            best_audio_size = 0
            best_audio_tbr = 0.0
            for f in formats:
                vcodec = f.get("vcodec")
                acodec = f.get("acodec")
                if vcodec == "none" and acodec and acodec != "none":
                    size = f.get("filesize") or f.get("filesize_approx") or 0
                    tbr = f.get("tbr") or f.get("abr") or 0.0
                    if tbr >= best_audio_tbr:
                        best_audio_tbr = tbr
                        if size > 0:
                            best_audio_size = size

            heights_info: Dict[int, Dict[str, Any]] = {}
            for f in formats:
                vcodec = f.get("vcodec")
                height = f.get("height")
                if not height or vcodec == "none":
                    continue
                fps = f.get("fps") or 30
                size = f.get("filesize") or f.get("filesize_approx") or 0
                acodec = f.get("acodec")
                has_audio = acodec is not None and acodec != "none"
                est_total_size = size + (0 if has_audio else best_audio_size) if size > 0 else 0

                existing = heights_info.get(height)
                if not existing or est_total_size > existing["size"] or fps > existing["fps"]:
                    heights_info[height] = {
                        "height": height,
                        "fps": int(fps) if fps else 30,
                        "size": max(est_total_size, existing["size"] if existing else 0),
                    }

            sorted_heights = sorted(heights_info.keys(), reverse=True)
            video_qualities: List[Dict[str, Any]] = [
                {
                    "id": "best",
                    "height": None,
                    "label": "Mejor calidad disponible (Automático)",
                }
            ]
            for h in sorted_heights:
                h_data = heights_info[h]
                base_label = RESOLUTION_LABELS.get(h, f"{h}p")
                fps_suffix = f" {h_data['fps']}fps" if h_data["fps"] > 30 else ""
                size_suffix = f"  •  ~{format_bytes(h_data['size'])}" if h_data["size"] > 0 else ""
                video_qualities.append(
                    {
                        "id": str(h),
                        "height": h,
                        "label": f"{base_label}{fps_suffix}{size_suffix}",
                    }
                )

            thumbnail_bytes = b""
            thumb_url = info.get("thumbnail")
            thumbnails = info.get("thumbnails") or []
            preferred_urls = []
            for t in reversed(thumbnails):
                u = t.get("url")
                if u and (".jpg" in u.lower() or ".png" in u.lower()):
                    preferred_urls.append(u)
            if thumb_url:
                preferred_urls.insert(0, thumb_url)

            for candidate_url in preferred_urls[:4]:
                try:
                    resp = requests.get(candidate_url, timeout=6)
                    if resp.status_code == 200 and resp.content:
                        thumbnail_bytes = resp.content
                        break
                except Exception:
                    continue

            result = {
                "title": title,
                "channel": channel,
                "duration": duration_sec,
                "duration_str": duration_str,
                "views_str": views_str,
                "upload_date_str": upload_date_str,
                "webpage_url": webpage_url,
                "video_qualities": video_qualities,
                "best_audio_size": format_bytes(best_audio_size) if best_audio_size > 0 else "",
                "thumbnail_bytes": thumbnail_bytes,
            }
            self.info_ready.emit(result)

        except Exception as e:
            clean_msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e))
            self.error_occurred.emit(f"No se pudo analizar el enlace:\n{clean_msg}")


class DownloadWorker(QThread):
    """Downloads video or audio (full or specific time range) with real-time progress hooks."""

    progress_updated = pyqtSignal(float, str, str)  # percent, stats_line, stage_label
    download_complete = pyqtSignal(str, str, str)   # final_filepath, title, quality_summary
    download_error = pyqtSignal(str)
    download_cancelled = pyqtSignal()

    def __init__(
        self,
        url: str,
        output_dir: str,
        mode: str,               # "video" or "audio"
        video_height: Optional[int],
        video_ext: str,          # "mp4", "mkv", "webm"
        audio_codec: str,        # "mp3", "m4a", "wav", "flac", "opus"
        audio_bitrate: str,      # "320", "256", "192", "128", "0"
        quality_summary: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ):
        super().__init__()
        self.url = url.strip()
        self.output_dir = output_dir
        self.mode = mode
        self.video_height = video_height
        self.video_ext = video_ext.lower()
        self.audio_codec = audio_codec.lower()
        self.audio_bitrate = audio_bitrate
        self.quality_summary = quality_summary
        self.start_time = start_time
        self.end_time = end_time
        self.has_range = (start_time is not None and start_time > 0) or (end_time is not None)
        self._cancelled = False
        self._final_filepath: Optional[str] = None
        self._max_percent: float = 0.0
        self._stream_index: int = 0

    def cancel(self) -> None:
        self._cancelled = True

    def _emit_monotonic_progress(self, raw_percent: float, stats_line: str, stage_label: str) -> None:
        clamped = min(max(raw_percent, 0.0), 100.0)
        if clamped > self._max_percent:
            self._max_percent = clamped
        self.progress_updated.emit(self._max_percent, stats_line, stage_label)

    def _progress_hook(self, d: Dict[str, Any]) -> None:
        if self._cancelled:
            raise DownloadCancelledError("Descarga cancelada por el usuario.")

        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed")
            eta = d.get("eta")
            clip_pct = d.get("_clip_percent")

            if clip_pct is not None:
                stream_pct = min(max(float(clip_pct), 0.0), 100.0)
            else:
                stream_pct = (downloaded / total * 100.0) if total > 0 else 0.0
                stream_pct = min(max(stream_pct, 0.0), 100.0)

            if self.mode == "video":
                if self.has_range:
                    # FFmpegFD merges both streams directly or sequentially
                    overall_pct = stream_pct * 0.95
                    stage_text = "Descargando y recortando fragmento de video..."
                elif self._stream_index == 0:
                    overall_pct = stream_pct * 0.85
                    stage_text = "Descargando pista de video..."
                else:
                    overall_pct = 85.0 + (stream_pct * 0.11)
                    stage_text = "Descargando pista de audio..."
            else:
                overall_pct = stream_pct * 0.94
                stage_text = (
                    "Descargando fragmento de audio..."
                    if self.has_range
                    else "Descargando flujo de audio..."
                )

            speed_str = d.get("_speed_label") or (f"{format_bytes(speed)}/s" if speed else " En curso...")
            if d.get("_time_label"):
                size_str = f"{format_bytes(downloaded)} ({d['_time_label']})"
            elif total > 0:
                size_str = f"{format_bytes(downloaded)} / {format_bytes(total)}"
            else:
                size_str = format_bytes(downloaded)

            eta_str = format_duration(eta) if eta is not None else "—"

            stats_line = f"Velocidad: {speed_str}   •   Descargado: {size_str}   •   Restante: {eta_str}"
            self._emit_monotonic_progress(overall_pct, stats_line, stage_text)

        elif status == "finished":
            filename = d.get("filename")
            if filename:
                self._final_filepath = filename
            if self.mode == "video" and not self.has_range and self._stream_index == 0:
                self._stream_index += 1
                self._emit_monotonic_progress(
                    85.0,
                    "Pista de video descargada. Descargando audio...",
                    "Preparando pista de audio...",
                )
            else:
                target_pct = 96.0 if self.mode == "video" else 95.0
                self._emit_monotonic_progress(
                    target_pct,
                    "Descarga de datos completada. Procesando archivo final...",
                    "Uniendo / convirtiendo con FFmpeg...",
                )

    def _postprocessor_hook(self, d: Dict[str, Any]) -> None:
        if self._cancelled:
            raise DownloadCancelledError("Descarga cancelada por el usuario.")
        status = d.get("status")
        info_dict = d.get("info_dict") or {}
        filepath = info_dict.get("filepath")
        if filepath:
            self._final_filepath = filepath
        if status == "started":
            self._emit_monotonic_progress(
                98.0,
                "Ejecutando FFmpeg para generar el formato final...",
                "Procesando con FFmpeg...",
            )

    def _install_ffmpeg_progress_wrapper(self):
        """
        Wraps FFmpegFD._call_downloader during range downloads so that FFmpeg emits
        real-time progress (out_time_us & total_size) and responds immediately to Cancel.
        """
        worker = self
        orig_call_downloader = FFmpegFD._call_downloader

        def patched_call_downloader(fd_self, tmpfilename, info_dict):
            start_s = info_dict.get("section_start") or 0.0
            end_s = info_dict.get("section_end")
            vid_dur = info_dict.get("duration") or 0.0
            target_dur = (end_s - start_s) if end_s else max(0.0, vid_dur - start_s)

            # Temporarily disable 'quiet' so ffmpeg doesn't get '-loglevel quiet',
            # and inject '-progress pipe:2 -nostats' via external_downloader_args
            old_quiet = fd_self.params.get("quiet")
            fd_self.params["quiet"] = False
            ext_args = dict(fd_self.params.get("external_downloader_args") or {})
            default_args = list(ext_args.get("default") or [])
            if "-progress" not in default_args:
                default_args.extend(["-loglevel", "error", "-progress", "pipe:2", "-nostats"])
            ext_args["default"] = default_args
            fd_self.params["external_downloader_args"] = ext_args

            orig_popen_init = Popen.__init__

            def patched_popen_init(proc_self, args, *p_args, **p_kwargs):
                is_progress_run = isinstance(args, (list, tuple)) and any(
                    str(a) == "-progress" for a in args
                )
                if is_progress_run:
                    p_kwargs["stderr"] = subprocess.PIPE
                if sys.platform == "win32":
                    p_kwargs["creationflags"] = p_kwargs.get("creationflags", 0) | 0x08000000
                orig_popen_init(proc_self, args, *p_args, **p_kwargs)

                if not is_progress_run:
                    return

                orig_wait = proc_self.wait

                def patched_wait(*w_args, **w_kwargs):
                    # Restore original wait immediately so Popen.__exit__ won't re-run this
                    proc_self.wait = orig_wait
                    total_size = 0
                    speed_label = ""
                    if proc_self.stderr and not proc_self.stderr.closed:
                        try:
                            for raw_line in iter(proc_self.stderr.readline, b""):
                                if worker._cancelled:
                                    proc_self.kill()
                                    raise DownloadCancelledError("Descarga cancelada por el usuario.")
                                line = raw_line.decode("utf-8", errors="ignore").strip()
                                if line.startswith("total_size="):
                                    try:
                                        total_size = int(line.split("=", 1)[1].strip())
                                    except ValueError:
                                        pass
                                elif line.startswith("speed="):
                                    spd_val = line.split("=", 1)[1].strip()
                                    if spd_val and spd_val != "N/A":
                                        speed_label = spd_val
                                elif line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                                    try:
                                        us = int(line.split("=", 1)[1].strip())
                                        cur_sec = max(0.0, us / 1_000_000.0)
                                        pct = (cur_sec / target_dur * 100.0) if target_dur > 0 else 50.0
                                        pct = min(max(pct, 0.0), 99.5)
                                        time_lbl = (
                                            f"{format_duration(cur_sec)} / {format_duration(target_dur)}"
                                            if target_dur > 0
                                            else format_duration(cur_sec)
                                        )
                                        worker._progress_hook(
                                            {
                                                "status": "downloading",
                                                "downloaded_bytes": total_size,
                                                "_clip_percent": pct,
                                                "_time_label": time_lbl,
                                                "_speed_label": speed_label,
                                            }
                                        )
                                    except ValueError:
                                        pass
                        except ValueError:
                            # Guard against closed stream edge cases
                            pass
                    return orig_wait(*w_args, **w_kwargs)

                proc_self.wait = patched_wait

            Popen.__init__ = patched_popen_init
            try:
                return orig_call_downloader(fd_self, tmpfilename, info_dict)
            finally:
                Popen.__init__ = orig_popen_init
                fd_self.params["quiet"] = old_quiet

        FFmpegFD._call_downloader = patched_call_downloader
        return orig_call_downloader

    def run(self) -> None:
        orig_call_dl = None
        try:
            ffmpeg_dir = ensure_ffmpeg()
            os.makedirs(self.output_dir, exist_ok=True)

            range_suffix = ""
            if self.has_range:
                s_lbl = format_duration(self.start_time or 0.0).replace(":", "m") + "s"
                e_lbl = (
                    format_duration(self.end_time).replace(":", "m") + "s"
                    if self.end_time is not None
                    else "fin"
                )
                range_suffix = f" [{s_lbl}-{e_lbl}]"

            outtmpl = str(Path(self.output_dir) / f"%(title).160B [%(id)s]{range_suffix}.%(ext)s")

            ydl_opts: Dict[str, Any] = {
                "outtmpl": outtmpl,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [self._progress_hook],
                "postprocessor_hooks": [self._postprocessor_hook],
                "windowsfilenames": True,
            }
            if ffmpeg_dir:
                ydl_opts["ffmpeg_location"] = ffmpeg_dir

            if self.has_range:
                s_val = float(self.start_time or 0.0)
                e_val = float(self.end_time) if self.end_time is not None else float("inf")
                ydl_opts["download_ranges"] = download_range_func(None, [(s_val, e_val)])
                orig_call_dl = self._install_ffmpeg_progress_wrapper()

            if self.mode == "video":
                if self.video_height:
                    if self.video_ext == "mp4":
                        fmt = (
                            f"bestvideo[height<={self.video_height}][ext=mp4]+bestaudio[ext=m4a]/"
                            f"bestvideo[height<={self.video_height}]+bestaudio/"
                            f"best[height<={self.video_height}]"
                        )
                    else:
                        fmt = (
                            f"bestvideo[height<={self.video_height}]+bestaudio/"
                            f"best[height<={self.video_height}]"
                        )
                else:
                    if self.video_ext == "mp4":
                        fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
                    else:
                        fmt = "bestvideo+bestaudio/best"

                ydl_opts["format"] = fmt
                ydl_opts["merge_output_format"] = self.video_ext

            else:
                ydl_opts["format"] = "bestaudio/best"
                postprocessor: Dict[str, Any] = {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": self.audio_codec,
                }
                if self.audio_codec in ("mp3", "m4a", "opus") and self.audio_bitrate != "0":
                    postprocessor["preferredquality"] = self.audio_bitrate
                else:
                    postprocessor["preferredquality"] = "0"
                ydl_opts["postprocessors"] = [postprocessor]

            info, ydl = extract_info_with_fallbacks(self.url, ydl_opts, download=True)
            if "entries" in info and info["entries"]:
                info = info["entries"][0]

            title = info.get("title") or "Archivo descargado"

            resolved_path = self._final_filepath
            req_downloads = info.get("requested_downloads")
            if req_downloads and isinstance(req_downloads, list):
                last_dl = req_downloads[-1]
                if last_dl.get("filepath"):
                    resolved_path = last_dl["filepath"]

            if not resolved_path or not os.path.exists(resolved_path):
                prepared = Path(ydl.prepare_filename(info))
                target_ext = self.video_ext if self.mode == "video" else self.audio_codec
                candidate = prepared.with_suffix(f".{target_ext}")
                if candidate.exists():
                    resolved_path = str(candidate)
                elif prepared.exists():
                    resolved_path = str(prepared)
                else:
                    resolved_path = str(candidate)

            self.download_complete.emit(str(resolved_path), title, self.quality_summary)

        except DownloadCancelledError:
            self.download_cancelled.emit()
        except Exception as e:
            if self._cancelled:
                self.download_cancelled.emit()
                return
            clean_msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e))
            self.download_error.emit(clean_msg)
        finally:
            if orig_call_dl is not None:
                FFmpegFD._call_downloader = orig_call_dl
