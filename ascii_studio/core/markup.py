"""Перевірка розмітки арту (чиста логіка, без Qt).

Формат: <b> <i> <u> <s> і <color:RRGGBB>, закриття — </b> … </color>. Помилки:
  * незакритий відкриваючий тег (усе далі покажеться як текст);
  * закриваючий тег без пари або перехрещені теги.
Вкладений <color> — попередження: перемагає внутрішній, але так легко помилитися.
"""
import re
from typing import List, NamedTuple

from ..i18n import tr

_TOKEN = re.compile(r"</(?:b|i|u|s|color)>|<(?:b|i|u|s)>|<color:[0-9a-fA-F]{6}>")
_BAD_COLOR = re.compile(r"<color:(?![0-9a-fA-F]{6}>)[^>\n]*>")


class Problem(NamedTuple):
    start: int
    end: int
    level: str   # "error" | "warning"
    message: str


def check_markup(text: str) -> List[Problem]:
    problems: List[Problem] = []
    stack = []  # (kind, start, end)
    for m in _TOKEN.finditer(text):
        tag = m.group(0)
        if tag.startswith("</"):
            kind = tag[2:-1]
            if stack and stack[-1][0] == kind:
                stack.pop()
            elif any(k == kind for k, _, _ in stack):
                problems.append(Problem(m.start(), m.end(), "error",
                                        tr("markup_crossed", tag=tag, open=stack[-1][0])))
            else:
                problems.append(Problem(m.start(), m.end(), "error", tr("markup_unopened", tag=tag)))
        else:
            kind = "color" if tag.startswith("<color:") else tag[1:-1]
            if kind == "color" and any(k == "color" for k, _, _ in stack):
                problems.append(Problem(m.start(), m.end(), "warning",
                                        tr("markup_nested_color")))
            stack.append((kind, m.start(), m.end()))
    for kind, s, e in stack:
        problems.append(Problem(s, e, "error", tr("markup_unclosed", kind=kind)))
    for m in _BAD_COLOR.finditer(text):
        problems.append(Problem(m.start(), m.end(), "error", tr("markup_bad_color")))
    return sorted(problems)
