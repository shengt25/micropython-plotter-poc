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
    """MicroPython Code Window"""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("MicroPython Code Runner")
        self.resize(1000, 700)

        # Plotter window (created on demand)
        self.plotter_window = None
        self.auto_open_plot = True

        # Create UI components
        self._setup_ui()

        # Create serial port monitor
        self._setup_port_monitor()

        # Create background thread and Worker
        self._setup_worker()

        # Connect signals
        self._connect_signals()

        # Auto connect to device after Worker initialization
        # (Connect after init to avoid uninitialized Worker)

    def _setup_ui(self):
        """Setup UI layout"""
        # Create toolbar
        self.toolbar = CodeToolBar(self)
        self.addToolBar(self.toolbar)

        self.current_port = None
        self.worker_ready = False
        self._connect_when_ready = False
        self._busy_directory_paths: set[str] = set()
        self._pending_deletes: dict[str, bool] = {}  # Record type of paths to delete {path: is_dir}

        # Track Plot Lib installation status
        self._installing_plot_lib = False
        self._plot_lib_content = None  # Cache local file content

        # Create file browser
        self.file_browser = FileBrowser()

        # Create multi-tab code editor
        self.tab_editor = TabEditorWidget()

        # Create output console
        self.output_console = OutputConsole()

        # Right splitter: Code Editor + Output Console
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(self.tab_editor)
        right_splitter.addWidget(self.output_console)
        right_splitter.setStretchFactor(0, 7)
        right_splitter.setStretchFactor(1, 3)

        # Main splitter: File Browser + Right Splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(self.file_browser)
        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(0, 3)  # File browser 30%
        main_splitter.setStretchFactor(1, 7)  # Right side 70%

        # Create central widget
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.addWidget(main_splitter)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setCentralWidget(central_widget)

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Initializing...")

        # Initial state: Disconnected, disable buttons requiring connection
        self.toolbar.run_action.setEnabled(False)
        self.toolbar.stop_action.setEnabled(False)
        self.toolbar.disconnect_action.setEnabled(False)

    def _setup_port_monitor(self):
        self.port_monitor = QTimer(self)
        self.port_monitor.setInterval(1500)
        self.port_monitor.timeout.connect(self._check_current_port_status)
        self.port_monitor.start()

    def _setup_worker(self):
        """Setup background thread and Worker"""
        # Create thread
        self.worker_thread = QThread()

        # Create Worker (will run in thread)
        self.worker = DeviceWorker('')

        # Move Worker to thread
        self.worker.moveToThread(self.worker_thread)

        # Initialize Worker after thread starts (Important: serial object must be created in thread)
        self.worker_thread.started.connect(self.worker.initialize)

        # Connect request signals to slots (UI -> Worker)
        # Qt automatically uses QueuedConnection to ensure execution in Worker thread
        self.worker.connect_requested.connect(self.worker.do_connect)
        self.worker.run_code_requested.connect(self.worker.do_run_code)
        self.worker.stop_requested.connect(self.worker.do_stop)
        self.worker.disconnect_requested.connect(self.worker.do_disconnect)
        self.worker.list_dir_requested.connect(self.worker.do_list_dir)
        self.worker.read_file_requested.connect(self.worker.do_read_file)
        self.worker.write_file_requested.connect(self.worker.do_write_file)
        self.worker.delete_path_requested.connect(self.worker.do_delete_path)
        self.worker.set_port_requested.connect(self.worker.set_port)

        # Start thread
        self.worker_thread.start()

    def _connect_signals(self):
        """Connect signals and slots"""
        # Toolbar buttons -> Worker actions
        self.toolbar.new_clicked.connect(self.on_new_file)
        self.toolbar.run_clicked.connect(self.on_run_code)
        self.toolbar.stop_clicked.connect(self.on_stop_code)
        self.toolbar.save_clicked.connect(self.on_save_file)
        self.toolbar.disconnect_clicked.connect(self.on_disconnect_clicked)
        self.toolbar.install_plot_lib_clicked.connect(self.on_install_plot_lib_clicked)

        # Worker initialization complete -> Auto connect device
        self.worker.initialized.connect(self._connect_device)

        # Worker progress info -> UI
        self.worker.progress.connect(self.output_console.append_info)
        self.worker.status_changed.connect(self.status_bar.showMessage)

        # Worker output info -> Output console
        self.worker.output_received.connect(self.output_console.append_output)
        self.worker.error_received.connect(self.output_console.append_error)

        # Worker action complete -> UI update
        self.worker.connect_finished.connect(self.on_connect_finished)
        self.worker.run_finished.connect(self.on_run_finished)
        self.worker.stop_finished.connect(self.on_stop_finished)
        self.worker.disconnect_finished.connect(self.on_disconnect_finished)

        # File browser -> Worker
        self.file_browser.dir_expand_requested.connect(self.worker.list_dir_requested.emit)
        self.file_browser.file_open_requested.connect(self.on_file_open_requested)
        self.file_browser.delete_requested.connect(self.on_delete_requested)

        # Worker -> File browser
        self.worker.list_dir_finished.connect(self.on_list_dir_finished)

        # Worker -> File operations
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

        # Plot button -> Open plotter window
        self.toolbar.plot_clicked.connect(self.on_plot_clicked)

        # Plot data -> Forward to plotter window
        self.worker.plot_data_received.connect(self._forward_plot_data)
        self.worker.plot_config_received.connect(self._forward_plot_config)

        # Initial scan but do not connect immediately (wait for Worker ready)
        self.refresh_ports(auto_connect=True)

    def _connect_device(self):
        """Connect to device"""
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

        # Update UI state
        self._update_ui_for_disconnected_state()

        ports = [(info.device, format_label(info)) for info in port_infos]
        self.toolbar.set_ports(ports, None)
        self.toolbar.show_disconnected_placeholder()
        self.status_bar.showMessage("Device disconnected")

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
        """Run code button handler"""
        # 1. Check if current file needs saving
        self.auto_open_plot = True
        path, content, modified = self.tab_editor.get_current_file_info()
        if path and modified:
            # Auto save (mark as saved only after async completion signal)
            self.output_console.append_info("[System] Auto saving file...")
            self.worker.write_file_requested.emit(path, content)

        # 2. Get code
        code = self.tab_editor.get_current_code().strip()

        if not code:
            self.output_console.append_error("[Error] Code is empty")
            self.status_bar.showMessage("Code is empty")
            return

        # Disable buttons to prevent double click
        self.set_buttons_enabled(False)

        # Trigger Worker to run code (async)
        self.worker.run_code_requested.emit(code)

    def on_stop_code(self):
        """Stop code button handler"""
        # Disable buttons to prevent double click
        self.set_buttons_enabled(False)

        # Trigger Worker to stop code (async)
        self.worker.stop_requested.emit()

    def on_connect_finished(self, success):
        """Connect finished handler"""
        if success:
            self.file_browser.initialize_root()
            # Enable disconnect and action buttons after successful connection
            self.toolbar.disconnect_action.setEnabled(True)
            self.toolbar.run_action.setEnabled(True)
            self.toolbar.stop_action.setEnabled(True)
            self.toolbar.install_plot_lib_action.setEnabled(True)
        else:
            self.file_browser.show_error("Connecting to device failed")
            # Connection failed, disable all buttons requiring connection
            self.toolbar.disconnect_action.setEnabled(False)
            self.toolbar.run_action.setEnabled(False)
            self.toolbar.stop_action.setEnabled(False)
            self.toolbar.install_plot_lib_action.setEnabled(False)

    def on_run_finished(self, success):
        """Run finished handler"""
        # Restore button state
        self.set_buttons_enabled(True)

    def on_stop_finished(self, success):
        """Stop finished handler"""
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
        """Directory list finished handler"""
        if success:
            self.file_browser.populate_directory(path, items)
            self._busy_directory_paths.discard(path)
            return

        if path in self._busy_directory_paths:
            # Device busy caused directory refresh failure, keep existing list
            self._busy_directory_paths.discard(path)
            self.file_browser.cancel_directory_request(path)
            self.output_console.append_info(
                f"[File browser] Device busy while refreshing {path}, keeping previous entries"
            )
            return

        self.file_browser.show_error(f"[File browser] Cannot list directory: {path}")
        self.output_console.append_error(f"[File browser] Cannot list directory: {path}")

    def on_delete_requested(self, path: str, is_dir: bool):
        """File or directory delete request"""
        target = "folder" if is_dir else "file"
        self.output_console.append_info(f"[File] Deleting {target}: {path}")
        # Record delete type for handling after success
        self._pending_deletes[path] = is_dir
        self.worker.delete_path_requested.emit(path)

    def on_file_open_requested(self, path: str):
        """File open request handler (double click file)"""
        self.output_console.append_info(f"[File] Opening: {path}")
        # Trigger Worker to read file
        self.worker.read_file_requested.emit(path)

    def on_read_file_finished(self, success: bool, path: str, content: str):
        """File read finished handler"""
        # Check if it is installation process
        if self._installing_plot_lib and path == '/lib/signal_plotter.py':
            self._handle_plot_lib_check_result(success)
            return

        if success:
            # Check if file is already open in tab
            current_path, _, _ = self.tab_editor.get_current_file_info()

            # Check if tab exists
            is_already_open = False
            for index, state in self.tab_editor.tab_states.items():
                if state['path'] == path:
                    is_already_open = True
                    break

            if is_already_open:
                # Already open, update content (do not trigger modified status)
                self.tab_editor.update_file_content(path, content)
                self.output_console.append_info(f"[File] Updated: {path}")
            else:
                # Not open, open in new tab
                self.tab_editor.open_file(path, content)
                self.output_console.append_info(f"[File] Opened: {path}")
        else:
            self.output_console.append_error(f"[File] Open failed: {path}")

    def _handle_plot_lib_check_result(self, file_exists: bool):
        """Handle Plot Lib file check result"""
        if file_exists:
            # File exists, ask user whether to update
            reply = QMessageBox.question(
                self,
                "Library Exists",
                "signal_plotter.py already exists in /lib/ directory.\n\nUpdate?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.output_console.append_info("[Install] Installation cancelled")
                self._cleanup_installation_state()
                return

        # Execute installation
        self.output_console.append_info("[Install] Installing library to device...")
        self.worker.write_file_requested.emit('/lib/signal_plotter.py', self._plot_lib_content)

    def on_save_file(self):
        """Save file button handler"""
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

        # Trigger Worker to write file (mark as saved only after async completion signal)
        self.output_console.append_info(f"[File] Saving: {path}")
        self.worker.write_file_requested.emit(path, content)

    def on_disconnect_clicked(self):
        """Disconnect button handler"""
        # Disable disconnect button to prevent double click
        self.toolbar.disconnect_action.setEnabled(False)

        # Output info
        self.output_console.append_info("[System] Requesting disconnect...")

        # Trigger Worker to disconnect (async)
        self.worker.disconnect_requested.emit()

    def on_disconnect_finished(self):
        """Disconnect finished handler"""
        # Update UI state
        self._update_ui_for_disconnected_state()

        # Update dropdown to show "Disconnected"
        self.toolbar.show_disconnected_placeholder()

        # Update status bar
        self.status_bar.showMessage("Disconnected")

        # Clear current_port (user initiated disconnect)
        self.current_port = None

    def on_install_plot_lib_clicked(self):
        """Install Plot Lib button handler"""
        # 1. Get library content (embedded in code, available after packaging)
        self._plot_lib_content = self._get_signal_plotter_lib_content()

        # 2. Disable button to prevent double click
        self.toolbar.install_plot_lib_action.setEnabled(False)
        self._installing_plot_lib = True

        # 3. Check if file exists on device
        self.output_console.append_info("[Install] Checking device library...")
        self.worker.read_file_requested.emit('/lib/signal_plotter.py')

    def _get_signal_plotter_lib_content(self) -> str:
        """Get signal_plotter.py library content"""
        # Embedded library content, usable after packaging
        return '''import builtins
import sys
from machine import UART, Pin


class _SignalPlotter:
    _MAX_PARAMS = 5
    _MAX_NAME_LEN = 16
    _CONFIG_INTERVAL = 10  # send name config every a few packets

    def __init__(self):
        self._built_in_print = builtins.print
        builtins.print = lambda *a, **k: None

        self._configured = False
        self._packet_counter = 0

        self._data_packet = bytearray(3 + self._MAX_PARAMS * 2)
        self._data_view = None
        self._config_packet = None

        self._iface = sys.stdout.buffer
        self._param_count = 0
        self._param_names = []

        self._debug_led = None
        self._debug_led_acc = 0
        self._debug_led_toggle_interval = 250

        self._print_welcome_msg()

    def _print_msg(self, msg):
        self._built_in_print("[Signal_Plotter]", msg)

    def _print_welcome_msg(self):
        self._built_in_print("\\n[Signal Plotter]")
        mode = "CDC" if self._iface == sys.stdout.buffer else "UART"
        self._print_msg(f"Using {mode} mode")

        self._print_msg("Built-in print() is suppressed by default.")
        self._print_msg("Use plotter.print(...) for debug output.\\n")
        self._print_msg("Use plotter.restore_print() to restore print function.\\n")

        self._print_msg("Use plotter.plot('name1', val1, 'name2', val2, ...) to send data.")
        self._print_msg("Maximum 5 variables can be print (int or float)\\n")

    def _validate_and_extract_params(self, args):
        """Validate format: 'name', value, 'name', value, ..."""
        if len(args) % 2 != 0:
            raise ValueError("Arguments must be pairs of ('name', value)")

        if len(args) // 2 > self._MAX_PARAMS:
            raise ValueError(f"Maximum {self._MAX_PARAMS} parameters allowed")

        names = []
        for i in range(0, len(args), 2):
            name = args[i]
            value = args[i + 1]

            if not isinstance(name, str):
                raise TypeError(f"Parameter {i // 2}: name must be string, got {type(name).__name__}")

            if not isinstance(value, (int, float)):
                raise TypeError(f"Parameter '{name}': value must be int or float, got {type(value).__name__}")

            # Check encoded length
            name_bytes = name.encode('utf-8')
            if len(name_bytes) > self._MAX_NAME_LEN:
                raise ValueError(f"Parameter name '{name}' exceeds {self._MAX_NAME_LEN} bytes when encoded")

            if not name:
                raise ValueError("Parameter name cannot be empty")

            names.append(name)

        return names

    def _build_config_packet(self):
        """Build configuration packet: 0xAA 0x02 [count] [len][name1][len][name2]..."""
        packet = bytearray([0xAA, 0x02, self._param_count])

        for name in self._param_names:
            name_bytes = name.encode('utf-8')
            packet.append(len(name_bytes))
            packet.extend(name_bytes)

        return packet

    def _send_config(self):
        """Send configuration packet"""
        if self._config_packet:
            self._iface.write(self._config_packet)

    def set_uart_mode(self, tx=4, rx=5, baudrate=115200):
        self._iface = UART(1, baudrate, tx=Pin(tx), rx=Pin(rx))
        self._print_msg("Switched to UART mode")

    def set_cdc_mode(self):
        self._iface = sys.stdout.buffer
        self._print_msg("Switched to CDC mode")

    def enable_debug(self, led_pin, toggle_interval=250):
        self._debug_led = Pin(led_pin, Pin.OUT)
        self._debug_led_acc = 0
        self._debug_led_toggle_interval = toggle_interval
        self._print_msg(f"LED debug enabled on pin {led_pin}")

    def disable_debug(self):
        if self._debug_led:
            self._debug_led.off()
            self._debug_led = None
            self._print_msg("LED debug disabled")

    def restore_print(self):
        builtins.print = self._built_in_print
        self._print_msg("Built-in print() restored")

    def suppress_print(self):
        builtins.print = lambda *a, **k: None
        self._print_msg("Built-in print() suppressed")

    def print(self, *args, **kwargs):
        self._built_in_print(*args, **kwargs)

    def plot(self, *args):
        # First call: validate and configure
        if not self._configured:
            self._param_names = self._validate_and_extract_params(args)
            self._param_count = len(self._param_names)

            # Prepare data packet buffer
            self._data_packet[0] = 0xAA
            self._data_packet[1] = 0x01
            self._data_packet[2] = self._param_count
            self._data_view = memoryview(self._data_packet)[:3 + self._param_count * 2]

            # Prepare config packet
            self._config_packet = self._build_config_packet()

            self._configured = True
            self._print_msg(f"Configured with {self._param_count} parameters: {', '.join(self._param_names)}")
            self._send_config() # Send config packet once immediately, the client can connect quickly (if it's running)
        else:
            expected_args = self._param_count * 2
            if len(args) != expected_args:
                raise ValueError(
                    f"plot() expects {expected_args} arguments (name/value pairs) after configuration"
                )
            for i, expected_name in enumerate(self._param_names):
                current_name = args[i * 2]
                if current_name != expected_name:
                    raise ValueError(
                        f"Parameter name/order mismatch at index {i}: expected '{expected_name}', got '{current_name}'"
                    )

        # Send config packet periodically
        self._packet_counter += 1
        if self._packet_counter % self._CONFIG_INTERVAL == 0:
            self._send_config()

        # Extract values and pack data
        idx = 3
        for i in range(1, len(args), 2):
            v = int(args[i]) & 0xFFFF
            self._data_packet[idx] = v & 0xFF
            self._data_packet[idx + 1] = v >> 8
            idx += 2

        # Send data packet
        self._iface.write(self._data_view)

        # Debug LED toggle
        if self._debug_led:
            self._debug_led_acc = (self._debug_led_acc + 1) % self._debug_led_toggle_interval
            if self._debug_led_acc == 0:
                self._debug_led.toggle()


plotter = _SignalPlotter()
'''

    def _update_ui_for_disconnected_state(self):
        """Update UI state after disconnect"""
        # 1. Disable buttons requiring connection
        self.toolbar.run_action.setEnabled(False)
        self.toolbar.stop_action.setEnabled(False)
        self.toolbar.disconnect_action.setEnabled(False)
        self.toolbar.install_plot_lib_action.setEnabled(False)

        # 2. Clear file browser
        self.file_browser.show_error("Device not connected")

        # 3. Close plotter window (if open)
        if self.plotter_window:
            self.plotter_window.close()
            self.plotter_window.deleteLater()
            self.plotter_window = None

    def _cleanup_installation_state(self):
        """Reset installation state and restore buttons"""
        self._installing_plot_lib = False
        self._plot_lib_content = None
        # Enable button only if connected
        if self.current_port and self.toolbar.disconnect_action.isEnabled():
            self.toolbar.install_plot_lib_action.setEnabled(True)

    def on_write_file_finished(self, success: bool, path: str):
        """File write finished handler"""
        # Check if installation process
        if self._installing_plot_lib and path == '/lib/signal_plotter.py':
            if success:
                self.output_console.append_info("[Install] Library installed successfully!")
                QMessageBox.information(
                    self,
                    "Installation Complete",
                    "signal_plotter.py has been installed to /lib/ directory.\n\n"
                    "You can now use:\nfrom signal_plotter import plotter",
                    QMessageBox.StandardButton.Ok
                )
                # Refresh /lib directory
                self.file_browser.request_directory('/lib')
            else:
                self.output_console.append_error("[Install] Installation failed")
                QMessageBox.warning(
                    self,
                    "Installation Failed",
                    "Failed to install library. Please check device connection.",
                    QMessageBox.StandardButton.Ok
                )
            self._cleanup_installation_state()
            return

        if success:
            # Saved successfully, mark as saved
            self.tab_editor.mark_file_saved(path)
            self.output_console.append_info(f"[File] Save successfully: {path}")
            parent_dir = self._parent_directory(path)
            # Force refresh parent directory to update browser immediately
            self.file_browser.request_directory(parent_dir)

            # Reload file to ensure consistency
            self.output_console.append_info(f"[File] Reloading after saving...")
            self.worker.read_file_requested.emit(path)
        else:
            # Save failed, keep modified status
            self.output_console.append_error(f"[File] Save failed: {path}")

    def on_delete_path_finished(self, success: bool, path: str):
        """File/directory delete finished"""
        if success:
            # Get type from pending deletes
            is_dir = self._pending_deletes.pop(path, False)

            # Close related tabs
            if is_dir:
                # If directory, close all files under it
                self.tab_editor.close_files_under_directory(path)
            else:
                # If file, close only that file tab
                self.tab_editor.close_file(path)

            # Remove from file browser
            self.file_browser.remove_entry(path)

            # Refresh parent directory
            parent_dir = self._parent_directory(path)
            self.file_browser.request_directory(parent_dir)

            self.output_console.append_info(f"[File] Deleted: {path}")
        else:
            # Delete failed, clean up pending record
            self._pending_deletes.pop(path, None)
            self.output_console.append_error(f"[File] Delete failed: {path}")

    def on_file_modified(self, modified: bool):
        """File modified status changed"""
        # Update save button status
        can_save = modified or self.tab_editor.current_is_untitled()
        self.toolbar.save_action.setEnabled(can_save)

    def on_file_access_busy(self, operation: str, path: str):
        """Show device busy dialog, allow user to stop program"""
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
        """Active file changed handler"""
        # Update status bar
        if path:
            self.status_bar.showMessage(f"Current file: {path}")
        else:
            self.status_bar.showMessage("Ready")

        # Update save button status
        _, _, modified = self.tab_editor.get_current_file_info()
        can_save = modified or self.tab_editor.current_is_untitled()
        self.toolbar.save_action.setEnabled(can_save)

    def set_buttons_enabled(self, enabled: bool):
        """Set buttons enabled state"""
        self.toolbar.run_action.setEnabled(enabled)
        self.toolbar.stop_action.setEnabled(enabled)

    @staticmethod
    def _parent_directory(path: str) -> str:
        """Return parent directory (return root if path is empty)"""
        if not path:
            return '/'
        normalized = path.rstrip('/') or '/'
        if normalized == '/':
            return '/'
        parent = normalized.rsplit('/', 1)[0]
        return parent or '/'

    def on_plot_clicked(self):
        """Plot button click handler"""
        self.auto_open_plot = True

        # If window exists, close and destroy
        if self.plotter_window is not None:
            self.plotter_window.close()
            self.plotter_window.deleteLater()
            self.plotter_window = None

        # Create new window (ensure data reset)
        self.plotter_window = PlotterWindow()
        self.plotter_window.closed.connect(self._on_plotter_closed)

        # Show window
        self.plotter_window.show()
        self.plotter_window.raise_()
        self.plotter_window.activateWindow()

        # Enable plot mode
        self.worker.set_plot_mode(True)

    def _on_plotter_closed(self):
        """Plotter window closed handler"""
        # Disable plot mode
        self.worker.set_plot_mode(False)
        self.auto_open_plot = False

    def _forward_plot_data(self, values: list):
        """
        Forward plot data to plotter window

        Args:
            values: List of plot data values
        """
        if not values:
            return

        if (not self.plotter_window or not self.plotter_window.isVisible()) and self.auto_open_plot:
            self.on_plot_clicked()

        if self.plotter_window and self.plotter_window.isVisible():
            self.plotter_window.on_plot_data_received(values)

    def _forward_plot_config(self, names: list):
        """Update legend names in plotter window after receiving channel config"""
        if not names:
            return

        if (not self.plotter_window or not self.plotter_window.isVisible()) and self.auto_open_plot:
            self.on_plot_clicked()

        if self.plotter_window and self.plotter_window.isVisible():
            self.plotter_window.on_plot_config_received(names)

    def closeEvent(self, event):
        """Window close event"""
        if hasattr(self, "port_monitor") and self.port_monitor.isActive():
            self.port_monitor.stop()

        # 1. Close plotter window
        if self.plotter_window:
            self.plotter_window.close()

        # 2. Disconnect device (in Worker thread)
        self.output_console.append_info("[System] Disconnecting device...")
        self.worker.disconnect_requested.emit()

        # 3. Stop and wait for thread to finish
        self.worker_thread.quit()
        self.worker_thread.wait(3000)  # Wait up to 3 seconds

        # 4. Accept close event
        event.accept()
