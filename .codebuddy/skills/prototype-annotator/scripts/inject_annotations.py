#!/usr/bin/env python3
"""Inject Prototype Annotator runtime into HTML files."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = SKILL_DIR / "templates" / "runtime"
ANNOTATION_DIR_NAME = "prototype-annotator"
LEGACY_ANNOTATION_DIR_NAME = ".prototype-annotations"
RUNTIME_SUBDIR = "runtime"
PUBLIC_RUNTIME_DIR_NAME = "prototype-annotator"
RUNTIME_FILES = [
    "prototype-annotator.css",
    "markdown-renderer.js",
    "mermaid-loader.js",
    "prototype-annotator.js",
]
ANNOTATION_README = """# 原型标注说明

本目录由 `prototype-annotator` skill 生成，用于保存原型页面的标注数据和运行时资源。

## 目录说明

- `annotations.json`：标注数据源。AI 生成和页面内手动编辑后的标注最终都应写入这里。
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


def should_ignore_dir_copy(directory: str, names: list[str]) -> set[str]:
    ignored = {ANNOTATION_DIR_NAME, LEGACY_ANNOTATION_DIR_NAME, "node_modules"}
    for name in names:
        if name.startswith("."):
            ignored.add(name)
        if name.endswith("-annotated.html"):
            ignored.add(name)
    return ignored


def annotation_file_for(target: Path, annotation_dir_name: str = ANNOTATION_DIR_NAME) -> Path:
    root = target.parent if target.is_file() else target
    preferred = root / annotation_dir_name / "annotations.json"
    if preferred.exists():
        return preferred
    legacy = root / LEGACY_ANNOTATION_DIR_NAME / "annotations.json"
    if legacy.exists():
        return legacy
    return preferred


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def write_annotation_readme(annotation_dir: Path) -> None:
    readme = annotation_dir / "README.md"
    if not readme.exists():
        readme.write_text(ANNOTATION_README, encoding="utf-8")
        return
    current = readme.read_text(encoding="utf-8", errors="ignore")
    if current.startswith(LEGACY_README_PREFIX):
        readme.write_text(ANNOTATION_README, encoding="utf-8")


def find_existing_annotation_dir(root: Path, annotation_dir_name: str) -> Path | None:
    for name in (annotation_dir_name, LEGACY_ANNOTATION_DIR_NAME):
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def find_existing_annotation_file_dir(root: Path, annotation_dir_name: str, file_name: str) -> Path | None:
    for name in (annotation_dir_name, LEGACY_ANNOTATION_DIR_NAME):
        candidate = root / name
        if (candidate / file_name).exists():
            return candidate
    return None


def write_annotation_workspace(root: Path, data: dict, source_root: Path | None = None, annotation_dir_name: str = ANNOTATION_DIR_NAME) -> Path:
    annotation_dir = root / annotation_dir_name
    annotation_dir.mkdir(parents=True, exist_ok=True)
    public_data = rewrite_asset_urls(data, annotation_dir_name)
    write_json(annotation_dir / "annotations.json", public_data)
    if source_root:
        source_dir = find_existing_annotation_file_dir(source_root, annotation_dir_name, "page-map.json") or source_root / annotation_dir_name
        source_page_map = source_dir / "page-map.json"
        target_page_map = annotation_dir / "page-map.json"
        if source_page_map.exists() and source_page_map.resolve() != target_page_map.resolve():
            shutil.copy2(source_page_map, target_page_map)
        asset_source_dir = find_existing_annotation_file_dir(source_root, annotation_dir_name, "assets") or source_dir
        if (asset_source_dir / "assets").resolve() != (annotation_dir / "assets").resolve():
            copy_assets(asset_source_dir / "assets", annotation_dir / "assets")
    write_annotation_readme(annotation_dir)
    return annotation_dir / "annotations.json"


def load_annotations(target: Path, annotation_path: Path | None, annotation_dir_name: str = ANNOTATION_DIR_NAME) -> dict:
    path = annotation_path or annotation_file_for(target, annotation_dir_name)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    page_path = target.name if target.is_file() else "index.html"
    return {
        "version": 1,
        "project": {"id": "prototype", "name": target.stem if target.is_file() else target.name, "source": "generated"},
        "pages": [{"pageKey": "P01", "title": "Prototype", "path": page_path, "route": "/" + page_path}],
        "annotations": []
    }


