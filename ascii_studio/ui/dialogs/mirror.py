"""Вікно «Дзеркало»: живе відображення виділення / шару / композиту поточного полотна.

Осі: ⇋ ліво↔право, ⇵ верх↔низ, ✛ поворот на 180°. Режим «Склеїти» показує оригінал
разом із відображенням (симетричний арт із половинки), «Спільна вісь» — без
подвоєння центральної колонки/рядка. Результат можна застосувати до полотна
(один крок undo), відкрити новою вкладкою чи скопіювати.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QToolButton,
    QVBoxLayout, QWidget,
)

from ... import settings
from ...core import mirror, textgrid
from ...core.textgrid import Rect
from ...i18n import tr
from ..canvas import CanvasEditor
from ..widgets import RichArtView, hint, render_markup

SOURCES = ("auto", "selection", "layer", "composite")


class MirrorWindow(QWidget):
    """Плаваюче вікно дзеркала (завжди поверх студії)."""
    open_as_tab = Signal(str, str)

    def __init__(self, workspace, tools, actions: list, parent=None):
        super().__init__(parent, Qt.Tool)
        self.setWindowTitle(tr("mirror_title"))
        self.resize(680, 440)
        self._ws = workspace
        self._tools = tools
        self._editor: Optional[CanvasEditor] = None
        self.addActions(actions)
        st = settings.get()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("lbl_mirror_source")))
        self.source_combo = QComboBox()
        for key in SOURCES:
            self.source_combo.addItem(tr(f"mirror_src_{key}"), key)
        self.source_combo.setCurrentIndex(max(0, SOURCES.index(st.get("mirror_source", "auto")) if st.get("mirror_source") in SOURCES else 0))
        top.addWidget(self.source_combo)
        top.addSpacing(8)
        self.axis_group = QButtonGroup(self)
        self.axis_buttons = {}
        for axis, label in ((mirror.H, "⇋"), (mirror.V, "⇵"), (mirror.HV, "✛")):
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setToolTip(tr(f"tt_axis_{axis}"))
            b.setFixedWidth(34)
            self.axis_group.addButton(b)
            self.axis_buttons[axis] = b
            top.addWidget(b)
        self.axis_buttons.get(st.get("mirror_axis", mirror.H), self.axis_buttons[mirror.H]).setChecked(True)
        top.addSpacing(8)
        self.join_check = QCheckBox(tr("chk_mirror_join"))
        self.join_check.setToolTip(tr("tt_mirror_join"))
        self.join_check.setChecked(bool(st.get("mirror_join", False)))
        self.overlap_check = QCheckBox(tr("chk_mirror_overlap"))
        self.overlap_check.setToolTip(tr("tt_mirror_overlap"))
        self.overlap_check.setChecked(bool(st.get("mirror_overlap", False)))
        top.addWidget(self.join_check)
        top.addWidget(self.overlap_check)
        top.addStretch()
        lay.addLayout(top)

        self.view = RichArtView(12)
        lay.addWidget(self.view, 1)
        self.info = hint("")
        lay.addWidget(self.info)

        bottom = QHBoxLayout()
        self.btn_apply = QPushButton(tr("btn_mirror_apply"))
        self.btn_apply.setObjectName("primary")
        self.btn_apply.setToolTip(tr("tt_mirror_apply"))
        self.btn_tab = QPushButton(tr("btn_mirror_tab"))
        self.btn_copy = QPushButton(tr("btn_copy"))
        for b in (self.btn_apply, self.btn_tab, self.btn_copy):
            b.setFocusPolicy(Qt.NoFocus)
            bottom.addWidget(b)
        bottom.addStretch()
        lay.addLayout(bottom)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self.refresh)
        self.source_combo.currentIndexChanged.connect(self._options_changed)
        self.axis_group.buttonToggled.connect(lambda _b, on: on and self._options_changed())
        self.join_check.toggled.connect(self._options_changed)
        self.overlap_check.toggled.connect(self._options_changed)
        self.btn_apply.clicked.connect(self.apply)
        self.btn_tab.clicked.connect(self._to_tab)
        self.btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.result()[0]))
        workspace.current_changed.connect(self._follow_current)
        tools.changed.connect(self._apply_colors)
        self._apply_colors()
        self._follow_current()

    # ── стан ────────────────────────────────────────────────────────────────

    def axis(self) -> str:
        for axis, b in self.axis_buttons.items():
            if b.isChecked():
                return axis
        return mirror.H

    def set_axis(self, axis: str) -> None:
        self.axis_buttons[axis].setChecked(True)

    def source(self) -> str:
        return self.source_combo.currentData()

    def _options_changed(self, *_):
        self.overlap_check.setEnabled(self.join_check.isChecked())
        st = settings.get()
        st.set("mirror_source", self.source())
        st.set("mirror_axis", self.axis())
        st.set("mirror_join", self.join_check.isChecked())
        st.set("mirror_overlap", self.overlap_check.isChecked())
        self.schedule()

    def _apply_colors(self):
        self.view.set_colors(self._tools.bg, self._tools.fg)

    def _follow_current(self):
        ed = self._ws.current()
        if ed is self._editor:
            self.schedule()
            return
        if self._editor is not None:
            for sig in (self._editor.textChanged, self._editor.selectionChanged, self._editor.layers_changed):
                try:
                    sig.disconnect(self.schedule)
                except (RuntimeError, TypeError):
                    pass
        self._editor = ed
        if ed is not None:
            ed.textChanged.connect(self.schedule)
            ed.selectionChanged.connect(self.schedule)
            ed.layers_changed.connect(self.schedule)
        self.schedule()

    def schedule(self, *_):
        if self.isVisible():
            self._timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    # ── обчислення ──────────────────────────────────────────────────────────

    def _source_region(self):
        """(текст, область): область = Rect | "layer" | "composite" | None."""
        ed = self._editor
        if ed is None:
            return "", None
        src = self.source()
        rect = ed.selection_rect(full_rows_if_empty=True) if src in ("auto", "selection") else None
        if rect is not None:
            return "\n".join(textgrid.read_rect(ed.lines(), rect)), rect
        if src == "selection":
            return "", None
        if src == "composite":
            return ed.composite_text(), "composite"
        return ed.toPlainText(), "layer"

    def result(self) -> tuple[str, object]:
        text, region = self._source_region()
        if not text.strip():
            return "", region
        axis = self.axis()
        if self.join_check.isChecked():
            return mirror.join_text(text, axis, self.overlap_check.isChecked()), region
        return mirror.flip_text(text, axis), region

    def refresh(self):
        out, region = self.result()
        styled = render_markup(self.view, out)
        if region is None:
            self.info.setText(tr("mirror_hint_empty"))
        else:
            text, _ = self._source_region()
            where = (tr("mirror_where_rect", r=region.r0 + 1, c=region.c0 + 1, w=region.width, h=region.height)
                     if isinstance(region, Rect) else tr(f"mirror_where_{region}"))
            parts = [where, tr("mirror_size", w=textgrid.max_width(mirror.plain_text(out).split("\n")), h=out.count("\n") + 1 if out else 0)]
            bad = mirror.unmatched_chars(text, self.axis())
            if bad:
                parts.append(tr("mirror_unmatched", chars=" ".join(bad[:20])))
            if not styled and mirror.plain_text(text) != text:
                parts.append(tr("mirror_markup_raw"))
            self.info.setText("  ·  ".join(parts))
        self.btn_apply.setEnabled(bool(out) and region not in (None, "composite"))
        self.btn_tab.setEnabled(bool(out))
        self.btn_copy.setEnabled(bool(out))

    def apply(self):
        ed = self._editor
        out, region = self.result()
        if ed is None or not out or region in (None, "composite"):
            return
        lines = ed.lines()
        if isinstance(region, Rect):
            block = out.split("\n")
            cleared = textgrid.clear_rect(lines, region)
            new = textgrid.write_rect(cleared, region.r0, region.c0, block)
            w = max(region.width, textgrid.max_width(block))
            ed.set_lines(new, select=Rect(region.r0, region.r0 + len(block) - 1, region.c0, region.c0 + w))
        else:
            ed.set_lines(out.split("\n"))
        ed.setFocus()

    def _to_tab(self):
        out, _ = self.result()
        if out and self._editor is not None:
            self.open_as_tab.emit(f"{self._editor.title}_mirror", out)
