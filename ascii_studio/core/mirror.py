"""Дзеркальне відображення ASCII-арту (чиста логіка, без Qt).

Таблиці пар будуються з імен Unicode (LEFT↔RIGHT, UP↔DOWN …) для стрілок,
рамок, блоків і геометричних фігур, плюс ручні пари для ASCII. Брайль
віддзеркалюється перестановкою крапок. Розмітка (<color:…>, <b>…)
зберігається: кожна клітинка несе свій стиль, після перевороту теги
перебудовуються рядок за рядком.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Sequence, Tuple

from .markup import check_markup

H = "h"
V = "v"
HV = "hv"
AXES = (H, V, HV)

_H_TOKENS = {
    "LEFT": "RIGHT", "RIGHT": "LEFT",
    "LEFTWARDS": "RIGHTWARDS", "RIGHTWARDS": "LEFTWARDS",
    "WEST": "EAST", "EAST": "WEST",
}
_V_TOKENS = {
    "UP": "DOWN", "DOWN": "UP",
    "UPPER": "LOWER", "LOWER": "UPPER",
    "UPWARDS": "DOWNWARDS", "DOWNWARDS": "UPWARDS",
    "NORTH": "SOUTH", "SOUTH": "NORTH",
    "TOP": "BOTTOM", "BOTTOM": "TOP",
}
_PREFIXES = ("BOX DRAWINGS ", "QUADRANT ")
_RANGES = (
    (0x0020, 0x007F), (0x00A0, 0x0100), (0x2000, 0x2070), (0x2190, 0x2200),
    (0x2300, 0x2400), (0x2500, 0x2600), (0x27E6, 0x2800), (0x27F0, 0x2800),
)

_MANUAL_H = ("<>", "/\\", "bd", "pq", "⊂⊃", "⊆⊇", "≤≥", "≪≫", "⊏⊐", "⋉⋊", "∈∋", "⊢⊣", "⌐¬")
_MANUAL_V = ("/\\", "^v", "_‾", "bp", "dq", "∧∨", "∩∪", "⊓⊔", "⌢⌣", "╱╲", "▚▞", "▧▨", "',")
_MANUAL_H_EXTRA = ("╱╲", "▚▞", "▧▨")

_BRAILLE_BASE = 0x2800
_BRAILLE_DOTS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))

_H_SYMMETRIC_ASCII = set(" !\"'*+-.:=^_|#08AHIMOTUVWXYilmnouvwx")
_H_SYMMETRIC_CYR = set("АЖНОПТФХШжнопртфхшмтФ")


def _split_key(name: str):
    prefix = ""
    for p in _PREFIXES:
        if name.startswith(p):
            prefix, name = p, name[len(p):]
            break
    return prefix, frozenset(name.split(" AND "))


def _swap_name(name: str, table: Dict[str, str]) -> str:
    return "".join(table.get(tok, tok) for tok in re.split(r"([ \-])", name))


def _build_pairs(table: Dict[str, str]) -> Dict[str, str]:
    by_key: Dict[tuple, str] = {}
    names: Dict[str, str] = {}
    for lo, hi in _RANGES:
        for cp in range(lo, hi):
            ch = chr(cp)
            name = unicodedata.name(ch, "")
            if name:
                names[ch] = name
                by_key.setdefault(_split_key(name), ch)
    pairs: Dict[str, str] = {}
    for ch, name in names.items():
        swapped = _swap_name(name, table)
        if swapped == name:
            continue
        other = by_key.get(_split_key(swapped))
        if other and other != ch:
            pairs[ch] = other
    return pairs


def _add_manual(pairs: Dict[str, str], manual: Iterable[str]) -> None:
    for a, b in manual:
        pairs[a] = b
        pairs[b] = a


def _flip_braille(ch: str, axis: str) -> str:
    bits = ord(ch) - _BRAILLE_BASE
    grid = [[bool(bits & d) for d in row] for row in _BRAILLE_DOTS]
    if axis in (H, HV):
        grid = [row[::-1] for row in grid]
    if axis in (V, HV):
        grid = grid[::-1]
    out = 0
    for r, row in enumerate(grid):
        for c, on in enumerate(row):
            if on:
                out |= _BRAILLE_DOTS[r][c]
    return chr(_BRAILLE_BASE + out)


def _symmetric_pairs(pairs: Dict[str, str]) -> Dict[str, str]:
    return {a: b for a, b in pairs.items() if pairs.get(b) == a}


H_MAP: Dict[str, str] = _build_pairs(_H_TOKENS)
_add_manual(H_MAP, _MANUAL_H + _MANUAL_H_EXTRA)
H_MAP = _symmetric_pairs(H_MAP)

V_MAP: Dict[str, str] = _build_pairs(_V_TOKENS)
_add_manual(V_MAP, _MANUAL_V)
V_MAP = _symmetric_pairs(V_MAP)


def mirror_char(ch: str, axis: str) -> str:
    """Дзеркальний відповідник символу для осі (h — ліво↔право, v — верх↔низ, hv — поворот на 180°)."""
    if len(ch) != 1:
        return ch
    if _BRAILLE_BASE <= ord(ch) <= _BRAILLE_BASE + 0xFF:
        return _flip_braille(ch, axis)
    if axis == H:
        return H_MAP.get(ch, ch)
    if axis == V:
        return V_MAP.get(ch, ch)
    h = H_MAP.get(ch, ch)
    return V_MAP.get(h, h)


def _has_pair(ch: str, axis: str) -> bool:
    if _BRAILLE_BASE <= ord(ch) <= _BRAILLE_BASE + 0xFF:
        return True
    if axis in (H, HV) and ch in H_MAP:
        return True
    if axis in (V, HV) and ch in V_MAP:
        return True
    return False


def unmatched_chars(text: str, axis: str) -> List[str]:
    """Символи, які після перевороту виглядатимуть «неправильно» (асиметричні й без пари)."""
    if axis not in (H, HV):
        return []
    out = set()
    for ch in plain_text(text):
        if ch == "\n" or _has_pair(ch, axis):
            continue
        if ch in _H_SYMMETRIC_ASCII or ch in _H_SYMMETRIC_CYR:
            continue
        cat = unicodedata.category(ch)
        if ord(ch) < 0x80 or cat[0] in ("L", "N"):
            out.add(ch)
    return sorted(out)


_TAG = re.compile(r"<color:[0-9a-fA-F]{6}>|</color>|</?[bius]>")

Cell = Tuple[str, Tuple[str, ...]]


def plain_text(text: str) -> str:
    """Текст без тегів розмітки."""
    return _TAG.sub("", text)


def markup_ok(text: str) -> bool:
    return not any(p.level == "error" for p in check_markup(text))


def to_cells(text: str) -> List[List[Cell]]:
    """Рядки клітинок (символ, стек відкритих тегів). Розмітка має бути коректною."""
    rows: List[List[Cell]] = [[]]
    stack: List[str] = []
    pos = 0
    for m in _TAG.finditer(text):
        _push_chars(rows, text[pos:m.start()], stack)
        tag = m.group(0)
        if tag.startswith("</"):
            if stack:
                stack.pop()
        else:
            stack.append(tag)
        pos = m.end()
    _push_chars(rows, text[pos:], stack)
    return rows


def _push_chars(rows: List[List[Cell]], chunk: str, stack: Sequence[str]) -> None:
    style = tuple(stack)
    for ch in chunk:
        if ch == "\n":
            rows.append([])
        else:
            rows[-1].append((ch, style))


def _close(tag: str) -> str:
    return "</color>" if tag.startswith("<color:") else "</" + tag[1:]


def from_cells(rows: List[List[Cell]]) -> str:
    """Серіалізує клітинки назад у текст із мінімальними тегами (усі теги закриваються в межах рядка)."""
    out_lines = []
    for row in rows:
        while row and row[-1][0] == " ":
            row = row[:-1]
        parts: List[str] = []
        cur: Tuple[str, ...] = ()
        for ch, style in row:
            if style != cur:
                k = 0
                while k < len(cur) and k < len(style) and cur[k] == style[k]:
                    k += 1
                parts.extend(_close(t) for t in reversed(cur[k:]))
                parts.extend(style[k:])
                cur = style
            parts.append(ch)
        parts.extend(_close(t) for t in reversed(cur))
        out_lines.append("".join(parts))
    return "\n".join(out_lines)


def flip_cells(rows: List[List[Cell]], axis: str, width: int | None = None) -> List[List[Cell]]:
    w = width if width is not None else max((len(r) for r in rows), default=0)
    padded = [r + [(" ", ())] * (w - len(r)) for r in rows]
    if axis in (H, HV):
        padded = [r[::-1] for r in padded]
    if axis in (V, HV):
        padded = padded[::-1]
    return [[(mirror_char(ch, axis), st) for ch, st in r] for r in padded]


def flip_text(text: str, axis: str, width: int | None = None) -> str:
    """Перевертає арт: рядки вирівнюються до спільної ширини, символи замінюються дзеркальними,
    розмітка зберігається. Хвостові пробіли прибираються."""
    if axis not in AXES:
        raise ValueError(f"невідома вісь: {axis!r}")
    if markup_ok(text):
        return from_cells(flip_cells(to_cells(text), axis, width))
    lines = text.split("\n")
    w = width if width is not None else max((len(l) for l in lines), default=0)
    lines = [l.ljust(w) for l in lines]
    if axis in (H, HV):
        lines = [l[::-1] for l in lines]
    if axis in (V, HV):
        lines = lines[::-1]
    return "\n".join("".join(mirror_char(c, axis) for c in l).rstrip() for l in lines)


def _raw_cells(text: str) -> List[List[Cell]]:
    return [[(ch, ()) for ch in line] for line in text.split("\n")]


def join_text(text: str, axis: str, overlap: bool = False) -> str:
    """Оригінал + його дзеркало поруч (h), під ним (v) або в чотири чверті (hv).
    overlap — крайня колонка/рядок спільні (вісь проходить через них): непарна ширина."""
    if axis not in AXES:
        raise ValueError(f"невідома вісь: {axis!r}")
    rows = to_cells(text) if markup_ok(text) else _raw_cells(text)
    k = 1 if overlap else 0
    if axis in (H, HV):
        w = max((len(r) for r in rows), default=0)
        padded = [r + [(" ", ())] * (w - len(r)) for r in rows]
        flipped = flip_cells(padded, H, w)
        rows = [o + f[k:] for o, f in zip(padded, flipped)]
    if axis in (V, HV):
        w = max((len(r) for r in rows), default=0)
        padded = [r + [(" ", ())] * (w - len(r)) for r in rows]
        flipped = [[(mirror_char(ch, V), st) for ch, st in r] for r in padded[::-1]]
        rows = padded + flipped[k:]
    return from_cells(rows)
