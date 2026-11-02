"""Власна копія формули auto-fit рушія LazyEngine (Text/fit.py) — студія нічого не імпортує з гри.

Auto-fit масштаб ASCII — єдине джерело правди.

Усі fit-точки (ascii/animate_ascii/журнал у `Engine/Managers/renderer.py`,
`Text/figlet.py::animate_figlet_runs_fit`, перерахунок при resize у
`GameThread`, прев'ю Scene Editor) використовують ОДИН і той самий механізм:
вьюпорт терміналу (`Viewport`) + одна формула масштабу. Без винятків: ні
журналу, ні центрованого режиму, ні окремих точок рендеру.

Вьюпорт (`Viewport`) — окремий об'єкт, який обчислює кожен з двох режимів
виведення (нормальний / центрований) окремо (див. `Terminal/viewport.py`).
Формула масштабу — standalone, єдине джерело правди. Мінімум 40×10 —
захист від мікро-масштабу при перехідно-малих вимірах (напр. під час
переходу вікна у фулскрін)."""

import re
from dataclasses import dataclass


# Мінімальний розмір вьюпорту (захист від мікро-масштабу при перехідно-малих
# вимірах, напр. під час переходу вікна у фулскрін).
MIN_TERMINAL_COLS = 40
MIN_TERMINAL_LINES = 10


_MARKUP_RE = re.compile(r'<[^>]+>')


def strip_markup(text: str) -> str:
    """Remove inline markup tags (<b>, <color:RRGGBB>, etc.) from a string,
    returning only the visible characters. Used to measure true rendered width
    of ASCII art / text before computing fit scale."""
    return _MARKUP_RE.sub('', text)


def visible_cols(lines: list[str]) -> int:
    """Max visible (post-markup) width of a list of lines."""
    return max((len(strip_markup(ln)) for ln in lines), default=1)


@dataclass(frozen=True)
class Viewport:
    """Бюджет виведення в символах (для фіту).

    `cols`/`lines` — кількість символів, що вміщуються у вьюпорті при
    масштабі 1.0 (без зворотного зв'язку від поточного масштабу).
    Один і той самий бюджет для ВСІХ fit-точок — звичайного, центрованого
    режиму та журналу.

    Необов'язкове піксельне уточнення (заповнює GUI-шар): `px_w`/`px_h` —
    видима область тексту в пікселях, `glyphs` — таблиця реальних метрик
    ASCII-шрифту `((scale, advance_px, line_px), ...)` за спаданням scale.
    Qt хінтить advance до ЦІЛИХ пікселів, тому реальна ширина арту може
    перевищити теоретичну `cols × scale`; таблиця дозволяє це врахувати."""
    cols: int
    lines: int
    px_w: int = 0
    px_h: int = 0
    glyphs: tuple = ()


# 2 × documentMargin (4px) + 2px запасу на округлення
DOC_PAD_PX = 10


def refine_scale_to_pixels(viewport, scale, content_w, content_h):
    """Зменшує `scale` (ніколи не збільшує), доки арт `content_w × content_h`
    символів не вміщується в піксельний бюджет вьюпорту з урахуванням РЕАЛЬНИХ
    (цілопіксельних) метрик шрифту. Без таблиці метрик — повертає `scale`."""
    glyphs = getattr(viewport, "glyphs", ())
    if not glyphs or not viewport.px_w or not viewport.px_h or not content_w or not content_h:
        return scale

    def fits(adv, line_px):
        return content_w * adv + DOC_PAD_PX <= viewport.px_w and content_h * line_px <= viewport.px_h

    above = [g for g in glyphs if g[0] >= scale]
    if above:
        upper = min(above, key=lambda g: g[0])
        if fits(upper[1], upper[2]):
            return scale
    for s, adv, line_px in glyphs:
        if s < scale and fits(adv, line_px):
            return s
    return glyphs[-1][0] if glyphs[-1][0] < scale else scale


def compute_fit_scale(ref_cols, ref_lines, content_w, content_h):
    """Чиста формула: `min((ref_cols*0.95)/content_w, (ref_lines*0.95)/content_h)`.

    0.95 = запас від похибки округлення Qt-рендерингу; порожній/нульовий
    контент → 1.0 (без ділення на 0)."""
    scale_w = (ref_cols * 0.95) / content_w if content_w else 1.0
    scale_h = (ref_lines * 0.95) / content_h if content_h else 1.0
    return min(scale_w, scale_h)


def normalize_fit(fit):
    """Нормалізує параметр `fit` у множник масштабу.

    None/False → None (масштаб взагалі не застосовується); True → 1.0 (повний фіт);
    додатне число → його множник (напр. 0.5 = половина від обчисленого масштабу).
    Невалідні значення (0, від'ємні, не-числа) → None."""
    if fit is None or fit is False:
        return None
    if fit is True:
        return 1.0
    try:
        factor = float(fit)
    except (TypeError, ValueError):
        return None
    return factor if factor > 0 else None


def fit_scale(ref_cols, ref_lines, content_w, content_h, fit=True):
    """Єдиний вхід для масштабу: `compute_fit_scale` × нормалізований множник
    `fit`, кламплений до 1.0 — арт не масштабується вгору понад нативний
    розмір (лише down-scale).

    `fit`: None/False → 1.0 (масштаб не застосовується); True → повний фіт;
    число → множник."""
    factor = normalize_fit(fit)
    if factor is None:
        return 1.0
    return min(compute_fit_scale(ref_cols, ref_lines, content_w, content_h) * factor, 1.0)


def fit_scale_for(viewport, content_w, content_h, fit=True):
    """`fit_scale` від вьюпорту (`Viewport`) — один механізм для всіх fit-точок.

    `viewport` — `Viewport` (бюджет виведення в символах). None → 1.0
    (масштаб не застосовується)."""
    if viewport is None:
        return 1.0
    scale = fit_scale(viewport.cols, viewport.lines, content_w, content_h, fit=fit)
    if normalize_fit(fit) is None:
        return scale
    return refine_scale_to_pixels(viewport, scale, content_w, content_h)


def viewport_from(terminal_or_thread):
    """Отримує або будує `Viewport` з об'єкта терміналу / GameThread.

    Порядок пошуку:
    1. `.viewport` (GameThread у production) → повертає напряму.
    2. `.plain_cols` / `.plain_lines` (FakeTerminal у тестах, Console) → будує Viewport.
    3. Fallback: `Viewport(96, 38)` (безпечний дефолт).
    """
    if terminal_or_thread is None:
        return Viewport(96, 38)
    vp = getattr(terminal_or_thread, "viewport", None)
    if isinstance(vp, Viewport):
        return vp
    cols = getattr(terminal_or_thread, "plain_cols", None) or getattr(terminal_or_thread, "ascii_cols", 96)
    lines = getattr(terminal_or_thread, "plain_lines", None) or getattr(terminal_or_thread, "ascii_lines", 38)
    return Viewport(
        max(MIN_TERMINAL_COLS, int(cols)),
        max(MIN_TERMINAL_LINES, int(lines)),
    )
