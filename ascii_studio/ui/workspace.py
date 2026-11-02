"""Робочий простір полотен: основна панель, панель порівняння, від'єднані вікна.

Знає, яке полотно «поточне» (останнє у фокусі, де б воно не було), тож усі дії
студії працюють і у від'єднаних вікнах.
"""
from __future__ import annotations

import os
from typing import Iterator, List, Optional

from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QTabBar, QTabWidget, QWidget

from ..i18n import tr
from ..paths import resource_path
from .canvas import CanvasEditor


class DraggableTabBar(QTabBar):
    """Таб-бар, що повідомляє, коли вкладку відпустили поза ним."""
    released_outside = Signal(int, QPoint)

    def __init__(self):
        super().__init__()
        self.setMovable(True)
        self.setExpanding(False)
        self.setElideMode(Qt.ElideMiddle)
        self._pressed = -1
        self._outside = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = self.tabAt(event.position().toPoint())
            self._outside = False
        elif event.button() == Qt.MiddleButton:
            idx = self.tabAt(event.position().toPoint())
            if idx >= 0:
                self.tabCloseRequested.emit(idx)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pressed >= 0 and not self._outside and not self.rect().adjusted(-20, -20, 20, 20).contains(event.position().toPoint()):
            self._outside = True
            self.setCursor(Qt.DragMoveCursor)
            return
        if not self._outside:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pressed >= 0 and self._outside:
            idx, self._pressed, self._outside = self._pressed, -1, False
            self.unsetCursor()
            self.released_outside.emit(idx, event.globalPosition().toPoint())
            return
        self._pressed, self._outside = -1, False
        self.unsetCursor()
        super().mouseReleaseEvent(event)


