import sys
from PySide6.QtWidgets import QApplication
from ui.code_window import CodeWindow


def main():
    app = QApplication(sys.argv)

    window = CodeWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
