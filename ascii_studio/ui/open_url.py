"""Надійне відкриття посилань і тек у системі.

QDesktopServices.openUrl на Linux часто мовчки не спрацьовує (вимкнена платформна тема, Wayland,
збірка PyInstaller із власним LD_LIBRARY_PATH, через який падає запущений браузер). Тому:
xdg-open із «чистим» оточенням → QDesktopServices → webbrowser.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

_PYI_VARS = ("LD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH",
             "QT_QPA_PLATFORMTHEME", "PYTHONHOME", "PYTHONPATH", "SSL_CERT_FILE")


def clean_env() -> dict:
    """Оточення для сторонньої програми: без підмін, які робить студія чи PyInstaller."""
    env = dict(os.environ)
    for key in _PYI_VARS:
        orig = env.pop(key + "_ORIG", None)  # PyInstaller зберігає початкові значення як *_ORIG
        if orig is not None:
            env[key] = orig
        elif getattr(sys, "frozen", False) or key == "QT_QPA_PLATFORMTHEME":
            env.pop(key, None)
    return env


def _xdg_open(target: str) -> bool:
    exe = shutil.which("xdg-open")
    if not exe:
        return False
    try:
        subprocess.Popen([exe, target], env=clean_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


def open_url(url: str) -> bool:
    """Відкрити веб-адресу у браузері; True — якщо хоч один спосіб запустився."""
    if sys.platform.startswith("linux") and _xdg_open(url):
        return True
    if QDesktopServices.openUrl(QUrl(url)):
        return True
    try:
        return webbrowser.open(url)
    except Exception:
        return False


def open_folder(path: str) -> bool:
    """Відкрити теку у файловому менеджері."""
    if sys.platform.startswith("linux") and _xdg_open(path):
        return True
    return QDesktopServices.openUrl(QUrl.fromLocalFile(path))
