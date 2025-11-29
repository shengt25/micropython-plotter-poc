from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QSplitter, QStatusBar
from PySide6.QtCore import Qt
from .component.toolbar import CodeToolBar
from .component.code_editor import CodeEditor
from .component.output_console import OutputConsole
from worker.device_manager import DeviceManager
from worker.code_runner import CodeRunner


class CodeWindow(QMainWindow):
    """MicroPython 代码执行窗口"""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("MicroPython Code Runner")
        self.resize(900, 700)

        # 创建后台 Worker
        self.device_manager = DeviceManager('/dev/cu.usbmodem11201')
        self.code_runner = CodeRunner(self.device_manager)

        # 创建 UI 组件
        self._setup_ui()

        # 连接信号
        self._connect_signals()

        # 连接设备
        self._connect_device()

    def _setup_ui(self):
        """设置 UI 布局"""
        # 创建工具栏
        self.toolbar = CodeToolBar(self)
        self.addToolBar(self.toolbar)

        # 创建代码编辑器
        self.code_editor = CodeEditor()

        # 创建输出控制台
        self.output_console = OutputConsole()

        # 使用 QSplitter 分割上下两部分（可调整大小）
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.code_editor)
        splitter.addWidget(self.output_console)

        # 设置初始比例：代码编辑器占 60%，输出控制台占 40%
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)

        # 创建中央部件
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.addWidget(splitter)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setCentralWidget(central_widget)

        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def _connect_signals(self):
        """连接信号和槽"""
        # 工具栏按钮 -> 处理函数
        self.toolbar.run_clicked.connect(self.on_run_code)
        self.toolbar.stop_clicked.connect(self.on_stop_code)
        # self.toolbar.reset_clicked.connect(self.on_reset_device)  # 暂时禁用软重启功能

        # CodeRunner 输出 -> 输出控制台
        self.code_runner.output_received.connect(self.output_console.append_output)
        self.code_runner.error_received.connect(self.output_console.append_error)

    def _connect_device(self):
        """连接设备"""
        self.output_console.append_info("[系统] 正在连接设备...")
        self.status_bar.showMessage("正在连接...")

        if self.device_manager.connect():
            self.output_console.append_info("[系统] 设备连接成功")
            self.status_bar.showMessage("就绪")
        else:
            self.output_console.append_error("[系统] 设备连接失败")
            self.status_bar.showMessage("连接失败")

    def on_run_code(self):
        """运行代码按钮处理"""
        code = self.code_editor.get_code().strip()

        if not code:
            self.output_console.append_error("[错误] 代码为空")
            self.status_bar.showMessage("代码为空")
            return

        # 1. 确保连接（如果未连接则尝试连接）
        if not self.device_manager.is_connected():
            self.output_console.append_info("[系统] 正在连接设备...")
            self.status_bar.showMessage("正在连接...")
            if not self.device_manager.connect():
                self.output_console.append_error("[错误] 设备连接失败")
                self.status_bar.showMessage("连接失败")
                return
            self.output_console.append_info("[系统] 设备连接成功")

        # 2. 无条件清理状态（发送 Ctrl+C + 进入 Raw REPL）
        self.output_console.append_info("[系统] 清理设备状态...")
        if not self.code_runner.stop():
            self.output_console.append_error("[错误] 设备无响应，请手动重启设备（按 RESET 按钮或拔插 USB）")
            self.status_bar.showMessage("设备无响应 - 需要手动重启")
            return

        # 3. 执行新代码
        self.output_console.append_info(f"\n[运行] 执行代码...")
        self.output_console.append_output("-" * 50)
        self.status_bar.showMessage("正在执行...")

        if self.code_runner.run_code(code):
            self.status_bar.showMessage("代码执行成功")
        else:
            self.status_bar.showMessage("代码执行失败")

    def on_stop_code(self):
        """停止代码按钮处理"""
        # 1. 确保连接
        if not self.device_manager.is_connected():
            self.output_console.append_info("[系统] 正在连接设备...")
            self.status_bar.showMessage("正在连接...")
            if not self.device_manager.connect():
                self.output_console.append_error("[错误] 设备连接失败")
                self.status_bar.showMessage("连接失败")
                return

        # 2. 发送停止信号
        self.output_console.append_info("[停止] 正在停止代码...")
        self.status_bar.showMessage("正在停止...")

        if self.code_runner.stop():
            self.status_bar.showMessage("停止成功")
        else:
            self.status_bar.showMessage("停止失败")

    # def on_reset_device(self):
    #     """软重启设备按钮处理 - 暂时禁用"""
    #     self.output_console.append_info("[重启] 正在软重启设备...")
    #     self.code_runner.soft_reset()

    def closeEvent(self, event):
        """窗口关闭事件"""
        self.output_console.append_info("[系统] 正在断开设备连接...")
        self.device_manager.disconnect()
        event.accept()