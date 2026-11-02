"""Студія анімації: черга кадрів із файлів, прев'ю, шкала, привид попереднього кадру,
оцінка плавності переходів (скільки кадру змінюється між сусідніми кадрами)."""
from __future__ import annotations

import html
import os
import re

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QSlider, QSpinBox, QVBoxLayout,
)

from ... import settings
from ...core import anim_metrics, files
from ...i18n import tr
from ..file_tree import ASCII_FILE_TREE_ROLE, _DragSelectTree
from ...theme import TERMINAL_THEMES, THEME
from ..widgets import RichArtView, hint
from .files import dir_combo

_MODE_COLORS = {"append": "#22c55e", "middle": "#22c55e", "same": "#71717a", "full": "#f59e0b"}


class ReverseRangeDialog(QDialog):
    """Корінь назви й діапазон номерів для вставки у зворотному порядку."""

    def __init__(self, root: str, num_from: int, num_to: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("reverse_dlg_title"))
        form = QFormLayout(self)
        self.root_edit = QLineEdit(root)
        form.addRow(tr("lbl_root"), self.root_edit)
        self.from_spin = QSpinBox()
        self.from_spin.setRange(0, 99999)
        self.from_spin.setValue(num_from)
        self.to_spin = QSpinBox()
        self.to_spin.setRange(0, 99999)
        self.to_spin.setValue(num_to)
        row = QHBoxLayout()
        row.addWidget(self.from_spin)
        row.addWidget(QLabel(tr("lbl_to")))
        row.addWidget(self.to_spin)
        form.addRow(tr("lbl_from"), row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("btn_add"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("btn_cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def get_result(self):
        return self.root_edit.text().strip(), self.from_spin.value(), self.to_spin.value()


class FramesList(QListWidget):
    """Черга кадрів: приймає перетягування з дерева файлів і внутрішнє переміщення."""

    def __init__(self, on_change, parent=None):
        super().__init__(parent)
        self._on_change = on_change
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.model().rowsMoved.connect(lambda *_: QTimer.singleShot(0, self._on_change))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            self.setDragEnabled(bool(item and item.isSelected()))
        super().mousePressEvent(event)

    def dropEvent(self, event):
        src = event.source()
        if src is self:
            super().dropEvent(event)
            return
        target = self.itemAt(event.position().toPoint())
        row = self.row(target) + (1 if target and event.position().y() > self.visualItemRect(target).center().y() else 0) if target else self.count()
        for item in src.selectedItems() if src is not None else []:
            if item.childCount() == 0:
                self.insertItem(row, (item.data(0, ASCII_FILE_TREE_ROLE) or item.text(0)) + files.ART_EXT)
                row += 1
        event.setDropAction(Qt.CopyAction)
        event.accept()
        QTimer.singleShot(0, self._on_change)

    def names(self) -> list[str]:
        return [self.item(i).text() for i in range(self.count())]


class AnimationDialog(QDialog):
    """Налаштування та прев'ю ASCII-анімації."""

    def __init__(self, initial_files=None, initial_delay: float = 0.3, parent=None, dir_index: int | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("anim_title"))
        self.resize(1100, 680)
        self.delay = initial_delay
        self._clipboard: list[str] = []
        self.frames: list[str] = []
        self._shown = 0
        self._next = 0

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("lbl_dir")))
        self.source_combo = dir_combo(dir_index)
        row.addWidget(self.source_combo, 1)
        left.addLayout(row)
        lbl = QLabel(tr("lbl_available"))
        lbl.setObjectName("section")
        left.addWidget(lbl)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("placeholder_search"))
        self.search_edit.setClearButtonEnabled(True)
        left.addWidget(self.search_edit)
        self.available = _DragSelectTree()
        self.available.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.available.setDragEnabled(True)
        self.available.setDefaultDropAction(Qt.CopyAction)
        left.addWidget(self.available, 1)
        add_row = QHBoxLayout()
        btn_add = QPushButton(tr("btn_add_selected"))
        btn_add.clicked.connect(self._add_selected)
        btn_series = QPushButton(tr("btn_add_series"))
        btn_series.setToolTip(tr("tt_add_series"))
        btn_series.clicked.connect(self._add_series)
        btn_reverse = QPushButton(tr("btn_reverse"))
        btn_reverse.setToolTip(tr("tt_reverse"))
        btn_reverse.clicked.connect(self._add_reversed)
        for b in (btn_add, btn_series, btn_reverse):
            add_row.addWidget(b)
        left.addLayout(add_row)
        lbl2 = QLabel(tr("lbl_frames"))
        lbl2.setObjectName("section")
        left.addWidget(lbl2)
        self.frames_list = FramesList(self._refresh)
        self.frames_list.installEventFilter(self)
        left.addWidget(self.frames_list, 1)
        move_row = QHBoxLayout()
        for text, slot in ((tr("btn_up"), lambda: self._move(-1)), (tr("btn_down"), lambda: self._move(1)),
                           (tr("btn_remove"), self._remove)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            move_row.addWidget(b)
        left.addLayout(move_row)
        left.addWidget(hint(tr("anim_keys_hint")))
        root.addLayout(left, 2)

        right = QVBoxLayout()
        grp = QGroupBox(tr("grp_settings"))
        gl = QHBoxLayout(grp)
        gl.addWidget(QLabel(tr("lbl_delay")))
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.01, 5.0)
        self.delay_spin.setSingleStep(0.05)
        self.delay_spin.setValue(self.delay)
        self.delay_spin.setSuffix(tr("lbl_delay_sec"))
        gl.addWidget(self.delay_spin)
        gl.addSpacing(12)
        gl.addWidget(QLabel(tr("lbl_theme")))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(TERMINAL_THEMES))
        gl.addWidget(self.theme_combo)
        gl.addStretch()
        right.addWidget(grp)
        self.preview = RichArtView(11)
        right.addWidget(self.preview, 1)
        tl = QHBoxLayout()
        self.btn_pause = QPushButton("⏸")
        self.btn_pause.setCheckable(True)
        self.btn_pause.setToolTip(tr("tt_anim_pause"))
        btn_prev = QPushButton("◀")
        btn_next = QPushButton("▶")
        btn_restart = QPushButton("↺")
        btn_restart.setToolTip(tr("tt_restart"))
        self.timeline = QSlider(Qt.Horizontal)
        self.frame_label = QLabel("")
        self.onion_check = QCheckBox(tr("chk_onion"))
        self.onion_check.setToolTip(tr("tt_onion"))
        for w in (self.btn_pause, btn_prev, btn_next, btn_restart):
            w.setFixedWidth(36)
            tl.addWidget(w)
        tl.addWidget(self.timeline, 1)
        tl.addWidget(self.frame_label)
        tl.addWidget(self.onion_check)
        right.addLayout(tl)
        self.smooth_label = hint("")
        right.addWidget(self.smooth_label)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText(tr("btn_close"))
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        root.addLayout(right, 3)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.source_combo.currentIndexChanged.connect(self._load_available)
        self.search_edit.textChanged.connect(lambda t: self.available.apply_filter(t))
        self.available.itemDoubleClicked.connect(lambda *_: self._add_selected())
        self.delay_spin.valueChanged.connect(self._set_delay)
        self.theme_combo.currentTextChanged.connect(self._apply_theme)
        self.btn_pause.toggled.connect(self._toggle_pause)
        btn_prev.clicked.connect(lambda: self._step(-1))
        btn_next.clicked.connect(lambda: self._step(1))
        btn_restart.clicked.connect(self._restart)
        self.timeline.valueChanged.connect(self._on_timeline)
        self.onion_check.toggled.connect(lambda _c: self._show(self._shown))

        self._load_available()
        for f in initial_files or []:
            self.frames_list.addItem(f if f.endswith(files.ART_EXT) else f + files.ART_EXT)
        self._apply_theme()
        self._refresh()

    def folder(self) -> str:
        return self.source_combo.currentData() or settings.get().current_dir

    def _load_available(self, *_):
        self._names = files.list_arts(self.folder())
        self.available.populate(self._names)
        self.available.apply_filter(self.search_edit.text())
        self._refresh()

    def _add_selected(self):
        for item in self.available.selectedItems():
            if item.childCount() == 0:
                self.frames_list.addItem(self.available.full_name(item) + files.ART_EXT)
        self._refresh()

    def _current_name(self) -> str:
        item = self.available.currentItem()
        return self.available.full_name(item) if item is not None and item.childCount() == 0 else ""

    def _add_series(self):
        name = self._current_name()
        if not name:
            return
        m = re.match(r"^(.*?)(\d+)$", name)
        if not m:
            self.frames_list.addItem(name + files.ART_EXT)
        else:
            pattern = re.compile(r"^" + re.escape(m.group(1)) + r"(\d+)$")
            series = sorted((int(pattern.match(n).group(1)), n) for n in self._names if pattern.match(n))
            for _, n in series:
                self.frames_list.addItem(n + files.ART_EXT)
        self._refresh()

    def _add_reversed(self):
        name = self._current_name()
        m = re.match(r"^(.*?)(\d+)$", name) if name else None
        if not m:
            return
        root, pad = m.group(1), len(m.group(2))
        pattern = re.compile(r"^" + re.escape(root) + r"(\d+)$")
        nums = [int(pattern.match(n).group(1)) for n in self._names if pattern.match(n)]
        dlg = ReverseRangeDialog(root, min(nums, default=1), max(nums, default=int(m.group(2))), self)
        if dlg.exec() != QDialog.Accepted:
            return
        new_root, a, b = dlg.get_result()
        if new_root:
            lo, hi = sorted((a, b))
            for num in range(hi, lo - 1, -1):
                self.frames_list.addItem(f"{new_root}{num:0{pad}d}{files.ART_EXT}")
            self._refresh()

    def eventFilter(self, obj, event):
        if obj is self.frames_list and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Delete:
                self._remove()
                return True
            if event.matches(QKeySequence.Copy):
                self._clipboard = [it.text() for it in sorted(self.frames_list.selectedItems(), key=self.frames_list.row)]
                return True
            if event.matches(QKeySequence.Cut):
                self._clipboard = [it.text() for it in sorted(self.frames_list.selectedItems(), key=self.frames_list.row)]
                self._remove()
                return True
            if event.matches(QKeySequence.Paste) and self._clipboard:
                row = self.frames_list.currentRow()
                for i, text in enumerate(self._clipboard):
                    self.frames_list.insertItem(row + 1 + i if row >= 0 else self.frames_list.count(), text)
                self._refresh()
                return True
        return super().eventFilter(obj, event)

    def _remove(self):
        for item in self.frames_list.selectedItems():
            self.frames_list.takeItem(self.frames_list.row(item))
        self._refresh()

    def _move(self, delta: int):
        row = self.frames_list.currentRow()
        target = row + delta
        if 0 <= row < self.frames_list.count() and 0 <= target < self.frames_list.count():
            item = self.frames_list.takeItem(row)
            self.frames_list.insertItem(target, item)
            self.frames_list.setCurrentRow(target)
            self._refresh()

    def _set_delay(self, val: float):
        self.delay = val
        if self.timer.isActive():
            self.timer.start(int(self.delay * 1000))

    def _apply_theme(self, *_):
        colors = TERMINAL_THEMES.get(self.theme_combo.currentText(), next(iter(TERMINAL_THEMES.values())))
        self.preview.set_colors(colors["bg"], colors["fg"])

    def _refresh(self):
        self.timer.stop()
        names = self.frames_list.names()
        raw = []
        for f in names:
            try:
                raw.append(files.read_text(os.path.join(self.folder(), f)).split("\n"))
            except OSError:
                raw.append([tr("anim_missing_frame", name=f)])
        h = max((len(r) for r in raw), default=0)
        w = max((len(l) for r in raw for l in r), default=0)
        self.frames = ["\n".join((r[i] if i < len(r) else "").ljust(w) for i in range(h)) for r in raw]
        self._update_transitions()
        if not self.frames:
            self.preview.setPlainText(tr("msg_no_frames_preview"))
            self.frame_label.setText("0/0")
            return
        self.timeline.blockSignals(True)
        self.timeline.setRange(0, len(self.frames) - 1)
        self.timeline.blockSignals(False)
        self._next = 0
        self._show(0)
        if not self.btn_pause.isChecked():
            self._next = 1
            self.timer.start(int(self.delay * 1000))

    def _update_transitions(self):
        trans = anim_metrics.transitions(self.frames, loop=True) if len(self.frames) > 1 else []
        names = {m: tr(f"anim_mode_{m}") for m in _MODE_COLORS}
        by_target = {t.index: t for t in trans}
        for i in range(self.frames_list.count()):
            item = self.frames_list.item(i)
            t = by_target.get(i)
            if t is None:
                item.setToolTip("")
                item.setForeground(QColor(THEME["text"]))
                continue
            item.setForeground(QColor(_MODE_COLORS[t.mode]))
            item.setToolTip(tr("anim_transition_tip", prev=(i - 1) % len(self.frames) + 1, cur=i + 1,
                               mode=names[t.mode], shared=int(t.shared * 100)))
        full = sum(1 for t in trans if t.mode == "full")
        self.smooth_label.setText(tr("anim_smooth_summary", ok=len(trans) - full, total=len(trans), full=full) if trans else "")

    def _toggle_pause(self, paused: bool):
        self.btn_pause.setText("▶" if paused else "⏸")
        if paused:
            self.timer.stop()
        elif self.frames:
            self._next = self._shown + 1
            self.timer.start(int(self.delay * 1000))

    def _restart(self):
        self.btn_pause.setChecked(False)
        self._next = 0
        self._tick()
        self.timer.start(int(self.delay * 1000))

    def _step(self, delta: int):
        if self.frames:
            self.btn_pause.setChecked(True)
            self._show(self._shown + delta)

    def _on_timeline(self, value: int):
        if self.frames and value != self._shown:
            self.btn_pause.setChecked(True)
            self._show(value)

    def _tick(self):
        if self.frames:
            self._show(self._next)
            self._next = self._shown + 1

    def _show(self, idx: int):
        if not self.frames:
            return
        n = len(self.frames)
        idx %= n
        self._shown = idx
        art = self.frames[idx]
        if self.onion_check.isChecked() and n > 1 and "<" not in art:
            rows = ["".join(f"<span style='color:#71717a'>{html.escape(ch)}</span>" if ghost else html.escape(ch)
                            for ch, ghost in row)
                    for row in anim_metrics.onion_cells(self.frames[(idx - 1) % n], art)]
            self.preview.setHtml("<pre style='margin:0'>" + "\n".join(rows) + "</pre>")
        else:
            self.preview.setPlainText(art)
        self.timeline.blockSignals(True)
        self.timeline.setValue(idx)
        self.timeline.blockSignals(False)
        self.frame_label.setText(f"{idx + 1}/{n}")
        item = self.frames_list.item(idx)
        if item is not None:
            self.frames_list.scrollToItem(item)

    def get_result(self):
        return {"files": [n[: -len(files.ART_EXT)] if n.endswith(files.ART_EXT) else n for n in self.frames_list.names()],
                "delay": self.delay}
