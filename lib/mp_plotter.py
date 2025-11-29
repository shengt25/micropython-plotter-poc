import builtins
import sys
from machine import UART, Pin


class _MPPlotter:
    _MAX_PARAMS = 5
    _HEADER_0 = 0xAA
    _HEADER_1 = 0x01

    def __init__(self):
        self._built_in_print = builtins.print
        builtins.print = lambda *a, **k: None

        self._configured = False

        self._packet_buf = bytearray(3 + self._MAX_PARAMS * 2)
        self._packet_view = None
        self._iface = sys.stdout.buffer
        self._param_count = 0

        self._debug_led = None
        self._debug_led_acc = 0
        self._debug_led_toggle_interval = 250

        self._print_welcome_msg()

    def _print_msg(self, msg):
        self._built_in_print("[MP_Plotter]", msg)

    def _print_welcome_msg(self):
        self._built_in_print("\n[MicroPython Plotter]")
        mode = "CDC" if self._iface == sys.stdout.buffer else "UART"
        self._print_msg(f"Using {mode} mode")
        self._print_msg("Built-in print() is suppressed by default.")
        self._print_msg("Use plotter.print(...) for debug output.\n")
        self._print_msg("Use plotter.plot(...) to send data for plotting.")
        self._print_msg("Parameters: 1 to 5 16-bit integers. (unsigned 0-65535 or signed -32768 to 32767)\n")

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
        self._print_msg("Build-in print() restored")

    def suppress_print(self):
        builtins.print = lambda *a, **k: None
        self._print_msg("Build-in print() suppressed")

    def print(self, *args, **kwargs):
        self._built_in_print(*args, **kwargs)

    def plot(self, *values):
        if not self._configured:
            self._param_count = len(values)
            if not (0 < self._param_count <= self._MAX_PARAMS):
                raise ValueError(f"Parameter count must be 1-{self._MAX_PARAMS}, got {self._param_count}")

            for i in range(self._param_count):
                if not isinstance(values[i], (int, float)):
                    raise TypeError(f"Parameter {i} must be int or float, got {type(values[i]).__name__}")

            self._packet_buf[0] = self._HEADER_0
            self._packet_buf[1] = self._HEADER_1
            self._packet_buf[2] = self._param_count
            self._packet_view = memoryview(self._packet_buf)[:3 + self._param_count * 2]
            self._configured = True
            self._print_msg(f"Configured with {self._param_count} parameters\n")

        idx = 3
        for i in range(self._param_count):
            v = int(values[i]) & 0xFFFF
            self._packet_buf[idx] = v & 0xFF
            self._packet_buf[idx + 1] = v >> 8
            idx += 2

        self._iface.write(self._packet_view)

        if self._debug_led:
            self._debug_led_acc = (self._debug_led_acc + 1) % self._debug_led_toggle_interval
            if self._debug_led_acc == 0:
                self._debug_led.toggle()


plotter = _MPPlotter()