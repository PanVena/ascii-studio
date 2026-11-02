"""Віконце «Додайте Ревізора підземель до бажаного в Steam» — під час запуску та з меню «Довідка»."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
)

from ... import settings
from ...i18n import tr
from ..open_url import open_url

STEAM_URL = "https://store.steampowered.com/app/4652870/Revizor_pidzemel/"
HIDE_KEY = "hide_wishlist_popup"


def should_show() -> bool:
    return not settings.get().get(HIDE_KEY, False)


class WishlistDialog(QDialog):
    """Розповідає, що студія — інструмент для артів гри, і веде на сторінку в Steam."""

    def __init__(self, parent=None, startup: bool = False):
        super().__init__(parent)
        self._startup = startup
        self.setWindowTitle(tr("wishlist_title"))
        self.setMinimumWidth(540)
        lay = QVBoxLayout(self)

        head = QLabel(tr("wishlist_heading"))
        head.setTextFormat(Qt.RichText)
        head.setAlignment(Qt.AlignCenter)
        head.setWordWrap(True)
        lay.addWidget(head)

        body = QLabel(tr("wishlist_body"))
        body.setTextFormat(Qt.RichText)
        body.setWordWrap(True)
        lay.addWidget(body)

        self.hide_box = QCheckBox(tr("wishlist_dont_show"))
        self.hide_box.setChecked(not should_show())
        self.hide_box.setVisible(startup)
        lay.addWidget(self.hide_box)

        row = QHBoxLayout()
        row.addStretch(1)
        later = QPushButton(tr("wishlist_later"))
        later.clicked.connect(self.reject)
        go = QPushButton(tr("wishlist_open"))
        go.setDefault(True)
        go.setMinimumWidth(go.sizeHint().width() + 24)
        go.clicked.connect(self.open_store)
        row.addWidget(later)
        row.addWidget(go)
        lay.addLayout(row)

    def open_store(self) -> None:
        if not open_url(STEAM_URL):
            QApplication.clipboard().setText(STEAM_URL)
            box = QMessageBox(QMessageBox.Information, tr("wishlist_title"),
                              tr("wishlist_open_failed", url=STEAM_URL), QMessageBox.Ok, self)
            box.setTextFormat(Qt.RichText)
            box.setTextInteractionFlags(Qt.TextBrowserInteraction)
            box.exec()
        self.accept()

    def done(self, result: int) -> None:
        if self._startup:
            settings.get().set(HIDE_KEY, self.hide_box.isChecked())
        super().done(result)
