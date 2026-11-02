# 🎨 ASCII Art Studio

A desktop editor for ASCII / Unicode art, built with PySide6.

> **This is the tool we use to draw the art for our game
> [Dungeon Revizor: The Game / Ревізор підземель](https://store.steampowered.com/app/4652870/Revizor_pidzemel/).**
> If the studio is useful to you, please ⭐ [add the game to your Steam wishlist](https://store.steampowered.com/app/4652870/Revizor_pidzemel/) — it helps a lot!
**[Українська версія нижче](#-ascii-art-studio-укр)**

- **FIGlet** — 570+ fonts with live preview, search and an “all fonts” gallery
- **Canvas** — tabs, split view, detachable windows, layers with a ghost underlay of the other layers
- **Brush** — click/drag painting anywhere (the canvas grows), any character, eraser, **symmetry** (⇋ ⇵ ✛)
- **Mirror** — live mirrored view of a selection / layer / composite; box-drawing, blocks, arrows,
  brackets and Braille are mapped to their mirrored counterparts; “join with original” turns a half into a symmetric art
- **Block editing** — rectangular copy / cut / paste (opaque or transparent), column insert/delete, flip in place
- **Color markup** — `<color:RRGGBB>…</color>`, `<b>`, `<i>`, `<u>`, `<s>` with live validation and preview
- **In-game fit** — will the art fit a LazyEngine game terminal on common screens (the studio keeps its own copy of the engine's fit formula, nothing is imported from the game)
- **Animation** — frame queue from numbered files, timeline, onion skin, smoothness analysis
- **Shortcuts everywhere** — one registry for menus, toolbar, canvases, detached windows and the mirror; all keys are
  rebindable (F1), and they keep working with non-Latin keyboard layouts
- Ukrainian and English UI

## Run

```bash
pip install -r requirements.txt
python -m ascii_studio            # or: python -m ascii_studio art.txt
```

or install it: `pip install .` → `ascii-studio`.

Standalone build: `pip install pyinstaller && python build.py` (output in `build/dist/`).

## Files

Arts are plain UTF-8 `.txt` files. A multi-layer canvas also writes `<name>.layers.json` next to the text file;
the `.txt` always contains the flattened composite, so other tools can read it.
Settings live in `~/.config/ascii_studio/config.json` (`%APPDATA%\ascii_studio` on Windows;
override with `ASCII_STUDIO_CONFIG`).

## Tests

```bash
QT_QPA_PLATFORM=offscreen python -m pytest
```

## License

GNU General Public License v2.0 only — see [LICENSE](LICENSE).
Bundled fonts keep their own licenses — see [ascii_studio/fonts/README_LICENSES.txt](ascii_studio/fonts/README_LICENSES.txt).

---

## 🎨 ASCII Art Studio (укр)

Редактор ASCII/Unicode-артів на PySide6.

> **Це інструмент, у якому ми малюємо арти для нашої гри
> [«Ревізор підземель» (Dungeon Revizor: The Game)](https://store.steampowered.com/app/4652870/Revizor_pidzemel/).**
> Якщо студія вам знадобилася — ⭐ [додайте гру до списку бажаного в Steam](https://store.steampowered.com/app/4652870/Revizor_pidzemel/), це дуже допомагає!

- **FIGlet** — 570+ шрифтів, живе прев'ю, пошук, галерея «усі шрифти»
- **Полотно** — вкладки, розділення на дві панелі, від'єднані вікна, шари з «привидом» інших шарів
- **Кисть** — малювання будь-де (полотно розширюється), будь-який символ, гумка, **симетрія** (⇋ ⇵ ✛)
- **Дзеркало** — живе відображення виділення / шару / композиту; рамки, блоки, стрілки, дужки й Брайль
  замінюються дзеркальними відповідниками; «склеїти з оригіналом» робить із половинки симетричний арт
- **Прямокутні операції** — копіювати/вирізати/вставити прямокутником (зокрема прозоро), колонки, переворот на місці
- **Кольорова розмітка** — `<color:RRGGBB>…</color>`, `<b>`, `<i>`, `<u>`, `<s>` з перевіркою та прев'ю
- **Як у грі** — чи влізе арт у термінал гри на LazyEngine на типових екранах (власна копія формули fit, із гри нічого не імпортується)
- **Анімація** — черга кадрів із пронумерованих файлів, шкала, «привид» попереднього кадру, аналіз плавності
- **Гарячі клавіші всюди** — один реєстр для меню, панелі, полотен, від'єднаних вікон і дзеркала; усе
  перепризначається (F1) і працює з кириличною розкладкою

Запуск: `pip install -r requirements.txt && python -m ascii_studio`. Ліцензія — GNU GPL v2.
