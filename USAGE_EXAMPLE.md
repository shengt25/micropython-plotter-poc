# Qt 原生版本使用示例

## 主要改动

### 1. DeviceManager
- ✅ 继承 `QObject`
- ✅ 使用 `Signal(object, object)` 替代回调函数
- ✅ 修复了 `is_connected()` 的线程安全问题
- ✅ 移除了 `on_state_change()` 方法

### 2. CodeRunner
- ✅ 继承 `QObject`
- ✅ 使用 `output_received` 和 `error_received` Signal
- ✅ 移除了 `on_output()` 和 `on_error()` 方法
- ✅ 修复了 import 路径问题

## 在 PySide UI 中使用

### 基本用法

```python
from PySide6.QtWidgets import QMainWindow, QTextEdit, QVBoxLayout, QWidget, QPushButton
from PySide6.QtCore import QThread
from src.worker.device_manager import DeviceManager, DeviceState
from src.worker.code_runner import CodeRunner


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # UI 组件
        self.console = QTextEdit()
        self.console.setReadOnly(True)

        # 创建 DeviceManager 和 CodeRunner
        self.device_manager = DeviceManager('/dev/cu.usbmodem11201')
        self.code_runner = CodeRunner(self.device_manager)

        # 连接 Signals 到 UI 更新（自动线程安全）
        self.device_manager.state_changed.connect(self.on_state_changed)
        self.code_runner.output_received.connect(self.on_output)
        self.code_runner.error_received.connect(self.on_error)

        # 连接设备
        self.device_manager.connect()

    def on_state_changed(self, old_state: DeviceState, new_state: DeviceState):
        """设备状态改变（在主线程执行）"""
        self.statusBar().showMessage(f"Device: {new_state.value}")

    def on_output(self, message: str):
        """接收输出消息（在主线程执行）"""
        self.console.append(f"[INFO] {message}")

    def on_error(self, error: str):
        """接收错误消息（在主线程执行）"""
        self.console.append(f"[ERROR] {error}")

    def run_code(self):
        """运行代码"""
        code = "print('Hello from MicroPython!')"
        self.code_runner.run_code(code)

    def closeEvent(self, event):
        """窗口关闭时断开连接"""
        self.device_manager.disconnect()
        event.accept()
```

### 在后台线程中使用（推荐）

```python
from PySide6.QtCore import QThread, Signal


class DeviceWorkerThread(QThread):
    """后台线程处理串口通信"""

    def __init__(self, port: str):
        super().__init__()
        self.port = port
        self.device_manager = None
        self.code_runner = None

    def run(self):
        # 在后台线程创建对象
        self.device_manager = DeviceManager(self.port)
        self.code_runner = CodeRunner(self.device_manager)

        # 连接设备
        if self.device_manager.connect():
            # 保持线程运行
            self.exec()

    def stop(self):
        if self.device_manager:
            self.device_manager.disconnect()
        self.quit()
        self.wait()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # 创建后台线程
        self.worker_thread = DeviceWorkerThread('/dev/cu.usbmodem11201')
        self.worker_thread.start()

        # 等待线程初始化（实际项目中用更优雅的方式）
        import time
        time.sleep(0.5)

        # 连接 Signals（跨线程安全）
        dm = self.worker_thread.device_manager
        runner = self.worker_thread.code_runner

        dm.state_changed.connect(self.on_state_changed)
        runner.output_received.connect(self.on_output)
        runner.error_received.connect(self.on_error)

    def closeEvent(self, event):
        self.worker_thread.stop()
        event.accept()
```

## 迁移指南（从旧版本）

### 旧版本（回调）
```python
# 旧代码
runner.on_output(lambda msg: print(msg))
runner.on_error(lambda msg: print(msg))
dm.on_state_change(lambda old, new: print(f"{old} -> {new}"))
```

### 新版本（Qt Signal）
```python
# 新代码
runner.output_received.connect(lambda msg: print(msg))
runner.error_received.connect(lambda msg: print(msg))
dm.state_changed.connect(lambda old, new: print(f"{old} -> {new}"))
```

## 注意事项

1. **线程安全**: Qt Signals 自动处理跨线程通信，不需要手动加锁
2. **UI 更新**: 连接到 Signal 的槽函数会在主线程执行，可以安全更新 UI
3. **对象生命周期**: `DeviceManager` 和 `CodeRunner` 都是 `QObject`，可以使用 Qt 的父子关系管理
4. **断开连接**: 使用 `disconnect()` 方法断开 Signal 连接（如果需要）

## 完整示例

参见 `src/worker/code_runner.py` 底部的示例代码。
