"""Чиста логіка: дзеркало, сітка тексту, файли й назви (без Qt)."""
import os
import unicodedata

import pytest

from ascii_studio.core import files, mirror, textgrid
from ascii_studio.core.layers import CanvasLayers, Layer
from ascii_studio.core.textgrid import Rect


# ── дзеркало ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("a,b", ["┌┐", "└┘", "├┤", "╭╮", "╔╗", "▌▐", "▖▗", "▙▟", "▛▜", "◀▶", "←→", "↖↗", "()", "[]",
                                 "{}", "<>", "/\\", "«»", "╱╲", "⎛⎞", "┍┑", "╼╾", "bd", "pq"])
def test_horizontal_pairs(a, b):
    assert mirror.mirror_char(a, mirror.H) == b
    assert mirror.mirror_char(b, mirror.H) == a


@pytest.mark.parametrize("a,b", ["┌└", "┐┘", "┬┴", "╭╰", "╔╚", "▀▄", "▖▘", "▙▛", "▲▼", "↑↓", "↖↙", "/\\", "^v",
                                 "⎛⎝", "╤╧", "bp", "▔▁"])
def test_vertical_pairs(a, b):
    assert mirror.mirror_char(a, mirror.V) == b
    assert mirror.mirror_char(b, mirror.V) == a


def test_maps_are_involutions():
    """Кожна пара взаємна: двічі віддзеркалити = оригінал."""
    for table in (mirror.H_MAP, mirror.V_MAP):
        for a, b in table.items():
            assert table[b] == a


def test_box_drawing_names_agree_with_horizontal_map():
    """Для рамок ім'я відповідника = ім'я з LEFT↔RIGHT (джерело таблиці — Unicode)."""
    for cp in range(0x2500, 0x2580):
        ch = chr(cp)
        name = unicodedata.name(ch)
        if "LEFT" in name or "RIGHT" in name:
            other = mirror.mirror_char(ch, mirror.H)
            assert other != ch, name
            swapped = " ".join({"LEFT": "RIGHT", "RIGHT": "LEFT"}.get(t, t) for t in name.split())
            assert mirror._split_key(unicodedata.name(other)) == mirror._split_key(swapped) or other in "╱╲", name


def test_symmetric_chars_unchanged():
    for ch in "│─┼█░▒▓ AHIMOTUVWXY|":
        assert mirror.mirror_char(ch, mirror.H) == ch


def test_braille_flip():
    dot1, dot4 = chr(0x2801), chr(0x2808)
    assert mirror.mirror_char(dot1, mirror.H) == dot4
    dot7 = chr(0x2840)
    assert mirror.mirror_char(dot1, mirror.V) == dot7
    full = chr(0x28FF)
    assert mirror.mirror_char(full, mirror.HV) == full


def test_rotate_is_h_then_v():
    for ch in "┌▙◢↖/":
        assert mirror.mirror_char(ch, mirror.HV) == mirror.mirror_char(mirror.mirror_char(ch, mirror.H), mirror.V)


def test_flip_text_pads_lines_before_reversing():
    """Рядки різної довжини вирівнюються — праве поле не «з'їжджає» (старий баг дзеркала)."""
    assert mirror.flip_text("ab\nabcd", mirror.H) == "  da\nbcda"


def test_flip_text_vertical_and_rotate():
    assert mirror.flip_text("┌─┐\n│x│", mirror.V) == "│x│\n└─┘"
    assert mirror.flip_text("ab\ncd", mirror.HV) == "pc\nqa"


def test_flip_preserves_color_markup():
    out = mirror.flip_text("<color:ff0000>ab</color>cd", mirror.H)
    assert mirror.plain_text(out) == "bcda"
    assert out == "bc<color:ff0000>da</color>"
    assert mirror.markup_ok(out)


def test_flip_multiline_color_closes_per_row():
    out = mirror.flip_text("<b>a\nb</b>", mirror.V)
    assert out == "<b>p</b>\n<b>a</b>"


def test_flip_invalid_markup_falls_back_to_raw():
    out = mirror.flip_text("<b>ab", mirror.H)
    assert "<b" not in out or out != "<b>ab"
    assert len(out.split("\n")) == 1


def test_join_horizontal_and_overlap():
    assert mirror.join_text("/-\n|a", mirror.H) == "/--\\\n|aa|"
    assert mirror.join_text("/-\n|a", mirror.H, overlap=True) == "/-\\\n|a|"


def test_join_quadrants():
    assert mirror.join_text("╭", mirror.HV) == "╭╮\n╰╯"


def test_unmatched_chars_reports_asymmetric_letters():
    bad = mirror.unmatched_chars("Яo?", mirror.H)
    assert "Я" in bad and "?" in bad and "o" not in bad
    assert mirror.unmatched_chars("Я", mirror.V) == []


def test_flip_unknown_axis_raises():
    with pytest.raises(ValueError):
        mirror.flip_text("x", "diagonal")


# ── сітка ─────────────────────────────────────────────────────────────────


def test_read_and_clear_rect():
    lines = ["abcd", "ef", "ghij"]
    r = Rect(0, 2, 1, 3)
    assert textgrid.read_rect(lines, r) == ["bc", "f ", "hi"]
    assert textgrid.clear_rect(lines, r) == ["a  d", "e ", "g  j"]


