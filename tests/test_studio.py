"""Студія: шорткати у всіх вікнах, дзеркало, файли, незбережені зміни, шари."""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QKeySequence, QTextCursor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ascii_studio import settings, shortcuts  # noqa: E402
from ascii_studio.core import files, mirror  # noqa: E402

from .conftest import show  # noqa: E402


def _key(widget, seq: str):
    comb = QKeySequence(seq)[0]
    QTest.keyClick(widget, comb.key(), comb.keyboardModifiers())
    QApplication.processEvents()


# ── реєстр ────────────────────────────────────────────────────────────────


def test_registry_has_no_default_conflicts(app):
    assert shortcuts.ShortcutManager().conflicts() == {}


def test_every_spec_has_label(app):
    for spec in shortcuts.SPECS:
        assert not spec.label.startswith("act_"), spec.id


def test_override_applies_to_bound_actions(app):
    mgr = shortcuts.ShortcutManager()
    from PySide6.QtGui import QAction
    act = mgr.bind(QAction("x"), "file.save")
    assert act.shortcut().toString() == "Ctrl+S"
    mgr.set_keys("file.save", ["Ctrl+Alt+F12"])
    assert act.shortcut().toString() == "Ctrl+Alt+F12"
    assert mgr.overrides_as_text() == {"file.save": "Ctrl+Alt+F12"}
    mgr.set_keys("file.save", ["Ctrl+S"])
    assert mgr.overrides_as_text() == {}


def test_conflict_detected(app):
    mgr = shortcuts.ShortcutManager({"file.new": "Ctrl+S"})
    assert set(mgr.conflicts()["Ctrl+S"]) == {"file.new", "file.save"}


# ── шорткати в різних вікнах ──────────────────────────────────────────────


def test_canvas_shortcuts_in_main_window(app, studio):
    c = studio.current()
    c.setPlainText("abcd\nefgh")
    show(app, studio, c)
    cur = c.textCursor()
    cur.setPosition(1)
    cur.setPosition(c._pos_of(1, 3), QTextCursor.KeepAnchor)
    c.setTextCursor(cur)
    _key(c, "Ctrl+Shift+C")
    assert QApplication.clipboard().text() == "bc\nfg"
    _key(c, "Ctrl+Shift+Del")
    assert c.lines() == ["a  d", "e  h"]


def test_tab_indents_in_canvas_but_not_elsewhere(app, studio):
    c = studio.current()
    c.setPlainText("x")
    show(app, studio, c)
    c.moveCursor(QTextCursor.Start)
    _key(c, "Tab")
    assert c.toPlainText() == "    x"
    studio.set_mode(0)
    show(app, studio, studio.figlet_panel.text_input)
    before = studio.figlet_panel.text_input.text()
    _key(studio.figlet_panel.text_input, "Tab")
    assert studio.figlet_panel.text_input.text() == before


def test_palette_alt_digit(app, studio):
    c = studio.current()
    show(app, studio, c)
    _key(c, "Alt+1")
    assert c.toPlainText() == studio.char_palette.chars()[0]


def test_app_shortcuts_in_detached_window(app, studio):
    studio.new_canvas()
    c = studio.current()
    c.setPlainText("┌")
    win = studio.workspace.detach(c)
    assert win is not None
    show(app, win, c)
    _key(c, "Ctrl+Alt+H")
    assert c.toPlainText() == "┐"
    n = len(list(studio.workspace.editors()))
    _key(c, "Ctrl+D")
    assert len(list(studio.workspace.editors())) == n + 1
    c.setPlainText("ab\ncd")
    cur = c.textCursor()
    cur.setPosition(0)
    cur.setPosition(4, QTextCursor.KeepAnchor)
    c.setTextCursor(cur)
    show(app, win, c)
    _key(c, "Ctrl+Shift+C")
    assert QApplication.clipboard().text() == "a\nc"
    win.close()
    assert studio.workspace.container_of(c) is studio.workspace.main


def test_shortcut_from_mirror_window(app, studio):
    studio.act("view.mirror").setChecked(True)
    mw = studio._mirror
    show(app, mw, mw.view)
    _key(mw.view, "Ctrl+B")
    assert studio.tools.brush


