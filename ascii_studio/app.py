"""Точка входу: QApplication, тема, мова, головне вікно; файли з командного рядка відкриваються як полотна."""
import os
import sys


def main(argv=None) -> int:
    if sys.platform.startswith("linux"):
        os.environ["QT_QPA_PLATFORMTHEME"] = ""
    argv = list(sys.argv if argv is None else argv)

    from PySide6.QtWidgets import QApplication

    from . import i18n, settings, theme
    from .ui.studio import StudioWindow

    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("ASCII Studio")
    app.setOrganizationName("ascii_studio")
    theme.apply(app)
    i18n.load(settings.get().lang)
    win = StudioWindow()
    for path in argv[1:]:
        if os.path.isfile(path):
            win.open_path(os.path.abspath(path))
    win.show()
    from PySide6.QtCore import QTimer
    from .ui.dialogs.promo import should_show
    if should_show():
        QTimer.singleShot(400, lambda: win.show_wishlist(startup=True))
    return app.exec()
