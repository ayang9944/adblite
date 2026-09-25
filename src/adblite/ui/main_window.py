from __future__ import annotations

import codecs
import ctypes
import shlex
import subprocess
import ipaddress
import json
import re
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QProcess, QRect, QSize, QTimer, Signal, Slot, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QHeaderView, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QSpinBox, QStackedWidget, QSplitter, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTabBar, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from ..domain import ConnectionHistory, CustomCommand, Device, merge_device_statuses
from ..infrastructure import AdbClient, BinaryResolver, ProcessRunner, SettingsRepository
from ..terminal import TerminalLogState, flush_terminal_log, render_terminal_log
from .terminal_window import DeviceTerminalWindow

GITHUB_PROJECT_URL = "https://github.com/ayang9944/adblite"
APP_VERSION = "0.2.0"


def split_local_process_arguments(argument_text: str) -> list[str]:
    """Parse arguments exactly as a native Windows process receives them."""
    if not argument_text.strip():
        return []
    if sys.platform != "win32":
        return shlex.split(argument_text, posix=False)

    # CommandLineToArgvW treats argv[0] differently from all other arguments,
    # so prepend a harmless placeholder and discard it after parsing.
    command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
    command_line_to_argv.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    command_line_to_argv.restype = ctypes.POINTER(ctypes.c_wchar_p)
    local_free = ctypes.windll.kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p

    argument_count = ctypes.c_int()
    argument_values = command_line_to_argv(
        f"placeholder.exe {argument_text}", ctypes.byref(argument_count),
    )
    if not argument_values:
        raise ctypes.WinError()
    try:
        return [argument_values[index] for index in range(1, argument_count.value)]
    finally:
        local_free(argument_values)


def interface_icon(name: str) -> QIcon:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    return QIcon(str(base / "assets" / "icons" / f"{name}.svg"))

DARK_STYLE = """
* { font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 13px; }
QMainWindow, QWidget { background: #111827; color: #E5E7EB; }
#topbar { background: #151D2B; border-bottom: 1px solid #273449; }
#brandName { color: #F8FAFC; font-size: 17px; font-weight: 700; padding-right: 12px; }
#navTabs { background: transparent; border: none; }
#navTabs::tab { background: transparent; color: #94A3B8; border: none; padding: 17px 14px 14px; }
#navTabs::tab:hover { color: #E2E8F0; background: #1C2738; }
#navTabs::tab:selected { color: #2DD4BF; font-weight: 600; border-bottom: 2px solid #14B8A6; }
#pageTitle { color: #F8FAFC; font-size: 20px; font-weight: 700; }
#pageHint, #mutedLabel { color: #94A3B8; font-size: 12px; }
#countBadge { background: #183B3A; color: #5EEAD4; border-radius: 10px; padding: 2px 8px; font-weight: 600; }
#primaryButton { background: #0F8F83; border-color: #14B8A6; color: white; font-weight: 600; }
#primaryButton:hover { background: #0D9488; }
#dangerButton { color: #FDA4AF; }
#statusLabel { background: #172033; border: 1px solid #2B3950; border-radius: 6px; padding: 7px 10px; color: #93C5FD; }
#onlineBadge { background: transparent; color: #6EE7B7; padding: 3px 9px; font-weight: 600; }
#warningBadge { background: transparent; color: #FCD34D; padding: 3px 9px; font-weight: 600; }
#offlineBadge { background: transparent; color: #94A3B8; padding: 3px 9px; font-weight: 600; }
#connectionBar { background: #151F2E; border: 1px solid #2B3950; border-radius: 9px; }
#emptyPanel { background: #141D2B; border: 1px solid #2B3950; border-radius: 9px; }
#emptyTitle { color: #E2E8F0; font-size: 16px; font-weight: 600; }
#terminalHeader { background: #151D2B; border-bottom: 1px solid #273449; }
#terminalDevice { background: #183B3A; color: #5EEAD4; border: 1px solid #245B57; border-radius: 5px; padding: 4px 9px; }
#terminalSurface { background: #0B1220; color: #DCE7F5; border: none; border-radius: 0; padding: 10px; selection-background-color: #0F766E; font-family: Consolas, "Cascadia Mono", monospace; font-size: 13px; }
QComboBox, QLineEdit, QSpinBox, QPlainTextEdit, QListWidget { background: #182235; border: 1px solid #334155; border-radius: 6px; padding: 7px; color: #E5E7EB; }
QComboBox { min-height: 22px; }
QComboBox:hover, QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus { border-color: #14B8A6; }
QPushButton, QToolButton { background: #223046; border: 1px solid #3B4A61; border-radius: 6px; padding: 7px 12px; color: #E5E7EB; }
QPushButton:hover, QToolButton:hover { background: #2C405B; border-color: #2DD4BF; }
QPushButton:disabled, QToolButton:disabled { color: #64748B; background: #1A2434; border-color: #2B3950; }
#iconButton, #rowAction { background: transparent; border: none; border-radius: 16px; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; padding: 0; }
#iconButton:hover, #rowAction:hover { background: #183B3A; border-color: #245B57; }
#rowAction::menu-indicator { image: none; width: 0; }
#shellPrompt { color: #5EEAD4; font-family: Consolas, "Cascadia Mono", monospace; font-size: 15px; font-weight: 700; min-width: 16px; }
#projectLink { color: #2DD4BF; }
QGroupBox { border: 1px solid #2B3950; border-radius: 8px; margin-top: 12px; padding: 14px 10px 10px; font-weight: 600; color: #CBD5E1; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; background: #111827; }
QListWidget::item { padding: 9px 8px; border-radius: 5px; }
QListWidget::item:selected { background: #0F766E; color: white; }
#deviceTable { background: #121B29; border: 1px solid #2B3950; border-radius: 8px; gridline-color: #263449; selection-background-color: transparent; selection-color: #5EEAD4; }
#deviceTable::item { background: transparent; padding: 8px; border-bottom: 1px solid #263449; }
#deviceTable::item:selected { background: transparent; color: #E5E7EB; }
#deviceIdentifierCell, #deviceStatusCell, #deviceActionsCell { background: transparent; }
#deviceIdentifierCell QLabel { background: transparent; }
QHeaderView::section { background: #172131; color: #94A3B8; border: none; border-bottom: 1px solid #2B3950; padding: 9px; font-weight: 600; }
QSplitter::handle { background: #334155; height: 5px; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #475569; border-radius: 5px; min-height: 25px; }
QPlainTextEdit { font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; }
QStatusBar { background: #0F172A; color: #94A3B8; border-top: 1px solid #273449; }
"""

LIGHT_STYLE = DARK_STYLE
for _dark, _light in (
    ("#111827", "#F5F7FA"), ("#151D2B", "#FFFFFF"), ("#273449", "#E5E7EB"),
    ("#F8FAFC", "#1F2937"), ("#94A3B8", "#6B7280"), ("#E2E8F0", "#374151"),
    ("#1C2738", "#F0FDFA"), ("#172033", "#F0FDFA"), ("#2B3950", "#E5E7EB"),
    ("#151F2E", "#FFFFFF"), ("#141D2B", "#FFFFFF"), ("#182235", "#FFFFFF"),
    ("#334155", "#CBD5E1"), ("#223046", "#FFFFFF"), ("#3B4A61", "#CBD5E1"),
    ("#2C405B", "#F0FDFA"), ("#1A2434", "#F3F4F6"), ("#121B29", "#FFFFFF"),
    ("#263449", "#EEF0F3"), ("#172131", "#F8FAFC"), ("#0F172A", "#F8FAFC"),
):
    LIGHT_STYLE = LIGHT_STYLE.replace(_dark, _light)
LIGHT_STYLE += """
QMainWindow, QWidget { color: #1F2937; }
QComboBox, QLineEdit, QSpinBox, QPlainTextEdit, QListWidget { color: #1F2937; }
QPushButton, QToolButton { color: #374151; }
QPushButton:disabled, QToolButton:disabled { color: #9CA3AF; }
#countBadge { background: #CCFBF1; color: #0F766E; }
#onlineBadge { background: transparent; color: #15803D; }
#warningBadge { background: transparent; color: #B45309; }
#offlineBadge { background: transparent; color: #64748B; }
#iconButton, #rowAction { color: #0F8F83; }
#iconButton:hover, #rowAction:hover { background: #F0FDFA; border-color: #99F6E4; }
#deviceTable { color: #1F2937; selection-background-color: transparent; selection-color: #0F766E; }
#deviceTable::item { background: transparent; color: #1F2937; }
#deviceTable::item:selected { background: transparent; color: #1F2937; }
#deviceIdentifierCell, #deviceStatusCell, #deviceActionsCell { background: transparent; }
QGroupBox::title { background: #F5F7FA; }
#terminalHeader { background: #FFFFFF; border-bottom-color: #E5E7EB; }
#terminalDevice { background: #F0FDFA; color: #0F8F83; border-color: #CCFBF1; }
#terminalSurface { background: #FCFCFD; color: #111827; selection-background-color: #99F6E4; }
"""


class AsyncDispatcher(QObject):
    done = Signal(int, object)
    failed = Signal(int, str)


class HistoryItemDelegate(QStyledItemDelegate):
    """Draw a delete affordance directly on each connection-history row."""

    def __init__(self, combo: "HistoryComboBox") -> None:
        super().__init__(combo)
        self.combo = combo

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        text_option = QStyleOptionViewItem(option)
        text_option.rect = option.rect.adjusted(0, 0, -34, 0)
        super().paint(painter, text_option, index)

        delete_rect = self.combo.delete_rect(option.rect)
        hovered = index.row() == self.combo.delete_hover_row
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(QRect(text_option.rect.right() + 1, option.rect.top(), 34, option.rect.height()), option.palette.highlight())
        if hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            delete_background = "#4C1D24" if option.palette.base().color().lightness() < 128 else "#FEE2E2"
            painter.setBrush(QColor(delete_background))
            painter.drawEllipse(delete_rect.adjusted(3, 3, -3, -3))
        color = QColor("#EF4444") if hovered else (option.palette.highlightedText().color() if selected else QColor("#94A3B8"))
        pen = QPen(color, 1.35)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        center = delete_rect.center()
        painter.drawLine(center.x() - 4, center.y() - 4, center.x() + 4, center.y() + 4)
        painter.drawLine(center.x() + 4, center.y() - 4, center.x() - 4, center.y() + 4)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width() + 34, max(size.height(), 34))


