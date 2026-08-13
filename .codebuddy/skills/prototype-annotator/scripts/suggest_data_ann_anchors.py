#!/usr/bin/env python3
"""Suggest stable data-ann anchors for fragile annotation selectors."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ANNOTATION_DIR_NAME = "prototype-annotator"
LEGACY_ANNOTATION_DIR_NAME = ".prototype-annotations"
FRAGILE_STRATEGIES = {"path", "text", "handler", ""}
STABLE_STRATEGIES = {"id", "data", "aria", "name", "href", "placeholder", "role", "tag"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def annotation_root(target: Path) -> Path:
    return target.parent if target.is_file() else target


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise SystemExit(f"Invalid JSON in {path}: {err}") from err


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def default_annotations(root: Path) -> Path:
    preferred = root / ANNOTATION_DIR_NAME / "annotations.json"
    if preferred.exists():
        return preferred
    legacy = root / LEGACY_ANNOTATION_DIR_NAME / "annotations.json"
    return legacy if legacy.exists() else preferred


def default_candidates(root: Path) -> Path:
    preferred = root / ANNOTATION_DIR_NAME / "annotation-candidates.json"
    if preferred.exists():
        return preferred
    legacy = root / LEGACY_ANNOTATION_DIR_NAME / "annotation-candidates.json"
    return legacy if legacy.exists() else preferred


def default_page_map(root: Path) -> Path:
    preferred = root / ANNOTATION_DIR_NAME / "page-map.json"
    if preferred.exists():
        return preferred
    legacy = root / LEGACY_ANNOTATION_DIR_NAME / "page-map.json"
    return legacy if legacy.exists() else preferred


def default_output(root: Path) -> Path:
    return root / ANNOTATION_DIR_NAME / "data-ann-plan.json"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def slugify(value: str, fallback: str) -> str:
    text = normalize_text(value) or fallback
    ascii_parts = re.findall(r"[A-Za-z0-9]+", text)
    if ascii_parts:
        slug = "-".join(part.lower() for part in ascii_parts[:5])
    else:
        slug = fallback
    slug = re.sub(r"-+", "-", slug).strip("-").lower()
    return slug or fallback


def unique_slug(base: str, used: set[str]) -> str:
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}-{index}"
        index += 1
    used.add(candidate)
    return candidate


def selector_is_fragile(selector: str, strategy: str, selector_quality: dict | None) -> bool:
    if strategy in STABLE_STRATEGIES and not selector_quality:
        return False
    if strategy in FRAGILE_STRATEGIES:
        return True
    if selector_quality and selector_quality.get("level") in {"fragile", "missing"}:
        return True
    return bool(re.search(r":nth-of-type|(?:^|>)\s*(?:div|span)(?:\s|>|:|$)", selector or ""))


def pages_by_key(data: dict) -> dict[str, dict]:
    return {
        str(page.get("pageKey")): page
        for page in data.get("pages", [])
        if page.get("pageKey")
    }


def source_file_for(root: Path, page: dict) -> str | None:
    raw_path = page.get("path") or ""
    if not raw_path:
        return None
    path = (root / raw_path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    if path.exists() and path.is_file():
        return str(path)
    return None


def candidate_entries(candidates: dict) -> list[dict]:
    entries: list[dict] = []
    for page in candidates.get("pages", []):
        for candidate in page.get("candidates", []):
            if candidate.get("selected"):
                entries.append(candidate)
    return entries


def annotation_entries(annotations: dict) -> list[dict]:
    entries: list[dict] = []
    for ann in annotations.get("annotations", []):
        target = ann.get("target") if isinstance(ann.get("target"), dict) else {}
        entries.append(
            {
                "candidateId": ann.get("candidateId"),
                "annotationId": ann.get("id"),
                "pageKey": ann.get("pageKey"),
                "elementId": target.get("sourceElementId"),
                "selector": target.get("selector") or ann.get("selector") or "",
                "strategy": target.get("strategy") or "",
                "fallbackText": target.get("fallbackText") or ann.get("title") or "",
                "tag": (target.get("boundsHint") or {}).get("tag") if isinstance(target.get("boundsHint"), dict) else "",
                "kind": ann.get("kind"),
                "dimension": ann.get("dimension"),
                "priority": ann.get("priority"),
                "selectorQuality": ann.get("selectorQuality") if isinstance(ann.get("selectorQuality"), dict) else None,
                "reason": ann.get("title") or "",
                "source": "annotations.json",
            }
        )
    return entries


def page_map_elements(page_map: dict) -> dict[tuple[str, str], dict]:
    elements: dict[tuple[str, str], dict] = {}
    for page in page_map.get("pages", []):
        page_key = str(page.get("pageKey") or "")
        for element in page.get("elements", []):
            element_id = str(element.get("elementId") or "")
            if page_key and element_id:
                elements[(page_key, element_id)] = element
    return elements


def build_plan(root: Path, annotations: dict, candidates: dict | None, page_map: dict | None, include_stable: bool) -> dict:
    pages = pages_by_key(annotations)
    if page_map:
        pages.update(pages_by_key(page_map))
    elements = page_map_elements(page_map or {})
    used_slugs: set[str] = set()
    seen_targets: set[tuple[str, str, str]] = set()
    suggestions: list[dict] = []

    entries = annotation_entries(annotations)
    if candidates:
        entries.extend(candidate_entries(candidates))

    for entry in entries:
        page_key = str(entry.get("pageKey") or "")
        selector = str(entry.get("selector") or "")
        strategy = str(entry.get("strategy") or "")
        selector_quality = entry.get("selectorQuality") if isinstance(entry.get("selectorQuality"), dict) else None
        target_key = (page_key, str(entry.get("elementId") or ""), selector)
        if target_key in seen_targets:
            continue
        seen_targets.add(target_key)
        fragile = selector_is_fragile(selector, strategy, selector_quality)
        if not fragile and not include_stable:
            continue

        element = elements.get((page_key, str(entry.get("elementId") or "")), {})
        tag = entry.get("tag") or element.get("tag") or ""
        fallback = normalize_text(str(entry.get("fallbackText") or element.get("text") or entry.get("reason") or "anchor"))
        prefix = {
            "button": "action",
            "a": "link",
            "input": "field",
            "select": "field",
            "textarea": "field",
            "form": "form",
            "table": "table",
            "section": "section",
            "h1": "heading",
            "h2": "heading",
        }.get(str(tag), "anchor")
        element_id = str(entry.get("elementId") or "").lower().replace(":", "-")
        fallback_slug = f"{prefix}-{element_id}" if element_id else f"{prefix}-{page_key.lower()}-anchor"
        suggested = unique_slug(slugify(fallback, fallback_slug), used_slugs)
        page = pages.get(page_key, {})
        suggestions.append(
            {
                "pageKey": page_key,
                "pagePath": page.get("path") or entry.get("pagePath") or "",
                "pageRoute": page.get("route") or entry.get("pageRoute") or "",
                "annotationId": entry.get("annotationId"),
                "candidateId": entry.get("candidateId"),
                "elementId": entry.get("elementId"),
                "selector": selector,
                "strategy": strategy,
                "selectorQuality": selector_quality or {"level": "fragile" if fragile else "stable", "issues": []},
                "fallbackText": fallback,
                "tag": tag,
                "sourceFile": source_file_for(root, page),
                "suggestedDataAnn": suggested,
                "replacementSelector": f'[data-ann="{suggested}"]',
                "reason": "当前锚点依赖结构路径或缺少稳定属性，建议补充 data-ann。" if fragile else "当前锚点已较稳定，本条仅因 include-stable 输出。",
                "applyStatus": "manual-review-required",
            }
        )

    return {
        "version": 1,
        "generatedAt": now_iso(),
        "root": str(root),
        "summary": {
            "suggestionCount": len(suggestions),
            "requiresManualSourcePatch": True,
            "note": "This plan is advisory. Review sourceFile and suggestedDataAnn before editing application source.",
        },
        "suggestions": suggestions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest data-ann anchors for fragile Prototype Annotator selectors.")
    parser.add_argument("prototype_path", help="HTML file, static directory, or frontend project root")
    parser.add_argument("--annotations", help="Path to annotations.json")
    parser.add_argument("--candidates", help="Path to annotation-candidates.json")
    parser.add_argument("--page-map", help="Path to page-map.json")
    parser.add_argument("--out", help="Output data-ann-plan.json path")
    parser.add_argument("--include-stable", action="store_true", help="Also include already-stable selectors for review")
    args = parser.parse_args()

    target = Path(args.prototype_path).resolve()
    if not target.exists():
        parser.error(f"Path does not exist: {target}")
    root = annotation_root(target)
    annotations_path = Path(args.annotations).resolve() if args.annotations else default_annotations(root)
    if not annotations_path.exists():
        parser.error(f"Annotation file does not exist: {annotations_path}")
    candidates_path = Path(args.candidates).resolve() if args.candidates else default_candidates(root)
    page_map_path = Path(args.page_map).resolve() if args.page_map else default_page_map(root)
    candidates = read_json(candidates_path) if candidates_path.exists() else None
    page_map = read_json(page_map_path) if page_map_path.exists() else None
    output = Path(args.out).resolve() if args.out else default_output(root)
    payload = build_plan(root, read_json(annotations_path), candidates, page_map, args.include_stable)
    write_json(output, payload)
    print(f"Wrote data-ann anchor plan: {output}")
    print(f"Suggestions: {len(payload.get('suggestions', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
