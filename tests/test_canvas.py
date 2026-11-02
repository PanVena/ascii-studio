"""Полотно: кисть і симетрія, прямокутні операції, переворот, шари й привид, UTF-16."""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ascii_studio.core import mirror  # noqa: E402
from ascii_studio.ui.canvas import CanvasEditor, CanvasTools, _cp, _u16  # noqa: E402

from .conftest import show  # noqa: E402


@pytest.fixture()
def tools(app):
    return CanvasTools()


@pytest.fixture()
def editor(app, tools):
    ed = CanvasEditor(tools, title="t")
    ed.resize(600, 400)
    yield ed
    ed.close()
    ed.deleteLater()


def _mouse(ed, etype, pos, buttons=Qt.LeftButton):
    ev = QMouseEvent(etype, QPointF(pos), Qt.LeftButton, buttons, Qt.NoModifier)
    {QEvent.MouseButtonPress: ed.mousePressEvent, QEvent.MouseMove: ed.mouseMoveEvent,
     QEvent.MouseButtonRelease: ed.mouseReleaseEvent}[etype](ev)


def _cell_pos(ed, row, col):
    o = ed._origin()
    return QPoint(int(o.x() + (col + 0.5) * ed._advance()), int(o.y() + (row + 0.5) * ed._line_height()))


def _select(ed, a, b):
    cur = ed.textCursor()
    cur.setPosition(ed._pos_of(*a))
    cur.setPosition(ed._pos_of(*b), QTextCursor.KeepAnchor)
    ed.setTextCursor(cur)


def test_utf16_helpers():
    s = "a🔥b"
    assert _u16(s, 2) == 3 and _cp(s, 3) == 2 and _cp(s, 1) == 1


def test_new_editor_is_clean_and_typing_marks_dirty(editor):
    assert not editor.dirty
    editor.insertPlainText("x")
    assert editor.dirty and editor.active_layer.text == "x"
    editor.mark_clean()
    assert not editor.dirty


def test_brush_paints_beyond_line_end(app, editor, tools):
    tools.update(brush=True)
    show(app, editor)
    p = _cell_pos(editor, 2, 5)
    _mouse(editor, QEvent.MouseButtonPress, p)
    _mouse(editor, QEvent.MouseButtonRelease, p)
    assert editor.lines() == ["", "", "     █"]


def test_brush_stroke_is_one_undo_step(app, editor, tools):
    editor.setPlainText(" " * 20)
    tools.update(brush=True)
    show(app, editor)
    _mouse(editor, QEvent.MouseButtonPress, _cell_pos(editor, 0, 1))
    _mouse(editor, QEvent.MouseMove, _cell_pos(editor, 0, 8))
    _mouse(editor, QEvent.MouseButtonRelease, _cell_pos(editor, 0, 8))
    assert editor.toPlainText().count("█") == 8
    editor.undo()
    assert "█" not in editor.toPlainText()


def test_eraser_does_not_extend(app, editor, tools):
    editor.setPlainText("abcd")
    tools.update(brush=True, brush_char=" ")
    show(app, editor)
    for col in (2, 9):
        p = _cell_pos(editor, 0, col)
        _mouse(editor, QEvent.MouseButtonPress, p)
        _mouse(editor, QEvent.MouseButtonRelease, p)
    assert editor.toPlainText() == "ab d"


def test_symmetry_brush_mirrors_char(app, editor, tools):
    editor.setPlainText("\n".join([" " * 6] * 4))
    tools.update(brush=True, brush_char="┌", symmetry=mirror.HV)
    show(app, editor)
    p = _cell_pos(editor, 0, 0)
    _mouse(editor, QEvent.MouseButtonPress, p)
    _mouse(editor, QEvent.MouseButtonRelease, p)
    assert editor.lines() == ["┌    ┐", "      ", "      ", "└    ┘"]


def test_paint_cell_with_emoji_before(editor):
    editor.setPlainText("🔥ab")
    editor._paint_cell(0, 2, "X")
    assert editor.toPlainText() == "🔥aX"


def test_cells_between():
    assert CanvasEditor.cells_between((0, 0), (0, 3)) == [(0, 1), (0, 2), (0, 3)]
    assert CanvasEditor.cells_between((3, 5), (1, 2))[-1] == (1, 2)


