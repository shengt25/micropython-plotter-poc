from PySide6.QtWidgets import (
    QWidget, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator,
    QVBoxLayout, QLabel, QMenu, QMessageBox
)
from PySide6.QtCore import Signal, Qt


class FileBrowser(QWidget):
    """MicroPython File Browser"""

    # Signals
    dir_expand_requested = Signal(str)  # Request to expand directory
    file_selected = Signal(str)         # File selected (optional)
    file_open_requested = Signal(str)   # Request to open file (double click)
    directory_loaded = Signal(str, list)  # Directory loaded
    delete_requested = Signal(str, bool)  # Request to delete path

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Title
        title = QLabel("Files")
        title.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(title)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("File Browser")
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu_requested)
        layout.addWidget(self.tree)

        # Placeholder text
        self.placeholder = QLabel("Device not connected")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("color: #888; padding: 20px;")
        layout.addWidget(self.placeholder)

        # Show placeholder by default
        self.tree.hide()
        self.placeholder.show()
        self._root_path = "/"
        self._path_to_item = {}
        self._loading_paths = set()

    def initialize_root(self):
        """Initialize root directory (called after device connection)"""
        self.tree.clear()
        self.placeholder.hide()
        self.tree.show()
        self._path_to_item = {self._root_path: self.tree.invisibleRootItem()}
        self._loading_paths.clear()
        self._request_directory(self._root_path)

    def show_error(self, message: str):
        """Show error"""
        self._loading_paths.clear()
        self._path_to_item.clear()
        self.tree.clear()
        self.tree.hide()
        self.placeholder.setText(message)
        self.placeholder.show()

    def populate_directory(self, path: str, items: list):
        """
        Populate directory content

        Args:
            path: Directory path
            items: [(name, is_dir), ...]
        """
        if path == self._root_path:
            root_item = self.tree.invisibleRootItem()
            self._clear_children(root_item)
            self._populate_children(root_item, items, path)
            return

        parent = self._path_to_item.get(path)
        if not parent:
            return

        self._loading_paths.discard(path)
        self._clear_children(parent)
        self._populate_children(parent, items, path)
        self.directory_loaded.emit(path, items)

    def remove_entry(self, path: str):
        """Remove specified path from tree"""
        item = self._path_to_item.pop(path, None)
        if not item:
            return
        parent = item.parent() or self.tree.invisibleRootItem()
        index = parent.indexOfChild(item)
        if index >= 0:
            parent.takeChild(index)
        self._remove_subtree(item)

    def _populate_children(self, parent: QTreeWidgetItem, items: list, path: str):
        """Populate children for specified parent node"""
        for name, is_dir in items:
            full_path = f"{path}/{name}" if path != "/" else f"/{name}"
            child = QTreeWidgetItem(parent, [name])
            child.setData(0, Qt.ItemDataRole.UserRole, full_path)
            child.setData(0, Qt.ItemDataRole.UserRole + 1, is_dir)
            self._path_to_item[full_path] = child

            if is_dir:
                placeholder = QTreeWidgetItem(child, ["Loading..."])
                placeholder.setDisabled(True)

    def _find_item_by_path(self, path: str):
        """Find item by path"""
        if path == self._root_path:
            return self.tree.invisibleRootItem()
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.ItemDataRole.UserRole) == path:
                return item
            iterator += 1
        return None

    def _on_item_expanded(self, item: QTreeWidgetItem):
        """Item expansion event"""
        path = item.data(0, Qt.ItemDataRole.UserRole)
        is_dir = item.data(0, Qt.ItemDataRole.UserRole + 1)

        if not path or not is_dir:
            return

        # Check if loaded (child is placeholder)
        if item.childCount() > 0 and item.child(0).isDisabled():
            self._request_directory(path)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Item double click event"""
        path = item.data(0, Qt.ItemDataRole.UserRole)
        is_dir = item.data(0, Qt.ItemDataRole.UserRole + 1)

        if not path:
            return

        if is_dir:
            if not item.isExpanded():
                item.setExpanded(True)
            if item.childCount() == 0 or item.child(0).isDisabled():
                self._request_directory(path)
            return

        self.file_open_requested.emit(path)

    def _on_context_menu_requested(self, position):
        """Context menu"""
        item = self.tree.itemAt(position)
        if not item:
            return

        path = item.data(0, Qt.ItemDataRole.UserRole)
        is_dir = bool(item.data(0, Qt.ItemDataRole.UserRole + 1))

        if not path or path == self._root_path:
            return

        self.tree.setCurrentItem(item)

        menu = QMenu(self)
        delete_action = menu.addAction("Delete")
        action = menu.exec(self.tree.viewport().mapToGlobal(position))

        if action == delete_action:
            self._confirm_and_request_delete(path, is_dir)

    def _confirm_and_request_delete(self, path: str, is_dir: bool):
        target_label = "folder" if is_dir else "file"
        reply = QMessageBox.question(
            self,
            "Delete",
            f"Delete {target_label}: {path}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(path, is_dir)

    def _request_directory(self, path: str):
        # Force refresh by removing and re-adding path
        # This ensures refresh happens even for already-loaded directories
        self._loading_paths.discard(path)
        self._loading_paths.add(path)
        self.dir_expand_requested.emit(path)

    def _clear_children(self, parent: QTreeWidgetItem):
        while parent.childCount():
            child = parent.takeChild(0)
            self._remove_subtree(child)

    def _remove_subtree(self, item: QTreeWidgetItem):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            self._path_to_item.pop(path, None)
        while item.childCount():
            child = item.takeChild(0)
            self._remove_subtree(child)
        del item

    def request_directory(self, path: str):
        """Public interface to load directory"""
        self._request_directory(path)

    def cancel_directory_request(self, path: str):
        """External notification of directory load failure, restore request state"""
        self._loading_paths.discard(path)

    def get_directory_entries(self, path: str):
        """Get children of specified directory (if loaded)"""
        if path == self._root_path:
            parent = self.tree.invisibleRootItem()
        else:
            parent = self._path_to_item.get(path)

        if not parent:
            return None

        if parent.childCount() == 0:
            return []

        first_child = parent.child(0)
        if first_child.isDisabled():
            return None

        entries = []
        for i in range(parent.childCount()):
            child = parent.child(i)
            name = child.text(0)
            is_dir = child.data(0, Qt.ItemDataRole.UserRole + 1)
            entries.append((name, bool(is_dir)))

        return entries

    def get_known_directories(self) -> list[str]:
        """Return list of currently known device directories"""
        directories = {'/'}
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            path = item.data(0, Qt.ItemDataRole.UserRole)
            is_dir = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if path and is_dir:
                directories.add(path)
            iterator += 1
        return sorted(directories)

    def get_selected_directory(self) -> str:
        """Return currently selected directory, or parent directory if file is selected"""
        item = self.tree.currentItem()
        while item:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            is_dir = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if path and is_dir:
                return path
            item = item.parent()
        return '/'

    def path_exists(self, path: str) -> tuple[bool, bool | None]:
        if path == '/':
            return True, True
        item = self._path_to_item.get(path)
        if not item:
            return False, None
        is_dir = bool(item.data(0, Qt.ItemDataRole.UserRole + 1))
        return True, is_dir
