import time
from typing import Optional
from PySide6.QtCore import QObject, Signal
from .device_manager import DeviceManager
from utils.logger import setup_logger
from serial import SerialException

class CodeRunner(QObject):
    """
    Responsible for executing code on MicroPython devices
    """

    # Qt Signals
    error_received = Signal(str)   # Error message

    def __init__(self, device_manager: DeviceManager):
        super().__init__()
        self.dm = device_manager

    def run_file(self, filepath: str) -> bool:
        """
        Run a file on the device (assuming connected and in Raw REPL)

        Args:
            filepath: File path on the device, e.g., 'main.py' or '/lib/sensor.py'

        Returns:
            Whether execution was successful
        """
        try:
            # Construct execution code
            code = f"exec(open('{filepath}').read())"

            # Send code
            self.dm.serial.write(code.encode('utf-8'))
            self.dm.serial.write(b'\x04')  # Execute with Ctrl+D

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
        Execute code string directly, read full output to avoid buffer pollution

        Args:
            code: Python code

        Returns:
            Whether execution was successful
        """

        logger = setup_logger(__name__)

        try:
            # Send code
            self.dm.serial.write(code.encode('utf-8'))
            self.dm.serial.write(b'\x04')  # Execute with Ctrl+D

            logger.debug("[Code Run] Code and Ctrl+D sent")

            # Read confirmation
            response = self.dm.read_until(b'OK', timeout=2)
            if b'OK' not in response:
                self.error_received.emit("Device no response")
                return False

            logger.debug("[Code Run] OK confirmation received")
            return True

        except Exception as e:
            logger.exception(f"[Code Run] Execution exception")
            self.error_received.emit(f"Exception when running: {e}")
            return False

    def stop(self) -> Optional[bool]:
        """
        Stop code execution and soft reboot REPL

        Returns:
            True if stopped successfully, False if failed
            None if serial exception occurred (reconnection needed)
        """

        logger = setup_logger(__name__)

        logger.info("[Stop Code] Starting stop operation")

        # Check if serial port exists and is open
        if not self.dm.serial or not self.dm.serial.is_open:
            logger.warning("[Stop Code] Serial port not open")
            return None

        try:
            with self.dm.lock:
                # 1. Alternately send Ctrl+C and Ctrl+D to enhance interruption capability
                # Ctrl+C interrupts running program
                # Ctrl+D executes and triggers soft reset
                for i in range(3):
                    # Send Ctrl+C
                    self.dm.serial.write(b'\x03')
                    logger.debug(f"[Stop Code] sending Ctrl+C (Attempt {i+1}/5)")
                    time.sleep(0.05)

                    # Send Ctrl+D
                    self.dm.serial.write(b'\x04')
                    logger.debug(f"[Stop Code] sending Ctrl+D (Attempt {i+1}/5)")
                    time.sleep(0.05)

                # 2. Clear buffer
                try:
                    self.dm.serial.reset_input_buffer()
                    logger.debug("[Stop Code] Input buffer cleared")
                except:
                    pass

                # 3. Send Ctrl+D one last time to ensure soft reset
                self.dm.serial.write(b'\x04')
                logger.debug("[Stop Code] Sending final Ctrl+D (soft reset)")
                time.sleep(0.5)  # Wait for device reboot

                # 4. Re-enter Raw REPL (explicitly send Ctrl+A)
                self.dm.serial.write(b'\x01')
                response = self.dm.read_until(b'raw REPL; CTRL-B to exit\r\n', timeout=2)
                if b'raw REPL' not in response:
                    logger.warning(f"[Stop Code] Failed to enter Raw REPL: {response}")
                    # Try again: exit Raw then re-enter to avoid residual state
                    self.dm.serial.write(b'\x02')
                    time.sleep(0.1)
                    self.dm.serial.write(b'\x01')
                    response = self.dm.read_until(b'raw REPL; CTRL-B to exit\r\n', timeout=2)
                    if b'raw REPL' not in response:
                        return False

                self.dm.read_until(b'>', timeout=1)

                logger.info("[Stop Code] Soft reset successful, REPL ready")
                return True

        except SerialException as e:
            logger.error(f"[Stop Code] Serial exception: {e}")
            # Return None to indicate reconnection needed
            return None

        except Exception as e:
            logger.exception("[Stop Code] Exception")
            self.error_received.emit(f"[System] Exception when stopping: {e}")
            return False
