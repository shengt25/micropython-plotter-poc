from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from PySide6.QtCore import Signal
from .code_editor import CodeEditor


class TabEditorWidget(QWidget):
    """多标签代码编辑器"""

    # Signals
    file_modified = Signal(bool)  # 当前活动标签的修改状态改变
    active_file_changed = Signal(str)  # 活动文件改变 (path or "")
    save_requested = Signal()  # 保存请求 (来自快捷键)

    def __init__(self, parent=None):
        super().__init__(parent)

        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tab Widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)
        layout.addWidget(self.tab_widget)

        # 标签状态字典: {tab_index: {'path': str | None, 'modified': bool, 'editor': CodeEditor, 'display_name': str}}
        self.tab_states = {}
        self._untitled_counter = 1

        # 创建默认的未命名标签
        self.create_new_tab()

    def create_new_tab(self):
        """创建新的未命名标签并切换过去"""
        editor = CodeEditor()
        editor.textChanged.connect(lambda: self._on_text_changed(editor))
        editor.save_requested.connect(self.save_requested.emit)

        title = self._next_untitled_title()
        index = self.tab_widget.addTab(editor, title)
        self.tab_widget.setTabToolTip(index, title)

        self.tab_states[index] = {
            'path': None,
            'modified': False,
            'editor': editor,
            'display_name': title
        }

        self.tab_widget.setCurrentIndex(index)
        return index

    def _next_untitled_title(self) -> str:
        if self._untitled_counter == 1:
            title = "Untitled"
        else:
            title = f"Untitled {self._untitled_counter}"
        self._untitled_counter += 1
        return title

    def open_file(self, path: str, content: str):
        """
        打开文件到新标签或切换到已存在的标签

        Args:
            path: 文件路径
            content: 文件内容
        """
        # 检查文件是否已打开
        for index, state in self.tab_states.items():
            if state['path'] == path:
                # 已打开，切换到该标签
                self.tab_widget.setCurrentIndex(index)
                return

        # 文件未打开，创建新标签
        editor = CodeEditor()
        editor.set_code(content)
        editor.textChanged.connect(lambda: self._on_text_changed(editor))
        editor.save_requested.connect(self.save_requested.emit)

        # 提取文件名
        filename = path.split('/')[-1]
        index = self.tab_widget.addTab(editor, filename)
        self.tab_widget.setTabToolTip(index, path)

        self.tab_states[index] = {
            'path': path,
            'modified': False,
            'editor': editor,
            'display_name': None
        }

        # 切换到新标签
        self.tab_widget.setCurrentIndex(index)

    def get_current_file_info(self):
        """
        获取当前活动标签的文件信息

        Returns:
            (path, content, modified) or (None, None, False) if no tab
        """
        current_index = self.tab_widget.currentIndex()
        if current_index == -1 or current_index not in self.tab_states:
            return (None, None, False)

        state = self.tab_states[current_index]
        path = state['path']
        content = state['editor'].get_code()
        modified = state['modified']

        return (path, content, modified)

    def mark_current_saved(self):
        """标记当前文件为已保存状态"""
        current_index = self.tab_widget.currentIndex()
        if current_index == -1 or current_index not in self.tab_states:
            return

        state = self.tab_states[current_index]
        if state['modified']:
            state['modified'] = False
            self._update_tab_title(current_index)
            self.file_modified.emit(False)

    def mark_file_saved(self, path: str):
        """
        标记指定路径的文件为已保存状态

        Args:
            path: 文件路径
        """
        for index, state in self.tab_states.items():
            if state['path'] == path:
                if state['modified']:
                    state['modified'] = False
                    self._update_tab_title(index)
                    # 如果是当前活动标签，发出信号
                    if index == self.tab_widget.currentIndex():
                        self.file_modified.emit(False)
                break

    def update_file_content(self, path: str, content: str):
        """
        更新指定路径文件的内容（不触发修改状态），并切换到该标签

        Args:
            path: 文件路径
            content: 新内容
        """
        for index, state in self.tab_states.items():
            if state['path'] == path:
                editor = state['editor']
                # 临时断开信号，避免触发修改标记
                editor.textChanged.disconnect()
                editor.set_code(content)
                editor.textChanged.connect(lambda: self._on_text_changed(editor))
                # 切换到该标签页
                self.tab_widget.setCurrentIndex(index)
                break

    def get_current_code(self) -> str:
        """获取当前标签的代码"""
        current_index = self.tab_widget.currentIndex()
        if current_index == -1 or current_index not in self.tab_states:
            return ""

        return self.tab_states[current_index]['editor'].get_code()

    def _on_text_changed(self, editor: CodeEditor):
        """文本改变事件"""
        # 查找该编辑器对应的标签
        for index, state in self.tab_states.items():
            if state['editor'] == editor:
                # 只有已保存的文件才需要标记修改
                if not state['modified']:
                    state['modified'] = True
                    self._update_tab_title(index)

                    if index == self.tab_widget.currentIndex():
                        self.file_modified.emit(True)
                break

    def _update_tab_title(self, index: int):
        """更新标签标题（添加/移除星号）"""
        if index not in self.tab_states:
            return

        state = self.tab_states[index]
        path = state['path']
        modified = state['modified']

        if path is None:
            title = state.get('display_name') or "Untitled"
        else:
            # 已命名文件
            filename = path.split('/')[-1]
            title = filename

        # 添加星号标记
        if modified:
            title = f"{title} *"

        self.tab_widget.setTabText(index, title)

    def _on_current_tab_changed(self, index: int):
        """当前标签改变事件"""
        if index == -1 or index not in self.tab_states:
            self.active_file_changed.emit("")
            self.file_modified.emit(False)
            return

        state = self.tab_states[index]
        path = state['path'] or ""
        modified = state['modified']

        self.active_file_changed.emit(path)
        self.file_modified.emit(modified)

    def _on_tab_close_requested(self, index: int):
        """标签关闭请求"""
        if index not in self.tab_states:
            return
        # TODO: 如果文件已修改，询问是否保存（暂时不实现）
        self._remove_tab_at_index(index)

    def _reindex_tabs(self):
        """重新索引标签状态（删除标签后调用）"""
        new_states = {}
        for i in range(self.tab_widget.count()):
            # 查找原来的状态
            for old_index, state in self.tab_states.items():
                if self.tab_widget.widget(i) == state['editor']:
                    new_states[i] = state
                    break
        self.tab_states = new_states

    def set_current_file_path(self, path: str):
        """为当前标签设置文件路径"""
        current_index = self.tab_widget.currentIndex()
        if current_index == -1 or current_index not in self.tab_states:
            return

        state = self.tab_states[current_index]
        state['path'] = path
        state['display_name'] = None
        self.tab_widget.setTabToolTip(current_index, path)
        self._update_tab_title(current_index)
        self._close_duplicate_tabs(current_index, path)
        self.active_file_changed.emit(path)

    def current_is_untitled(self) -> bool:
        """返回当前标签是否尚未命名"""
        current_index = self.tab_widget.currentIndex()
        if current_index == -1 or current_index not in self.tab_states:
            return False

        state = self.tab_states[current_index]
        return state['path'] is None

    def close_file(self, path: str):
        """关闭指定路径的标签（如果存在）"""
        for index, state in list(self.tab_states.items()):
            if state['path'] == path:
                self._remove_tab_at_index(index)
                break

    def close_files_under_directory(self, dir_path: str):
        """关闭指定目录下的所有文件标签"""
        # 规范化目录路径（确保以 / 结尾，方便匹配）
        normalized_dir = dir_path.rstrip('/') + '/'

        # 找出所有在该目录下的文件
        indices_to_close = []
        for index, state in self.tab_states.items():
            file_path = state['path']
            if file_path and file_path.startswith(normalized_dir):
                indices_to_close.append(index)

        # 按倒序关闭（避免索引混乱）
        for index in sorted(indices_to_close, reverse=True):
            self._remove_tab_at_index(index)

    def _close_duplicate_tabs(self, current_index: int, path: str):
        duplicates = [idx for idx, state in self.tab_states.items() if state['path'] == path and idx != current_index]
        for idx in sorted(duplicates, reverse=True):
            self._remove_tab_at_index(idx)

    def _remove_tab_at_index(self, index: int):
        if index not in self.tab_states:
            return

        self.tab_widget.removeTab(index)
        del self.tab_states[index]
        self._reindex_tabs()

        if self.tab_widget.count() == 0:
            self.create_new_tab()
