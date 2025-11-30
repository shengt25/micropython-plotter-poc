from PySide6.QtCore import QObject, Signal, Slot
from .device_manager import DeviceManager
from .code_runner import CodeRunner


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

    # Signals - 进度信息
    progress = Signal(str)              # 进度消息（显示在输出控制台）
    status_changed = Signal(str)        # 状态变化（显示在状态栏）

    # Signals - 输出信息（从 CodeRunner 转发）
    output_received = Signal(str)
    error_received = Signal(str)

    # Signals - 端口变化
    port_changed = Signal(str)

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate

        # 这些对象会在 Worker 线程中创建和使用
        self.device_manager = None
        self.code_runner = None

    @Slot()
    def initialize(self):
        """
        在 Worker 线程中初始化设备管理器
        必须在 moveToThread 之后调用
        """
        self.device_manager = DeviceManager(self.port, self.baudrate)
        self.code_runner = CodeRunner(self.device_manager)

        # 连接 CodeRunner 的 Signals 并转发到 UI
        self.code_runner.output_received.connect(self.output_received.emit)
        self.code_runner.error_received.connect(self.error_received.emit)

        # 发出初始化完成信号
        self.initialized.emit()

    @Slot()
    def do_connect(self):
        """连接设备"""
        self.progress.emit("[系统] 正在连接设备...")
        self.status_changed.emit("正在连接...")

        success = self.device_manager.connect()

        if success:
            self.progress.emit("[系统] 设备连接成功")
            self.status_changed.emit("就绪")
        else:
            self.progress.emit("[系统] 设备连接失败")
            self.status_changed.emit("连接失败")

        self.connect_finished.emit(success)

    @Slot()
    def do_disconnect(self):
        """断开设备"""
        self.progress.emit("[系统] 正在断开设备连接...")
        self.device_manager.disconnect()
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
            self.progress.emit("[系统] 正在连接设备...")
            self.status_changed.emit("正在连接...")
            if not self.device_manager.connect():
                self.progress.emit("[系统] 设备连接失败")
                self.status_changed.emit("连接失败")
                self.run_finished.emit(False)
                return
            self.progress.emit("[系统] 设备连接成功")

        # 2. 清理设备状态
        self.progress.emit("[系统] 清理设备状态...")
        if not self.code_runner.stop():
            self.progress.emit("[错误] 设备无响应，请手动重启设备（按 RESET 按钮或拔插 USB）")
            self.status_changed.emit("设备无响应 - 需要手动重启")
            self.run_finished.emit(False)
            return

        # 3. 执行代码
        self.progress.emit("\n[运行] 执行代码...")
        self.progress.emit("-" * 50)
        self.status_changed.emit("正在执行...")

        success = self.code_runner.run_code(code)

        if success:
            self.status_changed.emit("代码执行成功")
        else:
            self.status_changed.emit("代码执行失败")

        self.run_finished.emit(success)

    @Slot()
    def do_stop(self):
        """
        停止代码

        步骤：
        1. 检查连接
        2. 发送停止信号
        """
        # 1. 确保连接
        if not self.device_manager.is_connected():
            self.progress.emit("[系统] 正在连接设备...")
            self.status_changed.emit("正在连接...")
            if not self.device_manager.connect():
                self.progress.emit("[系统] 设备连接失败")
                self.status_changed.emit("连接失败")
                self.stop_finished.emit(False)
                return

        # 2. 发送停止信号
        self.progress.emit("[停止] 正在停止代码...")
        self.status_changed.emit("正在停止...")

        success = self.code_runner.stop()

        if success:
            self.status_changed.emit("停止成功")
        else:
            self.status_changed.emit("停止失败")

        self.stop_finished.emit(success)

    @Slot(str)
    def do_list_dir(self, path: str):
        """列出目录内容（在 Worker 线程执行）"""
        from .file_manager import FileManager
        from utils.logger import setup_logger

        logger = setup_logger(__name__)

        # 1. 检查连接
        if not self.device_manager.is_connected():
            logger.warning("[文件浏览器] 设备未连接")
            self.progress.emit("[文件浏览器] 设备未连接")
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
            self.progress.emit(f"[文件浏览器] 列出目录失败: {e}")
            self.list_dir_finished.emit(False, path, [])

    @Slot(str)
    def do_read_file(self, path: str):
        """读取文件内容（在 Worker 线程执行）"""
        from .file_manager import FileManager
        from utils.logger import setup_logger

        logger = setup_logger(__name__)

        # 1. 检查连接
        if not self.device_manager.is_connected():
            logger.warning("[文件读取] 设备未连接")
            self.progress.emit("[文件] 设备未连接，正在尝试重新连接...")
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

                        # 友好提示用户
                        self.progress.emit("[文件] 设备忙碌或无响应")
                        self.progress.emit("[提示] 如果设备正在执行代码，请点击 Stop 按钮停止")

                        self.read_file_finished.emit(False, path, "")
                        return

                except Exception as e:
                    logger.error(f"[文件读取] 读取确认超时: {e}")

                    # 友好提示用户
                    self.progress.emit("[文件] 设备响应超时")
                    self.progress.emit("[提示] 请点击 Stop 按钮停止当前操作，或检查设备连接")

                    self.read_file_finished.emit(False, path, "")
                    return

                # 5. 读取输出
                output_bytes = self.device_manager.read_until(b'\x04\x04', timeout=5)
                output = output_bytes.decode('utf-8', errors='replace')

                logger.debug(f"[文件读取] 接收到 {len(output)} 字符")

                # 6. 解析结果
                success, content = FileManager.parse_read_file_result(output)

                if success:
                    logger.info(f"[文件读取] 成功: {path}, {len(content)} 字符")
                    self.progress.emit(f"[文件] 成功打开: {path}")
                else:
                    logger.error(f"[文件读取] 解析失败: {path}")
                    self.progress.emit(f"[文件] 打开失败: {path}")

                self.read_file_finished.emit(success, path, content)

        except Exception as e:
            logger.exception(f"[文件读取] 异常: {path}")
            self.progress.emit(f"[文件] 读取失败: {e}")
            self.read_file_finished.emit(False, path, "")

    @Slot(str, str)
    def do_write_file(self, path: str, content: str):
        """写入文件内容（在 Worker 线程执行）"""
        from .file_manager import FileManager
        from utils.logger import setup_logger

        logger = setup_logger(__name__)

        # 1. 检查连接
        if not self.device_manager.is_connected():
            logger.warning("[文件写入] 设备未连接")
            self.progress.emit("[文件] 设备未连接")
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

                        # 友好提示用户
                        self.progress.emit("[文件] 设备忙碌或无响应")
                        self.progress.emit("[提示] 如果设备正在执行代码，请点击 Stop 按钮停止")

                        self.write_file_finished.emit(False, path)
                        return

                except Exception as e:
                    logger.error(f"[文件写入] 读取确认超时: {e}")

                    # 友好提示用户
                    self.progress.emit("[文件] 设备响应超时")
                    self.progress.emit("[提示] 请点击 Stop 按钮停止当前操作，或检查设备连接")

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
                    self.progress.emit(f"[文件] 成功保存: {path}")
                else:
                    logger.error(f"[文件写入] 失败: {path}")
                    self.progress.emit(f"[文件] 保存失败: {path}")

                self.write_file_finished.emit(success, path)

        except Exception as e:
            logger.exception(f"[文件写入] 异常: {path}")
            self.progress.emit(f"[文件] 写入失败: {e}")
            self.write_file_finished.emit(False, path)

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
