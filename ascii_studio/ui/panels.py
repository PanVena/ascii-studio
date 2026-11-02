"""Бічні й нижні панелі студії: FIGlet-параметри, шари, палітра символів, кисть, кольори, Брайль."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QColorDialog, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QSizePolicy, QSpinBox, QToolButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from .. import figlet, shortcuts
from ..core import charsets, mirror
from ..i18n import tr
from ..theme import CUSTOM_THEME, TERMINAL_THEMES, THEME, contrast_text
from .braille_picker import BraillePickerWidget
from .canvas import CanvasEditor
from .widgets import labeled, panel, tool_button


class FigletPanel(QWidget):
    """Ліва панель режиму FIGlet: текст, шрифт, параметри."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        grp_text = QGroupBox(tr("grp_text"))
        gt = QVBoxLayout(grp_text)
        self.text_input = QLineEdit(tr("pangram"))
        self.text_input.setPlaceholderText(tr("placeholder_text"))
        self.text_input.setClearButtonEnabled(True)
        gt.addWidget(self.text_input)
        lay.addWidget(grp_text)

        grp_font = QGroupBox(tr("grp_font", n=len(figlet.ALL_FONTS)))
        gf = QVBoxLayout(grp_font)
        self.font_search = QLineEdit()
        self.font_search.setPlaceholderText(tr("placeholder_font"))
        self.font_search.setClearButtonEnabled(True)
        gf.addWidget(self.font_search)
        self.font_list = QListWidget()
        self.font_list.setMinimumHeight(120)
        self.font_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        gf.addWidget(self.font_list, 1)
        lay.addWidget(grp_font, 1)

        grp_params = QGroupBox(tr("grp_params"))
        gp = QVBoxLayout(grp_params)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(20, 400)
        self.width_spin.setValue(80)
        gp.addLayout(labeled(tr("lbl_width"), self.width_spin))
        self.dir_combo = QComboBox()
        self.dir_combo.addItems(figlet.DIRECTIONS)
        gp.addLayout(labeled(tr("lbl_direction"), self.dir_combo))
        self.just_combo = QComboBox()
        self.just_combo.addItems(figlet.JUSTIFICATIONS)
        gp.addLayout(labeled(tr("lbl_align"), self.just_combo))
        self.line_numbers_cb = QCheckBox(tr("lbl_line_nums"))
        gp.addWidget(self.line_numbers_cb)
        lay.addWidget(grp_params)

        self.buttons = QVBoxLayout()
        self.buttons.setSpacing(4)
        lay.addLayout(self.buttons)

        self._fill_fonts("")
        self.font_search.textChanged.connect(self._fill_fonts)
        for sig in (self.text_input.textChanged, self.font_list.currentItemChanged, self.width_spin.valueChanged,
                    self.dir_combo.currentIndexChanged, self.just_combo.currentIndexChanged,
                    self.line_numbers_cb.toggled):
            sig.connect(lambda *_: self.changed.emit())
        if not figlet.AVAILABLE:
            for w in (self.text_input, self.font_search, self.font_list, self.width_spin, self.dir_combo,
                      self.just_combo, self.line_numbers_cb):
                w.setEnabled(False)

    def add_button(self, action) -> QToolButton:
        btn = tool_button(action)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setMinimumHeight(30)
        self.buttons.addWidget(btn)
        return btn

    def _fill_fonts(self, query: str) -> None:
        current = self.font_name()
        q = query.strip().lower()
        self.font_list.blockSignals(True)
        self.font_list.clear()
        if not figlet.AVAILABLE:
            self.font_list.addItem(tr("pyfiglet_missing"))
            self.font_list.blockSignals(False)
            return
        names = [f for f in figlet.ALL_FONTS if q in f.lower()] if q else figlet.ALL_FONTS
        self.font_list.addItems(names)
        target = current if current in names else (figlet.DEFAULT_FONT if figlet.DEFAULT_FONT in names else None)
        row = names.index(target) if target else 0
        self.font_list.blockSignals(False)
        if names:
            self.font_list.setCurrentRow(row)

    def font_name(self) -> str:
        it = self.font_list.currentItem() if hasattr(self, "font_list") else None
        return it.text() if it is not None and figlet.AVAILABLE else figlet.DEFAULT_FONT

    def set_font_name(self, name: str) -> None:
        items = self.font_list.findItems(name, Qt.MatchExactly)
        if items:
            self.font_list.setCurrentItem(items[0])

    def params(self) -> dict:
        return {
            "text": self.text_input.text() or " ",
            "font": self.font_name(),
            "width": self.width_spin.value(),
            "direction": self.dir_combo.currentText(),
            "justify": self.just_combo.currentText(),
        }


