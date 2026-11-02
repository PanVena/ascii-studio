"""Налаштування студії (JSON у теці конфігу користувача): робочі теки, мова, тема, шорткати, вікно."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .core.files import atomic_write_text
from .paths import config_path


class Settings:
    """Тонка обгортка над словником; кожна зміна одразу зберігається (атомарно)."""

    def __init__(self, path: str | None = None):
        self.path = path or config_path()
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self._data = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self._data = {}
        dirs = self._data.get("dirs", [])
        self._data["dirs"] = [d for d in dirs if isinstance(d, dict) and "name" in d and "path" in d] if isinstance(dirs, list) else []
        self._clamp_active()

    def save(self) -> None:
        try:
            atomic_write_text(self.path, json.dumps(self._data, indent=2, ensure_ascii=False))
        except OSError:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if self._data.get(key) != value:
            self._data[key] = value
            self.save()

    @property
    def lang(self) -> str:
        return self._data.get("lang", "uk")

    @lang.setter
    def lang(self, value: str) -> None:
        self.set("lang", value)

    def dirs(self) -> List[dict]:
        return [dict(d) for d in self._data["dirs"]]

    @property
    def active_index(self) -> int:
        return self._data.get("active", 0)

    def _clamp_active(self) -> None:
        n = len(self._data["dirs"])
        try:
            active = int(self._data.get("active", 0))
        except (TypeError, ValueError):
            active = 0
        self._data["active"] = max(0, min(active, max(0, n - 1)))

    @property
    def current_dir(self) -> str:
        dirs = self._data["dirs"]
        if not dirs:
            return os.path.join(os.getcwd(), "ascii")
        return dirs[self.active_index]["path"]

    def set_active(self, idx: int) -> None:
        self._data["active"] = idx
        self._clamp_active()
        self.save()

    def add_dir(self, name: str, path: str) -> int:
        self._data["dirs"].append({"name": name, "path": path})
        self._data["active"] = len(self._data["dirs"]) - 1
        self.save()
        return self._data["active"]

    def rename_dir(self, idx: int, name: str) -> None:
        if 0 <= idx < len(self._data["dirs"]):
            self._data["dirs"][idx]["name"] = name
            self.save()

    def remove_dir(self, idx: int) -> None:
        if 0 <= idx < len(self._data["dirs"]):
            self._data["dirs"].pop(idx)
            self._clamp_active()
            self.save()

    def dir_index_for(self, path: str) -> tuple[int, str]:
        """Робоча тека, що містить path (найглибша), і відносна підтека; (-1, "") — поза теками."""
        norm = os.path.normpath(path)
        best = (-1, "", -1)
        for i, d in enumerate(self._data["dirs"]):
            base = os.path.normpath(d["path"])
            if norm == base:
                return i, ""
            if norm.startswith(base + os.sep) and len(base) > best[2]:
                best = (i, os.path.relpath(norm, base), len(base))
        return best[0], best[1]

    def shortcut_overrides(self) -> Dict[str, str]:
        data = self._data.get("shortcuts", {})
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(data, dict) else {}

    def set_shortcut_overrides(self, overrides: Dict[str, str]) -> None:
        self.set("shortcuts", dict(overrides))


_instance: Settings | None = None


def get() -> Settings:
    global _instance
    if _instance is None:
        _instance = Settings()
    return _instance


def reset(path: str | None = None) -> Settings:
    """Перечитати налаштування (тести / зміна шляху конфігу)."""
    global _instance
    _instance = Settings(path)
    return _instance
