"""AsciiFileTree — дерево ASCII-файлів із пошуком і згортанням тек."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


ASCII_FILE_TREE_ROLE = Qt.UserRole


class AsciiFileTree(QTreeWidget):
    """Дерево ASCII-файлів: теки згорнуті типово, розгортання/згортання — стрілкою-гілкою або подвійним кліком."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self._nodes = {}

    def populate(self, names):
        """Будує дерево зі списку відносних шляхів; типово все згорнуто."""
        self.clear()
        self._nodes = {}
        for name in sorted(names):
            parts = name.split("/")
            parent_item = None
            for i, part in enumerate(parts):
                is_dir = i < len(parts) - 1
                path = "/".join(parts[:i + 1])
                node_key = path + "/" if is_dir else path
                item = self._nodes.get(node_key)
                if item is None:
                    label = f"📁 {part}" if is_dir else part
                    item = QTreeWidgetItem([label])
                    item.setData(0, ASCII_FILE_TREE_ROLE, path)
                    self._nodes[node_key] = item
                    if parent_item is None:
                        self.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)
                parent_item = item
        self.expandAll()

    def full_name(self, item):
        """Повний відносний шлях вузла."""
        return item.data(0, ASCII_FILE_TREE_ROLE) or item.text(0)

    def apply_filter(self, q):
        """Сховує невідповідні вузли; при пошуку розгортає предків збігів."""
        q = q.strip().lower()
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            self._filter_node(root.child(i), q)
        if not q:
            self.expandAll()

    def _filter_node(self, item, q):
        visible = (q in item.data(0, ASCII_FILE_TREE_ROLE).lower()) if q else True
        for i in range(item.childCount()):
            if self._filter_node(item.child(i), q):
                visible = True
                break
        item.setHidden(not visible)
        if visible and q:
            item.setExpanded(True)
        return visible

    def first_visible_item(self):
        """Перший насправді видимий лист (файл) у DFS-порядку (усі предки розгорнуті)."""
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            found = self._first_visible_leaf(root.child(i))
            if found is not None:
                return found
        return None

    def _first_visible_leaf(self, item):
        if item.isHidden() or not self._ancestors_expanded(item):
            return None
        if item.childCount() == 0:
            return item
        if not item.isExpanded():
            return None
        for i in range(item.childCount()):
            found = self._first_visible_leaf(item.child(i))
            if found is not None:
                return found
        return None

    def _ancestors_expanded(self, item):
        root = self.invisibleRootItem()
        parent = item.parent()
        while parent is not None and parent is not root:
            if not parent.isExpanded():
                return False
            parent = parent.parent()
        return True


class _DragSelectTree(AsciiFileTree):
    """Дерево: клік — один, Ctrl+клік — кілька, клік по вибраному (без Ctrl) — drag у кадри."""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            is_ctrl = bool(event.modifiers() & Qt.ControlModifier)
            # Drag тільки коли клік по ВЖЕ вибраному без Ctrl
            self.setDragEnabled(bool(item and item.isSelected() and not is_ctrl))
        super().mousePressEvent(event)
