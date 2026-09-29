from __future__ import annotations

import json
import locale
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from .domain import ConnectionHistory, CustomCommand, Device


def parse_adb_devices_output(output: str) -> list[Device]:
    """Parse ``adb devices -l`` output without depending on ADB availability."""
    devices: list[Device] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[0] in {"*", "List"}:
            continue
        attrs = dict(item.split(":", 1) for item in fields[2:] if ":" in item)
        devices.append(
            Device(
                serial=fields[0],
                state=fields[1],
                model=attrs.get("model", "").replace("_", " "),
                transport_id=attrs.get("transport_id", ""),
            )
        )
    return devices


def parse_mdns_services_output(output: str) -> list[str]:
    """Return unique host:port endpoints advertised for wireless ADB."""
    addresses: list[str] = []
    for line in output.splitlines():
        if "_adb-tls-connect._tcp" not in line and "_adb._tcp" not in line:
            continue
        match = re.search(r"((?:\[[0-9a-fA-F:]+\]|[^\s:]+):\d{1,5})\s*$", line.strip())
        if match and match.group(1) not in addresses:
            addresses.append(match.group(1))
    return addresses


class SettingsRepository:
    def __init__(self) -> None:
        self.path = Path(os.environ.get("APPDATA", Path.home())) / "ADBLite" / "settings.json"
        self.data: dict = {
            "adb_path": "", "scrcpy_path": "", "history": [], "commands": [], "shell_history": [],
            "theme": "light", "terminal_theme": "light",
            "scrcpy_max_size": 1920, "scrcpy_max_fps": 60, "scrcpy_bitrate": "8M",
            "scrcpy_extra": "", "scrcpy_no_audio": False,
        }
        self.load()

    def load(self) -> None:
        try:
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def histories(self) -> list[ConnectionHistory]:
        return [ConnectionHistory(**item) for item in self.data.get("history", [])]

    def remember(self, address: str, name: str = "", kind: str = "wifi") -> None:
        address = address.strip()
        if not address:
            return
        old = [h for h in self.histories() if h.address != address]
        old.insert(0, ConnectionHistory(address=address, name=name.strip(), kind=kind))
        self.data["history"] = [h.__dict__ for h in old[:30]]
        self.save()

    def remove_history(self, address: str) -> None:
        self.data["history"] = [h.__dict__ for h in self.histories() if h.address != address]
        self.save()

    def update_history(self, old_address: str, new_address: str, name: str = "") -> None:
        updated: list[ConnectionHistory] = []
        for item in self.histories():
            if item.address == old_address:
                item.address = new_address.strip()
                if name.strip():
                    item.name = name.strip()
                item.kind = "wifi"
            updated.append(item)
        self.data["history"] = [item.__dict__ for item in updated]
        self.save()

    def commands(self) -> list[CustomCommand]:
        return [CustomCommand(**item) for item in self.data.get("commands", [])]

    def save_commands(self, commands: Iterable[CustomCommand]) -> None:
        self.data["commands"] = [c.__dict__ for c in commands]
        self.save()


class BinaryResolver:
    def __init__(self, repo: SettingsRepository) -> None:
        self.repo = repo

    def resolve(self, name: str) -> str:
        configured = self.repo.data.get(f"{name}_path", "").strip()
        if configured:
            configured_path = Path(configured)
            if configured_path.is_file():
                return str(configured_path)
            if configured_path.is_dir() and (configured_path / f"{name}.exe").exists():
                return str(configured_path / f"{name}.exe")
        if name == "adb":
            explicit = os.environ.get("ADB_PATH", "").strip()
            if explicit and Path(explicit).exists():
                return explicit
        base = Path(__file__).resolve().parents[2] / "binaries"
        candidates = [base / name / f"{name}.exe", base / f"{name}.exe", base / name / name]
        if name == "adb":
            for env_name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
                sdk = os.environ.get(env_name, "").strip()
                if sdk:
                    candidates.append(Path(sdk) / "platform-tools" / "adb.exe")
            candidates.extend([
                Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
                Path.home() / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            ])
        elif name == "scrcpy":
            candidates.extend([
                Path.home() / "scoop" / "apps" / "scrcpy" / "current" / "scrcpy.exe",
                Path(os.environ.get("PROGRAMFILES", "")) / "scrcpy" / "scrcpy.exe",
            ])
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return shutil.which(f"{name}.exe") or shutil.which(name) or ""


