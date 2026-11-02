"""Головне вікно ASCII Art Studio: режими FIGlet / усі шрифти / полотно, меню, інструменти, статус."""
from __future__ import annotations

import os
from typing import Dict, Optional

from PySide6.QtCore import QByteArray, QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox,
    QSizePolicy, QSpinBox, QSplitter, QTabWidget, QTextEdit, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__, figlet, i18n, settings, shortcuts
from ..core import files, markup, mirror, textgrid
from ..core.layers import CanvasLayers, Layer
from ..i18n import tr
from ..paths import resource_path
from ..theme import DEFAULT_THEME, THEME, apply as apply_theme
from .canvas import DEFAULT_POINT_SIZE, CanvasEditor, CanvasTools, _u16
from .dialogs.animation import AnimationDialog
from .dialogs.files import ArtPickerDialog, CanvasSizeDialog, SaveDialog
from .dialogs.info import ColorPreviewDialog, GameFitDialog
from .dialogs.mirror import MirrorWindow
from .dialogs.promo import STEAM_URL, WishlistDialog
from .open_url import open_folder
from .dialogs.shortcuts_dialog import ShortcutsDialog
from .panels import BrushBar, CharPalette, ColorBar, FigletPanel, LayersPanel, ThemePicker, braille_bar, framed
from .widgets import ArtView, panel
from .workspace import Workspace

MODE_FIGLET, MODE_FONTS, MODE_CANVAS = 0, 1, 2
REPO_URL = "https://github.com/PanVena/ascii-studio"
GUIDE_COL_MAX = 1000


class StudioWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_theme()
        self.setObjectName("studio")
        self.setWindowTitle(tr("app_title"))
        self.setAcceptDrops(True)
        icon = resource_path("icon.png")
        if os.path.exists(icon):
            self.setWindowIcon(QIcon(icon))
        self.resize(1280, 780)
        self._st = settings.get()
        self._mirror: Optional[MirrorWindow] = None
        self._watched: Optional[CanvasEditor] = None
        self._fonts_job: list = []
        self.tools = CanvasTools(self)
        self.actions_by_id: Dict[str, QAction] = {}
        self._create_actions()
        self.workspace = Workspace(self, list(self.actions_by_id.values()))
        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self._build_status()
        self._wire()
        self._restore_state()
        if not list(self.workspace.editors()):
            self.new_canvas()
        self._render_figlet()

    # ── дії ─────────────────────────────────────────────────────────────────

    def _create_actions(self) -> None:
        mgr = shortcuts.manager()
        slots = {
            "file.new": self.new_canvas, "file.new_sized": self.new_sized_canvas, "file.open": self.open_from_dir,
            "file.open_path": self.open_from_path, "file.save": self.save_current, "file.save_to_dir": self.save_to_dir,
            "file.export": self.export_as, "file.close_tab": self.close_current_tab, "file.quit": self.close,
            "edit.copy_art": self.copy_art, "edit.duplicate": self.duplicate_canvas, "edit.import_figlet": self.import_figlet,
            "edit.pad": self.pad_canvas, "edit.trim": self.trim_canvas, "edit.clear": self.clear_canvas,
            "edit.flip_h": lambda: self.flip(mirror.H), "edit.flip_v": lambda: self.flip(mirror.V),
            "edit.rotate": lambda: self.flip(mirror.HV),
            "tools.eraser": self.select_eraser, "tools.symmetry": lambda: self.brush_bar.cycle_symmetry(),
            "view.mode_figlet": lambda: self.set_mode(MODE_FIGLET), "view.mode_fonts": lambda: self.set_mode(MODE_FONTS),
            "view.mode_canvas": lambda: self.set_mode(MODE_CANVAS), "view.detach": self.detach_current,
            "view.game_fit": self.show_game_fit, "view.color_preview": self.show_color_preview,
            "view.animation": self.show_animation, "view.zoom_in": lambda: self.zoom(1),
            "view.zoom_out": lambda: self.zoom(-1), "view.zoom_reset": lambda: self.zoom(0),
            "view.next_tab": lambda: self.workspace.cycle(1), "view.prev_tab": lambda: self.workspace.cycle(-1),
            "layers.add": self.layer_add, "layers.up": lambda: self.layer_move(1), "layers.down": lambda: self.layer_move(-1),
            "help.shortcuts": self.show_shortcuts,
        }
        toggles = {
            "tools.brush": self.set_brush, "tools.braille": self._toggle_bar("braille"),
            "tools.colors": self._toggle_bar("colors"), "tools.chars": self._toggle_bar("chars"),
            "view.layers": self.set_layers_visible, "view.split": self.set_split, "view.mirror": self.set_mirror_visible,
        }
        for spec in shortcuts.SPECS:
            if spec.scope != shortcuts.APP:
                continue
            if spec.id in toggles:
                act = mgr.make_action(spec.id, self, checkable=True)
                act.toggled.connect(toggles[spec.id])
            else:
                slot = slots[spec.id]
                act = mgr.make_action(spec.id, self, lambda _=False, f=slot: f())
            self.addAction(act)
            self.actions_by_id[spec.id] = act
        self.act_layer_rename = QAction(tr("act_layers_rename"), self)
        self.act_layer_rename.triggered.connect(self.layer_rename)
        self.act_layer_remove = QAction(tr("act_layers_remove"), self)
        self.act_layer_remove.triggered.connect(self.layer_remove)
        self.act_about = QAction(tr("act_help_about"), self)
        self.act_about.triggered.connect(self.show_about)
        self.act_wishlist = QAction(tr("act_help_wishlist"), self)
        self.act_wishlist.triggered.connect(self.show_wishlist)
        self.tools.context_actions = [self.act(i) for i in ("edit.flip_h", "edit.flip_v", "edit.rotate")] + [
            None, self.act("edit.pad"), self.act("edit.trim"), self.act("view.mirror")]

    def act(self, id_: str) -> QAction:
        return self.actions_by_id[id_]

    def _toggle_bar(self, key: str):
        return lambda on: self._bars[key].setVisible(on)

    # ── побудова інтерфейсу ─────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("studio_root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)
        self.split = QSplitter(Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        lay.addWidget(self.split, 1)

        left, ll = panel(margins=(6, 6, 6, 6))
        left.setMinimumWidth(220)
        left.setMaximumWidth(460)
        self.figlet_panel = FigletPanel()
        ll.addWidget(self.figlet_panel)
        for key in ("edit.copy_art", "file.save_to_dir", "file.export", "edit.import_figlet"):
            self.figlet_panel.add_button(self.act(key))
        self.left_panel = left
        self.split.addWidget(left)

        self.modes = QTabWidget()
        self.output = ArtView(10)
        self.modes.addTab(self.output, tr("tab_result"))
        fonts_page = QWidget()
        fl = QVBoxLayout(fonts_page)
        fl.setContentsMargins(0, 0, 0, 0)
        self.preview_all = ArtView(9)
        fl.addWidget(self.preview_all)
        self.modes.addTab(fonts_page, tr("tab_all_fonts"))
        self.modes.addTab(self._build_canvas_page(), tr("tab_canvas"))
        self.split.addWidget(self.modes)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([280, 1000])

    def _build_canvas_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.vsplit = QSplitter(Qt.Vertical)
        self.hsplit = QSplitter(Qt.Horizontal)
        self.hsplit.addWidget(self.workspace.main)
        layer_actions = {"add": self.act("layers.add"), "up": self.act("layers.up"), "down": self.act("layers.down"),
                         "rename": self.act_layer_rename, "remove": self.act_layer_remove}
        self.layers_panel = LayersPanel(layer_actions)
        self.layers_frame = framed(self.layers_panel)
        self.hsplit.addWidget(self.layers_frame)
        self.hsplit.addWidget(self.workspace.compare)
        self.hsplit.setStretchFactor(0, 1)
        self.hsplit.setStretchFactor(2, 1)
        self.vsplit.addWidget(self.hsplit)
        comp, cl = panel(margins=(2, 2, 2, 2))
        head = QLabel(tr("lbl_composite"))
        head.setObjectName("section")
        cl.addWidget(head)
        self.composite_view = ArtView(10)
        cl.addWidget(self.composite_view)
        self.composite_frame = comp
        self.vsplit.addWidget(comp)
        self.vsplit.setStretchFactor(0, 1)
        self.vsplit.setSizes([640, 140])
        lay.addWidget(self.vsplit, 1)

        self.brush_bar = BrushBar()
        self.color_bar = ColorBar()
        self.braille = braille_bar(self.insert_text)
        self.char_palette = CharPalette()
        self._bars = {
            "brush": framed(self.brush_bar), "colors": framed(self.color_bar),
            "braille": framed(self.braille), "chars": framed(self.char_palette),
        }
        for key in ("brush", "colors", "braille", "chars"):
            lay.addWidget(self._bars[key])
            self._bars[key].setVisible(key == "chars")
        self.layers_frame.setVisible(False)
        self.composite_frame.setVisible(False)
        return page

    def _build_menus(self) -> None:
        mb = self.menuBar()
        a = self.act

        m = mb.addMenu(tr("menu_file"))
        for key in ("file.new", "file.new_sized", None, "file.open", "file.open_path"):
            m.addAction(a(key)) if key else m.addSeparator()
        self.recent_menu = m.addMenu(tr("menu_recent"))
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        for key in (None, "file.save", "file.save_to_dir", "file.export", None, "file.close_tab", "file.quit"):
            m.addAction(a(key)) if key else m.addSeparator()

        m = mb.addMenu(tr("menu_edit"))
        for key in ("edit.copy_art", "edit.duplicate", "edit.import_figlet", None, "edit.flip_h", "edit.flip_v",
                    "edit.rotate", None, "edit.pad", "edit.trim", "edit.clear"):
            m.addAction(a(key)) if key else m.addSeparator()
        m.addSeparator()
        block = m.addMenu(tr("menu_block"))
        for spec in shortcuts.SPECS:
            if spec.group == "block" and not spec.id.startswith("block.palette_"):
                act = QAction(spec.label, block)
                act.triggered.connect(lambda _=False, i=spec.id: self._canvas_action(i))
                act.setProperty("hint_id", spec.id)
                block.addAction(act)
        block.aboutToShow.connect(lambda: self._refresh_hint_texts(block))

        m = mb.addMenu(tr("menu_tools"))
        for key in ("tools.brush", "tools.eraser", "tools.symmetry", None, "tools.chars", "tools.colors", "tools.braille"):
            m.addAction(a(key)) if key else m.addSeparator()

        m = mb.addMenu(tr("menu_view"))
        for key in ("view.mode_figlet", "view.mode_fonts", "view.mode_canvas", None, "view.layers", "view.split",
                    "view.detach", "view.mirror", None, "view.game_fit", "view.color_preview", "view.animation", None,
                    "view.zoom_in", "view.zoom_out", "view.zoom_reset", None, "view.next_tab", "view.prev_tab"):
            m.addAction(a(key)) if key else m.addSeparator()
        m.addSeparator()
        m.addAction(tr("menu_guide_col"), self.choose_guide_col)
        self.theme_menu = m.addMenu(tr("menu_theme"))

        m = mb.addMenu(tr("menu_layers"))
        for act in (a("layers.add"), a("layers.up"), a("layers.down"), self.act_layer_rename, self.act_layer_remove):
            m.addAction(act)

        m = mb.addMenu(tr("menu_dirs"))
        m.addAction(tr("menu_add_dir"), self.work_dir_add)
        m.addAction(tr("menu_rename_dir"), self.work_dir_rename)
        m.addAction(tr("menu_remove_dir"), self.work_dir_remove)
        m.addAction(tr("menu_open_dir"), self.work_dir_open)
        m.addSeparator()
        m.addAction(tr("menu_language"), self.choose_language)

        m = mb.addMenu(tr("menu_help"))
        m.addAction(a("help.shortcuts"))
        m.addAction(self.act_wishlist)
        m.addAction(self.act_about)

    def _refresh_hint_texts(self, menu: QMenu) -> None:
        mgr = shortcuts.manager()
        for act in menu.actions():
            id_ = act.property("hint_id")
            if id_:
                key = mgr.display(id_)
                act.setText(shortcuts.BY_ID[id_].label + (f"\t{key}" if key else ""))

    def _build_toolbar(self) -> None:
        tb = QToolBar(tr("toolbar_main"))
        tb.setObjectName("main_toolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(tb)
        groups = (("file.new", "file.new_sized", "file.open", "file.save"),
                  ("edit.duplicate", "edit.import_figlet"),
                  ("tools.brush", "tools.chars", "tools.colors", "tools.braille"),
                  ("view.mirror", "edit.flip_h", "edit.flip_v"),
                  ("view.layers", "view.split", "view.animation", "view.game_fit", "view.color_preview"))
        for gi, group in enumerate(groups):
            if gi:
                tb.addSeparator()
            for key in group:
                act = self.act(key)
                act.setIconText(tr("tb_" + key.replace(".", "_")))
                tb.addAction(act)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addWidget(QLabel(tr("lbl_theme")))
        self.theme_picker = ThemePicker()
        tb.addWidget(self.theme_picker)
        tb.addSeparator()
        tb.addWidget(QLabel(tr("lbl_workdir")))
        self.work_dir_combo = QComboBox()
        self.work_dir_combo.setMinimumWidth(120)
        self.work_dir_combo.setMaximumWidth(220)
        self.work_dir_combo.setToolTip(tr("tt_workdir"))
        tb.addWidget(self.work_dir_combo)
        manage = QToolButton()
        manage.setText("⚙")
        manage.setToolTip(tr("tt_manage"))
        manage.setPopupMode(QToolButton.InstantPopup)
        manage.setFocusPolicy(Qt.NoFocus)
        dm = QMenu(manage)
        dm.addAction(tr("menu_add_dir"), self.work_dir_add)
        dm.addAction(tr("menu_rename_dir"), self.work_dir_rename)
        dm.addAction(tr("menu_remove_dir"), self.work_dir_remove)
        dm.addAction(tr("menu_open_dir"), self.work_dir_open)
        manage.setMenu(dm)
        tb.addWidget(manage)
        self._refresh_work_dirs()

    def _build_status(self) -> None:
        sb = self.statusBar()
        self.lbl_stats = QLabel("")
        self.lbl_cursor = QLabel("")
        self.lbl_mode = QLabel("")
        self.lbl_markup = QLabel("")
        self.lbl_markup.setStyleSheet(f"color: {THEME['warning']};")
        for w in (self.lbl_stats, self.lbl_markup):
            sb.addWidget(w)
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(int(4 * 10), int(72 * 10))
        self.zoom_spin.setSingleStep(10)
        self.zoom_spin.setSuffix("%")
        self.zoom_spin.setKeyboardTracking(False)
        self.zoom_spin.setToolTip(tr("tt_zoom"))
        for w in (self.lbl_cursor, self.lbl_mode, self.zoom_spin):
            sb.addPermanentWidget(w)
        keys = QToolButton()
        keys.setDefaultAction(self.act("help.shortcuts"))
        keys.setText(tr("tt_kbd"))
        keys.setFocusPolicy(Qt.NoFocus)
        sb.addPermanentWidget(keys)

    def _wire(self) -> None:
        self._stats_timer = QTimer(self)
        self._stats_timer.setSingleShot(True)
        self._stats_timer.setInterval(80)
        self._stats_timer.timeout.connect(self._update_stats)
        self._figlet_timer = QTimer(self)
        self._figlet_timer.setSingleShot(True)
        self._figlet_timer.setInterval(150)
        self._figlet_timer.timeout.connect(self._render_figlet)
        self.figlet_panel.changed.connect(self._figlet_timer.start)
        self.modes.currentChanged.connect(self._on_mode_changed)
        self.workspace.current_changed.connect(self._on_current_changed)
        self.workspace.editors_changed.connect(self._ensure_canvas)
        self.workspace.main.tabCloseRequested.connect(lambda i: self.close_editor(self.workspace.main.widget(i)))
        self.workspace.compare.tabCloseRequested.connect(lambda i: self.close_editor(self.workspace.compare.widget(i)))
        self.theme_picker.changed.connect(self._on_theme)
        self.brush_bar.char_changed.connect(lambda ch: self.tools.update(brush_char=ch))
        self.brush_bar.symmetry_changed.connect(lambda s: self.tools.update(symmetry=s))
        self.char_palette.char_clicked.connect(self.insert_text)
        self.char_palette.palette_changed.connect(lambda chars: self.tools.update(palette=chars))
        self.tools.update(palette=self.char_palette.chars())
        self.color_bar.color_chosen.connect(self.insert_color_tag)
        self.color_bar.clear_requested.connect(self.remove_color_tags)
        self.zoom_spin.valueChanged.connect(lambda v: self._with_canvas(lambda c: c.set_point_size(v / 10)))
        self.work_dir_combo.currentIndexChanged.connect(self._on_work_dir_changed)
        self.act("tools.chars").setChecked(True)
        self._theme_group = QActionGroup(self)
        names = list(self.theme_picker.combo.itemText(i) for i in range(self.theme_picker.combo.count()))
        for i, name in enumerate(names):
            act = self.theme_menu.addAction(name)
            act.setCheckable(True)
            self._theme_group.addAction(act)
            act.triggered.connect(lambda _=False, idx=i: self.theme_picker.combo.setCurrentIndex(idx))
        self.theme_picker.combo.currentIndexChanged.connect(
            lambda i: self._theme_group.actions()[i].setChecked(True) if 0 <= i < len(self._theme_group.actions()) else None)

    # ── стан вікна ──────────────────────────────────────────────────────────

    def _restore_state(self) -> None:
        st = self._st
        geo = st.get("geometry")
        if isinstance(geo, str):
            self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
        self.theme_picker.set_theme(st.get("theme", DEFAULT_THEME), st.get("custom_colors"))
        acts = self._theme_group.actions()
        if 0 <= self.theme_picker.combo.currentIndex() < len(acts):
            acts[self.theme_picker.combo.currentIndex()].setChecked(True)
        guide = st.get("guide_col", 80)
        self.tools.update(guide_col=guide if isinstance(guide, int) and 0 <= guide <= GUIDE_COL_MAX else 80)
        font = st.get("figlet_font")
        if font:
            self.figlet_panel.set_font_name(font)
        mode = st.get("mode", MODE_CANVAS)
        self.set_mode(mode if mode in (MODE_FIGLET, MODE_FONTS, MODE_CANVAS) else MODE_CANVAS)
        self._on_mode_changed(self.modes.currentIndex())

    def _save_state(self) -> None:
        st = self._st
        st.set("geometry", bytes(self.saveGeometry().toBase64()).decode())
        st.set("theme", self.theme_picker.theme_name())
        st.set("custom_colors", self.theme_picker.custom_colors())
        st.set("figlet_font", self.figlet_panel.font_name())
        st.set("mode", self.modes.currentIndex())

    def closeEvent(self, event):
        dirty = [e for e in self.workspace.editors() if e.dirty]
        if dirty and not self._confirm_discard(dirty):
            event.ignore()
            return
        self._save_state()
        for win in list(self.workspace.detached):
            for ed in win.tabs.editors():
                ed.mark_clean()
            win.close()
        if self._mirror is not None:
            self._mirror.close()
        super().closeEvent(event)

    def _confirm_discard(self, editors) -> bool:
        names = "\n".join("• " + e.title for e in editors[:12])
        box = QMessageBox(QMessageBox.Warning, tr("msg_unsaved_title"), tr("msg_unsaved_body", names=names),
                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, self)
        box.button(QMessageBox.Save).setText(tr("btn_save_all"))
        box.button(QMessageBox.Discard).setText(tr("btn_discard"))
        box.button(QMessageBox.Cancel).setText(tr("btn_cancel"))
        ans = box.exec()
        if ans == QMessageBox.Cancel:
            return False
        if ans == QMessageBox.Save:
            return all(self.save(e) for e in editors)
        return True

    # ── режими ──────────────────────────────────────────────────────────────

    def set_mode(self, mode: int) -> None:
        self.modes.setCurrentIndex(mode)
        if mode == MODE_CANVAS:
            self._with_canvas(lambda c: c.setFocus())

    def _on_mode_changed(self, idx: int) -> None:
        self.left_panel.setVisible(idx != MODE_CANVAS)
        if idx == MODE_FONTS:
            self._start_fonts_preview()
        self._update_stats()

    def _render_figlet(self) -> None:
        if not figlet.AVAILABLE:
            self.output.setPlainText(tr("pyfiglet_missing") + "\n\n" + tr("pyfiglet_install"))
            return
        p = self.figlet_panel.params()
        try:
            result = figlet.render(p["text"], p["font"], p["width"], p["direction"], p["justify"])
        except figlet.FigletError as e:
            result = tr("msg_error_wrap", e=e)
        self._figlet_text = result
        if self.figlet_panel.line_numbers_cb.isChecked():
            lines = result.splitlines()
            w = len(str(len(lines) or 1))
            result = "\n".join(f"{i + 1:{w}} │ {l}" for i, l in enumerate(lines))
        self.output.setPlainText(result)
        if self.modes.currentIndex() == MODE_FONTS:
            self._start_fonts_preview()
        self._update_stats()

    def _start_fonts_preview(self) -> None:
        if not figlet.AVAILABLE:
            return
        p = self.figlet_panel.params()
        q = self.figlet_panel.font_search.text().strip().lower()
        self._fonts_job = [f for f in figlet.ALL_FONTS if q in f.lower()] if q else list(figlet.ALL_FONTS)
        self._fonts_params = (p["text"] if p["text"].strip() else "Hello", p["width"])
        self.preview_all.setPlainText("")
        QTimer.singleShot(0, self._fonts_step)

    def _fonts_step(self) -> None:
        if not self._fonts_job or self.modes.currentIndex() != MODE_FONTS:
            return
        text, width = self._fonts_params
        chunk, self._fonts_job = self._fonts_job[:12], self._fonts_job[12:]
        parts = []
        for name in chunk:
            try:
                parts.append(f"{'─' * 60}\n  {name}\n{'─' * 60}\n{figlet.render(text, name, width)}")
            except figlet.FigletError:
                continue
        if parts:
            self.preview_all.appendPlainText("\n".join(parts))
        if self._fonts_job:
            QTimer.singleShot(0, self._fonts_step)

    # ── полотна ─────────────────────────────────────────────────────────────

    def current(self) -> Optional[CanvasEditor]:
        return self.workspace.current()

    def _with_canvas(self, fn):
        c = self.current()
        if c is not None:
            return fn(c)
        return None

    def make_editor(self, title: str, text: str = "", stack: Optional[CanvasLayers] = None, active_idx: int = 0,
                    file_path: str = "") -> CanvasEditor:
        ed = CanvasEditor(self.tools, title=title, stack=stack if stack is not None else CanvasLayers([Layer(title, True, text)]),
                          active_idx=active_idx, file_path=file_path)
        ed.message.connect(lambda msg: self.statusBar().showMessage(msg, 4000))
        return ed

    def add_canvas(self, title: str, text: str = "", **kw) -> CanvasEditor:
        ed = self.workspace.add(self.make_editor(title, text, **kw))
        self.set_mode(MODE_CANVAS)
        ed.setFocus()
        return ed

    def new_canvas(self) -> CanvasEditor:
        n = sum(1 for _ in self.workspace.editors()) + 1
        return self.add_canvas(tr("canvas_n", n=n))

    def new_sized_canvas(self) -> Optional[CanvasEditor]:
        dlg = CanvasSizeDialog(self, *self._st.get("canvas_size", (80, 24)))
        if dlg.exec() != CanvasSizeDialog.Accepted:
            return None
        w, h = dlg.canvas_size()
        self._st.set("canvas_size", [w, h])
        ed = self.add_canvas(tr("canvas_size_name", w=w, h=h), "\n".join(" " * w for _ in range(h)))
        ed.mark_clean()
        return ed

    def _ensure_canvas(self) -> None:
        split = self.act("view.split")
        split.blockSignals(True)
        split.setChecked(not self.workspace.compare.isHidden())
        split.blockSignals(False)
        if self.workspace.main.count() == 0 and not list(self.workspace.editors()):
            QTimer.singleShot(0, lambda: self.workspace.main.count() == 0 and self.new_canvas())

    def close_editor(self, editor) -> None:
        if not isinstance(editor, CanvasEditor):
            return
        if editor.dirty and not self._confirm_discard([editor]):
            return
        only = sum(1 for _ in self.workspace.editors()) == 1
        self.workspace.remove(editor)
        if only:
            self.new_canvas()

    def close_current_tab(self) -> None:
        self._with_canvas(self.close_editor)

    def detach_current(self) -> None:
        c = self.current()
        if c is not None and self.workspace.detach(c) is None:
            self.statusBar().showMessage(tr("msg_cannot_detach"), 4000)

    def duplicate_canvas(self) -> None:
        c = self.current()
        if c is None:
            return
        stack = CanvasLayers([Layer(l.name, l.visible, l.text) for l in c.layers.layers])
        taken = {e.title for e in self.workspace.editors()}
        folder = os.path.dirname(c.file_path) if c.file_path else self._st.current_dir
        taken |= {os.path.basename(n) for n in files.list_arts(folder)}
        base = os.path.basename(c.title)
        prefix = c.title[: len(c.title) - len(base)]
        title = prefix + files.next_copy_name(base, taken)
        ed = self.workspace.add(self.make_editor(title, stack=stack, active_idx=c.active_index()),
                                target=self.workspace.container_of(c) if self.workspace.container_of(c) in (self.workspace.main, self.workspace.compare) else None)
        ed.setFocus()

    def import_figlet(self) -> None:
        text = getattr(self, "_figlet_text", "")
        if not text.strip():
            self.statusBar().showMessage(tr("msg_figlet_empty"), 4000)
            return
        self.add_canvas(files.safe_name(self.figlet_panel.text_input.text(), 24), text.rstrip("\n"))

    def insert_text(self, text: str) -> None:
        c = self.current()
        if c is not None:
            c.insertPlainText(text)
            c.setFocus()

    def clear_canvas(self) -> None:
        c = self.current()
        if c is None or not c.toPlainText().strip():
            return
        if QMessageBox.question(self, tr("msg_clear_canvas"), tr("msg_clear_confirm")) == QMessageBox.Yes:
            cur = QTextCursor(c.document())
            cur.select(QTextCursor.Document)
            cur.removeSelectedText()

    def pad_canvas(self) -> None:
        self._with_canvas(lambda c: c.set_lines(textgrid.pad_to_rectangle(c.lines())))

    def trim_canvas(self) -> None:
        self._with_canvas(lambda c: c.set_lines(textgrid.trim(c.lines())))

    def flip(self, axis: str) -> None:
        self._with_canvas(lambda c: c.flip(axis))

    def _canvas_action(self, id_: str) -> None:
        c = self.current()
        if c is not None:
            c.setFocus()
            c.canvas_actions[id_].trigger()

    def zoom(self, steps: int) -> None:
        self._with_canvas(lambda c: c.set_point_size(DEFAULT_POINT_SIZE) if steps == 0 else c.zoom_by(steps))

    # ── інструменти ─────────────────────────────────────────────────────────

    def set_brush(self, on: bool) -> None:
        self.tools.update(brush=bool(on))
        self._bars["brush"].setVisible(bool(on))
        if self.act("tools.brush").isChecked() != bool(on):
            self.act("tools.brush").setChecked(bool(on))

    def select_eraser(self) -> None:
        self.act("tools.brush").setChecked(True)
        self.brush_bar.select_eraser()

    def insert_color_tag(self, hex_color: str) -> None:
        c = self.current()
        if c is None:
            return
        cur = c.textCursor()
        open_tag, close_tag = f"<color:{hex_color}>", "</color>"
        if cur.hasSelection():
            cur.insertText(open_tag + cur.selectedText().replace(" ", "\n") + close_tag)
        else:
            pos = cur.position()
            cur.insertText(open_tag + close_tag)
            cur.setPosition(pos + len(open_tag))
            c.setTextCursor(cur)
        c.setFocus()

    def remove_color_tags(self) -> None:
        c = self.current()
        if c is None:
            return
        cur = c.textCursor()
        if not cur.hasSelection():
            cur.select(QTextCursor.LineUnderCursor)
        text = cur.selectedText().replace(" ", "\n")
        cleaned = mirror.plain_text(text) if mirror.markup_ok(text) else text
        if cleaned != text:
            cur.insertText(cleaned)
        c.setFocus()

    def set_layers_visible(self, on: bool) -> None:
        self.layers_frame.setVisible(on)
        self.composite_frame.setVisible(on)
        self._update_composite()

    def set_split(self, on: bool) -> None:
        if on and self.workspace.compare.count() == 0:
            self.workspace.compare.setVisible(True)
            self.workspace.add(self.make_editor(tr("canvas_compare")), target=self.workspace.compare)
        else:
            self.workspace.set_split(on)
        if self.act("view.split").isChecked() != on:
            self.act("view.split").setChecked(on)

    def set_mirror_visible(self, on: bool) -> None:
        if on and self._mirror is None:
            self._mirror = MirrorWindow(self.workspace, self.tools, list(self.actions_by_id.values()), self)
            self._mirror.open_as_tab.connect(lambda title, text: self.add_canvas(title, text))
            self._mirror.installEventFilter(self)
        if self._mirror is not None:
            self._mirror.setVisible(on)
            if on:
                self._mirror.raise_()

    def eventFilter(self, obj, event):
        if obj is self._mirror and event.type() == QEvent.Hide and self.act("view.mirror").isChecked():
            self.act("view.mirror").setChecked(False)
        return super().eventFilter(obj, event)

    # ── шари ────────────────────────────────────────────────────────────────

    def _layer_target(self):
        c = self.current()
        if c is None:
            return None, None
        return c, (self.layers_panel.selected_layer() if self.layers_frame.isVisible() else None) or c.active_layer

    def layer_add(self) -> None:
        c = self.current()
        if c is not None:
            c.add_layer(f"{tr('layer_new')} {c.layers.count + 1}")
            if not self.act("view.layers").isChecked():
                self.act("view.layers").setChecked(True)
            c.setFocus()

    def layer_move(self, delta: int) -> None:
        c, layer = self._layer_target()
        if c is not None:
            c.move_layer(layer, delta)

    def layer_rename(self) -> None:
        c, layer = self._layer_target()
        if c is None:
            return
        name, ok = QInputDialog.getText(self, tr("msg_rename_layer"), tr("lbl_layer_name"), text=layer.name)
        if ok and name.strip():
            c.rename_layer(layer, name.strip())

    def layer_remove(self) -> None:
        c, layer = self._layer_target()
        if c is None:
            return
        if layer.text.strip() and QMessageBox.question(self, tr("msg_remove_layer"), tr("msg_remove_layer_body", name=layer.name)) != QMessageBox.Yes:
            return
        c.remove_layer(layer)

    # ── файли ───────────────────────────────────────────────────────────────

    def _write(self, path: str, editor: Optional[CanvasEditor], content: str) -> bool:
        try:
            files.atomic_write_text(path, content)
            if editor is not None:
                files.save_sidecar(path, editor.layers, editor.active_index())
        except OSError as e:
            QMessageBox.critical(self, tr("msg_write_error"), str(e))
            return False
        self._remember_recent(path)
        return True

    def _bind_file(self, editor: CanvasEditor, path: str) -> None:
        editor.file_path = path
        idx, rel = self._st.dir_index_for(path)
        editor.title = os.path.splitext(rel)[0].replace(os.sep, "/") if idx >= 0 and rel else os.path.splitext(os.path.basename(path))[0]
        editor.mark_clean()
        self.workspace.refresh_label(editor)

    def save(self, editor: CanvasEditor) -> bool:
        if editor.file_path and os.path.isdir(os.path.dirname(editor.file_path)):
            if not self._write(editor.file_path, editor, editor.composite_text()):
                return False
            editor.mark_clean()
            self.workspace.refresh_label(editor)
            self.statusBar().showMessage(tr("status_saved", name=editor.file_path), 4000)
            return True
        return self.save_to_dir(editor)

    def save_current(self) -> None:
        if self.modes.currentIndex() != MODE_CANVAS:
            self.save_to_dir()
            return
        self._with_canvas(self.save)

    def save_to_dir(self, editor: Optional[CanvasEditor] = None) -> bool:
        canvas_mode = editor is not None or self.modes.currentIndex() == MODE_CANVAS
        editor = editor or (self.current() if canvas_mode else None)
        content = editor.composite_text() if editor is not None else self.active_text()
        if not content.strip():
            self.statusBar().showMessage(tr("msg_empty_content"), 4000)
            return False
        if editor is not None:
            default = os.path.basename(editor.file_path)[:-4] if editor.file_path else os.path.basename(editor.title)
            initial = os.path.dirname(editor.file_path) if editor.file_path else self._st.current_dir
        else:
            default, initial = files.safe_name(self.figlet_panel.text_input.text()), self._st.current_dir
        dlg = SaveDialog(files.safe_name(default), self, initial_dir=initial)
        if dlg.exec() != SaveDialog.Accepted:
            return False
        path = dlg.get_result()
        if not path:
            return False
        if os.path.exists(path) and path != (editor.file_path if editor else "") and QMessageBox.question(
                self, tr("msg_file_exists"), tr("msg_file_exists_body", name=os.path.basename(path))) != QMessageBox.Yes:
            return False
        if not self._write(path, editor, content):
            return False
        if editor is not None:
            self._bind_file(editor, path)
        self.statusBar().showMessage(tr("status_saved", name=path), 5000)
        return True

    def export_as(self) -> None:
        canvas_mode = self.modes.currentIndex() == MODE_CANVAS
        editor = self.current() if canvas_mode else None
        start = editor.file_path if editor is not None and editor.file_path else self._st.current_dir
        path, _ = QFileDialog.getSaveFileName(self, tr("save_file_title"), start, tr("file_filter"))
        if not path:
            return
        if not path.lower().endswith(files.ART_EXT):
            path += files.ART_EXT
        content = editor.composite_text() if editor is not None else self.active_text()
        if self._write(path, editor, content):
            if editor is not None:
                self._bind_file(editor, path)
            self.statusBar().showMessage(tr("status_saved", name=path), 5000)

    def open_path(self, path: str) -> Optional[CanvasEditor]:
        for ed in self.workspace.editors():
            if ed.file_path and os.path.normpath(ed.file_path) == os.path.normpath(path):
                tabs = self.workspace.container_of(ed)
                tabs.setCurrentWidget(ed)
                self.set_mode(MODE_CANVAS)
                ed.setFocus()
                return ed
        try:
            content = files.read_text(path)
        except OSError as e:
            QMessageBox.critical(self, tr("msg_read_error"), str(e))
            return None
        sidecar = files.load_sidecar(path)
        name = os.path.splitext(os.path.basename(path))[0]
        if sidecar is not None:
            stack, active = sidecar
            ed = self.make_editor(name, stack=stack, active_idx=active)
        else:
            ed = self.make_editor(name, content)
        self._bind_file(ed, path)
        self.workspace.add(ed)
        self.set_mode(MODE_CANVAS)
        ed.setFocus()
        self._remember_recent(path)
        return ed

    def open_from_dir(self) -> None:
        dlg = ArtPickerDialog(self, colors=(self.tools.bg, self.tools.fg))
        if dlg.exec() == ArtPickerDialog.Accepted and dlg.selected_path:
            self.open_path(dlg.selected_path)

    def open_from_path(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, tr("open_file_title"), self._st.current_dir, tr("file_filter"))
        for p in paths:
            self.open_path(p)

    def _remember_recent(self, path: str) -> None:
        recent = [p for p in self._st.get("recent", []) if isinstance(p, str) and p != path]
        self._st.set("recent", [path] + recent[:9])

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        recent = [p for p in self._st.get("recent", []) if isinstance(p, str)]
        for p in recent:
            act = self.recent_menu.addAction(p)
            act.setEnabled(os.path.exists(p))
            act.triggered.connect(lambda _=False, path=p: self.open_path(path))
        if not recent:
            self.recent_menu.addAction(tr("menu_recent_empty")).setEnabled(False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(files.ART_EXT) for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(files.ART_EXT):
                self.open_path(p)
        event.acceptProposedAction()

    def active_text(self) -> str:
        mode = self.modes.currentIndex()
        if mode == MODE_FIGLET:
            return getattr(self, "_figlet_text", "")
        if mode == MODE_FONTS:
            return self.preview_all.toPlainText()
        c = self.current()
        return c.composite_text() if c is not None else ""

    def copy_art(self) -> None:
        text = self.active_text()
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(tr("status_copied", n=len(text.splitlines())), 3000)

    # ── вікна-помічники ─────────────────────────────────────────────────────

    def show_game_fit(self) -> None:
        text = self.active_text()
        if text.strip():
            GameFitDialog(text, self).exec()

    def show_color_preview(self) -> None:
        text = self.active_text()
        c = self.current()
        if text.strip():
            ColorPreviewDialog(text, (self.tools.bg, self.tools.fg), c.font().pointSizeF() if c else 12, self).exec()

    def show_animation(self) -> None:
        c = self.current()
        folder_idx, name = self._st.active_index, ""
        if c is not None:
            if c.file_path:
                idx, rel = self._st.dir_index_for(c.file_path)
                if idx >= 0:
                    folder_idx, name = idx, os.path.splitext(rel)[0].replace(os.sep, "/")
            name = name or c.title
        root, _n = files.split_root_number(name) if name else ("", None)
        folder = self._st.dirs()[folder_idx]["path"] if self._st.dirs() else self._st.current_dir
        series = files.numbered_series(files.list_arts(folder), root) if root else []
        AnimationDialog(series, 0.3, self, dir_index=folder_idx).exec()

    def show_shortcuts(self) -> None:
        ShortcutsDialog(self).exec()

    def show_about(self) -> None:
        QMessageBox.about(self, tr("about_title"),
                          tr("about_body", version=__version__, url=REPO_URL, steam=STEAM_URL))

    def show_wishlist(self, startup: bool = False) -> None:
        WishlistDialog(self, startup=startup).exec()

    # ── робочі теки / мова ──────────────────────────────────────────────────

    def _refresh_work_dirs(self) -> None:
        self.work_dir_combo.blockSignals(True)
        self.work_dir_combo.clear()
        for d in self._st.dirs():
            self.work_dir_combo.addItem(d["name"], d["path"])
            self.work_dir_combo.setItemData(self.work_dir_combo.count() - 1, d["path"], Qt.ToolTipRole)
        if not self._st.dirs():
            self.work_dir_combo.addItem(tr("no_dirs"), "")
        self.work_dir_combo.setCurrentIndex(self._st.active_index)
        self.work_dir_combo.blockSignals(False)

    def _on_work_dir_changed(self, idx: int) -> None:
        if 0 <= idx < len(self._st.dirs()):
            self._st.set_active(idx)

    def work_dir_add(self) -> None:
        start = self._st.current_dir if self._st.dirs() else os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, tr("dlg_add_dir"), start)
        if not path:
            return
        name, ok = QInputDialog.getText(self, tr("dlg_dir_name"), tr("dlg_dir_name_label"), text=os.path.basename(path))
        if ok and name.strip():
            self._st.add_dir(name.strip(), path)
            self._refresh_work_dirs()

    def work_dir_rename(self) -> None:
        idx, dirs = self.work_dir_combo.currentIndex(), self._st.dirs()
        if 0 <= idx < len(dirs):
            name, ok = QInputDialog.getText(self, tr("dlg_rename"), tr("dlg_new_name"), text=dirs[idx]["name"])
            if ok and name.strip():
                self._st.rename_dir(idx, name.strip())
                self._refresh_work_dirs()

    def work_dir_remove(self) -> None:
        idx, dirs = self.work_dir_combo.currentIndex(), self._st.dirs()
        if 0 <= idx < len(dirs) and QMessageBox.question(
                self, tr("msg_remove_dir"), tr("msg_remove_dir_body", name=dirs[idx]["name"])) == QMessageBox.Yes:
            self._st.remove_dir(idx)
            self._refresh_work_dirs()

    def work_dir_open(self) -> None:
        if self._st.dirs() and os.path.isdir(self._st.current_dir):
            open_folder(self._st.current_dir)

    def choose_guide_col(self) -> None:
        col, ok = QInputDialog.getInt(self, tr("dlg_guide_title"), tr("dlg_guide_label"),
                                      self.tools.guide_col, 0, GUIDE_COL_MAX)
        if ok:
            self.tools.update(guide_col=col)
            self._st.set("guide_col", col)

    def choose_language(self) -> None:
        codes = list(i18n.LANGUAGES)
        labels = [i18n.LANGUAGES[c] for c in codes]
        current = codes.index(self._st.lang) if self._st.lang in codes else 0
        choice, ok = QInputDialog.getItem(self, tr("dlg_lang_title"), tr("dlg_lang_label"), labels, current, False)
        if ok and codes[labels.index(choice)] != self._st.lang:
            self._st.lang = codes[labels.index(choice)]
            QMessageBox.information(self, tr("dlg_lang_title"), tr("msg_lang_restart"))

    # ── статус ──────────────────────────────────────────────────────────────

    def _on_theme(self, bg: str, fg: str) -> None:
        self.tools.update(bg=bg, fg=fg)
        for view in (self.output, self.preview_all, self.composite_view):
            view.set_colors(bg, fg)

    def _on_current_changed(self) -> None:
        c = self.current()
        if c is not self._watched:
            if self._watched is not None:
                for sig in (self._watched.cursorPositionChanged, self._watched.selectionChanged,
                            self._watched.layers_changed, self._watched.zoom_changed):
                    try:
                        sig.disconnect(self._stats_timer.start)
                    except (RuntimeError, TypeError):
                        pass
                try:
                    self._watched.layers_changed.disconnect(self._update_composite)
                except (RuntimeError, TypeError):
                    pass
            self._watched = c
            if c is not None:
                for sig in (c.cursorPositionChanged, c.selectionChanged, c.layers_changed, c.zoom_changed):
                    sig.connect(self._stats_timer.start)
                c.layers_changed.connect(self._update_composite)
            self.layers_panel.set_editor(c)
        self._update_composite()
        self._update_stats()

    def _update_composite(self) -> None:
        if self.composite_frame.isHidden():
            return
        c = self.current()
        text = c.composite_text() if c is not None else ""
        if self.composite_view.toPlainText() != text:
            self.composite_view.setPlainText(text)

    def _update_stats(self) -> None:
        if self.modes.currentIndex() != MODE_CANVAS:
            text = getattr(self, "_figlet_text", "")
            lines = text.splitlines()
            self.lbl_stats.setText(tr("stat_figlet", font=self.figlet_panel.font_name(), lines=len(lines),
                                      cols=textgrid.max_width(lines)))
            self.lbl_cursor.setText("")
            self.lbl_mode.setText("")
            self.lbl_markup.setText("")
            return
        c = self.current()
        if c is None:
            self.lbl_stats.setText("")
            return
        text = c.toPlainText()
        lines = text.split("\n")
        row, col = c.cursor_cell()
        cur = c.textCursor()
        sel = ""
        rect = c.selection_rect()
        if rect is not None:
            sel = tr("stat_sel_rect", w=rect.width, h=rect.height)
        elif cur.hasSelection():
            sel = tr("stat_sel", n=len(cur.selectedText()))
        self.lbl_stats.setText(tr("stat_canvas", tab=c.title, layer=c.active_layer.name, n=c.layers.count,
                                  lines=len(lines), w=textgrid.max_width(lines)) + sel)
        self.lbl_cursor.setText(tr("stat_cursor", row=row + 1, col=col + 1))
        flags = [tr("mode_ovr") if c.overwriteMode() else tr("mode_ins")]
        if self.tools.brush:
            flags.append(tr("mode_brush"))
        if self.tools.brush and self.tools.symmetry:
            flags.append(tr(f"sym_{self.tools.symmetry}"))
        self.lbl_mode.setText(" · ".join(flags))
        self.zoom_spin.blockSignals(True)
        self.zoom_spin.setValue(int(round(c.font().pointSizeF() * 10)))
        self.zoom_spin.blockSignals(False)
        self._markup(c, text)

    def _markup(self, c: CanvasEditor, text: str) -> None:
        problems = markup.check_markup(text)
        selections = []
        for pr in problems:
            sel = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.WaveUnderline)
            fmt.setUnderlineColor(QColor(THEME["error"] if pr.level == "error" else THEME["warning"]))
            fmt.setToolTip(pr.message)
            cur = QTextCursor(c.document())
            cur.setPosition(_u16(text, pr.start))
            cur.setPosition(_u16(text, pr.end), QTextCursor.KeepAnchor)
            sel.cursor = cur
            sel.format = fmt
            selections.append(sel)
        c.setExtraSelections(selections)
        if problems:
            self.lbl_markup.setText(tr("markup_problems", n=len(problems)))
            self.lbl_markup.setToolTip("\n".join(tr("markup_problems_tip", line=text.count("\n", 0, p.start) + 1, msg=p.message)
                                                 for p in problems[:15]))
        else:
            self.lbl_markup.setText("")
            self.lbl_markup.setToolTip("")
