from PySide6.QtWidgets import QTextEdit
from PySide6.QtGui import QFont, QTextCursor


class OutputConsole(QTextEdit):
    """输出控制台组件"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # 设置为只读
        self.setReadOnly(True)

        # 设置等宽字体
        font = QFont("Courier New", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        # 设置占位符
        self.setPlaceholderText("Console output...")

    def append_output(self, message: str):
        """追加普通输出（黑色）"""
        self.setTextColor("#000000")
        # Strip trailing newlines since QTextEdit.append() adds one automatically
        message = message.rstrip('\r\n')
        self.append(message)
        self.scroll_to_bottom()

    def append_error(self, message: str):
        """追加错误信息（红色）"""
        self.setTextColor("#D32F2F")  # 红色
        # Strip trailing newlines since QTextEdit.append() adds one automatically
        message = message.rstrip('\r\n')
        self.append(message)
        self.scroll_to_bottom()

    def append_info(self, message: str):
        """追加提示信息（蓝色）"""
        self.setTextColor("#1976D2")  # 蓝色
        # Strip trailing newlines since QTextEdit.append() adds one automatically
        message = message.rstrip('\r\n')
        self.append(message)
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        """滚动到底部"""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def clear_console(self):
        """清空控制台"""
        self.clear()
