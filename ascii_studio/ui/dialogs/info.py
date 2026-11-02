"""Інформаційні діалоги: «Як у грі» (fit на типових екранах) і прев'ю кольорової розмітки."""
from __future__ import annotations

import re

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout

from ... import game_fit
from ...i18n import tr
from ...theme import load_app_fonts
from ..widgets import RichArtView, hint, render_markup

_TAGS = re.compile(r"</?(?:b|i|u|s)>|<color:[0-9a-fA-F]{6}>|</color>")


class GameFitDialog(QDialog):
    """Чи влізе арт у термінал гри (LazyEngine): бюджет, fit-масштаб, переповнення без fit."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("game_fit_title"))
        self.resize(780, 380)
        load_app_fonts()
        lay = QVBoxLayout(self)
        results = game_fit.evaluate_all(_TAGS.sub("", text))
        table = QTableWidget(len(results), 5)
        table.setHorizontalHeaderLabels(tr("game_fit_cols").split(";"))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        for row, r in enumerate(results):
            over = tr("game_fit_ok") if r.overflow == (0, 0) else tr("game_fit_over", c=r.overflow[0], l=r.overflow[1])
            cells = [r.name, f"{r.budget[0]}×{r.budget[1]}", f"{r.art[0]}×{r.art[1]}",
                     f"{r.scale:.2f}" + (" ✓" if r.scale >= 1.0 else ""), over]
            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                if col == 3 and r.scale < 0.6:
                    item.setForeground(QColor("#f59e0b"))
                if col == 4 and r.overflow != (0, 0):
                    item.setForeground(QColor("#ef4444"))
                table.setItem(row, col, item)
        lay.addWidget(table, 1)
        lay.addWidget(hint(tr("game_fit_hint")))
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText(tr("btn_close"))
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class ColorPreviewDialog(QDialog):
    """Арт із застосованою розміткою (кольори, жирний, курсив…)."""

    def __init__(self, text: str, colors: tuple[str, str], point_size: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("color_preview_title"))
        self.resize(820, 600)
        lay = QVBoxLayout(self)
        view = RichArtView(point_size)
        view.set_colors(*colors)
        if not render_markup(view, text) and _TAGS.search(text):
            lay.addWidget(hint(tr("color_preview_invalid")))
        lay.addWidget(view, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText(tr("btn_close"))
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
