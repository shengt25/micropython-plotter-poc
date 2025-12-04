from PySide6.QtWidgets import QToolBar, QComboBox
from PySide6.QtCore import Signal
from PySide6.QtGui import QAction


class PortComboBox(QComboBox):
    popup_about_to_show = Signal()

    def showPopup(self):
        self.popup_about_to_show.emit()
        super().showPopup()


class CodeToolBar(QToolBar):

    # Signals
    new_clicked = Signal()
    run_clicked = Signal()
    stop_clicked = Signal()
    save_clicked = Signal()
    plot_clicked = Signal()
    port_refresh_requested = Signal()
    port_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Code Control", parent)

        self.new_action = QAction("New", self)
        self.save_action = QAction("Save", self)
        self.run_action = QAction("Run", self)
        self.stop_action = QAction("Stop/Reset", self)
        self.plot_action = QAction("Plot", self)
        self.port_combo = PortComboBox(self)
        self.port_combo.setPlaceholderText("Select port…")
        self.port_combo.setMinimumWidth(200)
        self.port_combo.currentIndexChanged.connect(self._on_port_changed)
        self.port_combo.popup_about_to_show.connect(self.port_refresh_requested.emit)

        self.new_action.triggered.connect(self.new_clicked.emit)
        self.run_action.triggered.connect(self.run_clicked.emit)
        self.stop_action.triggered.connect(self.stop_clicked.emit)
        self.save_action.triggered.connect(self.save_clicked.emit)
        self.plot_action.triggered.connect(self.plot_clicked.emit)

        # 保存按钮默认禁用（只有打开文件并修改后才启用）
        self.save_action.setEnabled(False)

        self.addAction(self.new_action)
        self.addAction(self.save_action)
        self.addSeparator()
        self.addAction(self.run_action)
        self.addAction(self.stop_action)
        self.addSeparator()
        self.addAction(self.plot_action)
        self.addSeparator()
        self.addWidget(self.port_combo)

        self.setMovable(False)

    def set_ports(self, ports: list[tuple[str, str]], current_port: str | None = None):
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        if ports:
            self.port_combo.setPlaceholderText("Select port…")
            for device, label in ports:
                self.port_combo.addItem(label, device)
        else:
            self._set_no_device_item()
            self.port_combo.blockSignals(False)
            return

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

    def show_disconnected_placeholder(self):
        self.port_combo.blockSignals(True)
        if self.port_combo.count() == 0:
            self._set_no_device_item()
        else:
            self.port_combo.setPlaceholderText("Disconnected")
            self.port_combo.setCurrentIndex(-1)
        self.port_combo.blockSignals(False)

    def _set_no_device_item(self):
        self.port_combo.setPlaceholderText("Disconnected")
        self.port_combo.addItem("No device found")
        item = self.port_combo.model().item(0)
        if item:
            item.setEnabled(False)
            item.setSelectable(False)
        self.port_combo.setCurrentIndex(0)
