from typing import Optional, Tuple, List
from PySide6.QtCore import QObject, Signal
from utils.logger import setup_logger


class PlotStreamHandler(QObject):
    """
    Parse incoming serial data and route to plotter or console.

    Detects binary plot packets (0xAA 0x01 protocol) and emits them separately
    from normal text output.
    """

    # Qt Signals
    plot_data_received = Signal(list)   # Emits [val1, val2, ...] for plot packets
    plot_config_received = Signal(list) # Emits ['name1', 'name2', ...] for config packets
    text_data_received = Signal(str)    # Emits text for console output

    def __init__(self, device_manager=None):
        super().__init__()
        self.dm = device_manager
        self.buffer = bytearray()
        self.enabled = False
        self.logger = setup_logger(__name__)
        self._config_received = False

    def reset_config_state(self):
        """Allow next config packet to propagate to UI."""
        self._config_received = False

    def process_data(self, raw_bytes: bytes):
        """
        Process incoming raw bytes from serial port.

        Searches for 0xAA 0x01 packets and emits them as plot_data_received.
        Everything else is emitted as text_data_received.

        Args:
            raw_bytes: Raw bytes from serial port
        """
        if not raw_bytes:
            return

        # Add to buffer
        self.buffer.extend(raw_bytes)

        # Continuously try to extract packets or text
        while len(self.buffer) > 0:
            parsed = self._try_read_packet()
            if parsed is None:
                break

            packet_type, payload = parsed
            if packet_type == "plot":
                self.plot_data_received.emit(payload)
            elif packet_type == "config":
                self._handle_config_packet(payload)

    def _try_read_packet(self) -> Optional[Tuple[str, List]]:
        """
        Try to extract one plot packet from buffer.

        Packet format:
        - 0xAA (sync byte)
        - 0x01 (packet type)
        - param_count (1-5)
        - uint16[] data (little-endian, 2 bytes each)

        Returns:
            List of values if packet found, None otherwise
        """
        # 1. Search for sync header 0xAA
        sync_idx = -1
        for i in range(len(self.buffer)):
            if self.buffer[i] == 0xAA:
                # Emit everything before sync as text
                if i > 0:
                    text_bytes = bytes(self.buffer[:i])
                    self._emit_text_bytes(text_bytes)
                    self.buffer = self.buffer[i:]
                sync_idx = 0
                break

        if sync_idx == -1:
            # No sync found in entire buffer
            # Emit all as text if buffer gets too large (avoid infinite growth)
            if len(self.buffer) > 1024:  # Arbitrary threshold
                text_bytes = bytes(self.buffer)
                self._emit_text_bytes(text_bytes)
                self.buffer.clear()
            return None

        # 2. Need at least 2 bytes for header + packet type
        if len(self.buffer) < 2:
            return None

        packet_type = self.buffer[1]
        if packet_type == 0x01:
            return self._try_read_plot_packet()
        if packet_type == 0x02:
            return self._try_read_config_packet()

        # Unknown packet type, drop sync byte
        self.buffer.pop(0)
        return None

    def _try_read_plot_packet(self) -> Optional[Tuple[str, List[int]]]:
        # Need at least 3 bytes: AA 01 param_count
        if len(self.buffer) < 3:
            return None

        param_count = self.buffer[2]
        if not (1 <= param_count <= 5):
            # Invalid param count, skip sync byte
            self.buffer.pop(0)
            return None

        packet_size = 3 + param_count * 2
        if len(self.buffer) < packet_size:
            # Wait for more data
            return None

        values = []
        for i in range(param_count):
            idx = 3 + i * 2
            # Little-endian: low byte first, then high byte
            val = self.buffer[idx] | (self.buffer[idx + 1] << 8)
            values.append(val)

        self.buffer = self.buffer[packet_size:]

        return "plot", values

    def _try_read_config_packet(self) -> Optional[Tuple[str, List[str]]]:
        # Need at least 3 bytes: AA 02 param_count
        if len(self.buffer) < 3:
            return None

        param_count = self.buffer[2]
        if not (1 <= param_count <= 5):
            self.buffer.pop(0)
            return None

        idx = 3
        names = []
        for _ in range(param_count):
            if len(self.buffer) <= idx:
                return None
            name_len = self.buffer[idx]
            idx += 1

            end_idx = idx + name_len
            if len(self.buffer) < end_idx:
                return None

            name_bytes = bytes(self.buffer[idx:end_idx])
            name = name_bytes.decode("utf-8", errors="replace")
            names.append(name)
            idx = end_idx

        # Complete packet received
        self.buffer = self.buffer[idx:]
        return "config", names

    def _handle_config_packet(self, names: List[str]):
        if self._config_received:
            return

        message = "[Plot Config] " + ", ".join(names)
        self.logger.debug(message)
        self.plot_config_received.emit(names)
        self._config_received = True

    def _emit_text_bytes(self, data: bytes):
        """Emit buffered text unless it matches our plotter protocol headers."""
        if not data:
            return

        if data[0] == 0xAA and len(data) >= 2 and data[1] in (0x01, 0x02):
            # Suppress known plot/config headers
            self.logger.debug("Suppressed %d bytes of plot/config data", len(data))
            return

        text = data.decode('utf-8', errors='replace')
        if text:
            self.text_data_received.emit(text)
