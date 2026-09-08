"""
WSGI 适配层：让原本基于 http.server 的后端可在 PythonAnywhere / 任意 WSGI 服务器运行。

实现策略（零侵入）：
  把 WSGI 的环境变量重建为「原始 HTTP 请求报文」，喂给既有 Handler(BaseHTTPRequestHandler)，
  捕获 Handler 写入 wfile 的完整响应（状态行+头+正文），再转回 WSGI 响应返回。
  业务代码（app.py 内的 Handler 与各路由）完全不变，避免引入 bug。

本地仍以 `python app.py` 运行 http.server；本文件仅用于 WSGI 托管场景。
"""
import io
import os
import sys
import traceback

# 保证能 import 同目录的 app 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app  # noqa: E402  (供 _ensure_db_ready 调用 init_db/migrate 等)
from app import Handler  # noqa: E402


class _FakeSocket:
    """让 BaseHTTPRequestHandler 从内存 BytesIO 读写，而不是真实 socket。"""

    def __init__(self, rfile, wfile):
        self._r, self._w = rfile, wfile

    def makefile(self, mode="rb", bufsize=-1):
        return self._r if "r" in mode else self._w

    def close(self):
        pass

    def shutdown(self, *a):
        pass


class WSGIHandler(Handler):
    """复用既有 Handler 的全部路由逻辑，但把底层 I/O 改为内存缓冲，
    避免在 WSGI 环境下触碰真实 socket。"""

    def setup(self):
        # 先放空缓冲，handle() 期间不会被驱动；实际请求在 application() 中注入
        self.rfile = io.BytesIO()
        self.wfile = io.BytesIO()
        self.connection = _FakeSocket(self.rfile, self.wfile)

    def handle(self):
        # 覆盖基类：不在 __init__ 中自动处理，交给 application() 手动驱动一次请求
        pass

    def finish(self):
        # 覆盖基类：不要关闭/冲刷底层（这里是内存缓冲），便于读回响应
        pass


def _build_raw_request(environ):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/")
    qs = environ.get("QUERY_STRING", "")
    if qs:
        path = path + "?" + qs
    lines = ["%s %s HTTP/1.1" % (method, path)]
    added = set()
    for k, v in environ.items():
        if k.startswith("HTTP_"):
            name = k[5:].replace("_", "-").title()
        elif k in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            name = k.replace("_", "-").title()
        else:
            continue
        if name in added or not isinstance(v, str):
            continue
        added.add(name)
        lines.append("%s: %s" % (name, v))
    if "Host" not in added:
        lines.append("Host: localhost")
    raw = "\r\n".join(lines) + "\r\n\r\n"
    body = b""
    cl = environ.get("CONTENT_LENGTH")
    if cl:
        try:
            cl = int(cl)
        except (TypeError, ValueError):
            cl = 0
        if cl and cl > 0:
            body = environ["wsgi.input"].read(cl)
    return raw.encode("utf-8") + body


def _parse_response(data):
    head, _, body = data.partition(b"\r\n\r\n")
    head_lines = head.split(b"\r\n")
    status_line = head_lines[0].decode("latin-1")
    parts = status_line.split(None, 2)
    code = parts[1] if len(parts) > 1 else "200"
    reason = parts[2] if len(parts) > 2 else "OK"
    status = "%s %s" % (code, reason)
    headers = []
    for hl in head_lines[1:]:
        if b":" in hl:
            k, v = hl.split(b":", 1)
            headers.append((k.decode("latin-1").strip(), v.decode("latin-1").strip()))
    return status, headers, body


def application(environ, start_response):
    try:
        raw = _build_raw_request(environ)
        handler = WSGIHandler(None, ("127.0.0.1", 0), None)
        # 注入真实请求报文，手动驱动一次处理
        handler.rfile = io.BytesIO(raw)
        handler.wfile = io.BytesIO()
        handler.handle_one_request()
        handler.wfile.seek(0)
        status, headers, body = _parse_response(handler.wfile.read())
        start_response(status, headers)
        return [body]
    except Exception:  # noqa: BLE001
        tb = traceback.format_exc()
        try:
            sys.stderr.write(tb)
        except Exception:
            pass
        start_response("500 Internal Server Error",
                       [("Content-Type", "text/plain; charset=utf-8")])
        return [("500 Internal Server Error\n\n" + tb).encode("utf-8")]


# ---- 启动初始化（复刻 main() 的建库 + 迁移，确保 WSGI 模式下数据库就绪）----
_INIT_DONE = False


def _ensure_db_ready():
    global _INIT_DONE
    if _INIT_DONE:
        return
    try:
        app.init_db()
        app.migrate()
        app.migrate_team_config()
        app.migrate_violation_fields()
        app.migrate_phase19()
        app.migrate_phase21()
    except Exception:  # noqa: BLE001
        import traceback as _tb
        try:
            sys.stderr.write("DB init warning:\n" + _tb.format_exc())
        except Exception:
            pass
    finally:
        _INIT_DONE = True


_ensure_db_ready()
