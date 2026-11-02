"""«Як у грі»: чи влізе арт у термінал гри на типових екранах (метрики як у LazyEngine).

Повторює рушій: розмір шрифта з resizeEvent (45 рядків × 103 колонки опорної сітки),
бюджет вьюпорту з viewport._measure, масштаб — core/fit.fit_scale_for (власна копія
формули LazyEngine/Text/fit.py; із гри нічого не імпортується).
Без реального вікна Qt це оцінка: можлива похибка в кілька відсотків масштабу.
"""
import math
from dataclasses import dataclass

from PySide6.QtGui import QFont, QFontMetrics, QFontMetricsF

from .core.fit import Viewport, fit_scale_for, visible_cols, MIN_TERMINAL_COLS, MIN_TERMINAL_LINES

PRESETS = [
    ("1280×720", 1280, 720, False),
    ("Steam Deck 1280×800", 1280, 800, False),
    ("1600×900", 1600, 900, False),
    ("1920×1080", 1920, 1080, False),
    ("1920×1080 · центр вікна", 1920, 1080, True),
    ("2560×1440", 2560, 1440, False),
]

PLAIN_FONT = "JetBrains Mono"
ASCII_FONT = "DejaVu Sans Mono"
FONT_SCALE = 0.95   # масштаб шрифта гри після заставки (startup: set_font_scale(0.95))
_GLYPH_SCALES = tuple(round(1.0 - i * 0.01, 2) for i in range(0, 91))


@dataclass
class GameFit:
    name: str
    screen: tuple
    budget: tuple          # (cols, lines) при масштабі 1.0
    art: tuple             # (cols, lines)
    scale: float           # масштаб із fit=True
    overflow: tuple        # (колонки, рядки) переповнення БЕЗ fit


def _layout(full_w, full_h, centered):
    """viewport.compute_layout_geometry рушія."""
    if full_w / max(1, full_h) > 1.8:
        margin = int(full_w * 0.1)
        ref_w = full_w - 2 * margin
    else:
        ref_w = full_w - 20
    ref_h = full_h - 20
    if centered:
        side = max(100, full_h - 20)
        return ref_w, ref_h, side, side
    return ref_w, ref_h, ref_w, ref_h


def _ascii_pt(base_pt, scale, plain_cw):
    size = max(1.0, float(base_pt * scale))
    if scale != 1.0:
        f = QFont(ASCII_FONT)
        f.setPointSizeF(size)
        actual = QFontMetricsF(f).averageCharWidth()
        target = plain_cw * scale
        if actual > target > 0:
            size = max(1.0, size * (target / actual))
    return size


def evaluate(art: str, name: str, full_w: int, full_h: int, centered: bool, font_scale: float = FONT_SCALE) -> GameFit:
    ref_w, ref_h, out_w, out_h = _layout(full_w, full_h, centered)
    base_pt = max(4, int(min(ref_h / (45 * 1.46), ref_w / (103 * 0.85))))
    min_pt = 4 if font_scale < 1.0 else 11
    plain_pt = max(min_pt, min(int(int(base_pt * font_scale) * 0.9), 50))
    plain = QFont(PLAIN_FONT)
    plain.setPointSize(plain_pt)
    pfm = QFontMetrics(plain)
    plain_cw, plain_ch = pfm.averageCharWidth(), pfm.lineSpacing()
    afont = QFont(ASCII_FONT)
    afont.setPointSize(base_pt)
    afm = QFontMetrics(afont)
    cols = max(MIN_TERMINAL_COLS, out_w // max(1, plain_cw), out_w // max(1, afm.averageCharWidth()))
    lines = max(MIN_TERMINAL_LINES, out_h // max(1, plain_ch), out_h // max(1, afm.lineSpacing()))
    px_h = out_h  # ввід у грі вбудований у текст (QLineEdit прихований)
    glyphs = []
    pcw_f = QFontMetricsF(plain).averageCharWidth()
    for s in _GLYPH_SCALES:
        f = QFont(ASCII_FONT)
        f.setPointSizeF(_ascii_pt(base_pt, s, pcw_f))
        m = QFontMetricsF(f)
        glyphs.append((s, int(round(m.horizontalAdvance("M"))), int(round(m.lineSpacing()))))
    vp = Viewport(cols, lines, px_w=out_w, px_h=px_h, glyphs=tuple(glyphs))
    art_lines = art.split("\n") if art else [""]
    while art_lines and not art_lines[-1].strip():
        art_lines.pop()
    w, h = visible_cols(art_lines or [""]), max(1, len(art_lines))
    scale = fit_scale_for(vp, w, h, fit=True)
    adv1, line1 = glyphs[0][1], glyphs[0][2]
    over_c = max(0, math.ceil((w * adv1 + 10 - out_w) / max(1, adv1)))
    over_l = max(0, h - px_h // max(1, line1))
    return GameFit(name, (full_w, full_h), (cols, lines), (w, h), round(scale, 3), (over_c, over_l))


def evaluate_all(art: str):
    return [evaluate(art, *p) for p in PRESETS]
