"""Тема інтерфейсу: кольори, палітра Qt, глобальний stylesheet, моноширинні шрифти, теми полотна."""
from __future__ import annotations

import os

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from .paths import resource_path

THEME = {
    "bg":           "#09090b",
    "bg_panel":     "#121214",
    "bg_widget":    "#18181b",
    "bg_input":     "#1e1e21",
    "accent":       "#f59e0b",
    "accent_light": "#fbbf24",
    "accent_dim":   "#b45309",
    "text":         "#fafafa",
    "text_dim":     "#a1a1aa",
    "border":       "#27272a",
    "hover":        "#2a2a2e",
    "selected":     "#3f3f46",
    "error":        "#ef4444",
    "success":      "#10b981",
    "warning":      "#f59e0b",
}

TERMINAL_THEMES = {
    "Matrix":         {"bg": "#09090b", "fg": "#10b981"},
    "Classic":        {"bg": "#0c0c0c", "fg": "#ffffff"},
    "Amber (Retro)":  {"bg": "#0c0c0c", "fg": "#f59e0b"},
    "Cyan":           {"bg": "#0c0c0c", "fg": "#7dd3fc"},
    "Paper":          {"bg": "#fafafa", "fg": "#0a0a0a"},
    "Crimson":        {"bg": "#0c0c0c", "fg": "#ef4444"},
    "Monokai":        {"bg": "#272822", "fg": "#f8f8f2"},
    "Dracula":        {"bg": "#282a36", "fg": "#f8f8f2"},
    "Solarized Dark": {"bg": "#002b36", "fg": "#839496"},
    "Midnight":       {"bg": "#1b2838", "fg": "#10b981"},
}
CUSTOM_THEME = "Custom"
DEFAULT_THEME = "Matrix"

MONO_FAMILIES = ["JetBrains Mono", "DejaVu Sans Mono", "Noto Color Emoji", "Twemoji Mozilla", "DejaVu Sans"]

_fonts_loaded: list[str] | None = None


def load_app_fonts() -> list[str]:
    """Реєструє .ttf із fonts/ пакета (один раз); повертає імена родин."""
    global _fonts_loaded
    if _fonts_loaded is not None:
        return _fonts_loaded
    fams: list[str] = []
    folder = resource_path("fonts")
    if os.path.isdir(folder):
        for fn in sorted(os.listdir(folder)):
            if not fn.lower().endswith(".ttf"):
                continue
            font_id = QFontDatabase.addApplicationFont(os.path.join(folder, fn))
            for fam in QFontDatabase.applicationFontFamilies(font_id) if font_id != -1 else ():
                if fam not in fams:
                    fams.append(fam)
    _fonts_loaded = fams
    return fams


def mono_font(point_size: float = 12) -> QFont:
    f = QFont(MONO_FAMILIES)
    f.setPointSizeF(point_size)
    f.setStyleHint(QFont.Monospace)
    return f


def mix(bg: str, fg: str, k: float) -> QColor:
    a, b = QColor(bg), QColor(fg)
    if not (a.isValid() and b.isValid()):
        return QColor()
    return QColor(
        int(a.red() + (b.red() - a.red()) * k),
        int(a.green() + (b.green() - a.green()) * k),
        int(a.blue() + (b.blue() - a.blue()) * k),
    )


