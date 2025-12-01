from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtGui import QFont, QKeyEvent, QKeySequence
from PySide6.QtCore import Qt, Signal
from .syntax_highlighter import PythonSyntaxHighlighter


class CodeEditor(QPlainTextEdit):

    # 定义保存信号
    save_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # 跨平台字体选择：按优先级尝试多个等宽字体
        # macOS: SF Mono, Menlo, Monaco
        # Windows: Consolas, Courier New
        # Linux: DejaVu Sans Mono, Liberation Mono
        font_families = [
            "SF Mono",           # macOS 现代版本
            "Menlo",             # macOS 经典字体
            "Consolas",          # Windows 最佳字体
            "DejaVu Sans Mono",  # Linux 常用字体
            "Liberation Mono",   # Linux 备选字体
            "Monaco",            # macOS 旧版本
            "Courier New"        # 通用后备字体
        ]

        # 使用逗号分隔的字体列表，Qt会自动选择第一个可用的
        font = QFont(", ".join(font_families), 13)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setWeight(QFont.Weight.Medium)  # 设置为中等粗细，更易读
        self.setFont(font)

        self.setPlaceholderText("")

        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(' '))

        # 添加Python语法高亮
        self.highlighter = PythonSyntaxHighlighter(self.document())

    def keyPressEvent(self, event: QKeyEvent):
        """重写键盘事件，处理Tab键和保存快捷键"""
        # 检查是否是保存快捷键 (Cmd+S 在 macOS, Ctrl+S 在 Windows/Linux)
        if event.matches(QKeySequence.StandardKey.Save):
            # 发射保存信号
            self.save_requested.emit()
            event.accept()
            return

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
