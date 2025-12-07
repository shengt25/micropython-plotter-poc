from PySide6.QtWidgets import QTextEdit
from PySide6.QtGui import QFont, QTextCursor


class OutputConsole(QTextEdit):
    """Output console component"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Set to read-only
        self.setReadOnly(True)

        # Set monospace font
        font = QFont("Courier New", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        # Set placeholder
        self.setPlaceholderText("Console output...")

    def append_output(self, message: str):
        """Append normal output (black)"""
        self.setTextColor("#000000")
        # Strip trailing newlines since QTextEdit.append() adds one automatically
        message = message.rstrip('\r\n')
        self.append(message)
        self.scroll_to_bottom()

    def append_error(self, message: str):
        """Append error message (red)"""
        self.setTextColor("#D32F2F")  # Red
        # Strip trailing newlines since QTextEdit.append() adds one automatically
        message = message.rstrip('\r\n')
        self.append(message)
        self.scroll_to_bottom()

    def append_info(self, message: str):
        """Append info message (blue)"""
        self.setTextColor("#1976D2")  # Blue
        # Strip trailing newlines since QTextEdit.append() adds one automatically
        message = message.rstrip('\r\n')
        self.append(message)
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        """Scroll to bottom"""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def clear_console(self):
        """Clear console"""
        self.clear()
