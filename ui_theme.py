"""PySide6 앱 테마 (QSS)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

COLORS = {
    "bg": "#f4f6f9",
    "surface": "#ffffff",
    "border": "#d8dee9",
    "text": "#1e293b",
    "muted": "#64748b",
    "primary": "#2563eb",
    "primary_hover": "#1d4ed8",
    "success": "#059669",
    "success_hover": "#047857",
    "danger": "#dc2626",
    "danger_hover": "#b91c1c",
    "accent": "#7c3aed",
    "header": "#1e3a5f",
    "row_done": "#dbeafe",
    "row_failed": "#fecaca",
    "row_alt": "#f8fafc",
}


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLORS["bg"]))
    palette.setColor(QPalette.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Base, QColor(COLORS["surface"]))
    palette.setColor(QPalette.AlternateBase, QColor(COLORS["row_alt"]))
    palette.setColor(QPalette.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.Button, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Highlight, QColor(COLORS["primary"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    app.setStyleSheet(_STYLESHEET)


_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {COLORS["bg"]};
    color: {COLORS["text"]};
    font-family: "Malgun Gothic", "Segoe UI", sans-serif;
    font-size: 13px;
}}

#AppHeader {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["header"]}, stop:1 #2d5a87);
    border-radius: 10px;
    padding: 14px 18px;
}}

#AppTitle {{
    color: #ffffff;
    font-size: 20px;
    font-weight: 700;
}}

#AppSubtitle, #VersionLabel {{
    color: #cbd5e1;
    font-size: 12px;
}}

QGroupBox {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
    margin-top: 14px;
    padding: 16px 12px 12px 12px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    color: {COLORS["primary"]};
}}

QTabWidget::pane {{
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    background: {COLORS["surface"]};
    top: -1px;
}}

QTabBar::tab {{
    background: #e2e8f0;
    color: {COLORS["muted"]};
    padding: 10px 22px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
}}

QTabBar::tab:selected {{
    background: {COLORS["surface"]};
    color: {COLORS["primary"]};
    border: 1px solid {COLORS["border"]};
    border-bottom: none;
}}

QLineEdit, QPlainTextEdit, QTextEdit {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {COLORS["primary"]};
}}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {COLORS["primary"]};
}}

QTableWidget {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    gridline-color: #eef2f7;
    selection-background-color: #bfdbfe;
    selection-color: {COLORS["text"]};
}}

QHeaderView::section {{
    background: #eef2ff;
    color: {COLORS["text"]};
    padding: 8px 6px;
    border: none;
    border-bottom: 2px solid {COLORS["border"]};
    font-weight: 600;
}}

QPushButton {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 8px 14px;
    min-height: 18px;
}}

QPushButton:hover {{
    background: #f1f5f9;
    border-color: #94a3b8;
}}

QPushButton#PrimaryButton {{
    background: {COLORS["success"]};
    color: white;
    border: none;
    font-weight: 700;
    padding: 10px 28px;
    font-size: 14px;
}}

QPushButton#PrimaryButton:hover {{
    background: {COLORS["success_hover"]};
}}

QPushButton#DangerButton {{
    color: {COLORS["danger"]};
    border-color: #fecaca;
}}

QPushButton#DangerButton:hover {{
    background: #fef2f2;
}}

QPushButton#AccentButton {{
    background: {COLORS["accent"]};
    color: white;
    border: none;
    font-weight: 600;
}}

QPushButton#AccentButton:hover {{
    background: #6d28d9;
}}

QProgressBar {{
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    background: #e2e8f0;
    text-align: center;
    height: 22px;
}}

QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["primary"]}, stop:1 #60a5fa);
    border-radius: 5px;
}}

QCheckBox {{
    spacing: 8px;
}}

#StatusBar {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 6px 12px;
    color: {COLORS["muted"]};
    font-size: 12px;
}}

#GuideLabel {{
    color: {COLORS["muted"]};
    font-size: 12px;
    padding: 4px 2px;
}}
"""
