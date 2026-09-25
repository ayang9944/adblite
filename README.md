# ADBLite

ADBLite 是一个面向个人使用的 Windows 桌面工具，用于集中管理 ADB 设备、启动 scrcpy、打开设备终端和执行常用命令。

当前版本：`v0.2.0`

## v0.2.0 更新内容

- 全新设备管理界面：使用表格展示设备标识、名称、连接状态和快捷操作，并支持设备搜索。
- 完善多设备管理：保留已知设备的离线状态，可分别启动或停止每台设备的 scrcpy 和终端会话。
- 新增无线设备自动发现：通过 ADB mDNS 查找已开启无线调试的设备，并支持历史地址快速重连。
- 新增独立设备终端：内置离线 xterm.js，以独立窗口运行 `adb shell -tt`，支持 ANSI 颜色、Tab 补全、方向键、复制粘贴和 `Ctrl+C`。
- 新增日间/夜间主题：主界面与终端主题可分别切换并自动保存。
- 增强 scrcpy 管理：可配置最大尺寸、最大 FPS、视频码率、音频和附加参数，并识别已有 scrcpy 进程。
- 增强设备操作：支持查看设备信息、断开或重连无线设备、重启系统和重启到 Recovery。
- 修复 Windows 本地程序参数解析，带引号或空格的参数现在可以正确传递。
- 增加设备状态合并、ADB 输出解析、mDNS 解析和命令参数解析测试。

## 主要功能

- 扫描、搜索和管理 USB / 无线 ADB 设备；
- 识别已连接、未授权、离线、Recovery、Bootloader 等设备状态；
- 保存无线地址历史，断开后快速重新连接；
- 通过 ADB mDNS 自动发现无线调试设备；
- 按设备启动和停止 scrcpy；
- 为不同设备同时打开独立 ADB Shell 终端；
- 编辑和运行自定义 ADB、scrcpy、普通进程或 CMD 命令；
- 保存界面主题、工具路径和 scrcpy 参数。

## 环境要求

- Windows 10 或 Windows 11；
- Python 3.9 或更高版本；
- ADB；
- scrcpy（仅投屏功能需要）。

可以把 `adb.exe` 和 `scrcpy.exe` 放入项目的 `binaries/` 目录，也可以在应用“设置”页中选择它们的完整路径。若命令行可以看到设备但应用看不到，请确保两者使用的是同一个 `adb.exe`。

## 从源码运行

```powershell
git clone https://github.com/ayang9944/adblite.git
cd adblite
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe .\run.py
```

如果希望激活虚拟环境后运行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

如果 pip 报 `ProxyError`，请先确认代理软件和代理端口是否可用。只需让当前 PowerShell 会话直连时，可以临时清除代理环境变量：

```powershell
Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:ALL_PROXY -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

## 使用说明

### 连接设备

USB 设备开启 USB 调试后会出现在设备列表。无线设备可以输入 `IP:端口` 后连接，也可以点击“自动发现”通过 ADB mDNS 查找。

连接历史保存在 `%APPDATA%/ADBLite/settings.json`。其中只包含工具设置、地址、名称和最近使用时间，不保存设备中的数据。

### 打开终端

点击设备行中的“终端”按钮即可打开独立窗口。每台设备只维护一个终端窗口；再次点击同一设备时会聚焦已有窗口，不同设备的终端可以同时运行。

终端使用项目内置的 xterm.js 渲染 `adb -s SERIAL shell -tt`。所有前端资源均为本地文件，运行时不依赖 CDN。

### 启动 scrcpy

在“设置”页配置最大尺寸、最大 FPS、视频码率、音频和附加参数，然后点击设备行中的投屏按钮。ADBLite 会按设备跟踪 scrcpy 进程，避免重复启动。

## 运行测试

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 打包

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --clean .\ADBLite.spec
```

构建结果位于 `dist/` 目录。发布前请在未安装 Python 的 Windows 环境中验证设备扫描、无线连接、终端和 scrcpy 功能。

## 项目地址

<https://github.com/ayang9944/adblite>
