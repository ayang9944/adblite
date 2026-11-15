from __future__ import annotations

import secrets
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, QSize, Signal, Qt
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabBar,
    QStackedWidget,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..infrastructure import SettingsRepository
from ..phone_bridge import PhoneBridgeServer


def interface_icon(name: str) -> QIcon:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    return QIcon(str(base / "assets" / "icons" / f"{name}.svg"))


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
        # The parent tool workspace owns the horizontal gutter so the tool
        # navigation and the page content share exactly the same left edge.
        outer.setContentsMargins(0, 20, 0, 24)
        outer.setSpacing(14)

        header = QFrame(); header.setObjectName("toolHeader")
        header_layout = QHBoxLayout(header); header_layout.setContentsMargins(18, 14, 18, 14); header_layout.setSpacing(12)
        header_icon = QLabel(); header_icon.setPixmap(interface_icon("usb").pixmap(24, 24)); header_icon.setFixedSize(28, 28)
        header_layout.addWidget(header_icon, 0, Qt.AlignmentFlag.AlignTop)
        title = QLabel("手机桥接"); title.setObjectName("toolTitle"); header_layout.addWidget(title)
        header_layout.addStretch()
        self.service_toggle_button = QPushButton("启动"); self.service_toggle_button.setObjectName("serviceToggleButton"); self.service_toggle_button.setIcon(interface_icon("play")); self.service_toggle_button.setIconSize(QSize(16, 16)); self.service_toggle_button.setCursor(Qt.CursorShape.PointingHandCursor); self.service_toggle_button.clicked.connect(self._toggle_server); header_layout.addWidget(self.service_toggle_button, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(header)

        settings = QGroupBox("连接设置")
        settings.setObjectName("bridgeSettingsPanel")
        settings_layout = QFormLayout(settings)
        settings_layout.setContentsMargins(16, 22, 16, 14)
        settings_layout.setHorizontalSpacing(18)
        settings_layout.setVerticalSpacing(10)
        settings_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        settings_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        settings_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(0, 65535)
        self.port_spin.setValue(int(self.repo.data.get("phone_bridge_port", 8899)))
        self.port_spin.setMinimumWidth(180)
        self.port_spin.setToolTip("0 表示自动选择空闲端口")
        self.bind_edit = QLineEdit(str(self.repo.data.get("phone_bridge_bind", "0.0.0.0")))
        self.bind_edit.setMinimumWidth(260)
        self.bind_edit.setPlaceholderText("0.0.0.0")
        self.bind_edit.setToolTip("0.0.0.0 允许局域网手机访问；127.0.0.1 仅本机可访问")
        self.token_edit = QLineEdit(str(self.repo.data.get("phone_bridge_token", "")))
        self.token_edit.setMinimumWidth(260)
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
        content.setSpacing(14)
        pc_box = QFrame()
        pc_box.setObjectName("bridgePcBox")
        pc_layout = QVBoxLayout(pc_box); pc_layout.setContentsMargins(14, 14, 14, 14); pc_layout.setSpacing(10)
        pc_title = QLabel("电脑 → 手机"); pc_title.setObjectName("bridgePanelTitle"); pc_layout.addWidget(pc_title)
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

        received_box = QFrame()
        received_box.setObjectName("bridgeReceivedBox")
        received_layout = QVBoxLayout(received_box); received_layout.setContentsMargins(14, 14, 14, 14); received_layout.setSpacing(10)
        received_title = QLabel("手机 → 电脑"); received_title.setObjectName("bridgePanelTitle"); received_layout.addWidget(received_title)
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

        note = QLabel("安全提示：服务只传递文本，不提供 APK、文件或 ADB 命令接口。请仅把访问地址分享给可信设备。")
        note.setObjectName("fieldHint")
        outer.addWidget(note)

    def _toggle_server(self) -> None:
        if self.server and self.server.running:
            self.stop_server()
        else:
            self.start_server()

    def _set_service_state(self, running: bool) -> None:
        self.service_toggle_button.setText("停止" if running else "启动")
        self.service_toggle_button.setIcon(interface_icon("stop" if running else "play"))
        self.service_toggle_button.setProperty("running", running)
        self.service_toggle_button.style().unpolish(self.service_toggle_button)
        self.service_toggle_button.style().polish(self.service_toggle_button)

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
            self._set_service_state(False)
            self.status_message.emit(f"手机桥接启动失败：{exc}")
            return
        self.url_edit.setText(url)
        self.token_edit.setText(self.server.token)
        self._set_service_state(True)
        self.port_spin.setEnabled(False)
        self.bind_edit.setEnabled(False)
        self.token_edit.setEnabled(False)
        self.status_message.emit(f"手机桥接已启动 · {url}")

    def stop_server(self) -> None:
        if self.server:
            self.server.stop()
        self.server = None
        self._set_service_state(False)
        self.port_spin.setEnabled(True)
        self.bind_edit.setEnabled(True)
        self.token_edit.setEnabled(True)
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


class ToolPlaceholderPage(QWidget):
    """Visual placeholder for a tool whose backend is not wired yet."""

    def __init__(self, title: str, description: str, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("toolPlaceholder")
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 24, 24, 24); layout.setSpacing(10)
        layout.addStretch()
        icon = QLabel(); icon.setObjectName("placeholderIcon"); icon.setPixmap(interface_icon(icon_name).pixmap(28, 28)); icon.setFixedSize(52, 52); icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        heading = QLabel(title); heading.setObjectName("placeholderTitle"); heading.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(heading)
        hint = QLabel(description + "\n页面结构已预留，后续接入设备能力后可直接扩展。"); hint.setObjectName("toolSubtitle"); hint.setAlignment(Qt.AlignmentFlag.AlignCenter); hint.setWordWrap(True); layout.addWidget(hint, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()


class DeviceToolsPage(QWidget):
    """Tool workspace with a compact horizontal tool navigation."""

    def __init__(self, repo: SettingsRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("deviceToolsPage")
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 14, 24, 14); layout.setSpacing(12)
        nav_bar = QFrame(); nav_bar.setObjectName("toolNavBar")
        nav_layout = QHBoxLayout(nav_bar); nav_layout.setContentsMargins(14, 8, 14, 8); nav_layout.setSpacing(14)
        nav_title = QLabel("设备工具"); nav_title.setObjectName("toolNavTitle"); nav_layout.addWidget(nav_title)
        self.tool_navigation = QTabBar(); self.tool_navigation.setObjectName("toolNavTabs"); self.tool_navigation.setDocumentMode(True); self.tool_navigation.setDrawBase(False); self.tool_navigation.setExpanding(False); self.tool_navigation.setUsesScrollButtons(False); self.tool_navigation.setElideMode(Qt.TextElideMode.ElideNone); nav_layout.addWidget(self.tool_navigation, 1)
        layout.addWidget(nav_bar)
        self.tool_stack = QStackedWidget(); self.tool_stack.setObjectName("toolStack")
        self.phone_bridge_page = PhoneBridgePage(repo, self)
        tools = (
            ("手机桥接", "在电脑和手机之间传递文本", "usb", self.phone_bridge_page),
            ("应用管理", "安装、卸载和查看设备应用", "package", ToolPlaceholderPage("应用管理", "统一管理设备上的 APK 和应用包", "package", self)),
            ("文件管理", "浏览、上传和下载设备文件", "folder", ToolPlaceholderPage("文件管理", "浏览设备存储并管理文件", "folder", self)),
        )
        for title, description, icon_name, page in tools:
            index = self.tool_navigation.addTab(interface_icon(icon_name), title); self.tool_navigation.setTabToolTip(index, description)
            self.tool_stack.addWidget(page)
        self.tool_navigation.currentChanged.connect(self.tool_stack.setCurrentIndex)
        self.tool_navigation.setCurrentIndex(0)
        layout.addWidget(self.tool_stack, 1)