def test_write_rect_extends_canvas():
    assert textgrid.write_rect(["ab"], 1, 3, ["XY"]) == ["ab", "   XY"]
    assert textgrid.write_rect(["abcd"], 0, 1, ["XY"]) == ["aXYd"]


def test_write_rect_transparent_keeps_content():
    assert textgrid.write_rect(["abcd"], 0, 0, ["X Y"], transparent=True) == ["XbYd"]


def test_columns():
    lines = ["abc", "de", ""]
    assert textgrid.insert_column(lines, 0, 2, 1) == ["a bc", "d e", ""]
    assert textgrid.delete_column(lines, 0, 2, 1) == ["ac", "d", ""]


def test_indent_unindent():
    lines = ["a", "  b", "c"]
    assert textgrid.indent(lines, 0, 1, 2) == ["  a", "    b", "c"]
    out, removed = textgrid.unindent(lines, 0, 2, 4)
    assert out == ["a", "b", "c"] and removed == [0, 2, 0]


def test_pad_and_trim():
    assert textgrid.pad_to_rectangle(["ab  ", "abcd", ""]) == ["ab  ", "abcd", "    "]
    assert textgrid.trim(["", "   ab ", "    c", ""]) == ["ab", " c"]


def test_flip_rect_in_place():
    lines = ["x┌─y", "x│ y"]
    assert textgrid.flip_rect(lines, Rect(0, 1, 1, 3), mirror.V) == ["x│ y", "x└─y"]
    assert textgrid.flip_rect(["ab"], Rect(0, 0, 0, 4), mirror.H) == ["  da"]


def test_symmetric_cells():
    assert textgrid.symmetric_cells(0, 0, 4, 10, mirror.H) == [(0, 9, "h")]
    assert sorted(textgrid.symmetric_cells(0, 0, 4, 10, mirror.HV)) == [(0, 9, "h"), (3, 0, "v"), (3, 9, "hv")]
    assert textgrid.symmetric_cells(0, 2, 1, 5, mirror.H) == []


# ── файли й назви ─────────────────────────────────────────────────────────


def test_atomic_write_and_list(tmp_path):
    files.atomic_write_text(str(tmp_path / "a" / "кадр_1.txt"), "x")
    files.atomic_write_text(str(tmp_path / "b.txt"), "y")
    (tmp_path / ".hidden.txt").write_text("z")
    assert files.list_arts(str(tmp_path)) == ["a/кадр_1", "b"]
    assert not [p for p in os.listdir(tmp_path / "a") if p.startswith(".tmp_")]


def test_sidecar_roundtrip_and_stale_removal(tmp_path):
    txt = str(tmp_path / "art.txt")
    stack = CanvasLayers([Layer("bottom", True, "aa"), Layer("top", True, " b")])
    files.save_sidecar(txt, stack, 1)
    loaded, idx = files.load_sidecar(txt)
    assert [l.text for l in loaded] == ["aa", " b"] and idx == 1
    files.save_sidecar(txt, CanvasLayers([Layer("one", True, "x")]), 0)
    assert not os.path.exists(files.sidecar_path(txt))


def test_sidecar_corrupt(tmp_path):
    txt = str(tmp_path / "bad.txt")
    with open(files.sidecar_path(txt), "w") as f:
        f.write("{oops")
    assert files.load_sidecar(txt) is None


def test_safe_parts_and_names():
    assert files.safe_parts("маєток/../вороги/кіт мурчик.txt") == ["маєток", "вороги", "кіт_мурчик"]
    assert files.safe_name("  !!! ") == "ascii"
    assert files.split_root_number("кадр_12") == ("кадр", 12)
    assert files.next_copy_name("кадр_1", {"кадр_2"}) == "кадр_3"
    assert files.next_copy_name("art", set()) == "art_2"
    assert files.numbered_series(["f_10", "f_2", "g_1", "f_x"], "f") == ["f_2", "f_10"]


# ── розмітка й анімація ───────────────────────────────────────────────────

from ascii_studio.core import anim_metrics, markup  # noqa: E402


@pytest.mark.parametrize("text,levels", [
    ("<b>ok</b> <color:ff0000>x</color>", []),
    ("<b>незакритий", ["error"]),
    ("текст</i>", ["error"]),
    ("<b><i>x</b></i>", ["error", "error"]),
    ("<color:ff0000>a<color:00ff00>b</color></color>", ["warning"]),
    ("<color:red>x</color>", ["error", "error"]),
])
def test_markup_check(text, levels):
    assert sorted(p.level for p in markup.check_markup(text)) == sorted(levels)


def test_transition_classes():
    assert anim_metrics.classify("AB\n", "AB\nCD\n").mode == "append"
    assert anim_metrics.classify("AAAAAAAAAA\nBBBB", "AAAAAAAAAA\nBxBB").mode == "middle"
    assert anim_metrics.classify("abc", "xyz").mode == "full"
    assert [t.index for t in anim_metrics.transitions(["a", "b", "c"])] == [1, 2, 0]


def test_onion_cells_fill_spaces_from_previous():
    assert anim_metrics.onion_cells("ab", "a ") == [[("a", False), ("b", True)]]


def test_fit_scale_formula():
    from ascii_studio.core import fit
    assert fit.compute_fit_scale(96, 38, 192, 38) == pytest.approx(0.475)
    assert fit.fit_scale(96, 38, 48, 19) == 1.0
    assert fit.normalize_fit(False) is None and fit.normalize_fit(True) == 1.0
