"""Метрики анімації: наскільки сусідні кадри схожі (чиста логіка).

Для кожного переходу кадрів визначається, як його можна перемалювати інкрементально:
  * "append" — новий кадр починається зі старого: дописується лише хвіст;
  * "middle" — спільні префікс+суфікс ≥ 75% довшого кадру (без тегів у них): міняється середина;
  * "full"   — кадри надто різні, перемальовується все (на великих артах — можливі ривки).
"""
from typing import List, NamedTuple

MIDDLE_THRESHOLD = 0.75


class Transition(NamedTuple):
    index: int          # перехід index-1 → index
    mode: str           # "append" | "middle" | "full" | "same"
    shared: float       # частка спільного префікса+суфікса (0..1)


def _prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def classify(prev: str, art: str) -> Transition:
    prev = prev if prev.endswith("\n") else prev + "\n"
    art = art if art.endswith("\n") else art + "\n"
    if prev == art:
        return Transition(0, "same", 1.0)
    longest = max(len(prev), len(art)) or 1
    if art.startswith(prev):
        return Transition(0, "append", len(prev) / longest)
    p = _prefix_len(prev, art)
    minlen = min(len(prev), len(art))
    s = _prefix_len(prev[::-1][:minlen - p], art[::-1][:minlen - p])
    shared = (p + s) / longest
    mid_new = art[p:len(art) - s]
    ok = (p + s >= int(longest * MIDDLE_THRESHOLD)
          and "<" not in prev[:p] and not (s and "<" in prev[len(prev) - s:])
          and mid_new.count("<color:") == mid_new.count("</color>"))
    return Transition(0, "middle" if ok else "full", shared)


def transitions(frames: List[str], loop: bool = True) -> List[Transition]:
    """Класифікація всіх переходів (з loop — ще й останній → перший)."""
    out = []
    pairs = list(range(1, len(frames))) + ([0] if loop and len(frames) > 1 else [])
    for i in pairs:
        t = classify(frames[i - 1], frames[i])
        out.append(Transition(i, t.mode, t.shared))
    return out


def onion_cells(prev: str, cur: str):
    """[(рядок, [(символ, is_ghost)])]: пробіли поточного кадру заповнені символами попереднього."""
    p_lines, c_lines = prev.split("\n"), cur.split("\n")
    out = []
    for r in range(max(len(p_lines), len(c_lines))):
        pl = p_lines[r] if r < len(p_lines) else ""
        cl = c_lines[r] if r < len(c_lines) else ""
        row = []
        for c in range(max(len(pl), len(cl))):
            ch = cl[c] if c < len(cl) else " "
            if ch == " " and c < len(pl) and pl[c] != " ":
                row.append((pl[c], True))
            else:
                row.append((ch, False))
        out.append(row)
    return out