class ThemePicker(QWidget):
    """Тема полотна (пресети + власні кольори)."""
    changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.combo = QComboBox()
        self.combo.addItems(list(TERMINAL_THEMES) + [CUSTOM_THEME])
        self.combo.setItemText(self.combo.count() - 1, tr("theme_custom"))
        self.combo.setToolTip(tr("tt_theme"))
        lay.addWidget(self.combo)
        self.bg_btn = self._swatch_button(tr("lbl_bg"))
        self.fg_btn = self._swatch_button(tr("lbl_text_color"))
        lay.addWidget(self.bg_btn)
        lay.addWidget(self.fg_btn)
        self._custom = {"bg": "#000000", "fg": "#ffffff"}
        self.combo.currentIndexChanged.connect(self._emit)
        self.bg_btn.clicked.connect(lambda: self._pick("bg"))
        self.fg_btn.clicked.connect(lambda: self._pick("fg"))

    @staticmethod
    def _swatch_button(tip: str) -> QToolButton:
        b = QToolButton()
        b.setToolTip(tip)
        b.setFixedSize(22, 22)
        b.setFocusPolicy(Qt.NoFocus)
        return b

    def theme_name(self) -> str:
        i = self.combo.currentIndex()
        return CUSTOM_THEME if i == self.combo.count() - 1 else self.combo.currentText()

    def colors(self) -> tuple[str, str]:
        name = self.theme_name()
        c = self._custom if name == CUSTOM_THEME else TERMINAL_THEMES[name]
        return c["bg"], c["fg"]

    def set_theme(self, name: str, custom: Optional[dict] = None) -> None:
        if custom:
            self._custom.update({k: v for k, v in custom.items() if k in ("bg", "fg") and QColor(v).isValid()})
        idx = self.combo.count() - 1 if name == CUSTOM_THEME else self.combo.findText(name)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        self._emit()

    def custom_colors(self) -> dict:
        return dict(self._custom)

    def _pick(self, key: str) -> None:
        bg, fg = self.colors()
        col = QColorDialog.getColor(QColor(bg if key == "bg" else fg), self, tr("dlg_pick_color"))
        if not col.isValid():
            return
        self._custom.update({"bg": bg, "fg": fg})
        self._custom[key] = col.name()
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(self.combo.count() - 1)
        self.combo.blockSignals(False)
        self._emit()

    def _emit(self, *_):
        bg, fg = self.colors()
        for btn, c in ((self.bg_btn, bg), (self.fg_btn, fg)):
            btn.setStyleSheet(f"QToolButton {{ background: {c}; border: 1px solid {THEME['border']}; border-radius: 3px; }}"
                              f"QToolButton:hover {{ border-color: {THEME['accent']}; }}")
        self.changed.emit(bg, fg)


class LayersPanel(QWidget):
    """Список шарів поточного полотна (згори — верхній), видимість чекбоксом."""

    def __init__(self, actions: dict, parent=None):
        super().__init__(parent)
        self._editor: Optional[CanvasEditor] = None
        self.setMinimumWidth(150)
        self.setMaximumWidth(260)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        head = QLabel(tr("lbl_layers"))
        head.setObjectName("section")
        lay.addWidget(head)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.currentItemChanged.connect(self._on_selected)
        self.tree.itemDoubleClicked.connect(lambda *_: actions["rename"].trigger())
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        row.setSpacing(2)
        for key in ("add", "up", "down", "rename", "remove"):
            b = tool_button(actions[key])
            b.setText(tr(f"btn_layer_{key}"))
            row.addWidget(b)
        lay.addLayout(row)

    def set_editor(self, editor: Optional[CanvasEditor]) -> None:
        if self._editor is not None:
            try:
                self._editor.layers_changed.disconnect(self.rebuild)
            except (RuntimeError, TypeError):
                pass
        self._editor = editor
        if editor is not None:
            editor.layers_changed.connect(self.rebuild)
        self.rebuild()

    def rebuild(self) -> None:
        ed = self._editor
        self.tree.blockSignals(True)
        self.tree.clear()
        current = None
        if ed is not None:
            for i in reversed(range(ed.layers.count)):
                layer = ed.layers.get(i)
                item = QTreeWidgetItem(self.tree, [layer.name])
                item.setData(0, Qt.UserRole, i)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Checked if layer.visible else Qt.Unchecked)
                if layer is ed.active_layer:
                    f = QFont(item.font(0))
                    f.setBold(True)
                    item.setFont(0, f)
                    current = item
        if current is not None:
            self.tree.setCurrentItem(current)
        self.tree.blockSignals(False)

    def selected_layer(self):
        item = self.tree.currentItem()
        if item is None or self._editor is None:
            return None
        idx = int(item.data(0, Qt.UserRole))
        return self._editor.layers.get(idx) if 0 <= idx < self._editor.layers.count else None

    def item_for(self, idx: int) -> Optional[QTreeWidgetItem]:
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.data(0, Qt.UserRole) == idx:
                return it
        return None

    def _on_selected(self, current, _previous=None):
        layer = self.selected_layer() if current is not None else None
        if layer is not None and self._editor is not None:
            self._editor.switch_layer(layer)

    def _on_item_changed(self, item, column):
        if column != 0 or self._editor is None:
            return
        idx = int(item.data(0, Qt.UserRole))
        if 0 <= idx < self._editor.layers.count:
            self._editor.set_layer_visible(self._editor.layers.get(idx), item.checkState(0) == Qt.Checked)


