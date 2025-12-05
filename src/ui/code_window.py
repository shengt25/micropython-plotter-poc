from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QSplitter, QStatusBar, QMessageBox, QDialog
from PySide6.QtCore import Qt, QThread, QTimer
from .plotter_window import PlotterWindow
from .component.toolbar import CodeToolBar
from .component.tab_editor import TabEditorWidget
from .component.output_console import OutputConsole
from .component.file_browser import FileBrowser
from .component.device_save_dialog import DeviceSaveDialog
from worker.device_worker import DeviceWorker
from utils.serial_scanner import find_pico_ports, format_label


class CodeWindow(QMainWindow):
    """MicroPython 代码执行窗口"""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("MicroPython Code Runner")
        self.resize(1000, 700)

        # 绘图窗口（按需创建）
        self.plotter_window = None
        self.auto_open_plot = True

        # 创建 UI 组件
        self._setup_ui()

        # 创建串口监控
        self._setup_port_monitor()

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
        self._busy_directory_paths: set[str] = set()
        self._pending_deletes: dict[str, bool] = {}  # 记录待删除路径的类型 {path: is_dir}

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
        main_splitter.setStretchFactor(0, 3)  # 文件浏览器 30%
        main_splitter.setStretchFactor(1, 7)  # 右侧 70%

        # 创建中央部件
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.addWidget(main_splitter)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setCentralWidget(central_widget)

        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Initializing...")

    def _setup_port_monitor(self):
        self.port_monitor = QTimer(self)
        self.port_monitor.setInterval(1500)
        self.port_monitor.timeout.connect(self._check_current_port_status)
        self.port_monitor.start()

    def _setup_worker(self):
        """设置后台线程和 Worker"""
        # 创建线程
        self.worker_thread = QThread()

        # 创建 Worker（会在线程中运行）
        self.worker = DeviceWorker('')

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
        self.worker.delete_path_requested.connect(self.worker.do_delete_path)
        self.worker.set_port_requested.connect(self.worker.set_port)

        # 启动线程
        self.worker_thread.start()

    def _connect_signals(self):
        """连接信号和槽"""
        # 工具栏按钮 -> Worker 操作
        self.toolbar.new_clicked.connect(self.on_new_file)
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
        self.file_browser.delete_requested.connect(self.on_delete_requested)

        # Worker -> 文件浏览器
        self.worker.list_dir_finished.connect(self.on_list_dir_finished)

        # Worker -> 文件操作
        self.worker.read_file_finished.connect(self.on_read_file_finished)
        self.worker.write_file_finished.connect(self.on_write_file_finished)
        self.worker.delete_path_finished.connect(self.on_delete_path_finished)
        self.worker.file_access_busy.connect(self.on_file_access_busy)

        # TabEditor -> UI
        self.tab_editor.file_modified.connect(self.on_file_modified)
        self.tab_editor.active_file_changed.connect(self.on_active_file_changed)
        self.tab_editor.save_requested.connect(self.on_save_file)

        self.toolbar.port_refresh_requested.connect(
            lambda: self.refresh_ports(auto_connect=False, select_if_missing=False)
        )
        self.toolbar.port_selected.connect(self.on_port_selected)

        self.worker.port_changed.connect(lambda port: self.status_bar.showMessage(f"Serial port switched to {port}"))

        # 绘图按钮 -> 打开绘图窗口
        self.toolbar.plot_clicked.connect(self.on_plot_clicked)

        # 绘图数据 -> 转发到绘图窗口
        self.worker.plot_data_received.connect(self._forward_plot_data)
        self.worker.plot_config_received.connect(self._forward_plot_config)

        # 初始化时扫描一次串口但暂不立即连接（等待 Worker 就绪）
        self.refresh_ports(auto_connect=True)

    def _connect_device(self):
        """连接设备"""
        self.worker_ready = True
        if not self.current_port:
            self.status_bar.showMessage("Please select a port")
            return
        if self._connect_when_ready:
            self.worker.connect_requested.emit()
            self._connect_when_ready = False

    def refresh_ports(self, auto_connect: bool = True, select_if_missing: bool = True):
        port_infos = list(find_pico_ports())
        ports = [(info.device, format_label(info)) for info in port_infos]
        devices = [device for device, _ in ports]

        if not ports:
            self.current_port = None
            self.toolbar.set_ports([], None)
            self.toolbar.show_disconnected_placeholder()
            self.status_bar.showMessage("disconnected")
            self._connect_when_ready = False
            return

        selected_port = self.current_port if self.current_port in devices else None

        if not selected_port and select_if_missing:
            self.current_port = devices[0]
            selected_port = self.current_port
            self.status_bar.showMessage(f"Selected {self.current_port}")
        else:
            self.current_port = selected_port

        self.toolbar.set_ports(ports, selected_port)

        if not selected_port:
            self.toolbar.show_disconnected_placeholder()
            self.status_bar.showMessage("disconnected")
            self._connect_when_ready = False
            return

        self.worker.set_port_requested.emit(selected_port)

        if auto_connect:
            if self.worker_ready:
                self.status_bar.showMessage(f"Connecting {selected_port}...")
                self.worker.connect_requested.emit()
            else:
                self._connect_when_ready = True

    def _check_current_port_status(self):
        if not self.current_port:
            return

        port_infos = list(find_pico_ports())
        devices = [info.device for info in port_infos]

        if self.current_port in devices:
            return

        self._handle_device_disconnected(port_infos)

    def _handle_device_disconnected(self, port_infos):
        if not self.current_port:
            return

        self.worker.disconnect_requested.emit()
        self.current_port = None
        self._connect_when_ready = False
        ports = [(info.device, format_label(info)) for info in port_infos]
        self.toolbar.set_ports(ports, None)
        self.toolbar.show_disconnected_placeholder()
        self.status_bar.showMessage("disconnected")

    def on_port_selected(self, port: str):
        if port == self.current_port:
            return
        self.current_port = port
        self.worker.set_port_requested.emit(port)
        if self.worker_ready:
            self.status_bar.showMessage(f"Serial port switched to {port}，connecting...")
            self.worker.connect_requested.emit()
        else:
            self._connect_when_ready = True
            self.status_bar.showMessage(f"Selected {port}，getting ready...")

    def on_new_file(self):
        self.tab_editor.create_new_tab()
        self.status_bar.showMessage("Created new tab")

    def on_run_code(self):
        """运行代码按钮处理"""
        # 1. 先检查当前文件是否需要保存
        self.auto_open_plot = True
        path, content, modified = self.tab_editor.get_current_file_info()
        if path and modified:
            # 自动保存（等待异步完成信号后才标记为已保存）
            self.output_console.append_info("[System] Auto saving file...")
            self.worker.write_file_requested.emit(path, content)

        # 2. 获取代码
        code = self.tab_editor.get_current_code().strip()

        if not code:
            self.output_console.append_error("[Error] Code is empty")
            self.status_bar.showMessage("Code is empty")
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
            self.file_browser.show_error("Connecting to device failed")

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
        msg_box.setWindowTitle("Device no response")
        msg_box.setText("Cannot stop device or soft reset device.")
        msg_box.setInformativeText(
            "Please try:\n"
            "1. Press the reset button on the device\n"
            "2. or re-plug the USB cable\n"
            "3. Then click stop/reset button again\n"
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def on_list_dir_finished(self, success: bool, path: str, items: list):
        """目录列出完成处理"""
        if success:
            self.file_browser.populate_directory(path, items)
            self._busy_directory_paths.discard(path)
            return

        if path in self._busy_directory_paths:
            # 设备忙导致目录刷新失败，保持已有列表
            self._busy_directory_paths.discard(path)
            self.file_browser.cancel_directory_request(path)
            self.output_console.append_info(
                f"[File browser] Device busy while refreshing {path}, keeping previous entries"
            )
            return

        self.file_browser.show_error(f"[File browser] Cannot list directory: {path}")
        self.output_console.append_error(f"[File browser] Cannot list directory: {path}")

    def on_delete_requested(self, path: str, is_dir: bool):
        """文件或目录删除请求"""
        target = "folder" if is_dir else "file"
        self.output_console.append_info(f"[File] Deleting {target}: {path}")
        # 记录删除类型，用于删除成功后的处理
        self._pending_deletes[path] = is_dir
        self.worker.delete_path_requested.emit(path)

    def on_file_open_requested(self, path: str):
        """文件打开请求处理（双击文件）"""
        self.output_console.append_info(f"[File] Opening: {path}")
        # 触发 Worker 读取文件
        self.worker.read_file_requested.emit(path)

    def on_read_file_finished(self, success: bool, path: str, content: str):
        """文件读取完成处理"""
        if success:
            # 检查文件是否已经在标签中打开
            current_path, _, _ = self.tab_editor.get_current_file_info()

            # 查找是否有已打开的标签
            is_already_open = False
            for index, state in self.tab_editor.tab_states.items():
                if state['path'] == path:
                    is_already_open = True
                    break

            if is_already_open:
                # 已打开，更新内容（不触发修改标记）
                self.tab_editor.update_file_content(path, content)
                self.output_console.append_info(f"[File] Updated: {path}")
            else:
                # 未打开，在新标签中打开
                self.tab_editor.open_file(path, content)
                self.output_console.append_info(f"[File] Opened: {path}")
        else:
            self.output_console.append_error(f"[File] Open failed: {path}")

    def on_save_file(self):
        """保存文件按钮处理"""
        path, content, modified = self.tab_editor.get_current_file_info()
        is_new_file = path is None

        if is_new_file:
            selected_path = self._prompt_save_location()
            if not selected_path:
                self.output_console.append_info("[File] Save cancelled")
                return

            exists, is_dir = self.file_browser.path_exists(selected_path)
            if exists and not is_dir:
                reply = QMessageBox.question(
                    self,
                    "Overwrite file?",
                    f"{selected_path} already exists. Overwrite?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self.output_console.append_info("[File] Save cancelled")
                    return

            self.tab_editor.set_current_file_path(selected_path)
            path = selected_path

        if not modified and not is_new_file:
            self.output_console.append_info("[File] No modification made")
            return

        # 触发 Worker 写入文件（等待异步完成信号后才标记为已保存）
        self.output_console.append_info(f"[File] Saving: {path}")
        self.worker.write_file_requested.emit(path, content)

    def on_write_file_finished(self, success: bool, path: str):
        """文件写入完成处理"""
        if success:
            # 保存成功，标记为已保存
            self.tab_editor.mark_file_saved(path)
            self.output_console.append_info(f"[File] Save successfully: {path}")
            parent_dir = self._parent_directory(path)
            # 主动刷新父目录，确保文件浏览器立即反映保存结果
            self.file_browser.request_directory(parent_dir)

            # 重新读取文件，确保内容一致
            self.output_console.append_info(f"[File] Reloading after saving...")
            self.worker.read_file_requested.emit(path)
        else:
            # 保存失败，保持修改状态
            self.output_console.append_error(f"[File] Save failed: {path}")

    def on_delete_path_finished(self, success: bool, path: str):
        """文件/目录删除完成"""
        if success:
            # 从待删除字典中获取类型信息
            is_dir = self._pending_deletes.pop(path, False)

            # 关闭相关的标签页
            if is_dir:
                # 如果删除的是目录，关闭该目录下所有文件的标签页
                self.tab_editor.close_files_under_directory(path)
            else:
                # 如果删除的是文件，只关闭该文件的标签页
                self.tab_editor.close_file(path)

            # 从文件浏览器中移除
            self.file_browser.remove_entry(path)

            # 刷新父目录
            parent_dir = self._parent_directory(path)
            self.file_browser.request_directory(parent_dir)

            self.output_console.append_info(f"[File] Deleted: {path}")
        else:
            # 删除失败，清理待删除记录
            self._pending_deletes.pop(path, None)
            self.output_console.append_error(f"[File] Delete failed: {path}")

    def on_file_modified(self, modified: bool):
        """文件修改状态改变处理"""
        # 更新保存按钮状态
        can_save = modified or self.tab_editor.current_is_untitled()
        self.toolbar.save_action.setEnabled(can_save)

    def on_file_access_busy(self, operation: str, path: str):
        """显示设备忙提示框，允许用户停止程序"""
        base_text = operation or "the requested file operation"
        if operation == "list directory" and path:
            self._busy_directory_paths.add(path)
        if path:
            operation_text = f"{base_text} ({path})"
        else:
            operation_text = base_text
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Device Busy")
        dialog.setText(f"Cannot {operation_text}: the device is busy.")
        dialog.setInformativeText(
            "Stop the program or reset the device by reconnecting to the computer."
        )

        got_it_button = dialog.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        stop_button = dialog.addButton("Stop program", QMessageBox.ButtonRole.ActionRole)
        dialog.setDefaultButton(got_it_button)
        dialog.exec()

        if dialog.clickedButton() == stop_button:
            self.worker.stop_requested.emit()

    def _prompt_save_location(self) -> str | None:
        default_dir = self.file_browser.get_selected_directory()
        dialog = DeviceSaveDialog(
            default_directory=default_dir,
            default_name="untitled.py",
            file_browser=self.file_browser,
            parent=self,
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selected_path()

        return None

    def on_active_file_changed(self, path: str):
        """活动文件改变处理"""
        # 更新状态栏
        if path:
            self.status_bar.showMessage(f"Current file: {path}")
        else:
            self.status_bar.showMessage("Ready")

        # 更新保存按钮状态
        _, _, modified = self.tab_editor.get_current_file_info()
        can_save = modified or self.tab_editor.current_is_untitled()
        self.toolbar.save_action.setEnabled(can_save)

    def set_buttons_enabled(self, enabled: bool):
        """设置按钮启用/禁用状态"""
        self.toolbar.run_action.setEnabled(enabled)
        self.toolbar.stop_action.setEnabled(enabled)

    @staticmethod
    def _parent_directory(path: str) -> str:
        """返回文件的父目录（路径为空时返回根目录）"""
        if not path:
            return '/'
        normalized = path.rstrip('/') or '/'
        if normalized == '/':
            return '/'
        parent = normalized.rsplit('/', 1)[0]
        return parent or '/'

    def on_plot_clicked(self):
        """绘图按钮点击处理"""
        self.auto_open_plot = True

        # 如果窗口已存在，先关闭并销毁
        if self.plotter_window is not None:
            self.plotter_window.close()
            self.plotter_window.deleteLater()
            self.plotter_window = None

        # 创建新窗口（确保数据重置）
        self.plotter_window = PlotterWindow()
        self.plotter_window.closed.connect(self._on_plotter_closed)

        # 显示窗口
        self.plotter_window.show()
        self.plotter_window.raise_()
        self.plotter_window.activateWindow()

        # 启用绘图模式
        self.worker.set_plot_mode(True)

    def _on_plotter_closed(self):
        """绘图窗口关闭处理"""
        # 禁用绘图模式
        self.worker.set_plot_mode(False)
        self.auto_open_plot = False

    def _forward_plot_data(self, values: list):
        """
        转发绘图数据到绘图窗口

        Args:
            values: 绘图数据值列表
        """
        if not values:
            return

        if (not self.plotter_window or not self.plotter_window.isVisible()) and self.auto_open_plot:
            self.on_plot_clicked()

        if self.plotter_window and self.plotter_window.isVisible():
            self.plotter_window.on_plot_data_received(values)

    def _forward_plot_config(self, names: list):
        """接收到通道配置后更新绘图窗口的图例名称"""
        if not names:
            return

        if (not self.plotter_window or not self.plotter_window.isVisible()) and self.auto_open_plot:
            self.on_plot_clicked()

        if self.plotter_window and self.plotter_window.isVisible():
            self.plotter_window.on_plot_config_received(names)

    def closeEvent(self, event):
        """窗口关闭事件"""
        if hasattr(self, "port_monitor") and self.port_monitor.isActive():
            self.port_monitor.stop()

        # 1. 关闭绘图窗口
        if self.plotter_window:
            self.plotter_window.close()

        # 2. 断开设备（在 Worker 线程中执行）
        self.output_console.append_info("[System] Disconnecting device...")
        self.worker.disconnect_requested.emit()

        # 3. 停止并等待线程结束
        self.worker_thread.quit()
        self.worker_thread.wait(3000)  # 最多等待 3 秒

        # 4. 接受关闭事件
        event.accept()
