from __future__ import annotations

import codecs
import os
import shlex
import subprocess
import ipaddress
import json
import re
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QProcess, QRect, QSize, QTimer, Signal, Slot, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QHeaderView, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QSizePolicy, QSpinBox, QStackedWidget, QSplitter, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTabBar, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from ..domain import ConnectionHistory, CustomCommand, Device, merge_device_statuses, sort_devices_by_status
from ..infrastructure import AdbClient, BinaryResolver, ProcessRunner, SettingsRepository
from ..terminal import TerminalLogState, flush_terminal_log, render_terminal_log
from .phone_bridge_page import DeviceToolsPage
from .terminal_window import DeviceTerminalWindow

GITHUB_PROJECT_URL = "https://github.com/ayang9944/adblite"
APP_VERSION = "0.2.0"


def interface_asset_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    return base / "assets" / "icons" / f"{name}.svg"


def interface_icon(name: str) -> QIcon:
    return QIcon(str(interface_asset_path(name)))

DARK_STYLE = """
* { font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 13px; }
QMainWindow, QWidget { background: #111827; color: #E5E7EB; }
/* Text should sit on its parent surface instead of creating a separate
   rectangular fill behind every label.  Badges opt back into a background
   through their more specific object-name rules below. */
QLabel { background: transparent; }
#topbar { background: #151D2B; border: none; }
#brandName { color: #F8FAFC; font-size: 17px; font-weight: 700; padding-right: 12px; }
#navTabs { background: transparent; border: none; }
#navTabs::tab { background: transparent; color: #94A3B8; border: none; border-radius: 6px; padding: 9px 14px; margin: 7px 2px; min-width: 64px; font-size: 14px; font-weight: normal; }
#navTabs::tab:hover { color: #E2E8F0; background: #1C2738; }
#navTabs::tab:selected { color: #5EEAD4; background: #183B3A; font-weight: normal; border: none; }
#pageHint, #mutedLabel, #emptyHint { color: #94A3B8; font-size: 12px; }
#connectionLabel { color: #E5E7EB; font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 13px; font-weight: normal; }
#primaryButton { background: #0F8F83; border-color: #14B8A6; color: white; font-weight: 600; }
#primaryButton:hover { background: #0D9488; }
#dangerButton { color: #FDA4AF; }
#statusLabel { background: #172033; border: none; border-radius: 6px; padding: 7px 10px; color: #93C5FD; }
#onlineBadge { background: transparent; color: #6EE7B7; padding: 3px 0; font-weight: 600; }
#warningBadge { background: transparent; color: #FCD34D; padding: 3px 0; font-weight: 600; }
#offlineBadge { background: transparent; color: #94A3B8; padding: 3px 0; font-weight: 600; }
#devicesPage, #contentPage { background: #0F1724; }
#deviceSurface, #emptyPanel, #emptyPanel QLabel { background: transparent; border: none; }
#devicePanel, #operationPanel { background: #151F2E; border: none; border-radius: 9px; }
#connectionBar { background: #151F2E; border: none; border-radius: 9px; }
#emptyPanel { background: transparent; border: none; }
#operationLog { background: transparent; border: none; border-radius: 0; padding: 10px; font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 13px; }
#operationHeader { background: transparent; }
#logToggle { background: transparent; border: none; padding: 6px 10px; color: #94A3B8; font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 13px; font-weight: 600; }
#logToggle:hover { background: #1C2A3D; }
#sectionTitle { background: transparent; color: #94A3B8; font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 13px; font-weight: 600; padding: 0; }
#emptyTitle { color: #E2E8F0; font-size: 16px; font-weight: 600; }
#terminalHeader { background: #151D2B; border-bottom: 1px solid #273449; }
#terminalDevice { background: #183B3A; color: #5EEAD4; border: 1px solid #245B57; border-radius: 5px; padding: 4px 9px; }
#terminalSurface { background: #0B1220; color: #DCE7F5; border: none; border-radius: 0; padding: 10px; selection-background-color: #0F766E; font-family: Consolas, "Cascadia Mono", monospace; font-size: 13px; }
QComboBox, QLineEdit, QSpinBox, QPlainTextEdit, QListWidget { background: #182235; border: 1px solid #334155; border-radius: 6px; padding: 7px; color: #E5E7EB; }
QComboBox { min-height: 22px; padding-right: 38px; font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 13px; }
QComboBox QLineEdit { background: transparent; border: none; padding: 0; font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 13px; }
QComboBox QAbstractItemView { font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 13px; }
QComboBox QAbstractItemView::item { min-height: 34px; padding: 0 8px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 32px; background: #223046; border: none; border-left: 1px solid #334155; border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
QComboBox::drop-down:hover { background: #2C405B; }
QSpinBox { padding-right: 34px; }
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 28px; background: #223046; border: none; border-left: 1px solid #334155; border-bottom: 1px solid #334155; border-top-right-radius: 6px; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 28px; background: #223046; border: none; border-left: 1px solid #334155; border-bottom-right-radius: 6px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #2C405B; }
QComboBox:hover, QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus { border-color: #14B8A6; }
QPushButton, QToolButton { background: #223046; border: 1px solid #3B4A61; border-radius: 6px; padding: 7px 12px; color: #E5E7EB; }
QPushButton:hover, QToolButton:hover { background: #2C405B; border-color: #2DD4BF; }
QPushButton:disabled, QToolButton:disabled { color: #64748B; background: #1A2434; border-color: #2B3950; }
#iconButton, #rowAction { background: transparent; border: none; border-radius: 16px; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; padding: 0; }
#iconButton:hover, #rowAction:hover { background: #183B3A; border-color: #245B57; }
#rowAction::menu-indicator { image: none; width: 0; }
#shellPrompt { color: #5EEAD4; font-family: Consolas, "Cascadia Mono", monospace; font-size: 15px; font-weight: 700; min-width: 16px; }
#projectLink { color: #2DD4BF; }
QGroupBox { background: #151F2E; border: none; border-radius: 8px; margin-top: 0; padding: 0; color: #CBD5E1; }
QListWidget::item { padding: 9px 8px; border-radius: 5px; }
#commandList { outline: none; }
#commandList { background: transparent; border: none; padding: 0; }
#commandList::item { background: transparent; color: #94A3B8; border-radius: 8px; padding: 0; margin: 2px 0; }
#commandList::item:hover { background: #162238; color: #E2E8F0; }
#commandList::item:selected { background: #183B3A; color: #5EEAD4; border: none; outline: none; }
#commandRow { background: transparent; }
#commandRow QLabel { background: transparent; }
#commandRunnerMeta { color: #64748B; font-size: 11px; }
#commandDeleteButton { background: transparent; border: none; border-radius: 14px; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; padding: 0; }
#commandDeleteButton:hover { background: #3A2028; }
#deviceTable { background: transparent; border: none; border-radius: 0; gridline-color: transparent; selection-background-color: #1C2738; selection-color: #E5E7EB; }
#deviceTable::item { background: transparent; padding: 10px; border: none; }
#deviceTable::item:selected { background: #1C2738; color: #E5E7EB; }
#deviceIdentifierCell, #deviceStatusCell, #deviceActionsCell { background: transparent; }
#deviceIdentifierCell QLabel { background: transparent; }
QHeaderView::section { background: transparent; color: #94A3B8; border: none; padding: 10px; font-weight: 600; }
QSplitter::handle { background: transparent; height: 7px; }
#deviceSplitter { background: transparent; border: none; }
#deviceSplitter::handle { background: #0F1724; height: 8px; }
#deviceSplitter::handle:hover { background: #183B3A; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #475569; border-radius: 5px; min-height: 25px; }
QScrollBar::handle:vertical:hover { background: #64748B; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { background: transparent; border: none; height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QPlainTextEdit { font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; }
QStatusBar { background: #0F172A; color: #94A3B8; border: none; }
#deviceToolsTabs { background: transparent; border: none; }
#deviceToolsTabs::pane { background: transparent; border: none; }
#deviceToolsTabs::tab { background: transparent; color: #94A3B8; border: none; border-radius: 6px; padding: 8px 14px; margin: 4px 2px; }
#deviceToolsTabs::tab:selected { background: #183B3A; color: #5EEAD4; }
"""
DARK_STYLE += f"""
QComboBox::down-arrow {{ image: url("{interface_asset_path('chevron-down').as_posix()}"); width: 12px; height: 8px; }}
QSpinBox::up-arrow {{ image: url("{interface_asset_path('chevron-up').as_posix()}"); width: 10px; height: 7px; }}
QSpinBox::down-arrow {{ image: url("{interface_asset_path('chevron-down').as_posix()}"); width: 10px; height: 7px; }}
"""