def test_block_copy_paste_clear(app, editor):
    editor.setPlainText("abcd\nefgh\nijkl")
    _select(editor, (0, 1), (1, 3))
    assert editor.selection_rect().width == 2
    editor.block_copy()
    assert QApplication.clipboard().text() == "bc\nfg"
    editor.block_clear()
    assert editor.lines() == ["a  d", "e  h", "ijkl"]
    cur = editor.textCursor()
    cur.setPosition(editor._pos_of(2, 2))
    editor.setTextCursor(cur)
    editor.block_paste()
    assert editor.lines() == ["a  d", "e  h", "ijbc", "  fg"]


def test_transparent_paste_keeps_content(editor):
    editor.setPlainText("abcd")
    QApplication.clipboard().setText("X Y")
    editor.block_paste_transparent()
    assert editor.toPlainText() == "XbYd"


def test_column_ops_keep_selection(editor):
    editor.setPlainText("abc\ndef")
    _select(editor, (0, 1), (1, 1))
    editor.col_insert()
    assert editor.lines() == ["a bc", "d ef"]
    editor.col_backspace()
    assert editor.lines() == ["abc", "def"]
    editor.col_delete()
    assert editor.lines() == ["ac", "df"]


def test_indent_unindent(editor):
    editor.setPlainText("a\nb\nc")
    _select(editor, (0, 0), (1, 1))
    editor.indent()
    assert editor.lines() == ["    a", "    b", "c"]
    editor.unindent()
    assert editor.lines() == ["a", "b", "c"]


def test_flip_selection_and_whole(editor):
    editor.setPlainText("x┌─y\nx│ y")
    _select(editor, (0, 1), (1, 3))
    editor.flip(mirror.V)
    assert editor.lines() == ["x│ y", "x└─y"]
    editor.textCursor().clearSelection()
    editor.setTextCursor(QTextCursor(editor.document()))
    editor.flip(mirror.H)
    assert editor.lines() == ["y │x", "y─┘x"]


def test_flip_refuses_partial_markup(editor):
    msgs = []
    editor.message.connect(msgs.append)
    editor.setPlainText("<color:ff0000>ab</color>cd\nxy")
    _select(editor, (0, 1), (0, 5))
    editor.flip(mirror.H)
    assert msgs and editor.lines()[0] == "<color:ff0000>ab</color>cd"


def test_flip_whole_keeps_markup(editor):
    editor.setPlainText("<color:ff0000>ab</color>cd")
    editor.flip(mirror.H)
    assert editor.toPlainText() == "bc<color:ff0000>da</color>"


def test_set_lines_is_single_undo(editor):
    editor.setPlainText("abc\ndef")
    editor.set_lines(["abc", "dXf", "new"])
    assert editor.toPlainText() == "abc\ndXf\nnew"
    editor.undo()
    assert editor.toPlainText() == "abc\ndef"


def test_layers_switch_and_underlay(editor):
    editor.setPlainText("bottom")
    top = editor.add_layer("top")
    assert editor.toPlainText() == "" and editor.underlay_text == "bottom"
    editor.insertPlainText("  T")
    assert editor.composite_text() == "boTtom"
    editor.switch_layer(editor.layers.get(0))
    assert editor.toPlainText() == "bottom" and editor.underlay_text == "  T"
    editor.set_layer_visible(top, False)
    assert editor.underlay_text == "" and editor.composite_text() == "bottom"


def test_remove_last_layer_keeps_one(editor):
    editor.remove_layer(editor.active_layer)
    assert editor.layers.count == 1 and editor.toPlainText() == ""


def test_underlay_paints_ghost_pixels(app, editor, tools):
    editor.setPlainText("abcd")
    editor.add_layer("top")
    show(app, editor)
    img = editor.viewport().grab().toImage()
    ghost = tools.ghost_color.getRgb()
    assert any(img.pixelColor(x, y).getRgb() == ghost for y in range(img.height()) for x in range(img.width()))


def test_zoom_clamped(editor):
    editor.set_point_size(1000)
    assert editor.font().pointSizeF() == 72
    editor.set_point_size(1)
    assert editor.font().pointSizeF() == 4


def test_select_all_means_full_rows(editor):
    editor.setPlainText("ab\nlong line here\ncd")
    editor.selectAll()
    assert editor.selection_rect(full_rows_if_empty=True) == (0, 2, 0, 14)
    assert editor.selection_rect() is None