class HistoryComboBox(QComboBox):
    removeRequested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.delete_hover_row = -1
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setItemDelegate(HistoryItemDelegate(self))
        self.view().setMouseTracking(True)
        self.view().viewport().installEventFilter(self)

    @staticmethod
    def delete_rect(row_rect: QRect) -> QRect:
        return QRect(row_rect.right() - 31, row_rect.top(), 32, row_rect.height())

    def eventFilter(self, watched, event) -> bool:
        if watched is self.view().viewport():
            if event.type() == QEvent.Type.MouseMove:
                index = self.view().indexAt(event.position().toPoint())
                row = index.row() if index.isValid() and self.delete_rect(self.view().visualRect(index)).contains(event.position().toPoint()) else -1
                if row != self.delete_hover_row:
                    self.delete_hover_row = row
                    self.view().viewport().update()
            elif event.type() == QEvent.Type.Leave:
                self.delete_hover_row = -1
                self.view().viewport().update()
            elif event.type() == QEvent.Type.MouseButtonRelease:
                position = event.position().toPoint()
                index = self.view().indexAt(position)
                if index.isValid() and self.delete_rect(self.view().visualRect(index)).contains(position):
                    address = index.data(Qt.ItemDataRole.UserRole)
                    if address:
                        self.hidePopup()
                        self.removeRequested.emit(str(address))
                    return True
        return super().eventFilter(watched, event)


class ScrcpyHandle:
    """A process handle that works for both newly started and discovered PIDs."""
    def __init__(self, process: subprocess.Popen | None = None, pid: int | None = None, serial: str = "", log_callback=None) -> None:
        self.process = process
        self.pid = process.pid if process else pid
        self.serial = serial
        if process and log_callback:
            for stream_name in ("stdout", "stderr"):
                stream = getattr(process, stream_name)
                threading.Thread(target=self._read_stream, args=(stream, log_callback), daemon=True).start()
            threading.Thread(target=self._wait_process, args=(process, log_callback), daemon=True).start()

    def _wait_process(self, process, callback) -> None:
        try:
            return_code = process.wait()
            callback(self.serial, f"scrcpy 进程已退出，退出码：{return_code}")
        except (OSError, ValueError):
            pass

    def _read_stream(self, stream, callback) -> None:
        if not stream:
            return
        try:
            for line in iter(stream.readline, ""):
                line = line.rstrip()
                if line:
                    callback(self.serial, line)
        except (OSError, ValueError):
            pass

    def poll(self):
        if self.process:
            return self.process.poll()
        if not self.pid:
            return 0
        result = subprocess.run(["tasklist", "/FI", f"PID eq {self.pid}", "/NH"], capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=ProcessRunner._hidden_window_flags())
        return None if str(self.pid) in result.stdout else 0

    def terminate(self) -> None:
        if self.process:
            self.process.terminate()
        elif self.pid:
            subprocess.run(["taskkill", "/PID", str(self.pid), "/T", "/F"], capture_output=True, creationflags=ProcessRunner._hidden_window_flags())


