from PySide6.QtCore import QObject, Signal, Slot, QTimer
from .device_manager import DeviceManager
from .code_runner import CodeRunner
from .plot_stream_handler import PlotStreamHandler
from utils.logger import setup_logger
from .file_manager import FileManager


class DeviceWorker(QObject):
    """
    Worker for performing device operations in a background thread
    Avoids blocking the UI thread
    """

    # Signals - Request signals (UI -> Worker)
    connect_requested = Signal()        # Request to connect
    run_code_requested = Signal(str)    # Request to run code
    stop_requested = Signal()           # Request to stop code
    disconnect_requested = Signal()     # Request to disconnect
    list_dir_requested = Signal(str)    # Request to list directory
    read_file_requested = Signal(str)   # Request to read file
    write_file_requested = Signal(str, str)  # Request to write file (path, content)
    delete_path_requested = Signal(str)  # Request to delete file or directory
    set_port_requested = Signal(str)        # Request to change port

    # Signals - Completion signals
    initialized = Signal()              # Worker initialization complete
    connect_finished = Signal(bool)     # Connect finished (success/fail)
    disconnect_finished = Signal()      # Disconnect finished
    run_finished = Signal(bool)         # Run finished (success/fail)
    stop_finished = Signal(bool)        # Stop finished (success/fail)
    list_dir_finished = Signal(bool, str, list)  # List dir finished (success, path, items)
    read_file_finished = Signal(bool, str, str)  # Read file finished (success, path, content)
    write_file_finished = Signal(bool, str)      # Write file finished (success, path)
    delete_path_finished = Signal(bool, str)     # Delete path finished (success, path)
    file_access_busy = Signal(str, str)          # Device busy caused file op failure (operation, path)

    # Signals - Progress info
    progress = Signal(str)              # Progress message (displayed in output console)
    status_changed = Signal(str)        # Status changed (displayed in status bar)

    # Signals - Output info (forwarded from CodeRunner)
    output_received = Signal(str)
    error_received = Signal(str)

    # Signals - Plot data
    plot_data_received = Signal(list)  # Plot data packet
    plot_config_received = Signal(list)  # Plot channel config

    # Signals - Port change
    port_changed = Signal(str)

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate

        # These objects will be created and used in the Worker thread
        self.device_manager = None
        self.code_runner = None
        self.plot_handler = None
        self.monitor_timer = None
        self.plot_mode_enabled = False

    @Slot()
    def initialize(self):
        """
        Initialize DeviceManager in Worker thread
        Must be called after moveToThread
        """
        self.device_manager = DeviceManager(self.port, self.baudrate)
        self.code_runner = CodeRunner(self.device_manager)

        # Create plot stream handler
        self.plot_handler = PlotStreamHandler(self.device_manager)

        # Connect CodeRunner signals and forward to UI
        self.code_runner.error_received.connect(self.error_received.emit)

        # Connect PlotStreamHandler signals
        self.plot_handler.plot_data_received.connect(self.plot_data_received.emit)
        self.plot_handler.plot_config_received.connect(self.plot_config_received.emit)
        self.plot_handler.text_data_received.connect(self.output_received.emit)

        # Create background monitor timer
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._monitor_serial_output)

        # Emit initialization complete signal
        self.initialized.emit()

    @Slot()
    def do_connect(self):
        """Connect to device"""
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
        """Disconnect device (user initiated)"""
        self.progress.emit("[System] Disconnecting from device...")
        self.status_changed.emit("Disconnecting...")

        # Stop background monitor timer (if running)
        if self.monitor_timer and self.monitor_timer.isActive():
            self.monitor_timer.stop()

        # Disconnect
        self.device_manager.disconnect()

        self.progress.emit("[System] Disconnected")
        self.status_changed.emit("Disconnected")
        self.disconnect_finished.emit()

    @Slot(str)
    def do_run_code(self, code: str):
        """
        Run code

        Steps:
        1. Check connection
        2. Cleanup device status
        3. Execute code
        """
        # 1. Ensure connection
        if not self.device_manager.is_connected():
            self.progress.emit("[System] Connecting to device...")
            self.status_changed.emit("Connecting...")
            if not self.device_manager.connect():
                self.progress.emit("[System] Failed to connect to device")
                self.status_changed.emit("Failed to connect")
                self.run_finished.emit(False)
                return
            self.progress.emit("[System] Successfully connected to device")

        # 2. Cleanup device status
        self.progress.emit("[System] Cleaning up status...")
        if not self.code_runner.stop():
            self.progress.emit("[Error] Device no response, click stop/reset or hard reset on device")
            self.status_changed.emit("Device no response")
            self.run_finished.emit(False)
            return

        # 3. Execute code
        self.progress.emit("\n[Info] Running code...")
        self.progress.emit("-" * 50)
        self.status_changed.emit("Running...")
        if self.plot_handler:
            self.plot_handler.reset_config_state()

        success = self.code_runner.run_code(code)

        if success:
            # Start background monitor to read serial output
            if self.monitor_timer:
                self.monitor_timer.start(50)  # Poll every 50ms
            self.status_changed.emit("Code running successfully")
        else:
            self.status_changed.emit("Code running failed")

        self.run_finished.emit(success)

    @Slot()
    def do_stop(self):
        """
        Stop code

        Steps:
        1. Stop background monitor
        2. Send stop signal directly (no handshake to avoid timeout)
        3. If serial exception, auto reconnect
        """
        # 1. Stop background monitor
        if self.monitor_timer and self.monitor_timer.isActive():
            self.monitor_timer.stop()

        # 2. Send stop signal directly (regardless of connection status)
        # Even if serial status is unknown, try sending Ctrl+C/Ctrl+D
        # This avoids waiting for handshake timeout when device is spamming output
        self.progress.emit("[Stop] Stopping code execution...")
        self.status_changed.emit("Stopping...")

        success = self.code_runner.stop()

        # 3. If None returned, serial exception occurred, reconnect needed
        if success is None:
            self.progress.emit("[System] Device disconnected, reconnecting...")
            self.status_changed.emit("Reconnecting...")

            # Disconnect old connection
            self.device_manager.disconnect()

            # Try to reconnect
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
        """List directory content (run in Worker thread)"""

        logger = setup_logger(__name__)

        # 1. Check connection
        if not self.device_manager.is_connected():
            logger.warning("[File Browser] Device not connected")
            self.progress.emit("[File Browser] Device not connected")
            self.list_dir_finished.emit(False, path, [])
            return

        # 2. Generate MicroPython code
        code = FileManager.generate_list_dir_code(path)

        logger.debug(f"[File Browser] Preparing to list directory: {path}")

        try:
            with self.device_manager.lock:
                # Clear buffer
                try:
                    self.device_manager.serial.reset_input_buffer()
                    logger.debug("[File Browser] Input buffer cleared")
                except:
                    pass

                # 3. Send code
                self.device_manager.serial.write(code.encode('utf-8'))
                self.device_manager.serial.write(b'\x04')  # Execute with Ctrl+D

                logger.debug(f"[File Browser] List directory command sent")

                # 4. Read confirmation
                response = self.device_manager.read_until(b'OK', timeout=2)
                if b'OK' not in response:
                    logger.warning(f"[File Browser] No confirmation received: {path}")
                    self.file_access_busy.emit("list directory", path)
                    self.list_dir_finished.emit(False, path, [])
                    return

                # 5. Read output
                output_bytes = self.device_manager.read_until(b'\x04\x04', timeout=5)
                output = output_bytes.decode('utf-8', errors='replace')

                logger.debug(f"[File Browser] Output received: {output}")

                # 6. Parse result
                success, items = FileManager.parse_list_dir_result(output)

                if success:
                    logger.info(f"[File Browser] Directory listed successfully: {path}, {len(items)} items")
                else:
                    logger.error(f"[File Browser] Parse failed: {path}")

                self.list_dir_finished.emit(success, path, items)

        except Exception as e:
            logger.exception(f"[File Browser] Exception: {path}")
            self.progress.emit(f"[File Browser] Failed to list directory: {e}")
            self.list_dir_finished.emit(False, path, [])

    @Slot(str)
    def do_read_file(self, path: str):
        """Read file content (run in Worker thread)"""

        logger = setup_logger(__name__)

        # 1. Check connection
        if not self.device_manager.is_connected():
            logger.warning("[File Read] Device not connected")
            self.progress.emit("[File] Device not connected, trying to reconnect...")
            self.read_file_finished.emit(False, path, "")
            return

        # 2. Generate MicroPython code
        code = FileManager.generate_read_file_code(path)

        logger.debug(f"[File Read] Preparing to read file: {path}")

        try:
            with self.device_manager.lock:
                # Clear buffer
                try:
                    self.device_manager.serial.reset_input_buffer()
                    logger.debug("[File Read] Input buffer cleared")
                except Exception as e:
                    logger.error(f"[File Read] Failed to clear buffer: {e}")

                # 3. Send code
                self.device_manager.serial.write(code.encode('utf-8'))
                self.device_manager.serial.write(b'\x04')  # Execute with Ctrl+D

                logger.debug(f"[File Read] Read command sent")

                # 4. Read confirmation (short timeout to detect busy device)
                try:
                    response = self.device_manager.read_until(b'OK', timeout=2)

                    if b'OK' not in response:
                        logger.warning(f"[File Read] Device no response or busy, response: {response[:50]}")
                        self.file_access_busy.emit("read file", path)
                        self.read_file_finished.emit(False, path, "")
                        return

                except Exception as e:
                    logger.error(f"[File Read] Read confirmation timed out: {e}")
                    self.file_access_busy.emit("read file", path)
                    self.read_file_finished.emit(False, path, "")
                    return

                # 5. Read output
                output_bytes = self.device_manager.read_until(b'\x04\x04', timeout=5)
                output = output_bytes.decode('utf-8', errors='replace')

                logger.debug(f"[File Read] Received {len(output)} chars")

                # 6. Parse result
                success, content = FileManager.parse_read_file_result(output)

                if success:
                    # content is bytes, need to decode to str
                    content_str = content.decode('utf-8', errors='replace')
                    logger.info(f"[File Read] Success: {path}, {len(content_str)} chars")
                    self.progress.emit(f"[File] Successfully opened: {path}")
                    self.read_file_finished.emit(success, path, content_str)
                else:
                    # content is error message (bytes), needs decoding
                    error_msg = content.decode('utf-8', errors='replace')
                    logger.error(f"[File Read] Parse failed: {path}, Error: {error_msg}")
                    self.progress.emit(f"[File] Failed to open: {path}")
                    self.read_file_finished.emit(success, path, error_msg)

        except Exception as e:
            logger.exception(f"[File Read] Exception: {path}")
            self.progress.emit(f"[File] Failed to read: {e}")
            self.read_file_finished.emit(False, path, "")

    @Slot(str, str)
    def do_write_file(self, path: str, content: str):
        """Write file content (run in Worker thread)"""

        logger = setup_logger(__name__)

        # 1. Check connection
        if not self.device_manager.is_connected():
            logger.warning("[File Write] Device not connected")
            self.progress.emit("[File] Device not connected")
            self.write_file_finished.emit(False, path)
            return

        # 2. Generate MicroPython code
        code = FileManager.generate_write_file_code(path, content)

        logger.debug(f"[File Write] Preparing to write file: {path}, {len(content)} chars")

        try:
            with self.device_manager.lock:
                # Clear buffer
                try:
                    self.device_manager.serial.reset_input_buffer()
                    logger.debug("[File Write] Input buffer cleared")
                except Exception as e:
                    logger.error(f"[File Write] Failed to clear buffer: {e}")

                # 3. Send code
                self.device_manager.serial.write(code.encode('utf-8'))
                self.device_manager.serial.write(b'\x04')  # Execute with Ctrl+D

                logger.debug(f"[File Write] Write command sent")

                # 4. Read confirmation (short timeout to detect busy device)
                try:
                    response = self.device_manager.read_until(b'OK', timeout=2)

                    if b'OK' not in response:
                        logger.warning(f"[File Write] Device no response or busy")
                        self.file_access_busy.emit("write file", path)
                        self.write_file_finished.emit(False, path)
                        return

                except Exception as e:
                    logger.error(f"[File Write] Read confirmation timed out: {e}")
                    self.file_access_busy.emit("write file", path)
                    self.write_file_finished.emit(False, path)
                    return

                # 5. Read output
                output_bytes = self.device_manager.read_until(b'\x04\x04', timeout=5)
                output = output_bytes.decode('utf-8', errors='replace')

                logger.debug(f"[File Write] Response received: {len(output)} chars")

                # 6. Parse result
                success = FileManager.parse_write_file_result(output)

                if success:
                    logger.info(f"[File Write] Success: {path}")
                    self.progress.emit(f"[File] Successfully saved: {path}")
                else:
                    logger.error(f"[File Write] Failed: {path}")
                    self.progress.emit(f"[File] Failed to save: {path}")

                self.write_file_finished.emit(success, path)

        except Exception as e:
            logger.exception(f"[File Write] Exception: {path}")
            self.progress.emit(f"[File] Failed to write: {e}")
            self.write_file_finished.emit(False, path)

    @Slot(str)
    def do_delete_path(self, path: str):
        """Delete specified path (file or directory)"""

        logger = setup_logger(__name__)

        if not self.device_manager.is_connected():
            logger.warning("[File Delete] Device not connected")
            self.progress.emit("[File] Device not connected")
            self.delete_path_finished.emit(False, path)
            return

        code = FileManager.generate_delete_path_code(path)
        logger.debug(f"[File Delete] Preparing to delete: {path}")

        try:
            with self.device_manager.lock:
                try:
                    self.device_manager.serial.reset_input_buffer()
                    logger.debug("[File Delete] Input buffer cleared")
                except Exception as e:
                    logger.error(f"[File Delete] Failed to clear buffer: {e}")

                self.device_manager.serial.write(code.encode('utf-8'))
                self.device_manager.serial.write(b'\x04')

                try:
                    response = self.device_manager.read_until(b'OK', timeout=2)
                    if b'OK' not in response:
                        logger.warning("[File Delete] Device no response or busy")
                        self.file_access_busy.emit("delete path", path)
                        self.delete_path_finished.emit(False, path)
                        return
                except Exception as e:
                    logger.error(f"[File Delete] Read confirmation timed out: {e}")
                    self.file_access_busy.emit("delete path", path)
                    self.delete_path_finished.emit(False, path)
                    return

                output_bytes = self.device_manager.read_until(b'\x04\x04', timeout=5)
                output = output_bytes.decode('utf-8', errors='replace')

                success = FileManager.parse_delete_path_result(output)

                if success:
                    logger.info(f"[File Delete] Success: {path}")
                    self.progress.emit(f"[File] Deleted: {path}")
                else:
                    logger.error(f"[File Delete] Failed: {path}")
                    self.progress.emit(f"[File] Delete failed: {path}")

                self.delete_path_finished.emit(success, path)

        except Exception as e:
            logger.exception(f"[File Delete] Exception: {path}")
            self.progress.emit(f"[File] Failed to delete: {e}")
            self.delete_path_finished.emit(False, path)

    @Slot(str)
    def set_port(self, port: str):
        """Set port and reconnect (if needed)"""
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
        Enable/Disable plot mode

        Args:
            enabled: True to enable, False to disable
        """
        self.plot_mode_enabled = enabled
        if self.plot_handler:
            # Clear buffer to avoid residual data
            self.plot_handler.buffer.clear()
            if enabled:
                self.plot_handler.reset_config_state()

    def _monitor_serial_output(self):
        """
        Background monitor for serial output (timer callback)

        Periodically reads serial data during code execution,
        and routes data based on whether plot mode is enabled:
        - Plot mode: Parse packets via PlotStreamHandler
        - Normal mode: Decode directly as text output
        """
        if not self.device_manager or not self.device_manager.is_connected():
            return

        try:
            with self.device_manager.lock:
                # Check if data available
                if self.device_manager.serial.in_waiting > 0:
                    # Read all available data
                    raw_data = self.device_manager.serial.read(
                        self.device_manager.serial.in_waiting
                    )

                    # Always parse via PlotStreamHandler to filter plot protocol data
                    self.plot_handler.process_data(raw_data)

        except Exception as e:
            logger = setup_logger(__name__)
            logger.exception("Background monitor serial output exception")