def test_canvas_yields_platform_bindings(app, studio):
    """Комбінації студії перемагають вбудовані прив'язки поля (ShortcutOverride не приймається)."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    c = studio.current()
    show(app, studio, c)
    for seq, expect in (("Ctrl+B", True), ("Ctrl+C", False), ("Ctrl+Z", False)):
        comb = QKeySequence(seq)[0]
        ev = QKeyEvent(QEvent.ShortcutOverride, comb.key(), comb.keyboardModifiers())
        assert shortcuts.manager().wants(ev) is expect, seq


def test_rebinding_takes_effect_everywhere(app, studio):
    mgr = shortcuts.manager()
    mgr.set_keys("block.copy", ["Ctrl+Alt+K"])
    c = studio.current()
    assert c.canvas_actions["block.copy"].shortcut().toString() == "Ctrl+Alt+K"
    mgr.reset()


# ── дзеркало ──────────────────────────────────────────────────────────────


def test_mirror_window_follows_selection_and_applies(app, studio):
    c = studio.current()
    c.setPlainText("╭─x\n│ab")
    studio.act("view.mirror").setChecked(True)
    mw = studio._mirror
    show(app, mw)
    mw.set_axis(mirror.H)
    mw.join_check.setChecked(False)
    c.selectAll()
    mw.refresh()
    assert mw.result()[0] == "x─╮\nda│"
    mw.apply()
    assert c.lines() == ["x─╮", "da│"]
    c.undo()
    assert c.lines() == ["╭─x", "│ab"]


def test_mirror_join_builds_symmetric_art(app, studio):
    c = studio.current()
    c.setPlainText("╭─\n│ ")
    studio.act("view.mirror").setChecked(True)
    mw = studio._mirror
    mw.source_combo.setCurrentIndex(mw.source_combo.findData("layer"))
    mw.set_axis(mirror.HV)
    mw.join_check.setChecked(True)
    out, region = mw.result()
    assert region == "layer"
    assert out.split("\n") == ["╭──╮", "│  │", "│  │", "╰──╯"]


def test_mirror_composite_cannot_apply(app, studio):
    c = studio.current()
    c.setPlainText("ab")
    studio.act("view.mirror").setChecked(True)
    mw = studio._mirror
    mw.source_combo.setCurrentIndex(mw.source_combo.findData("composite"))
    show(app, mw)
    mw.refresh()
    assert not mw.btn_apply.isEnabled() and mw.btn_tab.isEnabled()


# ── файли й стан ──────────────────────────────────────────────────────────


def test_save_and_reopen_with_layers(app, studio, tmp_path):
    c = studio.current()
    c.setPlainText("bottom")
    c.add_layer("top")
    c.insertPlainText("  T")
    path = str(tmp_path / "art.txt")
    assert studio._write(path, c, c.composite_text())
    studio._bind_file(c, path)
    assert not c.dirty and c.title == "art"
    with open(path, encoding="utf-8") as f:
        assert f.read() == "boTtom"
    studio.workspace.remove(c)
    ed = studio.open_path(path)
    assert [l.text for l in ed.layers] == ["bottom", "  T"] and ed.toPlainText() == "  T"
    assert studio.open_path(path) is ed


def test_quick_save_writes_bound_file(app, studio, tmp_path):
    path = str(tmp_path / "q.txt")
    files.atomic_write_text(path, "old")
    ed = studio.open_path(path)
    ed.setPlainText("new")
    assert ed.dirty
    studio.save(ed)
    assert not ed.dirty
    assert files.read_text(path) == "new"


def test_title_relative_to_work_dir(app, studio, tmp_path):
    settings.get().add_dir("art", str(tmp_path))
    path = str(tmp_path / "castle" / "door_1.txt")
    files.atomic_write_text(path, "x")
    ed = studio.open_path(path)
    assert ed.title == "castle/door_1"
    studio.duplicate_canvas()
    assert studio.current().title == "castle/door_2"


def test_close_dirty_tab_asks(app, studio, monkeypatch):
    c = studio.current()
    c.setPlainText("x")
    asked = []
    monkeypatch.setattr(studio, "_confirm_discard", lambda eds: asked.append(eds) or False)
    studio.close_editor(c)
    assert asked and studio.workspace.container_of(c) is not None


def test_closing_last_tab_leaves_fresh_canvas(app, studio):
    c = studio.current()
    studio.close_editor(c)
    app.processEvents()
    eds = list(studio.workspace.editors())
    assert len(eds) == 1 and eds[0] is not c


def test_split_and_layers_toggles(app, studio):
    studio.act("view.split").setChecked(True)
    assert not studio.workspace.compare.isHidden() and studio.workspace.compare.count() == 1
    studio.act("view.split").setChecked(False)
    assert studio.workspace.compare.isHidden()
    studio.act("view.layers").setChecked(True)
    assert not studio.layers_frame.isHidden()
    studio.layer_add()
    assert studio.current().layers.count == 2
    assert studio.layers_panel.tree.topLevelItemCount() == 2


def test_brush_toggle_shows_bar(app, studio):
    studio.act("tools.brush").setChecked(True)
    assert studio.tools.brush and not studio._bars["brush"].isHidden()
    studio.select_eraser()
    assert studio.tools.brush_char == " "
    studio.brush_bar.set_char("#")
    assert studio.tools.brush_char == "#"


def test_markup_problems_in_status(app, studio):
    c = studio.current()
    c.setPlainText("🔥<b>x")
    studio._update_stats()
    assert studio.lbl_markup.text()
    sel = c.extraSelections()[0]
    assert sel.cursor.selectedText() == "<b>"


def test_figlet_render_and_import(app, studio):
    if not studio.figlet_panel.isEnabled() or not getattr(studio, "_figlet_text", ""):
        pytest.skip("pyfiglet недоступний")
    n = len(list(studio.workspace.editors()))
    studio.import_figlet()
    assert len(list(studio.workspace.editors())) == n + 1
    assert studio.current().toPlainText().strip()


def test_settings_survive_restart(app, studio):
    studio.theme_picker.set_theme("Amber (Retro)")
    studio._save_state()
    settings.reset(settings.get().path)
    assert settings.get().get("theme") == "Amber (Retro)"


def test_game_fit_estimate(app):
    from ascii_studio import game_fit
    small = game_fit.evaluate("█" * 20, "x", 1920, 1080, False)
    huge = game_fit.evaluate("\n".join(["█" * 400] * 120), "x", 1280, 720, False)
    assert small.scale == 1.0 and small.overflow == (0, 0)
    assert huge.scale < 1.0 and huge.overflow != (0, 0)
    assert len(game_fit.evaluate_all("x")) == len(game_fit.PRESETS)


def test_wishlist_dialog_dont_show_again(studio):
    from ascii_studio import settings
    from ascii_studio.ui.dialogs import promo
    assert promo.should_show()
    dlg = promo.WishlistDialog(studio, startup=True)
    dlg.hide_box.setChecked(True)
    dlg.reject()
    assert not promo.should_show()
    # з меню — без прапорця, налаштування не чіпає
    dlg = promo.WishlistDialog(studio)
    dlg.reject()
    assert settings.get().get(promo.HIDE_KEY) is True


def test_open_url_uses_xdg_open_with_clean_env(monkeypatch):
    import sys
    from ascii_studio.ui import open_url as ou
    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(ou.shutil, "which", lambda name: "/usr/bin/xdg-open")
    monkeypatch.setattr(ou.subprocess, "Popen", lambda args, **kw: calls.append((args, kw["env"])))
    monkeypatch.setenv("QT_QPA_PLATFORMTHEME", "")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundle")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib")
    assert ou.open_url("https://example.com/")
    args, env = calls[0]
    assert args == ["/usr/bin/xdg-open", "https://example.com/"]
    assert "QT_QPA_PLATFORMTHEME" not in env
    assert env["LD_LIBRARY_PATH"] == "/usr/lib"


def test_guide_col_setting_persists(studio, monkeypatch):
    from ascii_studio import settings
    from ascii_studio.ui import studio as studio_mod
    assert studio.tools.guide_col == 80
    monkeypatch.setattr(studio_mod.QInputDialog, "getInt", staticmethod(lambda *a, **k: (0, True)))
    studio.choose_guide_col()
    assert studio.tools.guide_col == 0
    assert settings.get().get("guide_col") == 0
    monkeypatch.setattr(studio_mod.QInputDialog, "getInt", staticmethod(lambda *a, **k: (120, True)))
    studio.choose_guide_col()
    settings.reset(settings.get().path)
    studio.tools.update(guide_col=80)
    studio._restore_state()
    assert studio.tools.guide_col == 120