DARK_STYLE += """
/* Application shell */
#appSidebar { background: #0B1220; border-right: 1px solid #1F2A3D; }
#sidebarBrand { color: #F8FAFC; font-size: 19px; font-weight: 700; }
#sidebarVersion { color: #64748B; font-size: 11px; }
#sidebarSection { color: #64748B; font-size: 11px; font-weight: 700; padding: 4px 10px; }
#navList { background: transparent; border: none; outline: none; padding: 4px 8px; }
#navList::item { color: #94A3B8; border-radius: 8px; padding: 11px 12px; margin: 2px 0; }
#navList::item:hover { background: #162238; color: #E2E8F0; }
#navList::item:selected { background: #183B3A; color: #5EEAD4; font-weight: 600; }
#sidebarStatus { background: #111B2C; border: 1px solid #24334A; border-radius: 8px; padding: 10px; }
#sidebarStatusTitle { color: #CBD5E1; font-size: 12px; font-weight: 600; }
#sidebarStatusText { color: #64748B; font-size: 11px; }
#topbar { background: #111827; border-bottom: 1px solid #1F2A3D; }
#pageTitle { color: #F8FAFC; font-size: 18px; font-weight: 700; }
#pageSubtitle { color: #94A3B8; font-size: 12px; }

/* Shared page primitives */
#contentPage, #devicesPage { background: #0F1724; }
#toolCard, #settingsCard, #commandCard, #toolHeader { background: #151F2E; border: 1px solid #223149; border-radius: 10px; }
#toolHeader { border-color: transparent; }
#toolTitle { color: #F8FAFC; font-size: 18px; font-weight: 700; }
#toolSubtitle { color: #94A3B8; font-size: 12px; }
#sectionTitle { color: #CBD5E1; font-size: 13px; font-weight: 700; }
#fieldHint { color: #64748B; font-size: 11px; }

/* Device tools */
#deviceToolsPage { background: #0F1724; }
#toolNavBar { background: transparent; border: none; border-bottom: 1px solid #334155; border-radius: 0; }
#toolNavTabs { background: transparent; border: none; }
#toolNavTabs::tab { background: transparent; color: #94A3B8; border: none; border-bottom: 2px solid transparent; padding: 9px 14px 8px; margin: 0 2px; }
#toolNavTabs::tab:hover { background: transparent; color: #E2E8F0; }
#toolNavTabs::tab:selected { background: transparent; color: #5EEAD4; border-bottom-color: #5EEAD4; font-weight: 600; }
#toolNavPanel { background: #111B2C; border: 1px solid #223149; border-radius: 10px; }
#toolNavTitle { color: #CBD5E1; font-size: 12px; font-weight: 700; }
#toolNav { background: transparent; border: none; outline: none; padding: 4px; }
#toolNav::item { color: #94A3B8; border-radius: 8px; padding: 11px 10px; margin: 2px 0; }
#toolNav::item:hover { background: #162238; color: #E2E8F0; }
#toolNav::item:selected { background: #183B3A; color: #5EEAD4; font-weight: 600; }
#toolPlaceholder { background: #151F2E; border: 1px solid #223149; border-radius: 10px; }
#placeholderTitle { color: #E2E8F0; font-size: 17px; font-weight: 700; }
#placeholderIcon { background: #183B3A; border-radius: 10px; padding: 12px; }

/* Commands */
#commandSearch { background: #111B2C; }
#commandMeta { color: #64748B; font-size: 11px; }
#commandToolbar { background: transparent; border: none; border-bottom: 1px solid #334155; }
#commandFilterTabs { background: transparent; border: none; }
#commandFilterTabs::tab { background: transparent; color: #94A3B8; border: none; border-bottom: 2px solid transparent; padding: 9px 12px 8px; margin: 0 2px; }
#commandFilterTabs::tab:hover { background: transparent; color: #E2E8F0; }
#commandFilterTabs::tab:selected { background: transparent; color: #5EEAD4; border-bottom-color: #5EEAD4; font-weight: 600; }
#commandRunner { min-width: 120px; }
#commandOutputHeader { color: #CBD5E1; font-size: 12px; font-weight: 700; }
#dangerButton { background: transparent; border-color: transparent; color: #FDA4AF; }
#dangerButton:hover { background: #3A2028; border-color: #6B2A36; }

/* Settings */
#settingsNavPanel { background: #111B2C; border: 1px solid #223149; border-radius: 10px; }
#settingsNav { background: transparent; border: none; outline: none; padding: 4px; }
#settingsNav::item { color: #94A3B8; border-radius: 8px; padding: 11px 10px; margin: 2px 0; }
#settingsNav::item:hover { background: #162238; color: #E2E8F0; }
#settingsNav::item:selected { background: #183B3A; color: #5EEAD4; font-weight: 600; }
#settingsDescription { color: #94A3B8; font-size: 12px; }
#settingsActions { background: #111B2C; border-top: 1px solid #223149; }

/* Tool cards and form rhythm */
#bridgeUrlPanel { background: #111B2C; border: 1px solid #24334A; border-radius: 8px; }
#bridgeStatusTitle { color: #CBD5E1; font-weight: 600; }
#bridgeStatusHint { color: #64748B; font-size: 12px; }
#serviceToggleButton { background: #0F8F83; border: 1px solid #14B8A6; color: white; font-weight: 600; min-width: 72px; }
#serviceToggleButton:hover { background: #0D9488; }
#serviceToggleButton[running="true"] { background: #3A2028; border-color: #6B2A36; color: #FDA4AF; }
#serviceToggleButton[running="true"]:hover { background: #4C1D24; }
#bridgeSettingsPanel { background: #111B2C; border: 1px solid #24334A; border-radius: 8px; }
#bridgeSettingsPanel::title { color: #CBD5E1; }
#bridgePcBox, #bridgeReceivedBox { background: #111B2C; border: 1px solid #24334A; border-radius: 8px; }
#bridgePanelTitle { color: #CBD5E1; font-size: 15px; font-weight: 700; padding: 0 2px 2px; }
"""

