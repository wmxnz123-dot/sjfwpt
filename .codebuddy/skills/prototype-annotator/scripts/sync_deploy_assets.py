#!/usr/bin/env python3
"""Sync Prototype Annotator assets into Vite/public deploy locations."""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path


ANNOTATION_DIR_NAME = "prototype-annotator"
LEGACY_ANNOTATION_DIR_NAME = ".prototype-annotations"
RUNTIME_PUBLIC_SUBDIR = "prototype-annotator"


@dataclass
class SyncReport:
    copied: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.stale

    def as_dict(self) -> dict[str, list[str] | bool]:
        return {
            "ok": self.ok,
            "copied": self.copied,
            "missing": self.missing,
            "stale": self.stale,
            "pruned": self.pruned,
            "checked": self.checked,
        }


def copy_file(source: Path, dest: Path, *, check: bool, report: SyncReport) -> None:
    if not source.exists():
        report.missing.append(str(source))
        return
    if check:
        report.checked.append(str(dest))
        if not dest.exists():
            report.missing.append(str(dest))
        elif not filecmp.cmp(source, dest, shallow=False):
            report.stale.append(str(dest))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    report.copied.append(str(dest))


def rewrite_asset_urls(text: str) -> str:
    return (
        text
        .replace("/.prototype-annotations/assets/", "/prototype-annotator/assets/")
        .replace("./.prototype-annotations/assets/", "./prototype-annotator/assets/")
        .replace(".prototype-annotations/assets/", "prototype-annotator/assets/")
    )


def copy_annotations_json(source: Path, dest: Path, *, check: bool, report: SyncReport) -> None:
    if not source.exists():
        report.missing.append(str(source))
        return
    text = rewrite_asset_urls(source.read_text(encoding="utf-8"))
    if check:
        report.checked.append(str(dest))
        if not dest.exists():
            report.missing.append(str(dest))
            return
        if dest.read_text(encoding="utf-8") != text:
            report.stale.append(str(dest))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    report.copied.append(str(dest))


def copy_tree(source: Path, dest: Path, *, check: bool, prune: bool, report: SyncReport) -> None:
    if not source.exists():
        report.missing.append(str(source))
        return
    if not source.is_dir():
        report.missing.append(f"{source} is not a directory")
        return
    for source_file in sorted(path for path in source.rglob("*") if path.is_file()):
        rel = source_file.relative_to(source)
        copy_file(source_file, dest / rel, check=check, report=report)

    if not prune or check or not dest.exists():
        return

    source_rel = {path.relative_to(source) for path in source.rglob("*") if path.is_file()}
    for dest_file in sorted(path for path in dest.rglob("*") if path.is_file()):
        rel = dest_file.relative_to(dest)
        if rel in source_rel:
            continue
        dest_file.unlink()
        report.pruned.append(str(dest_file))


def sync_deploy_assets(
    project_root: Path,
    *,
    public_dir: str,
    check: bool,
    prune: bool,
    include_runtime: bool,
) -> SyncReport:
    report = SyncReport()
    annotation_dir = project_root / ANNOTATION_DIR_NAME
    canonical_annotation_dir = annotation_dir
    if not (annotation_dir / "annotations.json").exists():
        legacy_dir = project_root / LEGACY_ANNOTATION_DIR_NAME
        if (legacy_dir / "annotations.json").exists():
            annotation_dir = legacy_dir
    public_root = project_root / public_dir
    public_annotations = public_root / ANNOTATION_DIR_NAME
    runtime_public = public_root / RUNTIME_PUBLIC_SUBDIR

    assets_dir = annotation_dir / "assets"
    if annotation_dir != canonical_annotation_dir:
        if assets_dir.exists():
            copy_tree(
                assets_dir,
                canonical_annotation_dir / "assets",
                check=check,
                prune=prune,
                report=report,
            )
        copy_annotations_json(
            annotation_dir / "annotations.json",
            canonical_annotation_dir / "annotations.json",
            check=check,
            report=report,
        )
    else:
        copy_annotations_json(
            annotation_dir / "annotations.json",
            canonical_annotation_dir / "annotations.json",
            check=check,
            report=report,
        )

    if assets_dir.exists():
        copy_tree(
            assets_dir,
            public_annotations / "assets",
            check=check,
            prune=prune,
            report=report,
        )
    copy_annotations_json(
        annotation_dir / "annotations.json",
        public_annotations / "annotations.json",
        check=check,
        report=report,
    )

    if runtime_public.exists() or not check:
        copy_annotations_json(
            annotation_dir / "annotations.json",
            runtime_public / "annotations.json",
            check=check,
            report=report,
        )

    if include_runtime:
        copy_tree(
            annotation_dir / "runtime",
            public_annotations / "runtime",
            check=check,
            prune=prune,
            report=report,
        )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Prototype Annotator deploy assets into public/prototype-annotator.")
    parser.add_argument("project_root", help="Frontend project root")
    parser.add_argument("--public-dir", default="public", help="Vite public directory. Defaults to public.")
    parser.add_argument("--check", action="store_true", help="Check deploy assets without writing files.")
    parser.add_argument("--prune", action="store_true", help="Remove stale files from public asset directories while syncing.")
    parser.add_argument("--include-runtime", action="store_true", help="Also sync prototype-annotator/runtime into public/prototype-annotator/runtime.")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Print a JSON report.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.exists():
        parser.error(f"Project root does not exist: {project_root}")

    report = sync_deploy_assets(
        project_root,
        public_dir=args.public_dir,
        check=args.check,
        prune=args.prune,
        include_runtime=args.include_runtime,
    )

    if args.json_output:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        action = "Checked" if args.check else "Synced"
        print(f"{action} Prototype Annotator deploy assets.")
        for key, values in report.as_dict().items():
            if key == "ok" or not values:
                continue
            print(f"{key}:")
            for value in values:
                print(f"  - {value}")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
