import time
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QDialog, QFormLayout, QDialogButtonBox,
    QColorDialog, QComboBox, QSlider, QLineEdit
)
from PySide6.QtCore import Signal, Slot, QTimer, Qt
from PySide6.QtGui import QColor, QIntValidator
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
        self.max_points = 5000
        self.time_buffer = np.zeros(self.max_points, dtype=np.float64)
        self.channel_buffers = np.zeros((5, self.max_points), dtype=np.float32)
        self.channel_valid_mask = np.zeros((5, self.max_points), dtype=bool)
        self._buffer_size = 0
        self._write_index = 0
        self.start_time = time.time()

        # Statistics
        self.packet_count = 0

        # Refresh rate and pause control
        self.is_paused = False
        self.refresh_rates = [10, 20, 30, 60]  # Hz
        self.current_refresh_rate = 30  # Default 30 Hz

        # Zoom control (10 = 1.0x, 15 = 1.5x, 20 = 2.0x, etc.)
        # Slider uses 10x scale to support 0.1x precision
        self.current_zoom_level = 10  # Default 1.0x (show all data), slider value
        self.pending_zoom_level = self.current_zoom_level
        self.min_visible_points = 100  # Minimum points to display when zoomed in

        # UI components (will be created in _setup_ui)
        self.channel_names = self.default_labels.copy()
        self.active_channel_count = len(self.default_labels)
        self.curves = []
        self.stats_text = None
        self.ui_timer = None
        self.view_box = None  # Cached ViewBox reference
        self.zoom_slider = None
        self.zoom_input = None
        self.zoom_change_timer = None

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

        # Debounce timer for zoom level updates
        self.zoom_change_timer = QTimer(self)
        self.zoom_change_timer.setSingleShot(True)
        self.zoom_change_timer.setInterval(300)
        self.zoom_change_timer.timeout.connect(self._apply_zoom_level)

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

        # Configure ViewBox and cache reference for performance
        view_box = self.plot.getViewBox()
        view_box.setAutoVisible(x=True, y=True)  # Visible data only
        view_box.enableAutoRange(axis='y', enable=True)  # Auto-range Y
        view_box.setMouseEnabled(x=False, y=True)  # Disable mouse drag on X

        # Cache ViewBox reference to avoid repeated lookups
        self.view_box = view_box

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
        layout.addWidget(title_label)

        # Color settings button
        color_button = QPushButton("Colors")
        color_button.clicked.connect(self._open_color_settings)
        layout.addWidget(color_button)

        layout.addSpacing(20)

        # Refresh rate selection
        layout.addWidget(QLabel("Plot Refresh Rate:"))
        self.refresh_rate_combo = QComboBox()
        self.refresh_rate_combo.addItems(["10 Hz", "20 Hz", "30 Hz", "60 Hz"])
        self.refresh_rate_combo.setCurrentIndex(2)  # Default 30 Hz
        self.refresh_rate_combo.currentIndexChanged.connect(self._on_refresh_rate_changed)
        layout.addWidget(self.refresh_rate_combo)

        layout.addSpacing(20)

        # Zoom control
        layout.addWidget(QLabel("Zoom:"))

        # Calculate max zoom based on min visible points
        # If buffer is 5000 points and min is 100, max zoom = 5000/100 = 50x
        # Slider uses 10x scale: 10 = 1.0x, 500 = 50.0x
        max_zoom_multiplier = max(1, int(self.max_points / self.min_visible_points))
        self.max_zoom = max_zoom_multiplier * 10  # Convert to slider scale (e.g., 500 for 50x)

        # Zoom slider (full width on first row)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, self.max_zoom)  # 1.0x (10) to max (e.g., 50.0x = 500)
        self.zoom_slider.setValue(self.current_zoom_level)
        self.zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        layout.addWidget(self.zoom_slider)

        # Zoom input box with "x" label (on second row)
        zoom_input_container = QWidget()
        zoom_input_layout = QHBoxLayout(zoom_input_container)
        zoom_input_layout.setContentsMargins(0, 0, 0, 0)

        # Display as decimal (e.g., "1.0", "2.5", "10.0")
        self.zoom_input = QLineEdit(f"{self.current_zoom_level / 10:.1f}")
        self.zoom_input.setMaximumWidth(60)
        self.zoom_input.editingFinished.connect(self._on_zoom_input_edited)
        zoom_input_layout.addWidget(self.zoom_input)

        zoom_x_label = QLabel("x")
        zoom_input_layout.addWidget(zoom_x_label)

        zoom_input_layout.addStretch()  # Push to left

        layout.addWidget(zoom_input_container)
        layout.addSpacing(10)

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

        # Track last time statistics were updated (lazy update inside update_ui)
        self._last_stats_update = 0.0

    def _update_x_range(self, visible_time):
        """Update X-axis display range for visible data"""
        if len(visible_time) > 0:
            self.view_box.enableAutoRange(axis='x', enable=False)
            x_min = visible_time[0]
            x_max = visible_time[-1]
            # Add small padding to prevent edge clipping
            padding = (x_max - x_min) * 0.02 if x_max > x_min else 0.1
            self.view_box.setXRange(x_min - padding, x_max + padding, padding=0)

    def _update_legend(self):
        """Recreate all curves to update legend with correct names/colors"""
        # Remove all existing curves (this also removes them from legend)
        for curve in self.curves:
            self.plot.removeItem(curve)

        # Clear curves list
        self.curves.clear()

        # Recreate all curves in order (0 to target_count)
        target_count = max(0, min(self.active_channel_count, len(self.curve_colors)))
        for i in range(target_count):
            current_name = self.channel_names[i] if i < len(self.channel_names) else f"Channel {i + 1}"
            if not current_name:
                current_name = f"Channel {i + 1}"

            # Create new curve (automatically added to legend)
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
    def _on_zoom_slider_changed(self, value):
        """Handle slider movement for zoom level"""
        if not self.zoom_input:
            return
        self._update_zoom_input(value)
        self._schedule_zoom_update(value)

    @Slot()
    def _on_zoom_input_edited(self):
        """Handle manual numeric entry for zoom level (supports decimals)"""
        if not self.zoom_slider or not self.zoom_input:
            return

        text = self.zoom_input.text().strip()
        if not text:
            value = self.zoom_slider.value()
        else:
            try:
                # Parse as float (e.g., "1.5", "2.0", "10.5")
                zoom_float = float(text)
                # Convert to slider scale (multiply by 10)
                value = int(zoom_float * 10)
            except ValueError:
                value = self.zoom_slider.value()

        # Clamp to valid range (10 = 1.0x, max_zoom = e.g., 500 = 50.0x)
        value = max(10, min(self.max_zoom, value))

        if value != self.zoom_slider.value():
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(value)
            self.zoom_slider.blockSignals(False)

        self._update_zoom_input(value)
        self._schedule_zoom_update(value)

    def _update_zoom_input(self, value: int):
        """Update zoom input field with new value (display as decimal)"""
        if not self.zoom_input:
            return
        # Convert slider value to display value (e.g., 10 -> "1.0", 25 -> "2.5")
        zoom_display = value / 10.0
        new_text = f"{zoom_display:.1f}"
        current_text = self.zoom_input.text()
        if current_text == new_text:
            return
        self.zoom_input.blockSignals(True)
        self.zoom_input.setText(new_text)
        self.zoom_input.blockSignals(False)

    def _schedule_zoom_update(self, zoom_level: int):
        """Schedule zoom level update with debouncing"""
        self.pending_zoom_level = zoom_level
        if self.zoom_change_timer:
            self.zoom_change_timer.start()

    def _apply_zoom_level(self):
        """Apply pending zoom level (called after debounce timer)"""
        self.current_zoom_level = self.pending_zoom_level

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

        # Write index where new sample should be stored
        idx = self._write_index
        self.time_buffer[idx] = current_time
        self.channel_valid_mask[:, idx] = False

        # Store provided channel values
        for channel_index, val in enumerate(values[:5]):
            self.channel_buffers[channel_index, idx] = val
            self.channel_valid_mask[channel_index, idx] = True

        # Advance circular buffer pointers
        self._write_index = (idx + 1) % self.max_points
        if self._buffer_size < self.max_points:
            self._buffer_size += 1

        self.packet_count += 1

    def update_ui(self):
        """Update curves (called by timer at configured Hz)"""
        if self._buffer_size == 0:
            return

        # Calculate visible points based on zoom level
        # current_zoom_level is slider value: 10 = 1.0x, 15 = 1.5x, 20 = 2.0x, etc.
        # Convert to actual multiplier
        zoom_multiplier = self.current_zoom_level / 10.0

        if zoom_multiplier > 1.0:
            visible_count = max(
                self.min_visible_points,
                int(self._buffer_size / zoom_multiplier)
            )
        else:
            visible_count = self._buffer_size  # 1.0x = show all

        start_index = (self._write_index - visible_count) % self.max_points
        indices = (start_index + np.arange(visible_count)) % self.max_points
        visible_time = self.time_buffer[indices]

        # Update each curve with visible data using masks to skip missing samples
        for channel_index, curve in enumerate(self.curves):
            mask = self.channel_valid_mask[channel_index, indices]
            if not np.any(mask):
                curve.setData([], [])
                continue

            channel_values = self.channel_buffers[channel_index, indices][mask]
            curve.setData(visible_time[mask], channel_values)

        # Update X-axis range using cached ViewBox reference
        self._update_x_range(visible_time)

        # Update statistics roughly once per second
        self._maybe_update_stats()

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

    def _maybe_update_stats(self):
        """Throttle statistics updates to avoid redundant label refreshes"""
        now = time.time()
        if now - self._last_stats_update >= 1.0:
            self._last_stats_update = now
            self._update_stats()

    def showEvent(self, event):
        """Handle window show event - restart timer when window reopens"""
        super().showEvent(event)

        # Restart timer if it was stopped
        if self.ui_timer and not self.ui_timer.isActive():
            self.ui_timer.start(50)

    def closeEvent(self, event):
        """Handle window close event"""
        # Stop timers
        if self.ui_timer:
            self.ui_timer.stop()

        # Emit closed signal
        self.closed.emit()

        # Accept the close event
        event.accept()
