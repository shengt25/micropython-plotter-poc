from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .file_browser import FileBrowser


class DeviceSaveDialog(QDialog):
    """更接近文件管理器体验的保存对话框"""

    ROLE_PATH = Qt.ItemDataRole.UserRole
    ROLE_IS_DIR = Qt.ItemDataRole.UserRole + 1
    ROLE_LOADED = Qt.ItemDataRole.UserRole + 2

    def __init__(
        self,
        default_directory: str,
        default_name: str,
        file_browser: FileBrowser,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Save to Device")
        self.setModal(True)
        self.resize(420, 520)

        self.file_browser = file_browser
        self._path_to_item: dict[str, QTreeWidgetItem] = {}
        self._loading_paths: set[str] = set()
        self._selected_directory = '/'
        self._desired_directory = default_directory.rstrip('/') or '/'

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Choose a directory:"))

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        layout.addWidget(self.tree, 1)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)

        # Root mapping (not shown as a row)
        self._path_to_item['/'] = self.tree.invisibleRootItem()
        self._populate_children('/')
        self._maybe_select_desired_directory()

        layout.addWidget(QLabel("File name:"))
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("untitled.py")
        self.filename_edit.setText(default_name)
        layout.addWidget(self.filename_edit)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.filename_edit.textChanged.connect(self._update_accept_enabled)
        self._update_accept_enabled()

        self.file_browser.directory_loaded.connect(self._on_directory_loaded)

    def closeEvent(self, event):
        try:
            self.file_browser.directory_loaded.disconnect(self._on_directory_loaded)
        except Exception:
            pass
        super().closeEvent(event)

    def _update_accept_enabled(self):
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if ok_button is None:
            return
        ok_button.setEnabled(bool(self.filename_edit.text().strip()))

    def _on_current_item_changed(self, current: QTreeWidgetItem[QTreeWidgetItem] = None, previous: QTreeWidgetItem[QTreeWidgetItem] = None):
        if not current:
            return
        path = current.data(0, self.ROLE_PATH)
        if not path:
            return
        is_dir = bool(current.data(0, self.ROLE_IS_DIR))
        if is_dir:
            self._selected_directory = path
        else:
            self._selected_directory = self._parent_path(path)
            filename = path.split('/')[-1]
            if filename:
                self.filename_edit.setText(filename)

    def _on_item_expanded(self, item: QTreeWidgetItem):
        path = item.data(0, self.ROLE_PATH)
        if not path:
            return
        loaded = item.data(0, self.ROLE_LOADED)
        if loaded:
            return
        self._populate_children(path)

    def _populate_children(self, path: str):
        parent = self._path_to_item.get(path)
        if not parent:
            return

        entries = self.file_browser.get_directory_entries(path)
        self._clear_children(parent)

        if entries is None:
            self._show_loading_placeholder(parent)
            parent.setData(0, self.ROLE_LOADED, False)
            if path not in self._loading_paths:
                self._loading_paths.add(path)
                self.file_browser.request_directory(path)
            return

        parent.setData(0, self.ROLE_LOADED, True)
        for name, is_dir in entries:
            child_path = f"{path}/{name}" if path != '/' else f"/{name}"
            child = QTreeWidgetItem(parent, [name])
            child.setData(0, self.ROLE_PATH, child_path)
            is_dir_flag = bool(is_dir)
            child.setData(0, self.ROLE_IS_DIR, is_dir_flag)
            if is_dir_flag:
                child.setData(0, self.ROLE_LOADED, False)
                child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            else:
                child.setData(0, self.ROLE_LOADED, True)
                child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)
            self._path_to_item[child_path] = child

        self._maybe_select_desired_directory()

    def _clear_children(self, parent: QTreeWidgetItem):
        while parent.childCount():
            child = parent.takeChild(0)
            child_path = child.data(0, self.ROLE_PATH)
            if child_path in self._path_to_item and self._path_to_item[child_path] == child:
                del self._path_to_item[child_path]

    def _show_loading_placeholder(self, parent: QTreeWidgetItem):
        placeholder = QTreeWidgetItem(parent, ["Loading..."])
        placeholder.setDisabled(True)
        placeholder.setData(0, self.ROLE_PATH, None)
        placeholder.setData(0, self.ROLE_IS_DIR, False)
        placeholder.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)

    def _on_directory_loaded(self, path: str, items: list):
        if path in self._loading_paths:
            self._loading_paths.discard(path)
        if path not in self._path_to_item:
            return
        self._populate_children(path)

    def _maybe_select_desired_directory(self):
        if not self._desired_directory:
            return

        normalized = self._desired_directory
        if normalized == '/':
            self._selected_directory = '/'
            self._desired_directory = ''
            return

        item = self._path_to_item.get(normalized)
        if not item:
            return
        self.tree.setCurrentItem(item)
        self._selected_directory = normalized
        self.tree.scrollToItem(item)
        self._desired_directory = ''

    def selected_path(self) -> Optional[str]:
        filename = self.filename_edit.text().strip()
        if not filename:
            return None

        directory = self._selected_directory or '/'
        if directory == '/':
            return f"/{filename}"

        return f"{directory}/{filename}"

    @staticmethod
    def _parent_path(path: str) -> str:
        if not path or path == '/':
            return '/'
        if '/' not in path[1:]:
            return '/'
        parent = path.rsplit('/', 1)[0]
        return parent or '/'
