"""Bootstrap: offscreen Qt і окремий конфіг ДО будь-якого імпорту PySide6/студії."""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ASCII_STUDIO_CONFIG"] = os.path.join(tempfile.mkdtemp(prefix="ascii_studio_test_"), "config.json")

_here = os.path.dirname(os.path.abspath(__file__))
while _here != os.path.dirname(_here) and not os.path.isfile(os.path.join(_here, "ascii_studio", "__init__.py")):
    _here = os.path.dirname(_here)
if _here not in sys.path:
    sys.path.insert(0, _here)

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def app():
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def studio(app, tmp_path, monkeypatch):
    from ascii_studio import settings, shortcuts
    settings.reset(str(tmp_path / "config.json"))
    shortcuts.reset_manager()
    from ascii_studio.ui.studio import StudioWindow
    win = StudioWindow()
    yield win
    for ed in list(win.workspace.editors()):
        ed.mark_clean()
    win.close()
    win.deleteLater()
    app.processEvents()


def show(app, win, widget=None):
    """Показати вікно й віддати фокус (offscreen: show → processEvents → activateWindow → setFocus)."""
    win.show()
    app.processEvents()
    win.activateWindow()
    if widget is not None:
        widget.setFocus()
    app.processEvents()
