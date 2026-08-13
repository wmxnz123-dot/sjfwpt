#!/usr/bin/env python3
"""Serve this prototype and persist browser annotation edits.

Run from the project root:
    python3 prototype-annotator/server.py

The annotation runtime sends PUT requests to
/.prototype-annotator/api/annotations.  A plain static-file server cannot
handle that request, which is why edits otherwise remain only in localStorage.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS_FILE = PROJECT_ROOT / "prototype-annotator" / "annotations.json"
HISTORY_FILE = PROJECT_ROOT / "prototype-annotator" / "history.jsonl"
API_PATH = "/.prototype-annotator/api/annotations"


def write_json_atomically(path: Path, data: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class AnnotationHandler(SimpleHTTPRequestHandler):
    """Static file handler plus the small annotation write API."""

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def do_PUT(self) -> None:  # noqa: N802 (HTTP method name)
        if urlparse(self.path).path != API_PATH:
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 10 * 1024 * 1024:
                raise ValueError("请求内容不能为空且不能超过 10 MB")
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            data = payload.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("annotations"), list):
                raise ValueError("请求中缺少有效的标注数据")

            # Keep the on-disk data format predictable before accepting it.
            data.setdefault("version", 1)
            data.setdefault("pages", [])
            data.setdefault("surfaces", [])
            write_json_atomically(ANNOTATIONS_FILE, data)

            history = {
                "at": datetime.now(timezone.utc).isoformat(),
                "action": payload.get("action", "save"),
                "annotationId": (payload.get("annotation") or {}).get("id"),
            }
            with HISTORY_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(history, ensure_ascii=False) + "\n")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            self.send_error(HTTPStatus.BAD_REQUEST, str(error))
            return
        except OSError as error:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"无法写入标注文件：{error}")
            return

        response = json.dumps({"ok": True, "reportRefreshRequired": True}, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def main() -> None:
    parser = argparse.ArgumentParser(description="启动可写入标注的原型服务")
    parser.add_argument("--host", default="::", help="监听地址（默认 :: 同时监听 IPv4+IPv6，localhost 与 127.0.0.1 均可访问）")
    parser.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    args = parser.parse_args()

    handler = AnnotationHandler

    # 双栈监听：绑定 :: 时开启 IPV6_V6ONLY=0，使 IPv4 (127.0.0.1) 与 IPv6 (::1) 都能访问。
    if args.host == "::":
        class DualStackServer(ThreadingHTTPServer):
            address_family = socket.AF_INET6

            def server_bind(self) -> None:
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                super().server_bind()

        server = DualStackServer((args.host, args.port), handler)
    else:
        server = ThreadingHTTPServer((args.host, args.port), handler)

    print(f"Prototype annotation server: http://{args.host}:{args.port}/")
    print(f"Annotation data file: {ANNOTATIONS_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
