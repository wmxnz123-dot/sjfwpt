#!/usr/bin/env python3
"""Run the Prototype Annotator smoke workflow against bundled examples."""

from __future__ import annotations

import argparse
import http.client
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse


SKILL_DIR = Path(__file__).resolve().parents[1]
EXAMPLE_INPUT = SKILL_DIR / "examples" / "expense-reimbursement-demo" / "input"
SURFACE_DEMO_INPUT = SKILL_DIR / "examples" / "surface-demo" / "input"
SURFACE_DEMO_EXPECTED = SKILL_DIR / "examples" / "surface-demo" / "expected-output"
SURFACE_RUNTIME_MARKERS = (
    "isSurfaceOpen",
    "contextAnnotations",
    "groupAnnotationsForSidebar",
    "inferSurfaceForTarget",
    "surfaceSharesOpenSelector",
    "displayWhenClosed",
)


def assert_schema_type_consistency() -> None:
    annotation_types = json.loads((SKILL_DIR / "references" / "annotation-types.json").read_text(encoding="utf-8"))
    annotations_schema = json.loads((SKILL_DIR / "schemas" / "annotations.schema.json").read_text(encoding="utf-8"))
    expected = annotation_types.get("annotationTypes") or []
    actual = annotations_schema.get("$defs", {}).get("annotationType", {}).get("enum") or []
    if expected != actual:
        raise SystemExit("schemas/annotations.schema.json annotationType enum is out of sync with references/annotation-types.json")


