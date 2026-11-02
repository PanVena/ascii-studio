"""Операції над полотном як над сіткою рядків (чиста логіка, без Qt).

Усі функції приймають список рядків і повертають НОВИЙ список; полотно
застосовує результат одним кроком undo.
"""
from __future__ import annotations

from typing import List, NamedTuple, Sequence

from . import mirror

Lines = List[str]


class Rect(NamedTuple):
    """Прямокутник клітинок: рядки [r0, r1] включно, колонки [c0, c1)."""
    r0: int
    r1: int
    c0: int
    c1: int

    @property
    def width(self) -> int:
        return self.c1 - self.c0

    @property
    def height(self) -> int:
        return self.r1 - self.r0 + 1


def ensure_rows(lines: Sequence[str], n: int) -> Lines:
    out = list(lines)
    while len(out) < n:
        out.append("")
    return out


def max_width(lines: Sequence[str]) -> int:
    return max((len(l) for l in lines), default=0)


def read_rect(lines: Sequence[str], rect: Rect) -> Lines:
    """Вміст прямокутника; короткі рядки доповнюються пробілами."""
    out = []
    for r in range(rect.r0, rect.r1 + 1):
        text = lines[r] if r < len(lines) else ""
        out.append(text[rect.c0:rect.c1].ljust(rect.width))
    return out


def write_rect(lines: Sequence[str], r0: int, c0: int, block: Sequence[str], transparent: bool = False) -> Lines:
    """Накладає блок у позицію (r0, c0); полотно розширюється. transparent — пробіли блоку не затирають."""
    out = ensure_rows(lines, r0 + len(block))
    for i, piece in enumerate(block):
        r = r0 + i
        row = out[r]
        if len(row) < c0 + len(piece):
            row = row.ljust(c0 + len(piece))
        if transparent:
            chars = list(row)
            for j, ch in enumerate(piece):
                if ch not in (" ", "⠀"):
                    chars[c0 + j] = ch
            row = "".join(chars)
        else:
            row = row[:c0] + piece + row[c0 + len(piece):]
        out[r] = row.rstrip() if transparent else row
    return out


def clear_rect(lines: Sequence[str], rect: Rect) -> Lines:
    """Заповнює прямокутник пробілами (лише існуючі символи, рядки не подовжуються)."""
    out = list(lines)
    for r in range(rect.r0, min(rect.r1 + 1, len(out))):
        row = out[r]
        if len(row) > rect.c0:
            end = min(rect.c1, len(row))
            out[r] = row[:rect.c0] + " " * (end - rect.c0) + row[end:]
    return out


def insert_column(lines: Sequence[str], r0: int, r1: int, col: int) -> Lines:
    out = list(lines)
    for r in range(r0, min(r1 + 1, len(out))):
        if len(out[r]) >= col:
            out[r] = out[r][:col] + " " + out[r][col:]
    return out


def delete_column(lines: Sequence[str], r0: int, r1: int, col: int) -> Lines:
    out = list(lines)
    for r in range(r0, min(r1 + 1, len(out))):
        if len(out[r]) > col:
            out[r] = out[r][:col] + out[r][col + 1:]
    return out


def indent(lines: Sequence[str], r0: int, r1: int, n: int = 4) -> Lines:
    out = list(lines)
    for r in range(r0, min(r1 + 1, len(out))):
        out[r] = " " * n + out[r]
    return out


def unindent(lines: Sequence[str], r0: int, r1: int, n: int = 4) -> tuple[Lines, List[int]]:
    """Прибирає до n пробілів на початку рядків; повертає (рядки, скільки знято з кожного)."""
    out = list(lines)
    removed = []
    for r in range(r0, min(r1 + 1, len(out))):
        row = out[r]
        k = 0
        while k < n and k < len(row) and row[k] == " ":
            k += 1
        out[r] = row[k:]
        removed.append(k)
    return out, removed


def pad_to_rectangle(lines: Sequence[str]) -> Lines:
    """Прибирає хвостові пробіли й доповнює всі рядки до найдовшого."""
    stripped = [l.rstrip(" ") for l in lines]
    w = max_width(stripped)
    return [l.ljust(w) for l in stripped]


def trim(lines: Sequence[str]) -> Lines:
    """Прибирає хвостові пробіли, порожні рядки згори/знизу та спільний відступ зліва."""
    rows = [l.rstrip() for l in lines]
    while rows and not rows[0]:
        rows.pop(0)
    while rows and not rows[-1]:
        rows.pop()
    indents = [len(l) - len(l.lstrip(" ")) for l in rows if l]
    k = min(indents, default=0)
    return [l[k:] for l in rows]


def flip_rect(lines: Sequence[str], rect: Rect, axis: str) -> Lines:
    """Перевертає прямокутник на місці (без розмітки)."""
    block = read_rect(lines, rect)
    flipped = mirror.flip_text("\n".join(block), axis, width=rect.width).split("\n")
    flipped = [l.ljust(rect.width) for l in flipped]
    flipped += [" " * rect.width] * (rect.height - len(flipped))
    out = write_rect(lines, rect.r0, rect.c0, flipped)
    for r in range(rect.r0, rect.r1 + 1):
        original = lines[r] if r < len(lines) else ""
        if len(original) <= rect.c1:
            out[r] = out[r].rstrip(" ")
    return out


def symmetric_cells(row: int, col: int, rows: int, cols: int, axis: str) -> List[tuple[int, int, str]]:
    """Дзеркальні позиції клітинки відносно центру полотна rows×cols: [(рядок, колонка, вісь)]."""
    out = []
    if axis in (mirror.H, mirror.HV) and cols > 0:
        out.append((row, cols - 1 - col, mirror.H))
    if axis in (mirror.V, mirror.HV) and rows > 0:
        out.append((rows - 1 - row, col, mirror.V))
    if axis == mirror.HV and rows > 0 and cols > 0:
        out.append((rows - 1 - row, cols - 1 - col, mirror.HV))
    return [(r, c, a) for r, c, a in out if (r, c) != (row, col) and r >= 0 and c >= 0]
