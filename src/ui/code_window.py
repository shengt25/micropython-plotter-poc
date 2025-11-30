from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QSplitter, QStatusBar, QMessageBox
from PySide6.QtCore import Qt, QThread
from .component.toolbar import CodeToolBar
from .component.tab_editor import TabEditorWidget
from .component.output_console import OutputConsole
from .component.file_browser import FileBrowser
from worker.device_worker import DeviceWorker
from utils.serial_scanner import find_pico_ports, format_label


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

        self.current_port = None
        self.worker_ready = False
        self._connect_when_ready = False

        # 创建文件浏览器
        self.file_browser = FileBrowser()

        # 创建多标签代码编辑器
        self.tab_editor = TabEditorWidget()

        # 创建输出控制台
        self.output_console = OutputConsole()

        # 右侧垂直分割器：代码编辑器 + 输出控制台
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(self.tab_editor)
        right_splitter.addWidget(self.output_console)
        right_splitter.setStretchFactor(0, 7)
        right_splitter.setStretchFactor(1, 3)

        # 主水平分割器：文件浏览器 + 右侧
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(self.file_browser)
        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(0, 4)  # 文件浏览器 40%
        main_splitter.setStretchFactor(1, 6)  # 右侧 60%

        # 创建中央部件
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.addWidget(main_splitter)
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

        # 连接请求信号到槽函数（UI -> Worker）
        # Qt 会自动使用 QueuedConnection，确保在 Worker 线程执行
        self.worker.connect_requested.connect(self.worker.do_connect)
        self.worker.run_code_requested.connect(self.worker.do_run_code)
        self.worker.stop_requested.connect(self.worker.do_stop)
        self.worker.disconnect_requested.connect(self.worker.do_disconnect)
        self.worker.list_dir_requested.connect(self.worker.do_list_dir)
        self.worker.read_file_requested.connect(self.worker.do_read_file)
        self.worker.write_file_requested.connect(self.worker.do_write_file)
        self.worker.set_port_requested.connect(self.worker.set_port)

        # 启动线程
        self.worker_thread.start()

    def _connect_signals(self):
        """连接信号和槽"""
        # 工具栏按钮 -> Worker 操作
        self.toolbar.run_clicked.connect(self.on_run_code)
        self.toolbar.stop_clicked.connect(self.on_stop_code)
        self.toolbar.save_clicked.connect(self.on_save_file)

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

        # 文件浏览器 -> Worker
        self.file_browser.dir_expand_requested.connect(self.worker.list_dir_requested.emit)
        self.file_browser.file_open_requested.connect(self.on_file_open_requested)

        # Worker -> 文件浏览器
        self.worker.list_dir_finished.connect(self.on_list_dir_finished)

        # Worker -> 文件操作
        self.worker.read_file_finished.connect(self.on_read_file_finished)
        self.worker.write_file_finished.connect(self.on_write_file_finished)

        # TabEditor -> UI
        self.tab_editor.file_modified.connect(self.on_file_modified)
        self.tab_editor.active_file_changed.connect(self.on_active_file_changed)

        self.toolbar.port_refresh_requested.connect(lambda: self.refresh_ports())
        self.toolbar.port_selected.connect(self.on_port_selected)

        self.worker.port_changed.connect(lambda port: self.status_bar.showMessage(f"串口已切换到 {port}"))

        # 初始化时扫描一次串口但暂不立即连接（等待 Worker 就绪）
        self.refresh_ports(auto_connect=True)

    def _connect_device(self):
        """连接设备"""
        self.worker_ready = True
        if not self.current_port:
            self.status_bar.showMessage("请选择设备串口")
            return
        if self._connect_when_ready:
            self.worker.connect_requested.emit()
            self._connect_when_ready = False

    def refresh_ports(self, auto_connect: bool = True):
        ports = [(info.device, format_label(info)) for info in find_pico_ports()]
        self.toolbar.set_ports(ports, self.current_port)
        devices = [device for device, _ in ports]

        if not ports:
            self.current_port = None
            self.status_bar.showMessage("未检测到 Raspberry Pi Pico 设备")
            self._connect_when_ready = False
            return

        if not self.current_port or self.current_port not in devices:
            self.current_port = devices[0]
            self.status_bar.showMessage(f"已选择 {self.current_port}")

        self.worker.set_port_requested.emit(self.current_port)

        if auto_connect:
            if self.worker_ready:
                self.status_bar.showMessage(f"正在连接 {self.current_port}...")
                self.worker.connect_requested.emit()
            else:
                self._connect_when_ready = True

    def on_port_selected(self, port: str):
        if port == self.current_port:
            return
        self.current_port = port
        self.worker.set_port_requested.emit(port)
        if self.worker_ready:
            self.status_bar.showMessage(f"切换串口到 {port}，正在连接...")
            self.worker.connect_requested.emit()
        else:
            self._connect_when_ready = True
            self.status_bar.showMessage(f"已选择 {port}，等待 Worker 初始化后连接")

    def on_run_code(self):
        """运行代码按钮处理"""
        # 1. 先检查当前文件是否需要保存
        path, content, modified = self.tab_editor.get_current_file_info()
        if path and modified:
            # 自动保存
            self.output_console.append_info("[系统] 自动保存文件...")
            self.worker.write_file_requested.emit(path, content)
            # 标记为已保存
            self.tab_editor.mark_current_saved()

        # 2. 获取代码
        code = self.tab_editor.get_current_code().strip()

        if not code:
            self.output_console.append_error("[错误] 代码为空")
            self.status_bar.showMessage("代码为空")
            return

        # 禁用按钮，防止重复点击
        self.set_buttons_enabled(False)

        # 触发 Worker 执行代码（异步执行）
        self.worker.run_code_requested.emit(code)

    def on_stop_code(self):
        """停止代码按钮处理"""
        # 禁用按钮，防止重复点击
        self.set_buttons_enabled(False)

        # 触发 Worker 停止代码（异步执行）
        self.worker.stop_requested.emit()

    def on_connect_finished(self, success):
        """连接完成处理"""
        if success:
            self.file_browser.initialize_root()
        else:
            self.file_browser.show_error("设备连接失败")

    def on_run_finished(self, success):
        """运行完成处理"""
        # 恢复按钮状态
        self.set_buttons_enabled(True)

    def on_stop_finished(self, success):
        """停止完成处理"""
        self.set_buttons_enabled(True)

        if success:
            self.file_browser.initialize_root()
            return

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("设备无响应")
        msg_box.setText("无法停止设备或软重启失败")
        msg_box.setInformativeText(
            "请尝试以下操作：\n"
            "1. 按下设备上的 RESET 按钮\n"
            "2. 或者拔插 USB 线重新连接\n"
            "3. 然后重启应用程序"
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def on_list_dir_finished(self, success: bool, path: str, items: list):
        """目录列出完成处理"""
        if success:
            self.file_browser.populate_directory(path, items)
            return

        self.file_browser.show_error(f"[文件浏览器] 无法列出目录: {path}")
        self.output_console.append_error(f"[文件浏览器] 无法列出目录: {path}")

    def on_file_open_requested(self, path: str):
        """文件打开请求处理（双击文件）"""
        self.output_console.append_info(f"[文件] 正在打开: {path}")
        # 触发 Worker 读取文件
        self.worker.read_file_requested.emit(path)

    def on_read_file_finished(self, success: bool, path: str, content: str):
        """文件读取完成处理"""
        if success:
            # 在新标签中打开文件
            self.tab_editor.open_file(path, content)
            self.output_console.append_info(f"[文件] 成功打开: {path}")
        else:
            self.output_console.append_error(f"[文件] 打开失败: {path}")

    def on_save_file(self):
        """保存文件按钮处理"""
        path, content, modified = self.tab_editor.get_current_file_info()

        if not path:
            self.output_console.append_error("[文件] 当前标签没有关联文件")
            return

        if not modified:
            self.output_console.append_info("[文件] 文件未修改，无需保存")
            return

        # 触发 Worker 写入文件
        self.output_console.append_info(f"[文件] 正在保存: {path}")
        self.worker.write_file_requested.emit(path, content)

        # 标记为已保存
        self.tab_editor.mark_current_saved()

    def on_write_file_finished(self, success: bool, path: str):
        """文件写入完成处理"""
        if not success:
            self.output_console.append_error(f"[文件] 保存失败: {path}")

    def on_file_modified(self, modified: bool):
        """文件修改状态改变处理"""
        # 更新保存按钮状态
        self.toolbar.save_action.setEnabled(modified)

    def on_active_file_changed(self, path: str):
        """活动文件改变处理"""
        # 更新状态栏
        if path:
            self.status_bar.showMessage(f"当前文件: {path}")
        else:
            self.status_bar.showMessage("就绪")

        # 更新保存按钮状态
        _, _, modified = self.tab_editor.get_current_file_info()
        self.toolbar.save_action.setEnabled(modified)

    def set_buttons_enabled(self, enabled: bool):
        """设置按钮启用/禁用状态"""
        self.toolbar.run_action.setEnabled(enabled)
        self.toolbar.stop_action.setEnabled(enabled)

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 1. 断开设备（在 Worker 线程中执行）
        self.output_console.append_info("[系统] 正在断开设备连接...")
        self.worker.disconnect_requested.emit()

        # 2. 停止并等待线程结束
        self.worker_thread.quit()
        self.worker_thread.wait(3000)  # 最多等待 3 秒

        # 3. 接受关闭事件
        event.accept()
