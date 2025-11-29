import time
from typing import Optional, Callable
from PySide6.QtCore import QObject, Signal
from .device_manager import DeviceManager


class CodeRunner(QObject):
    """
    负责在 MicroPython 设备上执行代码
    """

    # Qt Signals
    output_received = Signal(str)  # 输出消息
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

            # 读取执行确认（Raw REPL 会返回 'OK'）
            response = self.dm.serial.read_until(b'OK')

            if b'OK' not in response:
                error_msg = response.decode('utf-8', errors='replace')
                self.error_received.emit(f"执行失败: {error_msg}")
                return False

            self.output_received.emit(f"[CodeRunner] 正在运行: {filepath}")
            return True

        except Exception as e:
            self.error_received.emit(f"运行异常: {e}")
            return False

    def run_code(self, code: str) -> bool:
        """
        直接执行代码字符串（假设已连接且处于 Raw REPL）

        Args:
            code: Python 代码

        Returns:
            是否成功执行
        """
        try:
            # 发送代码
            self.dm.serial.write(code.encode('utf-8'))
            self.dm.serial.write(b'\x04')  # Ctrl+D 执行

            # 读取确认
            response = self.dm.serial.read_until(b'OK')

            if b'OK' not in response:
                error_msg = response.decode('utf-8', errors='replace')
                self.error_received.emit(f"执行失败: {error_msg}")
                return False

            self.output_received.emit(f"[CodeRunner] 代码已执行")
            return True

        except Exception as e:
            self.error_received.emit(f"执行异常: {e}")
            return False

    def stop(self) -> bool:
        """
        停止当前运行的程序（发送 Ctrl+C 并重新进入 Raw REPL）

        Returns:
            是否成功停止
        """
        success = self.dm.force_stop()

        if success:
            self.output_received.emit("[CodeRunner] 程序已停止")
        else:
            self.error_received.emit("[CodeRunner] 停止失败")

        return success

    # def soft_reset(self) -> bool:
    #     """
    #     软重启设备（Ctrl+D）- 暂时禁用
    #     会停止程序并重新加载 boot.py 和 main.py
    #
    #     Returns:
    #         是否成功重启
    #     """
    #     # DeviceManager 中的 soft_reset() 已被移除
    #     pass

    def interrupt(self) -> bool:
        """
        发送 Ctrl+C 中断信号（但不改变状态）
        用于需要中断但不想完全停止的场景

        Returns:
            是否成功发送
        """
        try:
            self.dm.serial.write(b'\x03')
            self.output_received.emit("[CodeRunner] 已发送中断信号")
            return True

        except Exception as e:
            self.error_received.emit(f"发送中断失败: {e}")
            return False