class CharPalette(QWidget):
    """Сітка символів обраної категорії; перші 9 — Alt+1…9 у полотні."""
    char_clicked = Signal(str)
    palette_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        head = QHBoxLayout()
        lbl = QLabel(tr("lbl_chars"))
        lbl.setObjectName("section")
        head.addWidget(lbl)
        self.combo = QComboBox()
        for key, _chars in charsets.GROUPS:
            self.combo.addItem(tr(f"cat_{key}"), key)
        head.addWidget(self.combo, 1)
        lay.addLayout(head)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(2)
        lay.addWidget(self.grid_host)
        self.grid_host.installEventFilter(self)
        self._key = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._rebuild)
        self.combo.currentIndexChanged.connect(lambda _i: self._rebuild(force=True))
        shortcuts.manager().changed.connect(lambda: self._rebuild(force=True))
        self._rebuild(force=True)

    def chars(self) -> str:
        return charsets.BY_KEY.get(self.combo.currentData(), "")

    def eventFilter(self, obj, event):
        if obj is self.grid_host and event.type() == QEvent.Resize:
            self._timer.start()
        return super().eventFilter(obj, event)

    def _rebuild(self, force: bool = False) -> None:
        chars = self.chars()
        size = 24
        avail = max(self.grid_host.width(), 240)
        cols = max(1, min(len(chars), (avail + 2) // (size + 2)))
        key = (self.combo.currentData(), cols)
        if key == self._key and not force:
            return
        self._key = key
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        mgr = shortcuts.manager()
        for i, ch in enumerate(chars):
            btn = QToolButton()
            btn.setObjectName("glyph")
            btn.setText(ch)
            btn.setFixedSize(size, size)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setAutoRepeat(True)
            btn.setAutoRepeatDelay(350)
            btn.setAutoRepeatInterval(60)
            tip = tr("braille_space") if ch == "⠀" else ch
            tooltip = tr("tt_insert_char", tip=tip, code=ord(ch))
            if i < 9 and mgr.display(f"block.palette_{i + 1}"):
                tooltip += f"  [{mgr.display(f'block.palette_{i + 1}')}]"
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda _=False, c=ch: self.char_clicked.emit(c))
            self.grid.addWidget(btn, i // cols, i % cols)
        self.grid.setColumnStretch(cols, 1)
        self.palette_changed.emit(chars)


class BrushBar(QWidget):
    """Кисть: символ (монохромки або будь-який), гумка, симетрія."""
    char_changed = Signal(str)
    symmetry_changed = Signal(str)

    MONO = ("█", "▓", "▒", "░")

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(4)
        lbl = QLabel(tr("lbl_brush_panel"))
        lbl.setObjectName("section")
        lay.addWidget(lbl)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.mono_buttons = []
        for ch in self.MONO:
            b = QToolButton()
            b.setObjectName("glyph")
            b.setText(ch)
            b.setCheckable(True)
            b.setFixedSize(26, 24)
            b.setFocusPolicy(Qt.NoFocus)
            b.setToolTip(tr("tt_brush_mono", ch=ch))
            self.group.addButton(b)
            self.mono_buttons.append(b)
            lay.addWidget(b)
        self.custom_edit = QLineEdit()
        self.custom_edit.setMaxLength(1)
        self.custom_edit.setFixedWidth(34)
        self.custom_edit.setAlignment(Qt.AlignCenter)
        self.custom_edit.setPlaceholderText("…")
        self.custom_edit.setToolTip(tr("tt_brush_custom"))
        lay.addWidget(self.custom_edit)
        self.erase_btn = QToolButton()
        self.erase_btn.setText(tr("btn_brush_erase"))
        self.erase_btn.setCheckable(True)
        self.erase_btn.setFocusPolicy(Qt.NoFocus)
        self.erase_btn.setToolTip(tr("tt_brush_erase"))
        self.group.addButton(self.erase_btn)
        lay.addWidget(self.erase_btn)
        lay.addSpacing(10)
        sym = QLabel(tr("lbl_symmetry"))
        sym.setObjectName("section")
        lay.addWidget(sym)
        self.sym_combo = QComboBox()
        for key, label in (("", "sym_off"), (mirror.H, "sym_h"), (mirror.V, "sym_v"), (mirror.HV, "sym_hv")):
            self.sym_combo.addItem(tr(label), key)
        self.sym_combo.setToolTip(tr("tt_symmetry"))
        lay.addWidget(self.sym_combo)
        lay.addStretch()
        self.mono_buttons[0].setChecked(True)
        self.group.buttonToggled.connect(self._on_toggled)
        self.custom_edit.textEdited.connect(self._on_custom)
        self.sym_combo.currentIndexChanged.connect(lambda _i: self.symmetry_changed.emit(self.sym_combo.currentData()))

    def current_char(self) -> str:
        b = self.group.checkedButton()
        if b is self.erase_btn:
            return " "
        if b is None:
            return self.custom_edit.text() or "█"
        return b.text()

    def set_char(self, ch: str) -> None:
        for b in self.mono_buttons:
            if b.text() == ch:
                b.setChecked(True)
                return
        self.group.setExclusive(False)
        for b in self.group.buttons():
            b.setChecked(False)
        self.group.setExclusive(True)
        self.custom_edit.setText(ch)
        self.char_changed.emit(ch)

    def select_eraser(self) -> None:
        self.erase_btn.setChecked(True)

    def cycle_symmetry(self) -> None:
        self.sym_combo.setCurrentIndex((self.sym_combo.currentIndex() + 1) % self.sym_combo.count())

    def _on_toggled(self, btn, checked):
        if checked:
            self.char_changed.emit(self.current_char())

    def _on_custom(self, text: str) -> None:
        if text:
            self.set_char(text)


COLOR_PALETTE = ("ffffff", "a1a1aa", "ef4444", "f97316", "facc15", "22c55e", "38bdf8", "a855f7", "f472b6")


class ColorBar(QWidget):
    """Кольорові теги <color:RRGGBB>…</color> для виділення в полотні."""
    color_chosen = Signal(str)
    clear_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(3)
        lbl = QLabel(tr("lbl_text_color_tag"))
        lbl.setObjectName("section")
        lay.addWidget(lbl)
        for hex_col in COLOR_PALETTE:
            b = QToolButton()
            b.setText("■")
            b.setFixedSize(22, 22)
            b.setFocusPolicy(Qt.NoFocus)
            b.setToolTip(f"#{hex_col}")
            b.setStyleSheet(f"QToolButton {{ background: #{hex_col}; color: {contrast_text(hex_col)}; border: 1px solid {THEME['border']}; border-radius: 3px; }}"
                            f"QToolButton:hover {{ border: 2px solid {THEME['accent']}; }}")
            b.clicked.connect(lambda _=False, h=hex_col: self.color_chosen.emit(h))
            lay.addWidget(b)
        custom = QToolButton()
        custom.setText("🎨")
        custom.setFocusPolicy(Qt.NoFocus)
        custom.setToolTip(tr("tt_color_custom"))
        custom.clicked.connect(self._pick)
        lay.addWidget(custom)
        clear = QToolButton()
        clear.setText("✕")
        clear.setFocusPolicy(Qt.NoFocus)
        clear.setToolTip(tr("tt_color_clear"))
        clear.clicked.connect(self.clear_requested.emit)
        lay.addWidget(clear)
        lay.addStretch()

    def _pick(self) -> None:
        col = QColorDialog.getColor(QColor("#ffffff"), self, tr("dlg_pick_color"))
        if col.isValid():
            self.color_chosen.emit(col.name().lstrip("#"))


def framed(widget: QWidget, layout_cls=QHBoxLayout):
    frame, lay = panel(layout_cls, margins=(2, 2, 2, 2))
    lay.addWidget(widget)
    return frame


def braille_bar(on_insert) -> QWidget:
    host = QWidget()
    lay = QHBoxLayout(host)
    lay.setContentsMargins(6, 0, 6, 0)
    lbl = QLabel(tr("lbl_braille"))
    lbl.setObjectName("section")
    lay.addWidget(lbl)
    host.picker = BraillePickerWidget(host, on_insert=on_insert, compact=True)
    lay.addWidget(host.picker, 1)
    return host
