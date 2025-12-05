from PySide6.QtWidgets import (
    QWidget, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator,
    QVBoxLayout, QLabel, QMenu, QMessageBox
)
from PySide6.QtCore import Signal, Qt


class FileBrowser(QWidget):
    """MicroPython 文件浏览器"""

    # Signals
    dir_expand_requested = Signal(str)  # 请求展开目录
    file_selected = Signal(str)         # 文件被选中（可选）
    file_open_requested = Signal(str)   # 请求打开文件（双击文件）
    directory_loaded = Signal(str, list)  # 某个目录加载完成
    delete_requested = Signal(str, bool)  # 请求删除路径

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title = QLabel("Files")
        title.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(title)

        # 树形控件
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("File Browser")
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu_requested)
        layout.addWidget(self.tree)

        # 占位文本
        self.placeholder = QLabel("Device not connected")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("color: #888; padding: 20px;")
        layout.addWidget(self.placeholder)

        # 默认显示占位符
        self.tree.hide()
        self.placeholder.show()
        self._root_path = "/"
        self._path_to_item = {}
        self._loading_paths = set()

    def initialize_root(self):
        """初始化根目录（设备连接后调用）"""
        self.tree.clear()
        self.placeholder.hide()
        self.tree.show()
        self._path_to_item = {self._root_path: self.tree.invisibleRootItem()}
        self._loading_paths.clear()
        self._request_directory(self._root_path)

    def show_error(self, message: str):
        """显示错误"""
        self._loading_paths.clear()
        self._path_to_item.clear()
        self.tree.clear()
        self.tree.hide()
        self.placeholder.setText(message)
        self.placeholder.show()

    def populate_directory(self, path: str, items: list):
        """
        填充目录内容

        Args:
            path: 目录路径
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
        """从树中移除指定路径"""
        item = self._path_to_item.pop(path, None)
        if not item:
            return
        parent = item.parent() or self.tree.invisibleRootItem()
        index = parent.indexOfChild(item)
        if index >= 0:
            parent.takeChild(index)
        self._remove_subtree(item)

    def _populate_children(self, parent: QTreeWidgetItem, items: list, path: str):
        """为指定父节点填充子节点"""
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
        """根据路径查找节点"""
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
        """节点展开事件"""
        path = item.data(0, Qt.ItemDataRole.UserRole)
        is_dir = item.data(0, Qt.ItemDataRole.UserRole + 1)

        if not path or not is_dir:
            return

        # 检查是否已加载（子节点是占位符）
        if item.childCount() > 0 and item.child(0).isDisabled():
            self._request_directory(path)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """节点双击事件"""
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
        """右键菜单"""
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
        """对外暴露的加载目录接口"""
        self._request_directory(path)

    def cancel_directory_request(self, path: str):
        """外部通知目录加载失败，恢复请求状态"""
        self._loading_paths.discard(path)

    def get_directory_entries(self, path: str):
        """获取指定目录的子项（如果已加载）"""
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
        """返回当前已知的设备目录列表"""
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
        """返回当前选中的目录，如果选中的是文件则返回其父目录"""
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