def contrast_text(hex_color: str) -> str:
    c = QColor("#" + hex_color.lstrip("#"))
    lum = (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255
    return "#000000" if lum > 0.5 else "#ffffff"


def canvas_style(bg: str, fg: str) -> str:
    return (f"QPlainTextEdit, QTextEdit {{ background-color: {bg}; color: {fg}; border: none; "
            f"padding: 6px; selection-background-color: {THEME['accent_dim']}; selection-color: {THEME['text']}; }}")


def _palette() -> QPalette:
    t = THEME
    p = QPalette()
    for role, key in (
        (QPalette.Window, "bg"), (QPalette.WindowText, "text"), (QPalette.Base, "bg_input"),
        (QPalette.AlternateBase, "bg_widget"), (QPalette.ToolTipBase, "bg_widget"),
        (QPalette.ToolTipText, "text"), (QPalette.Text, "text"), (QPalette.Button, "bg_widget"),
        (QPalette.ButtonText, "text"), (QPalette.BrightText, "accent_light"), (QPalette.Link, "accent"),
        (QPalette.Highlight, "accent_dim"), (QPalette.HighlightedText, "text"),
        (QPalette.PlaceholderText, "text_dim"),
    ):
        p.setColor(role, QColor(t[key]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText, QPalette.HighlightedText):
        p.setColor(QPalette.Disabled, role, QColor(t["text_dim"]))
    return p


def _stylesheet() -> str:
    t = THEME
    return f"""
QMainWindow, QDialog, QWidget#studio_root {{ background-color: {t['bg']}; color: {t['text']}; }}
QToolTip {{ background: {t['bg_widget']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 4px; }}
QMenuBar {{ background: {t['bg_panel']}; border-bottom: 1px solid {t['border']}; }}
QMenuBar::item {{ padding: 4px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {t['hover']}; color: {t['accent_light']}; }}
QMenu {{ background: {t['bg_panel']}; border: 1px solid {t['border']}; padding: 4px; }}
QMenu::item {{ padding: 4px 24px 4px 20px; border-radius: 3px; }}
QMenu::item:selected {{ background: {t['selected']}; color: {t['accent_light']}; }}
QMenu::item:disabled {{ color: {t['text_dim']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 6px; }}
QToolBar {{ background: {t['bg_panel']}; border: none; border-bottom: 1px solid {t['border']}; spacing: 3px; padding: 3px; }}
QToolBar::separator {{ background: {t['border']}; width: 1px; margin: 3px 4px; }}
QStatusBar {{ background: {t['bg_panel']}; border-top: 1px solid {t['border']}; color: {t['text_dim']}; }}
QStatusBar QLabel {{ color: {t['text_dim']}; padding: 0 6px; }}
QSplitter::handle {{ background-color: {t['border']}; }}
QFrame#panel {{ background-color: {t['bg_panel']}; border: 1px solid {t['border']}; border-radius: 6px; }}
QLabel#hint {{ color: {t['text_dim']}; font-size: 10px; }}
QLabel#section {{ color: {t['text_dim']}; font-size: 10px; font-weight: bold; }}
QLabel#warn {{ color: {t['warning']}; }}
QListWidget, QTreeWidget, QTableWidget {{ background-color: {t['bg_panel']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 2px; outline: none; }}
QListWidget::item, QTreeWidget::item {{ padding: 3px 6px; border-radius: 4px; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background-color: {t['hover']}; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background-color: {t['selected']}; color: {t['accent_light']}; }}
QHeaderView::section {{ background: {t['bg_widget']}; color: {t['text_dim']}; border: none; border-right: 1px solid {t['border']}; padding: 4px; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {{ background-color: {t['bg_input']}; border: 1px solid {t['border']}; border-radius: 4px; padding: 3px 6px; color: {t['text']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {t['accent']}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{ background-color: {t['bg_panel']}; border: 1px solid {t['border']}; selection-background-color: {t['selected']}; }}
QTextEdit, QPlainTextEdit {{ background-color: {t['bg_input']}; border: 1px solid {t['border']}; border-radius: 4px; color: {t['text']}; selection-background-color: {t['accent_dim']}; }}
QPushButton {{ background-color: {t['bg_widget']}; border: 1px solid {t['border']}; border-radius: 4px; padding: 5px 12px; color: {t['text']}; }}
QPushButton:hover {{ border-color: {t['accent']}; background-color: {t['hover']}; }}
QPushButton:pressed, QPushButton:checked {{ background-color: {t['selected']}; border-color: {t['accent']}; }}
QPushButton:default, QPushButton#primary {{ background-color: {t['accent_dim']}; border-color: {t['accent']}; font-weight: bold; }}
QPushButton:default:hover, QPushButton#primary:hover {{ background-color: {t['accent']}; color: #000; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t['text_dim']}; border-color: {t['border']}; }}
QToolButton {{ background-color: {t['bg_widget']}; border: 1px solid {t['border']}; border-radius: 4px; padding: 3px 7px; color: {t['text']}; }}
QToolButton:hover {{ background-color: {t['hover']}; border-color: {t['accent']}; }}
QToolButton:checked {{ background-color: {t['selected']}; border-color: {t['accent']}; color: {t['accent_light']}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton#glyph {{ background-color: {t['bg_input']}; font-size: 13px; padding: 0; }}
QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border-radius: 3px; border: 1px solid {t['border']}; background-color: {t['bg_input']}; }}
QCheckBox::indicator:checked {{ background-color: {t['accent']}; border-color: {t['accent_light']}; }}
QGroupBox {{ border: 1px solid {t['border']}; border-radius: 6px; margin-top: 8px; padding: 10px 6px 6px 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 3px; color: {t['accent_light']}; font-size: 10px; font-weight: bold; }}
QTabWidget::pane {{ border: 1px solid {t['border']}; border-radius: 4px; top: -1px; background: {t['bg_widget']}; }}
QTabWidget[active="true"]::pane {{ border: 1px solid {t['accent']}; }}
QTabBar::tab {{ background: {t['bg_panel']}; border: 1px solid {t['border']}; padding: 5px 12px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; color: {t['text_dim']}; }}
QTabBar::tab:selected {{ background: {t['bg_widget']}; border-bottom-color: {t['bg_widget']}; color: {t['accent_light']}; font-weight: bold; }}
QTabBar::tab:hover {{ background: {t['hover']}; }}
QSlider::groove:horizontal {{ height: 4px; background: {t['border']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {t['accent']}; width: 12px; margin: -5px 0; border-radius: 6px; }}
QScrollBar:vertical {{ background: {t['bg']}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {t['selected']}; min-height: 20px; border-radius: 6px; margin: 2px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {t['bg']}; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {t['selected']}; min-width: 20px; border-radius: 6px; margin: 2px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
"""


STYLESHEET = _stylesheet()


def apply(app: QApplication | None = None) -> None:
    """Fusion + темна палітра + stylesheet + шрифти пакета (ідемпотентно)."""
    app = app or QApplication.instance()
    if app is None:
        return
    load_app_fonts()
    if app.property("ascii_studio_theme"):
        return
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setStyleSheet(STYLESHEET)
    base = app.font()
    base.setPointSizeF(max(9.0, min(base.pointSizeF(), 10.5)) if base.pointSizeF() > 0 else 10.0)
    app.setFont(base)
    app.setProperty("ascii_studio_theme", True)
