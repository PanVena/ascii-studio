"""Єдиний реєстр гарячих клавіш студії.

Кожна дія описана один раз (id, типові клавіші, область, група). Звідси беруться
QAction-и головного вікна, від'єднаних вікон, дзеркала і кожного полотна; меню,
підказки, довідка (F1) та редактор клавіш. Перевизначення користувача
зберігаються в налаштуваннях і застосовуються одразу до всіх прив'язаних дій.

Області:
  * "app"    — діють у будь-якому вікні студії (Qt.WindowShortcut);
  * "canvas" — лише коли фокус у полотні (Qt.WidgetShortcut на кожному редакторі),
               тож Tab/Shift+Space тощо не заважають іншим полям.
Полотно відмовляється від ShortcutOverride для всіх зареєстрованих комбінацій,
тому вбудовані прив'язки QPlainTextEdit (на деяких платформах Ctrl+E/Ctrl+K…)
не «крадуть» клавіші студії. Розкладка (кирилиця тощо) обробляється самим Qt.
"""
from __future__ import annotations

import weakref
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import QEvent, QKeyCombination, QObject, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence

from .i18n import tr

APP = "app"
CANVAS = "canvas"

GROUPS = ("file", "edit", "block", "tools", "view", "layers", "help")


@dataclass(frozen=True)
class Spec:
    id: str
    keys: Tuple[str, ...]
    scope: str
    group: str

    @property
    def label(self) -> str:
        return tr("act_" + self.id.replace(".", "_"))


def _s(id_: str, keys, scope: str = APP) -> Spec:
    if isinstance(keys, str):
        keys = (keys,) if keys else ()
    return Spec(id_, tuple(keys), scope, id_.split(".")[0])


SPECS: List[Spec] = [
    _s("file.new", "Ctrl+N"),
    _s("file.new_sized", "Ctrl+Shift+N"),
    _s("file.open", "Ctrl+O"),
    _s("file.open_path", "Ctrl+Shift+O"),
    _s("file.save", "Ctrl+S"),
    _s("file.save_to_dir", "Ctrl+Shift+S"),
    _s("file.export", "Ctrl+Alt+S"),
    _s("file.close_tab", "Ctrl+W"),
    _s("file.quit", "Ctrl+Q"),

    _s("edit.copy_art", "Ctrl+Alt+C"),
    _s("edit.duplicate", "Ctrl+D"),
    _s("edit.import_figlet", "Ctrl+I"),
    _s("edit.pad", "Ctrl+Alt+P"),
    _s("edit.trim", "Ctrl+Shift+T"),
    _s("edit.clear", ""),
    _s("edit.flip_h", "Ctrl+Alt+H"),
    _s("edit.flip_v", "Ctrl+Alt+V"),
    _s("edit.rotate", "Ctrl+Alt+R"),

    _s("block.indent", "Tab", CANVAS),
    _s("block.unindent", "Shift+Tab", CANVAS),
    _s("block.col_insert", "Shift+Space", CANVAS),
    _s("block.col_delete", "Shift+Del", CANVAS),
    _s("block.col_backspace", "Shift+Backspace", CANVAS),
    _s("block.copy", "Ctrl+Shift+C", CANVAS),
    _s("block.cut", "Ctrl+Shift+X", CANVAS),
    _s("block.paste", "Ctrl+Shift+V", CANVAS),
    _s("block.paste_transparent", "Ctrl+Alt+Shift+V", CANVAS),
    _s("block.clear", "Ctrl+Shift+Del", CANVAS),
    _s("block.overwrite", "Ins", CANVAS),
    *[_s(f"block.palette_{i}", f"Alt+{i}", CANVAS) for i in range(1, 10)],

    _s("tools.brush", "Ctrl+B"),
    _s("tools.eraser", "Ctrl+Shift+E"),
    _s("tools.symmetry", "Ctrl+M"),
    _s("tools.braille", "Ctrl+Shift+B"),
    _s("tools.colors", "Ctrl+Shift+K"),
    _s("tools.chars", "Ctrl+Shift+J"),

    _s("view.mode_figlet", "Ctrl+1"),
    _s("view.mode_fonts", "Ctrl+2"),
    _s("view.mode_canvas", "Ctrl+3"),
    _s("view.layers", "Ctrl+L"),
    _s("view.split", "Ctrl+\\"),
    _s("view.detach", "Ctrl+Shift+D"),
    _s("view.mirror", "F4"),
    _s("view.game_fit", "F5"),
    _s("view.color_preview", "F6"),
    _s("view.animation", "F7"),
    _s("view.zoom_in", ("Ctrl+=", "Ctrl++")),
    _s("view.zoom_out", "Ctrl+-"),
    _s("view.zoom_reset", "Ctrl+0"),
    _s("view.next_tab", ("Ctrl+Tab", "Ctrl+PgDown")),
    _s("view.prev_tab", ("Ctrl+Shift+Tab", "Ctrl+PgUp")),

    _s("layers.add", "Ctrl+Shift+L"),
    _s("layers.up", "Alt+PgUp"),
    _s("layers.down", "Alt+PgDown"),

    _s("help.shortcuts", "F1"),
]
BY_ID: Dict[str, Spec] = {s.id: s for s in SPECS}

_PROTECTED = {QKeySequence(k).toString() for k in (
    "Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+Z", "Ctrl+Y", "Ctrl+Shift+Z", "Ctrl+A",
    "Shift+Ins", "Ctrl+Ins", "Left", "Right", "Up", "Down", "Home", "End", "Return",
    "Enter", "Backspace", "Del", "Space", "Esc",
)}


