"""Дрібні спільні віджети: текстові прев'ю з Ctrl+колесом, панелі, рядки «підпис — поле»."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QTextEdit, QToolButton, QVBoxLayout, QWidget

from ..core import mirror
from ..theme import canvas_style, mono_font


class _ZoomMixin:
    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y() or event.pixelDelta().y()
            if delta > 0:
                self.zoomIn(1)
            elif delta < 0:
                self.zoomOut(1)
            event.accept()
            return
        super().wheelEvent(event)


class ArtView(_ZoomMixin, QPlainTextEdit):
    """Read-only моноширинне прев'ю арту (без переносу, Ctrl+колесо — масштаб)."""

    def __init__(self, point_size: float = 11, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont(mono_font(point_size))

    def set_colors(self, bg: str, fg: str) -> None:
        self.setStyleSheet(canvas_style(bg, fg))


class RichArtView(_ZoomMixin, QTextEdit):
    """Read-only прев'ю з форматуванням (кольори, привид кадру)."""

    def __init__(self, point_size: float = 11, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setFont(mono_font(point_size))

    def set_colors(self, bg: str, fg: str) -> None:
        self.setStyleSheet(canvas_style(bg, fg))


def panel(layout_cls=QVBoxLayout, margins=(6, 4, 6, 4), spacing=4):
    """QFrame#panel із готовим layout."""
    frame = QFrame()
    frame.setObjectName("panel")
    lay = layout_cls(frame)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return frame, lay


def labeled(text: str, widget: QWidget, stretch: int = 1) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(6)
    lbl = QLabel(text)
    lbl.setBuddy(widget)
    row.addWidget(lbl)
    row.addWidget(widget, stretch)
    return row


def tool_button(action=None, text: str | None = None, checkable: bool = False) -> QToolButton:
    btn = QToolButton()
    if action is not None:
        btn.setDefaultAction(action)
    if text is not None:
        btn.setText(text)
    if checkable and action is None:
        btn.setCheckable(True)
    btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
    btn.setFocusPolicy(Qt.NoFocus)
    return btn


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("hint")
    lbl.setWordWrap(True)
    return lbl


def render_markup(view: QTextEdit, text: str) -> bool:
    """Показує текст із розміткою студії (колір, b/i/u/s); некоректна розмітка — сирим текстом.
    Повертає True, якщо розмітку застосовано."""
    view.clear()
    cur = QTextCursor(view.document())
    if not mirror.markup_ok(text) or mirror.plain_text(text) == text:
        cur.insertText(text)
        return False
    cache = {}
    for r, row in enumerate(mirror.to_cells(text)):
        if r:
            cur.insertText("\n", QTextCharFormat())
        run, style = [], None
        for ch, st in row + [("", None)]:
            if st != style and run:
                fmt = cache.get(style)
                if fmt is None:
                    fmt = QTextCharFormat()
                    for tag in style:
                        if tag.startswith("<color:"):
                            fmt.setForeground(QColor("#" + tag[7:13]))
                        elif tag == "<b>":
                            fmt.setFontWeight(QFont.Bold)
                        elif tag == "<i>":
                            fmt.setFontItalic(True)
                        elif tag == "<u>":
                            fmt.setFontUnderline(True)
                        elif tag == "<s>":
                            fmt.setFontStrikeOut(True)
                    cache[style] = fmt
                cur.insertText("".join(run), fmt)
                run = []
            style = st
            run.append(ch)
    return True
