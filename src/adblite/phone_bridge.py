from __future__ import annotations

import html
import json
import secrets
import socket
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable


MAX_MESSAGE_BYTES = 64 * 1024


def local_ipv4() -> str:
    """Return the most useful local IPv4 address for a phone on the LAN."""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            address = sock.getsockname()[0]
            if address and not address.startswith("127."):
                return address
    except OSError:
        pass
    try:
        address = socket.gethostbyname(socket.gethostname())
        if address:
            return address
    except OSError:
        pass
    return "127.0.0.1"


class _BridgeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class PhoneBridgeServer:
    """Small authenticated HTTP text bridge used by the ADBLite UI.

    The service intentionally handles text only.  Android APK/file transfer
    stays on the ADB path and is not exposed through this LAN endpoint.
    """

    def __init__(
        self,
        data_dir: str | Path,
        bind_host: str = "0.0.0.0",
        port: int = 8899,
        access_token: str = "",
        on_message: Callable[[str], None] | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.text_path = self.data_dir / "text.txt"
        self.received_path = self.data_dir / "received.txt"
        self.bind_host = bind_host or "0.0.0.0"
        self.requested_port = int(port)
        self.access_token = str(access_token).strip()
        self.on_message = on_message
        self.token = ""
        self._server: _BridgeHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def port(self) -> int:
        if self._server is not None:
            return int(self._server.server_address[1])
        return self.requested_port

    @property
    def access_host(self) -> str:
        if self.bind_host in {"", "0.0.0.0", "::"}:
            return local_ipv4()
        return self.bind_host.strip("[]")

    @property
    def url(self) -> str:
        token = urllib.parse.quote(self.token, safe="")
        return f"http://{self.access_host}:{self.port}/?token={token}"

    def start(self) -> str:
        if self.running:
            return self.url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.access_token:
            if len(self.access_token.encode("utf-8")) > 128:
                raise ValueError("访问令牌不能超过 128 字节")
            self.token = self.access_token
        else:
            self.token = secrets.token_urlsafe(24)
        handler = self._handler_class()
        server = _BridgeHTTPServer((self.bind_host, self.requested_port), handler)
        server.bridge = self  # type: ignore[attr-defined]
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, name="ADBLitePhoneBridge", daemon=True)
        self._thread.start()
        return self.url

    def stop(self) -> None:
        server = self._server
        self._server = None
        self.token = ""
        if server is None:
            return
        try:
            server.shutdown()
        finally:
            server.server_close()
        thread = self._thread
        self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=2)

    def read_text(self) -> str:
        try:
            return self.text_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""
        except OSError:
            return ""

    def write_text(self, text: str) -> None:
        text = str(text)
        encoded = text.encode("utf-8")
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise ValueError("文本过大，最多支持 64 KB")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.text_path.with_suffix(".tmp")
        with self._lock:
            temporary.write_bytes(encoded)
            temporary.replace(self.text_path)

    def read_received(self) -> str:
        try:
            return self.received_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return ""

    def clear_received(self) -> None:
        with self._lock:
            self.received_path.unlink(missing_ok=True)

    def _append_received(self, text: str) -> None:
        timestamp = time.strftime("%m-%d %H:%M:%S")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.received_path.open("a", encoding="utf-8") as stream:
                stream.write(f"[{timestamp}] {text}\n")
        if self.on_message:
            self.on_message(text)

    def _handler_class(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ADBLitePhoneBridge/1.0"

            def _send(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, payload: dict) -> None:
                self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

            def _token(self) -> str:
                authorization = self.headers.get("Authorization", "")
                if authorization.lower().startswith("bearer "):
                    return authorization[7:].strip()
                query = urllib.parse.urlsplit(self.path).query
                return urllib.parse.parse_qs(query).get("token", [""])[0]

            def _authorized(self) -> bool:
                supplied = self._token()
                return bool(supplied) and secrets.compare_digest(supplied, bridge.token)

            def _unauthorized(self) -> None:
                self._send(HTTPStatus.UNAUTHORIZED, "未授权，请使用 ADBLite 显示的访问地址。".encode("utf-8"), "text/plain; charset=utf-8")

            def do_GET(self) -> None:
                path = urllib.parse.urlsplit(self.path).path
                if path == "/health":
                    self._json(HTTPStatus.OK, {"running": True})
                    return
                if not self._authorized():
                    self._unauthorized()
                    return
                if path in {"/", "/index.html"}:
                    self._send(HTTPStatus.OK, self._page().encode("utf-8"), "text/html; charset=utf-8")
                    return
                if path == "/api/state":
                    self._json(HTTPStatus.OK, {"text": bridge.read_text(), "received": bridge.read_received()})
                    return
                self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")

            def do_POST(self) -> None:
                path = urllib.parse.urlsplit(self.path).path
                if not self._authorized():
                    self._unauthorized()
                    return
                if path != "/api/send":
                    self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")
                    return
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = 0
                if length <= 0 or length > MAX_MESSAGE_BYTES:
                    self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "文本大小必须在 1 到 65536 字节之间"})
                    return
                raw = self.rfile.read(length)
                try:
                    if "application/json" in self.headers.get("Content-Type", ""):
                        payload = json.loads(raw.decode("utf-8"))
                        text = str(payload.get("text", ""))
                    else:
                        values = urllib.parse.parse_qs(raw.decode("utf-8", errors="replace"))
                        text = (values.get("text") or [""])[0]
                except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "请求格式无效"})
                    return
                text = text.strip()
                if not text:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "文本不能为空"})
                    return
                if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
                    self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "文本过大"})
                    return
                bridge._append_received(text)
                self._json(HTTPStatus.OK, {"message": f"已收到（{len(text)} 字）"})

            def _page(self) -> str:
                token = json.dumps(bridge.token, ensure_ascii=False)
                title = html.escape("ADBLite 手机桥接")
                page = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%TITLE%</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#111827;color:#e5e7eb;margin:0;padding:16px}
