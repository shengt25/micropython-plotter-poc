from PySide6.QtWidgets import QToolBar, QComboBox
from PySide6.QtCore import Signal
from PySide6.QtGui import QAction

class CodeToolBar(QToolBar):

    # Signals
    run_clicked = Signal()
    stop_clicked = Signal()
    save_clicked = Signal()
    port_refresh_requested = Signal()
    port_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Code Control", parent)

        self.run_action = QAction("Run", self)
        self.stop_action = QAction("Stop", self)
        self.save_action = QAction("Save", self)
        self.port_combo = QComboBox(self)
        self.port_combo.setPlaceholderText("选择串口…")
        self.port_combo.setMinimumWidth(200)
        self.port_combo.currentIndexChanged.connect(self._on_port_changed)
        self.refresh_ports_action = QAction("刷新串口", self)
        self.refresh_ports_action.triggered.connect(self.port_refresh_requested.emit)

        self.run_action.triggered.connect(self.run_clicked.emit)
        self.stop_action.triggered.connect(self.stop_clicked.emit)
        self.save_action.triggered.connect(self.save_clicked.emit)

        # 保存按钮默认禁用（只有打开文件并修改后才启用）
        self.save_action.setEnabled(False)

        self.addAction(self.run_action)
        self.addAction(self.stop_action)
        self.addSeparator()
        self.addAction(self.save_action)
        self.addSeparator()
        self.addWidget(self.port_combo)
        self.addAction(self.refresh_ports_action)

        self.setMovable(False)

    def set_ports(self, ports: list[tuple[str, str]], current_port: str | None = None):
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        for device, label in ports:
            self.port_combo.addItem(label, device)

        if current_port:
            index = self.port_combo.findData(current_port)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
            else:
                self.port_combo.setCurrentIndex(-1)
        else:
            self.port_combo.setCurrentIndex(-1)

        self.port_combo.blockSignals(False)

    def _on_port_changed(self, index: int):
        if index < 0:
            return
        device = self.port_combo.itemData(index)
        if device:
            self.port_selected.emit(device)
