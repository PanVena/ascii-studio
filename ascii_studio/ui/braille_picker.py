"""Пікер символів Брайля (8 крапок): компактна панель полотна або окремий діалог."""
from PySide6.QtWidgets import (QApplication, QDialog, QWidget, QGridLayout,
                               QPushButton, QLabel, QVBoxLayout, QHBoxLayout)
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtCore import Qt, Signal

from ..i18n import tr as _tr

_DOT_VALUES = {
    1: 0x01, 2: 0x02, 3: 0x04, 4: 0x08,
    5: 0x10, 6: 0x20, 7: 0x40, 8: 0x80
}

_DOT_POSITIONS = {
    1: (0, 0), 4: (0, 1),
    2: (1, 0), 5: (1, 1),
    3: (2, 0), 6: (2, 1),
    7: (3, 0), 8: (3, 1)
}


class BraillePickerWidget(QWidget):
    """Пікер Брайля, який можна вбудувати в будь-який layout.

    compact=True — горизонтальна компактна розкладка для панелі полотна.
    compact=False — велика вертикальна розкладка (для діалогу).

    Глобальні Qt-шорткати 1..8 реєструються лише в режимі compact=False,
    щоб не ловити цифри під час набору тексту в полотні.
    """

    glyph_inserted = Signal(str)

    def __init__(self, parent=None, on_insert=None, compact=True):
        super().__init__(parent)
        self._on_insert = on_insert
        self._compact = compact
        self.buttons = {}

        if compact:
            self._init_compact()
        else:
            self._init_full()
            self._install_global_shortcuts()

        self.update_glyph()

    # ── layouts ────────────────────────────────────────────────────────────
    def _init_compact(self):
        main = QHBoxLayout(self)
        main.setContentsMargins(4, 4, 4, 4)
        main.setSpacing(8)

        # Дисплей
        disp = QVBoxLayout()
        disp.setSpacing(0)
        self.lbl_result = QLabel(chr(0x2800))
        self.lbl_result.setFont(QFont("DejaVu Sans", 28))
        self.lbl_result.setAlignment(Qt.AlignCenter)
        self.lbl_result.setMinimumWidth(44)
        disp.addWidget(self.lbl_result)
        self.lbl_hex = QLabel("U+2800")
        self.lbl_hex.setAlignment(Qt.AlignCenter)
        self.lbl_hex.setStyleSheet("font-size: 10px; color: #888;")
        disp.addWidget(self.lbl_hex)
        main.addLayout(disp)

        # Сітка 8 крапок (1 4 / 2 5 / 3 6 / 7 8)
        grid = QGridLayout()
        grid.setSpacing(2)
        for dot, pos in _DOT_POSITIONS.items():
            btn = QPushButton(str(dot))
            btn.setCheckable(True)
            btn.setFixedSize(28, 22)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setFont(QFont("JetBrains Mono", 10, QFont.Bold))
            btn.clicked.connect(self.update_glyph)
            self.buttons[dot] = btn
            grid.addWidget(btn, *pos)
        main.addLayout(grid)

        # Дії
        acts = QVBoxLayout()
        acts.setSpacing(2)
        btn_insert = QPushButton(_tr("bp_btn_insert"))
        btn_insert.setFocusPolicy(Qt.NoFocus)
        btn_insert.setToolTip(_tr("bp_tt_insert"))
        btn_insert.clicked.connect(self.insert_glyph)
        acts.addWidget(btn_insert)
        btn_clear = QPushButton(_tr("bp_btn_clear"))
        btn_clear.setFocusPolicy(Qt.NoFocus)
        btn_clear.setToolTip(_tr("bp_tt_clear"))
        btn_clear.clicked.connect(self.clear_dots)
        acts.addWidget(btn_clear)
        main.addLayout(acts)

        main.addStretch(1)

    def _init_full(self):
        layout = QVBoxLayout(self)

        self.lbl_result = QLabel(chr(0x2800))
        self.lbl_result.setFont(QFont("DejaVu Sans", 64))
        self.lbl_result.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_result)

        self.lbl_hex = QLabel("U+2800")
        self.lbl_hex.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_hex)

        grid = QGridLayout()
        for dot, pos in _DOT_POSITIONS.items():
            btn = QPushButton(str(dot))
            btn.setCheckable(True)
            btn.setFixedSize(60, 60)
            btn.setFont(QFont("JetBrains Mono", 20, QFont.Bold))
            btn.clicked.connect(self.update_glyph)
            self.buttons[dot] = btn
            grid.addWidget(btn, *pos)
        layout.addLayout(grid)

        info = QLabel(_tr("bp_info"))
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)

    def _install_global_shortcuts(self):
        for dot in range(1, 9):
            QShortcut(QKeySequence(str(dot)), self).activated.connect(
                lambda d=dot: self.toggle_dot(d)
            )
        QShortcut(QKeySequence("Backspace"), self).activated.connect(self.clear_dots)

    # ── logic ──────────────────────────────────────────────────────────────
    def toggle_dot(self, dot):
        btn = self.buttons.get(dot)
        if not btn:
            return
        btn.setChecked(not btn.isChecked())
        self.update_glyph()

    def update_glyph(self):
        val = 0
        for dot, btn in self.buttons.items():
            if btn.isChecked():
                val += _DOT_VALUES[dot]
        char = chr(0x2800 + val)
        self.lbl_result.setText(char)
        self.lbl_hex.setText(f"U+{0x2800 + val:04X}")

    def clear_dots(self):
        for btn in self.buttons.values():
            btn.setChecked(False)
        self.update_glyph()

    def current_glyph(self) -> str:
        return self.lbl_result.text()

    def insert_glyph(self, keep_dots: bool = False):
        """Викликає callback і (за замовчуванням) скидає крапки для наступного символа."""
        ch = self.current_glyph()
        self.glyph_inserted.emit(ch)
        if self._on_insert is not None:
            self._on_insert(ch)
        if not keep_dots:
            self.clear_dots()