LIGHT_STYLE = DARK_STYLE
for _dark, _light in (
    ("#111827", "#FFFFFF"), ("#151D2B", "#FFFFFF"), ("#273449", "#D8E0E8"),
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
#onlineBadge { background: transparent; color: #15803D; }
#warningBadge { background: transparent; color: #B45309; }
#offlineBadge { background: transparent; color: #64748B; }
#connectionLabel { color: #374151; }
#iconButton, #rowAction { color: #0F8F83; }
#iconButton:hover, #rowAction:hover { background: #F0FDFA; border-color: #99F6E4; }
#deviceTable { color: #1F2937; selection-background-color: #F1F3F5; selection-color: #1F2937; }
#deviceTable::item { background: transparent; color: #1F2937; }
#deviceTable::item:selected { background: #F1F3F5; color: #1F2937; }
#deviceIdentifierCell, #deviceStatusCell, #deviceActionsCell { background: transparent; }
/* Use spacing and quiet surface changes for structure.  Section outlines and
   row separators make the device page unnecessarily busy. */
#devicesPage, #contentPage { background: #F4F6F8; }
#topbar { background: #FFFFFF; border: none; }
#navTabs::tab:selected { color: #0F8F83; background: #E9F8F5; border: none; font-weight: normal; }
#devicePanel, #operationPanel, #connectionBar, QGroupBox {
    background: #FFFFFF;
    border: none;
}
#emptyPanel, #deviceTable, #operationLog { background: transparent; border: none; }
#emptyIcon, #emptyTitle, #emptyHint { background: transparent; border: none; }
#logToggle { background: transparent; border: none; color: #6B7280; }
#logToggle:hover { background: #F0FDFA; }
#sectionTitle { color: #6B7280; }
#emptyHint { color: #6B7280; }
QComboBox, QLineEdit, QSpinBox, QPlainTextEdit, QListWidget {
    background: #FFFFFF;
    border-color: #C9D4E0;
}
QComboBox::drop-down { background: #F8FAFC; border-left-color: #C9D4E0; }
QComboBox::drop-down:hover { background: #F0FDFA; }
QSpinBox::up-button, QSpinBox::down-button { background: #F8FAFC; border-left-color: #C9D4E0; }
QSpinBox::up-button { border-bottom-color: #C9D4E0; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #F0FDFA; }
QPushButton, QToolButton { background: #FFFFFF; border-color: #C9D4E0; }
QHeaderView::section { background: transparent; border: none; }
#deviceSplitter::handle { background: #F4F6F8; }
#deviceSplitter::handle:hover { background: #DDF4EF; }
QScrollBar::handle:vertical { background: #94A3B8; }
QScrollBar::handle:vertical:hover { background: #64748B; }
#commandList::item:selected { background: #F1F3F5; color: #1F2937; border: none; outline: none; }
QStatusBar { background: #F4F6F8; border: none; }
#deviceToolsTabs::tab { color: #6B7280; }
#deviceToolsTabs::tab:selected { background: #E9F8F5; color: #0F8F83; }
#terminalHeader { background: #FFFFFF; border-bottom-color: #D8E0E8; }
#terminalDevice { background: #F0FDFA; color: #0F8F83; border-color: #CCFBF1; }
#terminalSurface { background: #FCFCFD; color: #111827; selection-background-color: #99F6E4; }
"""

LIGHT_STYLE += """
#appSidebar { background: #FFFFFF; border-right-color: #D8E0E8; }
#sidebarBrand { color: #1F2937; }
#sidebarVersion, #sidebarStatusText { color: #9CA3AF; }
#sidebarSection { color: #6B7280; }
#navList::item { color: #6B7280; }
#navList::item:hover, #toolNav::item:hover, #settingsNav::item:hover { background: #F3F7F7; color: #374151; }
#navList::item:selected, #toolNav::item:selected, #settingsNav::item:selected { background: #E9F8F5; color: #0F766E; }
#sidebarStatus, #toolNavPanel, #settingsNavPanel { background: #F8FAFC; border-color: #E2E8F0; }
#toolNavBar { background: transparent; border: none; border-bottom: 1px solid #D8E0E8; }
#sidebarStatusTitle { color: #374151; }
#topbar { background: #FFFFFF; border-bottom-color: #D8E0E8; }
#pageTitle, #toolTitle { color: #1F2937; }
#pageSubtitle, #toolSubtitle, #settingsDescription { color: #6B7280; }
#contentPage, #devicesPage, #deviceToolsPage { background: #F4F6F8; }
#toolCard, #settingsCard, #commandCard, #toolHeader, #toolPlaceholder { background: #FFFFFF; border-color: #E2E8F0; }
#sectionTitle, #commandOutputHeader, #placeholderTitle { color: #374151; }
#toolNav::item, #settingsNav::item { color: #6B7280; }
#toolNavTabs::tab { color: #6B7280; }
#toolNavTabs::tab:hover { background: transparent; color: #374151; }
#toolNavTabs::tab:selected { background: transparent; color: #0F766E; border-bottom-color: #0F766E; }
#commandToolbar { background: transparent; border: none; border-bottom: 1px solid #D8E0E8; }
#commandFilterTabs::tab { color: #6B7280; }
#commandFilterTabs::tab:hover { background: transparent; color: #374151; }
#commandFilterTabs::tab:selected { background: transparent; color: #0F766E; border-bottom-color: #0F766E; }
#commandList::item { color: #6B7280; }
#commandList::item:hover { background: #F3F7F7; color: #374151; }
#commandList::item:selected { background: #E9F8F5; color: #0F766E; }
#commandRunnerMeta { color: #9CA3AF; }
#commandDeleteButton:hover { background: #FEE2E2; }
#commandSearch, #bridgeUrlPanel, #bridgeSettingsPanel, #bridgePcBox, #bridgeReceivedBox { background: #F8FAFC; border-color: #E2E8F0; }
#serviceToggleButton { background: #0F8F83; border-color: #14B8A6; color: #FFFFFF; }
#serviceToggleButton[running="true"] { background: #FEE2E2; border-color: #FECACA; color: #B91C1C; }
#bridgePanelTitle { color: #374151; }
#settingsActions { background: #FFFFFF; border-top-color: #E2E8F0; }
#placeholderIcon { background: #E9F8F5; }
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
                        self.removeRequested.emit(str(address))
                    return True
        return super().eventFilter(watched, event)


class ScrcpyHandle:
    """A process handle that works for both newly started and discovered PIDs."""
    def __init__(self, process: subprocess.Popen | None = None, pid: int | None = None, serial: str = "", log_callback=None) -> None:
        self.process = process
        self.pid = process.pid if process else pid
        self.serial = serial
        self.video_ready = threading.Event()
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
    scrcpy_ready = Signal(str)
    scrcpy_start_failed = Signal(str, str)
    scrcpy_finished = Signal(str)

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
        self.scrcpy_starting: set[str] = set()
        self.scrcpy_video_ready: set[str] = set()
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
        self._adb_restart_in_progress = False
        self._connection_busy = False
        self._pending_disconnects: set[str] = set()
        # Offline devices removed by the user stay hidden while ADB continues
        # to report the stale offline row.  A later live/non-offline state
        # automatically makes the device visible again.
        self._dismissed_devices: set[str] = set()
        self._async_dispatcher = AsyncDispatcher(self)
        self._async_dispatcher.done.connect(self._handle_job_done)
        self._async_dispatcher.failed.connect(self._handle_job_failed)
        self._next_job_token = 0
        self._job_callbacks: dict[int, tuple[object, object]] = {}
        self._async_threads: dict[int, threading.Thread] = {}
        self.setWindowTitle(f"ADBLite v{APP_VERSION}")
        self.resize(1120, 720)
        self._build_ui()
        self.scrcpy_log.connect(self._append_scrcpy_log)
        self.scrcpy_ready.connect(self._scrcpy_start_ready)
        self.scrcpy_start_failed.connect(self._scrcpy_start_failed)
        self.scrcpy_finished.connect(self._scrcpy_finished)
        self._discover_scrcpy_processes()
        self.refresh_devices()
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.refresh_devices(manual=False))
        self.timer.start(4000)

    def _build_ui(self) -> None:
        self.apply_theme(self.repo.data.get("theme", "dark"))
        root = QWidget(); root.setObjectName("root")
        layout = QHBoxLayout(root); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        sidebar = QFrame(); sidebar.setObjectName("appSidebar"); sidebar.setFixedWidth(224)
        sidebar_layout = QVBoxLayout(sidebar); sidebar_layout.setContentsMargins(14, 18, 14, 14); sidebar_layout.setSpacing(8)
        brand_row = QHBoxLayout(); brand_row.setContentsMargins(4, 0, 4, 8); brand_row.setSpacing(8)
        brand = QLabel("ADBLite"); brand.setObjectName("sidebarBrand"); brand_row.addWidget(brand)
        version = QLabel(f"v{APP_VERSION}"); version.setObjectName("sidebarVersion"); brand_row.addWidget(version, 0, Qt.AlignmentFlag.AlignBottom)
        brand_row.addStretch()
        sidebar_layout.addLayout(brand_row)
        workspace_label = QLabel("工作区"); workspace_label.setObjectName("sidebarSection"); sidebar_layout.addWidget(workspace_label)
        self.navigation = QListWidget(); self.navigation.setObjectName("navList")
        self.navigation.setSpacing(2); self.navigation.setIconSize(QSize(18, 18)); self.navigation.setMinimumHeight(210)
        self.navigation.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        navigation_items = (
            ("设备", "查看和管理已连接的 USB/无线 ADB 设备", "monitor"),
            ("工具", "手机桥接、应用管理和文件管理", "tools"),
            ("命令", "保存并运行常用 ADB、Scrcpy、CMD 和进程命令", "terminal"),
            ("设置", "配置工具链、主题和运行参数", "settings"),
        )
        for title, tooltip, icon_name in navigation_items:
            item = QListWidgetItem(interface_icon(icon_name), title)
            item.setToolTip(tooltip)
            item.setData(Qt.ItemDataRole.UserRole, tooltip)
            self.navigation.addItem(item)
        sidebar_layout.addWidget(self.navigation)
        sidebar_layout.addStretch(1)
        sidebar_status = QFrame(); sidebar_status.setObjectName("sidebarStatus")
        sidebar_status_layout = QVBoxLayout(sidebar_status); sidebar_status_layout.setContentsMargins(10, 8, 10, 8); sidebar_status_layout.setSpacing(2)
        status_title = QLabel("ADB 状态"); status_title.setObjectName("sidebarStatusTitle"); sidebar_status_layout.addWidget(status_title)
        self.sidebar_status_text = QLabel("正在初始化…"); self.sidebar_status_text.setObjectName("sidebarStatusText"); sidebar_status_layout.addWidget(self.sidebar_status_text)
        sidebar_layout.addWidget(sidebar_status)
        layout.addWidget(sidebar)

        content_root = QWidget(); content_layout = QVBoxLayout(content_root); content_layout.setContentsMargins(0, 0, 0, 0); content_layout.setSpacing(0)
        topbar = QWidget(); topbar.setObjectName("topbar")
        header = QHBoxLayout(topbar); header.setContentsMargins(24, 12, 18, 12); header.setSpacing(8)
        title_column = QVBoxLayout(); title_column.setContentsMargins(0, 0, 0, 0); title_column.setSpacing(2)
        self.page_title = QLabel("设备"); self.page_title.setObjectName("pageTitle"); title_column.addWidget(self.page_title)
        self.page_subtitle = QLabel("查看和管理已连接的 USB/无线 ADB 设备"); self.page_subtitle.setObjectName("pageSubtitle"); title_column.addWidget(self.page_subtitle)
        header.addLayout(title_column)
        header.addStretch()
        # The table is the single visible device selector. Keep this hidden
        # model combo so existing shell/command logic can share the selection.
        self.device_combo = QComboBox(self)
        self.device_combo.currentIndexChanged.connect(self._device_changed)
        self.device_combo.hide()
        self.device_search = QLineEdit(); self.device_search.setObjectName("headerSearch")
        self.device_search.setPlaceholderText("搜索设备名称或标识")
        self.device_search.setClearButtonEnabled(True); self.device_search.setFixedWidth(240)
        self.device_search.textChanged.connect(self._filter_devices); self.device_search.hide()
        header.addWidget(self.device_search)
        self.header_search_button = self._icon_button(
            "search", "搜索设备名称或标识", self._toggle_device_search, "iconButton",
        )
        header.addWidget(self.header_search_button)
        self.header_refresh_button = self._icon_button(
            "refresh", "刷新当前已连接的 USB/无线 ADB 设备列表", lambda: self.refresh_devices(manual=True), "iconButton",
        )
        header.addWidget(self.header_refresh_button)
        self.theme_toggle = self._icon_button("moon", "切换到夜间模式", self._toggle_theme, "iconButton")
        header.addWidget(self.theme_toggle)
        self._update_theme_toggle()
        content_layout.addWidget(topbar)

        self.scrcpy_output = QPlainTextEdit(self); self.scrcpy_output.hide()
        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self._devices_page()); self.page_stack.addWidget(self._device_tools_page()); self.page_stack.addWidget(self._commands_page()); self.page_stack.addWidget(self._settings_page())
        self.navigation.currentRowChanged.connect(self._switch_page)
        self.navigation.setCurrentRow(0)
        self._switch_page(0)
        content_layout.addWidget(self.page_stack, 1)
        layout.addWidget(content_root, 1)
        for button in root.findChildren(QAbstractButton):
            self._configure_button_focus(button)
        self.setCentralWidget(root)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage("ADB 就绪 · 等待设备刷新")

    def _switch_page(self, index: int) -> None:
        self.page_stack.setCurrentIndex(index)
        page_meta = (
            ("设备", "查看和管理已连接的 USB/无线 ADB 设备"),
            ("工具", "围绕当前设备执行桥接、应用和文件操作"),
            ("命令", "把常用操作保存成可重复运行的工作流"),
            ("设置", "配置工具链、主题和运行参数"),
        )
        if 0 <= index < len(page_meta):
            self.page_title.setText(page_meta[index][0])
            self.page_subtitle.setText(page_meta[index][1])
        on_devices_page = index == 0
        self.header_search_button.setVisible(on_devices_page)
        self.header_refresh_button.setVisible(on_devices_page)
        if not on_devices_page:
            self.device_search.clear()
            self.device_search.hide()

    def _device_tools_page(self) -> QWidget:
        self.device_tools_page = DeviceToolsPage(self.repo)
        self.phone_bridge_page = self.device_tools_page.phone_bridge_page
        self.phone_bridge_page.status_message.connect(self.statusBar().showMessage)
        return self.device_tools_page

    def _toggle_device_search(self) -> None:
        if self.device_search.isVisible():
            self.device_search.clear()
            self.device_search.hide()
            return
        self.device_search.show()
        self.device_search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.device_search.selectAll()

    def _devices_page(self) -> QWidget:
        page = QWidget(); page.setObjectName("devicesPage")
        layout = QVBoxLayout(page); layout.setContentsMargins(10, 10, 10, 8); layout.setSpacing(8)

        device_panel = QFrame(); device_panel.setObjectName("devicePanel"); device_panel.setFrameShape(QFrame.Shape.NoFrame)
        device_layout = QVBoxLayout(device_panel); device_layout.setContentsMargins(10, 10, 10, 10); device_layout.setSpacing(0)

        self.device_stack = QStackedWidget(); self.device_stack.setObjectName("deviceSurface"); self.device_stack.setFrameShape(QFrame.Shape.NoFrame)
        self.device_table = QTableWidget(0, 4); self.device_table.setObjectName("deviceTable")
        self.device_table.setHorizontalHeaderLabels(["设备标识", "设备名称", "状态", "操作"])
        self.device_table.verticalHeader().setVisible(False)
        self.device_table.setShowGrid(False); self.device_table.setAlternatingRowColors(False)
        self.device_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.device_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.device_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.device_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        device_header = self.device_table.horizontalHeader()
        device_header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        device_header.setFixedHeight(44)
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
        empty = QFrame(); empty.setObjectName("emptyPanel"); empty.setFrameShape(QFrame.Shape.NoFrame)
        empty_layout = QVBoxLayout(empty); empty_layout.addStretch()
        empty_icon = QLabel(); empty_icon.setObjectName("emptyIcon"); empty_icon.setFixedSize(48, 48)
        empty_icon.setPixmap(interface_icon("monitor").pixmap(40, 40))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setToolTip("暂未发现 ADB 设备")
        empty_title = QLabel("还没有发现设备"); empty_title.setObjectName("emptyTitle"); empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint = QLabel("连接 USB 设备，或在下方输入无线调试地址"); empty_hint.setObjectName("emptyHint"); empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon, 0, Qt.AlignmentFlag.AlignHCenter); empty_layout.addWidget(empty_title); empty_layout.addWidget(empty_hint); empty_layout.addStretch()
        self.device_stack.addWidget(empty)
        self.device_stack.setCurrentIndex(1)
        device_layout.addWidget(self.device_stack, 1)

        self.device_output = QPlainTextEdit(); self.device_output.setObjectName("operationLog"); self.device_output.setReadOnly(True); self.device_output.setMinimumHeight(80); self.device_output.hide()
        self.operation_panel = QFrame(); self.operation_panel.setObjectName("operationPanel")
        operation_layout = QVBoxLayout(self.operation_panel); operation_layout.setContentsMargins(8, 5, 8, 7); operation_layout.setSpacing(2)
        operation_header = QWidget(); operation_header.setObjectName("operationHeader"); operation_header.setFixedHeight(34)
        log_header = QHBoxLayout(operation_header); log_header.setContentsMargins(0, 0, 0, 0)
        self.log_toggle = QToolButton(); self.log_toggle.setObjectName("logToggle"); self.log_toggle.setText("操作记录  ▾")
        self.log_toggle.setCheckable(True); self.log_toggle.toggled.connect(self._toggle_device_log); log_header.addWidget(self.log_toggle)
        log_header.addStretch()
        operation_layout.addWidget(operation_header, 0, Qt.AlignmentFlag.AlignTop)
        operation_layout.addWidget(self.device_output, 1)

        self.device_splitter = QSplitter(Qt.Orientation.Vertical); self.device_splitter.setObjectName("deviceSplitter")
        self.device_splitter.setChildrenCollapsible(False)
        self.device_splitter.setHandleWidth(8)
        self.device_splitter.addWidget(device_panel); self.device_splitter.addWidget(self.operation_panel)
        self.device_splitter.setStretchFactor(0, 1); self.device_splitter.setStretchFactor(1, 0)
        self.device_splitter.setSizes([600, 42])
        layout.addWidget(self.device_splitter, 1)

        connection_bar = QFrame(); connection_bar.setObjectName("connectionBar")
        history_layout = QHBoxLayout(connection_bar); history_layout.setContentsMargins(12, 9, 10, 9); history_layout.setSpacing(8)
        connection_icon = QLabel(); connection_icon.setFixedSize(20, 20)
        connection_icon.setPixmap(interface_icon("wifi").pixmap(18, 18))
        connection_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        connection_icon.setToolTip("无线连接")
        history_layout.addWidget(connection_icon)
        connection_label = QLabel("无线连接"); connection_label.setObjectName("connectionLabel"); history_layout.addWidget(connection_label)
        self.history_combo = HistoryComboBox()
        self.history_combo.setMinimumWidth(260)
        self.history_combo.lineEdit().setPlaceholderText("IP:端口，例如 192.168.1.20:5555")
        self.history_combo.currentIndexChanged.connect(self._history_selection_changed)
        self.history_combo.removeRequested.connect(self.remove_history)
        self.history_combo.lineEdit().returnPressed.connect(self.connect_history); history_layout.addWidget(self.history_combo, 1)
        self.connect_button = QPushButton("连接设备"); self.connect_button.setObjectName("primaryButton"); self.connect_button.clicked.connect(self.connect_history); history_layout.addWidget(self.connect_button)
        self.connect_all_button = QPushButton("连接全部")
        self.connect_all_button.setToolTip("一键连接全部无线历史地址")
        self.connect_all_button.clicked.connect(self.connect_all_history); history_layout.addWidget(self.connect_all_button)
        self.discovery_button = QPushButton("自动发现")
        self.discovery_button.setToolTip("通过 ADB mDNS 发现同一网络中开启无线调试的设备（仅发现地址，不会自动连接）")
        self.discovery_button.clicked.connect(self.discover_wireless); history_layout.addWidget(self.discovery_button)
        self.restart_adb_button = QPushButton("重启 ADB")
        self.restart_adb_button.setToolTip("重启 ADB 服务（adb kill-server → adb start-server）")
        self.restart_adb_button.clicked.connect(self.restart_adb_server); history_layout.addWidget(self.restart_adb_button)
        layout.addWidget(connection_bar)
        self._reload_history()
        return page

    def _toggle_device_log(self, visible: bool) -> None:
        sizes = self.device_splitter.sizes()
        if not visible and len(sizes) == 2 and sizes[1] > 80:
            self._operation_log_height = sizes[1]
        self.device_output.setVisible(visible)
        self.log_toggle.setText("操作记录  ▴" if visible else "操作记录  ▾")
        QTimer.singleShot(0, lambda expanded=visible: self._resize_operation_panel(expanded))

    def _resize_operation_panel(self, expanded: bool) -> None:
        sizes = self.device_splitter.sizes()
        if len(sizes) != 2:
            return
        total = sum(sizes)
        if total <= 0:
            return
        if expanded:
            target = int(getattr(self, "_operation_log_height", 180))
            target = max(130, min(target, max(130, total - 160)))
        else:
            target = self.log_toggle.sizeHint().height() + 12
        self.device_splitter.setSizes([max(1, total - target), target])

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
        self.device_table.selectRow(row)
        self._select_device_serial(self.devices[row].serial)
        action()

    @staticmethod
    def _configure_button_focus(button: QAbstractButton) -> None:
        """Keep keyboard focus support without retaining focus after a click."""
        if button.property("transientClickFocus"):
            return
        button.setProperty("transientClickFocus", True)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        button.clicked.connect(lambda _checked=False, target=button: target.clearFocus())

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
        MainWindow._configure_button_focus(button)
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
            # Cell widgets are transparent so the row selection painted by
            # these backing items remains continuous across the whole row.
            for column in (0, 2, 3):
                self.device_table.setItem(row, column, QTableWidgetItem())
            identifier_wrap = QWidget(); identifier_wrap.setObjectName("deviceIdentifierCell")
            identifier_wrap.setToolTip(f"{connection} 设备 · {device.serial}")
            identifier_wrap.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            identifier_layout = QHBoxLayout(identifier_wrap); identifier_layout.setContentsMargins(10, 0, 10, 0); identifier_layout.setSpacing(6)
            connection_icon = QLabel(); connection_icon.setFixedSize(18, 18)
            connection_icon.setPixmap(interface_icon("wifi" if connection == "无线" else "usb").pixmap(18, 18))
            connection_icon.setToolTip(f"{connection} 设备")
            identifier_text = QLabel(device.serial); identifier_text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            identifier_text.setToolTip(f"{connection} 设备 · {device.serial}")
            identifier_layout.addStretch()
            identifier_layout.addWidget(identifier_text)
            identifier_layout.addWidget(connection_icon)
            identifier_layout.addStretch()

            name_item = QTableWidgetItem(device.model or "未知设备")
            name_item.setToolTip(device.model or "ADB 未返回设备型号")
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.device_table.setCellWidget(row, 0, identifier_wrap); self.device_table.setItem(row, 1, name_item)

            status_text, status_style = self._device_status(device)
            status_wrap = QWidget(); status_wrap.setObjectName("deviceStatusCell"); status_wrap.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            status_layout = QHBoxLayout(status_wrap); status_layout.setContentsMargins(10, 0, 10, 0)
            status = QLabel(status_text); status.setObjectName(status_style); status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_layout.addStretch(); status_layout.addWidget(status); status_layout.addStretch()
            self.device_table.setCellWidget(row, 2, status_wrap)

            actions = QWidget(); actions.setObjectName("deviceActionsCell"); actions.setMinimumWidth(280)
            action_layout = QHBoxLayout(actions); action_layout.setContentsMargins(10, 0, 10, 0); action_layout.setSpacing(6)
            # Device actions require an ADB-ready target, but the wireless
            # connection action is intentionally independent of the reported
            # device state.  ``adb devices`` commonly reports ``unauthorized``
            # or ``offline`` while the TCP endpoint is still available and
            # ``adb disconnect``/``adb connect`` are exactly what can recover
            # those states.
            enabled = device.state == "device" and not self._connection_busy
            action_layout.addStretch()
            action_specs = [
                ("monitor", "启动 Scrcpy 投屏（双击设备行也可启动）", lambda _=False, r=row: self._run_device_action(r, self.start_scrcpy), enabled),
                ("terminal", "打开当前设备的独立终端窗口", lambda _=False, r=row: self._open_device_shell(r), enabled),
                ("info", "读取设备信息", lambda _=False, r=row: self._run_device_action(r, self.show_device_info), enabled),
            ]
            if ":" in device.serial and device.state == "offline":
                action_specs.append(("connect", "重新连接无线 ADB", lambda _=False, r=row: self._connect_device_row(r), not self._connection_busy))
            elif ":" in device.serial:
                action_specs.append(("disconnect", "断开无线 ADB", lambda _=False, r=row: self._run_device_action(r, self.disconnect_current), not self._connection_busy))
            else:
                action_specs.append(("disconnect", "断开无线 ADB", lambda _=False, r=row: self._run_device_action(r, self.disconnect_current), False))
            if device.state == "offline":
                action_specs.append(("delete", "从设备列表和连接历史中删除", lambda _=False, r=row: self._run_device_action(r, self.remove_offline_device), not self._connection_busy))
            action_specs.extend((
                ("restart", "重启系统", lambda _=False, r=row: self._run_device_action(r, lambda: self.confirm_reboot(False)), enabled),
                ("recovery", "重启到 Recovery", lambda _=False, r=row: self._run_device_action(r, lambda: self.confirm_reboot(True)), enabled),
            ))
            for icon_name, tooltip, callback, action_enabled in action_specs:
                button = self._icon_button(icon_name, tooltip, callback)
                button.setEnabled(action_enabled); action_layout.addWidget(button)
            action_layout.addStretch()
            self.device_table.setCellWidget(row, 3, actions)
            self.device_table.setRowHeight(row, 56)
            if device.serial == selected:
                self.device_table.selectRow(row)
        self.device_table.blockSignals(False)
        self.device_stack.setCurrentIndex(0 if self.devices else 1)
        if hasattr(self, "sidebar_status_text"):
            connected_count = sum(device.state == "device" for device in self.devices)
            self.sidebar_status_text.setText(f"{connected_count} 台设备已连接" if connected_count else "等待设备连接")
        self._filter_devices(self.device_search.text())

    @staticmethod
    def _section_title(text: str) -> QLabel:
        title = QLabel(text)
        title.setObjectName("sectionTitle")
        return title

    def _scrcpy_settings_box(self) -> QGroupBox:
        settings_box = QGroupBox()
        settings_box.setObjectName("settingsCard")
        form = QFormLayout(settings_box)
        form.setContentsMargins(18, 22, 18, 18)
        form.setVerticalSpacing(12)
        form.addRow(self._section_title("Scrcpy 默认参数"))
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
        page = QWidget(); page.setObjectName("contentPage"); outer = QVBoxLayout(page); outer.setContentsMargins(24, 20, 24, 24); outer.setSpacing(14)
        command_toolbar = QFrame(); command_toolbar.setObjectName("commandToolbar")
        toolbar_layout = QHBoxLayout(command_toolbar); toolbar_layout.setContentsMargins(0, 0, 0, 8); toolbar_layout.setSpacing(14)
        toolbar_title = QLabel("命令集合"); toolbar_title.setObjectName("toolNavTitle"); toolbar_layout.addWidget(toolbar_title)
        self.command_filter_tabs = QTabBar(); self.command_filter_tabs.setObjectName("commandFilterTabs"); self.command_filter_tabs.setDocumentMode(True); self.command_filter_tabs.setDrawBase(False); self.command_filter_tabs.setExpanding(False); self.command_filter_tabs.setUsesScrollButtons(False); self.command_filter_tabs.setElideMode(Qt.TextElideMode.ElideNone)
        for label, runner in (("全部", "all"), ("ADB", "adb"), ("Scrcpy", "scrcpy"), ("CMD", "cmd"), ("进程", "process")):
            index = self.command_filter_tabs.addTab(label); self.command_filter_tabs.setTabData(index, runner)
        self.command_filter_tabs.setCurrentIndex(0); self.command_filter_tabs.currentChanged.connect(lambda _index: self._filter_commands(self.command_search.text() if hasattr(self, "command_search") else "")); toolbar_layout.addWidget(self.command_filter_tabs, 1)
        new_command = QPushButton("新建命令"); new_command.clicked.connect(self.new_command); toolbar_layout.addWidget(new_command)
        outer.addWidget(command_toolbar)

        workspace = QHBoxLayout(); workspace.setSpacing(14); outer.addLayout(workspace, 1)
        list_box = QFrame(); list_box.setObjectName("commandCard"); list_box.setMinimumWidth(280); list_box.setMaximumWidth(340); list_layout = QVBoxLayout(list_box); list_layout.setContentsMargins(14, 12, 14, 12); list_layout.setSpacing(8)
        list_header = QHBoxLayout(); list_header.addWidget(self._section_title("命令列表")); list_header.addStretch(); self.command_meta = QLabel("0 条"); self.command_meta.setObjectName("commandMeta"); list_header.addWidget(self.command_meta); list_layout.addLayout(list_header)
        self.command_search = QLineEdit(); self.command_search.setObjectName("commandSearch"); self.command_search.setPlaceholderText("搜索命令名称"); self.command_search.setClearButtonEnabled(True); self.command_search.textChanged.connect(self._filter_commands); list_layout.addWidget(self.command_search)
        self.command_list = QListWidget(); self.command_list.setObjectName("commandList"); self.command_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus); self.command_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection); self.command_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded); self.command_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_layout.addWidget(self.command_list, 1); workspace.addWidget(list_box)

        right_column = QVBoxLayout(); right_column.setSpacing(14); workspace.addLayout(right_column, 1)
        panel = QFrame(); panel.setObjectName("commandCard"); panel_layout = QVBoxLayout(panel); panel_layout.setContentsMargins(16, 14, 16, 16); panel_layout.setSpacing(10); right_column.addWidget(panel)
        editor_header = QHBoxLayout(); editor_header.addWidget(self._section_title("命令编辑器")); editor_header.addStretch(); editor_hint = QLabel("运行目标由设备页当前选择决定"); editor_hint.setObjectName("commandMeta"); editor_header.addWidget(editor_hint); panel_layout.addLayout(editor_header)
        editor_area = QWidget(); editor = QFormLayout(editor_area); editor.setContentsMargins(0, 0, 0, 0); editor.setHorizontalSpacing(14); editor.setVerticalSpacing(10); editor.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop); editor.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop); editor.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.cmd_name = QLineEdit(); self.cmd_name.setPlaceholderText("例如：获取设备型号")
        self.cmd_name.setMinimumHeight(38); self.cmd_name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cmd_runner = QComboBox(); self.cmd_runner.setObjectName("commandRunner"); self.cmd_runner.addItems(["adb", "scrcpy", "cmd", "process"]); self.cmd_runner.setMinimumWidth(220)
        self.cmd_args = QPlainTextEdit(); self.cmd_args.setPlaceholderText("每行一个参数；cmd 模式填写完整命令"); self.cmd_args.setMinimumHeight(120)
        self.cmd_args.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        args_label = QLabel("参数 / 命令"); args_label.setObjectName("fieldHint")
        editor.addRow("命令名称", self.cmd_name); editor.addRow("执行器", self.cmd_runner); editor.addRow(args_label, self.cmd_args)
        actions = QHBoxLayout(); actions.setSpacing(8); actions.addStretch()
        save = QPushButton("保存"); save.clicked.connect(self.save_command)
        run = QPushButton("运行"); run.setObjectName("primaryButton"); run.setIcon(interface_icon("play")); run.setIconSize(QSize(15, 15)); run.clicked.connect(self.run_command)
        actions.addWidget(save); actions.addWidget(run); editor.addRow(actions)
        panel_layout.addWidget(editor_area)

        output_panel = QFrame(); output_panel.setObjectName("commandCard"); output_layout = QVBoxLayout(output_panel); output_layout.setContentsMargins(14, 12, 14, 14); output_layout.setSpacing(6)
        output_header = QHBoxLayout(); output_label = QLabel("执行输出"); output_label.setObjectName("commandOutputHeader"); output_header.addWidget(output_label); output_header.addStretch()
        copy_output = QPushButton("复制"); copy_output.clicked.connect(lambda: QApplication.clipboard().setText(self.command_output.toPlainText()))
        clear_output = QPushButton("清空"); clear_output.clicked.connect(lambda: self.command_output.clear())
        output_header.addWidget(copy_output); output_header.addWidget(clear_output); output_layout.addLayout(output_header)
        self.command_output = QPlainTextEdit(); self.command_output.setReadOnly(True); self.command_output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap); self.command_output.setMinimumHeight(190); output_layout.addWidget(self.command_output, 1); right_column.addWidget(output_panel, 1)
        self.command_list.currentRowChanged.connect(self.load_command)
        self._reload_commands()
        return page

    def _shell_page(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(12)
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
        page = QWidget(); page.setObjectName("contentPage"); layout = QVBoxLayout(page); layout.setContentsMargins(24, 20, 24, 0); layout.setSpacing(14)
        intro = self._page_title("应用设置", "管理 ADBLite 的外观、工具链和投屏默认参数")
        layout.addWidget(intro)
        content = QHBoxLayout(); content.setSpacing(14); layout.addLayout(content, 1)
        nav_panel = QFrame(); nav_panel.setObjectName("settingsNavPanel"); nav_panel.setFixedWidth(160); nav_layout = QVBoxLayout(nav_panel); nav_layout.setContentsMargins(10, 12, 10, 10); nav_layout.setSpacing(8)
        settings_nav_title = QLabel("设置分类"); settings_nav_title.setObjectName("toolNavTitle"); nav_layout.addWidget(settings_nav_title)
        self.settings_nav = QListWidget(); self.settings_nav.setObjectName("settingsNav"); self.settings_nav.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for title in ("常规", "工具链", "投屏", "数据与关于"):
            self.settings_nav.addItem(QListWidgetItem(title))
        nav_layout.addWidget(self.settings_nav, 1); content.addWidget(nav_panel)

        self.settings_stack = QStackedWidget(); content.addWidget(self.settings_stack, 1)
        general = QGroupBox(); general.setObjectName("settingsCard"); general_form = QFormLayout(general); general_form.setContentsMargins(18, 22, 18, 18); general_form.setVerticalSpacing(12); general_form.addRow(self._section_title("常规"))
        self.theme_combo = QComboBox(); self.theme_combo.addItem("日间模式", "light"); self.theme_combo.addItem("夜间模式", "dark"); self.theme_combo.setCurrentIndex(0 if self.repo.data.get("theme", "dark") == "light" else 1); self.theme_combo.currentIndexChanged.connect(lambda: self.apply_theme(self.theme_combo.currentData()))
        general_form.addRow("界面主题", self.theme_combo)
        general_hint = QLabel("主题会立即应用，也会在保存设置时写入配置文件。"); general_hint.setObjectName("settingsDescription"); general_hint.setWordWrap(True); general_form.addRow(general_hint)
        self.settings_stack.addWidget(general)

        toolchain = QGroupBox(); toolchain.setObjectName("settingsCard"); tool_form = QFormLayout(toolchain); tool_form.setContentsMargins(18, 22, 18, 18); tool_form.setVerticalSpacing(12); tool_form.addRow(self._section_title("工具链"))
        self.adb_path = QLineEdit(self.repo.data.get("adb_path", "")); self.scrcpy_path = QLineEdit(self.repo.data.get("scrcpy_path", ""))
        for label, field in (("ADB 路径", self.adb_path), ("Scrcpy 路径", self.scrcpy_path)):
            row = QHBoxLayout(); row.addWidget(field, 1); browse = QPushButton("选择"); browse.clicked.connect(lambda _, f=field: self.pick_binary(f)); row.addWidget(browse); tool_form.addRow(label, row)
        tool_hint = QLabel("留空时自动从系统 PATH 查找；选择路径后建议重新刷新设备。"); tool_hint.setObjectName("settingsDescription"); tool_hint.setWordWrap(True); tool_form.addRow(tool_hint); self.settings_stack.addWidget(toolchain)
        self.settings_stack.addWidget(self._scrcpy_settings_box())

        about = QGroupBox(); about.setObjectName("settingsCard"); about_form = QFormLayout(about); about_form.setContentsMargins(18, 22, 18, 18); about_form.setVerticalSpacing(12); about_form.addRow(self._section_title("数据与关于"))
        config_row = QHBoxLayout(); self.config_path = QLineEdit(str(self.repo.path)); self.config_path.setReadOnly(True); self.config_path.setToolTip("当前实际使用的配置文件路径"); config_row.addWidget(self.config_path, 1)
        copy_config_path = QPushButton("复制路径"); copy_config_path.clicked.connect(lambda: QApplication.clipboard().setText(self.config_path.text())); config_row.addWidget(copy_config_path); about_form.addRow("配置文件", config_row)
        project_link = QLabel(f'<a href="{GITHUB_PROJECT_URL}">GitHub 开源项目主页</a>'); project_link.setObjectName("projectLink"); project_link.setOpenExternalLinks(True); project_link.setToolTip(GITHUB_PROJECT_URL); about_form.addRow("项目地址", project_link)
        about_form.addRow("软件版本", QLabel(f"v{APP_VERSION}")); about_form.addRow("软件作者", QLabel("luobida")); self.settings_stack.addWidget(about)
        self.settings_nav.currentRowChanged.connect(self.settings_stack.setCurrentIndex); self.settings_nav.setCurrentRow(0)

        settings_actions = QFrame(); settings_actions.setObjectName("settingsActions"); action_layout = QHBoxLayout(settings_actions); action_layout.setContentsMargins(24, 10, 24, 10); action_layout.addStretch(); save = QPushButton("保存设置"); save.setObjectName("primaryButton"); save.clicked.connect(self.save_settings); action_layout.addWidget(save); layout.addWidget(settings_actions)
        return page

    @staticmethod
    def _page_title(title: str, subtitle: str) -> QWidget:
        widget = QWidget(); layout = QVBoxLayout(widget); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(3)
        heading = QLabel(title); heading.setObjectName("toolTitle"); layout.addWidget(heading)
        hint = QLabel(subtitle); hint.setObjectName("toolSubtitle"); hint.setWordWrap(True); layout.addWidget(hint)
        return widget

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
        current = self.repo.data.get("theme", "dark")
        self.apply_theme("light" if current == "dark" else "dark")

    def _update_theme_toggle(self) -> None:
        """Show the mode that clicking the theme shortcut will switch to."""
        if not hasattr(self, "theme_toggle"):
            return
        is_dark = self.repo.data.get("theme", "dark") == "dark"
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

    def restart_adb_server(self) -> None:
        if self._adb_restart_in_progress:
            return
        if self._connection_busy:
            self.statusBar().showMessage("连接状态操作正在进行，请稍候…")
            return
        if self._refresh_in_progress:
            self.statusBar().showMessage("设备列表正在刷新，请稍后重试…")
            return

        self._adb_restart_in_progress = True
        self.restart_adb_button.setEnabled(False)
        self.restart_adb_button.setText("重启中…")
        self.restart_adb_button.setToolTip("正在重启 ADB 服务…")
        self.connect_button.setEnabled(False)
        self.connect_all_button.setEnabled(False)
        self.discovery_button.setEnabled(False)
        self.history_combo.setEnabled(False)
        self.header_refresh_button.setEnabled(False)
        self.statusBar().showMessage("正在重启 ADB 服务…")
        self._show_device_log()
        self.device_output.setPlainText(
            "正在重启 ADB 服务…\n\n"
            "[1/2] adb kill-server\n"
            "[2/2] adb start-server"
        )

        def restart():
            kill_result = self.adb.run(["kill-server"], timeout=20)
            if kill_result.returncode != 0:
                detail = (kill_result.stderr or kill_result.stdout).strip() or f"退出码 {kill_result.returncode}"
                raise RuntimeError(f"adb kill-server 失败：{detail}")
            start_result = self.adb.run(["start-server"], timeout=20)
            if start_result.returncode != 0:
                detail = (start_result.stderr or start_result.stdout).strip() or f"退出码 {start_result.returncode}"
                raise RuntimeError(f"adb start-server 失败：{detail}")
            return kill_result, start_result

        self._run_async(restart, self._finish_adb_restart, self._finish_adb_restart_error)

    def _reset_adb_restart_ui(self) -> None:
        self._adb_restart_in_progress = False
        self.restart_adb_button.setEnabled(True)
        self.restart_adb_button.setText("重启 ADB")
        self.restart_adb_button.setToolTip("重启 ADB 服务（adb kill-server → adb start-server）")
        self.connect_button.setEnabled(True)
        self.connect_all_button.setEnabled(True)
        self.discovery_button.setEnabled(True)
        self.history_combo.setEnabled(True)
        self.header_refresh_button.setEnabled(True)

    def _finish_adb_restart(self, results) -> None:
        self._reset_adb_restart_ui()
        kill_result, start_result = results
        lines = ["ADB 服务重启成功。"]
        for index, (command, result) in enumerate(
            (("adb kill-server", kill_result), ("adb start-server", start_result)),
            start=1,
        ):
            lines.extend(["", f"[{index}/2] {command}", f"退出码：{result.returncode}"])
            output = f"{result.stdout}{result.stderr}".strip()
            if output:
                lines.append(output)
        self.device_output.setPlainText("\n".join(lines))
        self.statusBar().showMessage("ADB 服务已重启，正在刷新设备列表…")
        self.refresh_devices(manual=True)

    def _finish_adb_restart_error(self, message: str) -> None:
        self._reset_adb_restart_ui()
        self.device_output.appendPlainText(f"\n\nADB 服务重启失败：{message}")
        self.statusBar().showMessage(f"ADB 服务重启失败 · {message}")
        self._show_error(f"重启 ADB 服务失败：\n{message}")

    def refresh_devices(self, manual: bool = False) -> None:
        if self._adb_restart_in_progress:
            if manual:
                self.statusBar().showMessage("ADB 服务正在重启，请稍候…")
            return
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
        if hasattr(self, "sidebar_status_text"):
            self.sidebar_status_text.setText("ADB 未就绪")
            self.sidebar_status_text.setToolTip(message)
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
            self.header_refresh_button.setToolTip("刷新当前已连接的 USB/无线 ADB 设备列表")
        return manual

    def _set_devices(self, devices: list[Device]) -> None:
        manual = self._finish_device_refresh()
        for device in devices:
            if device.serial in self._dismissed_devices and device.state != "offline":
                self._dismissed_devices.discard(device.serial)
        devices = [
            device for device in devices
            if device.serial not in self._dismissed_devices
        ]
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
        devices = sort_devices_by_status(merge_device_statuses(self.devices, devices))
        old_snapshot = [(item.serial, item.state, item.model, item.transport_id) for item in self.devices]
        new_snapshot = [(item.serial, item.state, item.model, item.transport_id) for item in devices]
        if self._initial_device_scan_done and old_snapshot == new_snapshot:
            if manual:
                self.statusBar().showMessage(f"设备列表已刷新 · {len(devices)} 台设备")
            return
        old_active = {device.serial for device in self.devices if device.state == "device"}
        new_active = {device.serial for device in devices if device.state == "device"}
        for serial in old_active - new_active:
            process = self.scrcpy_processes.get(serial)
            if process and process.poll() is None:
                self.scrcpy_log.emit(f"[{serial}] ADB 连接已断开，等待 scrcpy 自行退出")
        self.devices = devices; previous = self.current_serial()
        self.statusBar().showMessage(f"设备列表已刷新 · {len(devices)} 台设备")
        self._rebuild_device_combo(previous)
        if not self._initial_device_scan_done:
            for device in devices:
                if device.state == "device":
                    self.repo.remember(device.serial, kind="wifi" if ":" in device.serial else "usb")
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

    def _rebuild_device_combo(self, selected_serial: str = "") -> None:
        """Synchronize the hidden device selector with the visible table."""
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for device in self.devices:
            self.device_combo.addItem(self._device_combo_text(device), device.serial)
        if not self.devices:
            self.device_combo.addItem("未检测到设备", "")
        if selected_serial:
            index = self.device_combo.findData(selected_serial)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)
        self.device_combo.blockSignals(False)

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
        if serial in self.scrcpy_starting:
            return False
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
            # ``adb shell`` already runs the command through the device shell.
            # Adding ``sh -c`` here loses the first printf argument when ADB
            # reconstructs the remote command line (``printf`` becomes the
            # script and the label becomes $0).
            "shell",
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
        if not device:
            self.statusBar().showMessage(f"设备不存在 · {serial}")
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
        selected = self.current_serial()
        for index, device in enumerate(self.devices):
            if device.serial == serial:
                self.devices[index] = Device(serial=device.serial, state="offline", model=device.model)
                self.devices = sort_devices_by_status(self.devices)
                self._rebuild_device_combo(selected)
                self._render_device_table()
                break

    def connect_all_history(self) -> None:
        if self._connection_busy or self._adb_restart_in_progress:
            self.statusBar().showMessage("连接状态操作正在进行，请稍候…")
            return

        addresses: list[str] = []
        for item in self.repo.histories():
            address = item.address.strip()
            if address and (item.kind == "wifi" or ":" in address) and self._valid_wireless_address(address) and address not in addresses:
                addresses.append(address)
        if not addresses:
            return self._show_error("连接历史中没有可用的无线调试地址")

        self._show_device_log()
        self.device_output.setPlainText("正在连接全部无线历史地址…\n" + "\n".join(f"• {address}" for address in addresses))
        self._set_connection_busy(True, "连接中…", self.connect_all_button)
        self.statusBar().showMessage(f"正在连接 {len(addresses)} 个无线历史地址…")

        def connect_all():
            results = []
            for address in addresses:
                try:
                    result = self.adb.run(["connect", address], timeout=20)
                    results.append((address, result, ""))
                except Exception as exc:
                    results.append((address, None, str(exc)))
            return results

        def done(results) -> None:
            self._set_connection_busy(False)
            success_count = 0
            lines = ["全部历史地址连接结果："]
            for address, result, error in results:
                output = error if result is None else f"{result.stdout}\n{result.stderr}".strip()
                normalized = output.lower()
                succeeded = result is not None and result.returncode == 0 and ("connected to" in normalized or "already connected" in normalized)
                if succeeded:
                    success_count += 1
                    self._pending_disconnects.discard(address)
                lines.append(f"\n[{'成功' if succeeded else '失败'}] {address}")
                if output:
                    lines.append(output)
            self.device_output.setPlainText("\n".join(lines))
            self.statusBar().showMessage(f"全部连接完成 · 成功 {success_count}/{len(results)}")
            self.refresh_devices(manual=True)

        self._run_async(connect_all, done, self._finish_connection_error)

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
        self.device_table.selectRow(row)
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

    def _set_connection_busy(self, busy: bool, label: str = "连接中…", active_button: QPushButton | None = None) -> None:
        self._connection_busy = busy
        if hasattr(self, "device_table"):
            for row, device in enumerate(self.devices):
                actions = self.device_table.cellWidget(row, 3)
                if not actions:
                    continue
                for button in actions.findChildren(QToolButton):
                    enabled = device.state == "device"
                    action_name = button.property("actionName")
                    if action_name in {"disconnect", "connect"}:
                        # Keep the transport control usable for every state
                        # reported for a wireless endpoint (including
                        # ``unauthorized`` and ``offline``).
                        enabled = ":" in device.serial
                    elif action_name == "delete":
                        enabled = device.state == "offline"
                    button.setEnabled(enabled and not busy)
        if not hasattr(self, "connect_button"):
            return
        self.connect_button.setEnabled(not busy)
        self.connect_all_button.setEnabled(not busy)
        self.discovery_button.setEnabled(not busy)
        self.restart_adb_button.setEnabled(not busy and not self._adb_restart_in_progress)
        self.history_combo.setEnabled(not busy)
        self.connect_button.setText("连接设备")
        self.connect_all_button.setText("连接全部")
        self.discovery_button.setText("自动发现")
        if busy:
            (active_button or self.connect_button).setText(label)

    def _finish_connection_error(self, message: str) -> None:
        self._set_connection_busy(False)
        self._show_device_log()
        self.device_output.setPlainText(f"操作失败：{message}")
        self.statusBar().showMessage(f"ADB 操作失败 · {message}")

    def discover_wireless(self) -> None:
        if self._connection_busy:
            self.statusBar().showMessage("连接状态操作正在进行，请稍候…")
            return
        self._set_connection_busy(True, "发现中…", self.discovery_button)
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
            # Update the existing model instead of clearing and rebuilding the
            # combo box.  Rebuilding causes Qt to close the popup after every
            # deletion, forcing the user to open it again for the next row.
            if current_row >= 0:
                self.history_combo.blockSignals(True)
                self.history_combo.removeItem(current_row)
                if self.history_combo.count():
                    next_row = min(current_row, self.history_combo.count() - 1)
                    self.history_combo.setCurrentIndex(next_row)
                    self.history_combo.lineEdit().setText(str(self.history_combo.itemData(next_row)))
                else:
                    self.history_combo.setCurrentIndex(-1)
                    self.history_combo.clearEditText()
                self.history_combo.blockSignals(False)
                self.history_combo.delete_hover_row = -1
                self.history_combo.view().viewport().update()
            self.device_output.setPlainText(f"已删除连接历史：{address}\n设备本身不会被断开。")
            self.statusBar().showMessage(f"已删除连接记录 · {address}（设备连接不受影响）")

    def remove_offline_device(self) -> None:
        """Forget an offline device and its matching connection history."""
        if self._connection_busy:
            self.statusBar().showMessage("连接状态操作正在进行，请稍候…")
            return
        serial = self.current_serial()
        device = next((item for item in self.devices if item.serial == serial), None)
        if not device:
            return self._show_error("请先选择要删除的设备")
        if device.state != "offline":
            return self._show_error("只有离线设备可以从列表中删除")

        self.devices = [item for item in self.devices if item.serial != serial]
        self._pending_disconnects.discard(serial)
        self._dismissed_devices.add(serial)
        self.repo.remove_history(serial)
        self._rebuild_device_combo()
        self._render_device_table()
        self._last_selected_serial = self.current_serial()
        self._reload_history("")
        self._set_shell_log_view(self.current_serial())
        self._update_scrcpy_status(self.current_serial())
        self.device_output.setPlainText(f"已删除离线设备：{serial}\n同时移除了对应的连接历史。")
        self.statusBar().showMessage(f"已删除离线设备 · {serial}")

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
        if serial in self.scrcpy_starting:
            self.statusBar().showMessage(f"Scrcpy 正在启动 · {serial}")
            return
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
            scrcpy_path = self.resolver.resolve("scrcpy")
            adb_path = self.resolver.resolve("adb")
            if not scrcpy_path:
                return self._show_error("未找到 scrcpy，请先在设置中配置路径")
            if not adb_path:
                return self._show_error("未找到 adb，请先在设置中配置路径")
            process = ProcessRunner.start(scrcpy_path, args, env=self._scrcpy_environment(adb_path))
            self.scrcpy_starting.add(serial)
            handle = ScrcpyHandle(process=process, serial=serial, log_callback=self._emit_scrcpy_log)
            self.scrcpy_processes[serial] = handle
            if serial in self.scrcpy_video_ready:
                handle.video_ready.set()
                self.scrcpy_video_ready.discard(serial)
            self.scrcpy_output.appendPlainText("正在启动：scrcpy " + " ".join(args))
            self._show_device_log()
            self.device_output.setPlainText("正在启动：scrcpy " + " ".join(args))
            self.statusBar().showMessage(f"Scrcpy 正在启动 · {serial}")
            threading.Thread(
                target=self._wait_for_scrcpy_window,
                args=(serial, handle),
                name=f"ADBLiteScrcpy-{serial}",
                daemon=True,
            ).start()
        except Exception as exc: self._show_error(str(exc))

    @staticmethod
    def _scrcpy_environment(adb_path: str) -> dict[str, str]:
        """Give scrcpy an explicit ADB path when PATH is not inherited."""
        environment = os.environ.copy()
        environment["ADB"] = adb_path
        adb_dir = str(Path(adb_path).parent)
        current_path = environment.get("PATH", "")
        environment["PATH"] = adb_dir + (os.pathsep + current_path if current_path else "")
        return environment

    def _wait_for_scrcpy_window(self, serial: str, handle: ScrcpyHandle) -> None:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.scrcpy_processes.get(serial) is not handle:
                return
            if handle.poll() is not None:
                self.scrcpy_start_failed.emit(serial, "进程已退出，投屏窗口未出现")
                return
            if handle.video_ready.wait(0.15):
                self.scrcpy_ready.emit(serial)
                return
            time.sleep(0.01)
        self.scrcpy_start_failed.emit(serial, "等待投屏窗口超时（90 秒）")

    @Slot(str)
    def _scrcpy_start_ready(self, serial: str) -> None:
        handle = self.scrcpy_processes.get(serial)
        if not handle:
            return
        if serial not in self.scrcpy_starting:
            return
        if handle.poll() is not None:
            self._scrcpy_start_failed(serial, "投屏进程已退出")
            return
        self.scrcpy_starting.discard(serial)
        self.scrcpy_video_ready.discard(serial)
        self._update_scrcpy_status(serial)
        self.scrcpy_output.appendPlainText(f"Scrcpy 投屏窗口已出现：{serial}")
        self.statusBar().showMessage(f"Scrcpy 已启动 · {serial}")

    @Slot(str, str)
    def _scrcpy_start_failed(self, serial: str, message: str) -> None:
        handle = self.scrcpy_processes.get(serial)
        if not handle or serial not in self.scrcpy_starting:
            return
        self.scrcpy_starting.discard(serial)
        self.scrcpy_video_ready.discard(serial)
        self.scrcpy_processes.pop(serial, None)
        if handle.poll() is None:
            handle.terminate()
        self._update_scrcpy_status(serial)
        self.scrcpy_output.appendPlainText(f"Scrcpy 启动失败：{message}")
        self.statusBar().showMessage(f"Scrcpy 启动失败 · {serial} · {message}")

    def stop_scrcpy(self) -> None:
        serial = self.current_serial()
        if not serial:
            return self._show_error("请先选择需要停止 scrcpy 的设备")
        process = self.scrcpy_processes.get(serial)
        if not process or process.poll() is not None:
            self.scrcpy_processes.pop(serial, None)
            self.scrcpy_starting.discard(serial)
            self.scrcpy_video_ready.discard(serial)
            self._update_scrcpy_status(serial)
            self.scrcpy_output.appendPlainText(f"{serial} 当前没有运行中的 scrcpy")
            self.statusBar().showMessage(f"{serial} 没有运行中的 Scrcpy")
            return
        process.terminate()
        self.scrcpy_processes.pop(serial, None)
        self.scrcpy_starting.discard(serial)
        self.scrcpy_video_ready.discard(serial)
        self._update_scrcpy_status(serial)
        self.scrcpy_output.appendPlainText(f"{serial} 的 scrcpy 已停止")
        self.statusBar().showMessage(f"Scrcpy 已停止 · {serial}")

    def _emit_scrcpy_log(self, serial: str, line: str) -> None:
        if re.search(r"\bTexture:\s*\d+\s*x\s*\d+", line, re.IGNORECASE):
            self.scrcpy_video_ready.add(serial)
            handle = self.scrcpy_processes.get(serial)
            if handle:
                handle.video_ready.set()
        if "scrcpy 进程已退出" in line:
            self.scrcpy_finished.emit(serial)
        self.scrcpy_log.emit(f"[{serial}] {line}")

    def _append_scrcpy_log(self, line: str) -> None:
        if hasattr(self, "scrcpy_output"):
            self.scrcpy_output.appendPlainText(line)
        if hasattr(self, "device_output"):
            self._show_device_log()
            self.device_output.appendPlainText(line)

    @Slot(str)
    def _scrcpy_finished(self, serial: str) -> None:
        """Clear stale running/starting state after the native window closes."""
        handle = self.scrcpy_processes.get(serial)
        if not handle:
            return
        if serial in self.scrcpy_starting:
            self._scrcpy_start_failed(serial, "进程已退出，投屏窗口未出现")
            return
        if handle.poll() is None:
            return
        self.scrcpy_processes.pop(serial, None)
        self.scrcpy_video_ready.discard(serial)
        self._update_scrcpy_status(serial)
        if serial == self.current_serial():
            self.statusBar().showMessage(f"Scrcpy 已退出 · {serial}")

    def closeEvent(self, event) -> None:
        # scrcpy is an independent native window. Do not terminate its
        # processes when ADBLite exits; they remain usable on their devices.
        if hasattr(self, "phone_bridge_page"):
            self.phone_bridge_page.stop_server()
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
        commands = self.repo.commands()
        for row, command in enumerate(commands):
            item = QListWidgetItem(command.name)
            item.setToolTip(f"{command.runner} · {command.name}")
            item.setData(Qt.ItemDataRole.UserRole, command.runner)
            self.command_list.addItem(item)
            row_widget = QWidget()
            row_widget.setObjectName("commandRow")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(10, 7, 6, 7)
            row_layout.setSpacing(8)
            title = QLabel(command.name)
            title.setToolTip(command.name)
            title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            row_layout.addWidget(title)
            runner = QLabel(command.runner.upper())
            runner.setObjectName("commandRunnerMeta")
            row_layout.addWidget(runner)
            delete_button = QToolButton()
            delete_button.setObjectName("commandDeleteButton")
            delete_button.setIcon(interface_icon("delete"))
            delete_button.setIconSize(QSize(14, 14))
            delete_button.setToolTip("删除命令")
            delete_button.clicked.connect(lambda _checked=False, index=row: self.delete_command(index))
            row_layout.addWidget(delete_button)
            item.setSizeHint(row_widget.sizeHint())
            self.command_list.setItemWidget(item, row_widget)
        if hasattr(self, "command_meta"):
            self.command_meta.setText(f"{len(commands)} 条")
        if hasattr(self, "command_search"):
            self._filter_commands(self.command_search.text())

    def _filter_commands(self, text: str) -> None:
        query = text.strip().casefold()
        runner_filter = "all"
        if hasattr(self, "command_filter_tabs"):
            runner_filter = str(self.command_filter_tabs.tabData(self.command_filter_tabs.currentIndex()) or "all")
        visible = 0
        for row in range(self.command_list.count()):
            item = self.command_list.item(row)
            runner_matches = runner_filter == "all" or item.data(Qt.ItemDataRole.UserRole) == runner_filter
            matches = runner_matches and (not query or query in item.text().casefold())
            item.setHidden(not matches)
            visible += int(matches)
        if hasattr(self, "command_meta"):
            total = self.command_list.count()
            self.command_meta.setText(f"{visible}/{total} 条" if query else f"{total} 条")

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

    def delete_command(self, row: int | None = None) -> None:
        row = self.command_list.currentRow() if row is None else row
        commands = self.repo.commands()
        if 0 <= row < len(commands): commands.pop(row); self.repo.save_commands(commands); self._reload_commands()

    def run_command(self) -> None:
        row = self.command_list.currentRow(); commands = self.repo.commands()
        if not (0 <= row < len(commands)): return self._show_error("请先选择命令")
        command = commands[row]; serial = self.current_serial()
        if command.runner == "adb": fn = lambda: self.adb.run(command.args, serial)
        elif command.runner == "scrcpy":
            scrcpy_target = ["--serial", serial] if serial else []
            scrcpy_path = self.resolver.resolve("scrcpy")
            adb_path = self.resolver.resolve("adb")
            fn = lambda: ProcessRunner.run(scrcpy_path, [*scrcpy_target, *command.args], env=self._scrcpy_environment(adb_path))
        elif command.runner == "process": fn = lambda: ProcessRunner.run(command.args[0], command.args[1:])
        else:
            rendered = command.command.replace("${serial}", serial).replace("${adb}", self.resolver.resolve("adb")).replace("${scrcpy}", self.resolver.resolve("scrcpy"))
            fn = lambda: ProcessRunner.run_cmd(rendered)
        self._run_async(fn, lambda result: self._show_result(self.command_output, result))

    def _show_result(self, target: QPlainTextEdit, result) -> None:
        target.appendPlainText(f"退出码：{result.returncode}\n{result.stdout}{result.stderr}".strip())

    def _input(self, title: str, placeholder: str, initial: str = ""):
        dialog = QDialog(self); dialog.setWindowTitle(title); layout = QFormLayout(dialog); field = QLineEdit(initial); field.setPlaceholderText(placeholder); layout.addRow("地址", field); buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addRow(buttons); ok = dialog.exec() == QDialog.DialogCode.Accepted; return field.text(), ok

    def _notice(self, message: str) -> None: QMessageBox.information(self, "ADBLite", message)
    def _show_error(self, message: str) -> None: QMessageBox.critical(self, "ADBLite", message)