def normalize(text: str) -> str:
    """Портативний текст однієї комбінації ('' — некоректна/порожня)."""
    seq = QKeySequence(text)
    if seq.isEmpty() or seq.count() != 1:
        return ""
    return seq.toString(QKeySequence.PortableText)


def event_combination(event) -> str:
    """Портативний текст комбінації з QKeyEvent (Backtab → Shift+Tab, без Keypad)."""
    key = event.key()
    if key in (Qt.Key_unknown, 0, Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr):
        return ""
    mods = event.modifiers() & ~Qt.KeypadModifier
    if key == Qt.Key_Backtab:
        key = Qt.Key_Tab
        mods |= Qt.ShiftModifier
    return QKeySequence(QKeyCombination(mods, Qt.Key(key))).toString(QKeySequence.PortableText)


class ShortcutManager(QObject):
    """Поточні клавіші (типові + перевизначення) і всі прив'язані до них QAction."""
    changed = Signal()

    def __init__(self, overrides: Optional[Dict[str, str]] = None):
        super().__init__()
        self._overrides: Dict[str, Tuple[str, ...]] = {}
        self._bound: Dict[str, "weakref.WeakSet[QAction]"] = {}
        self._index: Dict[str, str] = {}
        self.set_overrides(overrides or {})

    @staticmethod
    def _parse(value: str) -> Tuple[str, ...]:
        parts = [normalize(p) for p in value.split(";")] if value else []
        return tuple(p for p in parts if p)

    def set_overrides(self, overrides: Dict[str, str]) -> None:
        self._overrides = {k: self._parse(v) for k, v in overrides.items() if k in BY_ID}
        self._rebuild()

    def overrides_as_text(self) -> Dict[str, str]:
        return {k: ";".join(v) for k, v in self._overrides.items()}

    def keys(self, id_: str) -> Tuple[str, ...]:
        if id_ in self._overrides:
            return self._overrides[id_]
        return tuple(normalize(k) for k in BY_ID[id_].keys if normalize(k))

    def set_keys(self, id_: str, keys: Iterable[str]) -> None:
        keys = tuple(k for k in (normalize(k) for k in keys) if k)
        default = tuple(normalize(k) for k in BY_ID[id_].keys if normalize(k))
        if keys == default:
            self._overrides.pop(id_, None)
        else:
            self._overrides[id_] = keys
        self._rebuild()

    def reset(self, id_: Optional[str] = None) -> None:
        if id_ is None:
            self._overrides.clear()
        else:
            self._overrides.pop(id_, None)
        self._rebuild()

    def display(self, id_: str) -> str:
        """Перша комбінація у вигляді для людей (порожньо — без клавіші)."""
        keys = self.keys(id_)
        return QKeySequence(keys[0]).toString(QKeySequence.NativeText) if keys else ""

    def conflicts(self) -> Dict[str, List[str]]:
        """Комбінація → кілька дій, що конфліктують (з урахуванням областей)."""
        seen: Dict[str, List[str]] = {}
        for spec in SPECS:
            for k in self.keys(spec.id):
                seen.setdefault(k, []).append(spec.id)
        return {k: ids for k, ids in seen.items() if len(ids) > 1}

    def action_for(self, combination: str) -> Optional[str]:
        return self._index.get(combination)

    def wants(self, event) -> bool:
        """Чи має полотно віддати цю клавішу шорткату студії (замість власної прив'язки)."""
        combo = event_combination(event)
        return bool(combo) and combo in self._index and QKeySequence(combo).toString() not in _PROTECTED

    def bind(self, action: QAction, id_: str) -> QAction:
        spec = BY_ID[id_]
        action.setShortcutContext(Qt.WidgetShortcut if spec.scope == CANVAS else Qt.WindowShortcut)
        action.setProperty("shortcut_id", id_)
        self._bound.setdefault(id_, weakref.WeakSet()).add(action)
        self._apply(action, id_)
        return action

    def make_action(self, id_: str, parent: QObject, slot=None, checkable: bool = False, text: str | None = None) -> QAction:
        act = QAction(text if text is not None else BY_ID[id_].label, parent)
        act.setCheckable(checkable)
        if slot is not None:
            act.triggered.connect(slot)
        return self.bind(act, id_)

    def _apply(self, action: QAction, id_: str) -> None:
        try:
            action.setShortcuts([QKeySequence(k) for k in self.keys(id_)])
            tip = action.text().replace("&", "")
            key = self.display(id_)
            action.setToolTip(f"{tip} ({key})" if key else tip)
        except RuntimeError:
            pass

    def _rebuild(self) -> None:
        self._index = {}
        for spec in SPECS:
            for k in self.keys(spec.id):
                self._index.setdefault(k, spec.id)
        for id_, actions in self._bound.items():
            for act in list(actions):
                self._apply(act, id_)
        self.changed.emit()


class CanvasShortcutFilter:
    """Міксин для полотна: віддає зареєстровані комбінації шорткатам студії."""

    def event(self, e):
        if e.type() == QEvent.ShortcutOverride and manager().wants(e):
            e.ignore()
            return True
        return super().event(e)


_manager: Optional[ShortcutManager] = None


def manager() -> ShortcutManager:
    global _manager
    if _manager is None:
        try:
            from . import settings
            overrides = settings.get().shortcut_overrides()
        except Exception:
            overrides = {}
        _manager = ShortcutManager(overrides)
    return _manager


def reset_manager() -> None:
    global _manager
    _manager = None
