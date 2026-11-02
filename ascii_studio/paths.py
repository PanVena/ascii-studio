import os
import sys

PACKAGE_NAME = "ascii_studio"


def resource_path(relative: str) -> str:
    """Абсолютний шлях до ресурсу пакета (розробка + PyInstaller)."""
    if getattr(sys, "frozen", False):
        base = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), PACKAGE_NAME)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


def config_path() -> str:
    """Файл налаштувань; ASCII_STUDIO_CONFIG перевизначає (тести, портативний режим)."""
    override = os.environ.get("ASCII_STUDIO_CONFIG")
    if override:
        return override
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, PACKAGE_NAME, "config.json")
