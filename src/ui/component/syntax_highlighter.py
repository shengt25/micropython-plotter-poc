"""
Python Syntax Highlighter
Provides basic syntax highlighting for Python code using QSyntaxHighlighter
"""
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QFont, QColor
from PySide6.QtCore import QRegularExpression


class PythonSyntaxHighlighter(QSyntaxHighlighter):
    """Python Syntax Highlighter"""

    def __init__(self, document):
        super().__init__(document)

        # Define highlighting rules
        self.highlighting_rules = []

        # Keyword format (blue bold)
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#0000FF"))
        keyword_format.setFontWeight(QFont.Weight.Bold)

        # Python keyword list
        keywords = [
            'and', 'as', 'assert', 'break', 'class', 'continue', 'def',
            'del', 'elif', 'else', 'except', 'False', 'finally', 'for',
            'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'None',
            'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'True',
            'try', 'while', 'with', 'yield', 'async', 'await'
        ]

        for word in keywords:
            pattern = QRegularExpression(f'\\b{word}\\b')
            self.highlighting_rules.append((pattern, keyword_format))

        # Built-in functions (dark purple)
        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor("#8B008B"))
        builtins = [
            'print', 'len', 'range', 'str', 'int', 'float', 'list', 'dict',
            'set', 'tuple', 'bool', 'type', 'isinstance', 'open', 'abs',
            'min', 'max', 'sum', 'all', 'any', 'enumerate', 'zip'
        ]
        for word in builtins:
            pattern = QRegularExpression(f'\\b{word}\\b')
            self.highlighting_rules.append((pattern, builtin_format))

        # String (green)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#008000"))
        # Double-quoted string
        self.highlighting_rules.append((
            QRegularExpression('"[^"\\\\]*(\\\\.[^"\\\\]*)*"'),
            string_format
        ))
        # Single-quoted string
        self.highlighting_rules.append((
            QRegularExpression("'[^'\\\\]*(\\\\.[^'\\\\]*)*'"),
            string_format
        ))

        # Comment (gray italic)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#808080"))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((
            QRegularExpression('#[^\n]*'),
            comment_format
        ))

        # Number (orange)
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#FF8C00"))
        self.highlighting_rules.append((
            QRegularExpression('\\b[0-9]+\\.?[0-9]*\\b'),
            number_format
        ))

        # Function definition (dark blue)
        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#00008B"))
        function_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((
            QRegularExpression('\\bdef\\s+([A-Za-z_][A-Za-z0-9_]*)'),
            function_format
        ))

        # Class definition (dark blue)
        class_format = QTextCharFormat()
        class_format.setForeground(QColor("#00008B"))
        class_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((
            QRegularExpression('\\bclass\\s+([A-Za-z_][A-Za-z0-9_]*)'),
            class_format
        ))

        # Triple-quoted string format
        self.tri_single_format = QTextCharFormat()
        self.tri_single_format.setForeground(QColor("#008000"))
        self.tri_double_format = QTextCharFormat()
        self.tri_double_format.setForeground(QColor("#008000"))

    def highlightBlock(self, text):
        """Apply syntax highlighting to a text block"""
        # Apply basic rules
        for pattern, format in self.highlighting_rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(
                    match.capturedStart(),
                    match.capturedLength(),
                    format
                )

        # Handle multi-line strings (triple quotes)
        self.setCurrentBlockState(0)

        # Triple double quotes
        start_index = 0
        if self.previousBlockState() != 1:
            start_index = text.find('"""')

        while start_index >= 0:
            end_index = text.find('"""', start_index + 3)
            if end_index == -1:
                self.setCurrentBlockState(1)
                comment_length = len(text) - start_index
            else:
                comment_length = end_index - start_index + 3

            self.setFormat(start_index, comment_length, self.tri_double_format)
            start_index = text.find('"""', start_index + comment_length)

        # Triple single quotes
        if self.currentBlockState() == 0:
            start_index = 0
            if self.previousBlockState() != 2:
                start_index = text.find("'''")

            while start_index >= 0:
                end_index = text.find("'''", start_index + 3)
                if end_index == -1:
                    self.setCurrentBlockState(2)
                    comment_length = len(text) - start_index
                else:
                    comment_length = end_index - start_index + 3

                self.setFormat(start_index, comment_length, self.tri_single_format)
                start_index = text.find("'''", start_index + comment_length)