class BraillePickerDialog(QDialog):
    """Автономне вікно пікера — використовується, коли модуль запускається
    самостійно або викликається без вбудованої панелі."""

    def __init__(self, parent=None, on_insert=None):
        super().__init__(parent)
        self.setWindowTitle(_tr("bp_window_title"))
        self._on_insert = on_insert

        layout = QVBoxLayout(self)
        self.picker = BraillePickerWidget(self, on_insert=on_insert, compact=False)
        layout.addWidget(self.picker)

        controls = QHBoxLayout()
        if on_insert is not None:
            btn_ins = QPushButton(_tr("bp_btn_insert"))
            btn_ins.setFixedHeight(40)
            btn_ins.clicked.connect(self.picker.insert_glyph)
            controls.addWidget(btn_ins)

            btn_accept = QPushButton(_tr("bp_btn_insert_close"))
            btn_accept.setFixedHeight(40)
            btn_accept.clicked.connect(self._insert_and_close)
            controls.addWidget(btn_accept)
        else:
            btn_copy = QPushButton(_tr("bp_btn_copy_close"))
            btn_copy.setFixedHeight(40)
            btn_copy.clicked.connect(self._copy_and_close)
            controls.addWidget(btn_copy)

        btn_clear = QPushButton(_tr("bp_btn_clear"))
        btn_clear.setFixedHeight(40)
        btn_clear.clicked.connect(self.picker.clear_dots)
        controls.addWidget(btn_clear)
        layout.addLayout(controls)

        accept_slot = self._insert_and_close if on_insert is not None else self._copy_and_close
        QShortcut(QKeySequence("Return"), self).activated.connect(accept_slot)
        QShortcut(QKeySequence("Enter"), self).activated.connect(accept_slot)
        if on_insert is not None:
            QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self.picker.insert_glyph)
            QShortcut(QKeySequence("Ctrl+Enter"), self).activated.connect(self.picker.insert_glyph)

    def _copy_and_close(self):
        QApplication.clipboard().setText(self.picker.current_glyph())
        self.accept()

    def _insert_and_close(self):
        if self._on_insert is None:
            self._copy_and_close()
            return
        try:
            self._on_insert(self.picker.current_glyph())
        finally:
            self.accept()

