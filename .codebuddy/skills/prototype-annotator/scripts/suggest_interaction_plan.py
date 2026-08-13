#!/usr/bin/env python3
"""Suggest interaction-plan entries for SPA surface components."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SURFACE_COMPONENTS = {
    "Sheet": "drawer",
    "Drawer": "drawer",
    "Dialog": "modal",
    "AlertDialog": "confirm",
    "Popover": "popover",
    "DropdownMenu": "dropdown",
}


def iter_source_files(root: Path) -> list[Path]:
    src = root / "src"
    if not src.exists():
        src = root
    return sorted(
        path for path in src.rglob("*")
        if path.suffix in {".tsx", ".jsx", ".vue"}
        and "node_modules" not in path.parts
        and "dist" not in path.parts
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "surface"


def route_hint_for_file(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    route_match = re.search(r'path=["\']([^"\']+)["\']', text)
    if route_match:
        return route_match.group(1)
    return None


def component_names(text: str) -> set[str]:
    names: set[str] = set()
    for name in SURFACE_COMPONENTS:
        if re.search(rf"<{name}\b", text):
            names.add(name)
    return names


def find_nearby_titles(text: str, component: str) -> list[str]:
    titles: list[str] = []
    for match in re.finditer(rf"<{component}\b[\s\S]*?</{component}>", text):
        block = match.group(0)
        title_match = re.search(r"<(?:SheetTitle|DialogTitle|AlertDialogTitle)[^>]*>([\s\S]*?)</", block)
        if title_match:
            title = re.sub(r"<[^>]+>", "", title_match.group(1))
            title = re.sub(r"\s+", " ", title).strip()
            if title:
                titles.append(title[:40])
    return titles


def suggest(root: Path) -> dict:
    suggestions: list[dict] = []
    page_counter = 1
    for path in iter_source_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        names = component_names(text)
        if not names:
            continue
        route_hint = route_hint_for_file(path)
        page_key = f"P{page_counter:02d}"
        page_counter += 1
        for name in sorted(names):
            titles = find_nearby_titles(text, name) or [name]
            for index, title in enumerate(titles, start=1):
                surface_type = SURFACE_COMPONENTS[name]
                surface_slug = slugify(f"{path.stem}-{title}-{index}")
                suggestions.append({
                    "name": f"打开{title}",
                    "pageRoute": route_hint,
                    "triggerSelector": "TODO: add stable selector for the button that opens this surface",
                    "triggerAction": "click",
                    "waitForSelector": "[role='dialog'], [role='alertdialog'], [data-radix-popper-content-wrapper]",
                    "surfaceId": f"surface-{page_key}-{surface_slug}",
                    "surfaceName": title,
                    "surfaceType": surface_type,
                    "contentSelector": "[role='dialog'], [role='alertdialog'], [data-radix-popper-content-wrapper]",
                    "textIncludes": [title] if title != name else [],
                    "sourceFile": str(path.relative_to(root)),
                    "status": "needs-trigger-selector",
                })
    return {
        "version": 1,
        "generatedBy": "suggest_interaction_plan.py",
        "interactions": suggestions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest interaction-plan entries for Sheet/Dialog/Popover/Dropdown surfaces.")
    parser.add_argument("project_root")
    parser.add_argument("--out", help="Output path. Defaults to prototype-annotator/interaction-plan.suggestions.json")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    if not root.exists():
        parser.error(f"Path does not exist: {root}")
    out = Path(args.out).resolve() if args.out else root / "prototype-annotator" / "interaction-plan.suggestions.json"
    payload = suggest(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(payload['interactions'])} suggestion(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