def run_command(args: list[str], *, cwd: Path = SKILL_DIR, expect_success: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if expect_success and result.returncode != 0:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(f"Command failed: {' '.join(args)}")
    if not expect_success and result.returncode == 0:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(f"Command unexpectedly passed: {' '.join(args)}")
    return result


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_request(method: str, url: str, body: bytes | None = None, content_type: str | None = None) -> tuple[int, bytes]:
    parsed = urlparse(url)
    conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port or 80, timeout=5)
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    conn.request(method, parsed.path or "/", body=body, headers=headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


def wait_for_server(url: str, process: subprocess.Popen, timeout_seconds: float = 8.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise SystemExit(
                "Review server exited early.\n"
                f"stdout:\n{stdout}\n"
                f"stderr:\n{stderr}"
            )
        try:
            status, _ = http_request("GET", url)
            if status == 200:
                return
        except OSError:
            time.sleep(0.15)
    raise SystemExit(f"Review server did not start: {url}")


def playwright_available() -> bool:
    script = (
        "try { require('playwright'); process.exit(0); } "
        "catch (e) { try { require('playwright-core'); process.exit(0); } "
        "catch (e2) { process.exit(1); } }"
    )
    result = subprocess.run(["node", "-e", script], cwd=SKILL_DIR, text=True, capture_output=True)
    return result.returncode == 0


def should_run_browser_smoke(name: str, *, require_browser: bool = False) -> bool:
    if playwright_available():
        return True
    if require_browser:
        raise SystemExit(f"{name} requires playwright or playwright-core, but neither is installed.")
    print(f"{name} skipped: playwright/playwright-core is not installed.")
    return False


def assert_script_json_escaping(work_dir: Path) -> None:
    case_dir = work_dir / "script-json-escaping"
    prototype = case_dir / "prototype"
    annotation_dir = prototype / "prototype-annotator"
    prototype.mkdir(parents=True)
    annotation_dir.mkdir(parents=True)
    (prototype / "index.html").write_text(
        "<!doctype html><html><body><button id=\"danger-target\">保存</button></body></html>\n",
        encoding="utf-8",
    )
    dangerous_content = "### 业务含义\n\n</script><script>window.__pa_escape_failed = true</script>"
    annotations = {
        "version": 1,
        "pages": [{"pageKey": "P01", "title": "Escape", "path": "index.html", "route": "/index.html"}],
        "annotations": [
            {
                "id": "ANN-P01-001",
                "pageKey": "P01",
                "annotationType": "A",
                "target": {"selector": "#danger-target", "fallbackText": "保存", "strategy": "id"},
                "title": "危险正文",
                "contentMarkdown": dangerous_content,
                "kind": "interaction",
                "dimension": "Primary action",
                "visible": True,
            }
        ],
    }
    (annotation_dir / "annotations.json").write_text(json.dumps(annotations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output = work_dir / "script-json-escaping-output"
    run_command([sys.executable, "scripts/inject_annotations.py", str(prototype), "--output", str(output), "--force"])
    html = (output / "index.html").read_text(encoding="utf-8")
    if dangerous_content in html or "</script><script>window.__pa_escape_failed" in html:
        raise SystemExit("Injected HTML contains unescaped script-breaking annotation content")
    if "\\u003c/script\\u003e" not in html:
        raise SystemExit("Injected HTML did not escape </script> inside annotation JSON")


def run_optional_browser_edit_smoke(url: str, work_dir: Path, annotation_path: Path, *, require_browser: bool = False) -> None:
    if not should_run_browser_smoke("Browser edit smoke", require_browser=require_browser):
        return
    script_path = work_dir / "browser-edit-smoke.mjs"
    script_path.write_text(
        """
const url = process.argv[2];
let playwright;
try {
  playwright = await import("playwright");
} catch (error) {
  playwright = await import("playwright-core");
}
const browser = await playwright.chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  page.on("dialog", async (dialog) => dialog.dismiss());
  await page.goto(url, { waitUntil: "networkidle" });
  await page.click('[data-pa-action="toggle-edit"]');
  await page.click("#browser-target");
  await page.fill('input[name="title"]', "Browser smoke annotation");
  await page.fill('textarea[name="contentMarkdown"]', "### 业务含义\\n\\n浏览器回写冒烟测试。");
  await page.click('button[type="submit"]');
  await page.waitForFunction(() => document.body.innerText.includes("标注已保存"), null, { timeout: 5000 });
} finally {
  await browser.close();
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    run_command(["node", str(script_path), url])
    data = load_json(annotation_path)
    if not any(ann.get("title") == "Browser smoke annotation" for ann in data.get("annotations", [])):
        raise SystemExit("Browser edit smoke did not persist the new annotation")


def run_optional_sidebar_scroll_smoke(work_dir: Path, *, require_browser: bool = False) -> None:
    if not should_run_browser_smoke("Sidebar scroll smoke", require_browser=require_browser):
        return

    case_dir = work_dir / "sidebar-scroll"
    prototype = case_dir / "prototype"
    annotation_dir = prototype / "prototype-annotator"
    prototype.mkdir(parents=True)
    annotation_dir.mkdir(parents=True)

    annotation_count = 18
    target_buttons = [
        f'<button id="scroll-target-{index:02d}">Scroll target {index:02d}</button>'
        for index in range(1, annotation_count + 1)
    ]
    (prototype / "index.html").write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html><head><title>Sidebar Scroll Smoke</title></head>",
                "<body>",
                "<main>",
                *target_buttons,
                "</main>",
                "</body></html>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    data = {
        "version": 1,
        "pages": [{"pageKey": "P01", "title": "Sidebar Scroll Smoke", "path": "index.html", "route": "/index.html"}],
        "annotations": [
            {
                "id": f"ANN-P01-{index:03d}",
                "pageKey": "P01",
                "annotationType": "P" if index == 1 else "A",
                "target": {"selector": f"#scroll-target-{index:02d}", "strategy": "id"},
                "title": f"Sidebar item {index:02d}",
                "contentMarkdown": f"### Test note\n\nGeneric sidebar scroll smoke annotation {index:02d}.",
                "kind": "note" if index == 1 else "interaction",
                "visible": True,
                "order": index,
            }
            for index in range(1, annotation_count + 1)
        ],
    }
    (annotation_dir / "annotations.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    port = find_free_port()
    url = f"http://127.0.0.1:{port}/"
    process = subprocess.Popen(
        [
            sys.executable,
            str(SKILL_DIR / "scripts" / "serve_annotation_review.py"),
            str(prototype),
            "--port",
            str(port),
        ],
        cwd=SKILL_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_for_server(url, process)
        script_path = work_dir / "sidebar-scroll-smoke.mjs"
        script_path.write_text(
            """
const url = process.argv[2];
const expectedCount = Number(process.argv[3]);
let playwright;
try {
  playwright = await import("playwright");
} catch (error) {
  playwright = await import("playwright-core");
}
const browser = await playwright.chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 480 } });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.click('[data-pa-action="sidebar"]');
  await page.waitForSelector(".pa-sidebar-list", { state: "visible", timeout: 5000 });
  const initial = await page.evaluate((count) => {
    const list = document.querySelector(".pa-sidebar-list");
    const items = Array.from(document.querySelectorAll(".pa-sidebar-item"));
    const last = items[items.length - 1];
    if (!list || !last) return { missing: true };
    const listRect = list.getBoundingClientRect();
    const lastRect = last.getBoundingClientRect();
    return {
      itemCount: items.length,
      maxScroll: list.scrollHeight - list.clientHeight,
      lastText: last.innerText,
      fullyVisible: lastRect.top >= listRect.top && lastRect.bottom <= listRect.bottom,
      expectedLastTitle: `Sidebar item ${String(count).padStart(2, "0")}`,
    };
  }, expectedCount);
  if (initial.missing) throw new Error("Sidebar list or final item was not rendered");
  if (initial.itemCount !== expectedCount) {
    throw new Error(`Expected ${expectedCount} sidebar items, found ${initial.itemCount}`);
  }
  if (initial.maxScroll <= 0) {
    throw new Error(`Sidebar list did not require scrolling; maxScroll=${initial.maxScroll}`);
  }
  if (!initial.lastText.includes(initial.expectedLastTitle)) {
    throw new Error(`Final sidebar item text did not include ${initial.expectedLastTitle}: ${initial.lastText}`);
  }
  if (initial.fullyVisible) {
    throw new Error("Final sidebar item should start below the visible list area in the constrained viewport");
  }
  const headerBox = await page.locator(".pa-sidebar-header").boundingBox();
  if (!headerBox) throw new Error("Sidebar header was not rendered");
  await page.mouse.move(headerBox.x + 80, headerBox.y + headerBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(headerBox.x + 80, 430, { steps: 12 });
  await page.mouse.up();
  const afterDrag = await page.evaluate(() => {
    const sidebar = document.querySelector(".pa-sidebar");
    const list = document.querySelector(".pa-sidebar-list");
    const items = Array.from(document.querySelectorAll(".pa-sidebar-item"));
    if (!sidebar || !list || !items.length) return { missing: true };
    const sidebarRect = sidebar.getBoundingClientRect();
    const listRect = list.getBoundingClientRect();
    return {
      sidebarTop: sidebarRect.top,
      sidebarBottom: sidebarRect.bottom,
      listHeight: listRect.height,
      maxScroll: list.scrollHeight - list.clientHeight,
      itemCount: items.length,
    };
  });
  if (afterDrag.missing) throw new Error("Sidebar list disappeared after dragging");
  if (afterDrag.listHeight < 120) {
    throw new Error(`Sidebar list collapsed after dragging; listHeight=${afterDrag.listHeight}`);
  }
  if (afterDrag.maxScroll <= 0) {
    throw new Error(`Sidebar list stopped scrolling after dragging; maxScroll=${afterDrag.maxScroll}`);
  }
  if (afterDrag.sidebarBottom > 481) {
    throw new Error(`Sidebar exceeded viewport after dragging; bottom=${afterDrag.sidebarBottom}`);
  }
  const after = await page.evaluate(() => {
    const list = document.querySelector(".pa-sidebar-list");
    const items = Array.from(document.querySelectorAll(".pa-sidebar-item"));
    const last = items[items.length - 1];
    list.scrollTop = list.scrollHeight;
    const listRect = list.getBoundingClientRect();
    const lastRect = last.getBoundingClientRect();
    return {
      scrollTop: list.scrollTop,
      maxScroll: list.scrollHeight - list.clientHeight,
      lastText: last.innerText,
      fullyVisible: lastRect.top >= listRect.top && lastRect.bottom <= listRect.bottom,
    };
  });
  if (after.scrollTop < after.maxScroll - 1) {
    throw new Error(`Sidebar did not scroll to the bottom; scrollTop=${after.scrollTop}, maxScroll=${after.maxScroll}`);
  }
  if (!after.fullyVisible) {
    throw new Error(`Final sidebar item is clipped after scrolling: ${after.lastText}`);
  }
} finally {
  await browser.close();
}
""".strip()
            + "\n",
            encoding="utf-8",
        )
        run_command(["node", str(script_path), url, str(annotation_count)])
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_optional_surface_context_smoke(work_dir: Path, *, require_browser: bool = False) -> None:
    if not should_run_browser_smoke("Surface context smoke", require_browser=require_browser):
        return

    case_dir = work_dir / "surface-context"
    prototype = case_dir / "prototype"
    annotation_dir = prototype / "prototype-annotator"
    runtime_dir = annotation_dir / "runtime"
    prototype.mkdir(parents=True)
    annotation_dir.mkdir(parents=True)
    runtime_dir.mkdir(parents=True)
    shutil.copyfile(SKILL_DIR / "templates" / "runtime" / "prototype-annotator.js", runtime_dir / "prototype-annotator.js")
    shutil.copyfile(SKILL_DIR / "templates" / "runtime" / "prototype-annotator.css", runtime_dir / "prototype-annotator.css")
    shutil.copyfile(SKILL_DIR / "templates" / "runtime" / "markdown-renderer.js", runtime_dir / "markdown-renderer.js")
    shutil.copyfile(SKILL_DIR / "templates" / "runtime" / "mermaid-loader.js", runtime_dir / "mermaid-loader.js")
    (prototype / "index.html").write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html data-page-key=\"P01\"><head><title>Surface Context Smoke</title>",
                "<style>",
                ".drawer-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.25)}",
                ".drawer-overlay.open{display:block}",
                ".drawer{position:absolute;right:0;top:0;bottom:0;width:420px;background:#fff;padding:24px}",
                "</style>",
                "<script>window.PROTOTYPE_ANNOTATOR_CONFIG={dataUrl:'./prototype-annotator/annotations.json'};</script>",
                "<link rel=\"stylesheet\" href=\"./prototype-annotator/runtime/prototype-annotator.css\">",
                "</head><body>",
                "<main><h1 id=\"page-title\">记录列表</h1><button id=\"btn-new-plan\" type=\"button\">新建记录</button></main>",
                "<div class=\"drawer-overlay\" id=\"drawer-plan-form\"><section class=\"drawer\"><h2>新建记录</h2><button aria-label=\"关闭\" type=\"button\">×</button><label>关联对象<select id=\"plan-project\"><option>示例对象</option></select></label><button id=\"btn-save-plan\" type=\"button\">保存</button></section></div>",
                "<script>document.getElementById('btn-new-plan').addEventListener('click',()=>document.getElementById('drawer-plan-form').classList.add('open'));</script>",
                "<script src=\"./prototype-annotator/runtime/markdown-renderer.js\"></script>",
                "<script src=\"./prototype-annotator/runtime/mermaid-loader.js\"></script>",
                "<script src=\"./prototype-annotator/runtime/prototype-annotator.js\"></script>",
                "</body></html>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    data = {
        "version": 1,
        "pages": [{"pageKey": "P01", "title": "Surface Context Smoke", "path": "index.html", "route": "/"}],
        "surfaces": [
            {
                "id": "surface-P01-drawer-plan-form",
                "type": "drawer",
                "name": "新建记录",
                "pageKey": "P01",
                "triggerSelector": "#btn-new-plan",
                "openSelector": "#drawer-plan-form",
                "containerSelector": "#drawer-plan-form",
                "titleText": "新建记录",
            }
        ],
        "annotations": [
            {
                "id": "ANN-P01-001",
                "pageKey": "P01",
                "annotationType": "P",
                "target": {"selector": "#page-title", "strategy": "id"},
                "title": "页面介绍",
                "contentMarkdown": "### 页面功能介绍\n\n页面标注。\n\n### 核心内容\n\n页面内容。\n\n### 业务流程\n\n打开抽屉。\n\n### 主要操作\n\n新建记录。\n\n### 待确认\n\n无。",
                "kind": "overview",
                "visible": True,
                "order": 1,
            },
            {
                "id": "ANN-P01-002",
                "pageKey": "P01",
                "surfaceId": "surface-P01-drawer-plan-form",
                "displayWhenClosed": "sidebar-only",
                "annotationType": "A",
                "target": {"selector": "#plan-project", "strategy": "id"},
                "title": "关联对象",
                "contentMarkdown": "### 业务含义\n\n选择关联对象。\n\n### 交互规则\n\n打开抽屉后选择对象。\n\n### 状态与异常\n\n未选择时不可保存。\n\n### 待确认\n\n无。",
                "kind": "form",
                "visible": True,
                "order": 2,
            },
        ],
    }
    (annotation_dir / "annotations.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    port = find_free_port()
    url = f"http://127.0.0.1:{port}/"
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=prototype,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_for_server(url, process)
        script_path = work_dir / "surface-context-smoke.mjs"
        script_path.write_text(
            """
const url = process.argv[2];
let playwright;
try {
  playwright = await import("playwright");
} catch (error) {
  playwright = await import("playwright-core");
}
const browser = await playwright.chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.click("#btn-new-plan");
  await page.waitForFunction(() => document.querySelector(".pa-badge")?.textContent === "1", null, { timeout: 5000 });
  await page.click('[data-pa-action="sidebar"]');
  await page.waitForSelector(".pa-sidebar-list", { state: "visible", timeout: 5000 });
  const result = await page.evaluate(() => ({
    badges: Array.from(document.querySelectorAll(".pa-badge")).map((node) => node.textContent),
    headers: Array.from(document.querySelectorAll(".pa-sidebar-group-header")).map((node) => node.innerText),
    items: Array.from(document.querySelectorAll(".pa-sidebar-item")).map((node) => node.innerText),
  }));
  if (result.badges.join(",") !== "1") {
    throw new Error(`Expected only the drawer badge after opening surface; got ${result.badges.join(",")}`);
  }
  if (!result.headers.some((text) => text.includes("新建记录"))) {
    throw new Error(`Sidebar did not show readable drawer group: ${JSON.stringify(result.headers)}`);
  }
  if (result.items.length !== 1 || !result.items[0].includes("关联对象")) {
    throw new Error(`Sidebar did not switch to drawer annotations: ${JSON.stringify(result.items)}`);
  }
} finally {
  await browser.close();
}
""".strip()
            + "\n",
            encoding="utf-8",
        )
        run_command(["node", str(script_path), url])
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_review_server_write_smoke(work_dir: Path, *, require_browser: bool = False) -> None:
    case_dir = work_dir / "review-server-write"
    prototype = case_dir / "prototype"
    annotation_dir = prototype / "prototype-annotator"
    prototype.mkdir(parents=True)
    annotation_dir.mkdir(parents=True)
    (prototype / "index.html").write_text(
        "\n".join([
            "<!doctype html>",
            "<html><head><title>Review Smoke</title></head>",
            "<body>",
            "<main><button id=\"browser-target\">保存草稿</button></main>",
            "</body></html>",
        ])
        + "\n",
        encoding="utf-8",
    )
    data = {
        "version": 1,
        "pages": [{"pageKey": "P01", "title": "Review Smoke", "path": "index.html", "route": "/index.html"}],
        "annotations": [],
    }
    annotation_path = annotation_dir / "annotations.json"
    annotation_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    port = find_free_port()
    url = f"http://127.0.0.1:{port}/"
    process = subprocess.Popen(
        [
            sys.executable,
            str(SKILL_DIR / "scripts" / "serve_annotation_review.py"),
            str(prototype),
            "--port",
            str(port),
        ],
        cwd=SKILL_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_for_server(url, process)
        dangerous_content = "### 业务含义\n\n</script><script>window.__pa_review_escape_failed = true</script>"
        next_data = {
            **data,
            "annotations": [
                {
                    "id": "ANN-P01-001",
                    "pageKey": "P01",
                    "annotationType": "A",
                    "target": {"selector": "#browser-target", "fallbackText": "保存草稿", "strategy": "id"},
                    "title": "Review API write",
                    "contentMarkdown": dangerous_content,
                    "kind": "interaction",
                    "dimension": "Primary action",
                    "visible": True,
                }
            ],
        }
        payload = json.dumps({"action": "save", "annotation": next_data["annotations"][0], "data": next_data}, ensure_ascii=False).encode("utf-8")
        status, _ = http_request("PUT", url + ".prototype-annotator/api/annotations", payload, "application/json; charset=utf-8")
        if status != 200:
            raise SystemExit(f"Review server PUT failed with HTTP {status}")
        written = load_json(annotation_path)
        if written.get("annotations", [{}])[0].get("title") != "Review API write":
            raise SystemExit("Review server did not write annotations.json")
        history = annotation_dir / "history.jsonl"
        if not history.exists() or "Review API write" not in history.read_text(encoding="utf-8"):
            raise SystemExit("Review server did not append history.jsonl")
        _, html_bytes = http_request("GET", url)
        html = html_bytes.decode("utf-8")
        if dangerous_content in html or "</script><script>window.__pa_review_escape_failed" in html:
            raise SystemExit("Review server HTML contains unescaped script-breaking annotation content")
        if "\\u003c/script\\u003e" not in html:
            raise SystemExit("Review server HTML did not escape </script> inside annotation JSON")
        png_data_url = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        )
        asset_payload = json.dumps(
            {
                "fileName": "clipboard.png",
                "mimeType": "image/png",
                "dataUrl": png_data_url,
                "annotationId": "ANN-P01-001",
                "pageKey": "P01",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        status, asset_bytes = http_request(
            "POST",
            url + ".prototype-annotator/api/assets",
            asset_payload,
            "application/json; charset=utf-8",
        )
        if status != 200:
            raise SystemExit(f"Review server asset upload failed with HTTP {status}")
        asset_result = json.loads(asset_bytes.decode("utf-8"))
        asset_src = str(asset_result.get("src") or "")
        if not asset_src.startswith("/prototype-annotator/assets/"):
            raise SystemExit(f"Review server asset upload returned unexpected src: {asset_src}")
        asset_path = annotation_dir / "assets" / Path(asset_src).name
        if not asset_path.exists() or asset_path.stat().st_size == 0:
            raise SystemExit("Review server asset upload did not write an image file")
        status, served_asset = http_request("GET", url + asset_src.lstrip("/"))
        if status != 200 or served_asset != asset_path.read_bytes():
            raise SystemExit("Review server did not serve the uploaded asset")
        run_optional_browser_edit_smoke(url, work_dir, annotation_path, require_browser=require_browser)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_deploy_asset_sync_smoke(work_dir: Path) -> None:
    case_dir = work_dir / "deploy-asset-sync"
    prototype = case_dir / "prototype"
    annotation_dir = prototype / "prototype-annotator"
    asset_dir = annotation_dir / "assets"
    asset_dir.mkdir(parents=True)
    (prototype / "index.html").write_text(
        "\n".join([
            "<!doctype html>",
            "<html><head><title>Deploy Asset Smoke</title></head>",
            "<body><main id=\"app\">发布资产测试</main></body></html>",
        ])
        + "\n",
        encoding="utf-8",
    )
    (asset_dir / "demo.png").write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02"
        b"\x00\x00\x00\x0bIDATx\xdac\xfc\xff\x1f\x00\x03\x03\x02\x00\xef\xbf\xa7\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    data = {
        "version": 1,
        "pages": [{"pageKey": "P01", "title": "Deploy Asset Smoke", "path": "index.html", "route": "/index.html"}],
        "annotations": [
            {
                "id": "ANN-P01-001",
                "pageKey": "P01",
                "annotationType": "P",
                "target": {"selector": "#app", "fallbackText": "发布资产测试", "strategy": "id"},
                "title": "页面功能介绍",
                "contentMarkdown": (
                    "### 页面功能介绍\n\n发布资产测试。\n\n"
                    "### 核心内容\n\n![粘贴图片](/.prototype-annotations/assets/demo.png)\n\n"
                    "### 业务流程\n\n进入页面后查看标注。\n\n"
                    "### 主要操作\n\n查看页面说明。\n\n"
                    "### 待确认\n\n无。"
                ),
                "kind": "overview",
                "dimension": "Page overview",
                "visible": True,
            }
        ],
    }
    annotation_path = annotation_dir / "annotations.json"
    annotation_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    run_command([
        sys.executable,
        "scripts/validate_annotations.py",
        str(prototype),
        "--deploy-check",
    ], expect_success=False)
    run_command([sys.executable, "scripts/inject_annotations.py", str(prototype)])
    run_command([
        sys.executable,
        "scripts/validate_annotations.py",
        str(prototype),
        "--deploy-check",
    ])
    runtime_js = prototype / "prototype-annotator" / "runtime" / "prototype-annotator.js"
    runtime_js.unlink()
    run_command([
        sys.executable,
        "scripts/validate_annotations.py",
        str(prototype),
        "--deploy-check",
    ], expect_success=False)
    run_command([sys.executable, "scripts/inject_annotations.py", str(prototype)])
    run_command([
        sys.executable,
        "scripts/validate_annotations.py",
        str(prototype),
        "--deploy-check",
    ])
    public_required = [
        prototype / "prototype-annotator" / "annotations.json",
        prototype / "prototype-annotator" / "assets" / "demo.png",
        prototype / "prototype-annotator" / "runtime" / "prototype-annotator.js",
    ]
    public_missing = [path for path in public_required if not path.exists()]
    if public_missing:
        raise SystemExit("Deploy-safe runtime smoke missing output(s): " + ", ".join(str(path) for path in public_missing))
    html = (prototype / "index.html").read_text(encoding="utf-8")
    if "./prototype-annotator/runtime/prototype-annotator.js" not in html:
        raise SystemExit("Deploy-safe runtime smoke did not rewrite HTML runtime references")

    (prototype / "package.json").write_text(
        json.dumps({"devDependencies": {"vite": "latest"}}, indent=2) + "\n",
        encoding="utf-8",
    )
    run_command([
        sys.executable,
        "scripts/validate_annotations.py",
        str(prototype),
        "--deploy-check",
    ], expect_success=False)
    run_command([sys.executable, "scripts/sync_deploy_assets.py", str(prototype)])
    run_command([sys.executable, "scripts/sync_deploy_assets.py", str(prototype), "--check"])
    run_command([
        sys.executable,
        "scripts/validate_annotations.py",
        str(prototype),
        "--deploy-check",
    ])
    required = [
        prototype / "public" / "prototype-annotator" / "annotations.json",
        prototype / "public" / "prototype-annotator" / "assets" / "demo.png",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        raise SystemExit("Deploy asset sync smoke missing output(s): " + ", ".join(str(path) for path in missing))

    legacy_app = case_dir / "legacy-vite"
    legacy_ann_dir = legacy_app / ".prototype-annotations"
    legacy_asset_dir = legacy_ann_dir / "assets"
    legacy_asset_dir.mkdir(parents=True)
    (legacy_app / "package.json").write_text(
        json.dumps({"devDependencies": {"vite": "latest"}}, indent=2) + "\n",
        encoding="utf-8",
    )
    (legacy_asset_dir / "legacy.png").write_bytes((asset_dir / "demo.png").read_bytes())
    legacy_data = json.loads(json.dumps(data, ensure_ascii=False))
    legacy_data["annotations"][0]["contentMarkdown"] = legacy_data["annotations"][0]["contentMarkdown"].replace(
        "/.prototype-annotations/assets/demo.png",
        "/.prototype-annotations/assets/legacy.png",
    )
    (legacy_ann_dir / "annotations.json").write_text(json.dumps(legacy_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run_command([sys.executable, "scripts/sync_deploy_assets.py", str(legacy_app)])
    run_command([sys.executable, "scripts/sync_deploy_assets.py", str(legacy_app), "--check"])
    migrated_annotations = legacy_app / "prototype-annotator" / "annotations.json"
    public_migrated_annotations = legacy_app / "public" / "prototype-annotator" / "annotations.json"
    for migrated in [migrated_annotations, public_migrated_annotations]:
        text = migrated.read_text(encoding="utf-8")
        if ".prototype-annotations" in text or "/prototype-annotator/assets/legacy.png" not in text:
            raise SystemExit(f"Legacy deploy sync did not rewrite annotation asset URLs: {migrated}")
    for migrated_asset in [
        legacy_app / "prototype-annotator" / "assets" / "legacy.png",
        legacy_app / "public" / "prototype-annotator" / "assets" / "legacy.png",
    ]:
        if not migrated_asset.exists():
            raise SystemExit(f"Legacy deploy sync did not migrate asset: {migrated_asset}")


def finalize_annotation_for_delivery(annotation: dict) -> None:
    source = annotation.get("source")
    if isinstance(source, dict) and source.get("type") == "local-rule-draft":
        source["type"] = "ai-inference"
    if not annotation.get("evidence"):
        ref = source.get("ref") if isinstance(source, dict) else "smoke-test"
        annotation["evidence"] = [str(ref)]
    content = str(annotation.get("contentMarkdown") or "")
    if "待补：" in content:
        annotation["contentMarkdown"] = content.replace("待补：", "已确认：")
    if "根据原型结构推断" in content and "### 待确认" not in content:
        annotation["contentMarkdown"] = content.rstrip() + "\n\n### 待确认\n\n- 已由冒烟测试确认。\n"
    review = annotation.setdefault("review", {})
    if isinstance(review, dict):
        review["required"] = True
        review["status"] = "approved"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_surface_demo_annotations(data: dict) -> None:
    surfaces = data.get("surfaces") if isinstance(data.get("surfaces"), list) else []
    if len(surfaces) != 2:
        raise SystemExit(f"surface-demo: expected 2 surfaces, found {len(surfaces)}")

    surface_ids = {str(surface.get("id") or "") for surface in surfaces}
    expected_surface_ids = {
        "surface-P01-create-app-drawer",
        "surface-P01-delete-confirm-modal",
    }
    if surface_ids != expected_surface_ids:
        raise SystemExit(f"surface-demo: unexpected surface ids: {sorted(surface_ids)}")

    annotations = data.get("annotations") if isinstance(data.get("annotations"), list) else []
    if len(annotations) != 10:
        raise SystemExit(f"surface-demo: expected 10 annotations, found {len(annotations)}")

    for ann in annotations:
        selector = str((ann.get("target") or {}).get("selector") or ann.get("selector") or "").lower()
        if "success-toast" in selector:
            raise SystemExit(f"surface-demo: toast should not be an independent annotation ({ann.get('id')})")

    save_ann = next(
        (
            ann
            for ann in annotations
            if "save-app" in str((ann.get("target") or {}).get("selector") or ann.get("selector") or "")
        ),
        None,
    )
    if not save_ann:
        raise SystemExit("surface-demo: missing save-app action annotation")
    save_content = str(save_ann.get("contentMarkdown") or "")
    save_evidence = " ".join(str(item) for item in (save_ann.get("evidence") or []))
    if (
        "成功" not in save_content
        and "toast" not in save_content.lower()
        and "保存成功" not in save_evidence
    ):
        raise SystemExit("surface-demo: save-app annotation should document success toast feedback")

    for ann in annotations:
        if not ann.get("surfaceId"):
            continue
        if not ann.get("displayWhenClosed"):
            raise SystemExit(f"surface-demo: {ann.get('id')} is missing displayWhenClosed")

    drawer_sidebar_only = [
        ann
        for ann in annotations
        if ann.get("surfaceId") == "surface-P01-create-app-drawer"
        and ann.get("displayWhenClosed") == "sidebar-only"
    ]
    if len(drawer_sidebar_only) < 2:
        raise SystemExit("surface-demo: drawer should have at least two sidebar-only internal annotations")

    modal_sidebar_only = [
        ann
        for ann in annotations
        if ann.get("surfaceId") == "surface-P01-delete-confirm-modal"
        and ann.get("displayWhenClosed") == "sidebar-only"
    ]
    if len(modal_sidebar_only) < 2:
        raise SystemExit("surface-demo: confirm modal should have at least two sidebar-only internal annotations")

    drawer_overview = next(
        (
            ann
            for ann in annotations
            if ann.get("surfaceId") == "surface-P01-create-app-drawer"
            and ann.get("displayWhenClosed") == "on-trigger"
            and ann.get("dimension") in {"Surface overview", "Surface trigger"}
        ),
        None,
    )
    if not drawer_overview:
        raise SystemExit("surface-demo: missing drawer on-trigger overview/trigger annotation")


def assert_surface_runtime(runtime_js: Path) -> None:
    if not runtime_js.exists():
        raise SystemExit(f"surface-demo: missing runtime file {runtime_js}")
    content = runtime_js.read_text(encoding="utf-8")
    missing = [marker for marker in SURFACE_RUNTIME_MARKERS if marker not in content]
    if missing:
        raise SystemExit(f"surface-demo: runtime missing surface markers: {', '.join(missing)}")


def page_overview_content() -> str:
    return "\n\n".join(
        [
            "### 页面功能介绍\n\n用于完成核心业务任务。",
            "### 核心内容\n\n- 页面对象：核心业务对象。",
            "### 业务流程\n\n- 进入页面：查看对象。\n- 完成任务：执行操作。",
            "### 主要操作\n\n- 查看列表。\n- 提交处理。",
            "### 待确认\n\n- 是否需要补充角色差异？",
        ]
    )


def write_validation_fixture(root: Path, annotations: list[dict], surfaces: list[dict] | None = None) -> Path:
    prototype = root / "prototype"
    prototype.mkdir(parents=True, exist_ok=True)
    (prototype / "index.html").write_text(
        """<!doctype html><html><body><main id="main"><h1>测试页</h1><button id="a">入口 A</button><button id="b">入口 B</button><div id="drawer">抽屉</div></main></body></html>""",
        encoding="utf-8",
    )
    annotation_dir = prototype / "prototype-annotator"
    annotation_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "project": {"id": "validation-fixture", "name": "Validation Fixture", "source": "smoke-test"},
        "pages": [{"pageKey": "P01", "title": "测试页", "path": "index.html", "route": "/index.html"}],
        "annotations": annotations,
    }
    if surfaces is not None:
        data["surfaces"] = surfaces
    (annotation_dir / "annotations.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return prototype


def run_validation_regression_checks(work_dir: Path) -> None:
    good_page_ann = {
        "id": "ANN-P01-001",
        "pageKey": "P01",
        "target": {"selector": "#main", "fallbackText": "测试页", "strategy": "id"},
        "title": "测试页 · 页面介绍",
        "contentMarkdown": page_overview_content(),
        "annotationType": "P",
        "kind": "note",
        "dimension": "Page overview",
        "priority": "high",
        "visible": True,
        "source": {"type": "prototype", "ref": "smoke-test"},
    }

    bad_template = dict(good_page_ann)
    bad_template["contentMarkdown"] = "### 页面功能介绍\n\n缺少核心内容和业务流程。"
    bad_template_dir = write_validation_fixture(work_dir / "bad-page-template", [bad_template])
    run_command(
        [sys.executable, "scripts/validate_annotations.py", str(bad_template_dir), "--strict-quality"],
        expect_success=False,
    )

    bad_surface_dir = write_validation_fixture(
        work_dir / "bad-surface-merge",
        [
            good_page_ann,
            {
                "id": "ANN-P01-002",
                "pageKey": "P01",
                "surfaceId": "surface-P01-drawer",
                "displayWhenClosed": "on-trigger",
                "fallbackAnchorSelector": "#a, #b",
                "target": {"selector": "#drawer", "fallbackText": "抽屉", "strategy": "id"},
                "title": "合并抽屉",
                "contentMarkdown": "### 业务含义\n\n用于打开抽屉。\n\n### 交互规则\n\n点击入口后打开抽屉。\n\n### 状态与异常\n\n失败时保留当前页面。\n\n### 待确认\n\n- 是否应拆分为不同业务抽屉？",
                "annotationType": "A",
                "kind": "interaction",
                "dimension": "Surface trigger",
                "priority": "high",
                "visible": True,
            },
        ],
        [
            {
                "id": "surface-P01-drawer",
                "type": "drawer",
                "name": "合并抽屉",
                "pageKey": "P01",
                "triggerSelector": "#a, #b",
                "openSelector": "#drawer",
                "titleText": "抽屉",
            }
        ],
    )
    run_command(
        [sys.executable, "scripts/validate_annotations.py", str(bad_surface_dir), "--strict-quality"],
        expect_success=False,
    )

    bad_compound_title_dir = write_validation_fixture(
        work_dir / "bad-compound-surface-title",
        [good_page_ann],
        [
            {
                "id": "surface-P01-record-form",
                "type": "drawer",
                "name": "记录表单",
                "pageKey": "P01",
                "triggerSelector": "#a",
                "openSelector": "#drawer",
                "titleText": "新增/修改记录",
            }
        ],
    )
    run_command(
        [sys.executable, "scripts/validate_annotations.py", str(bad_compound_title_dir), "--strict-quality"],
        expect_success=False,
    )

    tech_content = dict(good_page_ann)
    tech_content["contentMarkdown"] = page_overview_content() + "\n\n### 实现说明\n\n点击后调用 `openDrawer()` 和 `API.createApp()`。"
    tech_content_dir = write_validation_fixture(work_dir / "bad-product-copy", [tech_content])
    run_command(
        [
            sys.executable,
            "scripts/validate_annotations.py",
            str(tech_content_dir),
            "--strict-quality",
            "--lint-language",
            "product-review",
        ],
        expect_success=False,
    )


def assert_surface_expected_outputs(output_dir: Path) -> None:
    required = [
        output_dir / "index.html",
        output_dir / "prototype-annotator" / "annotations.json",
        output_dir / "prototype-annotator" / "runtime" / "prototype-annotator.js",
        output_dir / "annotation-report.md",
        output_dir / "annotation-checklist.md",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        raise SystemExit("surface-demo smoke missing output(s): " + ", ".join(str(path) for path in missing))

    report_markers = (
        "#### 二级界面：新建应用",
        "#### 二级界面：确认删除",
        "- 未打开时展示：sidebar-only",
    )
    checklist_markers = (
        "二级界面数量：2",
        "每个二级界面至少有入口与概览标注",
    )

    report_actual = (output_dir / "annotation-report.md").read_text(encoding="utf-8")
    report_expected = (SURFACE_DEMO_EXPECTED / "annotation-report.md").read_text(encoding="utf-8")
    for marker in report_markers:
        if marker not in report_actual:
            raise SystemExit(f"surface-demo report missing marker: {marker}")
        if marker not in report_expected:
            raise SystemExit(f"surface-demo expected report missing marker: {marker}")

    checklist_actual = (output_dir / "annotation-checklist.md").read_text(encoding="utf-8")
    checklist_expected = (SURFACE_DEMO_EXPECTED / "annotation-checklist.md").read_text(encoding="utf-8")
    for marker in checklist_markers:
        if marker not in checklist_actual:
            raise SystemExit(f"surface-demo checklist missing marker: {marker}")
        if marker not in checklist_expected:
            raise SystemExit(f"surface-demo expected checklist missing marker: {marker}")


def run_surface_smoke(work_dir: Path) -> None:
    if not SURFACE_DEMO_INPUT.exists():
        raise SystemExit(f"Missing surface demo fixture: {SURFACE_DEMO_INPUT}")

    case_dir = work_dir / "surface-demo"
    shutil.copytree(SURFACE_DEMO_INPUT, case_dir)
    prototype = case_dir / "prototype"
    prd = case_dir / "PRD.md"
    annotations = prototype / "prototype-annotator" / "annotations.json"
    annotated_output = work_dir / "surface-annotated-output"

    run_command([sys.executable, "scripts/scan_prototype.py", str(prototype)])
    run_command([sys.executable, "scripts/build_annotation_candidates.py", str(prototype), "--docs", str(prd)])
    run_command([
        sys.executable,
        "scripts/generate_annotations_draft.py",
        str(prototype),
        "--replace-generated",
        "--audience",
        "product-review",
    ])
    run_command([sys.executable, "scripts/validate_annotations.py", str(prototype), "--strict-quality"])

    data = load_json(annotations)
    assert_surface_demo_annotations(data)

    run_command([sys.executable, "scripts/inject_annotations.py", str(prototype), "--output", str(annotated_output), "--force"])
    run_command([sys.executable, "scripts/render_annotation_report.py", str(annotated_output)])
    assert_surface_runtime(annotated_output / "prototype-annotator" / "runtime" / "prototype-annotator.js")
    assert_surface_expected_outputs(annotated_output)


def approve_generated_annotations(annotation_path: Path, *, enable_dev_handoff: bool = False) -> None:
    data = json.loads(annotation_path.read_text(encoding="utf-8"))
    if enable_dev_handoff:
        profile = data.setdefault("productProfile", {})
        if isinstance(profile, dict):
            profile["annotationMode"] = "dev-handoff"
    for annotation in data.get("annotations", []):
        finalize_annotation_for_delivery(annotation)
    annotation_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_smoke(work_dir: Path) -> None:
    if not EXAMPLE_INPUT.exists():
        raise SystemExit(f"Missing example fixture: {EXAMPLE_INPUT}")
    assert_schema_type_consistency()
    run_validation_regression_checks(work_dir)

    case_dir = work_dir / "expense-reimbursement-demo"
    shutil.copytree(EXAMPLE_INPUT, case_dir)
    prototype = case_dir / "prototype"
    prd = case_dir / "PRD.md"
    product_profile = case_dir / "product-profile.json"
    annotations = prototype / "prototype-annotator" / "annotations.json"
    annotated_output = work_dir / "annotated-output"

    run_command([sys.executable, "scripts/scan_prototype.py", str(prototype)])
    run_command([sys.executable, "scripts/build_annotation_candidates.py", str(prototype), "--docs", str(prd)])
    run_command([
        sys.executable,
        "scripts/generate_annotations_draft.py",
        str(prototype),
        "--product-profile",
        str(product_profile),
        "--replace-generated",
    ])
    run_command([sys.executable, "scripts/validate_annotations.py", str(prototype), "--strict-quality"])
    run_command(
        [
            sys.executable,
            "scripts/validate_annotations.py",
            str(prototype),
            "--strict-quality",
            "--fail-on-pending-review",
        ],
        expect_success=False,
    )

    approve_generated_annotations(annotations)
    run_command([
        sys.executable,
        "scripts/validate_annotations.py",
        str(prototype),
        "--strict-quality",
        "--fail-on-pending-review",
    ])
    approve_generated_annotations(annotations, enable_dev_handoff=True)
    run_command([
        sys.executable,
        "scripts/validate_annotations.py",
        str(prototype),
        "--strict-quality",
        "--dev-handoff",
        "--fail-on-pending-review",
    ])
    run_command([sys.executable, "scripts/audit_annotation_coverage.py", str(prototype)])
    run_command([sys.executable, "scripts/inject_annotations.py", str(prototype), "--output", str(annotated_output), "--force"])
    run_command([sys.executable, "scripts/render_annotation_report.py", str(annotated_output)])

    required_outputs = [
        annotated_output / "index.html",
        annotated_output / "prototype-annotator" / "annotations.json",
        annotated_output / "prototype-annotator" / "runtime" / "prototype-annotator.js",
        annotated_output / "annotation-report.md",
        annotated_output / "annotation-checklist.md",
    ]
    missing = [path for path in required_outputs if not path.exists()]
    if missing:
        raise SystemExit("Smoke test missing output(s): " + ", ".join(str(path) for path in missing))


def run_all_smoke(work_dir: Path, *, require_browser: bool = False) -> None:
    assert_script_json_escaping(work_dir)
    run_optional_sidebar_scroll_smoke(work_dir, require_browser=require_browser)
    run_optional_surface_context_smoke(work_dir, require_browser=require_browser)
    run_review_server_write_smoke(work_dir, require_browser=require_browser)
    run_deploy_asset_sync_smoke(work_dir)
    run_smoke(work_dir)
    run_surface_smoke(work_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Prototype Annotator smoke workflow.")
    parser.add_argument("--work-dir", help="Optional work directory. Defaults to a temporary directory.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the generated temporary directory for inspection.")
    parser.add_argument("--require-browser", action="store_true", help="Fail when playwright/playwright-core is unavailable for browser smoke tests.")
    args = parser.parse_args()

    if args.work_dir:
        work_dir = Path(args.work_dir).resolve()
        if work_dir.exists() and any(work_dir.iterdir()):
            raise SystemExit(f"Work directory must be empty: {work_dir}")
        work_dir.mkdir(parents=True, exist_ok=True)
        run_all_smoke(work_dir, require_browser=args.require_browser)
        print(f"Smoke test passed. Work dir: {work_dir}")
        return 0

    with tempfile.TemporaryDirectory(prefix="prototype-annotator-smoke-") as tmp:
        work_dir = Path(tmp)
        run_all_smoke(work_dir, require_browser=args.require_browser)
        if args.keep_temp:
            kept_dir = Path(tempfile.mkdtemp(prefix="prototype-annotator-smoke-kept-"))
            shutil.copytree(work_dir, kept_dir, dirs_exist_ok=True)
            print(f"Smoke test passed. Kept work dir: {kept_dir}")
        else:
            print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
