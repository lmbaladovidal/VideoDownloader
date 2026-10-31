APP_STYLESHEET = """
QMainWindow, QWidget#CentralWidget {
    background-color: #0f1117;
    color: #e6edf3;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}

QFrame#Card {
    background-color: #161922;
    border: 1px solid #262b38;
    border-radius: 12px;
}

QFrame#PreviewCard {
    background-color: #161922;
    border: 1px solid #2a3040;
    border-radius: 12px;
}

QLabel#AppTitle {
    font-size: 20px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#AppSubtitle {
    font-size: 12px;
    color: #8b949e;
}

QLabel#BadgeOk {
    background-color: #122d1f;
    color: #3fb950;
    border: 1px solid #238636;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}

QLabel#BadgeClipActive {
    background-color: #1e293b;
    color: #38bdf8;
    border: 1px solid #0284c7;
    border-radius: 8px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}

QLabel#BadgeClipWarn {
    background-color: #3b1820;
    color: #fda4af;
    border: 1px solid #be123c;
    border-radius: 8px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}

QCheckBox {
    color: #e6edf3;
    font-weight: 600;
    font-size: 13px;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid #30363d;
    background-color: #0d0f14;
}

QCheckBox::indicator:checked {
    background-color: #e11d48;
    border: 1px solid #f43f5e;
}

QLabel#SectionTitle {
    font-size: 13px;
    font-weight: 600;
    color: #c9d1d9;
}

QLabel#VideoTitle {
    font-size: 15px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#VideoMeta {
    font-size: 12px;
    color: #9ca3af;
}

QLabel#VideoBadge {
    background-color: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}

QLabel#ThumbnailBox {
    background-color: #0d0f14;
    border: 1px solid #262b38;
    border-radius: 8px;
    color: #6e7681;
    font-size: 12px;
}

QLineEdit {
    background-color: #0d0f14;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 9px 12px;
    color: #f0f6fc;
    font-size: 13px;
    selection-background-color: #e11d48;
}

QLineEdit:focus {
    border: 1px solid #f43f5e;
    background-color: #11141c;
}

QComboBox {
    background-color: #0d0f14;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 7px 12px;
    color: #f0f6fc;
    font-size: 13px;
    min-height: 20px;
}

QComboBox:hover {
    border: 1px solid #484f58;
}

QComboBox:focus {
    border: 1px solid #f43f5e;
}

QComboBox::drop-down {
    border: none;
    width: 26px;
}

QComboBox QAbstractItemView {
    background-color: #161922;
    border: 1px solid #30363d;
    selection-background-color: #e11d48;
    selection-color: #ffffff;
    color: #e6edf3;
    padding: 4px;
    outline: 0;
}

QPushButton {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 8px 14px;
    color: #e6edf3;
    font-weight: 600;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #292e36;
    border-color: #484f58;
}

QPushButton:pressed {
    background-color: #1b1f26;
}

QPushButton:disabled {
    background-color: #161922;
    border-color: #21262d;
    color: #484f58;
}

QPushButton#PrimaryButton {
    background-color: #e11d48;
    border: 1px solid #f43f5e;
    color: #ffffff;
    font-size: 14px;
    font-weight: 700;
    padding: 10px 20px;
}

QPushButton#PrimaryButton:hover {
    background-color: #f43f5e;
    border-color: #fb7185;
}

QPushButton#PrimaryButton:pressed {
    background-color: #be123c;
}

QPushButton#PrimaryButton:disabled {
    background-color: #2b1820;
    border-color: #3d1f2b;
    color: #6e505a;
}

QPushButton#SuccessButton {
    background-color: #16a34a;
    border: 1px solid #22c55e;
    color: #ffffff;
    font-size: 14px;
    font-weight: 700;
    padding: 10px 20px;
}

QPushButton#SuccessButton:hover {
    background-color: #22c55e;
    border-color: #4ade80;
}

QPushButton#SuccessButton:pressed {
    background-color: #15803d;
}

QPushButton#AnalyzeButton {
    background-color: #2563eb;
    border: 1px solid #3b82f6;
    color: #ffffff;
    font-weight: 700;
    padding: 9px 18px;
}

QPushButton#AnalyzeButton:hover {
    background-color: #3b82f6;
}

QPushButton#AnalyzeButton:disabled {
    background-color: #172544;
    border-color: #1e335c;
    color: #5b6e94;
}

QPushButton#DangerButton {
    background-color: #3b1820;
    border: 1px solid #7f1d32;
    color: #fda4af;
}

QPushButton#DangerButton:hover {
    background-color: #551b29;
    border-color: #be123c;
}

QPushButton#ModeTab {
    background-color: #0d0f14;
    border: 1px solid #262b38;
    border-radius: 8px;
    padding: 9px 16px;
    color: #8b949e;
    font-weight: 600;
}

QPushButton#ModeTab:checked {
    background-color: #1f2433;
    border: 1px solid #f43f5e;
    color: #ffffff;
}

QPushButton#SmallActionBtn {
    background-color: #1f2430;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton#SmallActionBtn:hover {
    background-color: #2c3344;
    border-color: #58a6ff;
}

QProgressBar {
    background-color: #0d0f14;
    border: 1px solid #262b38;
    border-radius: 8px;
    min-height: 20px;
    max-height: 20px;
    text-align: center;
    color: #ffffff;
    font-weight: 700;
    font-size: 11px;
}

QProgressBar::chunk {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 0,
        stop: 0 #e11d48,
        stop: 1 #f97316
    );
    border-radius: 7px;
}

QTableWidget {
    background-color: #0d0f14;
    border: 1px solid #262b38;
    border-radius: 8px;
    gridline-color: #1c202b;
    color: #e6edf3;
    selection-background-color: #1f2433;
    selection-color: #ffffff;
    outline: 0;
}

QHeaderView::section {
    background-color: #161922;
    color: #8b949e;
    font-weight: 600;
    font-size: 12px;
    border: none;
    border-bottom: 1px solid #262b38;
    padding: 6px 10px;
}

QScrollBar:vertical {
    background: #0d0f14;
    width: 10px;
    margin: 0px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #2b3140;
    min-height: 24px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #3d4558;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

