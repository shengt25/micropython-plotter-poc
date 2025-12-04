import time
from collections import deque
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QDialog, QFormLayout, QDialogButtonBox,
    QColorDialog, QComboBox
)
from PySide6.QtCore import Signal, Slot, QTimer, Qt
from PySide6.QtGui import QColor
import pyqtgraph as pg


class ColorSettingsDialog(QDialog):
    """Dialog for customizing plot background and curve colors"""

    def __init__(self, current_bg_color, current_curve_colors, channel_names, channel_count, parent=None):
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
        self.channel_names = channel_names
        self.channel_count = channel_count

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
        for i in range(self.channel_count):
            label = self.channel_names[i] if i < len(self.channel_names) else f"Channel {i + 1}"
            if not label:
                label = f"Channel {i + 1}"

            button = QPushButton()
            button.setFixedHeight(30)
            self._update_button_color(button, self.curve_colors[i])
            button.clicked.connect(lambda checked, idx=i: self._choose_color(idx + 1))
            self.curve_color_buttons.append(button)
            form_layout.addRow(f"{label} Color:", button)

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
            label = None
            if 0 <= curve_idx < len(self.channel_names):
                label = self.channel_names[curve_idx]
            if not label:
                label = f"Channel {curve_idx + 1}"
            new_color = QColorDialog.getColor(
                current_color, self, f"Select {label} Color"
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
        self.buffers = [deque(maxlen=5000) for _ in range(5)]
        self.time_buffer = deque(maxlen=5000)
        self.start_time = time.time()

        # Statistics
        self.packet_count = 0

        # Refresh rate and pause control
        self.is_paused = False
        self.refresh_rates = [10, 20, 30, 60]  # Hz
        self.current_refresh_rate = 30  # Default 30 Hz

        # Display percentage control
        self.display_percentages = [0.10, 0.25, 0.50, 0.75, 1.0]  # 10%, 25%, 50%, 75%, 100%
        self.current_display_percentage = 0.50  # Default 50%

        # UI components (will be created in _setup_ui)
        self.channel_names = self.default_labels.copy()
        self.active_channel_count = len(self.default_labels)
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

        # Configure ViewBox
        view_box = self.plot.getViewBox()
        view_box.setAutoVisible(x=True, y=True)  # Visible data only
        view_box.enableAutoRange(axis='y', enable=True)  # Auto-range Y
        view_box.setMouseEnabled(x=False, y=True)  # Disable mouse drag on X

        # Create 5 curves
        self.curves = []
        for i in range(self.active_channel_count):
            curve = self.plot.plot(
                pen=pg.mkPen(self.curve_colors[i], width=2),
                name=self.channel_names[i],
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

        # Color settings button
        color_button = QPushButton("Color Settings...")
        color_button.clicked.connect(self._open_color_settings)
        layout.addWidget(color_button)

        layout.addSpacing(20)

        # Refresh rate selection
        layout.addWidget(QLabel("Refresh Rate:"))
        self.refresh_rate_combo = QComboBox()
        self.refresh_rate_combo.addItems(["10 Hz", "20 Hz", "30 Hz", "60 Hz"])
        self.refresh_rate_combo.setCurrentIndex(2)  # Default 30 Hz
        self.refresh_rate_combo.currentIndexChanged.connect(self._on_refresh_rate_changed)
        layout.addWidget(self.refresh_rate_combo)

        layout.addSpacing(20)

        # Display percentage selection
        layout.addWidget(QLabel("Display Range:"))
        self.display_percentage_combo = QComboBox()
        self.display_percentage_combo.addItems(["10%", "25%", "50%", "75%", "100%"])
        self.display_percentage_combo.setCurrentIndex(2)  # Default 50%
        self.display_percentage_combo.currentIndexChanged.connect(self._on_display_percentage_changed)
        layout.addWidget(self.display_percentage_combo)

        layout.addSpacing(20)

        # Pause/Resume button
        self.pause_button = QPushButton("Pause")
        self.pause_button.setCheckable(True)
        self.pause_button.clicked.connect(self._on_pause_toggled)
        layout.addWidget(self.pause_button)

        # Add stretch to push everything to the top
        layout.addStretch()

        return panel

    def _setup_timers(self):
        """Setup timers for UI updates"""
        # UI update timer - default 30 Hz
        interval_ms = int(1000 / self.current_refresh_rate)
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui)
        self.ui_timer.start(interval_ms)

    def _update_legend(self):
        """Recreate all curves to update legend with correct order"""
        # Remove all existing curves
        for curve in self.curves:
            self.plot.removeItem(curve)

        # Clear curves list
        self.curves.clear()

        # Recreate all curves in order (0 to 4)
        target_count = max(0, min(self.active_channel_count, len(self.curve_colors)))
        for i in range(target_count):
            current_name = self.channel_names[i] if i < len(self.channel_names) else f"Channel {i + 1}"
            if not current_name:
                current_name = f"Channel {i + 1}"

            # Create new curve
            curve = self.plot.plot(
                pen=pg.mkPen(self.curve_colors[i], width=2),
                name=current_name,
                skipFiniteCheck=True
            )
            self.curves.append(curve)

    @Slot(int)
    def _on_refresh_rate_changed(self, index):
        """Handle refresh rate change"""
        self.current_refresh_rate = self.refresh_rates[index]
        interval_ms = int(1000 / self.current_refresh_rate)

        # Update timer interval
        if self.ui_timer:
            self.ui_timer.setInterval(interval_ms)

    @Slot(bool)
    def _on_pause_toggled(self, checked):
        """Handle pause/resume toggle"""
        self.is_paused = checked

        if checked:
            # Paused
            self.pause_button.setText("Resume")
        else:
            # Resumed
            self.pause_button.setText("Pause")

    @Slot(int)
    def _on_display_percentage_changed(self, index):
        """Handle display percentage change"""
        self.current_display_percentage = self.display_percentages[index]

    @Slot()
    def _open_color_settings(self):
        """Open the color settings dialog"""
        dialog = ColorSettingsDialog(
            self.background_color,
            self.curve_colors,
            self.channel_names,
            self.active_channel_count,
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

        # Recreate all curves with new colors
        self._update_legend()

    @Slot(list)
    def on_plot_config_received(self, names: list):
        """Update channel names from device configuration packets"""
        if not names:
            return

        count = min(len(names), len(self.default_labels))
        if count == 0:
            return

        self.active_channel_count = count
        new_names = self.channel_names[:]
        for i in range(count):
            new_names[i] = names[i] or self.default_labels[i]
        for i in range(count, len(self.default_labels)):
            new_names[i] = self.default_labels[i]

        self.channel_names = new_names
        self._update_legend()

    @Slot(list)
    def on_plot_data_received(self, values: list):
        """
        Receive plot data from serial stream.

        Args:
            values: List of up to 5 uint16 values
        """
        # Discard data if paused
        if self.is_paused:
            return

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
        """Update curves and statistics (called by timer)"""
        if len(self.time_buffer) == 0:
            return

        # Convert time buffer to list
        time_array = list(self.time_buffer)
        total_points = len(time_array)

        # Calculate how many points to display based on percentage
        if self.current_display_percentage < 1.0:
            # Show only the most recent N% points
            points_to_show = max(1, int(total_points * self.current_display_percentage))
            start_idx = total_points - points_to_show
            visible_time = time_array[start_idx:]
        else:
            # Show 100% (all points)
            start_idx = 0
            visible_time = time_array

        # Update each curve with visible data
        for i, curve in enumerate(self.curves):
            # Get data for this channel
            data = list(self.buffers[i])

            # Extract visible portion
            if start_idx > 0:
                visible_data = data[start_idx:]
            else:
                visible_data = data

            # Filter out None values
            filtered_data = [x for x in visible_data if x is not None]
            filtered_time = visible_time[-len(filtered_data):] if filtered_data else []

            if filtered_data:
                curve.setData(filtered_time, filtered_data)
            else:
                curve.setData([], [])

        # Set X-axis range to show visible data
        if len(visible_time) > 0:
            view_box = self.plot.getViewBox()
            view_box.enableAutoRange(axis='x', enable=False)
            x_min = visible_time[0]
            x_max = visible_time[-1]
            # Add small padding to prevent edge clipping
            padding = (x_max - x_min) * 0.02 if x_max > x_min else 0.1
            view_box.setXRange(x_min - padding, x_max + padding, padding=0)

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
