"""Довідка й редактор гарячих клавіш (F1): пошук, перевизначення, конфлікти, скидання."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QKeySequenceEdit, QLabel, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from ... import settings, shortcuts
from ...i18n import tr
from ..widgets import hint


class KeyCaptureDialog(QDialog):
    """Запис однієї комбінації для дії."""

    def __init__(self, label: str, current: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg_key_capture"))
        self.result_keys: list[str] | None = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(label))
        self.edit = QKeySequenceEdit(QKeySequence(current))
        self.edit.setMaximumSequenceLength(1)
        lay.addWidget(self.edit)
        lay.addWidget(hint(tr("key_capture_hint")))
        row = QHBoxLayout()
        b_none = QPushButton(tr("btn_key_none"))
        b_default = QPushButton(tr("btn_key_default"))
        row.addWidget(b_none)
        row.addWidget(b_default)
        row.addStretch()
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText(tr("btn_cancel"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        b_none.clicked.connect(lambda: self._done([]))
        b_default.clicked.connect(lambda: self._done(None, reset=True))
        self.reset = False
        self.edit.setFocus()

    def _ok(self):
        seq = self.edit.keySequence().toString(QKeySequence.PortableText)
        self._done([seq] if seq else [])

    def _done(self, keys, reset: bool = False):
        self.result_keys = keys
        self.reset = reset
        self.accept()


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("shortcuts_title"))
        self.resize(720, 640)
        self._mgr = shortcuts.manager()
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("placeholder_search_shortcuts"))
        self.search.setClearButtonEnabled(True)
        lay.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([tr("col_action"), tr("col_keys")])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.itemDoubleClicked.connect(self._edit)
        lay.addWidget(self.tree, 1)
        self.conflicts = QLabel("")
        self.conflicts.setObjectName("warn")
        self.conflicts.setWordWrap(True)
        lay.addWidget(self.conflicts)
        lay.addWidget(hint(tr("shortcuts_hint")))
        bb = QDialogButtonBox(QDialogButtonBox.Close | QDialogButtonBox.Reset)
        bb.button(QDialogButtonBox.Close).setText(tr("btn_close"))
        bb.button(QDialogButtonBox.Reset).setText(tr("btn_reset_all"))
        bb.button(QDialogButtonBox.Reset).clicked.connect(self._reset_all)
        bb.button(QDialogButtonBox.Reset).setAutoDefault(False)
        bb.button(QDialogButtonBox.Close).setDefault(True)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.search.textChanged.connect(self._filter)
        self._build()

    def _build(self):
        self.tree.clear()
        conflicts = self._mgr.conflicts()
        bad_ids = {i for ids in conflicts.values() for i in ids}
        groups = {}
        for g in shortcuts.GROUPS:
            item = QTreeWidgetItem(self.tree, [tr(f"group_{g}")])
            item.setFirstColumnSpanned(True)
            f = item.font(0)
            f.setBold(True)
            item.setFont(0, f)
            item.setFlags(Qt.ItemIsEnabled)
            groups[g] = item
        for spec in shortcuts.SPECS:
            keys = ", ".join(QKeySequence(k).toString(QKeySequence.NativeText) for k in self._mgr.keys(spec.id))
            label = spec.label + ("  " + tr("scope_canvas") if spec.scope == shortcuts.CANVAS else "")
            item = QTreeWidgetItem(groups[spec.group], [label, keys or "—"])
            item.setData(0, Qt.UserRole, spec.id)
            if spec.id in self._mgr.overrides_as_text():
                f = item.font(1)
                f.setBold(True)
                item.setFont(1, f)
            if spec.id in bad_ids:
                item.setForeground(1, QColor("#ef4444"))
        self.tree.expandAll()
        if conflicts:
            lines = [f"{QKeySequence(k).toString(QKeySequence.NativeText)}: " + ", ".join(shortcuts.BY_ID[i].label for i in ids)
                     for k, ids in conflicts.items()]
            self.conflicts.setText(tr("shortcuts_conflicts") + "\n" + "\n".join(lines))
        else:
            self.conflicts.setText("")
        self._filter(self.search.text())

    def _filter(self, text: str):
        q = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            grp = self.tree.topLevelItem(i)
            any_visible = False
            for j in range(grp.childCount()):
                it = grp.child(j)
                vis = not q or q in it.text(0).lower() or q in it.text(1).lower()
                it.setHidden(not vis)
                any_visible |= vis
            grp.setHidden(not any_visible)

    def _edit(self, item, _column=0):
        id_ = item.data(0, Qt.UserRole)
        if not id_:
            return
        keys = self._mgr.keys(id_)
        dlg = KeyCaptureDialog(shortcuts.BY_ID[id_].label, keys[0] if keys else "", self)
        if dlg.exec() != QDialog.Accepted:
            return
        if dlg.reset:
            self._mgr.reset(id_)
        else:
            self._mgr.set_keys(id_, dlg.result_keys or [])
        self._save()

    def _reset_all(self):
        self._mgr.reset()
        self._save()

    def _save(self):
        settings.get().set_shortcut_overrides(self._mgr.overrides_as_text())
        self._build()
