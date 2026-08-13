#!/usr/bin/env python3
"""Serve a prototype with injected annotation runtime and save annotations locally."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import mimetypes
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from render_annotation_report import candidates_file_for, read_json, render_checklist, render_report, write_text


SKILL_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = SKILL_DIR / "templates" / "runtime"
ANNOTATION_DIR_NAME = "prototype-annotator"
LEGACY_ANNOTATION_DIR_NAME = ".prototype-annotations"
MAX_ASSET_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
INLINE_DATA_RE = re.compile(
    r"<script[^>]+id=[\"']prototype-annotations-data[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
ANNOTATION_README = """# 原型标注说明

本目录由 `prototype-annotator` skill 生成，用于保存原型页面的标注数据和运行时资源。

## 目录说明

- `annotations.json`：标注数据源。AI 生成和页面内手动编辑后的标注最终都应写入这里。
- `assets/`：标注正文引用的图片资产，例如从剪贴板粘贴的截图。
- `page-map.json`：原型扫描结果，用于重新生成标注或校验 selector。
- `history.jsonl`：本地在线评审服务写入的编辑历史。
- `runtime/`：标注层所需的 JavaScript 和 CSS 运行时资源。

## 如何启动在线标注

请在 `prototype-annotator` skill 项目目录中运行本地评审服务，并把当前原型路径作为参数传入。下面命令里的路径均为占位示例，请替换为你本机的实际目录：

```bash
cd /path/to/prototype-annotator
python3 scripts/serve_annotation_review.py /path/to/your/prototype
```

如果不想切换目录，也可以直接使用脚本绝对路径：

```bash
python3 /path/to/prototype-annotator/scripts/serve_annotation_review.py /path/to/your/prototype
```

启动后终端会输出类似地址：

```text
Serving annotation review at http://127.0.0.1:8765/
```

在浏览器中打开该地址即可在线查看、编辑、新增、删除和导出标注。页面内保存的修改会通过本地评审服务回写到本目录的 `annotations.json`。

## 注意事项