class ProcessRunner:
    @staticmethod
    def _hidden_window_flags() -> int:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    @staticmethod
    def _decode_output(value: bytes | str) -> str:
        if isinstance(value, str):
            return value
        # ADB and most modern tools emit UTF-8, while Windows console tools
        # (for example ipconfig) commonly use the system OEM code page.
        encodings = ["utf-8", locale.getpreferredencoding(False)]
        if os.name == "nt":
            encodings.extend(["oem", "cp936"])
        tried: set[str] = set()
        for encoding in encodings:
            if not encoding or encoding in tried:
                continue
            tried.add(encoding)
            try:
                return value.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
        return value.decode("utf-8", errors="replace")

    @staticmethod
    def run(program: str, args: list[str], timeout: int = 120, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
        if not program:
            raise FileNotFoundError("未找到可执行文件，请在设置中配置路径")
        result = subprocess.run([program, *args], capture_output=True, text=False, timeout=timeout, cwd=cwd, creationflags=ProcessRunner._hidden_window_flags())
        return subprocess.CompletedProcess(
            result.args,
            result.returncode,
            ProcessRunner._decode_output(result.stdout),
            ProcessRunner._decode_output(result.stderr),
        )

    @staticmethod
    def run_cmd(command: str, timeout: int = 120, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
        """Run *command* with the same parsing rules as a Windows cmd prompt.

        ``subprocess`` quotes every item in an argument list according to the
        C runtime's ``argv`` rules.  ``cmd.exe`` does not use those rules for
        the text following ``/c``: in particular, the inserted ``\"`` pairs
        become literal backslashes.  Commands containing normally quoted
        arguments (URLs, paths, JSON, and so on) therefore reach the target
        program corrupted.

        Build only cmd.exe's outer invocation here and leave the user's
        command text untouched.  This also preserves cmd syntax such as
        pipes, redirections, variable expansion, parentheses and chaining,
        instead of trying to recognize individual command shapes.
        """
        if os.name != "nt":
            raise OSError("cmd commands are only available on Windows")

        cmd = os.environ.get("COMSPEC", "").strip() or shutil.which("cmd.exe") or "cmd.exe"
        cmd_prefix = subprocess.list2cmdline([cmd])
        command_line = f'{cmd_prefix} /d /s /c "{command}"'
        result = subprocess.run(
            command_line,
            executable=cmd,
            capture_output=True,
            text=False,
            timeout=timeout,
            cwd=cwd,
            creationflags=ProcessRunner._hidden_window_flags(),
        )
        return subprocess.CompletedProcess(
            result.args,
            result.returncode,
            ProcessRunner._decode_output(result.stdout),
            ProcessRunner._decode_output(result.stderr),
        )

    @staticmethod
    def start(program: str, args: list[str], cwd: str | None = None) -> subprocess.Popen[str]:
        if not program:
            raise FileNotFoundError("未找到可执行文件，请在设置中配置路径")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | ProcessRunner._hidden_window_flags()
        return subprocess.Popen([program, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=cwd, creationflags=flags)


class AdbClient:
    def __init__(self, resolver: BinaryResolver) -> None:
        self.resolver = resolver

    def run(self, args: list[str], serial: str = "", timeout: int = 120) -> subprocess.CompletedProcess[str]:
        prefix = ["-s", serial] if serial else []
        return ProcessRunner.run(self.resolver.resolve("adb"), [*prefix, *args], timeout)

    def devices(self) -> list[Device]:
        result = ProcessRunner.run(self.resolver.resolve("adb"), ["devices", "-l"], timeout=15)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip() or f"adb exited with code {result.returncode}"
            raise RuntimeError(f"adb devices 执行失败：{detail}")
        return parse_adb_devices_output(result.stdout)

    def mdns_services(self) -> list[str]:
        result = ProcessRunner.run(self.resolver.resolve("adb"), ["mdns", "services"], timeout=15)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip() or "当前 ADB 不支持 mDNS 发现"
            raise RuntimeError(detail)
        return parse_mdns_services_output(result.stdout)