class CanvasTabs(QTabWidget):
    released_outside = Signal(object, int, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        bar = DraggableTabBar()
        self.setTabBar(bar)
        self.setTabsClosable(True)
        self.setDocumentMode(False)
        bar.released_outside.connect(lambda i, p: self.released_outside.emit(self, i, p))

    def set_active(self, active: bool) -> None:
        if self.property("active") != active:
            self.setProperty("active", active)
            self.style().unpolish(self)
            self.style().polish(self)

    def editors(self) -> List[CanvasEditor]:
        return [w for w in (self.widget(i) for i in range(self.count())) if isinstance(w, CanvasEditor)]


def _tab_label(editor: CanvasEditor) -> str:
    return ("● " if editor.dirty else "") + editor.title


class DetachedWindow(QMainWindow):
    """Окреме вікно з вкладками полотен; закриття повертає їх у студію."""
    returned = Signal(object)

    def __init__(self, workspace: "Workspace"):
        super().__init__(None)
        self._ws = workspace
        self.tabs = CanvasTabs()
        self.tabs.tabCloseRequested.connect(self._return_index)
        self.tabs.currentChanged.connect(self._update_title)
        self.tabs.released_outside.connect(self._released_outside)
        self.setCentralWidget(self.tabs)
        icon = resource_path("icon.png")
        if os.path.exists(icon):
            self.setWindowIcon(QIcon(icon))
        self.resize(900, 600)
        self.addActions(workspace.window_actions)

    def place_next_to(self, studio: QWidget) -> None:
        sg = studio.frameGeometry()
        screen = studio.screen().availableGeometry()
        x, y = sg.right() + 10, sg.top()
        if x + self.width() > screen.right():
            x, y = max(screen.left(), sg.left() + 40), min(sg.top() + 40, screen.bottom() - self.height())
        self.move(x, y)

    def _update_title(self, *_):
        ed = self.tabs.currentWidget()
        title = ed.title if isinstance(ed, CanvasEditor) else tr("detached_window_title")
        self.setWindowTitle(f"{title} — ASCII Studio")

    def _return_index(self, idx: int) -> None:
        ed = self.tabs.widget(idx)
        if isinstance(ed, CanvasEditor):
            self.tabs.removeTab(idx)
            self.returned.emit(ed)
        if self.tabs.count() == 0:
            self.close()

    def _released_outside(self, _src, idx: int, gpos: QPoint) -> None:
        if not QRect(self.mapToGlobal(QPoint(0, 0)), self.size()).contains(gpos):
            self._return_index(idx)

    def closeEvent(self, event):
        while self.tabs.count():
            ed = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if isinstance(ed, CanvasEditor):
                self.returned.emit(ed)
        super().closeEvent(event)
        self._ws._forget_window(self)


class Workspace(QObject):
    """Усі контейнери полотен і поточне полотно."""
    current_changed = Signal()
    editors_changed = Signal()

    def __init__(self, window: QWidget, window_actions: list):
        super().__init__(window)
        self._window = window
        self.window_actions = window_actions
        self.main = CanvasTabs()
        self.compare = CanvasTabs()
        self.compare.setVisible(False)
        self.detached: List[DetachedWindow] = []
        self._current: Optional[CanvasEditor] = None
        self._active_panel = self.main
        for tabs in (self.main, self.compare):
            tabs.currentChanged.connect(lambda _i, t=tabs: self._on_tab_switched(t))
            tabs.released_outside.connect(self._on_released_outside)
        self._update_panels()

    # ── пошук ───────────────────────────────────────────────────────────────

    def containers(self) -> List[CanvasTabs]:
        return [self.main, self.compare] + [w.tabs for w in self.detached]

    def editors(self) -> Iterator[CanvasEditor]:
        for tabs in self.containers():
            yield from tabs.editors()

    def container_of(self, editor: CanvasEditor) -> Optional[CanvasTabs]:
        for tabs in self.containers():
            if tabs.indexOf(editor) >= 0:
                return tabs
        return None

    def current(self) -> Optional[CanvasEditor]:
        if self._current is not None and self.container_of(self._current) is not None:
            return self._current
        w = self._active_panel.currentWidget()
        return w if isinstance(w, CanvasEditor) else None

    @property
    def active_panel(self) -> CanvasTabs:
        return self._active_panel

    # ── зміни ───────────────────────────────────────────────────────────────

    def add(self, editor: CanvasEditor, target: Optional[CanvasTabs] = None, index: int = -1) -> CanvasEditor:
        target = target or (self._active_panel if self._active_panel in (self.main, self.compare) else self.main)
        if target is self.compare:
            self.compare.setVisible(True)
        editor.focused.connect(lambda e=editor: self._set_current(e))
        editor.dirty_changed.connect(lambda _d, e=editor: self.refresh_label(e))
        idx = target.insertTab(index, editor, _tab_label(editor)) if index >= 0 else target.addTab(editor, _tab_label(editor))
        target.setTabToolTip(idx, editor.file_path or editor.title)
        target.setCurrentIndex(idx)
        self._set_current(editor)
        self.editors_changed.emit()
        return editor

    def refresh_label(self, editor: CanvasEditor) -> None:
        tabs = self.container_of(editor)
        if tabs is not None:
            i = tabs.indexOf(editor)
            tabs.setTabText(i, _tab_label(editor))
            tabs.setTabToolTip(i, editor.file_path or editor.title)
            win = tabs.window()
            if isinstance(win, DetachedWindow):
                win._update_title()

    def remove(self, editor: CanvasEditor) -> None:
        tabs = self.container_of(editor)
        if tabs is None:
            return
        tabs.removeTab(tabs.indexOf(editor))
        editor.deleteLater()
        if self._current is editor:
            self._current = None
        if tabs is self.compare and tabs.count() == 0:
            self.set_split(False)
        win = tabs.window()
        if isinstance(win, DetachedWindow) and tabs.count() == 0:
            win.close()
        self.editors_changed.emit()
        self.current_changed.emit()

    def move(self, editor: CanvasEditor, dest: CanvasTabs) -> None:
        src = self.container_of(editor)
        if src is None or src is dest or (src is self.main and src.count() <= 1):
            return
        src.removeTab(src.indexOf(editor))
        if dest is self.compare:
            self.compare.setVisible(True)
        idx = dest.addTab(editor, _tab_label(editor))
        dest.setCurrentIndex(idx)
        if src is self.compare and src.count() == 0:
            self.set_split(False)
        self._set_current(editor)
        self.editors_changed.emit()

    def detach(self, editor: CanvasEditor) -> Optional[DetachedWindow]:
        src = self.container_of(editor)
        if src is None or isinstance(src.window(), DetachedWindow) or (src is self.main and src.count() <= 1):
            return None
        src.removeTab(src.indexOf(editor))
        win = DetachedWindow(self)
        win.returned.connect(self._on_returned)
        win.tabs.currentChanged.connect(lambda _i, t=win.tabs: self._on_tab_switched(t))
        idx = win.tabs.addTab(editor, _tab_label(editor))
        win.tabs.setCurrentIndex(idx)
        self.detached.append(win)
        win.place_next_to(self._window)
        win.show()
        editor.setFocus()
        if src is self.compare and src.count() == 0:
            self.set_split(False)
        self._set_current(editor)
        self.editors_changed.emit()
        return win

    def _on_returned(self, editor: CanvasEditor) -> None:
        idx = self.main.addTab(editor, _tab_label(editor))
        self.main.setCurrentIndex(idx)
        editor.show()
        self.editors_changed.emit()

    def _forget_window(self, win: DetachedWindow) -> None:
        if win in self.detached:
            self.detached.remove(win)
        self.current_changed.emit()

    def set_split(self, on: bool) -> None:
        self.compare.setVisible(on)
        if not on:
            for ed in self.compare.editors():
                self.compare.removeTab(self.compare.indexOf(ed))
                self.main.addTab(ed, _tab_label(ed))
            self._active_panel = self.main
            if self._current is None or self.container_of(self._current) is None:
                w = self.main.currentWidget()
                self._current = w if isinstance(w, CanvasEditor) else None
            self._update_panels()
            self.editors_changed.emit()
            self.current_changed.emit()

    def cycle(self, delta: int) -> None:
        ed = self.current()
        tabs = self.container_of(ed) if ed else self._active_panel
        if tabs is not None and tabs.count():
            tabs.setCurrentIndex((tabs.currentIndex() + delta) % tabs.count())
            w = tabs.currentWidget()
            if isinstance(w, CanvasEditor):
                w.setFocus()

    # ── внутрішнє ───────────────────────────────────────────────────────────

    def _set_current(self, editor: Optional[CanvasEditor]) -> None:
        tabs = self.container_of(editor) if editor is not None else None
        if tabs in (self.main, self.compare):
            self._active_panel = tabs
        changed = editor is not self._current
        self._current = editor
        self._update_panels()
        if changed:
            self.current_changed.emit()

    def _on_tab_switched(self, tabs: CanvasTabs) -> None:
        w = tabs.currentWidget()
        if isinstance(w, CanvasEditor):
            self._set_current(w)
        else:
            self.current_changed.emit()

    def _update_panels(self) -> None:
        both = not self.compare.isHidden()
        self.main.set_active(both and self._active_panel is self.main)
        self.compare.set_active(both and self._active_panel is self.compare)

    def _on_released_outside(self, src: CanvasTabs, idx: int, gpos: QPoint) -> None:
        editor = src.widget(idx)
        if not isinstance(editor, CanvasEditor):
            return
        dest = self.compare if src is self.main else self.main
        if not dest.isHidden() and QRect(dest.mapToGlobal(QPoint(0, 0)), dest.size()).contains(gpos):
            self.move(editor, dest)
            return
        if src is self.main and self.compare.isHidden() and src.count() > 1:
            tl = src.mapToGlobal(QPoint(0, 0))
            right = QRect(tl.x() + src.width() // 2, tl.y(), src.width() // 2, src.height())
            if right.contains(gpos):
                self.compare.setVisible(True)
                self.move(editor, self.compare)
                return
        if not QRect(self._window.mapToGlobal(QPoint(0, 0)), self._window.size()).contains(gpos):
            self.detach(editor)