- 不建议用普通静态服务（例如 `python3 -m http.server`）进行人工编辑，因为它不能处理回写请求；页面修改只能暂存在浏览器 `localStorage` 草稿中。
- 静态 HTML 中内嵌的标注 JSON 只是离线或读取失败时的兜底快照，正式数据源仍是本目录的 `annotations.json`。
- 如果更新了 skill 的运行时修复，需要重新执行注入命令，或刷新本目录 `runtime/` 下的运行时文件。
- 如需清空或删除标注结果，请运行 `python3 /path/to/prototype-annotator/scripts/clear_annotations.py /path/to/your/prototype`。该命令会移除标注数据和静态 HTML 注入块，但不会删除 React/Vue adapter 源码，以免破坏原型构建。
"""
LEGACY_README_PREFIX = "# Prototype annotations"


def strip_existing_runtime(html: str) -> str:
    start = "<!-- Prototype Annotator runtime -->"
    end = "<!-- /Prototype Annotator runtime -->"
    while start in html and end in html:
        before, rest = html.split(start, 1)
        _, after = rest.split(end, 1)
        html = before + after
    return html


def json_for_script(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def runtime_markup(data: dict) -> str:
    json_text = json_for_script(data)

    def asset_url(name: str) -> str:
        asset = RUNTIME_DIR / name
        version = int(asset.stat().st_mtime) if asset.exists() else int(time.time())
        return f"/{name}?v={version}"

    return "\n".join([
        "<!-- Prototype Annotator runtime -->",
        f'<link rel="stylesheet" href="{asset_url("prototype-annotator.css")}">',
        '<script id="prototype-annotations-data" type="application/json">',
        json_text,
        "</script>",
        f'<script src="{asset_url("markdown-renderer.js")}"></script>',
        f'<script src="{asset_url("mermaid-loader.js")}"></script>',
        f'<script src="{asset_url("prototype-annotator.js")}"></script>',
        "<!-- /Prototype Annotator runtime -->",
    ])


def inject_html(html: str, data: dict) -> str:
    html = strip_existing_runtime(html)
    markup = runtime_markup(data)
    if "</body>" in html:
        return html.replace("</body>", markup + "\n</body>", 1)
    return html + "\n" + markup + "\n"


def write_annotation_readme(annotation_dir: Path) -> None:
    readme = annotation_dir / "README.md"
    if not readme.exists():
        readme.write_text(ANNOTATION_README, encoding="utf-8")
        return
    current = readme.read_text(encoding="utf-8", errors="ignore")
    if current.startswith(LEGACY_README_PREFIX):
        readme.write_text(ANNOTATION_README, encoding="utf-8")


def extract_inline_data(path: Path) -> dict | None:
    if path.suffix.lower() != ".html" or not path.exists():
        return None
    html = path.read_text(encoding="utf-8", errors="ignore")
    match = INLINE_DATA_RE.search(html)
    if not match:
        return None
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return None


def load_inline_data(target: Path, root: Path, entry_name: str) -> dict | None:
    candidates: list[Path] = []
    if target.is_file():
        candidates.append(target)
    else:
        candidates.append(root / entry_name)
        candidates.extend(path for path in sorted(root.rglob("*.html")) if path.name != entry_name)
    for candidate in candidates:
        data = extract_inline_data(candidate)
        if data and isinstance(data.get("annotations"), list):
            return data
    return None


def page_key_for_html(html_path: Path, root_dir: Path, data: dict) -> str | None:
    try:
        rel = str(html_path.relative_to(root_dir))
    except ValueError:
        rel = html_path.name
    name = html_path.name
    for page in data.get("pages", []):
        page_path = str(page.get("path") or "")
        if page_path == rel or page_path == name or page_path.endswith("/" + name):
            return str(page.get("pageKey") or "") or None
    return None


def snapshot_for_page(data: dict, page_key: str | None) -> dict:
    if not page_key:
        return data
    snapshot = dict(data)
    snapshot["pages"] = [page for page in data.get("pages", []) if page.get("pageKey") == page_key]
    snapshot["annotations"] = [ann for ann in data.get("annotations", []) if ann.get("pageKey") == page_key]
    if isinstance(data.get("surfaces"), list):
        snapshot["surfaces"] = [surface for surface in data.get("surfaces", []) if surface.get("pageKey") == page_key]
    return snapshot


def replace_inline_data(html: str, data: dict) -> str:
    json_text = json_for_script(data)
    return INLINE_DATA_RE.sub(
        lambda match: (
            match.group(0)[:match.group(0).find(">") + 1]
            + "\n"
            + json_text
            + "\n</script>"
        ),
        html,
        count=1,
    )


def find_annotation_path(root: Path, annotations: Path | None) -> Path:
    if annotations:
        return annotations.resolve()
    preferred = root / ANNOTATION_DIR_NAME / "annotations.json"
    if preferred.exists():
        return preferred
    legacy = root / LEGACY_ANNOTATION_DIR_NAME / "annotations.json"
    if legacy.exists():
        return legacy
    return preferred


def find_page_map(root: Path) -> Path:
    preferred = root / ANNOTATION_DIR_NAME / "page-map.json"
    if preferred.exists():
        return preferred
    return root / LEGACY_ANNOTATION_DIR_NAME / "page-map.json"


def default_data(root: Path, entry_name: str) -> dict:
    page_map = find_page_map(root)
    pages = []
    if page_map.exists():
        try:
            scanned = json.loads(page_map.read_text(encoding="utf-8"))
            pages = [
                {
                    "pageKey": page.get("pageKey"),
                    "title": page.get("title"),
                    "path": page.get("path"),
                    "route": page.get("route")
                }
                for page in scanned.get("pages", [])
                if page.get("pageKey")
            ]
        except json.JSONDecodeError:
            pages = []
    if not pages:
        pages = [{"pageKey": "P01", "title": root.name, "path": entry_name, "route": "/" + entry_name}]
    return {
        "version": 1,
        "project": {"id": root.name, "name": root.name, "source": "review-server"},
        "pages": pages,
        "annotations": []
    }


def sanitize_asset_stem(value: str) -> str:
    value = re.sub(r"\.[a-zA-Z0-9]+$", "", value or "")
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return value[:72] or "clipboard-image"


def asset_extension(mime_type: str, file_name: str = "") -> str:
    mime_type = (mime_type or "").split(";", 1)[0].strip().lower()
    if mime_type in ALLOWED_IMAGE_MIME_TYPES:
        return ALLOWED_IMAGE_MIME_TYPES[mime_type]
    guessed = (mimetypes.guess_type(file_name or "")[0] or "").lower()
    if guessed in ALLOWED_IMAGE_MIME_TYPES:
        return ALLOWED_IMAGE_MIME_TYPES[guessed]
    raise ValueError(f"Unsupported image type: {mime_type or file_name or 'unknown'}")


def decode_asset_data(payload: dict) -> tuple[bytes, str]:
    mime_type = str(payload.get("mimeType") or "")
    data_url = str(payload.get("dataUrl") or "")
    base64_text = str(payload.get("base64") or "")
    if data_url:
        match = re.match(r"^data:([^;,]+);base64,(.+)$", data_url, re.DOTALL)
        if not match:
            raise ValueError("dataUrl must be a base64 data URL")
        mime_type = match.group(1)
        base64_text = match.group(2)
    if not base64_text:
        raise ValueError("Missing image data")
    try:
        data = base64.b64decode(base64_text, validate=True)
    except binascii.Error as err:
        raise ValueError(f"Invalid base64 image data: {err}") from err
    if len(data) > MAX_ASSET_BYTES:
        raise ValueError(f"Image exceeds {MAX_ASSET_BYTES // (1024 * 1024)}MB")
    return data, mime_type


class ReviewServer:
    def __init__(self, target: Path, annotations: Path | None) -> None:
        self.target = target.resolve()
        self.root = self.target.parent if self.target.is_file() else self.target
        self.entry_name = self.target.name if self.target.is_file() else "index.html"
        self.annotation_path = find_annotation_path(self.root, annotations)
        self.annotation_path.parent.mkdir(parents=True, exist_ok=True)
        self.annotation_dir_name = self.annotation_path.parent.name
        self.asset_dir = self.annotation_path.parent / "assets"
        write_annotation_readme(self.annotation_path.parent)
        if not self.annotation_path.exists():
            data = load_inline_data(self.target, self.root, self.entry_name) or default_data(self.root, self.entry_name)
            self.write_data(data, action="init", annotation=None)

    def read_data(self) -> dict:
        return json.loads(self.annotation_path.read_text(encoding="utf-8"))

    def write_data(self, data: dict, action: str, annotation: dict | None) -> None:
        write_annotation_readme(self.annotation_path.parent)
        temp = self.annotation_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.annotation_path)
        self.refresh_inline_snapshots(data)
        self.refresh_reports(data)
        history = self.annotation_path.parent / "history.jsonl"
        event = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": action,
            "id": annotation.get("id") if annotation else None,
            "title": annotation.get("title") if annotation else None
        }
        with history.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def refresh_reports(self, data: dict) -> None:
        try:
            candidates_path = candidates_file_for(self.root)
            candidates = read_json(candidates_path) if candidates_path.exists() else None
            write_text(self.root / "annotation-report.md", render_report(data))
            write_text(self.root / "annotation-checklist.md", render_checklist(data, candidates))
        except Exception as err:
            print(f"WARNING: failed to refresh annotation report/checklist: {err}")

    def refresh_inline_snapshots(self, data: dict) -> None:
        html_files: list[Path]
        if self.target.is_file() and self.target.suffix.lower() == ".html":
            html_files = [self.target]
        else:
            html_files = [
                path for path in sorted(self.root.rglob("*.html"))
                if "node_modules" not in path.parts
                and ANNOTATION_DIR_NAME not in path.parts
                and LEGACY_ANNOTATION_DIR_NAME not in path.parts
            ]
        for html_file in html_files:
            html = html_file.read_text(encoding="utf-8", errors="ignore")
            if not INLINE_DATA_RE.search(html):
                continue
            page_key = page_key_for_html(html_file, self.root, data)
            next_html = replace_inline_data(html, snapshot_for_page(data, page_key))
            if next_html != html:
                html_file.write_text(next_html, encoding="utf-8")

    def resolve_request_path(self, request_path: str) -> Path | None:
        parsed = urlparse(request_path)
        path = unquote(parsed.path)
        if path == "/":
            return self.target if self.target.is_file() else self.root / "index.html"
        if self.target.is_file() and path == "/" + self.target.name:
            return self.target
        candidate = (self.root / path.lstrip("/")).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            return None
        return candidate

    def resolve_asset_request_path(self, request_path: str) -> Path | None:
        parsed = urlparse(request_path)
        path = unquote(parsed.path)
        asset_url_prefix = f"/{self.annotation_dir_name}/assets/"
        if not path.startswith(asset_url_prefix):
            return None
        rel = path[len(asset_url_prefix):].strip("/")
        if not rel:
            return None
        candidate = (self.asset_dir / rel).resolve()
        try:
            candidate.relative_to(self.asset_dir.resolve())
        except ValueError:
            return None
        return candidate

    def write_asset(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("Payload must be an object")
        data, mime_type = decode_asset_data(payload)
        file_name = str(payload.get("fileName") or "")
        ext = asset_extension(mime_type, file_name)
        annotation_id = sanitize_asset_stem(str(payload.get("annotationId") or ""))
        page_key = sanitize_asset_stem(str(payload.get("pageKey") or ""))
        source_stem = sanitize_asset_stem(file_name)
        prefix = "-".join(part for part in [page_key, annotation_id, source_stem] if part and part != "clipboard-image")
        if not prefix:
            prefix = "clipboard-image"
        timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        candidate = self.asset_dir / f"{prefix}-{timestamp}{ext}"
        index = 1
        while candidate.exists():
            candidate = self.asset_dir / f"{prefix}-{timestamp}-{index}{ext}"
            index += 1
        candidate.write_bytes(data)
        return {
            "ok": True,
            "src": f"/{self.annotation_dir_name}/assets/" + candidate.name,
            "fileName": candidate.name,
            "mimeType": (mime_type or mimetypes.guess_type(candidate.name)[0] or "application/octet-stream").split(";", 1)[0],
            "bytes": len(data),
        }


def make_handler(server_state: ReviewServer):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed_path = urlparse(self.path).path
            runtime_asset = RUNTIME_DIR / parsed_path.lstrip("/")
            if runtime_asset.exists() and runtime_asset.is_file():
                self.send_file(runtime_asset)
                return

            asset_path = server_state.resolve_asset_request_path(self.path)
            if asset_path and asset_path.exists() and asset_path.is_file():
                self.send_file(asset_path)
                return

            requested = server_state.resolve_request_path(self.path)
            if not requested or not requested.exists() or not requested.is_file():
                self.send_error(404)
                return

            if requested.suffix.lower() == ".html":
                html = requested.read_text(encoding="utf-8", errors="ignore")
                html = inject_html(html, server_state.read_data())
                self.send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
                return

            self.send_file(requested)

        def do_PUT(self) -> None:
            if urlparse(self.path).path != "/.prototype-annotator/api/annotations":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length)
            try:
                payload = json.loads(body.decode("utf-8"))
                data = payload["data"]
            except (json.JSONDecodeError, KeyError) as err:
                self.send_error(400, str(err))
                return

            server_state.write_data(data, payload.get("action", "save"), payload.get("annotation"))
            self.send_bytes(b'{"ok": true}', "application/json; charset=utf-8")

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/.prototype-annotator/api/assets":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                self.send_error(400, "Missing request body")
                return
            if length > MAX_ASSET_BYTES * 2:
                self.send_error(413, "Image payload is too large")
                return
            body = self.rfile.read(length)
            try:
                payload = json.loads(body.decode("utf-8"))
                result = server_state.write_asset(payload)
            except (json.JSONDecodeError, ValueError) as err:
                self.send_error(400, str(err))
                return
            self.send_bytes(json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def send_file(self, path: Path) -> None:
            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            self.send_bytes(path.read_bytes(), content_type)

        def send_bytes(self, data: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt: str, *args) -> None:
            print("%s - %s" % (self.address_string(), fmt % args))

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve a prototype annotation review page.")
    parser.add_argument("prototype_path", help="HTML file or static directory")
    parser.add_argument("--annotations", help="Path to annotations.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    target = Path(args.prototype_path).resolve()
    if not target.exists():
        parser.error(f"Path does not exist: {target}")
    annotation_path = Path(args.annotations).resolve() if args.annotations else None
    state = ReviewServer(target, annotation_path)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    url = f"http://{args.host}:{args.port}/"
    print(f"Serving annotation review at {url}")
    print(f"Annotations: {state.annotation_path}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
