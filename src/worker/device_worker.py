from PySide6.QtCore import QObject, Signal, Slot, QTimer
from .device_manager import DeviceManager
from .code_runner import CodeRunner
from .plot_stream_handler import PlotStreamHandler
from utils.logger import setup_logger
from .file_manager import FileManager


class DeviceWorker(QObject):
    """
    在后台线程中执行设备操作的 Worker
    避免阻塞 UI 线程
    """

    # Signals - 请求信号（UI -> Worker）
    connect_requested = Signal()        # 请求连接设备
    run_code_requested = Signal(str)    # 请求运行代码
    stop_requested = Signal()           # 请求停止代码
    disconnect_requested = Signal()     # 请求断开连接
    list_dir_requested = Signal(str)    # 请求列出目录
    read_file_requested = Signal(str)   # 请求读取文件
    write_file_requested = Signal(str, str)  # 请求写入文件 (path, content)
    delete_path_requested = Signal(str)  # 请求删除文件或目录
    set_port_requested = Signal(str)        # 请求切换串口

    # Signals - 操作完成信号
    initialized = Signal()              # Worker 初始化完成
    connect_finished = Signal(bool)     # 连接完成 (成功/失败)
    disconnect_finished = Signal()      # 断开完成
    run_finished = Signal(bool)         # 运行完成 (成功/失败)
    stop_finished = Signal(bool)        # 停止完成 (成功/失败)
    list_dir_finished = Signal(bool, str, list)  # 列出目录完成 (success, path, items)
    read_file_finished = Signal(bool, str, str)  # 读取文件完成 (success, path, content)
    write_file_finished = Signal(bool, str)      # 写入文件完成 (success, path)
    delete_path_finished = Signal(bool, str)     # 删除路径完成 (success, path)
    file_access_busy = Signal(str, str)          # 设备忙导致文件操作失败 (operation, path)

    # Signals - 进度信息
    progress = Signal(str)              # 进度消息（显示在输出控制台）
    status_changed = Signal(str)        # 状态变化（显示在状态栏）

    # Signals - 输出信息（从 CodeRunner 转发）
    output_received = Signal(str)
    error_received = Signal(str)

    # Signals - 绘图数据
    plot_data_received = Signal(list)  # 绘图数据包
    plot_config_received = Signal(list)  # 绘图通道配置

    # Signals - 端口变化
    port_changed = Signal(str)

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate

        # 这些对象会在 Worker 线程中创建和使用
        self.device_manager = None
        self.code_runner = None
        self.plot_handler = None
        self.monitor_timer = None
        self.plot_mode_enabled = False

    @Slot()
    def initialize(self):
        """
        在 Worker 线程中初始化设备管理器
        必须在 moveToThread 之后调用
        """
        self.device_manager = DeviceManager(self.port, self.baudrate)
        self.code_runner = CodeRunner(self.device_manager)

        # 创建绘图数据流处理器
        self.plot_handler = PlotStreamHandler(self.device_manager)

        # 连接 CodeRunner 的 Signals 并转发到 UI
        self.code_runner.error_received.connect(self.error_received.emit)

        # 连接 PlotStreamHandler 的 Signals
        self.plot_handler.plot_data_received.connect(self.plot_data_received.emit)
        self.plot_handler.plot_config_received.connect(self.plot_config_received.emit)
        self.plot_handler.text_data_received.connect(self.output_received.emit)

        # 创建后台监控定时器
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._monitor_serial_output)

        # 发出初始化完成信号
        self.initialized.emit()

    @Slot()
    def do_connect(self):
        """连接设备"""
        self.progress.emit("[System] Connecting to device...")
        self.status_changed.emit("Connecting...")

        success = self.device_manager.connect()

        if success:
            self.progress.emit("[System] Connected successfully")
            self.status_changed.emit("Ready")
        else:
            self.progress.emit("[System] Connection failed")
            self.status_changed.emit("Connection failed")

        self.connect_finished.emit(success)

    @Slot()
    def do_disconnect(self):
        """断开设备（用户主动断开）"""
        self.progress.emit("[System] Disconnecting from device...")
        self.status_changed.emit("Disconnecting...")

        # 停止后台监控定时器（如果正在运行）
        if self.monitor_timer and self.monitor_timer.isActive():
            self.monitor_timer.stop()

        # 断开连接
        self.device_manager.disconnect()

        self.progress.emit("[System] Disconnected")
        self.status_changed.emit("Disconnected")
        self.disconnect_finished.emit()

    @Slot(str)
    def do_run_code(self, code: str):
        """
        运行代码

        步骤：
        1. 检查连接
        2. 清理设备状态
        3. 执行代码
        """
        # 1. 确保连接
        if not self.device_manager.is_connected():
            self.progress.emit("[System] Connecting to device...")
            self.status_changed.emit("Connecting...")
            if not self.device_manager.connect():
                self.progress.emit("[System] Failed to connect to device")
                self.status_changed.emit("Failed to connect")
                self.run_finished.emit(False)
                return
            self.progress.emit("[System] Successfully connected to device")

        # 2. 清理设备状态
        self.progress.emit("[System] Cleaning up status...")
        if not self.code_runner.stop():
            self.progress.emit("[Error] Device no response, click stop/reset or hard reset on device")
            self.status_changed.emit("Device no response")
            self.run_finished.emit(False)
            return

        # 3. 执行代码
        self.progress.emit("\n[Info] Running code...")
        self.progress.emit("-" * 50)
        self.status_changed.emit("Running...")
        if self.plot_handler:
            self.plot_handler.reset_config_state()

        success = self.code_runner.run_code(code)

        if success:
            # 启动后台监控，读取串口输出
            if self.monitor_timer:
                self.monitor_timer.start(50)  # 每 50ms 轮询一次
            self.status_changed.emit("Code running successfully")
        else:
            self.status_changed.emit("Code running failed")

        self.run_finished.emit(success)

    @Slot()
    def do_stop(self):
        """
        停止代码

        步骤：
        1. 停止后台监控
        2. 直接发送停止信号（不先握手，避免等待超时）
        3. 如果串口异常，自动重新连接
        """
        # 1. 停止后台监控
        if self.monitor_timer and self.monitor_timer.isActive():
            self.monitor_timer.stop()

        # 2. 直接发送停止信号（无论是否显示为已连接）
        # 即使串口状态不明，也先尝试发送 Ctrl+C/Ctrl+D
        # 这样可以避免在设备疯狂输出时等待握手超时
        self.progress.emit("[Stop] Stopping code execution...")
        self.status_changed.emit("Stopping...")

        success = self.code_runner.stop()

        # 3. 如果返回 None，表示串口异常，需要重新连接
        if success is None:
            self.progress.emit("[System] Device disconnected, reconnecting...")
            self.status_changed.emit("Reconnecting...")

            # 断开旧连接
            self.device_manager.disconnect()

            # 尝试重新连接
            if self.device_manager.connect():
                self.progress.emit("[System] Reconnected successfully, stopping code...")
                success = self.code_runner.stop()

                if success:
                    self.status_changed.emit("Stopped successfully")
                    self.stop_finished.emit(True)
                else:
                    self.progress.emit("[System] Stop failed")
                    self.status_changed.emit("Stop failed")
                    self.stop_finished.emit(False)
            else:
                self.progress.emit("[System] Reconnection failed, please check device")
                self.status_changed.emit("Connection failed")
                self.stop_finished.emit(False)
        elif success:
            self.status_changed.emit("Stopped successfully")
            self.stop_finished.emit(True)
        else:
            self.status_changed.emit("Stop failed")
            self.stop_finished.emit(False)

    @Slot(str)
    def do_list_dir(self, path: str):
        """列出目录内容（在 Worker 线程执行）"""

        logger = setup_logger(__name__)

        # 1. 检查连接
        if not self.device_manager.is_connected():
            logger.warning("[文件浏览器] 设备未连接")
            self.progress.emit("[File Browser] Device not connected")
            self.list_dir_finished.emit(False, path, [])
            return

        # 2. 生成 MicroPython 代码
        code = FileManager.generate_list_dir_code(path)

        logger.debug(f"[文件浏览器] 准备列出目录: {path}")

        try:
            with self.device_manager.lock:
                # 清空缓冲区
                try:
                    self.device_manager.serial.reset_input_buffer()
                    logger.debug("[文件浏览器] 已清空输入缓冲区")
                except:
                    pass

                # 3. 发送代码
                self.device_manager.serial.write(code.encode('utf-8'))
                self.device_manager.serial.write(b'\x04')  # Ctrl+D 执行

                logger.debug(f"[文件浏览器] 已发送列出目录命令")

                # 4. 读取确认
                response = self.device_manager.read_until(b'OK', timeout=2)
                if b'OK' not in response:
                    logger.warning(f"[文件浏览器] 未收到确认: {path}")
                    self.file_access_busy.emit("list directory", path)
                    self.list_dir_finished.emit(False, path, [])
                    return

                # 5. 读取输出
                output_bytes = self.device_manager.read_until(b'\x04\x04', timeout=5)
                output = output_bytes.decode('utf-8', errors='replace')

                logger.debug(f"[文件浏览器] 接收到输出: {output}")

                # 6. 解析结果
                success, items = FileManager.parse_list_dir_result(output)

                if success:
                    logger.info(f"[文件浏览器] 成功列出目录: {path}, {len(items)} 项")
                else:
                    logger.error(f"[文件浏览器] 解析失败: {path}")

                self.list_dir_finished.emit(success, path, items)

        except Exception as e:
            logger.exception(f"[文件浏览器] 异常: {path}")
            self.progress.emit(f"[File Browser] Failed to list directory: {e}")
            self.list_dir_finished.emit(False, path, [])

    @Slot(str)
    def do_read_file(self, path: str):
        """读取文件内容（在 Worker 线程执行）"""

        logger = setup_logger(__name__)

        # 1. 检查连接
        if not self.device_manager.is_connected():
            logger.warning("[文件读取] 设备未连接")
            self.progress.emit("[File] Device not connected, trying to reconnect...")
            self.read_file_finished.emit(False, path, "")
            return

        # 2. 生成 MicroPython 代码
        code = FileManager.generate_read_file_code(path)

        logger.debug(f"[文件读取] 准备读取文件: {path}")

        try:
            with self.device_manager.lock:
                # 清空缓冲区
                try:
                    self.device_manager.serial.reset_input_buffer()
                    logger.debug("[文件读取] 已清空输入缓冲区")
                except Exception as e:
                    logger.error(f"[文件读取] 清空缓冲区失败: {e}")

                # 3. 发送代码
                self.device_manager.serial.write(code.encode('utf-8'))
                self.device_manager.serial.write(b'\x04')  # Ctrl+D 执行

                logger.debug(f"[文件读取] 已发送读取命令")

                # 4. 读取确认（设置较短超时检测设备忙碌）
                try:
                    response = self.device_manager.read_until(b'OK', timeout=2)

                    if b'OK' not in response:
                        logger.warning(f"[文件读取] 设备无响应或忙碌，响应: {response[:50]}")
                        self.file_access_busy.emit("read file", path)
                        self.read_file_finished.emit(False, path, "")
                        return

                except Exception as e:
                    logger.error(f"[文件读取] 读取确认超时: {e}")
                    self.file_access_busy.emit("read file", path)
                    self.read_file_finished.emit(False, path, "")
                    return

                # 5. 读取输出
                output_bytes = self.device_manager.read_until(b'\x04\x04', timeout=5)
                output = output_bytes.decode('utf-8', errors='replace')

                logger.debug(f"[文件读取] 接收到 {len(output)} 字符")

                # 6. 解析结果
                success, content = FileManager.parse_read_file_result(output)

                if success:
                    # content 是 bytes 类型，需要解码为 str
                    content_str = content.decode('utf-8', errors='replace')
                    logger.info(f"[文件读取] 成功: {path}, {len(content_str)} 字符")
                    self.progress.emit(f"[File] Successfully opened: {path}")
                    self.read_file_finished.emit(success, path, content_str)
                else:
                    # content 是错误消息，也是 bytes，需要解码
                    error_msg = content.decode('utf-8', errors='replace')
                    logger.error(f"[文件读取] 解析失败: {path}, 错误: {error_msg}")
                    self.progress.emit(f"[File] Failed to open: {path}")
                    self.read_file_finished.emit(success, path, error_msg)

        except Exception as e:
            logger.exception(f"[文件读取] 异常: {path}")
            self.progress.emit(f"[File] Failed to read: {e}")
            self.read_file_finished.emit(False, path, "")

    @Slot(str, str)
    def do_write_file(self, path: str, content: str):
        """写入文件内容（在 Worker 线程执行）"""

        logger = setup_logger(__name__)

        # 1. 检查连接
        if not self.device_manager.is_connected():
            logger.warning("[文件写入] 设备未连接")
            self.progress.emit("[File] Device not connected")
            self.write_file_finished.emit(False, path)
            return

        # 2. 生成 MicroPython 代码
        code = FileManager.generate_write_file_code(path, content)

        logger.debug(f"[文件写入] 准备写入文件: {path}, {len(content)} 字符")

        try:
            with self.device_manager.lock:
                # 清空缓冲区
                try:
                    self.device_manager.serial.reset_input_buffer()
                    logger.debug("[文件写入] 已清空输入缓冲区")
                except Exception as e:
                    logger.error(f"[文件写入] 清空缓冲区失败: {e}")

                # 3. 发送代码
                self.device_manager.serial.write(code.encode('utf-8'))
                self.device_manager.serial.write(b'\x04')  # Ctrl+D 执行

                logger.debug(f"[文件写入] 已发送写入命令")

                # 4. 读取确认（设置较短超时检测设备忙碌）
                try:
                    response = self.device_manager.read_until(b'OK', timeout=2)

                    if b'OK' not in response:
                        logger.warning(f"[文件写入] 设备无响应或忙碌")
                        self.file_access_busy.emit("write file", path)
                        self.write_file_finished.emit(False, path)
                        return

                except Exception as e:
                    logger.error(f"[文件写入] 读取确认超时: {e}")
                    self.file_access_busy.emit("write file", path)
                    self.write_file_finished.emit(False, path)
                    return

                # 5. 读取输出
                output_bytes = self.device_manager.read_until(b'\x04\x04', timeout=5)
                output = output_bytes.decode('utf-8', errors='replace')

                logger.debug(f"[文件写入] 接收到响应: {len(output)} 字符")

                # 6. 解析结果
                success = FileManager.parse_write_file_result(output)

                if success:
                    logger.info(f"[文件写入] 成功: {path}")
                    self.progress.emit(f"[File] Successfully saved: {path}")
                else:
                    logger.error(f"[文件写入] 失败: {path}")
                    self.progress.emit(f"[File] Failed to save: {path}")

                self.write_file_finished.emit(success, path)

        except Exception as e:
            logger.exception(f"[文件写入] 异常: {path}")
            self.progress.emit(f"[File] Failed to write: {e}")
            self.write_file_finished.emit(False, path)

    @Slot(str)
    def do_delete_path(self, path: str):
        """删除指定路径（文件或目录）"""

        logger = setup_logger(__name__)

        if not self.device_manager.is_connected():
            logger.warning("[文件删除] 设备未连接")
            self.progress.emit("[File] Device not connected")
            self.delete_path_finished.emit(False, path)
            return

        code = FileManager.generate_delete_path_code(path)
        logger.debug(f"[文件删除] 准备删除: {path}")

        try:
            with self.device_manager.lock:
                try:
                    self.device_manager.serial.reset_input_buffer()
                    logger.debug("[文件删除] 已清空输入缓冲区")
                except Exception as e:
                    logger.error(f"[文件删除] 清空缓冲区失败: {e}")

                self.device_manager.serial.write(code.encode('utf-8'))
                self.device_manager.serial.write(b'\x04')

                try:
                    response = self.device_manager.read_until(b'OK', timeout=2)
                    if b'OK' not in response:
                        logger.warning("[文件删除] 设备无响应或忙碌")
                        self.file_access_busy.emit("delete path", path)
                        self.delete_path_finished.emit(False, path)
                        return
                except Exception as e:
                    logger.error(f"[文件删除] 读取确认超时: {e}")
                    self.file_access_busy.emit("delete path", path)
                    self.delete_path_finished.emit(False, path)
                    return

                output_bytes = self.device_manager.read_until(b'\x04\x04', timeout=5)
                output = output_bytes.decode('utf-8', errors='replace')

                success = FileManager.parse_delete_path_result(output)

                if success:
                    logger.info(f"[文件删除] 成功: {path}")
                    self.progress.emit(f"[File] Deleted: {path}")
                else:
                    logger.error(f"[文件删除] 失败: {path}")
                    self.progress.emit(f"[File] Delete failed: {path}")

                self.delete_path_finished.emit(success, path)

        except Exception as e:
            logger.exception(f"[文件删除] 异常: {path}")
            self.progress.emit(f"[File] Failed to delete: {e}")
            self.delete_path_finished.emit(False, path)

    @Slot(str)
    def set_port(self, port: str):
        """设置串口并重新连接（如果需要）"""
        if not self.device_manager:
            return
        if self.device_manager.port == port:
            return
        self.device_manager.port = port
        self.device_manager.disconnect()
        self.port_changed.emit(port)

    @Slot(bool)
    def set_plot_mode(self, enabled: bool):
        """
        启用/禁用绘图模式

        Args:
            enabled: True 启用绘图模式，False 禁用
        """
        self.plot_mode_enabled = enabled
        if self.plot_handler:
            # 清空缓冲区，避免残留数据
            self.plot_handler.buffer.clear()
            if enabled:
                self.plot_handler.reset_config_state()

    def _monitor_serial_output(self):
        """
        后台监控串口输出（定时器回调）

        在代码运行时定期读取串口数据，并根据是否启用绘图模式进行分流：
        - 绘图模式：通过 PlotStreamHandler 解析数据包
        - 普通模式：直接解码为文本输出
        """
        if not self.device_manager or not self.device_manager.is_connected():
            return

        try:
            with self.device_manager.lock:
                # 检查是否有数据可读
                if self.device_manager.serial.in_waiting > 0:
                    # 读取所有可用数据
                    raw_data = self.device_manager.serial.read(
                        self.device_manager.serial.in_waiting
                    )

                    # 始终通过 PlotStreamHandler 解析，以滤除绘图协议数据
                    self.plot_handler.process_data(raw_data)

        except Exception as e:
            logger = setup_logger(__name__)
            logger.exception("后台监控串口输出异常")
