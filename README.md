# ADBLite

一个面向个人使用的轻量 ADB / scrcpy / 快捷命令工具。当前版本重点解决：

- 扫描和选择 ADB 设备；
- 保存 USB 序列号和无线地址历史，断开后可快速重新连接；
- 用预设参数启动 scrcpy；
- 为当前设备打开持久 ADB Shell 会话；
- 编辑和运行自定义 ADB、scrcpy、普通进程或 CMD 命令。

## 运行

```powershell
cd adblite
py -m venv .venv
# 如果 PowerShell 允许脚本执行：
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

如果看到“在此系统上禁止运行脚本”，可以不激活虚拟环境，直接使用虚拟环境里的 Python：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe .\run.py
```

也可以只对当前 PowerShell 窗口临时放宽策略（关闭窗口后恢复）：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

如果使用 CMD，则执行 `.venv\Scripts\activate.bat`。

如果 pip 报 `ProxyError`，先清除当前终端中的代理变量，再指定一个可访问的软件源：

```powershell
Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:ALL_PROXY -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
python run.py
```

如果清华镜像不可访问，把地址替换成官方源 `https://pypi.org/simple`。

本机当前检测到 Windows Internet Settings 中启用了 `127.0.0.1:19828`，但该端口没有可用代理，因此 pip 会报连接重置。若你平时不需要这个代理，可以在“设置 > 网络和 Internet > 代理”中关闭“使用代理服务器”，或在 PowerShell 中关闭当前用户代理：

```powershell
Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -Type DWord -Value 0
```

如果这个代理是你主动使用的，请先启动对应代理软件，或把端口改成实际监听的端口；不要盲目关闭它。只想让 pip 永久直连而不影响浏览器时，可以给 pip 单独设置环境变量：

```powershell
[Environment]::SetEnvironmentVariable('NO_PROXY', '*', 'User')
```

也可以把 `adb.exe`、`scrcpy.exe` 放入 `adblite/binaries/`，或在“设置”中填写完整路径。

如果命令行中的 `adb` 能运行，但应用刷新不到设备，请在“设置”中选择命令行实际使用的 `adb.exe`。例如 ADB 位于 `D:\myTool\platform-tools\adb.exe` 时，就选择这个文件。应用和命令行必须使用同一个 ADB，才能看到同一个 ADB Server 下的设备。

连接历史保存在 `%APPDATA%/ADBLite/settings.json`。历史只保存地址、名称和最近使用时间，不保存设备数据。

Shell 页面使用 `adb -s SERIAL shell` 持久进程，支持持续输入命令和实时输出；它不是完整的 ANSI 终端模拟器，暂不保证全屏交互式程序（例如 vim、top）的显示效果。
