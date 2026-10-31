import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw


PROJECT_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"
INSTALLER_OUT_DIR = PROJECT_DIR / "Instalador"


def generate_icon(icon_path: Path) -> None:
    """Generates a sleek multi-resolution Windows .ico file (play + download arrow)."""
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark rounded background card
    draw.rounded_rectangle(
        [(12, 12), (size - 12, size - 12)],
        radius=56,
        fill=(18, 21, 30, 255),
        outline=(225, 29, 72, 255),
        width=8,
    )

    # Inner crimson circle
    draw.ellipse(
        [(48, 48), (size - 48, size - 48)],
        fill=(225, 29, 72, 255),
    )

    # White download arrow inside the crimson circle
    # Shaft
    draw.rounded_rectangle(
        [(112, 78), (144, 146)],
        radius=6,
        fill=(255, 255, 255, 255),
    )
    # Arrowhead triangle pointing down
    draw.polygon(
        [(82, 134), (174, 134), (128, 182)],
        fill=(255, 255, 255, 255),
    )
    # Bottom tray bar
    draw.rounded_rectangle(
        [(86, 190), (170, 204)],
        radius=6,
        fill=(255, 255, 255, 255),
    )

    img.save(
        icon_path,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    print(f"[1/4] Icono generado: {icon_path}")


def create_installer_script(script_path: Path) -> None:
    """Writes the standalone GUI installer script that will be compiled into Instalar_YouTubeDownloader.exe."""
    code = '''import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def get_resource_path(rel_name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / rel_name


def create_shortcut(target_exe: str, shortcut_path: str, icon_path: str, description: str) -> None:
    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
$Shortcut.TargetPath = '{target_exe}'
$Shortcut.WorkingDirectory = '{Path(target_exe).parent}'
$Shortcut.IconLocation = '{icon_path}'
$Shortcut.Description = '{description}'
$Shortcut.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        creationflags=0x08000000,
        check=False,
    )


class InstallerWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Instalador — YouTube Video & Audio Downloader")
        self.root.geometry("560x390")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f1117")

        icon_file = get_resource_path("app_icon.ico")
        if icon_file.exists():
            try:
                self.root.iconbitmap(str(icon_file))
            except Exception:
                pass

        default_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "YouTubeDownloader"
        self.install_dir_var = tk.StringVar(value=str(default_dir))
        self.desktop_shortcut_var = tk.BooleanVar(value=True)
        self.startmenu_shortcut_var = tk.BooleanVar(value=True)
        self.launch_after_var = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg="#161922", padx=20, pady=16)
        header.pack(fill="x")

        tk.Label(
            header,
            text="🎬 YouTube Video & Audio Downloader",
            font=("Segoe UI", 15, "bold"),
            fg="#ffffff",
            bg="#161922",
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Asistente de instalación en tu equipo (incluye FFmpeg integrado)",
            font=("Segoe UI", 9),
            fg="#8b949e",
            bg="#161922",
        ).pack(anchor="w", pady=(2, 0))

        body = tk.Frame(self.root, bg="#0f1117", padx=22, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            text="Carpeta de instalación:",
            font=("Segoe UI", 10, "bold"),
            fg="#c9d1d9",
            bg="#0f1117",
        ).pack(anchor="w")

        dir_row = tk.Frame(body, bg="#0f1117")
        dir_row.pack(fill="x", pady=(6, 14))

        entry = tk.Entry(
            dir_row,
            textvariable=self.install_dir_var,
            font=("Segoe UI", 9),
            bg="#161922",
            fg="#f0f6fc",
            insertbackground="#ffffff",
            relief="flat",
            bd=6,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse = tk.Button(
            dir_row,
            text="Examinar...",
            command=self._choose_dir,
            font=("Segoe UI", 9, "bold"),
            bg="#21262d",
            fg="#e6edf3",
            activebackground="#30363d",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
        )
        btn_browse.pack(side="right")

        chk_style = {
            "font": ("Segoe UI", 10),
            "bg": "#0f1117",
            "fg": "#e6edf3",
            "selectcolor": "#161922",
            "activebackground": "#0f1117",
            "activeforeground": "#ffffff",
        }
        tk.Checkbutton(
            body,
            text="Crear acceso directo en el Escritorio",
            variable=self.desktop_shortcut_var,
            **chk_style,
        ).pack(anchor="w", pady=2)

        tk.Checkbutton(
            body,
            text="Agregar al Menú Inicio de Windows",
            variable=self.startmenu_shortcut_var,
            **chk_style,
        ).pack(anchor="w", pady=2)

        tk.Checkbutton(
            body,
            text="Abrir YouTube Downloader al terminar la instalación",
            variable=self.launch_after_var,
            **chk_style,
        ).pack(anchor="w", pady=2)

        self.status_lbl = tk.Label(
            body,
            text="Listo para instalar.",
            font=("Segoe UI", 9),
            fg="#8b949e",
            bg="#0f1117",
        )
        self.status_lbl.pack(anchor="w", pady=(14, 4))

        self.progress = ttk.Progressbar(body, orient="horizontal", length=510, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 14))

        btn_row = tk.Frame(body, bg="#0f1117")
        btn_row.pack(fill="x")

        self.btn_install = tk.Button(
            btn_row,
            text="⬇  Instalar Ahora",
            command=self._run_install,
            font=("Segoe UI", 11, "bold"),
            bg="#e11d48",
            fg="#ffffff",
            activebackground="#f43f5e",
            activeforeground="#ffffff",
            relief="flat",
            padx=22,
            pady=7,
            cursor="hand2",
        )
        self.btn_install.pack(side="right")

        self.btn_close = tk.Button(
            btn_row,
            text="Cancelar",
            command=self.root.destroy,
            font=("Segoe UI", 10),
            bg="#21262d",
            fg="#c9d1d9",
            activebackground="#30363d",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=7,
            cursor="hand2",
        )
        self.btn_close.pack(side="right", padx=(0, 10))

    def _choose_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.install_dir_var.get())
        if chosen:
            self.install_dir_var.set(str(Path(chosen) / "YouTubeDownloader"))

    def _run_install(self) -> None:
        target_dir = Path(self.install_dir_var.get().strip())
        payload_zip = get_resource_path("app_payload.zip")
        if not payload_zip.exists():
            messagebox.showerror("Error", "No se encontró el paquete de instalación interno.")
            return

        self.btn_install.config(state="disabled")
        self.status_lbl.config(text="Extrayendo archivos de la aplicación...", fg="#58a6ff")
        self.root.update()

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(payload_zip, "r") as zf:
                members = zf.namelist()
                total = max(len(members), 1)
                for idx, member in enumerate(members, 1):
                    zf.extract(member, target_dir)
                    if idx % 15 == 0 or idx == total:
                        self.progress["value"] = int(idx / total * 85)
                        self.root.update()

            exe_path = target_dir / "YouTubeDownloader.exe"
            icon_path = target_dir / "app_icon.ico"
            if not icon_path.exists():
                shutil.copy2(get_resource_path("app_icon.ico"), icon_path)

            self.status_lbl.config(text="Creando accesos directos...", fg="#58a6ff")
            self.root.update()

            if self.desktop_shortcut_var.get():
                desktop_dir = Path(os.path.expanduser("~")) / "Desktop"
                if desktop_dir.exists():
                    create_shortcut(
                        str(exe_path),
                        str(desktop_dir / "YouTube Video & Audio Downloader.lnk"),
                        str(icon_path),
                        "Descargar videos y música de YouTube",
                    )

            if self.startmenu_shortcut_var.get():
                programs_dir = (
                    Path(os.environ.get("APPDATA", ""))
                    / "Microsoft"
                    / "Windows"
                    / "Start Menu"
                    / "Programs"
                )
                if programs_dir.exists():
                    create_shortcut(
                        str(exe_path),
                        str(programs_dir / "YouTube Video & Audio Downloader.lnk"),
                        str(icon_path),
                        "Descargar videos y música de YouTube",
                    )

            # Create uninstaller script
            uninstaller_bat = target_dir / "Desinstalar.bat"
            uninstaller_bat.write_text(
                f\'@echo off\\r\\n\'
                f\'echo Desinstalando YouTube Video ^& Audio Downloader...\\r\\n\'
                f\'del /f /q "%USERPROFILE%\\\\Desktop\\\\YouTube Video & Audio Downloader.lnk" 2>nul\\r\\n\'
                f\'del /f /q "%APPDATA%\\\\Microsoft\\\\Windows\\\\Start Menu\\\\Programs\\\\YouTube Video & Audio Downloader.lnk" 2>nul\\r\\n\'
                f\'cd /d "%~dp0.."\\r\\n\'
                f\'rmdir /s /q "{target_dir}"\\r\\n\',
                encoding="utf-8",
            )

            self.progress["value"] = 100
            self.status_lbl.config(
                text="✔ ¡Instalación completada con éxito!", fg="#3fb950"
            )
            self.root.update()

            if self.launch_after_var.get() and exe_path.exists():
                subprocess.Popen([str(exe_path)], cwd=str(target_dir))

            messagebox.showinfo(
                "Instalación completada",
                f"YouTube Video & Audio Downloader se instaló correctamente en:\\n{target_dir}",
            )
            self.root.destroy()

        except Exception as e:
            self.btn_install.config(state="normal")
            self.status_lbl.config(text="✖ Error durante la instalación.", fg="#f43f5e")
            messagebox.showerror("Error de instalación", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = InstallerWindow(root)
    root.mainloop()
'''
    script_path.write_text(code, encoding="utf-8")


def main() -> None:
    icon_path = PROJECT_DIR / "app_icon.ico"
    generate_icon(icon_path)

    # Locate static_ffmpeg binaries
    import static_ffmpeg
    static_ffmpeg.add_paths()
    ffmpeg_exe = shutil.which("ffmpeg")
    ffprobe_exe = shutil.which("ffprobe")
    if not ffmpeg_exe or not ffprobe_exe:
        raise RuntimeError("No se encontraron los binarios de ffmpeg/ffprobe.")

    print(f"[2/4] Empaquetando aplicación principal con PyInstaller (incluyendo FFmpeg)...")
    pyinstaller_exe = str(PROJECT_DIR / ".venv" / "Scripts" / "pyinstaller.exe")

    cmd_app = [
        pyinstaller_exe,
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name",
        "YouTubeDownloader",
        "--icon",
        str(icon_path),
        "--add-data",
        f"{icon_path};.",
        "--add-binary",
        f"{ffmpeg_exe};ffmpeg_bin",
        "--add-binary",
        f"{ffprobe_exe};ffmpeg_bin",
        str(PROJECT_DIR / "main.py"),
    ]
    subprocess.run(cmd_app, cwd=str(PROJECT_DIR), check=True)

    app_dist_dir = DIST_DIR / "YouTubeDownloader"
    shutil.copy2(icon_path, app_dist_dir / "app_icon.ico")

    # Compress the built app directory into app_payload.zip for the single-file installer
    payload_zip = BUILD_DIR / "app_payload.zip"
    print(f"[3/4] Creando paquete comprimido para el instalador...")
    with zipfile.ZipFile(payload_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file_path in app_dist_dir.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(app_dist_dir)
                zf.write(file_path, rel)

    # Create and compile GUI installer executable
    installer_script = BUILD_DIR / "installer_gui.py"
    create_installer_script(installer_script)

    INSTALLER_OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[4/4] Compilando instalador ejecutable (Instalar_YouTubeDownloader.exe)...")
    cmd_installer = [
        pyinstaller_exe,
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name",
        "Instalar_YouTubeDownloader",
        "--icon",
        str(icon_path),
        "--distpath",
        str(INSTALLER_OUT_DIR),
        "--add-data",
        f"{payload_zip};.",
        "--add-data",
        f"{icon_path};.",
        str(installer_script),
    ]
    subprocess.run(cmd_installer, cwd=str(PROJECT_DIR), check=True)
    print(f"¡Empaquetado finalizado! Instalador creado en: {INSTALLER_OUT_DIR / 'Instalar_YouTubeDownloader.exe'}")


if __name__ == "__main__":
    main()

