import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure headless Qt rendering during tests
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6.QtWidgets import QApplication

from downloader import (
    DownloadWorker,
    DownloadCancelledError,
    Popen,
    FFmpegFD,
    ensure_ffmpeg,
    format_bytes,
    format_duration,
    format_views,
    parse_single_time,
    parse_natural_time_range,
)
from history_manager import HistoryManager
from main import MainWindow


# Shared QApplication instance for all UI tests
_app = QApplication.instance() or QApplication([])


class TestFormattingAndTimeParser(unittest.TestCase):
    """Tests for formatting utilities, timestamp parsing, and natural-language Spanish range parsing."""

    def test_format_bytes(self):
        self.assertEqual(format_bytes(0), "—")
        self.assertEqual(format_bytes(None), "—")
        self.assertEqual(format_bytes(512), "512.0 B")
        self.assertEqual(format_bytes(1024 * 5), "5.0 KB")
        self.assertEqual(format_bytes(1024 * 1024 * 12.5), "12.5 MB")

    def test_format_duration(self):
        self.assertEqual(format_duration(None), "—")
        self.assertEqual(format_duration(-5), "—")
        self.assertEqual(format_duration(0), "00:00")
        self.assertEqual(format_duration(65), "01:05")
        self.assertEqual(format_duration(300), "05:00")
        self.assertEqual(format_duration(3661), "1:01:01")

    def test_format_views(self):
        self.assertEqual(format_views(None), "")
        self.assertEqual(format_views(850), "850 visualizaciones")
        self.assertEqual(format_views(15_400), "15.4 K visualizaciones")
        self.assertEqual(format_views(2_300_000), "2.3 M visualizaciones")

    def test_parse_single_time(self):
        self.assertEqual(parse_single_time("principio"), 0.0)
        self.assertEqual(parse_single_time("el inicio"), 0.0)
        self.assertIsNone(parse_single_time("final"))
        self.assertEqual(parse_single_time("05:00"), 300.0)
        self.assertEqual(parse_single_time("01:30"), 90.0)
        self.assertEqual(parse_single_time("1:02:03"), 3723.0)
        self.assertEqual(parse_single_time("5 min"), 300.0)
        self.assertEqual(parse_single_time("45 seg"), 45.0)
        self.assertEqual(parse_single_time("1h 10m"), 4200.0)
        self.assertEqual(parse_single_time("5", default_unit="m"), 300.0)
        self.assertEqual(parse_single_time("30", default_unit="s"), 30.0)

    def test_parse_natural_time_range_valid_phrases(self):
        cases = [
            ("del principio hasta el minuto 5", (0.0, 300.0, True)),
            ("desde el inicio hasta el minuto 3:30", (0.0, 210.0, True)),
            ("primeros 5 minutos", (0.0, 300.0, True)),
            ("primeros 45 segundos", (0.0, 45.0, True)),
            ("primera media hora", (0.0, 1800.0, True)),
            ("del minuto 2 al 5", (120.0, 300.0, True)),
            ("del minuto 1:30 al 4:45", (90.0, 285.0, True)),
            ("de 01:20 a 03:45", (80.0, 225.0, True)),
            ("00:30 - 02:00", (30.0, 120.0, True)),
            ("hasta el minuto 4", (0.0, 240.0, True)),
            ("desde el minuto 10 hasta el final", (600.0, None, True)),
            ("a partir del minuto 2", (120.0, None, True)),
        ]
        for phrase, expected in cases:
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_natural_time_range(phrase), expected)

    def test_parse_natural_time_range_invalid(self):
        # End <= Start must be flagged invalid
        _s, _e, valid = parse_natural_time_range("del minuto 5 al minuto 2")
        self.assertFalse(valid)

        # Empty or unrelated text
        self.assertEqual(parse_natural_time_range(""), (None, None, False))
        self.assertEqual(parse_natural_time_range("texto sin numeros"), (None, None, False))