def runtime_asset_prefix(asset_prefix: str = "./", annotation_dir_name: str = ANNOTATION_DIR_NAME) -> str:
    return f"{asset_prefix}{annotation_dir_name.strip('/')}/{RUNTIME_SUBDIR}/"


def annotation_data_url(asset_prefix: str = "./", annotation_dir_name: str = ANNOTATION_DIR_NAME) -> str:
    return f"{asset_prefix}{annotation_dir_name.strip('/')}/annotations.json"


def public_runtime_prefix(asset_prefix: str = "./", public_runtime_dir: str = PUBLIC_RUNTIME_DIR_NAME) -> str:
    return f"{asset_prefix}{public_runtime_dir.strip('/')}/"


def public_annotation_data_url(asset_prefix: str = "./", public_runtime_dir: str = PUBLIC_RUNTIME_DIR_NAME) -> str:
    return f"{public_runtime_prefix(asset_prefix, public_runtime_dir)}annotations.json"


def runtime_config_script(asset_prefix: str = "./", annotation_dir_name: str = ANNOTATION_DIR_NAME) -> str:
    data_url_value = annotation_data_url(asset_prefix, annotation_dir_name)
    data_url = json.dumps(data_url_value, ensure_ascii=False)
    return (
        "<script>\n"
        "window.PROTOTYPE_ANNOTATOR_CONFIG = Object.assign({}, "
        f"window.PROTOTYPE_ANNOTATOR_CONFIG || {{}}, {{ dataUrl: {data_url} }});\n"
        "</script>"
    )


def page_key_for_html(html_path: Path, root_dir: Path, data: dict) -> str | None:
    rel = str(html_path.relative_to(root_dir))
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


