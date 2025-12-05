import time
import math
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


class AdvancedSettingsDialog(QDialog):
    """Dialog for configuring advanced plotter settings"""

    def __init__(self, current_use_fixed, current_rate, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Settings")
        self.setModal(True)
        self.resize(350, 200)

        # Store current values
        self.use_fixed_timing = current_use_fixed
        self.sampling_rate_hz = current_rate

        self._setup_ui()

    def _setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout(self)

        # Timing mode section
        timing_label = QLabel("Timing Mode:")
        layout.addWidget(timing_label)

        # Checkbox for fixed timing
        self.fixed_timing_checkbox = QPushButton()
        self.fixed_timing_checkbox.setCheckable(True)
        self.fixed_timing_checkbox.setChecked(self.use_fixed_timing)
        self.fixed_timing_checkbox.setText("Use Fixed Sampling Rate")
        self.fixed_timing_checkbox.toggled.connect(self._on_checkbox_toggled)
        layout.addWidget(self.fixed_timing_checkbox)

        # Hint label
        hint_label = QLabel("(for smooth visualization)")
        hint_label.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(hint_label)

        layout.addSpacing(10)

        # Sampling rate input
        rate_container = QWidget()
        rate_layout = QHBoxLayout(rate_container)
        rate_layout.setContentsMargins(0, 0, 0, 0)

        rate_layout.addWidget(QLabel("Sampling Rate:"))

        self.rate_input = QLineEdit(f"{self.sampling_rate_hz:.1f}")
        self.rate_input.setMaximumWidth(80)
        self.rate_input.setValidator(QIntValidator(1, 10000))
        self.rate_input.setEnabled(self.use_fixed_timing)
        rate_layout.addWidget(self.rate_input)

        rate_layout.addWidget(QLabel("Hz"))
        rate_layout.addStretch()

        layout.addWidget(rate_container)

        layout.addSpacing(20)

        # OK/Cancel buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accepted)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_checkbox_toggled(self, checked):
        """Handle checkbox toggle"""
        self.rate_input.setEnabled(checked)

    def _on_accepted(self):
        """Handle OK button - validate and accept"""
        self.use_fixed_timing = self.fixed_timing_checkbox.isChecked()

        if self.use_fixed_timing:
            text = self.rate_input.text().strip()
            try:
                rate = float(text)
                if rate > 0:
                    self.sampling_rate_hz = rate
            except ValueError:
                pass  # Keep previous value if invalid

        self.accept()

    def get_settings(self):
        """Return (use_fixed_timing: bool, sampling_rate_hz: float)"""
        return self.use_fixed_timing, self.sampling_rate_hz


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

        # Zoom control with logarithmic mapping
        # Slider range: 1-100 (linear) → Zoom: 1.0x-50.0x (logarithmic)
        self.current_zoom_level = 1  # Default slider value (1 = 1.0x zoom)
        self.pending_zoom_level = self.current_zoom_level
        self.max_zoom_multiplier = 50  # Maximum zoom multiplier (50x)
        self.min_visible_points = 100  # Minimum points to display when zoomed in

        # Sampling rate configuration for fixed timing mode
        self.use_fixed_timing = True  # Default: enabled
        self.sampling_rate_hz = 250.0  # Default 250 Hz
        self.time_interval = 1.0 / 250.0  # 0.004 seconds
        self.synthetic_time = 0.0  # Cumulative synthetic time

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

        # Advanced settings button
        advanced_button = QPushButton("Advanced")
        advanced_button.clicked.connect(self._open_advanced_settings)
        layout.addWidget(advanced_button)

        layout.addSpacing(20)

        # Refresh rate selection
        layout.addWidget(QLabel("Plot Refresh Rate:"))
        self.refresh_rate_combo = QComboBox()
        self.refresh_rate_combo.addItems(["10 Hz", "20 Hz", "30 Hz", "60 Hz"])
        self.refresh_rate_combo.setCurrentIndex(2)  # Default 30 Hz
        self.refresh_rate_combo.currentIndexChanged.connect(self._on_refresh_rate_changed)
        layout.addWidget(self.refresh_rate_combo)

        layout.addSpacing(20)

        # Zoom control with logarithmic mapping
        layout.addWidget(QLabel("Zoom:"))

        # Zoom slider (linear 1-100, maps to logarithmic 1.0x-50.0x)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(1, 100)  # Linear slider range
        self.zoom_slider.setValue(self.current_zoom_level)
        self.zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        layout.addWidget(self.zoom_slider)

        # Zoom input box with "x" label (on second row)
        zoom_input_container = QWidget()
        zoom_input_layout = QHBoxLayout(zoom_input_container)
        zoom_input_layout.setContentsMargins(0, 0, 0, 0)

        # Display actual zoom multiplier (e.g., "1.0", "7.1", "50.0")
        initial_zoom = self._slider_to_zoom(self.current_zoom_level)
        self.zoom_input = QLineEdit(f"{initial_zoom:.1f}")
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
        """滑块值变化 → 转换为缩放倍数 → 更新输入框"""
        if not self.zoom_input:
            return

        # 转换为缩放倍数
        zoom = self._slider_to_zoom(value)

        # 更新输入框显示
        self.zoom_input.blockSignals(True)
        self.zoom_input.setText(f"{zoom:.1f}")
        self.zoom_input.blockSignals(False)

        self._schedule_zoom_update(value)

    @Slot()
    def _on_zoom_input_edited(self):
        """输入框编辑 → 解析缩放倍数 → 更新滑块"""
        if not self.zoom_slider or not self.zoom_input:
            return

        text = self.zoom_input.text().strip()
        try:
            zoom = float(text)
            zoom = max(1.0, min(self.max_zoom_multiplier, zoom))

            # 转换为滑块值
            slider_value = self._zoom_to_slider(zoom)

            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(slider_value)
            self.zoom_slider.blockSignals(False)

            # 更新显示
            self.zoom_input.setText(f"{zoom:.1f}")
            self._schedule_zoom_update(slider_value)

        except ValueError:
            # 无效输入，恢复当前值
            zoom = self._slider_to_zoom(self.zoom_slider.value())
            self.zoom_input.setText(f"{zoom:.1f}")

    def _slider_to_zoom(self, slider_value: int) -> float:
        """将线性滑块值转换为对数缩放倍数

        Args:
            slider_value: 滑块值（1-100）

        Returns:
            缩放倍数（1.0-50.0）
        """
        if slider_value <= 1:
            return 1.0

        # 对数映射：zoom = exp(ln(max_zoom) × (slider/100))
        log_max = math.log(self.max_zoom_multiplier)
        zoom = math.exp(log_max * slider_value / 100.0)

        return zoom

    def _zoom_to_slider(self, zoom: float) -> int:
        """将缩放倍数转换回滑块值

        Args:
            zoom: 缩放倍数（1.0-50.0）

        Returns:
            滑块值（1-100）
        """
        if zoom <= 1.0:
            return 1

        # 反向对数映射：slider = 100 × ln(zoom) / ln(max_zoom)
        log_max = math.log(self.max_zoom_multiplier)
        slider = int(100.0 * math.log(zoom) / log_max)

        return max(1, min(100, slider))

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

    @Slot()
    def _open_advanced_settings(self):
        """Open the advanced settings dialog"""
        dialog = AdvancedSettingsDialog(
            self.use_fixed_timing,
            self.sampling_rate_hz,
            parent=self
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            use_fixed, rate = dialog.get_settings()
            self._apply_timing_settings(use_fixed, rate)

    def _apply_timing_settings(self, use_fixed: bool, rate: float):
        """Apply timing settings from advanced dialog"""
        self.use_fixed_timing = use_fixed

        if use_fixed and rate > 0:
            self.sampling_rate_hz = rate
            self.time_interval = 1.0 / rate

        # Reset synthetic time when settings change
        self.synthetic_time = 0.0

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

        # Calculate time based on mode
        if self.use_fixed_timing and self.sampling_rate_hz > 0:
            # Use synthetic time for smooth visualization
            self.synthetic_time += self.time_interval
            current_time = self.synthetic_time
        else:
            # Use arrival time (original behavior)
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
        # Convert slider value (1-100) to zoom multiplier (1.0x-50.0x) using logarithmic mapping
        zoom_multiplier = self._slider_to_zoom(self.current_zoom_level)

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

        # Reset timing state
        self.start_time = time.time()
        self.synthetic_time = 0.0  # Reset synthetic time counter

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
