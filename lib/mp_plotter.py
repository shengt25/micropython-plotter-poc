import builtins
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
        self._built_in_print("\n[Signal Plotter]")
        mode = "CDC" if self._iface == sys.stdout.buffer else "UART"
        self._print_msg(f"Using {mode} mode")

        self._print_msg("Built-in print() is suppressed by default.")
        self._print_msg("Use plotter.print(...) for debug output.\n")
        self._print_msg("Use plotter.restore_print() to restore print function.\n")

        self._print_msg("Use plotter.plot('name1', val1, 'name2', val2, ...) to send data.")
        self._print_msg("Maximum 5 variables can be print (int or float)\n")

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
