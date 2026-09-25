from __future__ import annotations

import codecs
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPointF, QProcess, QRectF, QTimer, QUrl, Signal, Slot, Qt
from PySide6.QtGui import QColor, QCloseEvent, QMouseEvent, QPainter, QPainterPath, QPen, QResizeEvent
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QFrame, QHBoxLayout, QLabel, QSizeGrip,
    QVBoxLayout, QWidget,
)


TERMINAL_DARK_STYLE = """
#terminalWindow { background: #0D1117; color: #C9D1D9; }
#terminalTitleBar { background: #161B22; border-bottom: 1px solid #30363D; }
#terminalTitle { color: #F0F6FC; font-size: 13px; font-weight: 700; }
#terminalDevice { background: #153C32; color: #6EE7B7; border: 1px solid #245B57; border-radius: 5px; padding: 3px 9px; }
"""

TERMINAL_LIGHT_STYLE = """
#terminalWindow { background: #FFFFFF; color: #24292F; }
#terminalTitleBar { background: #FFFFFF; border-bottom: 1px solid #E5E7EB; }
#terminalTitle { color: #111827; font-size: 13px; font-weight: 700; }
#terminalDevice { background: #F0FDFA; color: #0F8F83; border: 1px solid #CCFBF1; border-radius: 5px; padding: 3px 9px; }
"""


def terminal_asset_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    return base / "assets" / "terminal" / "index.html"


class TerminalBridge(QObject):
    output = Signal(str)
    themeChanged = Signal(str)
    resetRequested = Signal()
    focusRequested = Signal()
    pasteRequested = Signal(str)

    def __init__(self, window: "DeviceTerminalWindow") -> None:
        super().__init__(window)
        self.window = window

    @Slot(str)
    def sendInput(self, data: str) -> None:
        self.window.write_input(data)

    @Slot(int, int)
    def resizeTerminal(self, columns: int, rows: int) -> None:
        self.window.set_terminal_size(columns, rows)

    @Slot(int, int)
    def terminalReady(self, columns: int, rows: int) -> None:
        self.window.terminal_ready(columns, rows)

    @Slot(str)
    def copyText(self, text: str) -> None:
        QApplication.clipboard().setText(text)

    @Slot()
    def requestPaste(self) -> None:
        self.pasteRequested.emit(QApplication.clipboard().text())


