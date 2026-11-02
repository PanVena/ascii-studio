"""Полотно ASCII: QPlainTextEdit з номерами рядків, шарами-привидами, кистю, симетрією та
прямокутними операціями. Позиції Qt рахуються в UTF-16, колонки полотна — у символах;
перетворення — `_u16`/`_cp`, тож емодзі та інші не-BMP символи не зсувають клітинки."""
from __future__ import annotations

import math
from typing import List, Optional

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QWidget

from .. import shortcuts
from ..core import mirror, textgrid
from ..core.layers import CanvasLayers, Layer, compose
from ..core.textgrid import Rect
from ..i18n import tr
from ..theme import THEME, canvas_style, mix, mono_font

DEFAULT_POINT_SIZE = 12.0
MIN_POINT_SIZE = 4.0
MAX_POINT_SIZE = 72.0


def _u16(text: str, cp: int) -> int:
    """Індекс у символах → зсув у UTF-16 (як рахує Qt)."""
    head = text[:cp]
    return len(head) + sum(1 for ch in head if ord(ch) > 0xFFFF)


def _cp(text: str, u16: int) -> int:
    """Зсув UTF-16 → індекс у символах."""
    n = 0
    for i, ch in enumerate(text):
        if n >= u16:
            return i
        n += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


class CanvasTools(QObject):
    """Спільний стан інструментів для всіх полотен (кисть, символ, симетрія, палітра)."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.brush = False
        self.brush_char = "█"
        self.symmetry = ""
        self.palette = ""
        self.guide_col = 80
        self.bg = THEME["bg"]
        self.fg = THEME["success"]
        self.context_actions: list = []

    def update(self, **kw) -> None:
        changed = False
        for k, v in kw.items():
            if getattr(self, k) != v:
                setattr(self, k, v)
                changed = True
        if changed:
            self.changed.emit()

    @property
    def ghost_color(self) -> QColor:
        return mix(self.bg, self.fg, 0.32)


class LineNumbers(QWidget):
    """Смуга номерів рядків; рядки, довші за напрямну, підсвічуються «N+»."""

    def __init__(self, editor: "CanvasEditor"):
        super().__init__(editor)
        self._editor = editor

    def calc_width(self) -> int:
        digits = max(2, len(str(max(1, self._editor.blockCount()))))
        fm = self._editor.fontMetrics()
        return fm.horizontalAdvance("9") * digits + fm.horizontalAdvance("+") + 10

    def sizeHint(self):
        return QSize(self.calc_width(), 0)

    def paintEvent(self, event):
        ed = self._editor
        p = QPainter(self)
        p.setFont(ed.font())
        p.fillRect(event.rect(), QColor(THEME["bg_panel"]))
        p.setPen(QPen(QColor(THEME["border"]), 1))
        p.drawLine(self.width() - 1, event.rect().top(), self.width() - 1, event.rect().bottom())
        block = ed.firstVisibleBlock()
        top = int(ed.blockBoundingGeometry(block).translated(ed.contentOffset()).top())
        bottom = top + int(ed.blockBoundingRect(block).height())
        current = ed.textCursor().blockNumber()
        limit = ed.tools.guide_col if ed.tools.guide_col > 0 else 10 ** 9
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                num = block.blockNumber()
                h = bottom - top
                if len(block.text()) > limit:
                    p.fillRect(0, top, self.width() - 1, h, QColor(THEME["accent_dim"]))
                    p.setPen(QColor(THEME["accent_light"]))
                    txt = f"{num + 1}+"
                else:
                    p.setPen(QColor(THEME["accent_light"] if num == current else THEME["text_dim"]))
                    txt = str(num + 1)
                p.drawText(0, top, self.width() - 5, h, Qt.AlignRight | Qt.AlignVCenter, txt)
            block = block.next()
            top = bottom
            bottom = top + int(ed.blockBoundingRect(block).height())
        p.end()


_BLOCK_SLOTS = {
    "block.indent": "indent",
    "block.unindent": "unindent",
    "block.col_insert": "col_insert",
    "block.col_delete": "col_delete",
    "block.col_backspace": "col_backspace",
    "block.copy": "block_copy",
    "block.cut": "block_cut",
    "block.paste": "block_paste",
    "block.paste_transparent": "block_paste_transparent",
    "block.clear": "block_clear",
    "block.overwrite": "toggle_overwrite",
}


class CanvasEditor(shortcuts.CanvasShortcutFilter, QPlainTextEdit):
    """Одне полотно (вкладка): стек шарів, активний шар редагується в полі."""
    focused = Signal()
    zoom_changed = Signal(float)
    dirty_changed = Signal(bool)
    layers_changed = Signal()
    message = Signal(str)

    def __init__(self, tools: CanvasTools, title: str = "", stack: Optional[CanvasLayers] = None,
                 active_idx: int = 0, file_path: str = "", parent=None):
        super().__init__(parent)
        self.tools = tools
        self.title = title or tr("canvas_default")
        self.file_path = file_path
        self._dirty = False
        self._loading = False
        self._painting = False
        self._last_cell = None
        self._stroke_dims = (0, 0)
        self._stroke_cursor: Optional[QTextCursor] = None
        self._underlay = ""
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont(mono_font(DEFAULT_POINT_SIZE))
        self.setPlaceholderText(tr("placeholder_canvas"))
        self.setCursorWidth(2)
        self._nums = LineNumbers(self)
        self.blockCountChanged.connect(self._sync_margins)
        self.updateRequest.connect(self._on_update_request)
        self.cursorPositionChanged.connect(self._nums.update)
        self.textChanged.connect(self._on_text_changed)
        tools.changed.connect(self._on_tools_changed)
        self.layers = stack if stack is not None and stack.count else CanvasLayers([Layer(name=self.title, text="")])
        idx = active_idx if 0 <= active_idx < self.layers.count else 0
        self.active_layer = self.layers.get(idx)
        self._load_text(self.active_layer.text)
        self._make_actions()
        self._on_tools_changed()
        self._sync_margins()

    # ── стан ────────────────────────────────────────────────────────────────

    @property
    def dirty(self) -> bool:
        return self._dirty

    def set_dirty(self, value: bool = True) -> None:
        if self._dirty != value:
            self._dirty = value
            self.dirty_changed.emit(value)

    def mark_clean(self) -> None:
        self.set_dirty(False)

    def _load_text(self, text: str) -> None:
        self._loading = True
        try:
            self.setPlainText(text)
        finally:
            self._loading = False
        self._refresh_underlay()

    def _on_text_changed(self) -> None:
        if self._loading:
            return
        if self.active_layer is not None:
            self.active_layer.text = self.toPlainText()
        self.set_dirty(True)
        self.layers_changed.emit()

    def composite_text(self) -> str:
        return self.layers.composite_text()

    def lines(self) -> List[str]:
        return self.toPlainText().split("\n")

    def grid_size(self) -> tuple[int, int]:
        lines = self.lines()
        return len(lines), textgrid.max_width(lines)

    def _on_tools_changed(self) -> None:
        self.setStyleSheet(canvas_style(self.tools.bg, self.tools.fg))
        if self.tools.brush != getattr(self, "_brush_active", None):
            self._end_stroke()
            self._brush_active = self.tools.brush
            self.viewport().setCursor(Qt.CrossCursor if self.tools.brush else Qt.IBeamCursor)
        self.viewport().update()
        self._nums.update()

    # ── шари ────────────────────────────────────────────────────────────────

    def switch_layer(self, layer: Layer) -> None:
        if layer is self.active_layer or layer not in self.layers.layers:
            return
        self.active_layer.text = self.toPlainText()
        self.active_layer = layer
        self._load_text(layer.text)
        self.layers_changed.emit()

    def add_layer(self, name: str) -> Layer:
        self.active_layer.text = self.toPlainText()
        idx = self.layers.layers.index(self.active_layer) + 1
        layer = self.layers.add_layer(name, idx)
        self.active_layer = layer
        self._load_text("")
        self.set_dirty(True)
        self.layers_changed.emit()
        return layer

    def remove_layer(self, layer: Layer) -> None:
        if layer not in self.layers.layers:
            return
        idx = self.layers.layers.index(layer)
        self.layers.remove_layer(idx)
        if not self.layers.count:
            self.layers.add_layer(tr("layer_new"))
        if layer is self.active_layer:
            self.active_layer = self.layers.get(min(idx, self.layers.count - 1))
            self._load_text(self.active_layer.text)
        self.set_dirty(True)
        self.layers_changed.emit()

    def move_layer(self, layer: Layer, delta: int) -> None:
        if layer in self.layers.layers:
            self.layers.move(self.layers.layers.index(layer), delta)
            self.set_dirty(True)
            self.layers_changed.emit()
            self._refresh_underlay()

    def set_layer_visible(self, layer: Layer, visible: bool) -> None:
        if layer in self.layers.layers and layer.visible != visible:
            layer.visible = visible
            self.set_dirty(True)
            self.layers_changed.emit()
            self._refresh_underlay()

    def rename_layer(self, layer: Layer, name: str) -> None:
        if layer in self.layers.layers and name and layer.name != name:
            layer.name = name
            self.set_dirty(True)
            self.layers_changed.emit()

    def active_index(self) -> int:
        return self.layers.layers.index(self.active_layer)

    def _refresh_underlay(self) -> None:
        texts = [l.text for l in self.layers.layers if l.visible and l is not self.active_layer] if self.layers.count > 1 else []
        text = compose(texts) if texts else ""
        if text != self._underlay:
            self._underlay = text
            # Підказка порожнього полотна інакше лягає поверх привида нижніх шарів.
            self.setPlaceholderText("" if text else tr("placeholder_canvas"))
            self.viewport().update()

    @property
    def underlay_text(self) -> str:
        return self._underlay

    # ── малювання ───────────────────────────────────────────────────────────

    def _advance(self) -> float:
        return max(1.0, self.fontMetrics().horizontalAdvance("M"))

    def _line_height(self) -> float:
        h = self.document().begin().layout().boundingRect().height()
        return h if h > 0 else float(self.fontMetrics().lineSpacing())

    def _origin(self) -> QPoint:
        """Верхній лівий кут клітинки (0, 0) у координатах viewport."""
        c = QTextCursor(self.document())
        c.setPosition(0)
        r = self.cursorRect(c)
        top = self.blockBoundingGeometry(self.document().begin()).translated(self.contentOffset()).top()
        return QPoint(r.left(), int(top))

    def paintEvent(self, event):
        p = QPainter(self.viewport())
        o = self._origin()
        adv, lh = self._advance(), self._line_height()
        if self._underlay:
            fm = self.fontMetrics()
            p.setPen(QPen(self.tools.ghost_color))
            lines = self._underlay.split("\n")
            i0 = max(0, int(math.floor(-o.y() / lh)) - 1)
            i1 = min(len(lines), int(math.ceil((self.viewport().height() - o.y()) / lh)) + 1)
            for i in range(i0, i1):
                p.drawText(o.x(), int(o.y() + i * lh + fm.ascent()), lines[i])
        if self.tools.guide_col > 0:
            x = int(o.x() + self.tools.guide_col * adv)
            p.setPen(QPen(QColor(THEME["border"]), 1, Qt.DashLine))
            p.drawLine(x, 0, x, self.viewport().height())
        if self.tools.brush and self.tools.symmetry:
            rows, cols = self._stroke_dims if self._painting else self.grid_size()
            pen = QPen(QColor(THEME["accent"]), 1, Qt.DashDotLine)
            p.setPen(pen)
            if self.tools.symmetry in (mirror.H, mirror.HV) and cols:
                x = int(o.x() + cols * adv / 2)
                p.drawLine(x, 0, x, self.viewport().height())
            if self.tools.symmetry in (mirror.V, mirror.HV) and rows:
                y = int(o.y() + rows * lh / 2)
                p.drawLine(0, y, self.viewport().width(), y)
        p.end()
        super().paintEvent(event)

    def cell_at(self, pos: QPoint) -> tuple[int, int]:
        """Клітинка під точкою viewport; праворуч від тексту й нижче за останній рядок — теж (полотно розшириться)."""
        o = self._origin()
        row = int(math.floor((pos.y() - o.y()) / self._line_height()))
        col = int(math.floor((pos.x() - o.x()) / self._advance()))
        return max(0, row), max(0, col)

    def _paint_cell(self, row: int, col: int, ch: str) -> None:
        doc = self.document()
        cur = self._stroke_cursor or QTextCursor(doc)
        while doc.blockCount() <= row:
            if ch == " ":
                return
            cur.movePosition(QTextCursor.End)
            cur.insertText("\n")
        block = doc.findBlockByNumber(row)
        text = block.text()
        if col >= len(text):
            if ch == " ":
                return
            cur.setPosition(block.position() + _u16(text, len(text)))
            cur.insertText(" " * (col - len(text)) + ch)
            return
        if text[col] == ch:
            return
        pos = block.position() + _u16(text, col)
        cur.setPosition(pos)
        cur.setPosition(pos + _u16(text[col], 1), QTextCursor.KeepAnchor)
        cur.insertText(ch)

    def _stamp(self, row: int, col: int) -> None:
        ch = self.tools.brush_char
        self._paint_cell(row, col, ch)
        rows, cols = self._stroke_dims
        for r, c, axis in textgrid.symmetric_cells(row, col, rows, cols, self.tools.symmetry):
            self._paint_cell(r, c, mirror.mirror_char(ch, axis))

    @staticmethod
    def cells_between(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
        """Клітинки від a (не включно) до b (включно) — без пропусків."""
        cells = []
        r, c = a
        r1, c1 = b
        while (r, c) != (r1, c1):
            dr, dc = r1 - r, c1 - c
            if abs(dr) >= abs(dc):
                r += 1 if dr > 0 else -1
            else:
                c += 1 if dc > 0 else -1
            cells.append((r, c))
        return cells

    def _begin_stroke(self) -> None:
        self._painting = True
        self._stroke_dims = self.grid_size()
        self._stroke_cursor = QTextCursor(self.document())
        self._stroke_cursor.beginEditBlock()

    def _end_stroke(self) -> None:
        if self._stroke_cursor is not None:
            self._stroke_cursor.endEditBlock()
            self._stroke_cursor = None
        self._painting = False
        self._last_cell = None

    def mousePressEvent(self, event):
        if self.tools.brush and event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            cell = self.cell_at(event.position().toPoint())
            self._begin_stroke()
            self._stamp(*cell)
            self._last_cell = cell
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.tools.brush and (event.buttons() & Qt.LeftButton):
            if self._painting:
                cell = self.cell_at(event.position().toPoint())
                if cell != self._last_cell:
                    for r, c in self.cells_between(self._last_cell, cell):
                        self._stamp(r, c)
                    self._last_cell = cell
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.tools.brush and event.button() == Qt.LeftButton:
            if self._painting:
                cell = self.cell_at(event.position().toPoint())
                if cell != self._last_cell:
                    for r, c in self.cells_between(self._last_cell, cell):
                        self._stamp(r, c)
                self._end_stroke()
                self.viewport().update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.tools.brush and event.button() == Qt.LeftButton:
            self.setTextCursor(self.cursorForPosition(event.position().toPoint()))
            return
        super().mouseDoubleClickEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused.emit()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y() or event.pixelDelta().y()
            if delta:
                self.zoom_by(1 if delta > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)

    def zoom_by(self, steps: float) -> None:
        self.set_point_size(self.font().pointSizeF() + steps)

    def set_point_size(self, pt: float) -> None:
        pt = max(MIN_POINT_SIZE, min(MAX_POINT_SIZE, float(pt)))
        f = self.font()
        if abs(f.pointSizeF() - pt) > 0.01:
            f.setPointSizeF(pt)
            self.setFont(f)
            self._sync_margins()
            self.zoom_changed.emit(pt)

    # ── прямокутні операції ─────────────────────────────────────────────────

    def _row_col(self, pos: int) -> tuple[int, int]:
        block = self.document().findBlock(pos)
        return block.blockNumber(), _cp(block.text(), pos - block.position())

    def cursor_cell(self) -> tuple[int, int]:
        return self._row_col(self.textCursor().position())

    def selection_rect(self, full_rows_if_empty: bool = False) -> Optional[Rect]:
        """Прямокутник виділення (колонки між кінцями). Порожня ширина → цілі рядки, якщо full_rows_if_empty."""
        cur = self.textCursor()
        if not cur.hasSelection():
            return None
        r0, ca = self._row_col(cur.selectionStart())
        r1, cb = self._row_col(cur.selectionEnd())
        lines = self.lines()
        if r1 > r0 and cb == 0 and ca == 0:
            r1 -= 1
            ca, cb = 0, 0
        elif r1 > r0 and ca == 0 and cb >= len(lines[r1]):
            ca, cb = 0, 0
        c0, c1 = min(ca, cb), max(ca, cb)
        if c0 == c1:
            if not full_rows_if_empty:
                return None
            c0, c1 = 0, max(1, textgrid.max_width(lines[r0:r1 + 1]))
        return Rect(r0, r1, c0, c1)

    def set_lines(self, new_lines: List[str], select: Optional[Rect] = None, cursor: Optional[tuple[int, int]] = None) -> None:
        """Замінює текст мінімальним фрагментом (один крок undo, прокрутка не стрибає)."""
        old = self.toPlainText()
        new = "\n".join(new_lines)
        if old == new:
            if select is not None or cursor is not None:
                self._restore(select, cursor)
            return
        p = 0
        n = min(len(old), len(new))
        while p < n and old[p] == new[p]:
            p += 1
        s = 0
        while s < n - p and old[len(old) - 1 - s] == new[len(new) - 1 - s]:
            s += 1
        cur = QTextCursor(self.document())
        cur.beginEditBlock()
        cur.setPosition(_u16(old, p))
        cur.setPosition(_u16(old, len(old) - s), QTextCursor.KeepAnchor)
        cur.insertText(new[p:len(new) - s])
        cur.endEditBlock()
        self._restore(select, cursor)

    def _pos_of(self, row: int, col: int) -> int:
        doc = self.document()
        block = doc.findBlockByNumber(min(row, doc.blockCount() - 1))
        text = block.text()
        return block.position() + _u16(text, min(col, len(text)))

    def _restore(self, select: Optional[Rect], cursor: Optional[tuple[int, int]]) -> None:
        cur = self.textCursor()
        if select is not None:
            cur.setPosition(self._pos_of(select.r0, select.c0))
            cur.setPosition(self._pos_of(select.r1, select.c1), QTextCursor.KeepAnchor)
        elif cursor is not None:
            cur.setPosition(self._pos_of(*cursor))
        self.setTextCursor(cur)

    def _col_selection(self) -> Optional[tuple[int, int, int]]:
        cur = self.textCursor()
        if not cur.hasSelection():
            return None
        r0, col = self._row_col(cur.selectionStart())
        r1, _ = self._row_col(cur.selectionEnd())
        return r0, r1, col

    def _restore_cols(self, r0: int, r1: int, col: int) -> None:
        self._restore(Rect(r0, r1, col, col), None)

    def indent(self) -> None:
        cur = self.textCursor()
        if not cur.hasSelection():
            cur.insertText("    ")
            return
        r0, r1, _ = self._col_selection()
        r_end, c_end = self._row_col(cur.selectionEnd())
        if c_end == 0 and r1 > r0:
            r1 -= 1
        a, b = self._row_col(cur.selectionStart()), (r_end, c_end)
        self.set_lines(textgrid.indent(self.lines(), r0, r1))
        cur = self.textCursor()
        cur.setPosition(self._pos_of(a[0], a[1] + 4))
        cur.setPosition(self._pos_of(b[0], b[1] + (4 if b[0] <= r1 else 0)), QTextCursor.KeepAnchor)
        self.setTextCursor(cur)

    def unindent(self) -> None:
        cur = self.textCursor()
        if cur.hasSelection():
            (r0, ca), (r1, cb) = self._row_col(cur.selectionStart()), self._row_col(cur.selectionEnd())
            last = r1 - 1 if cb == 0 and r1 > r0 else r1
        else:
            (r0, ca) = (r1, cb) = self.cursor_cell()
            last = r0
        lines, removed = textgrid.unindent(self.lines(), r0, last)
        self.set_lines(lines)
        cur = self.textCursor()
        cur.setPosition(self._pos_of(r0, max(0, ca - removed[0])))
        if (r0, ca) != (r1, cb):
            dr = removed[r1 - r0] if r1 - r0 < len(removed) else 0
            cur.setPosition(self._pos_of(r1, max(0, cb - dr)), QTextCursor.KeepAnchor)
        self.setTextCursor(cur)

    def col_insert(self) -> None:
        sel = self._col_selection()
        if sel is None:
            self.textCursor().insertText(" ")
            return
        r0, r1, col = sel
        self.set_lines(textgrid.insert_column(self.lines(), r0, r1, col))
        self._restore_cols(r0, r1, col + 1)

    def col_delete(self) -> None:
        sel = self._col_selection()
        if sel is None:
            return
        r0, r1, col = sel
        self.set_lines(textgrid.delete_column(self.lines(), r0, r1, col))
        self._restore_cols(r0, r1, col)

    def col_backspace(self) -> None:
        sel = self._col_selection()
        if sel is None or sel[2] == 0:
            return
        r0, r1, col = sel
        self.set_lines(textgrid.delete_column(self.lines(), r0, r1, col - 1))
        self._restore_cols(r0, r1, col - 1)

    def block_copy(self) -> bool:
        rect = self.selection_rect(full_rows_if_empty=True)
        if rect is None:
            self.message.emit(tr("msg_need_rect"))
            return False
        QApplication.clipboard().setText("\n".join(textgrid.read_rect(self.lines(), rect)))
        return True

    def block_clear(self) -> None:
        rect = self.selection_rect(full_rows_if_empty=True)
        if rect is not None:
            self.set_lines(textgrid.clear_rect(self.lines(), rect), select=rect)

    def block_cut(self) -> None:
        if self.block_copy():
            self.block_clear()

    def _paste(self, transparent: bool) -> None:
        text = QApplication.clipboard().text().replace("\r\n", "\n")
        if not text:
            return
        block = text.split("\n")
        if block and block[-1] == "":
            block = block[:-1]
        if not block:
            return
        cur = self.textCursor()
        r0, c0 = self._row_col(cur.selectionStart() if cur.hasSelection() else cur.position())
        self.set_lines(textgrid.write_rect(self.lines(), r0, c0, block, transparent=transparent),
                       cursor=(r0 + len(block) - 1, c0 + len(block[-1])))

    def block_paste(self) -> None:
        self._paste(False)

    def block_paste_transparent(self) -> None:
        self._paste(True)

    def toggle_overwrite(self) -> None:
        self.setOverwriteMode(not self.overwriteMode())
        self.message.emit(tr("status_overwrite_on") if self.overwriteMode() else tr("status_overwrite_off"))

    def insert_palette(self, index: int) -> None:
        chars = self.tools.palette
        if 0 <= index < len(chars):
            self.insertPlainText(chars[index])

    def flip(self, axis: str) -> None:
        """Перевертає виділений прямокутник або весь шар; розмітка зберігається для цілих рядків."""
        lines = self.lines()
        rect = self.selection_rect(full_rows_if_empty=True)
        whole = rect is None
        if whole:
            rect = Rect(0, len(lines) - 1, 0, max(1, textgrid.max_width(lines)))
        region_rows = lines[rect.r0:rect.r1 + 1]
        has_markup = any(mirror.plain_text(l) != l for l in region_rows)
        if has_markup:
            full_width = rect.c0 == 0 and rect.c1 >= textgrid.max_width(region_rows)
            if not full_width:
                self.message.emit(tr("msg_flip_markup_partial"))
                return
            flipped = mirror.flip_text("\n".join(region_rows), axis).split("\n")
            new = lines[:rect.r0] + flipped + lines[rect.r1 + 1:]
        else:
            new = textgrid.flip_rect(lines, rect, axis)
        self.set_lines(new, select=None if whole else rect)

    # ── дії / меню ──────────────────────────────────────────────────────────

    def _make_actions(self) -> None:
        mgr = shortcuts.manager()
        self.canvas_actions = {}
        for spec in shortcuts.SPECS:
            if spec.scope != shortcuts.CANVAS:
                continue
            if spec.id.startswith("block.palette_"):
                idx = int(spec.id.rsplit("_", 1)[1]) - 1
                slot = (lambda _=False, i=idx: self.insert_palette(i))
            else:
                slot = getattr(self, _BLOCK_SLOTS[spec.id])
                slot = (lambda _=False, f=slot: f())
            act = mgr.make_action(spec.id, self, slot)
            self.addAction(act)
            self.canvas_actions[spec.id] = act

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu(event.pos())
        menu.addSeparator()
        for key in ("block.copy", "block.cut", "block.paste", "block.paste_transparent", "block.clear"):
            menu.addAction(self.canvas_actions[key])
        menu.addSeparator()
        for key in ("block.col_insert", "block.col_delete", "block.overwrite"):
            menu.addAction(self.canvas_actions[key])
        if self.tools.context_actions:
            menu.addSeparator()
            for act in self.tools.context_actions:
                menu.addAction(act) if act is not None else menu.addSeparator()
        menu.exec(event.globalPos())
        menu.deleteLater()

    # ── геометрія ───────────────────────────────────────────────────────────

    def _sync_margins(self) -> None:
        self.setViewportMargins(self._nums.calc_width(), 0, 0, 0)
        cr = self.contentsRect()
        self._nums.setGeometry(QRect(cr.left(), cr.top(), self._nums.calc_width(), cr.height()))

    def _on_update_request(self, rect, dy):
        if dy:
            self._nums.scroll(0, dy)
        else:
            self._nums.update(0, rect.y(), self._nums.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_margins()
