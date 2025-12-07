from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtGui import QFont, QKeyEvent, QKeySequence
from PySide6.QtCore import Qt, Signal
from .syntax_highlighter import PythonSyntaxHighlighter


class CodeEditor(QPlainTextEdit):

    # Define save signal
    save_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Cross-platform font selection: try multiple monospace fonts by priority
        # macOS: SF Mono, Menlo, Monaco
        # Windows: Consolas, Courier New
        # Linux: DejaVu Sans Mono, Liberation Mono
        font_families = [
            "SF Mono",           # macOS Modern
            "Menlo",             # macOS Classic
            "Consolas",          # Windows Best
            "DejaVu Sans Mono",  # Linux Common
            "Liberation Mono",   # Linux Alternative
            "Monaco",            # macOS Old
            "Courier New"        # Universal Fallback
        ]

        # Comma-separated font list, Qt will select the first available one
        font = QFont(", ".join(font_families), 13)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setWeight(QFont.Weight.Medium)  # Set to medium weight for better readability
        self.setFont(font)

        self.setPlaceholderText("")

        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(' '))

        # Add Python syntax highlighting
        self.highlighter = PythonSyntaxHighlighter(self.document())

    def keyPressEvent(self, event: QKeyEvent):
        """Override key press event to handle Tab key and save shortcut"""
        # Check if it is save shortcut (Cmd+S on macOS, Ctrl+S on Windows/Linux)
        if event.matches(QKeySequence.StandardKey.Save):
            # Emit save signal
            self.save_requested.emit()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Tab:
            # Insert 4 spaces instead of Tab character
            cursor = self.textCursor()
            cursor.insertText("    ")  # 4 spaces
            return
        elif event.key() == Qt.Key.Key_Backtab:
            # Shift+Tab removes preceding spaces (if any)
            cursor = self.textCursor()
            cursor.movePosition(cursor.MoveOperation.StartOfLine, cursor.MoveMode.KeepAnchor)
            selected_text = cursor.selectedText()
            if selected_text.endswith("    "):
                # Remove the last 4 spaces
                cursor.removeSelectedText()
                cursor.insertText(selected_text[:-4])
                return
            else:
                # Restore selection
                cursor = self.textCursor()

        # Default handling for other keys
        super().keyPressEvent(event)

    def get_code(self) -> str:
        return self.toPlainText()

    def set_code(self, code: str):
        self.setPlainText(code)

    def clear_code(self):
        self.clear()
