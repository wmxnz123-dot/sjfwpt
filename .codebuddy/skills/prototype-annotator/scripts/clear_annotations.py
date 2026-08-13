#!/usr/bin/env python3
"""Clear Prototype Annotator results without breaking the prototype."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from inject_annotations import ANNOTATION_DIR_NAME, LEGACY_ANNOTATION_DIR_NAME, RUNTIME_SUBDIR, strip_existing_runtime


def annotation_root(target: Path) -> Path:
    return target.parent if target.is_file() else target


def html_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if target.suffix.lower() == ".html" else []
    return [
        path
        for path in sorted(target.rglob("*.html"))
        if "node_modules" not in path.parts
        and ANNOTATION_DIR_NAME not in path.parts
        and LEGACY_ANNOTATION_DIR_NAME not in path.parts
        and not any(part.startswith(".") for part in path.relative_to(target).parts)
    ]


def remove_file(path: Path) -> bool:
    if not path.exists():
        return False
    path.unlink()
    return True


def remove_dir(path: Path) -> bool:
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True


def strip_runtime_blocks(paths: list[Path]) -> list[Path]:
    changed: list[Path] = []
    for path in paths:
        html = path.read_text(encoding="utf-8", errors="ignore")
        stripped = strip_existing_runtime(html)
        if stripped != html:
            path.write_text(stripped, encoding="utf-8")
            changed.append(path)
    return changed


def prune_empty_annotation_dir(annotation_dir: Path) -> bool:
    if not annotation_dir.exists():
        return False
    try:
        next(annotation_dir.iterdir())
    except StopIteration:
        annotation_dir.rmdir()
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove Prototype Annotator visible results while keeping the prototype runnable."
    )
    parser.add_argument("prototype_path", help="HTML file, static directory, or frontend project root")
    parser.add_argument(
        "--purge-cache",
        action="store_true",
        help="Also remove page-map, candidates, data-ann plan, and README from annotation directories.",
    )
    args = parser.parse_args()

    target = Path(args.prototype_path).resolve()
    if not target.exists():
        parser.error(f"Path does not exist: {target}")

    root = annotation_root(target)
    annotation_dirs = [root / ANNOTATION_DIR_NAME, root / LEGACY_ANNOTATION_DIR_NAME]
    public_dir = root / "public" / "prototype-annotator"

    removed: list[Path] = []
    for annotation_dir in annotation_dirs:
        for path in [
            annotation_dir / "annotations.json",
            annotation_dir / "history.jsonl",
        ]:
            if remove_file(path):
                removed.append(path)

    for annotation_dir in annotation_dirs:
        path = annotation_dir / RUNTIME_SUBDIR
        if remove_dir(path):
            removed.append(path)
    if remove_dir(public_dir):
        removed.append(public_dir)

    if args.purge_cache:
        for annotation_dir in annotation_dirs:
            for name in ["page-map.json", "annotation-candidates.json", "data-ann-plan.json", "README.md"]:
                path = annotation_dir / name
                if remove_file(path):
                    removed.append(path)
            if prune_empty_annotation_dir(annotation_dir):
                removed.append(annotation_dir)

    stripped = strip_runtime_blocks(html_files(target))

    print(f"Cleared Prototype Annotator data under: {root}")
    if removed:
        print("Removed generated files:")
        for path in removed:
            print(f"  {path}")
    if stripped:
        print("Removed static HTML runtime blocks:")
        for path in stripped:
            print(f"  {path}")
    if not removed and not stripped:
        print("No Prototype Annotator result files or static runtime blocks were found.")
    print("Framework adapter source files were left in place so existing imports do not break builds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