class TestHistoryManager(unittest.TestCase):
    """Tests for persistent JSON download history management."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.storage_file = self.base_path / "test_history.json"
        self.manager = HistoryManager(storage_path=self.storage_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_load_remove_clear_history(self):
        self.assertEqual(self.manager.load_history(), [])

        dummy_media = self.base_path / "sample.mp4"
        dummy_media.write_bytes(b"0" * 2048)

        entry1 = self.manager.add_entry(
            title="Video 1",
            url="https://youtube.com/watch?v=111",
            mode="video",
            quality_label="🎬 Video 1080p (MP4)",
            file_path=str(dummy_media),
            channel="Canal Uno",
        )
        self.assertEqual(entry1["file_size"], "2.0 KB")

        entry2 = self.manager.add_entry(
            title="Canción 2",
            url="https://youtube.com/watch?v=222",
            mode="audio",
            quality_label="🎵 Audio MP3 (320 kbps)",
            file_path=str(dummy_media),
            channel="Canal Dos",
        )

        loaded = self.manager.load_history()
        self.assertEqual(len(loaded), 2)
        # Most recent entry first
        self.assertEqual(loaded[0]["id"], entry2["id"])
        self.assertEqual(loaded[1]["id"], entry1["id"])

        # Remove first entry
        self.manager.remove_entry(entry2["id"])
        loaded_after = self.manager.load_history()
        self.assertEqual(len(loaded_after), 1)
        self.assertEqual(loaded_after[0]["id"], entry1["id"])

        # Clear all
        self.manager.clear_history()
        self.assertEqual(self.manager.load_history(), [])


class TestDownloadWorkerAndFFmpegWrapper(unittest.TestCase):
    """Tests for DownloadWorker monotonic progress, cancellation, and Popen context-manager safety."""

    def test_monotonic_progress_never_decreases(self):
        worker = DownloadWorker(
            url="https://youtube.com/watch?v=abc",
            output_dir=".",
            mode="video",
            video_height=1080,
            video_ext="mp4",
            audio_codec="mp3",
            audio_bitrate="320",
            quality_summary="test",
        )
        emitted = []
        worker.progress_updated.connect(lambda pct, stats, stage: emitted.append(pct))

        # Stream 1 (video): 50% of stream -> 42.5% overall
        worker._progress_hook({"status": "downloading", "downloaded_bytes": 500, "total_bytes": 1000})
        # Simulate yt-dlp recalculating a larger total_bytes_estimate (40% of stream -> 34% overall)
        worker._progress_hook({"status": "downloading", "downloaded_bytes": 520, "total_bytes": 1300})
        # Stream 1 finishes -> 85%
        worker._progress_hook({"status": "finished", "filename": "temp.f137.mp4"})
        # Stream 2 (audio) starts at 10% -> 85 + 1.1 = 86.1%
        worker._progress_hook({"status": "downloading", "downloaded_bytes": 100, "total_bytes": 1000})

        self.assertEqual(len(emitted), 4)
        # Verify strict non-decreasing sequence
        for i in range(1, len(emitted)):
            self.assertGreaterEqual(
                emitted[i],
                emitted[i - 1],
                f"Progress decreased at step {i}: {emitted}",
            )

    def test_cancellation_raises_download_cancelled_error(self):
        worker = DownloadWorker(
            url="https://youtube.com/watch?v=abc",
            output_dir=".",
            mode="audio",
            video_height=None,
            video_ext="mp4",
            audio_codec="mp3",
            audio_bitrate="320",
            quality_summary="test",
        )
        worker.cancel()
        with self.assertRaises(DownloadCancelledError):
            worker._progress_hook({"status": "downloading", "downloaded_bytes": 100, "total_bytes": 1000})

    def test_ffmpeg_range_popen_context_manager_does_not_raise_closed_file(self):
        """Regression test for 'readline of closed file' when Popen.__exit__ closes stderr and calls wait()."""
        ensure_ffmpeg()
        ffmpeg_bin = shutil.which("ffmpeg")
        self.assertIsNotNone(ffmpeg_bin, "FFmpeg binary should be available")

        worker = DownloadWorker(
            url="https://youtube.com/watch?v=abc",
            output_dir=".",
            mode="video",
            video_height=720,
            video_ext="mp4",
            audio_codec="mp3",
            audio_bitrate="320",
            quality_summary="test",
            start_time=0.0,
            end_time=60.0,
        )
        emitted = []
        worker.progress_updated.connect(lambda pct, stats, stage: emitted.append(pct))

        # Mock the underlying FFmpegFD._call_downloader to run a Popen context manager with '-progress'
        def fake_orig_call_downloader(fd_self, tmpfilename, info_dict):
            cmd = [
                sys.executable,
                "-c",
                "import sys; sys.stderr.write('total_size=102400\\nspeed=2.5x\\nout_time_us=30000000\\n'); sys.stderr.flush()",
                "-progress",
                "pipe:2",
            ]
            with Popen(cmd, stdin=subprocess.PIPE) as proc:
                return proc.wait()

        with patch.object(FFmpegFD, "_call_downloader", fake_orig_call_downloader):
            orig_call = worker._install_ffmpeg_progress_wrapper()
            try:
                dummy_fd = MagicMock()
                dummy_fd.params = {"quiet": True}
                retval = FFmpegFD._call_downloader(
                    dummy_fd,
                    "out.mp4",
                    {"section_start": 0.0, "section_end": 60.0, "duration": 120.0},
                )
                self.assertEqual(retval, 0)
                self.assertTrue(len(emitted) >= 1)
                self.assertAlmostEqual(emitted[-1], 47.5, places=1)
            finally:
                FFmpegFD._call_downloader = orig_call


class TestMainWindowUI(unittest.TestCase):
    """Tests for PyQt6 MainWindow interactions, state transitions, and clip controls."""

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def test_initial_ui_state(self):
        self.assertEqual(self.window.btn_download.text(), "⬇  Descargar Ahora")
        self.assertEqual(self.window.btn_download.objectName(), "PrimaryButton")
        self.assertTrue(self.window.btn_mode_video.isChecked())
        self.assertFalse(self.window.chk_clip.isChecked())
        self.assertGreaterEqual(self.window.combo_video_quality.count(), 5)
        self.assertEqual(self.window.combo_audio_codec.count(), 5)

    def test_audio_codec_lossless_disables_bitrate_combo(self):
        # Select WAV (index 2)
        self.window.combo_audio_codec.setCurrentIndex(2)
        self.assertFalse(self.window.combo_audio_bitrate.isEnabled())

        # Select MP3 (index 0)
        self.window.combo_audio_codec.setCurrentIndex(0)
        self.assertTrue(self.window.combo_audio_bitrate.isEnabled())

    def test_download_button_open_folder_transition_and_reset(self):
        self.window._set_open_folder_button_mode("C:/fake/video.mp4")
        self.assertTrue(self.window.download_completed_mode)
        self.assertEqual(self.window.btn_download.text(), "📂  Abrir Carpeta")
        self.assertEqual(self.window.btn_download.objectName(), "SuccessButton")

        # Clicking when in completed mode should call open_output_directory
        with patch.object(self.window, "open_output_directory") as mock_open_dir:
            self.window._on_primary_action_clicked()
            mock_open_dir.assert_called_once()

        # Changing URL resets button back to "Descargar Ahora"
        self.window.url_input.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertFalse(self.window.download_completed_mode)
        self.assertEqual(self.window.btn_download.text(), "⬇  Descargar Ahora")
        self.assertEqual(self.window.btn_download.objectName(), "PrimaryButton")

    def test_progress_bar_monotonic_and_color_gradient(self):
        self.window._update_progress_bar(0.0, reset=True)
        self.assertEqual(self.window.progress_bar.value(), 0)
        style_0 = self.window.progress_bar.styleSheet()

        self.window._update_progress_bar(60.0)
        self.assertEqual(self.window.progress_bar.value(), 60)

        # Attempting to set lower percentage without reset=True must not decrease value
        self.window._update_progress_bar(45.0)
        self.assertEqual(self.window.progress_bar.value(), 60)

        self.window._update_progress_bar(100.0)
        self.assertEqual(self.window.progress_bar.value(), 100)
        style_100 = self.window.progress_bar.styleSheet()

        # Verify color changed between 0% (Red) and 100% (Green)
        self.assertNotEqual(style_0, style_100)

    def test_clip_natural_language_syncs_fields_and_badge(self):
        self.window.txt_clip_natural.setText("del principio hasta el minuto 5")
        self.window._on_clip_natural_edited("del principio hasta el minuto 5")

        self.assertTrue(self.window.chk_clip.isChecked())
        self.assertEqual(self.window.txt_clip_start.text(), "00:00")
        self.assertEqual(self.window.txt_clip_end.text(), "05:00")
        self.assertIn("00:00 → 05:00", self.window.lbl_clip_badge.text())

        start_s, end_s, valid, _lbl = self.window._resolve_clip_range()
        self.assertTrue(valid)
        self.assertEqual(start_s, 0.0)
        self.assertEqual(end_s, 300.0)

    def test_clip_manual_fields_validation(self):
        self.window.txt_clip_start.setText("05:00")
        self.window.txt_clip_end.setText("02:00")
        self.window._on_clip_manual_edited()

        _s, _e, valid, msg = self.window._resolve_clip_range()
        self.assertFalse(valid)
        self.assertIn("mayor al inicial", msg)
        self.assertEqual(self.window.lbl_clip_badge.objectName(), "BadgeClipWarn")


if __name__ == "__main__":
    unittest.main(verbosity=2)
