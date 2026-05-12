import json
import sys
import threading
import time
from pathlib import Path

from pynput.keyboard import GlobalHotKeys
from pynput.mouse import Button, Controller

try:
    from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal
    from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError:
    print("缺少 PySide6，请先运行：pip install -r requirements.txt")
    raise SystemExit(1)


CONFIG_PATH = Path(__file__).with_name("settings.json")
DEFAULT_CLICKS_PER_SECOND = 100
DEFAULT_TOGGLE_HOTKEY = "<f8>"
MIN_CLICKS_PER_SECOND = 1
MAX_CLICKS_PER_SECOND = 100


def clamp_clicks_per_second(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = DEFAULT_CLICKS_PER_SECOND
    return max(MIN_CLICKS_PER_SECOND, min(MAX_CLICKS_PER_SECOND, value))


def parse_region(value):
    if not isinstance(value, dict):
        return None
    try:
        x1 = int(value["x1"])
        y1 = int(value["y1"])
        x2 = int(value["x2"])
        y2 = int(value["y2"])
    except (KeyError, TypeError, ValueError):
        return None

    left = min(x1, x2)
    top = min(y1, y2)
    right = max(x1, x2)
    bottom = max(y1, y2)
    if left == right or top == bottom:
        return None
    return {"x1": left, "y1": top, "x2": right, "y2": bottom}


def load_settings():
    defaults = {
        "clicks_per_second": DEFAULT_CLICKS_PER_SECOND,
        "toggle_hotkey": DEFAULT_TOGGLE_HOTKEY,
        "region_enabled": True,
        "region": None,
    }
    if not CONFIG_PATH.exists():
        return defaults

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            raw_settings = json.load(file)
    except (OSError, json.JSONDecodeError):
        return defaults

    if not isinstance(raw_settings, dict):
        return defaults

    hotkey = str(raw_settings.get("toggle_hotkey", DEFAULT_TOGGLE_HOTKEY)).strip()
    return {
        "clicks_per_second": clamp_clicks_per_second(
            raw_settings.get("clicks_per_second", DEFAULT_CLICKS_PER_SECOND)
        ),
        "toggle_hotkey": hotkey or DEFAULT_TOGGLE_HOTKEY,
        "region_enabled": bool(raw_settings.get("region_enabled", True)),
        "region": parse_region(raw_settings.get("region")),
    }


def save_settings(settings):
    data = {
        "clicks_per_second": clamp_clicks_per_second(
            settings.get("clicks_per_second", DEFAULT_CLICKS_PER_SECOND)
        ),
        "toggle_hotkey": str(settings.get("toggle_hotkey", DEFAULT_TOGGLE_HOTKEY)).strip()
        or DEFAULT_TOGGLE_HOTKEY,
        "region_enabled": bool(settings.get("region_enabled", True)),
        "region": parse_region(settings.get("region")),
    }
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def region_to_text(region):
    if not region:
        return "未选择"
    return "({}, {}) 到 ({}, {})".format(
        region["x1"], region["y1"], region["x2"], region["y2"]
    )


def hotkey_to_text(hotkey):
    names = {
        "ctrl": "Ctrl",
        "alt": "Alt",
        "shift": "Shift",
        "cmd": "Win",
        "space": "Space",
        "esc": "Esc",
        "tab": "Tab",
        "enter": "Enter",
        "backspace": "Backspace",
        "delete": "Delete",
        "insert": "Insert",
        "home": "Home",
        "end": "End",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
    }
    parts = []
    for token in str(hotkey).split("+"):
        token = token.strip()
        if token.startswith("<") and token.endswith(">"):
            token = token[1:-1]
        parts.append(names.get(token, token.upper() if token.startswith("f") else token))
    return " + ".join(parts)


def build_hotkey_from_event(event):
    key = int(event.key())
    modifiers = event.modifiers()
    modifier_keys = {
        int(Qt.Key.Key_Control),
        int(Qt.Key.Key_Shift),
        int(Qt.Key.Key_Alt),
        int(Qt.Key.Key_Meta),
    }
    if key in modifier_keys:
        return None

    parts = []
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        parts.append("<ctrl>")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        parts.append("<alt>")
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        parts.append("<shift>")
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        parts.append("<cmd>")

    key_token = key_to_pynput_token(event)
    if not key_token:
        return None
    parts.append(key_token)
    return "+".join(parts)


def key_to_pynput_token(event):
    key = int(event.key())
    special_keys = {
        int(Qt.Key.Key_Escape): "<esc>",
        int(Qt.Key.Key_Space): "<space>",
        int(Qt.Key.Key_Tab): "<tab>",
        int(Qt.Key.Key_Return): "<enter>",
        int(Qt.Key.Key_Enter): "<enter>",
        int(Qt.Key.Key_Backspace): "<backspace>",
        int(Qt.Key.Key_Delete): "<delete>",
        int(Qt.Key.Key_Insert): "<insert>",
        int(Qt.Key.Key_Home): "<home>",
        int(Qt.Key.Key_End): "<end>",
        int(Qt.Key.Key_Up): "<up>",
        int(Qt.Key.Key_Down): "<down>",
        int(Qt.Key.Key_Left): "<left>",
        int(Qt.Key.Key_Right): "<right>",
    }
    for number in range(1, 25):
        special_keys[int(getattr(Qt.Key, f"Key_F{number}"))] = f"<f{number}>"

    if key in special_keys:
        return special_keys[key]

    if int(Qt.Key.Key_A) <= key <= int(Qt.Key.Key_Z):
        return chr(ord("a") + key - int(Qt.Key.Key_A))
    if int(Qt.Key.Key_0) <= key <= int(Qt.Key.Key_9):
        return chr(ord("0") + key - int(Qt.Key.Key_0))

    text = event.text().lower()
    if len(text) == 1 and text.isprintable() and not text.isspace():
        return text
    return None


class AppSignals(QObject):
    toggle_requested = Signal()
    click_error = Signal(str)


class SelectionOverlay(QWidget):
    region_selected = Signal(int, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.start_point = None
        self.end_point = None

        virtual_rect = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(virtual_rect)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.raise_()
        self.grabKeyboard()

    def closeEvent(self, event):
        self.releaseKeyboard()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.globalPosition().toPoint()
            self.end_point = self.start_point
            self.update()

    def mouseMoveEvent(self, event):
        if self.start_point is not None:
            self.end_point = event.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.start_point is None:
            return

        self.end_point = event.globalPosition().toPoint()
        selected = QRect(self.start_point, self.end_point).normalized()
        self.start_point = None
        self.end_point = None

        if selected.width() >= 3 and selected.height() >= 3:
            self.region_selected.emit(
                selected.left(), selected.top(), selected.right(), selected.bottom()
            )
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))

        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawText(
            self.rect().adjusted(20, 20, -20, -20),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            "拖拽选择连点区域，按 Esc 取消",
        )

        if self.start_point is None or self.end_point is None:
            return

        local_offset = self.geometry().topLeft()
        selection = QRect(self.start_point - local_offset, self.end_point - local_offset).normalized()
        painter.fillRect(selection, QColor(0, 120, 215, 70))
        painter.setPen(QPen(QColor(0, 120, 215), 2))
        painter.drawRect(selection)


class AutoClickerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.mouse = Controller()
        self.signals = AppSignals()
        self.hotkey_listener = None
        self.recording_hotkey = False
        self.enabled = False
        self.start_click_after = 0.0
        self.click_thread = None
        self.click_stop_event = threading.Event()
        self.click_lock = threading.Lock()
        self.overlay = None

        self.setWindowTitle("点到为止")
        self.setMinimumWidth(440)

        self.build_ui()
        self.bind_events()

        self.state_timer = QTimer(self)
        self.state_timer.setInterval(50)
        self.state_timer.timeout.connect(self.evaluate_click_state)
        self.state_timer.start()

        self.signals.toggle_requested.connect(self.toggle_enabled)
        self.signals.click_error.connect(self.handle_click_error)

        self.start_hotkey_listener()
        self.update_ui()

    def build_ui(self):
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)

        status_layout = QFormLayout()
        self.status_label = QLabel()
        self.region_label = QLabel()
        self.hotkey_label = QLabel()
        status_layout.addRow("运行状态：", self.status_label)
        status_layout.addRow("当前区域：", self.region_label)
        status_layout.addRow("切换快捷键：", self.hotkey_label)
        layout.addLayout(status_layout)

        self.region_checkbox = QCheckBox("启用矩形区域限制")
        self.region_checkbox.setChecked(bool(self.settings["region_enabled"]))
        layout.addWidget(self.region_checkbox)

        cps_layout = QFormLayout()
        self.cps_spinbox = QSpinBox()
        self.cps_spinbox.setRange(MIN_CLICKS_PER_SECOND, MAX_CLICKS_PER_SECOND)
        self.cps_spinbox.setSuffix(" 次/秒")
        self.cps_spinbox.setValue(self.settings["clicks_per_second"])
        cps_layout.addRow("点击频率：", self.cps_spinbox)
        layout.addLayout(cps_layout)

        action_layout = QHBoxLayout()
        self.toggle_button = QPushButton("开始")
        self.select_region_button = QPushButton("选择区域")
        self.record_hotkey_button = QPushButton("设置快捷键")
        self.exit_button = QPushButton("退出")
        action_layout.addWidget(self.toggle_button)
        action_layout.addWidget(self.select_region_button)
        action_layout.addWidget(self.record_hotkey_button)
        action_layout.addWidget(self.exit_button)
        layout.addLayout(action_layout)

        self.setCentralWidget(central)

    def bind_events(self):
        self.toggle_button.clicked.connect(self.toggle_enabled_from_button)
        self.select_region_button.clicked.connect(self.open_region_selector)
        self.record_hotkey_button.clicked.connect(self.begin_hotkey_recording)
        self.exit_button.clicked.connect(self.close)
        self.region_checkbox.toggled.connect(self.set_region_enabled)
        self.cps_spinbox.valueChanged.connect(self.set_clicks_per_second)

    def start_hotkey_listener(self):
        self.stop_hotkey_listener()
        hotkey = self.settings["toggle_hotkey"]
        try:
            listener = GlobalHotKeys({hotkey: self.signals.toggle_requested.emit})
            listener.start()
        except Exception as exc:
            self.hotkey_listener = None
            self.status_label.setText(f"快捷键注册失败：{exc}")
            return False

        self.hotkey_listener = listener
        return True

    def stop_hotkey_listener(self):
        if self.hotkey_listener is None:
            return
        try:
            self.hotkey_listener.stop()
        finally:
            self.hotkey_listener = None

    def begin_hotkey_recording(self):
        if self.recording_hotkey:
            return
        self.recording_hotkey = True
        self.stop_hotkey_listener()
        self.record_hotkey_button.setText("请按新的快捷键...")
        self.record_hotkey_button.setEnabled(False)
        self.status_label.setText("正在录制快捷键，按 Esc 取消")
        self.grabKeyboard()

    def finish_hotkey_recording(self):
        self.recording_hotkey = False
        self.releaseKeyboard()
        self.record_hotkey_button.setEnabled(True)
        self.record_hotkey_button.setText("设置快捷键")
        self.update_ui()

    def cancel_hotkey_recording(self):
        self.finish_hotkey_recording()
        self.start_hotkey_listener()

    def keyPressEvent(self, event):
        if not self.recording_hotkey:
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key.Key_Escape:
            self.cancel_hotkey_recording()
            return

        hotkey = build_hotkey_from_event(event)
        if not hotkey:
            QMessageBox.warning(self, "快捷键无效", "无法识别该快捷键，请重新设置。")
            return

        old_hotkey = self.settings["toggle_hotkey"]
        self.settings["toggle_hotkey"] = hotkey
        if self.start_hotkey_listener():
            self.save_current_settings()
            self.finish_hotkey_recording()
            return

        self.settings["toggle_hotkey"] = old_hotkey
        self.start_hotkey_listener()
        self.finish_hotkey_recording()
        QMessageBox.warning(self, "快捷键无效", "该快捷键无法注册，已恢复原快捷键。")

    def set_clicks_per_second(self, value):
        self.settings["clicks_per_second"] = clamp_clicks_per_second(value)
        self.save_current_settings()

    def set_region_enabled(self, checked):
        self.settings["region_enabled"] = bool(checked)
        if checked and self.enabled and not self.settings["region"]:
            self.enabled = False
            self.stop_actual_clicking()
            QMessageBox.information(self, "需要选择区域", "请先选择矩形区域。")
        self.save_current_settings()
        self.evaluate_click_state()
        self.update_ui()

    def open_region_selector(self):
        if self.enabled:
            self.enabled = False
            self.stop_actual_clicking()
            self.update_ui()

        self.overlay = SelectionOverlay(self)
        self.overlay.region_selected.connect(self.set_region)
        self.overlay.show()

    def set_region(self, x1, y1, x2, y2):
        self.settings["region"] = parse_region({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
        self.save_current_settings()
        self.update_ui()

    def toggle_enabled(self, start_delay=0.0):
        if self.recording_hotkey:
            return

        if not self.enabled and self.settings["region_enabled"] and not self.settings["region"]:
            QMessageBox.information(self, "需要选择区域", "请先选择矩形区域。")
            self.update_ui()
            return

        self.enabled = not self.enabled
        self.start_click_after = time.monotonic() + start_delay if self.enabled else 0.0
        if not self.enabled:
            self.stop_actual_clicking()
        self.evaluate_click_state()
        self.update_ui()

    def toggle_enabled_from_button(self):
        self.toggle_enabled(start_delay=0.25)

    def evaluate_click_state(self):
        if not self.enabled:
            self.stop_actual_clicking()
            self.update_ui()
            return

        if time.monotonic() < self.start_click_after:
            self.stop_actual_clicking()
            self.update_ui()
            return

        if not self.settings["region_enabled"]:
            self.start_actual_clicking()
            self.update_ui()
            return

        region = self.settings["region"]
        if not region:
            self.enabled = False
            self.stop_actual_clicking()
            self.update_ui()
            return

        x, y = self.mouse.position
        if self.point_in_region(x, y, region):
            self.start_actual_clicking()
        else:
            self.stop_actual_clicking()
        self.update_ui()

    def point_in_region(self, x, y, region):
        return region["x1"] <= x <= region["x2"] and region["y1"] <= y <= region["y2"]

    def start_actual_clicking(self):
        with self.click_lock:
            if self.click_thread is not None and self.click_thread.is_alive():
                return
            self.click_stop_event.clear()
            self.click_thread = threading.Thread(target=self.click_worker, daemon=True)
            self.click_thread.start()

    def stop_actual_clicking(self):
        with self.click_lock:
            thread = self.click_thread
            if thread is None:
                return
            self.click_stop_event.set()

        if thread.is_alive():
            thread.join(timeout=0.3)

        with self.click_lock:
            if self.click_thread is thread:
                self.click_thread = None

    def click_worker(self):
        while not self.click_stop_event.is_set():
            try:
                self.mouse.click(Button.left)
            except Exception as exc:
                self.signals.click_error.emit(str(exc))
                break

            interval = 1.0 / clamp_clicks_per_second(self.settings["clicks_per_second"])
            self.click_stop_event.wait(interval)

    def handle_click_error(self, message):
        self.enabled = False
        self.stop_actual_clicking()
        QMessageBox.warning(self, "点击失败", f"无法执行鼠标点击：{message}")
        self.update_ui()

    def is_actually_clicking(self):
        with self.click_lock:
            return self.click_thread is not None and self.click_thread.is_alive()

    def update_ui(self):
        if not hasattr(self, "status_label"):
            return

        self.region_checkbox.blockSignals(True)
        self.region_checkbox.setChecked(bool(self.settings["region_enabled"]))
        self.region_checkbox.blockSignals(False)

        self.region_label.setText(region_to_text(self.settings["region"]))
        self.hotkey_label.setText(hotkey_to_text(self.settings["toggle_hotkey"]))
        self.toggle_button.setText("停止" if self.enabled else "开始")

        if self.recording_hotkey:
            return
        if self.enabled and self.is_actually_clicking():
            self.status_label.setText("运行中：正在点击")
        elif self.enabled and self.settings["region_enabled"]:
            self.status_label.setText("已启用：等待鼠标进入区域")
        elif self.enabled:
            self.status_label.setText("已启用")
        else:
            self.status_label.setText("已停止")

    def save_current_settings(self):
        save_settings(self.settings)

    def closeEvent(self, event):
        self.enabled = False
        self.stop_actual_clicking()
        self.stop_hotkey_listener()
        self.save_current_settings()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = AutoClickerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