main{max-width:720px;margin:auto}h1{font-size:18px;color:#5eead4;margin:0 0 8px}
textarea,input{width:100%;box-sizing:border-box;background:#182235;color:#fff;border:1px solid #334155;border-radius:8px;padding:10px;font-size:16px}
textarea{min-height:150px;resize:vertical;white-space:pre-wrap}button{width:100%;margin-top:10px;padding:12px;border:0;border-radius:8px;background:#0f8f83;color:#fff;font-size:16px}
.muted{color:#94a3b8;font-size:12px;margin:8px 0}hr{border:0;border-top:1px solid #334155;margin:22px 0}
</style></head><body><main>
<h1>ADBLite 手机桥接</h1><div class="muted" id="updated">正在连接…</div>
<textarea id="box" readonly></textarea><button onclick="copyText()">复制电脑文本</button><button id="open" hidden onclick="openLink()">打开链接</button>
<hr><h1>手机 → 电脑</h1><textarea id="inp" placeholder="输入文本后点击发送"></textarea><button onclick="sendText()">发送到电脑</button><div class="muted" id="msg"></div>
<script>
const TOKEN=%TOKEN%; let latest='';
async function state(){try{const r=await fetch('/api/state',{headers:{Authorization:'Bearer '+TOKEN}});if(!r.ok)throw Error();const d=await r.json();latest=d.text||'';document.getElementById('box').value=latest;document.getElementById('updated').textContent='已连接 · '+new Date().toLocaleTimeString();const b=document.getElementById('open');if(/^https?:\\/\\//i.test(latest.trim())){b.hidden=false;}else{b.hidden=true;}}catch(e){document.getElementById('updated').textContent='连接已断开';}}
function copyText(){navigator.clipboard?.writeText(latest).then(()=>document.getElementById('msg').textContent='已复制').catch(()=>{document.getElementById('box').select();document.execCommand('copy');document.getElementById('msg').textContent='已复制';});}
function openLink(){if(/^https?:\\/\\//i.test(latest.trim())) location.href=latest.trim();}
async function sendText(){const field=document.getElementById('inp');const text=field.value.trim();if(!text)return;const r=await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+TOKEN},body:JSON.stringify({text})});const d=await r.json();document.getElementById('msg').textContent=d.message||d.error||'发送失败';if(r.ok)field.value='';}
state();setInterval(state,1500);
</script></main></body></html>'''
                return page.replace("%TITLE%", title).replace("%TOKEN%", token)

            def log_message(self, fmt: str, *args) -> None:
                # Do not print URLs because they contain the access token.
                return

        return Handler
