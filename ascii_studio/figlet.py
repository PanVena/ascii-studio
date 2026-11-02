"""FIGlet-рендер: шрифти pyfiglet + власні .flf з fonts/ пакета (без копіювання в site-packages)."""
from __future__ import annotations

import os
from typing import Dict, List

from .paths import resource_path

DIRECTIONS = ["auto", "left-to-right", "right-to-left"]
JUSTIFICATIONS = ["auto", "left", "center", "right"]
DEFAULT_FONT = "ansi_shadow_extended"

try:
    import pyfiglet as _pyfiglet
except Exception:
    _pyfiglet = None

AVAILABLE = _pyfiglet is not None


def _local_fonts() -> Dict[str, str]:
    folder = resource_path("fonts")
    out = {}
    if os.path.isdir(folder):
        for fn in os.listdir(folder):
            if fn.lower().endswith((".flf", ".tlf")):
                out[os.path.splitext(fn)[0]] = os.path.join(folder, fn)
    return out


LOCAL_FONTS = _local_fonts()

if AVAILABLE:
    class _Font(_pyfiglet.FigletFont):
        @classmethod
        def preloadFont(cls, font):
            path = LOCAL_FONTS.get(font)
            if path:
                with open(path, "rb") as f:
                    return f.read().decode("utf-8", "replace")
            return super().preloadFont(font)

    try:
        _system = list(_pyfiglet.FigletFont.getFonts())
    except Exception:
        _system = []
    ALL_FONTS: List[str] = sorted(set(_system) | set(LOCAL_FONTS))
else:
    ALL_FONTS = []


class FigletError(Exception):
    pass


def render(text: str, font: str = DEFAULT_FONT, width: int = 80, direction: str = "auto", justify: str = "auto") -> str:
    if not AVAILABLE:
        raise FigletError("pyfiglet")
    try:
        fig = _pyfiglet.Figlet(font="standard", direction=direction, justify=justify, width=width)
        fig.font = font
        fig.Font = _Font(font=font)
        return fig.renderText(text)
    except Exception as e:
        raise FigletError(str(e)) from e
