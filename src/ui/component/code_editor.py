from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtCore import Qt


class CodeEditor(QPlainTextEdit):

    def __init__(self, parent=None):
        super().__init__(parent)

        font = QFont("Courier New", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        self.setPlaceholderText("MicroPython")

        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(' '))

    def keyPressEvent(self, event: QKeyEvent):
        """重写键盘事件，将Tab键转换为4个空格"""
        if event.key() == Qt.Key.Key_Tab:
            # 插入4个空格而不是Tab字符
            cursor = self.textCursor()
            cursor.insertText("    ")  # 4个空格
            return
        elif event.key() == Qt.Key.Key_Backtab:
            # Shift+Tab 删除前面的空格（如果有的话）
            cursor = self.textCursor()
            cursor.movePosition(cursor.MoveOperation.StartOfLine, cursor.MoveMode.KeepAnchor)
            selected_text = cursor.selectedText()
            if selected_text.endswith("    "):
                # 删除最后4个空格
                cursor.removeSelectedText()
                cursor.insertText(selected_text[:-4])
                return
            else:
                # 恢复选择
                cursor = self.textCursor()

        # 其他按键使用默认处理
        super().keyPressEvent(event)

    def get_code(self) -> str:
        return self.toPlainText()

    def set_code(self, code: str):
        self.setPlainText(code)

    def clear_code(self):
        self.clear()
