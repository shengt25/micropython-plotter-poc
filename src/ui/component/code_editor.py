from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtGui import QFont


class CodeEditor(QPlainTextEdit):

    def __init__(self, parent=None):
        super().__init__(parent)

        font = QFont("Courier New", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        self.setPlaceholderText("MicroPython")

        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(' '))

    def get_code(self) -> str:
        return self.toPlainText()

    def set_code(self, code: str):
        self.setPlainText(code)

    def clear_code(self):
        self.clear()
