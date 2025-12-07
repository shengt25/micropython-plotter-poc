import serial
import threading
import time
from typing import Optional
from PySide6.QtCore import QObject
from utils.logger import setup_logger


class DeviceManager(QObject):
    """
    Manage MicroPython device connection
    Provide shared Serial instance for other modules
    """

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial: Optional[serial.Serial] = None
        self.lock = threading.Lock()
        self._default_read_timeout = 1.0

    def connect(self) -> bool:
        """Connect to device and enter Raw REPL"""
        with self.lock:
            # If already connected, disconnect first
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

                # Enter Raw REPL
                if self._enter_raw_mode():
                    return True
                else:
                    self.serial.close()
                    self.serial = None
                    return False

            except Exception as e:
                print(f"Connection failed: {e}")
                self.serial = None
                return False

    def disconnect(self):
        """Disconnect"""
        with self.lock:
            if self.serial and self.serial.is_open:
                try:
                    # Try to exit Raw REPL gracefully
                    self.serial.write(b'\x02')  # Ctrl+B Exit Raw REPL
                except Exception:
                    # Serial port might be broken, ignore
                    pass
                finally:
                    self.serial.close()

            self.serial = None

    def _enter_raw_mode(self) -> bool:
        """Enter Raw REPL mode (with retry)"""
        # Try multiple times to enter Raw REPL (refer to Thonny's approach)
        for attempt in range(3):
            try:
                # 1. Send Ctrl+C multiple times, try to stop any running program
                for _ in range(3):
                    self.serial.write(b'\x03')
                    time.sleep(0.05)

                # 2. Clear buffer
                self.serial.reset_input_buffer()
                time.sleep(0.1)

                # 3. Enter Raw REPL
                self.serial.write(b'\x01')

                # 4. Wait for confirmation (timeout 2s)
                response = self.serial.read_until(b'raw REPL; CTRL-B to exit\r\n')

                if b'raw REPL' in response:
                    # Read prompt '>'
                    self.serial.read_until(b'>')
                    if attempt > 0:
                        print(f"[DeviceManager] Successfully entered Raw REPL on attempt {attempt + 1}")
                    return True
                else:
                    print(f"[DeviceManager] Failed to enter Raw REPL (Attempt {attempt + 1}/3), received: {response}")

            except Exception as e:
                print(f"[DeviceManager] Exception entering Raw REPL (Attempt {attempt + 1}/3): {e}")

            # If not the last attempt, wait and retry
            if attempt < 2:
                time.sleep(0.5)

        # All attempts failed
        print("[DeviceManager] Unable to enter Raw REPL, device may be unresponsive, please restart manually")
        return False

    def force_stop(self) -> bool:
        """
        Send Ctrl+C and re-enter Raw REPL
        Used to stop current running program or cleanup device state

        Returns:
            Success or not
        """
        with self.lock:
            if not self.serial or not self.serial.is_open:
                return False

            try:
                # Send Ctrl+C to stop program
                self.serial.write(b'\x03\x03')
                time.sleep(0.1)

                # Clear buffer
                self.serial.read_all()

                # Re-enter Raw REPL
                return self._enter_raw_mode()

            except Exception as e:
                print(f"Force stop failed: {e}")
                return False

    def is_connected(self) -> bool:
        """Check if connected (simple check, does not guarantee availability)"""
        with self.lock:
            return self.serial is not None and self.serial.is_open

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()

    def read_until(self, expected: bytes, timeout: Optional[float] = None) -> bytes:
        """Read until specific terminator or timeout"""
        if not self.serial:
            return b""

        deadline = time.time() + (timeout or self._default_read_timeout)
        buffer = bytearray()
        terminator = expected

        while time.time() < deadline:
            chunk = self.serial.read(1)
            if chunk:
                buffer += chunk
                if buffer.endswith(terminator):
                    break
            else:
                time.sleep(0.01)

        return bytes(buffer)
