import time
from typing import Optional
from PySide6.QtCore import QObject, Signal
from .device_manager import DeviceManager
from utils.logger import setup_logger
from serial import SerialException

class CodeRunner(QObject):
    """
    负责在 MicroPython 设备上执行代码
    """

    # Qt Signals
    error_received = Signal(str)   # 错误消息

    def __init__(self, device_manager: DeviceManager):
        super().__init__()
        self.dm = device_manager

    def run_file(self, filepath: str) -> bool:
        """
        运行设备上的文件（假设已连接且处于 Raw REPL）

        Args:
            filepath: 设备上的文件路径，如 'main.py' 或 '/lib/sensor.py'

        Returns:
            是否成功执行
        """
        try:
            # 构造执行代码
            code = f"exec(open('{filepath}').read())"

            # 发送代码
            self.dm.serial.write(code.encode('utf-8'))
            self.dm.serial.write(b'\x04')  # Ctrl+D 执行

            response = self.dm.read_until(b'OK', timeout=2)

            if b'OK' not in response:
                error_msg = response.decode('utf-8', errors='replace')
                self.error_received.emit(f"Execution failed: {error_msg}")
                return False

            return True

        except Exception as e:
            self.error_received.emit(f"Exception when running: {e}")
            return False

    def run_code(self, code: str) -> bool:
        """
        直接执行代码字符串，读取完整输出避免缓冲区污染

        Args:
            code: Python 代码

        Returns:
            是否成功执行
        """

        logger = setup_logger(__name__)

        try:
            # 发送代码
            self.dm.serial.write(code.encode('utf-8'))
            self.dm.serial.write(b'\x04')  # Ctrl+D 执行

            logger.debug("[代码运行] 已发送代码和 Ctrl+D")

            # 读取确认
            response = self.dm.read_until(b'OK', timeout=2)
            if b'OK' not in response:
                self.error_received.emit("Device no response")
                return False

            logger.debug("[代码运行] 收到 OK 确认")
            return True

        except Exception as e:
            logger.exception(f"[代码运行] 执行异常")
            self.error_received.emit(f"Exception when running: {e}")
            return False

    def stop(self) -> Optional[bool]:
        """
        停止代码执行并软重启 REPL

        Returns:
            True 如果停止成功，False 如果失败
            None 如果遇到串口异常（需要重新连接）
        """

        logger = setup_logger(__name__)

        logger.info("[停止代码] 开始执行停止操作")

        # 检查串口是否存在且打开
        if not self.dm.serial or not self.dm.serial.is_open:
            logger.warning("[停止代码] 串口未打开")
            return None

        try:
            with self.dm.lock:
                # 1. 交替发送 Ctrl+C 和 Ctrl+D，增强中断能力
                # Ctrl+C 用于中断运行的程序
                # Ctrl+D 用于执行并触发 soft reset
                for i in range(3):
                    # 发送 Ctrl+C
                    self.dm.serial.write(b'\x03')
                    logger.debug(f"[停止代码] 发送 Ctrl+C (尝试 {i+1}/5)")
                    time.sleep(0.05)

                    # 发送 Ctrl+D
                    self.dm.serial.write(b'\x04')
                    logger.debug(f"[停止代码] 发送 Ctrl+D (尝试 {i+1}/5)")
                    time.sleep(0.05)

                # 2. 清空缓冲区
                try:
                    self.dm.serial.reset_input_buffer()
                    logger.debug("[停止代码] 已清空输入缓冲区")
                except:
                    pass

                # 3. 最后再发送一次 Ctrl+D 确保进入 soft reset
                self.dm.serial.write(b'\x04')
                logger.debug("[停止代码] 最后发送 Ctrl+D (soft reset)")
                time.sleep(0.5)  # 等待设备重启

                # 4. 重新进入 Raw REPL（显式发送 Ctrl+A）
                self.dm.serial.write(b'\x01')
                response = self.dm.read_until(b'raw REPL; CTRL-B to exit\r\n', timeout=2)
                if b'raw REPL' not in response:
                    logger.warning(f"[停止代码] 未进入 Raw REPL: {response}")
                    # 再尝试一次：先退出 Raw 再进入，避免残留状态
                    self.dm.serial.write(b'\x02')
                    time.sleep(0.1)
                    self.dm.serial.write(b'\x01')
                    response = self.dm.read_until(b'raw REPL; CTRL-B to exit\r\n', timeout=2)
                    if b'raw REPL' not in response:
                        return False

                self.dm.read_until(b'>', timeout=1)

                logger.info("[停止代码] 软重启成功，REPL 就绪")
                return True

        except SerialException as e:
            logger.error(f"[停止代码] 串口异常: {e}")
            # 返回 None 表示需要重新连接
            return None

        except Exception as e:
            logger.exception("[停止代码] 异常")
            self.error_received.emit(f"[System] Exception when stopping: {e}")
            return False
