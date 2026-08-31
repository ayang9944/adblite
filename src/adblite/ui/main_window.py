from __future__ import annotations

import shlex
import subprocess
import ipaddress
import json
import re
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QProcess, QThread, QTimer, Signal, Qt
from PySide6.QtGui import QAction, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QStackedWidget,
    QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from ..domain import ConnectionHistory, CustomCommand, Device
from ..infrastructure import AdbClient, BinaryResolver, ProcessRunner, SettingsRepository

GITHUB_PROJECT_URL = "https://github.com/ayang9944/adblite"
APP_VERSION = "0.1.1"

DARK_STYLE = """
* { font-family: \"Segoe UI\", \"Microsoft YaHei UI\", sans-serif; font-size: 13px; }
QMainWindow, QWidget { background: #111827; color: #E5E7EB; }
#topbar { background: #111827; border-bottom: 1px solid #2B3950; }
#brand { color: #F8FAFC; font-size: 19px; font-weight: 700; }
#brandMark { background: #2563EB; color: white; border-radius: 8px; font-size: 16px; font-weight: 800; min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; }
#brandName { background: transparent; color: #F8FAFC; font-size: 18px; font-weight: 700; }
#subtitle { color: #94A3B8; font-size: 11px; }
#pageTitle { color: #F8FAFC; font-size: 20px; font-weight: 700; }
#pageHint { color: #94A3B8; font-size: 12px; }
#primaryButton { background: #2563EB; border-color: #3B82F6; color: white; font-weight: 600; }
#primaryButton:hover { background: #1D4ED8; }
#dangerButton { background: #3A2028; border-color: #7F1D1D; color: #FCA5A5; }
#dangerButton:hover { background: #7F1D1D; color: white; }
#statusLabel { background: #172033; border: 1px solid #2B3950; border-radius: 6px; padding: 7px 10px; color: #93C5FD; }
#sidebar { background: #151E2E; border: none; padding: 12px 8px; }
#sidebar::item { padding: 12px 14px; margin: 2px 0; border-radius: 7px; color: #94A3B8; }
#sidebar::item:hover { background: #202C41; color: #E2E8F0; }
#sidebar::item:selected { background: #2563EB; color: white; font-weight: 600; }
QComboBox, QLineEdit, QSpinBox, QPlainTextEdit, QListWidget { background: #182235; border: 1px solid #334155; border-radius: 6px; padding: 7px; color: #E5E7EB; }
QComboBox { font-size: 15px; min-height: 22px; }
QComboBox QAbstractItemView { font-size: 15px; padding: 5px; }
QComboBox:hover, QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus { border-color: #3B82F6; }
QPushButton { background: #263449; border: 1px solid #3B4A61; border-radius: 6px; padding: 8px 14px; color: #E5E7EB; }
QPushButton:hover { background: #334766; border-color: #60A5FA; }
QPushButton:pressed { background: #1D4ED8; }
#themeToggleButton { background: #1E293B; border-color: #475569; padding-left: 11px; padding-right: 11px; }
#themeToggleButton:hover { background: #334155; border-color: #60A5FA; }
#shellPrompt { color: #93C5FD; font-family: Consolas, "Cascadia Mono", monospace; font-size: 15px; font-weight: 700; min-width: 16px; }
#projectLink { color: #60A5FA; }
QGroupBox { border: 1px solid #2B3950; border-radius: 8px; margin-top: 12px; padding: 14px 10px 10px; font-weight: 600; color: #CBD5E1; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; background: #111827; }
QListWidget::item { padding: 9px 8px; border-radius: 5px; }
QListWidget::item:selected { background: #1D4ED8; color: white; }
QSplitter::handle { background: #334155; height: 5px; }
QScrollBar:vertical { background: #111827; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #475569; border-radius: 5px; min-height: 25px; }
QPlainTextEdit { font-family: Consolas, \"Cascadia Mono\", monospace; font-size: 12px; }
QStatusBar { background: #0F172A; color: #94A3B8; }
"""

ANSI_ESCAPE_RE = re.compile(r"\x1B(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1B\\))")

