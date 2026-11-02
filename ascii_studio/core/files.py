"""Файлові операції студії: атомарний запис, пошук артів, sidecar шарів, назви (без Qt)."""
from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Iterable, List, Optional, Tuple

from .layers import CanvasLayers

ART_EXT = ".txt"
SIDECAR_EXT = ".layers.json"


def atomic_write_text(path: str, text: str) -> None:
    """Запис через тимчасовий файл + os.replace: збій посеред запису не обрізає файл."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=os.path.basename(path), dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().replace("\r\n", "\n")


def list_arts(folder: str) -> List[str]:
    """Відносні шляхи (через «/», без .txt) усіх артів у теці й підтеках."""
    names = []
    if not folder or not os.path.isdir(folder):
        return names
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for fn in files:
            if fn.endswith(ART_EXT) and not fn.startswith("."):
                rel = os.path.relpath(os.path.join(root, fn), folder).replace("\\", "/")
                names.append(rel[: -len(ART_EXT)])
    return sorted(names)


def sidecar_path(txt_path: str) -> str:
    return os.path.splitext(txt_path)[0] + SIDECAR_EXT


def save_sidecar(txt_path: str, stack: CanvasLayers, active_idx: int) -> None:
    """Пише шари поруч із .txt; для одношарового полотна застарілий sidecar видаляється."""
    path = sidecar_path(txt_path)
    if stack.count <= 1:
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass
        return
    data = stack.to_dict()
    data["active_idx"] = active_idx
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def load_sidecar(txt_path: str) -> Optional[Tuple[CanvasLayers, int]]:
    path = sidecar_path(txt_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    stack = CanvasLayers.from_dict(data)
    if stack.count == 0:
        return None
    try:
        active_idx = int(data.get("active_idx", 0))
    except (TypeError, ValueError, AttributeError):
        active_idx = 0
    if not 0 <= active_idx < stack.count:
        active_idx = 0
    return stack, active_idx


_UNSAFE = re.compile(r"[^\w\-]+", re.UNICODE)


def safe_parts(name: str) -> List[str]:
    """Розбиває «тека/ім'я» на безпечні частини (без «..», спецсимволів і розширення .txt)."""
    name = name.strip()
    if name.lower().endswith(ART_EXT):
        name = name[: -len(ART_EXT)]
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    return [(_UNSAFE.sub("_", p).strip("_") or "ascii") for p in parts]


def safe_name(text: str, limit: int = 40) -> str:
    return _UNSAFE.sub("_", text).strip("_")[:limit] or "ascii"


def split_root_number(name: str) -> Tuple[str, Optional[int]]:
    """«кадр_12» → («кадр», 12); без номера — (name, None)."""
    m = re.match(r"^(.+?)_(\d+)$", name)
    if m:
        return m.group(1), int(m.group(2))
    return name, None


def next_copy_name(base: str, taken: Iterable[str]) -> str:
    """Наступна вільна назва виду <корінь>_N."""
    root, n = split_root_number(base)
    taken = set(taken)
    k = (n + 1) if n is not None else 2
    while f"{root}_{k}" in taken:
        k += 1
    return f"{root}_{k}"


def numbered_series(names: Iterable[str], root: str) -> List[str]:
    """Імена <root>_N, відсортовані за N."""
    pattern = re.compile(rf"^{re.escape(root)}_(\d+)$")
    found = []
    for n in names:
        m = pattern.match(n)
        if m:
            found.append((int(m.group(1)), n))
    return [n for _, n in sorted(found)]
