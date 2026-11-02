"""Діалоги файлів: браузер артів робочих тек, збереження в теку, розмір нового полотна."""
from __future__ import annotations

import os

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QSplitter, QVBoxLayout, QWidget,
)

from ... import settings
from ...core import files
from ...i18n import tr
from ..file_tree import AsciiFileTree
from ..widgets import ArtView, hint


def dir_combo(initial_index: int | None = None) -> QComboBox:
    combo = QComboBox()
    st = settings.get()
    for d in st.dirs():
        combo.addItem(f"📁 {d['name']}", d["path"])
        combo.setItemData(combo.count() - 1, d["path"], Qt.ToolTipRole)
    if not st.dirs():
        combo.addItem(tr("no_dirs"), "")
    combo.setCurrentIndex(st.active_index if initial_index is None else max(0, initial_index))
    return combo


class ArtPickerDialog(QDialog):
    """Браузер артів із живим прев'ю (подвійний клік/Enter — відкрити)."""

    def __init__(self, parent=None, colors: tuple[str, str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("picker_title"))
        self.resize(1000, 680)
        self.selected = ""
        self.selected_path = ""
        root = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("lbl_dir")))
        self.source_combo = dir_combo()
        row.addWidget(self.source_combo, 1)
        lv.addLayout(row)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("placeholder_search"))
        self.search_edit.setClearButtonEnabled(True)
        lv.addWidget(self.search_edit)
        self.tree = AsciiFileTree()
        lv.addWidget(self.tree, 1)
        self.count_label = hint("")
        lv.addWidget(self.count_label)
        split.addWidget(left)
        self.preview = ArtView(11)
        if colors:
            self.preview.set_colors(*colors)
        split.addWidget(self.preview)
        split.setSizes([320, 680])
        root.addWidget(split, 1)
        btns = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Open).setText(tr("btn_pick"))
        btns.button(QDialogButtonBox.Cancel).setText(tr("btn_cancel"))
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)
        self.source_combo.currentIndexChanged.connect(self._load)
        self.search_edit.textChanged.connect(self._filter)
        self.tree.currentItemChanged.connect(self._on_current)
        self.tree.itemDoubleClicked.connect(lambda item, _c=0: item.childCount() == 0 and self._accept())
        self._load()
        self.search_edit.setFocus()

    def folder(self) -> str:
        return self.source_combo.currentData() or settings.get().current_dir

    def _load(self, *_):
        self._names = files.list_arts(self.folder())
        self.tree.populate(self._names)
        self._filter(self.search_edit.text())

    def _filter(self, text: str) -> None:
        self.tree.apply_filter(text)
        first = self.tree.first_visible_item()
        if first is not None and first.childCount() == 0:
            self.tree.setCurrentItem(first)
        else:
            self.preview.clear()
        self.count_label.setText(tr("picker_count", n=len(self._names)))

    def _on_current(self, current, _previous=None):
        if isinstance(current, QModelIndex):
            current = self.tree.itemFromIndex(current)
        if current is None or current.childCount() > 0:
            self.preview.clear()
            return
        path = os.path.join(self.folder(), self.tree.full_name(current) + files.ART_EXT)
        try:
            self.preview.setPlainText(files.read_text(path))
        except OSError:
            self.preview.setPlainText(tr("msg_file_not_found_path", path=path))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.tree.hasFocus():
            self._accept()
            return
        super().keyPressEvent(event)

    def _accept(self):
        item = self.tree.currentItem()
        if item is None or item.childCount() > 0:
            return
        self.selected = self.tree.full_name(item)
        self.selected_path = os.path.join(self.folder(), self.selected + files.ART_EXT)
        self.accept()


class SaveDialog(QDialog):
    """Ім'я, робоча тека й підтека для збереження арту."""

    def __init__(self, default_name: str, parent=None, initial_dir: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("save_dlg_title"))
        self.setMinimumWidth(460)
        st = settings.get()
        idx, sub = (st.dir_index_for(initial_dir) if initial_dir else (-1, ""))
        form = QFormLayout(self)
        self.name_edit = QLineEdit(default_name)
        self.name_edit.selectAll()
        form.addRow(tr("lbl_filename"), self.name_edit)
        self.dir_combo = dir_combo(idx if idx >= 0 else None)
        form.addRow(tr("lbl_target_dir"), self.dir_combo)
        self.subdir_edit = QLineEdit(sub.replace(os.sep, "/"))
        self.subdir_edit.setPlaceholderText(tr("placeholder_subdir"))
        form.addRow(tr("lbl_subdir"), self.subdir_edit)
        self.path_hint = hint("")
        form.addRow(self.path_hint)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText(tr("btn_save_ok"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("btn_cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        for sig in (self.name_edit.textChanged, self.subdir_edit.textChanged, self.dir_combo.currentIndexChanged):
            sig.connect(self._update_hint)
        self._update_hint()

    def target_path(self) -> str:
        parts = files.safe_parts(self.subdir_edit.text() + "/" + self.name_edit.text()) if self.name_edit.text().strip() else []
        if not parts:
            return ""
        base = self.dir_combo.currentData() or settings.get().current_dir
        return os.path.join(base, *parts) + files.ART_EXT

    def _update_hint(self, *_):
        path = self.target_path()
        exists = bool(path) and os.path.exists(path)
        self.path_hint.setText((tr("save_hint_exists") if exists else tr("save_hint")) + (f"\n{path}" if path else ""))

    def get_result(self) -> str:
        return self.target_path()


class CanvasSizeDialog(QDialog):
    """Розмір нового полотна (заповнюється пробілами — зручно для кисті)."""

    def __init__(self, parent=None, width: int = 80, height: int = 24):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg_canvas_size_title"))
        form = QFormLayout(self)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 1000)
        self.width_spin.setValue(width)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 500)
        self.height_spin.setValue(height)
        form.addRow(tr("lbl_width"), self.width_spin)
        form.addRow(tr("lbl_height"), self.height_spin)
        presets = QComboBox()
        presets.addItem(tr("canvas_presets"), None)
        for w, h in ((40, 12), (80, 24), (96, 38), (120, 40), (160, 50)):
            presets.addItem(f"{w}×{h}", (w, h))
        presets.currentIndexChanged.connect(lambda _i: presets.currentData() and self._set(*presets.currentData()))
        form.addRow(tr("lbl_presets"), presets)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Cancel).setText(tr("btn_cancel"))
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _set(self, w: int, h: int) -> None:
        self.width_spin.setValue(w)
        self.height_spin.setValue(h)

    def canvas_size(self) -> tuple[int, int]:
        return self.width_spin.value(), self.height_spin.value()
