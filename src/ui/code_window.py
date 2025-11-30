from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QSplitter, QStatusBar
from PySide6.QtCore import Qt, QThread
from .component.toolbar import CodeToolBar
from .component.code_editor import CodeEditor
from .component.output_console import OutputConsole
from worker.device_worker import DeviceWorker


class CodeWindow(QMainWindow):
    """MicroPython 代码执行窗口"""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("MicroPython Code Runner")
        self.resize(900, 700)

        # 创建 UI 组件
        self._setup_ui()

        # 创建后台线程和 Worker
        self._setup_worker()

        # 连接信号
        self._connect_signals()

        # Worker 初始化完成后自动连接设备
        # （不在 __init__ 直接调用，避免 Worker 未初始化）

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
        self.status_bar.showMessage("初始化中...")

    def _setup_worker(self):
        """设置后台线程和 Worker"""
        # 创建线程
        self.worker_thread = QThread()

        # 创建 Worker（会在线程中运行）
        self.worker = DeviceWorker('/dev/cu.usbmodem11201')

        # 将 Worker 移动到线程
        self.worker.moveToThread(self.worker_thread)

        # 在线程启动后初始化 Worker（重要：必须在线程中创建串口对象）
        self.worker_thread.started.connect(self.worker.initialize)

        # 启动线程
        self.worker_thread.start()

    def _connect_signals(self):
        """连接信号和槽"""
        # 工具栏按钮 -> Worker 操作
        self.toolbar.run_clicked.connect(self.on_run_code)
        self.toolbar.stop_clicked.connect(self.on_stop_code)

        # Worker 初始化完成 -> 自动连接设备
        self.worker.initialized.connect(self._connect_device)

        # Worker 进度信息 -> UI
        self.worker.progress.connect(self.output_console.append_info)
        self.worker.status_changed.connect(self.status_bar.showMessage)

        # Worker 输出信息 -> 输出控制台
        self.worker.output_received.connect(self.output_console.append_output)
        self.worker.error_received.connect(self.output_console.append_error)

        # Worker 操作完成 -> UI 更新
        self.worker.connect_finished.connect(self.on_connect_finished)
        self.worker.run_finished.connect(self.on_run_finished)
        self.worker.stop_finished.connect(self.on_stop_finished)

    def _connect_device(self):
        """连接设备"""
        # 触发 Worker 连接设备（异步执行）
        self.worker.do_connect()

    def on_run_code(self):
        """运行代码按钮处理"""
        code = self.code_editor.get_code().strip()

        if not code:
            self.output_console.append_error("[错误] 代码为空")
            self.status_bar.showMessage("代码为空")
            return

        # 禁用按钮，防止重复点击
        self.set_buttons_enabled(False)

        # 触发 Worker 执行代码（异步执行）
        self.worker.do_run_code(code)

    def on_stop_code(self):
        """停止代码按钮处理"""
        # 禁用按钮，防止重复点击
        self.set_buttons_enabled(False)

        # 触发 Worker 停止代码（异步执行）
        self.worker.do_stop()

    def on_connect_finished(self, success):
        """连接完成处理"""
        # 连接完成后，不需要特殊处理（状态栏已经通过 status_changed 更新）
        pass

    def on_run_finished(self, success):
        """运行完成处理"""
        # 恢复按钮状态
        self.set_buttons_enabled(True)

    def on_stop_finished(self, success):
        """停止完成处理"""
        # 恢复按钮状态
        self.set_buttons_enabled(True)

    def set_buttons_enabled(self, enabled: bool):
        """设置按钮启用/禁用状态"""
        self.toolbar.run_action.setEnabled(enabled)
        self.toolbar.stop_action.setEnabled(enabled)

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 1. 断开设备（在 Worker 线程中执行）
        self.output_console.append_info("[系统] 正在断开设备连接...")
        self.worker.do_disconnect()

        # 2. 停止并等待线程结束
        self.worker_thread.quit()
        self.worker_thread.wait(3000)  # 最多等待 3 秒

        # 3. 接受关闭事件
        event.accept()