LIGHT_STYLE = DARK_STYLE.replace("#111827", "#F4F7FB").replace("#182235", "#FFFFFF").replace("#151E2E", "#E9EEF6").replace("#202C41", "#DCE7F5").replace("#2B3950", "#CBD5E1").replace("#334155", "#B8C4D4").replace("#263449", "#E7EDF5").replace("#3B4A61", "#AAB8CA").replace("#E5E7EB", "#1F2937").replace("#F8FAFC", "#0F172A").replace("#94A3B8", "#64748B").replace("#CBD5E1", "#334155").replace("#1D4ED8", "#1D4ED8").replace("#0F172A", "#E2E8F0")
# Keep the shortcut visually integrated with either palette.
LIGHT_STYLE += "\n#themeToggleButton { background: #FFFFFF; border-color: #AAB8CA; color: #1F2937; }\n#themeToggleButton:hover { background: #E7EDF5; border-color: #3B82F6; }\n"
LIGHT_STYLE += "#brand, #brandName, #pageTitle { color: #0F172A; }\n#pageHint, #subtitle { color: #64748B; }\nQGroupBox { color: #334155; }\n"


class Job(QObject):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as exc:  # UI boundary: display the process error
            self.failed.emit(str(exc))


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
        self.shell_privileged: dict[str, bool] = {}
        self.shell_logs: dict[str, str] = {}
        self.shell_terminal_lines: dict[str, tuple[str, int]] = {}
        self.shell_process: QProcess | None = None
        self.shell_serial = ""
        self._last_selected_serial = ""
        self._threads: set[QThread] = set()
        self._jobs: set[Job] = set()
        self.setWindowTitle(f"ADBLite v{APP_VERSION} — ADB · Scrcpy · 快捷命令")
        self.resize(1100, 720)
        self._build_ui()
        self.scrcpy_log.connect(self._append_scrcpy_log)
        self._discover_scrcpy_processes()
        self.refresh_devices()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_devices)
        self.timer.start(2500)

    def _build_ui(self) -> None:
        self.apply_theme(self.repo.data.get("theme", "dark"))
        root = QWidget(); root.setObjectName("root")
        layout = QVBoxLayout(root); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        topbar = QWidget(); topbar.setObjectName("topbar")
        header = QHBoxLayout(topbar); header.setContentsMargins(20, 10, 20, 10); header.setSpacing(0)
        brand_wrap = QWidget(); brand_wrap.setFixedWidth(178)
        brand_layout = QHBoxLayout(brand_wrap); brand_layout.setContentsMargins(2, 0, 0, 0); brand_layout.setSpacing(10)
        brand = QLabel("ADBLite"); brand.setObjectName("brandName")
        brand_layout.addWidget(brand, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter); header.addWidget(brand_wrap)
        current_label = QLabel("当前设备"); current_label.setObjectName("pageTitle"); header.addWidget(current_label); header.addSpacing(12)
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(420)
        self.device_combo.currentIndexChanged.connect(self._device_changed)
        header.addWidget(self.device_combo, 1)
        refresh = QPushButton("⟳  刷新"); refresh.setObjectName("primaryButton")
        refresh.clicked.connect(self.refresh_devices)
        header.addWidget(refresh)
        header.addSpacing(8)
        self.theme_toggle = QPushButton()
        self.theme_toggle.setObjectName("themeToggleButton")
        self.theme_toggle.setMinimumWidth(108)
        self.theme_toggle.setToolTip("切换日间/夜间模式")
        self.theme_toggle.setAccessibleName("主题模式切换")
        self.theme_toggle.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_toggle)
        self._update_theme_toggle()
        layout.addWidget(topbar)

        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        self.navigation = QListWidget(); self.navigation.setObjectName("sidebar"); self.navigation.setFixedWidth(178)
        for item in ("⌂   设备", "▣   Scrcpy", ">_  Shell", "⚡  快捷命令", "⚙   设置"):
            self.navigation.addItem(item)
        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self._devices_page()); self.page_stack.addWidget(self._scrcpy_page()); self.page_stack.addWidget(self._shell_page()); self.page_stack.addWidget(self._commands_page()); self.page_stack.addWidget(self._settings_page())
        self.navigation.currentRowChanged.connect(self.page_stack.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        body.addWidget(self.navigation); body.addWidget(self.page_stack, 1)
        layout.addLayout(body, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("ADB 就绪 · 等待设备刷新")

    def _devices_page(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(12)
        title = QLabel("设备管理"); title.setObjectName("pageTitle"); layout.addWidget(title)
        hint = QLabel("连接、选择并管理 ADB 设备"); hint.setObjectName("pageHint"); layout.addWidget(hint)
        self.device_list = QListWidget()
        self.device_list.currentRowChanged.connect(self._select_device_row)
        device_group = QWidget(); device_group_layout = QVBoxLayout(device_group); device_group_layout.setContentsMargins(0, 0, 0, 0)
        device_group_layout.addWidget(QLabel("已连接设备")); device_group_layout.addWidget(self.device_list)
        actions = QHBoxLayout()
        for text, fn in [("设备信息", self.show_device_info), ("重启系统", lambda: self.confirm_reboot(False)), ("重启 Recovery", lambda: self.confirm_reboot(True)), ("断开连接", self.disconnect_current)]:
            button = QPushButton(text); button.clicked.connect(fn)
            if text == "设备信息": button.setObjectName("primaryButton")
            if text == "断开连接": button.setObjectName("dangerButton")
            actions.addWidget(button)
        layout.addLayout(actions)
        self.device_output = QPlainTextEdit(); self.device_output.setReadOnly(True)
        log_group = QWidget(); log_group_layout = QVBoxLayout(log_group); log_group_layout.setContentsMargins(0, 0, 0, 0)
        log_header = QHBoxLayout(); log_header.addWidget(QLabel("操作日志")); log_header.addStretch()
        copy_log = QPushButton("复制"); copy_log.clicked.connect(lambda: QApplication.clipboard().setText(self.device_output.toPlainText()))
        clear_log = QPushButton("清空"); clear_log.clicked.connect(self.device_output.clear)
        log_header.addWidget(copy_log); log_header.addWidget(clear_log); log_group_layout.addLayout(log_header); log_group_layout.addWidget(self.device_output)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(device_group); splitter.addWidget(log_group)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 1); splitter.setSizes([360, 150])
        layout.addWidget(splitter, 1)

        history_box = QGroupBox("连接历史（断开后仍保留）")
        history_layout = QVBoxLayout(history_box)
        row = QHBoxLayout()
        self.history_combo = QComboBox(); row.addWidget(self.history_combo, 1)
        connect = QPushButton("连接"); connect.setObjectName("primaryButton"); connect.clicked.connect(self.connect_history); row.addWidget(connect)
        copy = QPushButton("复制"); copy.clicked.connect(self.copy_history); row.addWidget(copy)
        edit = QPushButton("编辑"); edit.clicked.connect(self.edit_history); row.addWidget(edit)
        remove = QPushButton("删除"); remove.setObjectName("dangerButton"); remove.clicked.connect(self.remove_history); row.addWidget(remove)
        history_layout.addLayout(row)
        add = QPushButton("添加无线地址")
        add.clicked.connect(self.add_history)
        history_layout.addWidget(add, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(history_box)
        self._reload_history()
        return page

    def _scrcpy_page(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(12)
        title = QLabel("Scrcpy 控制台"); title.setObjectName("pageTitle"); layout.addWidget(title)
        hint = QLabel("为当前设备配置画面参数并管理独立投屏会话"); hint.setObjectName("pageHint"); layout.addWidget(hint)
        content = QHBoxLayout(); content.setSpacing(14)
        settings_box = QGroupBox("投屏配置"); form = QFormLayout(settings_box); settings_box.setMaximumWidth(390)
        self.scrcpy_size = QSpinBox(); self.scrcpy_size.setRange(0, 8192); self.scrcpy_size.setValue(1920)
        self.scrcpy_fps = QSpinBox(); self.scrcpy_fps.setRange(0, 240); self.scrcpy_fps.setValue(60)
        self.scrcpy_bitrate = QLineEdit("8M")
        self.scrcpy_extra = QLineEdit()
        self.scrcpy_no_audio = QPushButton("禁用音频：否"); self.scrcpy_no_audio.setCheckable(True)
        self.scrcpy_no_audio.toggled.connect(lambda checked: self.scrcpy_no_audio.setText(f"禁用音频：{'是' if checked else '否'}"))
        form.addRow("最大尺寸", self.scrcpy_size); form.addRow("最大 FPS", self.scrcpy_fps); form.addRow("码率", self.scrcpy_bitrate); form.addRow("附加参数", self.scrcpy_extra); form.addRow(self.scrcpy_no_audio)
        buttons = QHBoxLayout(); start = QPushButton("启动 Scrcpy"); start.setObjectName("primaryButton"); start.clicked.connect(self.start_scrcpy); stop = QPushButton("停止当前设备"); stop.setObjectName("dangerButton"); stop.clicked.connect(self.stop_scrcpy); buttons.addWidget(start); buttons.addWidget(stop); form.addRow(buttons)
        log_box = QGroupBox("会话日志"); log_layout = QVBoxLayout(log_box)
        self.scrcpy_output = QPlainTextEdit(); self.scrcpy_output.setReadOnly(True)
        log_tools = QHBoxLayout(); log_tools.addStretch(); copy_log = QPushButton("复制日志"); copy_log.clicked.connect(lambda: QApplication.clipboard().setText(self.scrcpy_output.toPlainText())); clear_log = QPushButton("清空"); clear_log.clicked.connect(self.scrcpy_output.clear); log_tools.addWidget(copy_log); log_tools.addWidget(clear_log); log_layout.addLayout(log_tools)
        log_layout.addWidget(self.scrcpy_output)
        content.addWidget(settings_box); content.addWidget(log_box, 1); layout.addLayout(content, 1)
        return page

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
        save = QPushButton("保存"); save.clicked.connect(self.save_command)
        run = QPushButton("运行"); run.setObjectName("primaryButton"); run.clicked.connect(self.run_command)
        delete = QPushButton("删除"); delete.setObjectName("dangerButton"); delete.clicked.connect(self.delete_command)
        for button in (save, run, delete):
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
        hint = QLabel("连接当前设备的持久 ADB Shell 会话（伪终端模式，支持列布局和交互式命令）"); hint.setObjectName("pageHint"); layout.addWidget(hint)
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
        box = QGroupBox("运行环境"); form = QFormLayout(box); layout.addWidget(box); layout.addStretch()
        self.theme_combo = QComboBox(); self.theme_combo.addItem("夜间模式", "dark"); self.theme_combo.addItem("日间模式", "light"); self.theme_combo.setCurrentIndex(0 if self.repo.data.get("theme", "dark") == "dark" else 1); self.theme_combo.currentIndexChanged.connect(lambda: self.apply_theme(self.theme_combo.currentData()))
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
        return page

    def pick_binary(self, field: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择可执行文件", filter="Executable (*.exe);;All files (*)")
        if path: field.setText(path)

    def save_settings(self) -> None:
        self.repo.data["adb_path"] = self.adb_path.text().strip(); self.repo.data["scrcpy_path"] = self.scrcpy_path.text().strip(); self.repo.data["theme"] = self.theme_combo.currentData(); self.repo.save(); self._notice("设置已保存")

    def apply_theme(self, theme: str) -> None:
        theme = "light" if theme == "light" else "dark"
        self.setStyleSheet(LIGHT_STYLE if theme == "light" else DARK_STYLE)
        if hasattr(self, "repo"):
            self.repo.data["theme"] = theme
            self.repo.save()
        if hasattr(self, "theme_combo"):
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(1 if theme == "light" else 0)
            self.theme_combo.blockSignals(False)
        self._update_theme_toggle()

    def _toggle_theme(self) -> None:
        current = self.repo.data.get("theme", "dark")
        self.apply_theme("light" if current == "dark" else "dark")

    def _update_theme_toggle(self) -> None:
        """Update the shortcut label to describe the mode it will switch to."""
        if not hasattr(self, "theme_toggle"):
            return
        is_dark = self.repo.data.get("theme", "dark") == "dark"
        self.theme_toggle.setText("☀ 日间模式" if is_dark else "☾ 夜间模式")

    def _run_async(self, fn, on_done, on_failed=None) -> None:
        thread = QThread(self); job = Job(fn); job.moveToThread(thread); thread.started.connect(job.run); job.done.connect(on_done); job.failed.connect(on_failed or self._show_error); job.done.connect(thread.quit); job.failed.connect(thread.quit); thread.finished.connect(job.deleteLater); thread.finished.connect(thread.deleteLater)
        self._threads.add(thread)
        self._jobs.add(job)
        thread.finished.connect(lambda: self._threads.discard(thread))
        thread.finished.connect(lambda: self._jobs.discard(job))
        thread.start()

    def refresh_devices(self) -> None:
        self._run_async(self.adb.devices, self._set_devices, self._show_device_error)

    def _show_device_error(self, message: str) -> None:
        self.statusBar().showMessage("ADB 刷新失败")

    def _set_devices(self, devices: list[Device]) -> None:
        old_active = {device.serial for device in self.devices if device.state == "device"}
        new_active = {device.serial for device in devices if device.state == "device"}
        for serial in old_active - new_active:
            process = self.scrcpy_processes.get(serial)
            if process and process.poll() is None:
                self.scrcpy_log.emit(f"[{serial}] ADB 连接已断开，等待 scrcpy 自行退出")
        self.devices = devices; previous = self.current_serial()
        self.statusBar().showMessage(f"ADB 已刷新 · {len(devices)} 台设备")
        self.device_combo.blockSignals(True); self.device_combo.clear(); self.device_list.clear()
        for device in devices:
            self.device_combo.addItem(self._device_combo_text(device), device.serial)
            self.device_list.addItem(f"{device.label} [{device.state}]")
            if not self._initial_device_scan_done and device.state == "device":
                self.repo.remember(device.serial, kind="wifi" if ":" in device.serial else "usb")
        if previous:
            idx = self.device_combo.findData(previous)
            if idx >= 0: self.device_combo.setCurrentIndex(idx)
        self.device_combo.blockSignals(False)
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

    def _select_device_row(self, row: int) -> None:
        if 0 <= row < len(self.devices):
            index = self.device_combo.findData(self.devices[row].serial)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)

    def _device_changed(self) -> None:
        serial = self.current_serial()
        if serial:
            self.repo.remember(serial, kind="wifi" if ":" in serial else "usb")
            if hasattr(self, "shell_target"):
                previous_serial = self._last_selected_serial
                self._last_selected_serial = serial
                if previous_serial and previous_serial != serial:
                    target_process = self.shell_processes.get(serial)
                    target_state = target_process.state() if target_process else QProcess.ProcessState.NotRunning
                    target_note = "已有 Shell 会话" if target_state != QProcess.ProcessState.NotRunning else "尚未进入 Shell"
                    self._append_shell_log(serial, f"\n切换设备：{previous_serial} → {serial}（{target_note}，其他设备会话保持连接）\n")
                if self.shell_serial != serial:
                    self.shell_process = self.shell_processes.get(serial)
                    self.shell_serial = serial if self.shell_process and self.shell_process.state() != QProcess.ProcessState.NotRunning else ""
                self._update_shell_prompt(serial)
                if not self.shell_process or self.shell_process.state() == QProcess.ProcessState.NotRunning:
                    self.shell_target.setText(f"待连接设备：{serial}")
                else:
                    self.shell_target.setText(f"当前设备：{serial}")
                self._set_shell_log_view(serial)
            self._update_scrcpy_status(serial)
        else:
            self._set_shell_log_view("")
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
            self.shell_terminal_lines.pop(serial, None)
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
        self.shell_process = QProcess(self)
        setattr(self.shell_process, "_adblite_serial", serial)
        self.shell_processes[serial] = self.shell_process
        self.shell_process.setProgram(adb_path)
        # -tt forces a remote pseudo-terminal even though QProcess stdin is
        # not itself a console, so ls/curl behave as in an interactive shell.
        self.shell_process.setArguments(["-s", serial, "shell", "-tt"])
        # Keep stdout/stderr in the order produced by the remote terminal.
        self.shell_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.shell_process.readyReadStandardOutput.connect(self._read_shell_stdout)
        self.shell_process.finished.connect(self._shell_finished)
        self.shell_process.start()
        self._update_device_shell_marker(serial)
        self.shell_target.setText(f"当前设备：{serial}")
        self._append_shell_log(serial, f"$ adb -s {serial} shell -tt\nShell 已连接（伪终端模式），可以输入命令。\n")
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
            text = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
            if text:
                serial = next((key for key, value in self.shell_processes.items() if value is process), getattr(process, "_adblite_serial", self.shell_serial))
                self._append_shell_terminal_text(text, serial)

    def _append_shell_terminal_text(self, text: str, serial: str = "") -> None:
        """Render common terminal control sequences in the shell log."""
        text = ANSI_ESCAPE_RE.sub("", text)
        # QPlainTextEdit cannot overwrite a line on carriage return. Turning
        # progress updates into separate lines keeps curl and similar tools
        # readable instead of leaving control characters in the log.
        if not serial:
            serial = self.current_serial()
        if not serial:
            return
        line, cursor_pos = self.shell_terminal_lines.get(serial, ("", 0))
        emitted: list[str] = []
        prompt_re = re.compile(r"([\w.-]+:/[^\r\n]*?[#$]\s)")
        for char in text:
            if char == "\n":
                emitted.append(line + "\n")
                line, cursor_pos = "", 0
                continue
            if char == "\r":
                cursor_pos = 0
                continue
            if cursor_pos < len(line):
                line = line[:cursor_pos] + char + line[cursor_pos + 1:]
            else:
                line += char
            cursor_pos += 1
            match = prompt_re.search(line)
            if match and match.start() > 0:
                emitted.append(line[:match.start()] + "\n" + line[match.start():])
                line, cursor_pos = "", 0
            elif match and match.start() == 0 and match.end() == len(line):
                # A complete prompt can be displayed immediately even though
                # interactive shells do not terminate it with LF.
                emitted.append(line + "\n")
                line, cursor_pos = "", 0
        self.shell_terminal_lines[serial] = (line, cursor_pos)
        if emitted:
            self._append_shell_log(serial, "".join(emitted))

    def _read_shell_stderr(self) -> None:
        process = self.sender()
        if isinstance(process, QProcess):
            text = bytes(process.readAllStandardError()).decode("utf-8", errors="replace")
            if text:
                serial = next((key for key, value in self.shell_processes.items() if value is process), getattr(process, "_adblite_serial", self.shell_serial))
                self._append_shell_terminal_text(text, serial)

    def _shell_finished(self, exit_code: int, _status) -> None:
        process = self.sender()
        serial = next((key for key, value in self.shell_processes.items() if value is process), getattr(process, "_adblite_serial", ""))
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
        self.device_output.setPlainText(f"正在读取设备信息...\n设备：{serial}")
        self._run_async(lambda: self.adb.run(info_args, serial), lambda result: self._show_result(self.device_output, result))

    def disconnect_current(self) -> None:
        serial = self.current_serial()
        if not serial:
            return self._show_error("请先选择设备")
        if ":" not in serial:
            return self._show_error("这是 USB 设备。请拔出 USB，或在 ADB 设置中停止对应连接；adb disconnect 只适用于无线设备。")
        self.device_output.setPlainText(f"正在断开 {serial} ...")
        try:
            result = self.adb.run(["disconnect", serial], timeout=20)
            self._show_result(self.device_output, result)
            if result.returncode == 0:
                self.refresh_devices()
        except Exception as exc:
            self._show_device_error(str(exc))

    def connect_history(self) -> None:
        if self.history_combo.currentIndex() < 0: return
        address = self.history_combo.currentData()
        if ":" not in address:
            idx = self.device_combo.findData(address)
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)
                return
            return self._show_error("这是 USB 序列号。请插入设备后点击刷新；USB 设备不能使用 adb connect。")
        if not self._valid_wireless_address(address):
            return self._show_error("无线地址格式应为 IP:端口，例如 192.168.1.20:5555。端口必须在 1-65535 之间。")
        self.device_output.setPlainText(f"正在连接 {address} ...\nADB 路径：{self.resolver.resolve('adb') or '未找到'}")
        try:
            result = self.adb.run(["connect", address], timeout=20)
            self._handle_connect_result(address, result)
        except Exception as exc:
            self._show_device_error(str(exc))

    def _valid_wireless_address(self, address: str) -> bool:
        parts = str(address).rsplit(":", 1)
        if len(parts) != 2:
            return False
        host, port_text = parts
        if not host or not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
            return False
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return bool(host.replace("-", "").replace(".", "").isalnum())

    def _handle_connect_result(self, address: str, result) -> None:
        self._show_result(self.device_output, result)
        text = f"{result.stdout}\n{result.stderr}".lower()
        if result.returncode == 0 and ("connected to" in text or "already connected" in text):
            self.repo.remember(address, kind="wifi")
            self._reload_history()
            self.refresh_devices()

    def add_history(self) -> None:
        address, ok = self._input("无线地址", "例如 192.168.1.20:5555")
        if ok and address.strip(): self.repo.remember(address.strip()); self._reload_history()

    def remove_history(self) -> None:
        address = self.history_combo.currentData()
        if address:
            online = next((device for device in self.devices if device.serial == address), None)
            if online and online.state == "device":
                return self._show_error(f"设备 {address} 当前已连接，不能删除连接历史。请先断开设备后再删除。")
            self.repo.remove_history(address)
            self._reload_history()
            self.device_output.setPlainText(f"已删除连接历史：{address}\n设备本身不会被断开。")

    def copy_history(self) -> None:
        address = self.history_combo.currentData()
        if address:
            QApplication.clipboard().setText(str(address))
            self.device_output.setPlainText(f"已复制连接地址：{address}")

    def edit_history(self) -> None:
        old_address = self.history_combo.currentData()
        if not old_address:
            return self._show_error("请先选择一条连接历史")
        online = next((device for device in self.devices if device.serial == old_address), None)
        if online and online.state == "device":
            return self._show_error(f"设备 {old_address} 当前已连接，不能编辑地址。请先断开设备后再编辑。")
        new_address, ok = self._input("编辑连接地址", "例如 192.168.1.20:5555", str(old_address))
        new_address = new_address.strip()
        if not ok or new_address == old_address:
            return
        if not self._valid_wireless_address(new_address):
            return self._show_error("无线地址格式应为 IP:端口，例如 192.168.1.20:5555。端口必须在 1-65535 之间。")
        if any(item.address == new_address for item in self.repo.histories()):
            return self._show_error("这个连接地址已经存在于历史记录中。")
        self.repo.update_history(str(old_address), new_address)
        self._reload_history()
        self.history_combo.setCurrentIndex(self.history_combo.findData(new_address))
        self.device_output.setPlainText(f"已修改连接地址：{old_address} → {new_address}")

    def _reload_history(self) -> None:
        if not hasattr(self, "history_combo"): return
        selected_address = self.history_combo.currentData()
        self.history_combo.blockSignals(True)
        self.history_combo.clear()
        for item in self.repo.histories(): self.history_combo.addItem(item.label, item.address)
        if selected_address:
            selected_index = self.history_combo.findData(selected_address)
            if selected_index >= 0:
                self.history_combo.setCurrentIndex(selected_index)
        self.history_combo.blockSignals(False)

    def _shell_is_running(self, serial: str) -> bool:
        process = self.shell_processes.get(serial)
        return bool(process and process.state() != QProcess.ProcessState.NotRunning)

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

    def start_scrcpy(self) -> None:
        serial = self.current_serial()
        if not serial: return self._show_error("请先选择设备")
        existing = self.scrcpy_processes.get(serial)
        if existing and existing.poll() is None:
            return self._show_error(f"{serial} 已经有一个 scrcpy 窗口在运行")
        # Persist the field even when the user starts directly without pressing Save.
        self.repo.data["scrcpy_path"] = self.scrcpy_path.text().strip()
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
            return
        process.terminate()
        self.scrcpy_processes.pop(serial, None)
        self._update_scrcpy_status(serial)
        self.scrcpy_output.appendPlainText(f"{serial} 的 scrcpy 已停止")

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
        if command.device_required and not serial: return self._show_error("该命令需要先选择设备")
        if command.runner == "adb": fn = lambda: self.adb.run(command.args, serial)
        elif command.runner == "scrcpy": fn = lambda: ProcessRunner.run(self.resolver.resolve("scrcpy"), ["--serial", serial, *command.args])
        elif command.runner == "process": fn = lambda: ProcessRunner.run(command.args[0], command.args[1:])
        else:
            rendered = command.command.replace("${serial}", serial).replace("${adb}", self.resolver.resolve("adb")).replace("${scrcpy}", self.resolver.resolve("scrcpy"))
            fn = lambda: ProcessRunner.run("cmd.exe", ["/d", "/s", "/c", rendered])
        self._run_async(fn, lambda result: self._show_result(self.command_output, result))

    def _show_result(self, target: QPlainTextEdit, result) -> None:
        target.appendPlainText(f"退出码：{result.returncode}\n{result.stdout}{result.stderr}".strip())

    def _input(self, title: str, placeholder: str, initial: str = ""):
        dialog = QDialog(self); dialog.setWindowTitle(title); layout = QFormLayout(dialog); field = QLineEdit(initial); field.setPlaceholderText(placeholder); layout.addRow("地址", field); buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addRow(buttons); ok = dialog.exec() == QDialog.DialogCode.Accepted; return field.text(), ok

    def _notice(self, message: str) -> None: QMessageBox.information(self, "ADBLite", message)
    def _show_error(self, message: str) -> None: QMessageBox.critical(self, "ADBLite", message)