def json_for_script(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def rewrite_asset_urls(data: dict, annotation_dir_name: str = ANNOTATION_DIR_NAME) -> dict:
    public_dir = annotation_dir_name.strip("/")
    rewritten = copy.deepcopy(data)

    def rewrite_text(value: str) -> str:
        return (
            value
            .replace("/.prototype-annotations/assets/", f"/{public_dir}/assets/")
            .replace("./.prototype-annotations/assets/", f"./{public_dir}/assets/")
            .replace(".prototype-annotations/assets/", f"{public_dir}/assets/")
            .replace("/prototype-annotator/assets/", f"/{public_dir}/assets/")
            .replace("./prototype-annotator/assets/", f"./{public_dir}/assets/")
            .replace("prototype-annotator/assets/", f"{public_dir}/assets/")
        )

    annotations = rewritten.get("annotations") if isinstance(rewritten, dict) else []
    for ann in annotations if isinstance(annotations, list) else []:
        if not isinstance(ann, dict):
            continue
        for field in ("contentMarkdown", "devNotesMarkdown"):
            if isinstance(ann.get(field), str):
                ann[field] = rewrite_text(ann[field])
        assets = ann.get("assets")
        for asset in assets if isinstance(assets, list) else []:
            if isinstance(asset, dict) and isinstance(asset.get("src"), str):
                asset["src"] = rewrite_text(asset["src"])
    return rewritten


def runtime_markup(data: dict, asset_prefix: str = "./", annotation_dir_name: str = ANNOTATION_DIR_NAME) -> str:
    embed_data = rewrite_asset_urls(data, annotation_dir_name)
    json_text = json_for_script(embed_data)
    runtime_prefix = runtime_asset_prefix(asset_prefix, annotation_dir_name)
    return "\n".join([
        "<!-- Prototype Annotator runtime -->",
        runtime_config_script(asset_prefix, annotation_dir_name),
        f'<link rel="stylesheet" href="{runtime_prefix}prototype-annotator.css">',
        '<script id="prototype-annotations-data" type="application/json">',
        json_text,
        "</script>",
        f'<script src="{runtime_prefix}markdown-renderer.js"></script>',
        f'<script src="{runtime_prefix}mermaid-loader.js"></script>',
        f'<script src="{runtime_prefix}prototype-annotator.js"></script>',
        "<!-- /Prototype Annotator runtime -->",
    ])


def strip_existing_runtime(html: str) -> str:
    start = "<!-- Prototype Annotator runtime -->"
    end = "<!-- /Prototype Annotator runtime -->"
    while start in html and end in html:
        before, rest = html.split(start, 1)
        _, after = rest.split(end, 1)
        html = before + after
    return html


def inject_html(
    path: Path,
    data: dict,
    asset_prefix: str = "./",
    *,
    page_key: str | None = None,
    annotation_dir_name: str = ANNOTATION_DIR_NAME,
) -> None:
    html = path.read_text(encoding="utf-8", errors="ignore")
    html = strip_existing_runtime(html)
    embed_data = snapshot_for_page(data, page_key) if page_key else data
    markup = runtime_markup(embed_data, asset_prefix, annotation_dir_name)
    if "</body>" in html:
        html = html.replace("</body>", markup + "\n</body>", 1)
    else:
        html = html + "\n" + markup + "\n"
    path.write_text(html, encoding="utf-8")


def copy_runtime(dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_FILES:
        shutil.copy2(RUNTIME_DIR / name, dest_dir / name)


def copy_assets(source_assets: Path, dest_assets: Path) -> None:
    if not source_assets.exists():
        return
    if dest_assets.exists():
        shutil.rmtree(dest_assets)
    shutil.copytree(source_assets, dest_assets)


def inject_file(source: Path, output: Path, data: dict, annotation_dir_name: str = ANNOTATION_DIR_NAME) -> None:
    if source.resolve() != output.resolve():
        shutil.copy2(source, output)
    write_annotation_workspace(output.parent, data, source.parent, annotation_dir_name)
    copy_runtime(output.parent / annotation_dir_name / RUNTIME_SUBDIR)
    page_key = page_key_for_html(output, output.parent, data)
    inject_html(output, data, "./", page_key=page_key, annotation_dir_name=annotation_dir_name)


def inject_directory(source: Path, output: Path, data: dict, force: bool, annotation_dir_name: str = ANNOTATION_DIR_NAME) -> None:
    in_place = source.resolve() == output.resolve()
    if not in_place and output.exists() and not force:
        raise SystemExit(f"Output directory already exists: {output}. Use --force to overwrite files in it.")
    if not in_place:
        shutil.copytree(source, output, dirs_exist_ok=force, ignore=should_ignore_dir_copy)
    write_annotation_workspace(output, data, source, annotation_dir_name)
    copy_runtime(output / annotation_dir_name / RUNTIME_SUBDIR)
    for html_file in output.rglob("*.html"):
        if "node_modules" in html_file.parts:
            continue
        if annotation_dir_name in html_file.parts or LEGACY_ANNOTATION_DIR_NAME in html_file.parts:
            continue
        rel_depth = len(html_file.relative_to(output).parents) - 1
        prefix = "./" if rel_depth <= 0 else "../" * rel_depth
        page_key = page_key_for_html(html_file, output, data)
        inject_html(html_file, data, prefix, page_key=page_key, annotation_dir_name=annotation_dir_name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject Prototype Annotator runtime into HTML prototypes.")
    parser.add_argument("prototype_path", help="HTML file or static directory")
    parser.add_argument("--annotations", help="Path to annotations.json")
    parser.add_argument("--output", help="Optional output file or directory. Defaults to in-place injection.")
    parser.add_argument("--force", action="store_true", help="Allow writing into an existing --output directory")
    parser.add_argument(
        "--annotation-dir",
        default=ANNOTATION_DIR_NAME,
        help="Annotation workspace and static runtime directory. Defaults to prototype-annotator.",
    )
    parser.add_argument(
        "--public-runtime-dir",
        help="Deprecated alias for --annotation-dir.",
    )
    args = parser.parse_args()

    source = Path(args.prototype_path).resolve()
    if not source.exists():
        parser.error(f"Path does not exist: {source}")
    annotation_path = Path(args.annotations).resolve() if args.annotations else None
    annotation_dir_name = (args.public_runtime_dir or args.annotation_dir).strip("/")
    data = load_annotations(source, annotation_path, annotation_dir_name)

    if source.is_file():
        output = Path(args.output).resolve() if args.output else source
        inject_file(source, output, data, annotation_dir_name)
        print(f"Updated HTML with Prototype Annotator runtime: {output}")
        print(f"Annotations: {output.parent / annotation_dir_name / 'annotations.json'}")
    else:
        output = Path(args.output).resolve() if args.output else source
        inject_directory(source, output, data, args.force, annotation_dir_name)
        print(f"Updated directory with Prototype Annotator runtime: {output}")
        print(f"Annotations: {output / annotation_dir_name / 'annotations.json'}")
    if args.public_runtime_dir:
        root = output.parent if output.is_file() else output
        print(f"Deprecated --public-runtime-dir used as annotation dir: {root / annotation_dir_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