class MainWindow(QMainWindow):
    scrcpy_log = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.repo = SettingsRepository()
        # Keep a small persistent command history for quick shell recall.
        stored_shell_history = self.repo.data.get("shell_history", [])
        if not isinstance(stored_shell_history, list):
            stored_shell_history = []
        self.shell_history: list[str] = [str(item) for item in stored_shell_history if str(item).strip()][-100:]
        self._shell_history_index: int | None = None
        self._shell_history_draft = ""
        self.resolver = BinaryResolver(self.repo)
        self.adb = AdbClient(self.resolver)
        self.devices: list[Device] = []
        self._initial_device_scan_done = False
        # One scrcpy process per device serial. Starting another device must
        # never overwrite the process handle of an existing session.
        self.scrcpy_processes: dict[str, ScrcpyHandle] = {}
        self.shell_processes: dict[str, QProcess] = {}
        self.terminal_windows: dict[str, DeviceTerminalWindow] = {}
        self.shell_privileged: dict[str, bool] = {}
        self.shell_logs: dict[str, str] = {}
        self.shell_terminal_states: dict[str, TerminalLogState] = {}
        self.shell_decoders = {}
        self.shell_process: QProcess | None = None
        self.shell_serial = ""
        self._last_selected_serial = ""
        self._refresh_in_progress = False
        self._refresh_requested_manually = False
        self._connection_busy = False
        self._pending_disconnects: set[str] = set()
        self._async_dispatcher = AsyncDispatcher(self)
        self._async_dispatcher.done.connect(self._handle_job_done)
        self._async_dispatcher.failed.connect(self._handle_job_failed)
        self._next_job_token = 0
        self._job_callbacks: dict[int, tuple[object, object]] = {}
        self._async_threads: dict[int, threading.Thread] = {}
        self.setWindowTitle(f"ADBLite v{APP_VERSION} — ADB · Scrcpy · 快捷命令")
        self.resize(1120, 720)
        self._build_ui()
        self.scrcpy_log.connect(self._append_scrcpy_log)
        self._discover_scrcpy_processes()
        self.refresh_devices()
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.refresh_devices(manual=False))
        self.timer.start(4000)

    def _build_ui(self) -> None:
        self.apply_theme(self.repo.data.get("theme", "light"))
        root = QWidget(); root.setObjectName("root")
        layout = QVBoxLayout(root); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        topbar = QWidget(); topbar.setObjectName("topbar")
        header = QHBoxLayout(topbar); header.setContentsMargins(18, 0, 14, 0); header.setSpacing(8)
        brand = QLabel("ADBLite"); brand.setObjectName("brandName"); header.addWidget(brand)
        self.navigation = QTabBar(); self.navigation.setObjectName("navTabs")
        self.navigation.setDrawBase(False)
        for item in ("设备", "快捷命令", "设置"):
            self.navigation.addTab(item)
        header.addWidget(self.navigation)
        header.addStretch()
        # The table is the single visible device selector. Keep this hidden
        # model combo so existing shell/command logic can share the selection.
        self.device_combo = QComboBox(self)
        self.device_combo.currentIndexChanged.connect(self._device_changed)
        self.device_combo.hide()
        self.header_refresh_button = self._icon_button(
            "refresh", "刷新设备", lambda: self.refresh_devices(manual=True), "iconButton",
        )
        header.addWidget(self.header_refresh_button)
        self.theme_toggle = self._icon_button("moon", "切换到夜间模式", self._toggle_theme, "iconButton")
        header.addWidget(self.theme_toggle)
        self._update_theme_toggle()
        layout.addWidget(topbar)

        self.scrcpy_output = QPlainTextEdit(self); self.scrcpy_output.hide()
        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self._devices_page()); self.page_stack.addWidget(self._commands_page()); self.page_stack.addWidget(self._settings_page())
        self.navigation.currentChanged.connect(self.page_stack.setCurrentIndex)
        self.navigation.setCurrentIndex(0)
        layout.addWidget(self.page_stack, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("ADB 就绪 · 等待设备刷新")

    def _devices_page(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(18, 16, 18, 12); layout.setSpacing(10)
        toolbar = QHBoxLayout(); toolbar.setSpacing(8)
        title = QLabel("设备"); title.setObjectName("pageTitle"); toolbar.addWidget(title)
        self.device_count = QLabel("0 台"); self.device_count.setObjectName("countBadge"); toolbar.addWidget(self.device_count)
        toolbar.addStretch()
        self.device_search = QLineEdit(); self.device_search.setPlaceholderText("搜索设备名称或标识")
        self.device_search.setClearButtonEnabled(True); self.device_search.setMaximumWidth(260)
        self.device_search.textChanged.connect(self._filter_devices); toolbar.addWidget(self.device_search)
        layout.addLayout(toolbar)

        self.device_stack = QStackedWidget()
        self.device_table = QTableWidget(0, 4); self.device_table.setObjectName("deviceTable")
        self.device_table.setHorizontalHeaderLabels(["设备标识", "设备名称", "状态", "操作"])
        self.device_table.verticalHeader().setVisible(False)
        self.device_table.setShowGrid(False); self.device_table.setAlternatingRowColors(False)
        self.device_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.device_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.device_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.device_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        device_header = self.device_table.horizontalHeader()
        device_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        device_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        device_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        device_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.device_table.setColumnWidth(0, 260)
        self.device_table.setColumnWidth(1, 180)
        self.device_table.setColumnWidth(2, 120)
        # Keep enough room for every primary action; long identifiers and
        # model names are elided in their cells and remain available as tips.
        self.device_table.setMinimumWidth(840)
        self.device_table.itemSelectionChanged.connect(self._device_table_selection_changed)
        self.device_table.cellDoubleClicked.connect(lambda row, _column: self._run_device_action(row, self.start_scrcpy))
        self.device_stack.addWidget(self.device_table)
        empty = QFrame(); empty.setObjectName("emptyPanel")
        empty_layout = QVBoxLayout(empty); empty_layout.addStretch()
        empty_icon = QLabel("⌁"); empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter); empty_icon.setStyleSheet("font-size: 34px; color: #14B8A6;")
        empty_title = QLabel("还没有发现设备"); empty_title.setObjectName("emptyTitle"); empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint = QLabel("连接 USB 设备，或在下方输入无线调试地址"); empty_hint.setObjectName("mutedLabel"); empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon); empty_layout.addWidget(empty_title); empty_layout.addWidget(empty_hint); empty_layout.addStretch()
        self.device_stack.addWidget(empty)
        self.device_stack.setCurrentIndex(1)
        layout.addWidget(self.device_stack, 1)

        self.device_output = QPlainTextEdit(); self.device_output.setReadOnly(True); self.device_output.setMaximumHeight(125); self.device_output.hide()
        log_header = QHBoxLayout(); self.log_toggle = QToolButton(); self.log_toggle.setText("操作记录  ▾")
        self.log_toggle.setCheckable(True); self.log_toggle.toggled.connect(self._toggle_device_log); log_header.addWidget(self.log_toggle)
        log_header.addStretch()
        copy_log = QToolButton(); copy_log.setText("复制"); copy_log.clicked.connect(lambda: QApplication.clipboard().setText(self.device_output.toPlainText())); log_header.addWidget(copy_log)
        clear_log = QToolButton(); clear_log.setText("清空"); clear_log.clicked.connect(self.device_output.clear); log_header.addWidget(clear_log)
        layout.addLayout(log_header)
        layout.addWidget(self.device_output)

        connection_bar = QFrame(); connection_bar.setObjectName("connectionBar")
        history_layout = QHBoxLayout(connection_bar); history_layout.setContentsMargins(12, 9, 10, 9); history_layout.setSpacing(8)
        connection_label = QLabel("⌁  无线连接"); connection_label.setObjectName("mutedLabel"); history_layout.addWidget(connection_label)
        self.history_combo = HistoryComboBox()
        self.history_combo.setMinimumWidth(260)
        self.history_combo.lineEdit().setPlaceholderText("IP:端口，例如 192.168.1.20:5555")
        self.history_combo.currentIndexChanged.connect(self._history_selection_changed)
        self.history_combo.removeRequested.connect(self.remove_history)
        self.history_combo.lineEdit().returnPressed.connect(self.connect_history); history_layout.addWidget(self.history_combo, 1)
        self.connect_button = QPushButton("连接设备"); self.connect_button.setObjectName("primaryButton"); self.connect_button.clicked.connect(self.connect_history); history_layout.addWidget(self.connect_button)
        self.discovery_button = QPushButton("自动发现"); self.discovery_button.clicked.connect(self.discover_wireless); history_layout.addWidget(self.discovery_button)
        layout.addWidget(connection_bar)
        self._reload_history()
        return page

    def _toggle_device_log(self, visible: bool) -> None:
        self.device_output.setVisible(visible)
        self.log_toggle.setText("操作记录  ▴" if visible else "操作记录  ▾")

    def _show_device_log(self) -> None:
        if not self.log_toggle.isChecked():
            self.log_toggle.setChecked(True)

    def _filter_devices(self, text: str) -> None:
        needle = text.strip().lower()
        for row, device in enumerate(self.devices):
            haystack = f"{device.serial} {device.model} {device.state}".lower()
            self.device_table.setRowHidden(row, bool(needle and needle not in haystack))

    def _device_table_selection_changed(self) -> None:
        row = self.device_table.currentRow()
        if 0 <= row < len(self.devices):
            self._select_device_serial(self.devices[row].serial)

    def _select_device_serial(self, serial: str) -> None:
        index = self.device_combo.findData(serial)
        if index >= 0 and self.device_combo.currentIndex() != index:
            self.device_combo.setCurrentIndex(index)

    def _run_device_action(self, row: int, action) -> None:
        if not 0 <= row < len(self.devices):
            return
        self._select_device_serial(self.devices[row].serial)
        action()

    @staticmethod
    def _icon_button(icon_name: str, tooltip: str, callback=None, object_name: str = "rowAction") -> QToolButton:
        button = QToolButton()
        button.setObjectName(object_name)
        button.setIcon(interface_icon(icon_name))
        button.setIconSize(QSize(17, 17))
        button.setFixedSize(32, 32)
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setProperty("actionName", icon_name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if callback:
            button.clicked.connect(callback)
        return button

    def _open_device_shell(self, row: int) -> None:
        if not 0 <= row < len(self.devices):
            return
        device = self.devices[row]
        existing = self.terminal_windows.get(device.serial)
        if existing:
            existing.showNormal() if existing.isMinimized() else existing.show()
            existing.raise_(); existing.activateWindow()
            return
        adb_path = self.resolver.resolve("adb")
        if not adb_path:
            return self._show_error("未找到 adb，请先在设置中配置路径")
        terminal = DeviceTerminalWindow(
            adb_path, device.serial, device.model or device.serial,
            self.repo.data.get("terminal_theme", "light"),
        )
        terminal.theme_change_requested.connect(self.apply_terminal_theme)
        terminal.closed.connect(self._terminal_window_closed)
        self.terminal_windows[device.serial] = terminal
        terminal.show(); terminal.raise_(); terminal.activateWindow()
        self._update_device_shell_marker(device.serial)

    def _terminal_window_closed(self, terminal: DeviceTerminalWindow) -> None:
        if self.terminal_windows.get(terminal.serial) is terminal:
            self.terminal_windows.pop(terminal.serial, None)
        self._update_device_shell_marker(terminal.serial)

    def _device_status(self, device: Device) -> tuple[str, str]:
        if device.state == "device":
            return "已连接", "onlineBadge"
        if device.state == "unauthorized":
            return "等待授权", "warningBadge"
        if device.state == "offline":
            return "离线", "offlineBadge"
        labels = {"recovery": "恢复模式", "bootloader": "引导模式", "sideload": "侧载模式"}
        return labels.get(device.state, device.state or "未知"), "warningBadge"

    def _render_device_table(self) -> None:
        if not hasattr(self, "device_table"):
            return
        selected = self.current_serial()
        self.device_table.blockSignals(True)
        self.device_table.setRowCount(len(self.devices))
        for row, device in enumerate(self.devices):
            connection = "无线" if ":" in device.serial else "USB"
            identifier_wrap = QWidget(); identifier_wrap.setObjectName("deviceIdentifierCell")
            identifier_wrap.setToolTip(f"{connection} 设备 · {device.serial}")
            identifier_wrap.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            identifier_layout = QHBoxLayout(identifier_wrap); identifier_layout.setContentsMargins(10, 0, 10, 0); identifier_layout.setSpacing(6)
            connection_icon = QLabel(); connection_icon.setFixedSize(18, 18)
            connection_icon.setPixmap(interface_icon("wifi" if connection == "无线" else "usb").pixmap(18, 18))
            connection_icon.setToolTip(f"{connection} 设备")
            identifier_text = QLabel(device.serial); identifier_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            identifier_text.setToolTip(f"{connection} 设备 · {device.serial}")
            identifier_spacer = QLabel(); identifier_spacer.setFixedSize(18, 18)
            identifier_layout.addWidget(connection_icon)
            identifier_layout.addStretch()
            identifier_layout.addWidget(identifier_text)
            identifier_layout.addStretch()
            identifier_layout.addWidget(identifier_spacer)

            name_item = QTableWidgetItem(device.model or "未知设备")
            name_item.setToolTip(device.model or "ADB 未返回设备型号")
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.device_table.setCellWidget(row, 0, identifier_wrap); self.device_table.setItem(row, 1, name_item)

            status_text, status_style = self._device_status(device)
            status_wrap = QWidget(); status_wrap.setObjectName("deviceStatusCell"); status_layout = QHBoxLayout(status_wrap); status_layout.setContentsMargins(6, 0, 8, 0)
            status = QLabel(status_text); status.setObjectName(status_style); status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_layout.addStretch(); status_layout.addWidget(status); status_layout.addStretch()
            self.device_table.setCellWidget(row, 2, status_wrap)

            actions = QWidget(); actions.setObjectName("deviceActionsCell"); actions.setMinimumWidth(244)
            action_layout = QHBoxLayout(actions); action_layout.setContentsMargins(8, 0, 4, 0); action_layout.setSpacing(6)
            enabled = device.state == "device" and not self._connection_busy
            action_layout.addStretch()
            action_specs = [
                ("monitor", "启动 Scrcpy 投屏（双击设备行也可启动）", lambda _=False, r=row: self._run_device_action(r, self.start_scrcpy), enabled),
                ("terminal", "打开当前设备的独立终端窗口", lambda _=False, r=row: self._open_device_shell(r), enabled),
                ("info", "读取设备信息", lambda _=False, r=row: self._run_device_action(r, self.show_device_info), enabled),
            ]
            if ":" in device.serial and device.state == "offline":
                action_specs.append(("connect", "重新连接无线 ADB", lambda _=False, r=row: self._connect_device_row(r), not self._connection_busy))
            else:
                action_specs.append(("disconnect", "断开无线 ADB", lambda _=False, r=row: self._run_device_action(r, self.disconnect_current), enabled and ":" in device.serial))
            action_specs.extend((
                ("restart", "重启系统", lambda _=False, r=row: self._run_device_action(r, lambda: self.confirm_reboot(False)), enabled),
                ("recovery", "重启到 Recovery", lambda _=False, r=row: self._run_device_action(r, lambda: self.confirm_reboot(True)), enabled),
            ))
            for icon_name, tooltip, callback, action_enabled in action_specs:
                button = self._icon_button(icon_name, tooltip, callback)
                button.setEnabled(action_enabled); action_layout.addWidget(button)
            action_layout.addStretch()
            self.device_table.setCellWidget(row, 3, actions)
            self.device_table.setRowHeight(row, 52)
            if device.serial == selected:
                self.device_table.selectRow(row)
        self.device_table.blockSignals(False)
        self.device_count.setText(f"{len(self.devices)} 台")
        self.device_stack.setCurrentIndex(0 if self.devices else 1)
        self._filter_devices(self.device_search.text())

    def _scrcpy_settings_box(self) -> QGroupBox:
        settings_box = QGroupBox("Scrcpy 默认参数")
        form = QFormLayout(settings_box)
        self.scrcpy_size = QSpinBox(); self.scrcpy_size.setRange(0, 8192); self.scrcpy_size.setValue(int(self.repo.data.get("scrcpy_max_size", 1920)))
        self.scrcpy_fps = QSpinBox(); self.scrcpy_fps.setRange(0, 240); self.scrcpy_fps.setValue(int(self.repo.data.get("scrcpy_max_fps", 60)))
        self.scrcpy_bitrate = QLineEdit(str(self.repo.data.get("scrcpy_bitrate", "8M")))
        self.scrcpy_extra = QLineEdit(str(self.repo.data.get("scrcpy_extra", "")))
        self.scrcpy_no_audio = QPushButton(); self.scrcpy_no_audio.setCheckable(True)
        self.scrcpy_no_audio.setChecked(bool(self.repo.data.get("scrcpy_no_audio", False)))
        self.scrcpy_no_audio.toggled.connect(lambda checked: self.scrcpy_no_audio.setText(f"禁用音频：{'是' if checked else '否'}"))
        self.scrcpy_no_audio.setText(f"禁用音频：{'是' if self.scrcpy_no_audio.isChecked() else '否'}")
        form.addRow("最大尺寸", self.scrcpy_size)
        form.addRow("最大 FPS", self.scrcpy_fps)
        form.addRow("视频码率", self.scrcpy_bitrate)
        form.addRow("附加参数", self.scrcpy_extra)
        form.addRow(self.scrcpy_no_audio)
        hint = QLabel("设备列表中的“投屏”会直接使用这些参数。0 表示不限制。")
        hint.setObjectName("pageHint"); form.addRow(hint)
        return settings_box

    def _commands_page(self) -> QWidget:
        page = QWidget(); outer = QVBoxLayout(page); outer.setContentsMargins(20, 18, 20, 18); outer.setSpacing(12)
        title = QLabel("快捷命令"); title.setObjectName("pageTitle"); outer.addWidget(title)
        hint = QLabel("保存常用 ADB、Scrcpy、CMD 和进程命令"); hint.setObjectName("pageHint"); outer.addWidget(hint)
        layout = QHBoxLayout(); layout.setSpacing(14); outer.addLayout(layout, 1)
        list_box = QGroupBox("命令列表"); list_layout = QVBoxLayout(list_box); self.command_list = QListWidget(); list_layout.addWidget(self.command_list); layout.addWidget(list_box, 1)

        panel = QGroupBox("命令编辑器"); panel_layout = QVBoxLayout(panel); panel_layout.setContentsMargins(10, 14, 10, 10); layout.addWidget(panel, 2)
        editor_area = QWidget(); editor = QFormLayout(editor_area); editor.setContentsMargins(0, 0, 0, 0); editor.setHorizontalSpacing(10); editor.setVerticalSpacing(8); editor.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.cmd_name = QLineEdit(); self.cmd_runner = QComboBox(); self.cmd_runner.addItems(["adb", "scrcpy", "cmd", "process"]); self.cmd_args = QPlainTextEdit(); self.cmd_args.setPlaceholderText("每行一个参数；cmd 模式填写完整命令"); self.cmd_args.setMinimumHeight(110)
        args_label = QLabel("参数/命令"); args_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        editor.addRow("名称", self.cmd_name); editor.addRow("执行器", self.cmd_runner); editor.addRow(args_label, self.cmd_args)
        row = QHBoxLayout(); row.setSpacing(6)
        new_command = QPushButton("新建")
        new_command.clicked.connect(self.new_command)
        save = QPushButton("保存"); save.clicked.connect(self.save_command)
        run = QPushButton("运行"); run.setObjectName("primaryButton"); run.clicked.connect(self.run_command)
        delete = QPushButton("删除"); delete.setObjectName("dangerButton"); delete.clicked.connect(self.delete_command)
        for button in (new_command, save, run, delete):
            row.addWidget(button, 1)
        editor.addRow(row)

        splitter = QSplitter(Qt.Orientation.Vertical); splitter.setChildrenCollapsible(False); splitter.addWidget(editor_area)
        self.command_output = QPlainTextEdit(); self.command_output.setReadOnly(True); self.command_output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap); splitter.addWidget(self.command_output)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 2); splitter.setSizes([360, 220]); panel_layout.addWidget(splitter, 1)
        self.command_list.currentRowChanged.connect(self.load_command)
        self._reload_commands()
        return page

    def _shell_page(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(12)
        title = QLabel("设备 Shell"); title.setObjectName("pageTitle"); layout.addWidget(title)
        hint = QLabel("连接当前设备的持久 ADB Shell 会话（稳定日志模式，避免长命令回显错乱）"); hint.setObjectName("pageHint"); layout.addWidget(hint)
        shell_notice = QLabel("提示：Shell 功能尚不完善，推荐优先使用设备原生终端功能。")
        shell_notice.setObjectName("pageHint")
        layout.addWidget(shell_notice)
        toolbar = QHBoxLayout(); self.shell_target = QLabel("未连接"); self.shell_target.setObjectName("statusLabel"); toolbar.addWidget(self.shell_target, 1)
        open_shell = QPushButton("进入 Shell"); open_shell.setObjectName("primaryButton"); open_shell.clicked.connect(self.start_shell)
        close_shell = QPushButton("关闭会话"); close_shell.setObjectName("dangerButton"); close_shell.clicked.connect(self.stop_shell)
        toolbar.addWidget(open_shell); toolbar.addWidget(close_shell); layout.addLayout(toolbar)
        log_container = QWidget(); log_layout = QVBoxLayout(log_container); log_layout.setContentsMargins(0, 0, 0, 0)
        log_header = QHBoxLayout(); log_header.addWidget(QLabel("Shell 日志")); log_header.addStretch()
        copy_shell = QPushButton("复制日志"); copy_shell.clicked.connect(self.copy_shell_log); log_header.addWidget(copy_shell)
        clear_shell = QPushButton("清除日志"); clear_shell.clicked.connect(self.clear_shell_log); log_header.addWidget(clear_shell)
        log_layout.addLayout(log_header)
        self.shell_output = QPlainTextEdit(); self.shell_output.setReadOnly(True); self.shell_output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap); log_layout.addWidget(self.shell_output, 1)
        layout.addWidget(log_container, 1)
        input_row = QHBoxLayout(); self.shell_prompt_label = QLabel("$"); self.shell_prompt_label.setObjectName("shellPrompt"); input_row.addWidget(self.shell_prompt_label); self.shell_input = QLineEdit(); self.shell_input.setPlaceholderText("输入设备端命令，例如 getprop ro.product.model（↑/↓ 可调用历史命令）"); self.shell_input.installEventFilter(self); self.shell_input.textEdited.connect(self._shell_input_edited); self.shell_input.returnPressed.connect(self.send_shell_input); input_row.addWidget(self.shell_input, 1)
        send = QPushButton("发送"); send.setObjectName("primaryButton"); send.clicked.connect(self.send_shell_input); input_row.addWidget(send); layout.addLayout(input_row)
        return page

    def _settings_page(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(12)
        title = QLabel("设置"); title.setObjectName("pageTitle"); layout.addWidget(title)
        hint = QLabel("配置外部工具路径和运行环境"); hint.setObjectName("pageHint"); layout.addWidget(hint)
        content = QHBoxLayout(); content.setSpacing(14); layout.addLayout(content, 1)
        box = QGroupBox("运行环境"); form = QFormLayout(box); content.addWidget(box, 3)
        self.theme_combo = QComboBox(); self.theme_combo.addItem("日间模式", "light"); self.theme_combo.addItem("夜间模式", "dark"); self.theme_combo.setCurrentIndex(0 if self.repo.data.get("theme", "light") == "light" else 1); self.theme_combo.currentIndexChanged.connect(lambda: self.apply_theme(self.theme_combo.currentData()))
        form.addRow("界面主题", self.theme_combo)
        self.adb_path = QLineEdit(self.repo.data.get("adb_path", "")); self.scrcpy_path = QLineEdit(self.repo.data.get("scrcpy_path", ""))
        for label, field, key, binary in [("adb 路径", self.adb_path, "adb_path", "adb"), ("scrcpy 路径", self.scrcpy_path, "scrcpy_path", "scrcpy")]:
            row = QHBoxLayout(); row.addWidget(field, 1); browse = QPushButton("选择"); browse.clicked.connect(lambda _, f=field: self.pick_binary(f)); row.addWidget(browse); form.addRow(label, row)
        save = QPushButton("保存设置"); save.setObjectName("primaryButton"); save.clicked.connect(self.save_settings); form.addRow(save)
        config_row = QHBoxLayout()
        self.config_path = QLineEdit(str(self.repo.path)); self.config_path.setReadOnly(True); self.config_path.setToolTip("当前实际使用的配置文件路径"); config_row.addWidget(self.config_path, 1)
        copy_config_path = QPushButton("复制路径"); copy_config_path.clicked.connect(lambda: QApplication.clipboard().setText(self.config_path.text())); config_row.addWidget(copy_config_path)
        form.addRow("配置文件", config_row)
        project_link = QLabel(f'<a href="{GITHUB_PROJECT_URL}">GitHub 开源项目主页：{GITHUB_PROJECT_URL}</a>')
        project_link.setObjectName("projectLink")
        project_link.setOpenExternalLinks(True)
        project_link.setToolTip(GITHUB_PROJECT_URL)
        form.addRow("项目地址", project_link)
        form.addRow("软件版本", QLabel(f"v{APP_VERSION}"))
        form.addRow("软件作者", QLabel("luobida"))
        content.addWidget(self._scrcpy_settings_box(), 2)
        return page

    def pick_binary(self, field: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择可执行文件", filter="Executable (*.exe);;All files (*)")
        if path: field.setText(path)

    def save_settings(self) -> None:
        self.repo.data.update({
            "adb_path": self.adb_path.text().strip(),
            "scrcpy_path": self.scrcpy_path.text().strip(),
            "theme": self.theme_combo.currentData(),
            "scrcpy_max_size": self.scrcpy_size.value(),
            "scrcpy_max_fps": self.scrcpy_fps.value(),
            "scrcpy_bitrate": self.scrcpy_bitrate.text().strip(),
            "scrcpy_extra": self.scrcpy_extra.text().strip(),
            "scrcpy_no_audio": self.scrcpy_no_audio.isChecked(),
        })
        self.repo.save(); self._notice("设置已保存")

    def apply_theme(self, theme: str) -> None:
        theme = "light" if theme == "light" else "dark"
        self.setStyleSheet(LIGHT_STYLE if theme == "light" else DARK_STYLE)
        if hasattr(self, "repo"):
            self.repo.data["theme"] = theme
            self.repo.save()
        if hasattr(self, "theme_combo"):
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(0 if theme == "light" else 1)
            self.theme_combo.blockSignals(False)
        self._update_theme_toggle()

    def apply_terminal_theme(self, theme: str) -> None:
        """Persist and apply the Shell theme without changing the main UI."""
        theme = "light" if theme == "light" else "dark"
        self.repo.data["terminal_theme"] = theme
        self.repo.save()
        for terminal in self.terminal_windows.values():
            terminal.set_theme(theme)

    def _toggle_theme(self) -> None:
        current = self.repo.data.get("theme", "light")
        self.apply_theme("light" if current == "dark" else "dark")

    def _update_theme_toggle(self) -> None:
        """Show the mode that clicking the theme shortcut will switch to."""
        if not hasattr(self, "theme_toggle"):
            return
        is_dark = self.repo.data.get("theme", "light") == "dark"
        self.theme_toggle.setIcon(interface_icon("sun" if is_dark else "moon"))
        self.theme_toggle.setToolTip("切换到日间模式" if is_dark else "切换到夜间模式")
        self.theme_toggle.setAccessibleName(self.theme_toggle.toolTip())

    def _run_async(self, fn, on_done, on_failed=None) -> None:
        self._next_job_token += 1
        token = self._next_job_token
        self._job_callbacks[token] = (on_done, on_failed or self._show_error)

        def run() -> None:
            try:
                result = fn()
            except Exception as exc:  # Worker boundary: report on the GUI thread.
                try:
                    self._async_dispatcher.failed.emit(token, str(exc))
                except RuntimeError:
                    pass  # The application closed while the worker was running.
            else:
                try:
                    self._async_dispatcher.done.emit(token, result)
                except RuntimeError:
                    pass

        thread = threading.Thread(target=run, name=f"ADBLiteJob-{token}", daemon=True)
        self._async_threads[token] = thread
        thread.start()

    @Slot(int, object)
    def _handle_job_done(self, token: int, result) -> None:
        self._async_threads.pop(token, None)
        callbacks = self._job_callbacks.pop(token, None)
        if callbacks:
            callbacks[0](result)

    @Slot(int, str)
    def _handle_job_failed(self, token: int, message: str) -> None:
        self._async_threads.pop(token, None)
        callbacks = self._job_callbacks.pop(token, None)
        if callbacks:
            callbacks[1](message)

    def refresh_devices(self, manual: bool = False) -> None:
        if self._refresh_in_progress:
            if manual:
                self._refresh_requested_manually = True
            return
        self._refresh_in_progress = True
        self._refresh_requested_manually = manual
        if manual:
            if hasattr(self, "header_refresh_button"):
                self.header_refresh_button.setEnabled(False)
                self.header_refresh_button.setToolTip("正在刷新设备…")
            self.statusBar().showMessage("正在刷新 ADB 设备…")
        self._run_async(self.adb.devices, self._set_devices, self._show_device_error)

    def _show_device_error(self, message: str) -> None:
        first_result = not self._initial_device_scan_done
        manual = self._finish_device_refresh()
        self._initial_device_scan_done = True
        if manual or first_result:
            self.statusBar().showMessage(f"ADB 刷新失败 · {message}")
        if hasattr(self, "device_output") and not self.devices:
            self.device_output.setPlainText(f"ADB 刷新失败：{message}")

    def _finish_device_refresh(self) -> bool:
        manual = self._refresh_requested_manually
        self._refresh_in_progress = False
        self._refresh_requested_manually = False
        if hasattr(self, "header_refresh_button"):
            self.header_refresh_button.setEnabled(True)
            self.header_refresh_button.setToolTip("刷新设备")
        return manual

    def _set_devices(self, devices: list[Device]) -> None:
        manual = self._finish_device_refresh()
        detected_serials = {device.serial for device in devices}
        # ADB can briefly return its pre-disconnect snapshot. Keep a device
        # offline until one scan has confirmed that it is actually absent.
        confirmed_disconnects = self._pending_disconnects - detected_serials
        self._pending_disconnects.difference_update(confirmed_disconnects)
        devices = [
            Device(serial=device.serial, state="offline", model=device.model)
            if device.serial in self._pending_disconnects else device
            for device in devices
        ]
        devices = merge_device_statuses(self.devices, devices)
        old_snapshot = [(item.serial, item.state, item.model, item.transport_id) for item in self.devices]
        new_snapshot = [(item.serial, item.state, item.model, item.transport_id) for item in devices]
        if self._initial_device_scan_done and old_snapshot == new_snapshot:
            if manual:
                self.statusBar().showMessage(f"ADB 已刷新 · {len(devices)} 台设备")
            return
        old_active = {device.serial for device in self.devices if device.state == "device"}
        new_active = {device.serial for device in devices if device.state == "device"}
        for serial in old_active - new_active:
            process = self.scrcpy_processes.get(serial)
            if process and process.poll() is None:
                self.scrcpy_log.emit(f"[{serial}] ADB 连接已断开，等待 scrcpy 自行退出")
        self.devices = devices; previous = self.current_serial()
        status = "ADB 已刷新" if manual or not self._initial_device_scan_done else "设备列表已更新"
        self.statusBar().showMessage(f"{status} · {len(devices)} 台设备")
        self.device_combo.blockSignals(True); self.device_combo.clear()
        for device in devices:
            self.device_combo.addItem(self._device_combo_text(device), device.serial)
            if not self._initial_device_scan_done and device.state == "device":
                self.repo.remember(device.serial, kind="wifi" if ":" in device.serial else "usb")
        if not devices:
            self.device_combo.addItem("未检测到设备", "")
        if previous:
            idx = self.device_combo.findData(previous)
            if idx >= 0: self.device_combo.setCurrentIndex(idx)
        self.device_combo.blockSignals(False)
        self._render_device_table()
        if not self._last_selected_serial:
            self._last_selected_serial = self.current_serial()
        self._initial_device_scan_done = True
        self._reload_history()
        serial = self.current_serial()
        if serial:
            if self.shell_serial != serial:
                process = self.shell_processes.get(serial)
                self.shell_process = process if process and process.state() != QProcess.ProcessState.NotRunning else None
                self.shell_serial = serial if self.shell_process else ""
            self._set_shell_log_view(serial, keep_position=True)
        else:
            self._set_shell_log_view("")
        self._update_scrcpy_status(serial)

    def current_serial(self) -> str:
        return str(self.device_combo.currentData() or "")

    def _select_device_row(self, row: int, *_args) -> None:
        if 0 <= row < len(self.devices):
            self._select_device_serial(self.devices[row].serial)

    def _device_changed(self) -> None:
        serial = self.current_serial()
        if serial:
            if hasattr(self, "device_table"):
                for row, device in enumerate(self.devices):
                    if device.serial == serial and self.device_table.currentRow() != row:
                        self.device_table.blockSignals(True); self.device_table.selectRow(row); self.device_table.blockSignals(False)
                        break
            self.repo.remember(serial, kind="wifi" if ":" in serial else "usb")
            self._update_scrcpy_status(serial)
        else:
            self._update_scrcpy_status("")

    def _set_shell_log_view(self, serial: str, keep_position: bool = False) -> None:
        if not hasattr(self, "shell_output"):
            return
        scrollbar = self.shell_output.verticalScrollBar()
        old_value = scrollbar.value()
        was_at_bottom = old_value >= scrollbar.maximum() - 2
        content = self.shell_logs.get(serial, "") if serial else ""
        if self.shell_output.toPlainText() == content:
            return
        self.shell_output.setPlainText(content)
        if keep_position and not was_at_bottom:
            scrollbar.setValue(min(old_value, scrollbar.maximum()))
        else:
            cursor = self.shell_output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.shell_output.setTextCursor(cursor)
            self.shell_output.ensureCursorVisible()

    def _append_shell_log(self, serial: str, text: str) -> None:
        if not serial:
            serial = self.current_serial()
        if not serial:
            return
        previous = self.shell_logs.get(serial, "")
        if "\u5207\u6362\u8bbe\u5907\uff1a" in text and text in previous:
            return
        if previous and not previous.endswith("\n") and not text.startswith("\n"):
            text = "\n" + text
        self.shell_logs[serial] = previous + text
        if serial != self.current_serial() or not hasattr(self, "shell_output"):
            return
        scrollbar = self.shell_output.verticalScrollBar()
        old_value = scrollbar.value()
        was_at_bottom = old_value >= scrollbar.maximum() - 2
        # Insert through a separate document cursor so an existing user
        # selection remains intact while new output arrives.
        doc_cursor = QTextCursor(self.shell_output.document())
        doc_cursor.movePosition(QTextCursor.MoveOperation.End)
        doc_cursor.insertText(text)
        if was_at_bottom:
            self.shell_output.moveCursor(QTextCursor.MoveOperation.End)
            self.shell_output.ensureCursorVisible()
        else:
            scrollbar.setValue(min(old_value, scrollbar.maximum()))

    def copy_shell_log(self) -> None:
        serial = self.current_serial()
        QApplication.clipboard().setText(self.shell_logs.get(serial, "") if serial else "")

    def clear_shell_log(self) -> None:
        serial = self.current_serial()
        if serial:
            self.shell_logs[serial] = ""
            self.shell_terminal_states.pop(serial, None)
        self._set_shell_log_view(serial)

    def _scrcpy_is_running(self, serial: str) -> bool:
        process = self.scrcpy_processes.get(serial)
        return bool(process and process.poll() is None)

    def _update_scrcpy_status(self, serial: str = "") -> None:
        serial = serial or self.current_serial()
        self._update_device_marker(serial)

    def run_adb(self, args: list[str]) -> None:
        serial = self.current_serial()
        if not serial: return self._show_error("请先选择设备")
        self._show_device_log()
        self._run_async(lambda: self.adb.run(args, serial), lambda result: self._show_result(self.device_output, result))

    def confirm_reboot(self, recovery: bool = False) -> None:
        serial = self.current_serial()
        if not serial:
            return self._show_error("请先选择设备")
        target = "Recovery 恢复模式" if recovery else "普通系统"
        detail = (
            f"设备：{serial}\n\n设备将重启并进入 {target}。\n"
            "ADB 和 Scrcpy 连接可能会暂时断开。是否继续？"
        )
        answer = QMessageBox.warning(
            self,
            "确认重启设备",
            detail,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.run_adb(["reboot", "recovery"] if recovery else ["reboot"])

    def start_shell(self) -> None:
        serial = self.current_serial()
        if not serial:
            return self._show_error("请先选择设备")
        existing = self.shell_processes.get(serial)
        if existing and existing.state() != QProcess.ProcessState.NotRunning:
            self._append_shell_log(serial, "Shell 会话已经在运行中\n")
            self.shell_process = existing
            self.shell_serial = serial
            self._update_device_shell_marker(serial)
            self._update_shell_prompt(serial)
            return
        adb_path = self.resolver.resolve("adb")
        if not adb_path:
            return self._show_error("未找到 adb，请先在设置中配置路径")
        self.shell_serial = serial
        self.shell_privileged[serial] = False
        self.shell_terminal_states[serial] = TerminalLogState()
        self.shell_decoders[serial] = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.shell_process = QProcess(self)
        setattr(self.shell_process, "_adblite_serial", serial)
        self.shell_processes[serial] = self.shell_process
        self.shell_process.setProgram(adb_path)
        # This UI is an input box plus an append-only log, not a terminal
        # emulator. A forced PTY starts Android's interactive line editor,
        # whose horizontal redraws corrupt long commands in the log.
        self.shell_process.setArguments(["-s", serial, "shell"])
        # Keep stdout/stderr in the order produced by the remote shell.
        self.shell_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.shell_process.readyReadStandardOutput.connect(self._read_shell_stdout)
        self.shell_process.finished.connect(self._shell_finished)
        self.shell_process.start()
        self._update_device_shell_marker(serial)
        self.shell_target.setText(f"当前设备：{serial}")
        self._append_shell_log(serial, f"$ adb -s {serial} shell\nShell 已连接（稳定日志模式），可以输入命令。\n")
        self._update_shell_prompt(serial)
        self.shell_input.setFocus()

    def send_shell_input(self) -> None:
        if not self.shell_process or self.shell_process.state() == QProcess.ProcessState.NotRunning:
            return self._show_error("请先点击“进入 Shell”")
        command = self.shell_input.text().strip()
        if not command:
            return
        serial = self.shell_serial or self.current_serial()
        self._remember_shell_command(command)
        prompt = "#" if self.shell_privileged.get(serial, False) else "$"
        self._append_shell_log(serial, f"{prompt} {command}\n")
        self.shell_process.write((command + "\n").encode("utf-8"))
        self._update_shell_privilege(serial, command)
        self.shell_input.clear()
        self._shell_history_index = None
        self._shell_history_draft = ""

    def _update_shell_privilege(self, serial: str, command: str) -> None:
        """Emulate the prompt transition that a non-PTY adb shell hides."""
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        if not tokens:
            return
        executable = tokens[0].lower()
        if executable == "su" and "-c" not in tokens and "--command" not in tokens:
            self.shell_privileged[serial] = True
        elif executable in {"exit", "logout"} and self.shell_privileged.get(serial, False):
            self.shell_privileged[serial] = False
        self._update_shell_prompt(serial)

    def _update_shell_prompt(self, serial: str = "") -> None:
        if not hasattr(self, "shell_prompt_label"):
            return
        active_serial = serial or self.shell_serial or self.current_serial()
        prompt = "#" if self.shell_privileged.get(active_serial, False) else "$"
        self.shell_prompt_label.setText(prompt)

    def _remember_shell_command(self, command: str) -> None:
        """Add a command to the MRU history, avoiding adjacent duplicates."""
        if self.shell_history and self.shell_history[-1] == command:
            return
        self.shell_history = [item for item in self.shell_history if item != command]
        self.shell_history.append(command)
        self.shell_history = self.shell_history[-100:]
        self.repo.data["shell_history"] = self.shell_history
        self.repo.save()

    def _navigate_shell_history(self, direction: int) -> None:
        if not self.shell_history:
            return
        if self._shell_history_index is None:
            self._shell_history_draft = self.shell_input.text()
            self._shell_history_index = len(self.shell_history)
        next_index = max(0, min(len(self.shell_history), self._shell_history_index + direction))
        self._shell_history_index = next_index
        value = self._shell_history_draft if next_index == len(self.shell_history) else self.shell_history[next_index]
        self.shell_input.setText(value)
        self.shell_input.setCursorPosition(len(value))

    def _shell_input_edited(self, _text: str) -> None:
        """Start a fresh history navigation sequence after manual edits."""
        self._shell_history_index = None
        self._shell_history_draft = ""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is getattr(self, "shell_input", None) and event.type() == QEvent.Type.KeyPress:
            key_event = event  # QKeyEvent API is available on KeyPress events.
            if key_event.modifiers() == Qt.KeyboardModifier.NoModifier:
                if key_event.key() == Qt.Key.Key_Up:
                    self._navigate_shell_history(-1)
                    return True
                if key_event.key() == Qt.Key.Key_Down:
                    self._navigate_shell_history(1)
                    return True
        return super().eventFilter(watched, event)

    def stop_shell(self) -> None:
        serial = self.shell_serial or self.current_serial()
        process = self.shell_processes.get(serial) if serial else None
        if process and process.state() != QProcess.ProcessState.NotRunning:
            process.terminate()
            setattr(process, "_adblite_serial", serial)
            self._append_shell_log(serial, f"[{serial}] Shell \u4f1a\u8bdd\u5df2\u5173\u95ed\n")
            self.shell_processes.pop(serial, None)
            self.shell_privileged.pop(serial, None)
            self._update_device_shell_marker(serial)
            self.shell_process = None
            self.shell_serial = ""
            self._update_shell_prompt()
            self.shell_target.setText("未连接")
            return
        if self.shell_process and self.shell_process.state() != QProcess.ProcessState.NotRunning:
            self.shell_process.terminate()
            self._append_shell_log(serial, f"[{serial}] Shell 会话已关闭\n")
        elif serial:
            self._append_shell_log(serial, f"[{serial}] 没有正在运行的 Shell 会话\n")
        if serial and (not self.shell_process or self.shell_process.state() == QProcess.ProcessState.NotRunning):
            self.shell_processes.pop(serial, None)
            self.shell_privileged.pop(serial, None)
            self._update_device_shell_marker(serial)
        self.shell_process = None
        self.shell_serial = ""
        self._update_shell_prompt()
        self.shell_target.setText("未连接")

    def _read_shell_stdout(self) -> None:
        process = self.sender()
        if isinstance(process, QProcess):
            data = bytes(process.readAllStandardOutput())
            serial = next((key for key, value in self.shell_processes.items() if value is process), getattr(process, "_adblite_serial", self.shell_serial))
            decoder = self.shell_decoders.setdefault(serial, codecs.getincrementaldecoder("utf-8")(errors="replace"))
            text = decoder.decode(data)
            if text:
                self._append_shell_terminal_text(text, serial)

    def _append_shell_terminal_text(self, text: str, serial: str = "") -> None:
        """Render common terminal control sequences in the shell log."""
        if not serial:
            serial = self.current_serial()
        if not serial:
            return
        state = self.shell_terminal_states.setdefault(serial, TerminalLogState())
        rendered = render_terminal_log(text, state)
        if rendered:
            self._append_shell_log(serial, rendered)

    def _read_shell_stderr(self) -> None:
        process = self.sender()
        if isinstance(process, QProcess):
            data = bytes(process.readAllStandardError())
            serial = next((key for key, value in self.shell_processes.items() if value is process), getattr(process, "_adblite_serial", self.shell_serial))
            decoder = self.shell_decoders.setdefault(serial, codecs.getincrementaldecoder("utf-8")(errors="replace"))
            text = decoder.decode(data)
            if text:
                self._append_shell_terminal_text(text, serial)

    def _shell_finished(self, exit_code: int, _status) -> None:
        process = self.sender()
        serial = next((key for key, value in self.shell_processes.items() if value is process), getattr(process, "_adblite_serial", ""))
        decoder = self.shell_decoders.pop(serial, None)
        if decoder:
            tail = decoder.decode(b"", final=True)
            if tail:
                self._append_shell_terminal_text(tail, serial)
        terminal_state = self.shell_terminal_states.pop(serial, None)
        if terminal_state:
            final_line = flush_terminal_log(terminal_state)
            if final_line:
                self._append_shell_log(serial, final_line)
        if serial:
            self.shell_processes.pop(serial, None)
            self.shell_privileged.pop(serial, None)
            self._update_device_shell_marker(serial)
        self._append_shell_log(serial, f"\n[{serial or '未知设备'}] Shell 已退出，退出码：{exit_code}\n")
        if process is self.shell_process:
            self.shell_process = None
            self.shell_serial = ""
            self._update_shell_prompt()
            self.shell_target.setText("未连接")

    def show_device_info(self) -> None:
        serial = self.current_serial()
        if not serial:
            return self._show_error("请先选择设备")
        info_args = [
            "shell", "sh", "-c",
            "printf '型号: '; getprop ro.product.model; printf '品牌: '; getprop ro.product.brand; printf 'Android: '; getprop ro.build.version.release; printf '分辨率: '; wm size; printf '电量: '; dumpsys battery | grep level",
        ]
        self._show_device_log()
        self.device_output.setPlainText(f"正在读取设备信息...\n设备：{serial}")
        self._run_async(lambda: self.adb.run(info_args, serial), lambda result: self._show_result(self.device_output, result))

    def disconnect_current(self) -> None:
        if self._connection_busy:
            self.statusBar().showMessage("连接状态操作正在进行，请稍候…")
            return
        serial = self.current_serial()
        if not serial:
            return self._show_error("请先选择设备")
        device = next((item for item in self.devices if item.serial == serial), None)
        if not device or device.state != "device":
            self.statusBar().showMessage(f"设备已经离线 · {serial}")
            return
        if ":" not in serial:
            return self._show_error("这是 USB 设备。请拔出 USB，或在 ADB 设置中停止对应连接；adb disconnect 只适用于无线设备。")
        self._show_device_log()
        self.device_output.setPlainText(f"正在断开 {serial} ...")
        self._set_connection_busy(True, "断开中…")

        def done(result) -> None:
            self._show_result(self.device_output, result)
            if result.returncode == 0:
                self._pending_disconnects.add(serial)
                # Finish the button's signal delivery before replacing its
                # table cell. Rebuilding it inside the callback can delete a
                # Qt widget that is still on the event stack.
                QTimer.singleShot(0, lambda serial=serial: self._finish_disconnect(serial))
            else:
                self._set_connection_busy(False)

        self._run_async(lambda: self.adb.run(["disconnect", serial], timeout=20), done, self._finish_connection_error)

    def _finish_disconnect(self, serial: str) -> None:
        self._mark_device_offline(serial)
        self._set_connection_busy(False)
        self.statusBar().showMessage(f"设备已断开 · {serial}")

    def _mark_device_offline(self, serial: str) -> None:
        for index, device in enumerate(self.devices):
            if device.serial == serial:
                self.devices[index] = Device(serial=device.serial, state="offline", model=device.model)
                self._update_device_marker(serial)
                break

    def connect_history(self) -> None:
        if self._connection_busy:
            self.statusBar().showMessage("连接状态操作正在进行，请稍候…")
            return
        # The visible editor is authoritative. This lets users select an old
        # address, change it in place, and connect the new address without
        # overwriting the original history entry.
        address = self.history_combo.lineEdit().text().strip()
        if not address:
            return self._show_error("请输入无线调试地址")
        if ":" not in address:
            idx = self.device_combo.findData(address)
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)
                return
            return self._show_error("这是 USB 序列号。请插入设备后点击刷新；USB 设备不能使用 adb connect。")
        if not self._valid_wireless_address(address):
            return self._show_error("无线地址格式应为 IP:端口，例如 192.168.1.20:5555。端口必须在 1-65535 之间。")
        self._connect_wireless_address(address)

    def _connect_device_row(self, row: int) -> None:
        if not 0 <= row < len(self.devices):
            return
        device = self.devices[row]
        if ":" not in device.serial:
            return
        self._select_device_serial(device.serial)
        self._connect_wireless_address(device.serial)

    def _connect_wireless_address(self, address: str) -> None:
        if self._connection_busy:
            self.statusBar().showMessage("连接状态操作正在进行，请稍候…")
            return
        self._show_device_log()
        self.device_output.setPlainText(f"正在连接 {address} ...\nADB 路径：{self.resolver.resolve('adb') or '未找到'}")
        self._set_connection_busy(True)

        def done(result) -> None:
            self._set_connection_busy(False)
            self._handle_connect_result(address, result)

        self._run_async(lambda: self.adb.run(["connect", address], timeout=20), done, self._finish_connection_error)

    def _set_connection_busy(self, busy: bool, label: str = "连接中…") -> None:
        self._connection_busy = busy
        if hasattr(self, "device_table"):
            for row, device in enumerate(self.devices):
                actions = self.device_table.cellWidget(row, 3)
                if not actions:
                    continue
                for button in actions.findChildren(QToolButton):
                    enabled = device.state == "device"
                    action_name = button.property("actionName")
                    if action_name == "disconnect":
                        enabled = enabled and ":" in device.serial
                    elif action_name == "connect":
                        enabled = device.state == "offline" and ":" in device.serial
                    button.setEnabled(enabled and not busy)
        if not hasattr(self, "connect_button"):
            return
        self.connect_button.setEnabled(not busy)
        self.discovery_button.setEnabled(not busy)
        self.history_combo.setEnabled(not busy)
        self.connect_button.setText(label if busy else "连接设备")

    def _finish_connection_error(self, message: str) -> None:
        self._set_connection_busy(False)
        self._show_device_log()
        self.device_output.setPlainText(f"操作失败：{message}")
        self.statusBar().showMessage(f"ADB 操作失败 · {message}")

    def discover_wireless(self) -> None:
        if self._connection_busy:
            self.statusBar().showMessage("连接状态操作正在进行，请稍候…")
            return
        self._set_connection_busy(True, "发现中…")
        self.statusBar().showMessage("正在通过 ADB mDNS 发现无线设备…")

        def done(addresses: list[str]) -> None:
            self._set_connection_busy(False)
            self._show_device_log()
            if not addresses:
                self.device_output.setPlainText("未发现可连接的无线调试设备。\n请确认手机与电脑位于同一网络，并已开启无线调试。")
                self.statusBar().showMessage("自动发现完成 · 未发现设备")
                return
            for address in addresses:
                self.repo.remember(address, kind="wifi")
            self._reload_history()
            index = self.history_combo.findData(addresses[0])
            if index >= 0:
                self.history_combo.setCurrentIndex(index)
            self.device_output.setPlainText("已发现无线设备：\n" + "\n".join(f"• {item}" for item in addresses) + "\n\n选择地址后点击“连接设备”。")
            self.statusBar().showMessage(f"自动发现完成 · {len(addresses)} 个地址")

        self._run_async(self.adb.mdns_services, done, self._finish_connection_error)

    def _valid_wireless_address(self, address: str) -> bool:
        parts = str(address).rsplit(":", 1)
        if len(parts) != 2:
            return False
        host, port_text = parts
        if not host or not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
            return False
        try:
            ipaddress.ip_address(host.strip("[]"))
            return True
        except ValueError:
            return bool(host.replace("-", "").replace(".", "").isalnum())

    def _handle_connect_result(self, address: str, result) -> None:
        self._show_result(self.device_output, result)
        text = f"{result.stdout}\n{result.stderr}".lower()
        if result.returncode == 0 and ("connected to" in text or "already connected" in text):
            self._pending_disconnects.discard(address)
            self.repo.remember(address, kind="wifi")
            self._reload_history()
            self.refresh_devices()

    def remove_history(self, address: str = "") -> None:
        address = address or str(self.history_combo.currentData() or "")
        if address:
            current_row = self.history_combo.findData(address)
            self.repo.remove_history(address)
            remaining = [item.address for item in self.repo.histories() if item.kind == "wifi" or ":" in item.address]
            next_address = remaining[min(max(current_row, 0), len(remaining) - 1)] if remaining else ""
            self._reload_history(next_address)
            self.device_output.setPlainText(f"已删除连接历史：{address}\n设备本身不会被断开。")
            self.statusBar().showMessage(f"已删除连接记录 · {address}（设备连接不受影响）")

    def _history_selection_changed(self, index: int) -> None:
        if index < 0:
            return
        address = self.history_combo.itemData(index)
        if address and self.history_combo.lineEdit().text() != str(address):
            self.history_combo.lineEdit().setText(str(address))

    def _reload_history(self, selected_address: str | None = None) -> None:
        if not hasattr(self, "history_combo"): return
        if selected_address is None:
            selected_address = self.history_combo.lineEdit().text().strip()
        self.history_combo.blockSignals(True)
        self.history_combo.clear()
        for item in self.repo.histories():
            if item.kind == "wifi" or ":" in item.address:
                self.history_combo.addItem(item.label, item.address)
        if selected_address:
            selected_index = self.history_combo.findData(selected_address)
            if selected_index >= 0:
                self.history_combo.setCurrentIndex(selected_index)
                self.history_combo.lineEdit().setText(str(selected_address))
            else:
                self.history_combo.setCurrentIndex(-1)
                self.history_combo.lineEdit().setText(str(selected_address))
        elif self.history_combo.count():
            self.history_combo.setCurrentIndex(0)
            self.history_combo.lineEdit().setText(str(self.history_combo.itemData(0)))
        else:
            self.history_combo.setCurrentIndex(-1)
            self.history_combo.clearEditText()
        self.history_combo.blockSignals(False)

    def _shell_is_running(self, serial: str) -> bool:
        return bool(self.terminal_windows.get(serial))

    def _device_combo_text(self, device: Device) -> str:
        markers = []
        if self._shell_is_running(device.serial):
            markers.append("Shell 已连接")
        if self._scrcpy_is_running(device.serial):
            markers.append("Scrcpy 已连接")
        suffix = " · " + " · ".join(markers) if markers else ""
        return f"{device.label} · {device.state}{suffix}"

    def _update_device_shell_marker(self, serial: str) -> None:
        """Refresh one device label without changing the selected device."""
        self._update_device_marker(serial)

    def _update_device_marker(self, serial: str) -> None:
        """Refresh one device label without changing the selected device."""
        if not hasattr(self, "device_combo"):
            return
        index = self.device_combo.findData(serial)
        device = next((item for item in self.devices if item.serial == serial), None)
        if index >= 0 and device:
            self.device_combo.setItemText(index, self._device_combo_text(device))
            self._render_device_table()

    def start_scrcpy(self) -> None:
        serial = self.current_serial()
        if not serial: return self._show_error("请先选择设备")
        existing = self.scrcpy_processes.get(serial)
        if existing and existing.poll() is None:
            return self._show_error(f"{serial} 已经有一个 scrcpy 窗口在运行")
        # Row actions use the live settings and persist them automatically.
        self.repo.data.update({
            "scrcpy_path": self.scrcpy_path.text().strip(),
            "scrcpy_max_size": self.scrcpy_size.value(),
            "scrcpy_max_fps": self.scrcpy_fps.value(),
            "scrcpy_bitrate": self.scrcpy_bitrate.text().strip(),
            "scrcpy_extra": self.scrcpy_extra.text().strip(),
            "scrcpy_no_audio": self.scrcpy_no_audio.isChecked(),
        })
        self.repo.save()
        args = ["--serial", serial]
        if self.scrcpy_size.value(): args += ["--max-size", str(self.scrcpy_size.value())]
        if self.scrcpy_fps.value(): args += ["--max-fps", str(self.scrcpy_fps.value())]
        if self.scrcpy_bitrate.text().strip(): args += ["--video-bit-rate", self.scrcpy_bitrate.text().strip()]
        if self.scrcpy_no_audio.isChecked(): args.append("--no-audio")
        if self.scrcpy_extra.text().strip(): args += shlex.split(self.scrcpy_extra.text(), posix=False)
        try:
            process = ProcessRunner.start(self.resolver.resolve("scrcpy"), args)
            self.scrcpy_processes[serial] = ScrcpyHandle(process=process, serial=serial, log_callback=self._emit_scrcpy_log)
            self._update_scrcpy_status(serial)
            self.scrcpy_output.appendPlainText("启动：scrcpy " + " ".join(args))
            self.statusBar().showMessage(f"Scrcpy 已启动 · {serial}")
        except Exception as exc: self._show_error(str(exc))

    def stop_scrcpy(self) -> None:
        serial = self.current_serial()
        if not serial:
            return self._show_error("请先选择需要停止 scrcpy 的设备")
        process = self.scrcpy_processes.get(serial)
        if not process or process.poll() is not None:
            self.scrcpy_processes.pop(serial, None)
            self._update_scrcpy_status(serial)
            self.scrcpy_output.appendPlainText(f"{serial} 当前没有运行中的 scrcpy")
            self.statusBar().showMessage(f"{serial} 没有运行中的 Scrcpy")
            return
        process.terminate()
        self.scrcpy_processes.pop(serial, None)
        self._update_scrcpy_status(serial)
        self.scrcpy_output.appendPlainText(f"{serial} 的 scrcpy 已停止")
        self.statusBar().showMessage(f"Scrcpy 已停止 · {serial}")

    def _emit_scrcpy_log(self, serial: str, line: str) -> None:
        self.scrcpy_log.emit(f"[{serial}] {line}")

    def _append_scrcpy_log(self, line: str) -> None:
        if hasattr(self, "scrcpy_output"):
            self.scrcpy_output.appendPlainText(line)

    def closeEvent(self, event) -> None:
        # scrcpy is an independent native window. Do not terminate its
        # processes when ADBLite exits; they remain usable on their devices.
        self.scrcpy_processes.clear()
        if self.shell_process and self.shell_process.state() != QProcess.ProcessState.NotRunning:
            self.shell_process.terminate()
        for process in list(self.shell_processes.values()):
            if process.state() != QProcess.ProcessState.NotRunning:
                process.terminate()
        self.shell_processes.clear()
        for terminal in list(self.terminal_windows.values()):
            terminal.close()
        self.terminal_windows.clear()
        super().closeEvent(event)

    def _discover_scrcpy_processes(self) -> None:
        """Import scrcpy windows launched before ADBLite started (Windows)."""
        if sys.platform != "win32":
            return
        command = "Get-CimInstance Win32_Process -Filter \"Name='scrcpy.exe'\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
        try:
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5, creationflags=ProcessRunner._hidden_window_flags())
            payload = json.loads(result.stdout) if result.stdout.strip() else []
            if isinstance(payload, dict):
                payload = [payload]
            for item in payload:
                cmdline = str(item.get("CommandLine") or "")
                match = re.search(r"(?:--serial(?:=|\s+)|-s\s+)(?:\"([^\"]+)\"|(\S+))", cmdline)
                serial = (match.group(1) or match.group(2)) if match else ""
                pid = int(item.get("ProcessId")) if item.get("ProcessId") else 0
                if serial and pid:
                    self.scrcpy_processes.setdefault(serial, ScrcpyHandle(pid=pid))
                    self.scrcpy_output.appendPlainText(f"已识别已有 scrcpy：{serial} (PID {pid})")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass

    def _reload_commands(self) -> None:
        self.command_list.clear()
        for command in self.repo.commands(): self.command_list.addItem(command.name)

    def load_command(self, index: int) -> None:
        commands = self.repo.commands()
        if 0 <= index < len(commands):
            command = commands[index]; self.cmd_name.setText(command.name); self.cmd_runner.setCurrentText(command.runner); self.cmd_args.setPlainText(command.command if command.runner == "cmd" else "\n".join(command.args))

    def new_command(self) -> None:
        """Clear the current selection and prepare the editor for a new item."""
        self.command_list.blockSignals(True)
        self.command_list.clearSelection()
        self.command_list.setCurrentRow(-1)
        self.command_list.blockSignals(False)
        self.cmd_name.clear()
        self.cmd_runner.setCurrentText("cmd")
        self.cmd_args.clear()
        self.cmd_name.setFocus()

    def save_command(self) -> None:
        name = self.cmd_name.text().strip()
        if not name: return self._show_error("命令名称不能为空")
        commands = self.repo.commands(); row = self.command_list.currentRow(); runner = self.cmd_runner.currentText(); text = self.cmd_args.toPlainText(); command = CustomCommand(name=name, runner=runner, command=text if runner == "cmd" else "", args=[] if runner == "cmd" else [line for line in text.splitlines() if line.strip()])
        if 0 <= row < len(commands): commands[row] = command
        else: commands.append(command)
        self.repo.save_commands(commands); self._reload_commands()

    def delete_command(self) -> None:
        row = self.command_list.currentRow(); commands = self.repo.commands()
        if 0 <= row < len(commands): commands.pop(row); self.repo.save_commands(commands); self._reload_commands()

    def run_command(self) -> None:
        row = self.command_list.currentRow(); commands = self.repo.commands()
        if not (0 <= row < len(commands)): return self._show_error("请先选择命令")
        command = commands[row]; serial = self.current_serial()
        if command.runner == "adb": fn = lambda: self.adb.run(command.args, serial)
        elif command.runner == "scrcpy":
            scrcpy_target = ["--serial", serial] if serial else []
            fn = lambda: ProcessRunner.run(self.resolver.resolve("scrcpy"), [*scrcpy_target, *command.args])
        elif command.runner == "process": fn = lambda: ProcessRunner.run(command.args[0], command.args[1:])
        else:
            rendered = command.command.replace("${serial}", serial).replace("${adb}", self.resolver.resolve("adb")).replace("${scrcpy}", self.resolver.resolve("scrcpy"))
            cmdline = rendered.strip()
            # A quoted executable path (especially one containing spaces) is
            # best launched directly. Passing it through ``cmd /c`` via a
            # subprocess argument list escapes the quotes on Windows, causing
            # cmd.exe to report that the command is not recognized.
            direct = re.match(r'^\s*"([^"\r\n]+)"(?:\s+(.*))?\s*$', cmdline, re.S)
            shell_operators = ("&&", "||", "|", ">", "<")
            if direct and not any(operator in cmdline for operator in shell_operators):
                executable = direct.group(1)
                argument_text = direct.group(2) or ""
                arguments = split_local_process_arguments(argument_text)
                fn = lambda: self._launch_local_process(executable, arguments)
            else:
                fn = lambda: ProcessRunner.run("cmd.exe", ["/d", "/s", "/c", cmdline])
        self._run_async(fn, lambda result: self._show_result(self.command_output, result))

    @staticmethod
    def _launch_local_process(executable: str, arguments: list[str]) -> subprocess.CompletedProcess:
        """Start a local GUI process without waiting for it to exit."""
        flags = ProcessRunner._hidden_window_flags() | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(
            [executable, *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
        return subprocess.CompletedProcess([executable, *arguments], 0, "", "")

    def _show_result(self, target: QPlainTextEdit, result) -> None:
        target.appendPlainText(f"退出码：{result.returncode}\n{result.stdout}{result.stderr}".strip())

    def _input(self, title: str, placeholder: str, initial: str = ""):
        dialog = QDialog(self); dialog.setWindowTitle(title); layout = QFormLayout(dialog); field = QLineEdit(initial); field.setPlaceholderText(placeholder); layout.addRow("地址", field); buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addRow(buttons); ok = dialog.exec() == QDialog.DialogCode.Accepted; return field.text(), ok

    def _notice(self, message: str) -> None: QMessageBox.information(self, "ADBLite", message)
    def _show_error(self, message: str) -> None: QMessageBox.critical(self, "ADBLite", message)
