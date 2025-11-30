import time
from collections import deque
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QLineEdit, QPushButton, QDialog, QFormLayout, QDialogButtonBox,
    QColorDialog
)
from PySide6.QtCore import Signal, Slot, QTimer, Qt
from PySide6.QtGui import QColor
import pyqtgraph as pg


class ColorSettingsDialog(QDialog):
    """Dialog for customizing plot background and curve colors"""

    def __init__(self, current_bg_color, current_curve_colors, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Color Settings")
        self.setModal(True)
        self.resize(400, 300)

        # Store current colors
        self.bg_color = QColor(current_bg_color) if isinstance(current_bg_color, str) else current_bg_color
        self.curve_colors = [
            QColor(c) if isinstance(c, str) else c
            for c in current_curve_colors
        ]

        self._setup_ui()

    def _setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout(self)

        # Form layout for color selections
        form_layout = QFormLayout()

        # Background color button
        self.bg_color_button = QPushButton()
        self.bg_color_button.setFixedHeight(30)
        self._update_button_color(self.bg_color_button, self.bg_color)
        self.bg_color_button.clicked.connect(lambda: self._choose_color(0))
        form_layout.addRow("Background Color:", self.bg_color_button)

        # Curve color buttons
        self.curve_color_buttons = []
        for i in range(5):
            button = QPushButton()
            button.setFixedHeight(30)
            self._update_button_color(button, self.curve_colors[i])
            button.clicked.connect(lambda checked, idx=i: self._choose_color(idx + 1))
            self.curve_color_buttons.append(button)
            form_layout.addRow(f"Channel {i + 1} Color:", button)

        layout.addLayout(form_layout)

        # OK/Cancel buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _update_button_color(self, button, color):
        """Update button appearance to show the selected color"""
        button.setStyleSheet(
            f"background-color: {color.name()}; "
            f"border: 1px solid #555;"
        )

    def _choose_color(self, index):
        """Open color picker dialog

        Args:
            index: 0 for background, 1-5 for curves
        """
        if index == 0:
            # Background color
            current_color = self.bg_color
            new_color = QColorDialog.getColor(current_color, self, "Select Background Color")
            if new_color.isValid():
                self.bg_color = new_color
                self._update_button_color(self.bg_color_button, new_color)
        else:
            # Curve color
            curve_idx = index - 1
            current_color = self.curve_colors[curve_idx]
            new_color = QColorDialog.getColor(
                current_color, self, f"Select Channel {curve_idx + 1} Color"
            )
            if new_color.isValid():
                self.curve_colors[curve_idx] = new_color
                self._update_button_color(self.curve_color_buttons[curve_idx], new_color)

    def get_colors(self):
        """Return selected colors as (bg_color, curve_colors)"""
        return self.bg_color, self.curve_colors


class PlotterWindow(QWidget):
    """
    Real-time plotter window for displaying multi-channel data.

    Displays up to 5 customizable data channels with:
    - Custom channel names (editable in real-time)
    - Customizable colors (via settings dialog)
    - Real-time updates at 20 Hz
    - Simple runtime and datarate statistics
    """

    closed = Signal()  # Emitted when window is closed

    def __init__(self, parent=None):
        super().__init__(parent)

        # Window setup
        self.setWindowTitle("Real-time Plotter")
        self.resize(1200, 800)

        # Default settings
        self.default_labels = ["Channel 1", "Channel 2", "Channel 3", "Channel 4", "Channel 5"]
        self.background_color = QColor(0, 0, 0)  # Black background
        self.curve_colors = [
            QColor(255, 0, 0),      # Red
            QColor(0, 0, 255),      # Blue
            QColor(0, 255, 0),      # Green
            QColor(255, 255, 0),    # Yellow
            QColor(255, 0, 255),    # Magenta
        ]

        # Data buffers (5 channels)
        self.buffers = [deque(maxlen=2000) for _ in range(5)]
        self.time_buffer = deque(maxlen=2000)
        self.start_time = time.time()

        # Statistics
        self.packet_count = 0

        # UI components (will be created in _setup_ui)
        self.channel_name_inputs = []
        self.curves = []
        self.stats_text = None
        self.ui_timer = None

        # Setup UI and timers
        self._setup_ui()
        self._setup_timers()

    def _setup_ui(self):
        """Create the plotting UI with control panel"""
        # Main horizontal layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create splitter for resizable layout
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side: Plot area (80%)
        self.graphics_widget = self._create_plot_area()
        splitter.addWidget(self.graphics_widget)

        # Right side: Control panel (20%)
        control_panel = self._create_control_panel()
        splitter.addWidget(control_panel)

        # Set initial splitter sizes
        splitter.setStretchFactor(0, 4)  # Plot: 80%
        splitter.setStretchFactor(1, 1)  # Control: 20%

        main_layout.addWidget(splitter)

    def _create_plot_area(self):
        """Create the plotting area with pyqtgraph"""
        # Performance optimizations
        pg.setConfigOptions(antialias=False)

        # Create graphics widget
        graphics_widget = pg.GraphicsLayoutWidget()

        # Set background color
        graphics_widget.setBackground(self.background_color)

        # Create plot
        self.plot = graphics_widget.addPlot(title="Waveform Display")
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.setLabel("left", "Value")
        self.plot.addLegend()
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setClipToView(True)
        self.plot.setDownsampling(auto=True, mode="peak")

        # Create 5 curves
        self.curves = []
        for i in range(5):
            curve = self.plot.plot(
                pen=pg.mkPen(self.curve_colors[i], width=2),
                name=self.default_labels[i],
                skipFiniteCheck=True
            )
            self.curves.append(curve)

        # Statistics label (below plot)
        graphics_widget.nextRow()
        self.stats_label = pg.LabelItem(justify="left")
        graphics_widget.addItem(self.stats_label)

        return graphics_widget

    def _create_control_panel(self):
        """Create the right-side control panel"""
        panel = QWidget()
        panel.setMaximumWidth(250)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)

        # Title
        title_label = QLabel("Channel Settings")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        # Channel name inputs
        layout.addWidget(QLabel("Channel Names:"))
        for i in range(5):
            name_input = QLineEdit(self.default_labels[i])
            name_input.textChanged.connect(
                lambda text, idx=i: self._update_curve_name(idx, text)
            )
            self.channel_name_inputs.append(name_input)
            layout.addWidget(name_input)

        layout.addSpacing(20)

        # Color settings button
        color_button = QPushButton("Color Settings...")
        color_button.clicked.connect(self._open_color_settings)
        layout.addWidget(color_button)

        # Add stretch to push everything to the top
        layout.addStretch()

        return panel

    def _setup_timers(self):
        """Setup timers for UI updates"""
        # UI update timer - 20 Hz (50ms)
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui)
        self.ui_timer.start(50)

    @Slot(int, str)
    def _update_curve_name(self, index, name):
        """Update the legend name for a curve"""
        if 0 <= index < len(self.curves):
            # Remove old curve from legend and re-add with new name
            self.curves[index].setData([], [])  # Clear temporarily

            # Update curve with new name
            self.curves[index] = self.plot.plot(
                pen=pg.mkPen(self.curve_colors[index], width=2),
                name=name or f"Channel {index + 1}",
                skipFiniteCheck=True
            )

    @Slot()
    def _open_color_settings(self):
        """Open the color settings dialog"""
        dialog = ColorSettingsDialog(
            self.background_color,
            self.curve_colors,
            parent=self
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            bg_color, curve_colors = dialog.get_colors()
            self._apply_colors(bg_color, curve_colors)

    def _apply_colors(self, bg_color, curve_colors):
        """Apply new colors to the plot"""
        # Update stored colors
        self.background_color = bg_color
        self.curve_colors = curve_colors

        # Apply background color
        self.graphics_widget.setBackground(bg_color)

        # Apply curve colors
        for i, color in enumerate(curve_colors):
            self.curves[i].setPen(pg.mkPen(color, width=2))

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

        # Update statistics
        self._update_stats()

    def _update_stats(self):
        """Update statistics label (simplified)"""
        elapsed = time.time() - self.start_time
        packet_rate = self.packet_count / elapsed if elapsed > 0 else 0

        # Format statistics string
        stats = (
            f"Runtime: {elapsed:.1f}s  |  "
            f"Datarate: {packet_rate:.1f}/s"
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
