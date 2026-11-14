from __future__ import annotations

import secrets
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..infrastructure import SettingsRepository
from ..phone_bridge import PhoneBridgeServer


class PhoneBridgePage(QWidget):
    """UI for the local authenticated PC↔phone text bridge."""

    status_message = Signal(str)

    def __init__(self, repo: SettingsRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.server: PhoneBridgeServer | None = None
        self._build_ui()
        self._refresh_received()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_received)
        self._timer.start(1000)

    def _build_ui(self) -> None:
        self.setObjectName("contentPage")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("手机桥接")
        title.setObjectName("emptyTitle")
        header.addWidget(title)
        hint = QLabel("通过局域网浏览器在电脑和手机之间传递文本")
        hint.setObjectName("pageHint")
        header.addWidget(hint)
        header.addStretch()
        self.status_label = QLabel("未启动")
        self.status_label.setObjectName("statusLabel")
        header.addWidget(self.status_label)
        outer.addLayout(header)

        settings = QGroupBox()
        settings.setObjectName("bridgeSettingsBox")
        settings_layout = QFormLayout(settings)
        settings_layout.addRow(QLabel("服务设置"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(0, 65535)
        self.port_spin.setValue(int(self.repo.data.get("phone_bridge_port", 8899)))
        self.port_spin.setToolTip("0 表示自动选择空闲端口")
        self.bind_edit = QLineEdit(str(self.repo.data.get("phone_bridge_bind", "0.0.0.0")))
        self.bind_edit.setPlaceholderText("0.0.0.0")
        self.bind_edit.setToolTip("0.0.0.0 允许局域网手机访问；127.0.0.1 仅本机可访问")
        self.token_edit = QLineEdit(str(self.repo.data.get("phone_bridge_token", "")))
        self.token_edit.setPlaceholderText("留空则自动生成；也可以自定义为 123456")
        self.token_edit.setToolTip("手机访问令牌。建议使用易输入但不容易猜到的短字符串")
        settings_layout.addRow("端口", self.port_spin)
        settings_layout.addRow("绑定地址", self.bind_edit)
        token_row = QHBoxLayout()
        token_row.addWidget(self.token_edit, 1)
        generate_token = QPushButton("随机生成")
        generate_token.clicked.connect(lambda: self.token_edit.setText(secrets.token_urlsafe(8)))
        token_row.addWidget(generate_token)
        settings_layout.addRow("访问令牌", token_row)
        service_row = QHBoxLayout()
        self.start_button = QPushButton("启动服务")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start_server)
        self.stop_button = QPushButton("停止服务")
        self.stop_button.setObjectName("dangerButton")
        self.stop_button.clicked.connect(self.stop_server)
        self.stop_button.setEnabled(False)
        service_row.addWidget(self.start_button)
        service_row.addWidget(self.stop_button)
        service_row.addStretch()
        settings_layout.addRow(service_row)
        self.url_edit = QLineEdit()
        self.url_edit.setReadOnly(True)
        self.url_edit.setPlaceholderText("启动后显示手机访问地址")
        url_row = QHBoxLayout()
        url_row.addWidget(self.url_edit, 1)
        copy_url = QPushButton("复制地址")
        copy_url.clicked.connect(self.copy_url)
        open_url = QPushButton("打开浏览器")
        open_url.clicked.connect(self.open_url)
        url_row.addWidget(copy_url)
        url_row.addWidget(open_url)
        settings_layout.addRow("访问地址", url_row)
        outer.addWidget(settings)

        content = QHBoxLayout()
        content.setSpacing(12)
        pc_box = QGroupBox("电脑 → 手机")
        pc_box.setObjectName("bridgePcBox")
        pc_layout = QVBoxLayout(pc_box)
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("输入或粘贴文本，手机打开地址后即可查看")
        self.text_edit.setMinimumHeight(180)
        pc_layout.addWidget(self.text_edit, 1)
        pc_actions = QHBoxLayout()
        save_text = QPushButton("保存并同步")
        save_text.setObjectName("primaryButton")
        save_text.clicked.connect(self.save_text)
        pc_actions.addWidget(save_text)
        pc_actions.addStretch()
        pc_layout.addLayout(pc_actions)
        content.addWidget(pc_box, 1)

        received_box = QGroupBox("手机 → 电脑")
        received_box.setObjectName("bridgeReceivedBox")
        received_layout = QVBoxLayout(received_box)
        self.received_edit = QPlainTextEdit()
        self.received_edit.setReadOnly(True)
        self.received_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.received_edit.setMinimumHeight(180)
        received_layout.addWidget(self.received_edit, 1)
        received_actions = QHBoxLayout()
        clear_received = QPushButton("清空记录")
        clear_received.clicked.connect(self.clear_received)
        received_actions.addWidget(clear_received)
        received_actions.addStretch()
        received_layout.addLayout(received_actions)
        content.addWidget(received_box, 1)
        outer.addLayout(content, 1)

        note = QLabel("提示：服务只传递文本，不提供 APK、文件或 ADB 命令接口。请仅把访问地址分享给可信设备。")
        note.setObjectName("pageHint")
        outer.addWidget(note)

    def _data_dir(self) -> Path:
        return self.repo.path.parent / "phone_bridge"

    def _save_config(self) -> None:
        self.repo.data["phone_bridge_port"] = self.port_spin.value()
        self.repo.data["phone_bridge_bind"] = self.bind_edit.text().strip() or "0.0.0.0"
        self.repo.data["phone_bridge_token"] = self.token_edit.text().strip()
        self.repo.save()

    def start_server(self) -> None:
        if self.server and self.server.running:
            return
        self._save_config()
        self.server = PhoneBridgeServer(
            self._data_dir(),
            bind_host=self.bind_edit.text().strip() or "0.0.0.0",
            port=self.port_spin.value(),
            access_token=self.token_edit.text().strip(),
        )
        try:
            url = self.server.start()
        except (OSError, ValueError) as exc:
            self.server = None
            self.status_label.setText("启动失败")
            self.status_message.emit(f"手机桥接启动失败：{exc}")
            return
        self.url_edit.setText(url)
        self.token_edit.setText(self.server.token)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.port_spin.setEnabled(False)
        self.bind_edit.setEnabled(False)
        self.token_edit.setEnabled(False)
        self.status_label.setText(f"运行中 · {self.server.port}")
        self.status_message.emit(f"手机桥接已启动 · {url}")

    def stop_server(self) -> None:
        if self.server:
            self.server.stop()
        self.server = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.port_spin.setEnabled(True)
        self.bind_edit.setEnabled(True)
        self.token_edit.setEnabled(True)
        self.status_label.setText("未启动")
        self.status_message.emit("手机桥接已停止")

    def save_text(self) -> None:
        if not self.server:
            self.server = PhoneBridgeServer(
                self._data_dir(),
                bind_host=self.bind_edit.text().strip() or "0.0.0.0",
                port=self.port_spin.value(),
                access_token=self.token_edit.text().strip(),
            )
        try:
            self.server.write_text(self.text_edit.toPlainText())
        except (OSError, ValueError) as exc:
            self.status_message.emit(f"保存桥接文本失败：{exc}")
            return
        self.status_message.emit("桥接文本已保存")

    def _refresh_received(self) -> None:
        bridge = self.server
        if bridge is None:
            bridge = PhoneBridgeServer(self._data_dir(), bind_host=self.bind_edit.text().strip() or "0.0.0.0", port=self.port_spin.value())
        text = bridge.read_text()
        if self.text_edit.toPlainText() != text and not self.text_edit.hasFocus():
            self.text_edit.setPlainText(text)
        received = bridge.read_received()
        if self.received_edit.toPlainText() != received:
            self.received_edit.setPlainText(received)
            scrollbar = self.received_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def clear_received(self) -> None:
        if self.server:
            self.server.clear_received()
        else:
            PhoneBridgeServer(self._data_dir()).clear_received()
        self._refresh_received()
        self.status_message.emit("已清空手机接收记录")

    def copy_url(self) -> None:
        if self.url_edit.text():
            QApplication.clipboard().setText(self.url_edit.text())
            self.status_message.emit("手机桥接地址已复制")

    def open_url(self) -> None:
        if self.url_edit.text():
            QDesktopServices.openUrl(QUrl(self.url_edit.text()))


class DeviceToolsPage(QTabWidget):
    """Container for device-related tools.

    The first tool is the LAN text bridge.  APK management and file transfer
    can be added as sibling tabs without expanding the top-level navigation.
    """

    def __init__(self, repo: SettingsRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("deviceToolsTabs")
        self.setDocumentMode(True)
        self.phone_bridge_page = PhoneBridgePage(repo, self)
        self.addTab(self.phone_bridge_page, "手机桥接")

