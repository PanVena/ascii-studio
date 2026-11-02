#!/usr/bin/env python3
"""Автономна збірка ASCII Art Studio (PyInstaller).

Запуск: python build.py (потрібен pyinstaller). Wrapper-вхід, щоб модулі пакета імпортувалися як `ascii_studio.*`
(відносні імпорти працюють у frozen-застосунок).
"""

import os
import subprocess
import sys
import tempfile

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.join(ROOT_DIR, "ascii_studio")
PARENT_DIR = ROOT_DIR
APP_NAME = "ASCIIStudio"


def main():
    sep = ";" if sys.platform == "win32" else ":"

    entry_dir = tempfile.mkdtemp(prefix="ascii_studio_build_")
    entry_path = os.path.join(entry_dir, f"{APP_NAME}_entry.py")
    with open(entry_path, "w", encoding="utf-8") as f:
        f.write("import sys\nfrom ascii_studio.app import main\n\nsys.exit(main())\n")

    cmd = ["pyinstaller", "--noconfirm", "--onedir"]

    for src, dest in [
        ("fonts", "ascii_studio/fonts"),
        ("locales", "ascii_studio/locales"),
        ("icon.png", "ascii_studio/icon.png"),
    ]:
        cmd.append(f"--add-data={os.path.join(PKG_DIR, src)}{sep}{dest}")

    cmd.extend(["--collect-all", "pyfiglet"])

    if sys.platform == "win32":
        cmd.append("--noconsole")
    elif sys.platform == "darwin":
        cmd.append("--windowed")
    else:
        cmd.append("--console")

    icon = os.path.join(PKG_DIR, "icon.png")
    if os.path.exists(icon):
        cmd.append(f"--icon={icon}")

    build_dir = os.path.join(ROOT_DIR, "build")
    cmd.extend([
        "--name", APP_NAME,
        f"--paths={PARENT_DIR}",
        f"--distpath={os.path.join(build_dir, 'dist')}",
        f"--workpath={os.path.join(build_dir, 'work')}",
        f"--specpath={build_dir}",
        "--exclude-module=PySide6.QtNetwork",
        "--exclude-module=PySide6.QtQml",
        "--exclude-module=PySide6.QtWebEngineCore",
        "--exclude-module=PySide6.QtWebEngineWidgets",
        "--exclude-module=PySide6.Qt3DCore",
        "--exclude-module=PySide6.Qt3DInput",
        "--exclude-module=PySide6.Qt3DLogic",
        "--exclude-module=PySide6.Qt3DRender",
        "--exclude-module=PySide6.QtSql",
        "--exclude-module=PySide6.QtTest",
        "--exclude-module=PySide6.QtBluetooth",
        "--exclude-module=PySide6.QtNfc",
        "--exclude-module=PySide6.QtQuick",
        "--exclude-module=PySide6.QtQuickWidgets",
        "--exclude-module=PySide6.QtMultimedia",
        "--exclude-module=PySide6.QtNetworkAuth",
        "--exclude-module=PySide6.QtPositioning",
        "--exclude-module=PySide6.QtSensors",
        "--exclude-module=PySide6.QtSerialPort",
        "--exclude-module=PySide6.QtTextToSpeech",
        "--exclude-module=PySide6.QtWebChannel",
        "--exclude-module=PySide6.QtWebSockets",
        "--exclude-module=tkinter",
        "--exclude-module=unittest",
        "--exclude-module=pytest",
    ])

    cmd.append(entry_path)

    print(f"[BUILD] Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
