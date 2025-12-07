from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from PySide6.QtCore import Signal
from .code_editor import CodeEditor


class TabEditorWidget(QWidget):
    """Multi-tab code editor"""

    # Signals
    file_modified = Signal(bool)  # Active tab modified status changed
    active_file_changed = Signal(str)  # Active file changed (path or "")
    save_requested = Signal()  # Save requested (from shortcut)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tab Widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)
        layout.addWidget(self.tab_widget)

        # Tab state dictionary: {tab_index: {'path': str | None, 'modified': bool, 'editor': CodeEditor, 'display_name': str}}
        self.tab_states = {}
        self._untitled_counter = 1

        # Create default untitled tab
        self.create_new_tab()

    def create_new_tab(self):
        """Create new untitled tab and switch to it"""
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
        Open file in new tab or switch to existing tab

        Args:
            path: File path
            content: File content
        """
        # Check if file is already open
        for index, state in self.tab_states.items():
            if state['path'] == path:
                # Already open, switch to this tab
                self.tab_widget.setCurrentIndex(index)
                return

        # File not open, create new tab
        editor = CodeEditor()
        editor.set_code(content)
        editor.textChanged.connect(lambda: self._on_text_changed(editor))
        editor.save_requested.connect(self.save_requested.emit)

        # Extract filename
        filename = path.split('/')[-1]
        index = self.tab_widget.addTab(editor, filename)
        self.tab_widget.setTabToolTip(index, path)

        self.tab_states[index] = {
            'path': path,
            'modified': False,
            'editor': editor,
            'display_name': None
        }

        # Switch to new tab
        self.tab_widget.setCurrentIndex(index)

    def get_current_file_info(self):
        """
        Get file info of current active tab

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
        """Mark current file as saved"""
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
        Mark file at specified path as saved

        Args:
            path: File path
        """
        for index, state in self.tab_states.items():
            if state['path'] == path:
                if state['modified']:
                    state['modified'] = False
                    self._update_tab_title(index)
                    # If it is the current active tab, emit signal
                    if index == self.tab_widget.currentIndex():
                        self.file_modified.emit(False)
                break

    def update_file_content(self, path: str, content: str):
        """
        Update content of file at specified path (without triggering modified status) and switch to that tab

        Args:
            path: File path
            content: New content
        """
        for index, state in self.tab_states.items():
            if state['path'] == path:
                editor = state['editor']
                # Temporarily disconnect signal to avoid triggering modified flag
                editor.textChanged.disconnect()
                editor.set_code(content)
                editor.textChanged.connect(lambda: self._on_text_changed(editor))
                # Switch to that tab
                self.tab_widget.setCurrentIndex(index)
                break

    def get_current_code(self) -> str:
        """Get code of current tab"""
        current_index = self.tab_widget.currentIndex()
        if current_index == -1 or current_index not in self.tab_states:
            return ""

        return self.tab_states[current_index]['editor'].get_code()

    def _on_text_changed(self, editor: CodeEditor):
        """Text changed event"""
        # Find tab corresponding to this editor
        for index, state in self.tab_states.items():
            if state['editor'] == editor:
                # Only mark as modified if file was saved
                if not state['modified']:
                    state['modified'] = True
                    self._update_tab_title(index)

                    if index == self.tab_widget.currentIndex():
                        self.file_modified.emit(True)
                break

    def _update_tab_title(self, index: int):
        """Update tab title (add/remove asterisk)"""
        if index not in self.tab_states:
            return

        state = self.tab_states[index]
        path = state['path']
        modified = state['modified']

        if path is None:
            title = state.get('display_name') or "Untitled"
        else:
            # Named file
            filename = path.split('/')[-1]
            title = filename

        # Add asterisk marker
        if modified:
            title = f"{title} *"

        self.tab_widget.setTabText(index, title)

    def _on_current_tab_changed(self, index: int):
        """Current tab changed event"""
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
        """Tab close requested"""
        if index not in self.tab_states:
            return
        # TODO: If file is modified, ask to save (not implemented yet)
        self._remove_tab_at_index(index)

    def _reindex_tabs(self):
        """Reindex tab states (called after deleting tab)"""
        new_states = {}
        for i in range(self.tab_widget.count()):
            # Find original state
            for old_index, state in self.tab_states.items():
                if self.tab_widget.widget(i) == state['editor']:
                    new_states[i] = state
                    break
        self.tab_states = new_states

    def set_current_file_path(self, path: str):
        """Set file path for current tab"""
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
        """Return whether current tab is untitled"""
        current_index = self.tab_widget.currentIndex()
        if current_index == -1 or current_index not in self.tab_states:
            return False

        state = self.tab_states[current_index]
        return state['path'] is None

    def close_file(self, path: str):
        """Close tab with specified path (if exists)"""
        for index, state in list(self.tab_states.items()):
            if state['path'] == path:
                self._remove_tab_at_index(index)
                break

    def close_files_under_directory(self, dir_path: str):
        """Close all file tabs under specified directory"""
        # Normalize directory path (ensure ending with / for easier matching)
        normalized_dir = dir_path.rstrip('/') + '/'

        # Find all files under this directory
        indices_to_close = []
        for index, state in self.tab_states.items():
            file_path = state['path']
            if file_path and file_path.startswith(normalized_dir):
                indices_to_close.append(index)

        # Close in reverse order (avoid index confusion)
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
