from PySide6.QtWidgets import (
    QWidget, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator,
    QVBoxLayout, QLabel
)
from PySide6.QtCore import Signal, Qt


class FileBrowser(QWidget):
    """MicroPython 文件浏览器"""

    # Signals
    dir_expand_requested = Signal(str)  # 请求展开目录
    file_selected = Signal(str)         # 文件被选中（可选）

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title = QLabel("设备文件")
        title.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(title)

        # 树形控件
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("文件浏览器")
        self.tree.itemExpanded.connect(self._on_item_expanded)
        layout.addWidget(self.tree)

        # 占位文本
        self.placeholder = QLabel("设备未连接")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("color: #888; padding: 20px;")
        layout.addWidget(self.placeholder)

        # 默认显示占位符
        self.tree.hide()
        self.placeholder.show()

    def initialize_root(self):
        """初始化根目录（设备连接后调用）"""
        self.tree.clear()
        self.placeholder.hide()
        self.tree.show()

        # 创建根节点
        root_item = QTreeWidgetItem(self.tree, ["/"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, "/")  # 存储路径
        root_item.setData(0, Qt.ItemDataRole.UserRole + 1, True)  # 是否为目录

        # 添加占位子节点（使其可展开）
        placeholder = QTreeWidgetItem(root_item, ["加载中..."])
        placeholder.setDisabled(True)

        # 请求加载根目录
        self.dir_expand_requested.emit("/")

    def show_error(self, message: str):
        """显示错误"""
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
        # 查找对应的节点
        item = self._find_item_by_path(path)
        if not item:
            return

        # 删除占位子节点
        item.takeChildren()

        # 添加实际内容
        for name, is_dir in items:
            full_path = f"{path}/{name}" if path != "/" else f"/{name}"
            child = QTreeWidgetItem(item, [name])
            child.setData(0, Qt.ItemDataRole.UserRole, full_path)
            child.setData(0, Qt.ItemDataRole.UserRole + 1, is_dir)

            # 如果是目录，添加占位子节点
            if is_dir:
                placeholder = QTreeWidgetItem(child, ["加载中..."])
                placeholder.setDisabled(True)

    def _find_item_by_path(self, path: str):
        """根据路径查找节点"""
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

        if not is_dir:
            return

        # 检查是否已加载（子节点是占位符）
        if item.childCount() > 0 and item.child(0).isDisabled():
            self.dir_expand_requested.emit(path)
