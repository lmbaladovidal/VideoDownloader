import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


class HistoryManager:
    """Manages persistent download history stored in a local JSON file."""

    def __init__(self, storage_path: Path | None = None):
        if storage_path is None:
            if getattr(sys, "frozen", False):
                appdata = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
                app_dir = appdata / "YouTubeMediaDownloader"
                app_dir.mkdir(parents=True, exist_ok=True)
                self.storage_path = app_dir / "download_history.json"
            else:
                self.storage_path = Path(__file__).resolve().parent / "download_history.json"
        else:
            self.storage_path = storage_path

    def load_history(self) -> List[Dict[str, Any]]:
        if not self.storage_path.exists():
            return []
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def add_entry(
        self,
        title: str,
        url: str,
        mode: str,
        quality_label: str,
        file_path: str,
        channel: str = "",
    ) -> Dict[str, Any]:
        history = self.load_history()
        file_size_str = ""
        try:
            if file_path and os.path.exists(file_path):
                size_bytes = os.path.getsize(file_path)
                file_size_str = self._format_bytes(size_bytes)
        except Exception:
            pass

        entry = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "title": title,
            "channel": channel,
            "url": url,
            "mode": mode,  # "video" or "audio"
            "quality_label": quality_label,
            "file_path": str(file_path),
            "file_size": file_size_str,
            "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }
        history.insert(0, entry)
        # Keep up to 100 entries
        history = history[:100]
        self._save_history(history)
        return entry

    def remove_entry(self, entry_id: str) -> None:
        history = [item for item in self.load_history() if item.get("id") != entry_id]
        self._save_history(history)

    def clear_history(self) -> None:
        self._save_history([])

    def _save_history(self, history: List[Dict[str, Any]]) -> None:
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        if num_bytes <= 0:
            return ""
        for unit in ["B", "KB", "MB", "GB"]:
            if num_bytes < 1024.0:
                return f"{num_bytes:.1f} {unit}"
            num_bytes /= 1024.0
        return f"{num_bytes:.1f} TB"