class TitleBarButton(QAbstractButton):
    """Small circular title-bar action matching Escrcpy's AppControls."""

    def __init__(self, kind: str, tooltip: str, callback, parent=None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.dark = False
        self.setFixedSize(30, 30)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(tooltip)
        self.clicked.connect(callback)

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.update()

    def set_theme(self, theme: str) -> None:
        self.dark = theme == "dark"
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hovered = self.underMouse()
        pressed = self.isDown()

        if hovered:
            if self.kind == "close":
                background = QColor("#EF4444" if not pressed else "#F87171")
            elif self.dark:
                background = QColor("#30363D" if not pressed else "#374151")
            else:
                background = QColor("#E5E7EB" if not pressed else "#D1D5DB")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawEllipse(QRectF(0, 0, self.width(), self.height()))

        foreground = QColor("#FFFFFF") if hovered and self.kind == "close" else QColor("#C9D1D9" if self.dark else "#4B5563")
        pen = QPen(foreground, 1.35)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if self.kind == "minimize":
            painter.drawLine(QPointF(10, 16), QPointF(20, 16))
        elif self.kind == "maximize":
            painter.drawRect(QRectF(10, 10, 10, 10))
        elif self.kind == "restore":
            painter.drawRect(QRectF(9, 11, 9, 9))
            painter.drawLine(QPointF(12, 9), QPointF(21, 9))
            painter.drawLine(QPointF(21, 9), QPointF(21, 18))
            painter.drawLine(QPointF(18, 11), QPointF(18, 9))
            painter.drawLine(QPointF(21, 18), QPointF(18, 18))
        elif self.kind == "close":
            painter.drawLine(QPointF(11, 11), QPointF(19, 19))
            painter.drawLine(QPointF(19, 11), QPointF(11, 19))
        elif self.kind == "refresh":
            arc_rect = QRectF(9, 9, 12, 12)
            painter.drawArc(arc_rect, 35 * 16, 285 * 16)
            path = QPainterPath(QPointF(19.6, 8.8))
            path.lineTo(QPointF(20.2, 13.0))
            path.lineTo(QPointF(16.3, 11.6))
            painter.setBrush(foreground)
            painter.drawPath(path)


class ThemeSwitch(QAbstractButton):
    """Compact sun/moon switch used by Escrcpy's terminal header."""

    def __init__(self, callback, parent=None) -> None:
        super().__init__(parent)
        self.dark = False
        self.setCheckable(True)
        self.setFixedSize(38, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("切换日间/夜间模式")
        self.clicked.connect(callback)

    def set_theme(self, theme: str) -> None:
        self.dark = theme == "dark"
        self.setChecked(self.dark)
        self.setToolTip("切换到日间模式" if self.dark else "切换到夜间模式")
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QColor("#374151" if self.dark else "#DDE2EA")
        if self.underMouse():
            track = QColor("#4B5563" if self.dark else "#CDD3DD")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0, 1, 38, 20), 10, 10)

        center = QPointF(27 if self.dark else 11, 11)
        painter.setBrush(QColor("#111827" if self.dark else "#FFFFFF"))
        painter.drawEllipse(center, 8, 8)

        icon_color = QColor("#F8FAFC" if self.dark else "#4B5563")
        painter.setPen(QPen(icon_color, 1.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.dark:
            # Build a closed crescent from two circles.  The previous open
            # Bezier path left the upper-right edge missing and made the moon
            # look clipped inside the switch thumb.
            outer = QPainterPath()
            outer.addEllipse(center, 4.8, 4.8)
            cutout = QPainterPath()
            cutout.addEllipse(QPointF(center.x() + 2.5, center.y() - 1.5), 4.3, 4.3)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(icon_color)
            painter.drawPath(outer.subtracted(cutout))
        else:
            painter.drawEllipse(center, 2.2, 2.2)
            for dx, dy in ((0, -5), (0, 5), (-5, 0), (5, 0), (-3.6, -3.6), (3.6, 3.6), (3.6, -3.6), (-3.6, 3.6)):
                start = QPointF(center.x() + dx * 0.72, center.y() + dy * 0.72)
                end = QPointF(center.x() + dx, center.y() + dy)
                painter.drawLine(start, end)


class TerminalTitleBar(QFrame):
    def __init__(self, window: "DeviceTerminalWindow", device_label: str) -> None:
        super().__init__(window)
        self.window = window
        self.drag_offset: QPoint | None = None
        self.setObjectName("terminalTitleBar")
        self.setFixedHeight(40)
        layout = QHBoxLayout(self); layout.setContentsMargins(8, 4, 8, 4); layout.setSpacing(16)

        title = QLabel("设备终端"); title.setObjectName("terminalTitle"); title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); layout.addWidget(title)
        device = QLabel(device_label); device.setObjectName("terminalDevice"); device.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); layout.addWidget(device)
        layout.addStretch()

        self.refresh_button = TitleBarButton("refresh", "重新连接当前设备终端", self.window.restart_session, self)
        self.theme_button = ThemeSwitch(self.window.toggle_theme, self)
        self.minimize_button = TitleBarButton("minimize", "最小化", self.window.showMinimized, self)
        self.maximize_button = TitleBarButton("maximize", "最大化", self.window.toggle_maximized, self)
        self.close_button = TitleBarButton("close", "关闭", self.window.close, self)
        controls = QWidget(self)
        controls_layout = QHBoxLayout(controls); controls_layout.setContentsMargins(0, 0, 0, 0); controls_layout.setSpacing(8)
        for button in (self.refresh_button, self.theme_button, self.minimize_button, self.maximize_button, self.close_button):
            controls_layout.addWidget(button)
        layout.addWidget(controls)

    def set_theme(self, theme: str) -> None:
        for button in (self.refresh_button, self.minimize_button, self.maximize_button, self.close_button):
            button.set_theme(theme)
        self.theme_button.set_theme(theme)

    def update_window_state(self) -> None:
        maximized = self.window.isMaximized()
        self.maximize_button.set_kind("restore" if maximized else "maximize")
        self.maximize_button.setToolTip("还原" if maximized else "最大化")
        self.window.size_grip.setVisible(not maximized)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self.window.isMaximized():
            handle = self.window.windowHandle()
            if handle and handle.startSystemMove():
                event.accept()
                return
            self.drag_offset = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window.move(event.globalPosition().toPoint() - self.drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.window.toggle_maximized()
        super().mouseDoubleClickEvent(event)


class DeviceTerminalWindow(QWidget):
    closed = Signal(object)
    theme_change_requested = Signal(str)

    def __init__(self, adb_path: str, serial: str, device_name: str, theme: str = "light", parent=None) -> None:
        # This must be a real top-level window. Giving it the main window as a
        # parent makes Windows treat it as an owned dialog: it then has no
        # independent taskbar presence and frameless maximize can immediately
        # bounce back to the owner window.
        super().__init__(None)
        self.adb_path = adb_path
        self.serial = serial
        self.device_name = device_name or serial
        self.theme = "dark" if theme == "dark" else "light"
        self.process: QProcess | None = None
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.pending_output: list[str] = []
        self.web_ready = False
        self.closing = False
        self.restart_pending = False
        self.columns = 80
        self.rows = 24

        self.setObjectName("terminalWindow")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle(f"设备终端 · {self.device_name}[{serial}]")
        self.setMinimumSize(680, 400)
        self.resize(1000, 640)
        self._build_ui()
        self.set_theme(self.theme)
        self._start_process()

    @property
    def device_label(self) -> str:
        return f"{self.device_name}[{self.serial}]"

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        self.title_bar = TerminalTitleBar(self, self.device_label); layout.addWidget(self.title_bar)

        self.web_view = QWebEngineView(self)
        self._set_web_background(self.theme)
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.bridge = TerminalBridge(self)
        self.channel = QWebChannel(self.web_view.page())
        self.channel.registerObject("terminalBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        terminal_url = QUrl.fromLocalFile(str(terminal_asset_path()))
        terminal_url.setQuery(f"theme={self.theme}")
        self.web_view.setUrl(terminal_url)
        layout.addWidget(self.web_view, 1)

        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(14, 14)

    def _start_process(self) -> None:
        if self.closing:
            return
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        process = QProcess(self)
        process.setProgram(self.adb_path)
        process.setArguments(["-s", self.serial, "shell", "-tt"])
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(lambda p=process: self._read_output(p))
        process.finished.connect(lambda code, status, p=process: self._process_finished(p, code, status))
        process.errorOccurred.connect(lambda error, p=process: self._process_error(p, error))
        self.process = process
        self.restart_pending = False
        process.start()

    def _read_output(self, process: QProcess) -> None:
        if process is not self.process:
            return
        text = self.decoder.decode(bytes(process.readAllStandardOutput()))
        if text:
            self.write_terminal(text)

    def write_input(self, data: str) -> None:
        if not self.process or self.process.state() == QProcess.ProcessState.NotRunning:
            return
        if sys.platform == "win32" and data == "\r":
            data = "\r\n"
        self.process.write(data.encode("utf-8"))

    def write_terminal(self, text: str) -> None:
        if self.web_ready:
            self.bridge.output.emit(text)
        else:
            self.pending_output.append(text)

    def terminal_ready(self, columns: int, rows: int) -> None:
        self.web_ready = True
        self.columns, self.rows = columns, rows
        self.bridge.themeChanged.emit(self.theme)
        for text in self.pending_output:
            self.bridge.output.emit(text)
        self.pending_output.clear()
        self.bridge.focusRequested.emit()

    def set_terminal_size(self, columns: int, rows: int) -> None:
        self.columns, self.rows = columns, rows
        # adb shell -tt does not expose a host-side SIGWINCH/resize channel.

    def restart_session(self) -> None:
        self.bridge.resetRequested.emit()
        self.pending_output.clear()
        self.restart_pending = True
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
        else:
            self._start_process()

    def _process_error(self, process: QProcess, _error) -> None:
        if not self.closing and process is self.process:
            self.write_terminal(f"\r\n\x1b[31m无法启动终端：{process.errorString()}\x1b[0m\r\n")

    def _process_finished(self, process: QProcess, exit_code: int, _status) -> None:
        if self.closing or process is not self.process:
            return
        tail = self.decoder.decode(b"", final=True)
        if tail:
            self.write_terminal(tail)
        if self.restart_pending:
            QTimer.singleShot(0, self._start_process)
            return
        self.write_terminal(f"\r\n\x1b[33m进程已退出，退出码 {exit_code}。点击刷新按钮重新连接。\x1b[0m\r\n")

    def set_theme(self, theme: str) -> None:
        self.theme = "dark" if theme == "dark" else "light"
        self.setStyleSheet(TERMINAL_DARK_STYLE if self.theme == "dark" else TERMINAL_LIGHT_STYLE)
        if hasattr(self, "web_view"):
            self._set_web_background(self.theme)
        if hasattr(self, "bridge"):
            self.bridge.themeChanged.emit(self.theme)
        if hasattr(self, "title_bar"):
            self.title_bar.set_theme(self.theme)

    def _set_web_background(self, theme: str) -> None:
        """Keep Chromium's pre-DOM surface aligned with the Shell theme."""
        color = "#0D1117" if theme == "dark" else "#FFFFFF"
        self.web_view.page().setBackgroundColor(QColor(color))
        self.web_view.setStyleSheet(f"background: {color}; border: none;")

    def toggle_theme(self) -> None:
        theme = "light" if self.theme == "dark" else "dark"
        self.set_theme(theme)
        self.theme_change_requested.emit(theme)

    def toggle_maximized(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()
        self.title_bar.update_window_state()

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.size_grip.move(self.width() - self.size_grip.width(), self.height() - self.size_grip.height())
        self.size_grip.raise_()
        super().resizeEvent(event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "title_bar"):
            self.title_bar.update_window_state()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.closing = True
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(500)
        self.closed.emit(self)
        super().closeEvent(event)
