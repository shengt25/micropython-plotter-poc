import serial
import threading
import time
from typing import Optional
from PySide6.QtCore import QObject


class DeviceManager(QObject):
    """
    管理 MicroPython 设备的连接
    提供共享的 Serial 实例给其他模块使用
    """

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial: Optional[serial.Serial] = None
        self.lock = threading.Lock()

    def connect(self) -> bool:
        """连接设备并进入 Raw REPL 模式"""
        with self.lock:
            # 如果已连接，先断开
            if self.serial and self.serial.is_open:
                try:
                    self.serial.close()
                except Exception:
                    pass
                self.serial = None

            try:
                self.serial = serial.Serial(
                    self.port,
                    self.baudrate,
                    timeout=1,
                    write_timeout=1
                )

                # 进入 Raw REPL
                if self._enter_raw_mode():
                    return True
                else:
                    self.serial.close()
                    self.serial = None
                    return False

            except Exception as e:
                print(f"连接失败: {e}")
                self.serial = None
                return False

    def disconnect(self):
        """断开连接"""
        with self.lock:
            if self.serial and self.serial.is_open:
                try:
                    # 尝试优雅退出 Raw REPL
                    self.serial.write(b'\x02')  # Ctrl+B 退出 Raw REPL
                except Exception:
                    # 串口可能已经出错了，忽略
                    pass
                finally:
                    self.serial.close()

            self.serial = None

    def _enter_raw_mode(self) -> bool:
        """进入 Raw REPL 模式（带重试）"""
        # 尝试多次进入 Raw REPL（参考 Thonny 的做法）
        for attempt in range(3):
            try:
                # 1. 发送 Ctrl+C 多次，尝试停止任何运行的程序
                for _ in range(3):
                    self.serial.write(b'\x03')
                    time.sleep(0.05)

                # 2. 清空缓冲区
                self.serial.reset_input_buffer()
                time.sleep(0.1)

                # 3. 进入 Raw REPL
                self.serial.write(b'\x01')

                # 4. 等待确认消息（超时 2 秒）
                response = self.serial.read_until(b'raw REPL; CTRL-B to exit\r\n')

                if b'raw REPL' in response:
                    # 读取提示符 '>'
                    self.serial.read_until(b'>')
                    if attempt > 0:
                        print(f"[DeviceManager] 第 {attempt + 1} 次尝试成功进入 Raw REPL")
                    return True
                else:
                    print(f"[DeviceManager] 进入 Raw REPL 失败（尝试 {attempt + 1}/3），收到: {response}")

            except Exception as e:
                print(f"[DeviceManager] 进入 Raw REPL 异常（尝试 {attempt + 1}/3）: {e}")

            # 如果不是最后一次尝试，等待后重试
            if attempt < 2:
                time.sleep(0.5)

        # 所有尝试都失败
        print("[DeviceManager] 无法进入 Raw REPL，设备可能无响应，请手动重启设备")
        return False

    def force_stop(self) -> bool:
        """
        发送 Ctrl+C 并重新进入 Raw REPL
        用于停止当前运行的程序或清理设备状态

        Returns:
            是否成功
        """
        with self.lock:
            if not self.serial or not self.serial.is_open:
                return False

            try:
                # 发送 Ctrl+C 停止程序
                self.serial.write(b'\x03\x03')
                time.sleep(0.1)

                # 清空缓冲区
                self.serial.read_all()

                # 重新进入 Raw REPL
                return self._enter_raw_mode()

            except Exception as e:
                print(f"停止失败: {e}")
                return False

    def is_connected(self) -> bool:
        """检查是否已连接（简单检查，不保证可用）"""
        with self.lock:
            return self.serial is not None and self.serial.is_open

    def __enter__(self):
        """支持 with 语句"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句"""
        self.disconnect()