#!/usr/bin/env python3
"""Move static Prototype Annotator runtime files into prototype-annotator/runtime."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_RUNTIME_DIR = SKILL_DIR / "templates" / "runtime"
ANNOTATION_DIR_NAME = "prototype-annotator"
LEGACY_ANNOTATION_DIR_NAME = ".prototype-annotations"
RUNTIME_SUBDIR = "runtime"
RUNTIME_FILES = [
    "prototype-annotator.css",
    "markdown-renderer.js",
    "mermaid-loader.js",
    "prototype-annotator.js",
]
RUNTIME_START = "<!-- Prototype Annotator runtime -->"


def asset_prefix_for(html_file: Path, root: Path) -> str:
    rel_depth = len(html_file.relative_to(root).parents) - 1
    return "./" if rel_depth <= 0 else "../" * rel_depth


def runtime_prefix_for(html_file: Path, root: Path) -> str:
    return f"{asset_prefix_for(html_file, root)}{ANNOTATION_DIR_NAME}/{RUNTIME_SUBDIR}/"


def annotation_data_url_for(html_file: Path, root: Path) -> str:
    return f"{asset_prefix_for(html_file, root)}{ANNOTATION_DIR_NAME}/annotations.json"


def runtime_config_script(data_url: str) -> str:
    encoded_url = json.dumps(data_url, ensure_ascii=False)
    return (
        "<script>\n"
        "window.PROTOTYPE_ANNOTATOR_CONFIG = Object.assign({}, "
        f"window.PROTOTYPE_ANNOTATOR_CONFIG || {{}}, {{ dataUrl: {encoded_url} }});\n"
        "</script>"
    )


def ensure_data_url_config(html: str, data_url: str) -> str:
    if "PROTOTYPE_ANNOTATOR_CONFIG" in html or RUNTIME_START not in html:
        return html
    return html.replace(RUNTIME_START, RUNTIME_START + "\n" + runtime_config_script(data_url), 1)


def update_html_references(html_file: Path, root: Path) -> bool:
    original = html_file.read_text(encoding="utf-8", errors="ignore")
    updated = original
    runtime_prefix = runtime_prefix_for(html_file, root)
    legacy_prefix = asset_prefix_for(html_file, root)
    for name in RUNTIME_FILES:
        updated = updated.replace(f'href="{legacy_prefix}{name}"', f'href="{runtime_prefix}{name}"')
        updated = updated.replace(f"href='{legacy_prefix}{name}'", f"href='{runtime_prefix}{name}'")
        updated = updated.replace(f'src="{legacy_prefix}{name}"', f'src="{runtime_prefix}{name}"')
        updated = updated.replace(f"src='{legacy_prefix}{name}'", f"src='{runtime_prefix}{name}'")
        updated = updated.replace(f'href="./{name}"', f'href="{runtime_prefix}{name}"')
        updated = updated.replace(f"href='./{name}'", f"href='{runtime_prefix}{name}'")
        updated = updated.replace(f'src="./{name}"', f'src="{runtime_prefix}{name}"')
        updated = updated.replace(f"src='./{name}'", f"src='{runtime_prefix}{name}'")
    updated = ensure_data_url_config(updated, annotation_data_url_for(html_file, root))
    if updated == original:
        return False
    html_file.write_text(updated, encoding="utf-8")
    return True


def refresh_runtime_assets(runtime_dir: Path) -> list[Path]:
    refreshed: list[Path] = []
    for name in RUNTIME_FILES:
        source = TEMPLATE_RUNTIME_DIR / name
        if source.exists():
            target = runtime_dir / name
            shutil.copy2(source, target)
            refreshed.append(target)
    return refreshed


def organize(root: Path, remove_root_assets: bool, refresh_runtime: bool) -> tuple[list[Path], list[Path], list[Path]]:
    root = root.resolve()
    runtime_dir = root / ANNOTATION_DIR_NAME / RUNTIME_SUBDIR
    runtime_dir.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []
    for name in RUNTIME_FILES:
        source = root / name
        if source.exists():
            target = runtime_dir / name
            if remove_root_assets:
                shutil.move(str(source), str(target))
            else:
                shutil.copy2(source, target)
            moved.append(target)
    changed_html: list[Path] = []
    for html_file in root.rglob("*.html"):
        if ANNOTATION_DIR_NAME in html_file.parts or LEGACY_ANNOTATION_DIR_NAME in html_file.parts:
            continue
        if update_html_references(html_file, root):
            changed_html.append(html_file)
    refreshed = refresh_runtime_assets(runtime_dir) if refresh_runtime else []
    return moved, changed_html, refreshed


def main() -> int:
    parser = argparse.ArgumentParser(description="Organize Prototype Annotator runtime files into prototype-annotator/runtime.")
    parser.add_argument("prototype_dir", help="Annotated static prototype directory")
    parser.add_argument("--keep-root-assets", action="store_true", help="Copy runtime files instead of moving them from the root")
    parser.add_argument("--no-refresh-runtime", action="store_true", help="Do not refresh runtime assets from the current skill templates")
    args = parser.parse_args()

    root = Path(args.prototype_dir)
    if not root.exists() or not root.is_dir():
        parser.error(f"Directory does not exist: {root}")

    moved, changed_html, refreshed = organize(
        root,
        remove_root_assets=not args.keep_root_assets,
        refresh_runtime=not args.no_refresh_runtime,
    )
    print(f"Runtime files organized: {len(moved)}")
    print(f"Runtime files refreshed: {len(refreshed)}")
    print(f"HTML files updated: {len(changed_html)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
