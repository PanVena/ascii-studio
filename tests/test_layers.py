"""Тести модулів шарів ASCII-канвасу (compose + CanvasLayers)."""
import pytest

from ascii_studio.core.layers import (
    TRANSPARENT,
    CanvasLayers,
    Layer,
    compose,
)


# ── compose ────────────────────────────────────────────────────────────────


def test_compose_single_layer_passthrough():
    assert compose(["abc\ndef"]) == "abc\ndef"


def test_compose_empty_input():
    assert compose([]) == ""


def test_compose_rstrips_trailing_spaces():
    assert compose(["abc   "]) == "abc"
    assert compose(["abcd  ", "1"]) == "1bcd"


def test_compose_top_wins_when_both_opaque():
    assert compose(["abcd", "1234"]) == "1234"


def test_compose_bottom_shows_through_spaces():
    assert compose(["abcd", "   1"]) == "abc1"


def test_compose_bottom_shows_through_braille_blank():
    blank = "\u2800"
    assert compose(["abcd", blank * 3 + "1"]) == "abc1"


def test_compose_row_width_is_max_across_layers():
    assert compose(["xy", "  z"]) == "xyz"


def test_compose_multi_line_alignment():
    bottom = "aaaa\nbbbb"
    top = " 1\n 2"
    assert compose([bottom, top]) == "a1aa\nb2bb"


def test_compose_shorter_top_leaves_bottom_tail():
    assert compose(["abcd", "1"]) == "1bcd"


# ── Layer / CanvasLayers ───────────────────────────────────────────────────


def test_layer_defaults():
    layer = Layer()
    assert layer.name == "" and layer.visible is True and layer.text == ""


def test_layer_dict_roundtrip():
    layer = Layer(name="тло", visible=False, text="abc")
    data = layer.to_dict()
    back = Layer.from_dict(data)
    assert (back.name, back.visible, back.text) == ("тло", False, "abc")


def test_canvas_layers_add_remove_move():
    stack = CanvasLayers()
    a = stack.add_layer("a")
    b = stack.add_layer("b")
    c = stack.add_layer("c")
    assert [l.name for l in stack] == ["a", "b", "c"]
    stack.move(2, -1)
    assert [l.name for l in stack] == ["a", "c", "b"]
    stack.remove_layer(0)
    assert [l.name for l in stack] == ["c", "b"]


def test_canvas_layers_move_clamped():
    stack = CanvasLayers()
    stack.add_layer("a")
    stack.add_layer("b")
    stack.move(0, -1)
    assert [l.name for l in stack] == ["a", "b"]
    stack.move(1, 5)
    assert [l.name for l in stack] == ["a", "b"]


def test_canvas_layers_bounds_safe_ops():
    stack = CanvasLayers()
    stack.add_layer("a")
    stack.set_visible(99, False)
    stack.rename(99, "x")
    stack.remove_layer(-1)
    assert stack.count == 1


def test_active_index_prefers_topmost_visible():
    stack = CanvasLayers()
    for name in ("1", "2", "3"):
        layer = stack.add_layer(name)
        layer.text = name
    stack.set_visible(0, False)
    assert stack.active_index() == 2


def test_active_index_when_all_hidden():
    stack = CanvasLayers()
    stack.add_layer("a")
    stack.add_layer("b")
    stack.set_visible(0, False)
    stack.set_visible(1, False)
    assert stack.active_index() == 1


def test_composite_text_uses_only_visible_layers():
    stack = CanvasLayers()
    bottom = stack.add_layer("тло")
    top = stack.add_layer("верх")
    bottom.text = "abcd"
    top.text = "   1"
    assert stack.composite_text() == "abc1"
    stack.set_visible(1, False)
    assert stack.composite_text() == "abcd"


def test_canvas_layers_dict_roundtrip():
    stack = CanvasLayers()
    bottom = stack.add_layer("тло")
    top = stack.add_layer("верх")
    bottom.text = "aaaa"
    top.text = " 12"
    top.visible = False
    data = stack.to_dict()
    assert data["version"] == 1
    back = CanvasLayers.from_dict(data)
    assert back.count == 2
    assert [l.name for l in back] == ["тло", "верх"]
    assert back.get(0).text == "aaaa"
    assert back.get(1).visible is False
    assert back.composite_text() == "aaaa"


def test_canvas_layers_from_dict_ignores_garbage():
    back = CanvasLayers.from_dict({"layers": [None, 42, {"name": "x"}]})
    assert back.count == 1
    assert back.get(0).name == "x"


def test_transparent_set_contents():
    assert " " in TRANSPARENT and "\u2800" in TRANSPARENT
