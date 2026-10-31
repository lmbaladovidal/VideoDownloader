import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QPixmap, QDesktopServices, QIcon, QFont, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QProgressBar,
    QFrame,
    QFileDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QStackedWidget,
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
)

from downloader import (
    VideoInfoWorker,
    DownloadWorker,
    ensure_ffmpeg,
    format_duration,
    parse_single_time,
    parse_natural_time_range,
    RESOLUTION_LABELS,
)
from history_manager import HistoryManager
from ui_styles import APP_STYLESHEET


YOUTUBE_URL_PATTERN = re.compile(
    r"^(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/.+$",
    re.IGNORECASE,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("YouTube Media Downloader — Video & Audio")
        self.setMinimumSize(880, 740)
        self.resize(940, 780)
        self._load_app_icon()

        self.history_manager = HistoryManager()
        self.output_dir = str(Path.home() / "Downloads")
        self.current_video_info: Optional[Dict[str, Any]] = None
        self.info_worker: Optional[VideoInfoWorker] = None
        self.download_worker: Optional[DownloadWorker] = None
        self.download_completed_mode: bool = False
        self.last_downloaded_file: Optional[str] = None

        self._init_ui()
        self.setStyleSheet(APP_STYLESHEET)
        self._populate_default_video_qualities()
        self._refresh_history_table()
        self._check_ffmpeg_status()

    def _init_ui(self) -> None:
        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(20, 18, 20, 18)
        root_layout.setSpacing(14)

        # 1. Header Bar
        header_layout = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        lbl_title = QLabel("🎬 YouTube Video & Audio Downloader")
        lbl_title.setObjectName("AppTitle")
        lbl_sub = QLabel(
            "Descargá videos en hasta 4K/8K o extraé el audio en MP3, M4A, WAV, FLAC y OPUS"
        )
        lbl_sub.setObjectName("AppSubtitle")
        title_col.addWidget(lbl_title)
        title_col.addWidget(lbl_sub)

        header_layout.addLayout(title_col)
        header_layout.addStretch()

        self.lbl_ffmpeg_badge = QLabel("✔ FFmpeg listo")
        self.lbl_ffmpeg_badge.setObjectName("BadgeOk")
        header_layout.addWidget(self.lbl_ffmpeg_badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        root_layout.addLayout(header_layout)

        # 2. URL Input Card
        url_card = QFrame()
        url_card.setObjectName("Card")
        url_layout = QHBoxLayout(url_card)
        url_layout.setContentsMargins(14, 12, 14, 12)
        url_layout.setSpacing(10)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(
            "Pegá acá el enlace de YouTube (ej. https://www.youtube.com/watch?v=...)"
        )
        self.url_input.returnPressed.connect(self.analyze_url)
        self.url_input.textChanged.connect(self._reset_download_button)

        self.btn_paste = QPushButton("📋 Pegar")
        self.btn_paste.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_paste.setToolTip("Pegar enlace del portapapeles y analizar automáticamente")
        self.btn_paste.clicked.connect(self.paste_and_analyze)

        self.btn_analyze = QPushButton("🔍 Analizar Video")
        self.btn_analyze.setObjectName("AnalyzeButton")
        self.btn_analyze.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_analyze.clicked.connect(self.analyze_url)

        url_layout.addWidget(self.url_input, stretch=1)
        url_layout.addWidget(self.btn_paste)
        url_layout.addWidget(self.btn_analyze)
        root_layout.addWidget(url_card)

        # 3. Video Preview Card
        self.preview_card = QFrame()
        self.preview_card.setObjectName("PreviewCard")
        preview_layout = QHBoxLayout(self.preview_card)
        preview_layout.setContentsMargins(14, 12, 14, 12)
        preview_layout.setSpacing(16)

        self.lbl_thumbnail = QLabel("Sin vista previa\n\nPegá un enlace y tocá\n«Analizar Video»")
        self.lbl_thumbnail.setObjectName("ThumbnailBox")
        self.lbl_thumbnail.setFixedSize(224, 126)
        self.lbl_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.lbl_thumbnail)

        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(6)

        self.lbl_video_title = QLabel("Esperando enlace de YouTube...")
        self.lbl_video_title.setObjectName("VideoTitle")
        self.lbl_video_title.setWordWrap(True)

        self.lbl_video_channel = QLabel(
            "Analizá un enlace para ver la miniatura, duración y las calidades exactas disponibles."
        )
        self.lbl_video_channel.setObjectName("VideoMeta")

        badges_row = QHBoxLayout()
        badges_row.setSpacing(8)
        self.lbl_badge_duration = QLabel("⏱ —:—")
        self.lbl_badge_duration.setObjectName("VideoBadge")
        self.lbl_badge_views = QLabel("👁 —")
        self.lbl_badge_views.setObjectName("VideoBadge")
        self.lbl_badge_date = QLabel("📅 —")
        self.lbl_badge_date.setObjectName("VideoBadge")

        badges_row.addWidget(self.lbl_badge_duration)
        badges_row.addWidget(self.lbl_badge_views)
        badges_row.addWidget(self.lbl_badge_date)
        badges_row.addStretch()

        meta_layout.addWidget(self.lbl_video_title)
        meta_layout.addWidget(self.lbl_video_channel)
        meta_layout.addStretch()
        meta_layout.addLayout(badges_row)

        preview_layout.addLayout(meta_layout, stretch=1)
        root_layout.addWidget(self.preview_card)

        # 4. Format & Quality Configuration Card
        options_card = QFrame()
        options_card.setObjectName("Card")
        options_layout = QVBoxLayout(options_card)
        options_layout.setContentsMargins(14, 12, 14, 12)
        options_layout.setSpacing(12)

        # Mode switcher row
        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        lbl_mode = QLabel("Modo de descarga:")
        lbl_mode.setObjectName("SectionTitle")

        self.btn_mode_video = QPushButton("🎬 Video (con Audio)")
        self.btn_mode_video.setObjectName("ModeTab")
        self.btn_mode_video.setCheckable(True)
        self.btn_mode_video.setChecked(True)
        self.btn_mode_video.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_mode_audio = QPushButton("🎵 Solo Audio (Extraer / Convertir)")
        self.btn_mode_audio.setObjectName("ModeTab")
        self.btn_mode_audio.setCheckable(True)
        self.btn_mode_audio.setCursor(Qt.CursorShape.PointingHandCursor)

        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.btn_mode_video, 0)
        self.mode_group.addButton(self.btn_mode_audio, 1)
        self.mode_group.idClicked.connect(self._on_mode_changed)

        mode_row.addWidget(lbl_mode)
        mode_row.addWidget(self.btn_mode_video)
        mode_row.addWidget(self.btn_mode_audio)
        mode_row.addStretch()
        options_layout.addLayout(mode_row)

        # Stacked widget for Video vs Audio controls
        self.options_stack = QStackedWidget()

        # Page 0: Video options
        video_page = QWidget()
        video_page_layout = QHBoxLayout(video_page)
        video_page_layout.setContentsMargins(0, 0, 0, 0)
        video_page_layout.setSpacing(14)

        vq_col = QVBoxLayout()
        vq_col.setSpacing(4)
        vq_label = QLabel("Calidad / Resolución de Video:")
        vq_label.setObjectName("VideoMeta")
        self.combo_video_quality = QComboBox()
        self.combo_video_quality.currentIndexChanged.connect(self._reset_download_button)
        vq_col.addWidget(vq_label)
        vq_col.addWidget(self.combo_video_quality)

        vf_col = QVBoxLayout()
        vf_col.setSpacing(4)
        vf_label = QLabel("Formato contenedor:")
        vf_label.setObjectName("VideoMeta")
        self.combo_video_ext = QComboBox()
        self.combo_video_ext.addItem("MP4  —  Compatible universal (Recomendado)", "mp4")
        self.combo_video_ext.addItem("MKV  —  Matroska alta fidelidad", "mkv")
        self.combo_video_ext.addItem("WebM —  Formato nativo web", "webm")
        self.combo_video_ext.currentIndexChanged.connect(self._reset_download_button)
        vf_col.addWidget(vf_label)
        vf_col.addWidget(self.combo_video_ext)

        video_page_layout.addLayout(vq_col, stretch=3)
        video_page_layout.addLayout(vf_col, stretch=2)
        self.options_stack.addWidget(video_page)

        # Page 1: Audio options
        audio_page = QWidget()
        audio_page_layout = QHBoxLayout(audio_page)
        audio_page_layout.setContentsMargins(0, 0, 0, 0)
        audio_page_layout.setSpacing(14)

        af_col = QVBoxLayout()
        af_col.setSpacing(4)
        af_label = QLabel("Formato de Audio:")
        af_label.setObjectName("VideoMeta")
        self.combo_audio_codec = QComboBox()
        self.combo_audio_codec.addItem("MP3   —  Estándar universal", "mp3")
        self.combo_audio_codec.addItem("M4A   —  AAC (Ideal iPhone / Apple / Móvil)", "m4a")
        self.combo_audio_codec.addItem("WAV   —  Audio sin compresión (Sin pérdida)", "wav")
        self.combo_audio_codec.addItem("FLAC  —  Estudio sin pérdida (Lossless)", "flac")
        self.combo_audio_codec.addItem("OPUS  —  Máxima eficiencia de YouTube", "opus")
        self.combo_audio_codec.currentIndexChanged.connect(self._on_audio_codec_changed)
        self.combo_audio_codec.currentIndexChanged.connect(self._reset_download_button)
        af_col.addWidget(af_label)
        af_col.addWidget(self.combo_audio_codec)

        ab_col = QVBoxLayout()
        ab_col.setSpacing(4)
        ab_label = QLabel("Calidad de Audio (Bitrate):")
        ab_label.setObjectName("VideoMeta")
        self.combo_audio_bitrate = QComboBox()
        self.combo_audio_bitrate.addItem("320 kbps  —  Máxima calidad", "320")
        self.combo_audio_bitrate.addItem("256 kbps  —  Alta calidad", "256")
        self.combo_audio_bitrate.addItem("192 kbps  —  Calidad estándar equilibrada", "192")
        self.combo_audio_bitrate.addItem("128 kbps  —  Tamaño reducido", "128")
        self.combo_audio_bitrate.addItem("Mejor original sin recodificar extra", "0")
        self.combo_audio_bitrate.currentIndexChanged.connect(self._reset_download_button)
        ab_col.addWidget(ab_label)
        ab_col.addWidget(self.combo_audio_bitrate)

        audio_page_layout.addLayout(af_col, stretch=3)
        audio_page_layout.addLayout(ab_col, stretch=2)
        self.options_stack.addWidget(audio_page)

        options_layout.addWidget(self.options_stack)

        # Time range / Clip section
        clip_header_row = QHBoxLayout()
        clip_header_row.setSpacing(10)
        self.chk_clip = QCheckBox("✂ Recortar por tiempo (descargar solo un fragmento)")
        self.chk_clip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_clip.toggled.connect(self._on_clip_toggled)

        self.lbl_clip_badge = QLabel("Duración completa")
        self.lbl_clip_badge.setObjectName("VideoBadge")

        clip_header_row.addWidget(self.chk_clip)
        clip_header_row.addStretch()
        clip_header_row.addWidget(self.lbl_clip_badge)
        options_layout.addLayout(clip_header_row)

        clip_inputs_row = QHBoxLayout()
        clip_inputs_row.setSpacing(10)

        lbl_ind = QLabel("Indicación:")
        lbl_ind.setObjectName("VideoMeta")
        self.txt_clip_natural = QLineEdit()
        self.txt_clip_natural.setPlaceholderText(
            "Ej: del principio hasta el minuto 5  |  primeros 3 min  |  del 1:30 al 4:00"
        )
        self.txt_clip_natural.textEdited.connect(self._on_clip_natural_edited)

        lbl_start = QLabel("Desde:")
        lbl_start.setObjectName("VideoMeta")
        self.txt_clip_start = QLineEdit()
        self.txt_clip_start.setPlaceholderText("00:00 (Inicio)")
        self.txt_clip_start.setFixedWidth(105)
        self.txt_clip_start.textEdited.connect(self._on_clip_manual_edited)

        lbl_end = QLabel("Hasta:")
        lbl_end.setObjectName("VideoMeta")
        self.txt_clip_end = QLineEdit()
        self.txt_clip_end.setPlaceholderText("05:00 (Fin)")
        self.txt_clip_end.setFixedWidth(105)
        self.txt_clip_end.textEdited.connect(self._on_clip_manual_edited)

        clip_inputs_row.addWidget(lbl_ind)
        clip_inputs_row.addWidget(self.txt_clip_natural, stretch=1)
        clip_inputs_row.addWidget(lbl_start)
        clip_inputs_row.addWidget(self.txt_clip_start)
        clip_inputs_row.addWidget(lbl_end)
        clip_inputs_row.addWidget(self.txt_clip_end)
        options_layout.addLayout(clip_inputs_row)

        # Destination folder row
        dest_row = QHBoxLayout()
        dest_row.setSpacing(10)
        lbl_dest = QLabel("Guardar en:")
        lbl_dest.setObjectName("VideoMeta")

        self.txt_output_dir = QLineEdit(self.output_dir)
        self.txt_output_dir.setReadOnly(True)

        self.btn_choose_dir = QPushButton("📂 Cambiar carpeta...")
        self.btn_choose_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_choose_dir.clicked.connect(self.choose_output_directory)

        self.btn_open_dir = QPushButton("↗ Abrir carpeta")
        self.btn_open_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_dir.clicked.connect(self.open_output_directory)

        dest_row.addWidget(lbl_dest)
        dest_row.addWidget(self.txt_output_dir, stretch=1)
        dest_row.addWidget(self.btn_choose_dir)
        dest_row.addWidget(self.btn_open_dir)
        options_layout.addLayout(dest_row)

        root_layout.addWidget(options_card)

        # 5. Progress & Download Action Card
        progress_card = QFrame()
        progress_card.setObjectName("Card")
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(14, 12, 14, 12)
        progress_layout.setSpacing(8)

        status_top_row = QHBoxLayout()
        self.lbl_status_stage = QLabel("Listo para descargar")
        self.lbl_status_stage.setObjectName("SectionTitle")

        self.lbl_status_stats = QLabel("")
        self.lbl_status_stats.setObjectName("VideoMeta")
        self.lbl_status_stats.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        status_top_row.addWidget(self.lbl_status_stage)
        status_top_row.addStretch()
        status_top_row.addWidget(self.lbl_status_stats)
        progress_layout.addLayout(status_top_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")

        self.btn_download = QPushButton("⬇  Descargar Ahora")
        self.btn_download.setObjectName("PrimaryButton")
        self.btn_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download.clicked.connect(self._on_primary_action_clicked)

        self.btn_cancel = QPushButton("✖ Cancelar")
        self.btn_cancel.setObjectName("DangerButton")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_download)

        action_row.addWidget(self.progress_bar, stretch=1)
        action_row.addWidget(self.btn_download)
        action_row.addWidget(self.btn_cancel)
        progress_layout.addLayout(action_row)

        root_layout.addWidget(progress_card)

        # 6. Recent Downloads History Card
        history_card = QFrame()
        history_card.setObjectName("Card")
        history_layout = QVBoxLayout(history_card)
        history_layout.setContentsMargins(14, 10, 14, 12)
        history_layout.setSpacing(8)

        history_header = QHBoxLayout()
        lbl_history = QLabel("🕘 Historial de descargas recientes")
        lbl_history.setObjectName("SectionTitle")

        self.btn_clear_history = QPushButton("🗑 Limpiar historial")
        self.btn_clear_history.setObjectName("SmallActionBtn")
        self.btn_clear_history.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_history.clicked.connect(self.clear_history)

        history_header.addWidget(lbl_history)
        history_header.addStretch()
        history_header.addWidget(self.btn_clear_history)
        history_layout.addLayout(history_header)

        self.table_history = QTableWidget(0, 5)
        self.table_history.setHorizontalHeaderLabels(
            ["Título", "Calidad / Formato", "Tamaño", "Fecha", "Acciones"]
        )
        self.table_history.verticalHeader().setVisible(False)
        self.table_history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_history.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        header = self.table_history.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table_history.setColumnWidth(4, 175)

        history_layout.addWidget(self.table_history, stretch=1)
        root_layout.addWidget(history_card, stretch=1)

    def _load_app_icon(self) -> None:
        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        icon_path = base_dir / "app_icon.ico"
        if not icon_path.exists():
            icon_path = Path(__file__).resolve().parent / "app_icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _check_ffmpeg_status(self) -> None:
        ffmpeg_dir = ensure_ffmpeg()
        if ffmpeg_dir:
            self.lbl_ffmpeg_badge.setText("✔ FFmpeg listo (Audio y Video HD activos)")
        else:
            self.lbl_ffmpeg_badge.setText("⚠ FFmpeg no detectado")

    def _populate_default_video_qualities(self) -> None:
        self.combo_video_quality.clear()
        self.combo_video_quality.addItem("Mejor calidad disponible (Automático)", None)
        for h in [2160, 1440, 1080, 720, 480, 360]:
            self.combo_video_quality.addItem(RESOLUTION_LABELS[h], h)

    def _on_mode_changed(self, mode_id: int) -> None:
        self.options_stack.setCurrentIndex(mode_id)
        self._reset_download_button()

    def _reset_download_button(self) -> None:
        if self.download_completed_mode:
            self.download_completed_mode = False
            self.last_downloaded_file = None
            self.btn_download.setText("⬇  Descargar Ahora")
            self.btn_download.setObjectName("PrimaryButton")
            self.btn_download.style().unpolish(self.btn_download)
            self.btn_download.style().polish(self.btn_download)

    def _set_open_folder_button_mode(self, filepath: str) -> None:
        self.download_completed_mode = True
        self.last_downloaded_file = filepath
        self.btn_download.setText("📂  Abrir Carpeta")
        self.btn_download.setObjectName("SuccessButton")
        self.btn_download.style().unpolish(self.btn_download)
        self.btn_download.style().polish(self.btn_download)

    def _on_primary_action_clicked(self) -> None:
        if self.download_completed_mode:
            self.open_output_directory()
            return
        self.start_download()

    def _update_progress_bar(self, percent: float, reset: bool = False) -> None:
        val = int(round(min(max(percent, 0.0), 100.0)))
        if not reset and val < self.progress_bar.value():
            val = self.progress_bar.value()

        self.progress_bar.setValue(val)

        # Interpolate Hue from 0° (Red) at 0% -> 135° (Green) at 100%
        ratio = val / 100.0
        end_hue = (ratio * 135.0) / 360.0
        start_hue = (max(0.0, ratio - 0.15) * 135.0) / 360.0

        c_start = QColor.fromHslF(start_hue, 0.85, 0.45).name()
        c_end = QColor.fromHslF(end_hue, 0.85, 0.50).name()

        self.progress_bar.setStyleSheet(
            f"""
            QProgressBar::chunk {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 {c_start},
                    stop: 1 {c_end}
                );
                border-radius: 7px;
            }}
            """
        )

    def _on_audio_codec_changed(self) -> None:
        codec = self.combo_audio_codec.currentData()
        if codec in ("wav", "flac"):
            self.combo_audio_bitrate.setEnabled(False)
            self.combo_audio_bitrate.setToolTip(
                "WAV y FLAC son formatos sin pérdida; conservan el 100% de la calidad original."
            )
        else:
            self.combo_audio_bitrate.setEnabled(True)
            self.combo_audio_bitrate.setToolTip("")

    def _set_clip_badge_style(self, text: str, obj_name: str) -> None:
        self.lbl_clip_badge.setText(text)
        self.lbl_clip_badge.setObjectName(obj_name)
        self.lbl_clip_badge.style().unpolish(self.lbl_clip_badge)
        self.lbl_clip_badge.style().polish(self.lbl_clip_badge)

    def _on_clip_toggled(self, checked: bool) -> None:
        self._reset_download_button()
        if not checked:
            self._set_clip_badge_style("Duración completa", "VideoBadge")
        else:
            self._refresh_clip_preview()

    def _on_clip_natural_edited(self, text: str) -> None:
        self._reset_download_button()
        cleaned = text.strip()
        if not cleaned:
            if not self.txt_clip_start.text().strip() and not self.txt_clip_end.text().strip():
                self.chk_clip.setChecked(False)
            self._refresh_clip_preview()
            return

        if not self.chk_clip.isChecked():
            self.chk_clip.blockSignals(True)
            self.chk_clip.setChecked(True)
            self.chk_clip.blockSignals(False)

        start_sec, end_sec, valid = parse_natural_time_range(cleaned)
        if valid:
            self.txt_clip_start.blockSignals(True)
            self.txt_clip_end.blockSignals(True)
            self.txt_clip_start.setText(format_duration(start_sec or 0.0))
            self.txt_clip_end.setText(format_duration(end_sec) if end_sec is not None else "final")
            self.txt_clip_start.blockSignals(False)
            self.txt_clip_end.blockSignals(False)
        self._refresh_clip_preview()

    def _on_clip_manual_edited(self, _text: str = "") -> None:
        self._reset_download_button()
        has_any = bool(self.txt_clip_start.text().strip() or self.txt_clip_end.text().strip())
        if has_any and not self.chk_clip.isChecked():
            self.chk_clip.blockSignals(True)
            self.chk_clip.setChecked(True)
            self.chk_clip.blockSignals(False)
        elif not has_any and not self.txt_clip_natural.text().strip():
            self.chk_clip.setChecked(False)
        self._refresh_clip_preview()

    def _resolve_clip_range(self) -> tuple[Optional[float], Optional[float], bool, str]:
        """Returns (start_sec, end_sec, is_valid, human_label)."""
        if not self.chk_clip.isChecked():
            return None, None, True, ""

        s_raw = self.txt_clip_start.text().strip()
        e_raw = self.txt_clip_end.text().strip()
        nat_raw = self.txt_clip_natural.text().strip()

        start_sec: Optional[float] = None
        end_sec: Optional[float] = None

        if s_raw or e_raw:
            start_sec = parse_single_time(s_raw, default_unit="m") if s_raw else 0.0
            if e_raw:
                end_sec = parse_single_time(e_raw, default_unit="m")
                is_end_word = e_raw.lower() in ("fin", "final", "el final", "end")
            else:
                end_sec = None
                is_end_word = True

            if start_sec is None or (e_raw and end_sec is None and not is_end_word):
                return None, None, False, "Formato de tiempo no válido (usá ej. 00:00 a 05:00)"
        elif nat_raw:
            start_sec, end_sec, valid = parse_natural_time_range(nat_raw)
            if not valid:
                return None, None, False, "Escribí ej: «del principio hasta el minuto 5»"
        else:
            return None, None, True, ""

        s_val = start_sec or 0.0
        if end_sec is not None and end_sec <= s_val:
            return s_val, end_sec, False, "El tiempo final debe ser mayor al inicial"

        if s_val == 0.0 and end_sec is None:
            return None, None, True, ""

        s_fmt = format_duration(s_val)
        if end_sec is not None:
            e_fmt = format_duration(end_sec)
            dur_fmt = format_duration(end_sec - s_val)
            label = f"✂ Tramo: {s_fmt} → {e_fmt} (Duración: {dur_fmt})"
        else:
            label = f"✂ Tramo: {s_fmt} → Final"

        return s_val, end_sec, True, label

    def _refresh_clip_preview(self) -> None:
        if not self.chk_clip.isChecked():
            self._set_clip_badge_style("Duración completa", "VideoBadge")
            return
        _s, _e, valid, label = self._resolve_clip_range()
        if not valid:
            self._set_clip_badge_style(f"⚠ {label}", "BadgeClipWarn")
        elif label:
            self._set_clip_badge_style(f"✔ {label}", "BadgeClipActive")
        else:
            self._set_clip_badge_style("Indicá inicio / fin o una frase", "VideoBadge")

    def paste_and_analyze(self) -> None:
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.url_input.setText(text)
            self.analyze_url()

    def analyze_url(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Enlace vacío", "Por favor pegá un enlace de YouTube primero.")
            return

        if self.info_worker and self.info_worker.isRunning():
            return

        self._reset_download_button()
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText("⏳ Analizando...")
        self.lbl_status_stage.setText("Obteniendo información del video y calidades disponibles...")
        self.lbl_status_stats.setText("")
        self.lbl_video_title.setText("Analizando enlace de YouTube...")
        self.lbl_video_channel.setText("Por favor esperá unos segundos...")
        self.lbl_thumbnail.setPixmap(QPixmap())
        self.lbl_thumbnail.setText("Cargando\nminiatura...")

        self.info_worker = VideoInfoWorker(url)
        self.info_worker.info_ready.connect(self._on_info_ready)
        self.info_worker.error_occurred.connect(self._on_info_error)
        self.info_worker.start()

    def _on_info_ready(self, info: Dict[str, Any]) -> None:
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("🔍 Analizar Video")
        self.current_video_info = info

        self.lbl_video_title.setText(info.get("title", "Video de YouTube"))
        self.lbl_video_channel.setText(f"Canal: {info.get('channel', 'Desconocido')}")
        self.lbl_badge_duration.setText(f"⏱ {info.get('duration_str', '—')}")
        self.lbl_badge_views.setText(f"👁 {info.get('views_str') or '—'}")
        self.lbl_badge_date.setText(f"📅 {info.get('upload_date_str') or '—'}")

        # Populate exact available video resolutions
        video_qualities: List[Dict[str, Any]] = info.get("video_qualities") or []
        if video_qualities:
            self.combo_video_quality.clear()
            for q in video_qualities:
                self.combo_video_quality.addItem(q["label"], q["height"])
            # Pre-select 1080p if present, otherwise first specific resolution
            selected_idx = 0
            for idx, q in enumerate(video_qualities):
                if q.get("height") == 1080:
                    selected_idx = idx
                    break
                elif idx == 1:
                    selected_idx = 1
            self.combo_video_quality.setCurrentIndex(selected_idx)

        # Render thumbnail
        thumb_bytes: bytes = info.get("thumbnail_bytes") or b""
        if thumb_bytes:
            pixmap = QPixmap()
            if pixmap.loadFromData(thumb_bytes):
                scaled = pixmap.scaled(
                    self.lbl_thumbnail.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                # Center crop to fit 224x126 cleanly
                x_off = max(0, (scaled.width() - self.lbl_thumbnail.width()) // 2)
                y_off = max(0, (scaled.height() - self.lbl_thumbnail.height()) // 2)
                cropped = scaled.copy(
                    x_off, y_off, self.lbl_thumbnail.width(), self.lbl_thumbnail.height()
                )
                self.lbl_thumbnail.setText("")
                self.lbl_thumbnail.setPixmap(cropped)
            else:
                self.lbl_thumbnail.setText("Miniatura\nno disponible")
        else:
            self.lbl_thumbnail.setText("Miniatura\nno disponible")

        num_res = max(0, len(video_qualities) - 1)
        self.lbl_status_stage.setText(
            f"✔ Video analizado ({num_res} resoluciones disponibles). Elegí el formato y presioná Descargar."
        )

    def _on_info_error(self, error_msg: str) -> None:
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("🔍 Analizar Video")
        self.lbl_status_stage.setText("Error al analizar el enlace")
        self.lbl_video_title.setText("No se pudo cargar el video")
        self.lbl_video_channel.setText("Verificá que el enlace de YouTube sea válido y público.")
        self.lbl_thumbnail.setText("Error al\ncargar")
        QMessageBox.critical(self, "Error al analizar", error_msg)

    def choose_output_directory(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de descarga", self.output_dir
        )
        if folder:
            self.output_dir = str(Path(folder))
            self.txt_output_dir.setText(self.output_dir)

    def open_output_directory(self) -> None:
        target_dir = os.path.normpath(self.txt_output_dir.text().strip() or self.output_dir)
        os.makedirs(target_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(target_dir)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(target_dir))

    def start_download(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Enlace requerido", "Pegá un enlace de YouTube para descargar.")
            return

        if self.download_worker and self.download_worker.isRunning():
            return

        start_sec, end_sec, clip_valid, clip_label = self._resolve_clip_range()
        if not clip_valid:
            QMessageBox.warning(
                self,
                "Rango de tiempo inválido",
                f"Revisá la indicación de recorte:\n{clip_label}\n\n"
                "Ejemplos válidos:\n"
                "• «del principio hasta el minuto 5»\n"
                "• «primeros 3 minutos»\n"
                "• «del minuto 1:30 al 4:00»\n"
                "• Desde: 00:00  |  Hasta: 05:00",
            )
            return

        is_video_mode = self.btn_mode_video.isChecked()
        mode = "video" if is_video_mode else "audio"

        video_height: Optional[int] = self.combo_video_quality.currentData()
        video_ext: str = self.combo_video_ext.currentData() or "mp4"
        audio_codec: str = self.combo_audio_codec.currentData() or "mp3"
        audio_bitrate: str = self.combo_audio_bitrate.currentData() or "320"

        if is_video_mode:
            res_text = f"{video_height}p" if video_height else "Mejor calidad"
            quality_summary = f"🎬 Video {res_text} ({video_ext.upper()})"
        else:
            if audio_codec in ("wav", "flac"):
                quality_summary = f"🎵 Audio {audio_codec.upper()} (Sin pérdida)"
            elif audio_bitrate == "0":
                quality_summary = f"🎵 Audio {audio_codec.upper()} (Original)"
            else:
                quality_summary = f"🎵 Audio {audio_codec.upper()} ({audio_bitrate} kbps)"

        if clip_label:
            short_clip = clip_label.replace("✂ Tramo: ", "✂ ")
            quality_summary = f"{quality_summary}  •  {short_clip}"

        self._set_downloading_ui_state(True)
        self._update_progress_bar(0.0, reset=True)
        self.lbl_status_stage.setText("Iniciando descarga...")
        self.lbl_status_stats.setText("Conectando con YouTube...")

        self.download_worker = DownloadWorker(
            url=url,
            output_dir=self.output_dir,
            mode=mode,
            video_height=video_height,
            video_ext=video_ext,
            audio_codec=audio_codec,
            audio_bitrate=audio_bitrate,
            quality_summary=quality_summary,
            start_time=start_sec,
            end_time=end_sec,
        )
        self.download_worker.progress_updated.connect(self._on_download_progress)
        self.download_worker.download_complete.connect(self._on_download_complete)
        self.download_worker.download_error.connect(self._on_download_error)
        self.download_worker.download_cancelled.connect(self._on_download_cancelled)
        self.download_worker.start()

    def cancel_download(self) -> None:
        if self.download_worker and self.download_worker.isRunning():
            self.lbl_status_stage.setText("Cancelando descarga...")
            self.btn_cancel.setEnabled(False)
            self.download_worker.cancel()

    def _on_download_progress(self, percent: float, stats_line: str, stage_label: str) -> None:
        self._update_progress_bar(percent)
        self.lbl_status_stage.setText(stage_label)
        self.lbl_status_stats.setText(stats_line)

    def _on_download_complete(self, filepath: str, title: str, quality_summary: str) -> None:
        self._set_downloading_ui_state(False)
        self._update_progress_bar(100.0)
        self.lbl_status_stage.setText(f"✔ ¡Descarga completada! ({Path(filepath).name})")
        self.lbl_status_stats.setText(quality_summary)
        self._set_open_folder_button_mode(filepath)

        channel = ""
        if self.current_video_info:
            channel = self.current_video_info.get("channel", "")

        mode = "video" if self.btn_mode_video.isChecked() else "audio"
        self.history_manager.add_entry(
            title=title,
            url=self.url_input.text().strip(),
            mode=mode,
            quality_label=quality_summary,
            file_path=filepath,
            channel=channel,
        )
        self._refresh_history_table()

    def _on_download_error(self, error_msg: str) -> None:
        self._set_downloading_ui_state(False)
        self.lbl_status_stage.setText("✖ Error durante la descarga")
        self.lbl_status_stats.setText("")
        QMessageBox.critical(
            self,
            "Error en la descarga",
            f"Ocurrió un problema al descargar el archivo:\n\n{error_msg}",
        )

    def _on_download_cancelled(self) -> None:
        self._set_downloading_ui_state(False)
        self._update_progress_bar(0.0, reset=True)
        self.lbl_status_stage.setText("Descarga cancelada por el usuario.")
        self.lbl_status_stats.setText("")

    def _set_downloading_ui_state(self, downloading: bool) -> None:
        self.btn_download.setEnabled(not downloading)
        self.btn_cancel.setEnabled(downloading)
        self.btn_analyze.setEnabled(not downloading)
        self.btn_paste.setEnabled(not downloading)
        self.url_input.setEnabled(not downloading)
        self.btn_mode_video.setEnabled(not downloading)
        self.btn_mode_audio.setEnabled(not downloading)
        self.combo_video_quality.setEnabled(not downloading)
        self.combo_video_ext.setEnabled(not downloading)
        self.combo_audio_codec.setEnabled(not downloading)
        self.chk_clip.setEnabled(not downloading)
        self.txt_clip_natural.setEnabled(not downloading)
        self.txt_clip_start.setEnabled(not downloading)
        self.txt_clip_end.setEnabled(not downloading)
        if not downloading:
            self._on_audio_codec_changed()
        else:
            self.combo_audio_bitrate.setEnabled(False)

    def _refresh_history_table(self) -> None:
        items = self.history_manager.load_history()
        self.table_history.setRowCount(len(items))

        for row_idx, entry in enumerate(items):
            title_item = QTableWidgetItem(entry.get("title", ""))
            title_item.setToolTip(entry.get("file_path", ""))

            quality_item = QTableWidgetItem(entry.get("quality_label", ""))
            size_item = QTableWidgetItem(entry.get("file_size") or "—")
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            date_item = QTableWidgetItem(entry.get("timestamp", ""))
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table_history.setItem(row_idx, 0, title_item)
            self.table_history.setItem(row_idx, 1, quality_item)
            self.table_history.setItem(row_idx, 2, size_item)
            self.table_history.setItem(row_idx, 3, date_item)

            # Action buttons cell
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(6, 2, 6, 2)
            actions_layout.setSpacing(6)

            file_path = entry.get("file_path", "")

            btn_open_file = QPushButton("▶ Abrir")
            btn_open_file.setObjectName("SmallActionBtn")
            btn_open_file.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_open_file.setToolTip("Reproducir / abrir archivo")
            btn_open_file.clicked.connect(
                lambda checked=False, p=file_path: self._open_file(p)
            )

            btn_show_folder = QPushButton("📂 Carpeta")
            btn_show_folder.setObjectName("SmallActionBtn")
            btn_show_folder.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_show_folder.setToolTip("Mostrar archivo en el Explorador de Windows")
            btn_show_folder.clicked.connect(
                lambda checked=False, p=file_path: self._reveal_in_explorer(p)
            )

            actions_layout.addWidget(btn_open_file)
            actions_layout.addWidget(btn_show_folder)
            self.table_history.setCellWidget(row_idx, 4, actions_widget)
            self.table_history.setRowHeight(row_idx, 38)

    def _open_file(self, file_path: str) -> None:
        if file_path and os.path.exists(file_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
        else:
            QMessageBox.warning(
                self,
                "Archivo no encontrado",
                f"El archivo ya no se encuentra en la ruta original:\n{file_path}",
            )

    def _reveal_in_explorer(self, file_path: str) -> None:
        if not file_path:
            self.open_output_directory()
            return
        path_obj = Path(file_path)
        target_dir = path_obj.parent if path_obj.parent.exists() else Path(self.output_dir)
        if target_dir.exists():
            norm_dir = os.path.normpath(str(target_dir))
            if sys.platform == "win32":
                os.startfile(norm_dir)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(norm_dir))
        else:
            QMessageBox.warning(
                self,
                "Carpeta no encontrada",
                f"No se encontró la ubicación:\n{file_path}",
            )

    def clear_history(self) -> None:
        self.history_manager.clear_history()
        self._refresh_history_table()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("YouTube Media Downloader")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

