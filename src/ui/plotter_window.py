import time
from collections import deque
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Signal, Slot, QTimer
import pyqtgraph as pg


class PlotterWindow(QWidget):
    """
    Real-time plotter window for displaying heart rate monitor data.

    Displays 5 channels:
    - Threshold (red)
    - ADC Value (blue)
    - FIFO Count (green)
    - Peak (yellow)
    - Heart Rate (magenta)
    """

    closed = Signal()  # Emitted when window is closed

    def __init__(self, parent=None):
        super().__init__(parent)

        # Window setup
        self.setWindowTitle("Real-time Plotter")
        self.resize(1200, 800)

        # Data buffers (5 channels)
        self.buffers = [deque(maxlen=2000) for _ in range(5)]
        self.time_buffer = deque(maxlen=2000)
        self.start_time = time.time()

        # Statistics
        self.packet_count = 0
        self.error_count = 0
        self.last_fifo_count = 0

        # Setup UI and timers
        self._setup_ui()
        self._setup_timers()

    def _setup_ui(self):
        """Create the plotting UI using pyqtgraph"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Performance optimizations
        pg.setConfigOptions(antialias=False)  # Faster rendering

        # Create graphics widget
        self.graphics_widget = pg.GraphicsLayoutWidget()
        layout.addWidget(self.graphics_widget)

        # Create plot
        self.plot = self.graphics_widget.addPlot(title="Waveform Display")
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.setLabel("left", "Value")
        self.plot.addLegend()
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setClipToView(True)  # Only render visible area
        self.plot.setDownsampling(auto=True, mode="peak")  # Downsample for performance

        # Create 5 curves with different colors
        colors = ["r", "b", "g", "y", "m"]
        labels = ["Threshold", "ADC Value", "FIFO Count", "Peak", "Heart Rate"]
        self.curves = []

        for i in range(5):
            curve = self.plot.plot(
                pen=pg.mkPen(colors[i], width=2),
                name=labels[i],
                skipFiniteCheck=True  # Skip validation for performance
            )
            self.curves.append(curve)

        # Statistics label
        self.graphics_widget.nextRow()
        self.stats_label = pg.LabelItem(justify="left")
        self.graphics_widget.addItem(self.stats_label)

    def _setup_timers(self):
        """Setup timers for UI updates"""
        # UI update timer - 20 Hz (50ms)
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui)
        self.ui_timer.start(50)

    @Slot(list)
    def on_plot_data_received(self, values: list):
        """
        Receive plot data from serial stream.

        Args:
            values: List of up to 5 uint16 values
        """
        current_time = time.time() - self.start_time
        self.time_buffer.append(current_time)

        # Append values to corresponding buffers
        for i, val in enumerate(values):
            if i < 5:  # Safety check
                self.buffers[i].append(val)

        # Fill remaining buffers with None if values list is shorter
        for i in range(len(values), 5):
            self.buffers[i].append(None)

        # Track FIFO count if available (channel 2)
        if len(values) >= 3:
            self.last_fifo_count = values[2]

        self.packet_count += 1

    def update_ui(self):
        """Update curves and statistics (called by timer at 20 Hz)"""
        if len(self.time_buffer) == 0:
            return

        # Convert time buffer to list once
        time_array = list(self.time_buffer)

        # Update each curve
        for i, curve in enumerate(self.curves):
            # Filter out None values
            data = [x for x in self.buffers[i] if x is not None]

            if data:
                # Match time array length to data length
                time_data = time_array[-len(data):]
                curve.setData(time_data, data)
            else:
                # Clear curve if no data
                curve.setData([], [])

        # Update statistics every 10 packets
        if self.packet_count % 10 == 0:
            self._update_stats()

    def _update_stats(self):
        """Update statistics label"""
        elapsed = time.time() - self.start_time
        packet_rate = self.packet_count / elapsed if elapsed > 0 else 0

        # Calculate average BPM from recent heart rate values (channel 4)
        recent_bpm = [x for x in list(self.buffers[4])[-10:] if x and x > 0]
        bpm_str = (
            f"{int(sum(recent_bpm) / len(recent_bpm))} BPM" if recent_bpm else "N/A"
        )

        # Calculate FIFO percentage
        fifo_percent = (
            (self.last_fifo_count / 256) * 100 if self.last_fifo_count > 0 else 0
        )

        # Format statistics string
        stats = (
            f"Runtime: {elapsed:.1f}s  |  "
            f"Packets: {self.packet_count}  |  "
            f"Datarate: {packet_rate:.1f}/s  |  "
            f"Errors: {self.error_count}  |  "
            f"BPM: {bpm_str}  |  "
            f"FIFO: {self.last_fifo_count} ({fifo_percent:.1f}%)"
        )
        self.stats_label.setText(stats)

    def showEvent(self, event):
        """Handle window show event - restart timer when window reopens"""
        super().showEvent(event)

        # Restart timer if it was stopped
        if self.ui_timer and not self.ui_timer.isActive():
            self.ui_timer.start(50)

    def closeEvent(self, event):
        """Handle window close event"""
        # Stop timer
        if self.ui_timer:
            self.ui_timer.stop()

        # Emit closed signal
        self.closed.emit()

        # Accept the close event
        event.accept()
