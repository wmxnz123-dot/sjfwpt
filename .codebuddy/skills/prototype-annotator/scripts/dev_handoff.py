"""Shared dev-handoff delivery checks for prototype annotations."""

from __future__ import annotations

import json
import re
from pathlib import Path

COARSE_SELECTORS = {"main", "h1", "h2", "h3", "body"}
PLACEHOLDER_MARKERS = [
    "最终说明应补充",
    "需结合 PRD、上游页面级需求说明文档或人工评审补全",
    "需结合 PRD、上游页面级需求说明文档",
    "本条由本地规则草稿生成",
    "待补：",
]
FORM_HEAVY_DIMENSIONS = {
    "Form and validation",
    "Table and list",
    "Primary action",
    "Permission and risk",
    "State and exception",
    "Flow and navigation",
    "AI and automation",
}
READ_ONLY_DIMENSIONS = {"Data explanation", "Context"}


def candidates_file_for(target: Path) -> Path:
    root = target.parent if target.is_file() else target
    preferred = root / "prototype-annotator" / "annotation-candidates.json"
    if preferred.exists():
        return preferred
    legacy = root / ".prototype-annotations" / "annotation-candidates.json"
    return legacy if legacy.exists() else preferred


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def annotation_mode(data: dict) -> str:
    profile = data.get("productProfile") if isinstance(data.get("productProfile"), dict) else {}
    return str(profile.get("annotationMode") or "standard").strip().lower()


def is_dev_handoff_mode(data: dict, explicit: bool = False) -> bool:
    if explicit:
        return True
    return annotation_mode(data) == "dev-handoff"


def is_page_overview(ann: dict) -> bool:
    return (
        ann.get("dimension") == "Page overview"
        or ann.get("annotationType") == "P"
        or "页面介绍" in str(ann.get("title") or "")
        or "页面功能介绍" in str(ann.get("title") or "")
    )


def normalize_key(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip().lower()


def target_keys(ann: dict) -> set[str]:
    target = ann.get("target") if isinstance(ann.get("target"), dict) else {}
    keys: set[str] = set()
    page_key = str(ann.get("pageKey") or "")
    source_element_id = str(target.get("sourceElementId") or "").strip()
    selector = str(target.get("selector") or ann.get("selector") or "").strip()
    fallback = normalize_key(str(target.get("fallbackText") or ""))
    if page_key and source_element_id:
        keys.add(f"{page_key}|element:{source_element_id}")
    if page_key and selector:
        keys.add(f"{page_key}|selector:{selector}")
    if page_key and fallback:
        keys.add(f"{page_key}|text:{fallback}")
    return keys


def candidate_keys(candidate: dict) -> set[str]:
    keys: set[str] = set()
    page_key = str(candidate.get("pageKey") or "")
    element_id = str(candidate.get("elementId") or "").strip()
    selector = str(candidate.get("selector") or "").strip()
    fallback = normalize_key(str(candidate.get("fallbackText") or ""))
    if page_key and element_id:
        keys.add(f"{page_key}|element:{element_id}")
    if page_key and selector:
        keys.add(f"{page_key}|selector:{selector}")
    if page_key and fallback:
        keys.add(f"{page_key}|text:{fallback}")
    return keys


def selected_candidates_by_page(candidates: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for page in candidates.get("pages", []):
        page_key = str(page.get("pageKey") or "")
        if not page_key:
            continue
        for candidate in page.get("candidates", []):
            if candidate.get("selected"):
                grouped.setdefault(page_key, []).append(candidate)
    return grouped


def annotations_by_page(data: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for ann in data.get("annotations", []):
        page_key = str(ann.get("pageKey") or "")
        if page_key:
            grouped.setdefault(page_key, []).append(ann)
    return grouped


def is_coarse_selector(selector: str) -> bool:
    return (selector or "").strip().lower() in COARSE_SELECTORS


def has_placeholder_content(content: str) -> bool:
    text = content or ""
    return any(marker in text for marker in PLACEHOLDER_MARKERS)


def page_route(page: dict) -> str:
    return str(page.get("route") or page.get("path") or "").lower()


def is_admin_or_management_page(page: dict) -> bool:
    route = page_route(page)
    return any(token in route for token in ("/admin", "management", "/me/", "edit", "/new", "review"))


def page_min_annotations(page: dict, selected: list[dict]) -> int:
    non_overview = [item for item in selected if item.get("dimension") != "Page overview"]
    if not non_overview:
        return 1
    dimensions = {str(item.get("dimension") or "") for item in non_overview}
    if is_admin_or_management_page(page) or bool(dimensions & FORM_HEAVY_DIMENSIONS):
        return max(4, 1 + len(non_overview))
    if dimensions and dimensions <= READ_ONLY_DIMENSIONS:
        return max(2, 1 + len(non_overview))
    return max(3, 1 + len(non_overview))


def build_annotation_index(annotations: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for ann in annotations:
        for key in target_keys(ann):
            index.setdefault(key, []).append(ann)
    return index


def is_scan_artifact_candidate(candidate: dict) -> bool:
    fallback = str(candidate.get("fallbackText") or "")
    return "${" in fallback or "{{" in fallback


def is_chrome_candidate(candidate: dict) -> bool:
    fallback = str(candidate.get("fallbackText") or "").strip()
    selector = str(candidate.get("selector") or "")
    if fallback:
        return False
    chrome_patterns = ("parentElement.remove", "sidebarToggle", "#sidebarToggle")
    return any(pattern in selector for pattern in chrome_patterns)


def should_require_promotion(candidate: dict) -> bool:
    if candidate.get("dimension") == "Page overview":
        return False
    if is_scan_artifact_candidate(candidate) or is_chrome_candidate(candidate):
        return False
    return True


def dimension_covered_by_existing(candidate: dict, annotations: list[dict]) -> bool:
    dimension = str(candidate.get("dimension") or "")
    selector = str(candidate.get("selector") or "")
    fallback = str(candidate.get("fallbackText") or "")
    non_overview = [ann for ann in annotations if not is_page_overview(ann)]

    if "tr:nth-of-type(" in selector or "exportCredentials" in selector or "deleteApp" in selector:
        return any(ann.get("dimension") == "Table and list" for ann in non_overview)

    if dimension == "Form and validation":
        return any(
            ann.get("dimension") in {"Form and validation", "Primary action"}
            and "字段规则" in str(ann.get("contentMarkdown") or "")
            for ann in non_overview
        )

    coverage_map = {
        "Permission and risk": {"Permission and risk", "Table and list"},
        "Primary action": {"Primary action", "Table and list", "Flow and navigation"},
        "Flow and navigation": {"Flow and navigation", "Primary action"},
        "State and exception": {"State and exception", "Table and list", "Primary action"},
    }
    allowed = coverage_map.get(dimension, {dimension})
    for ann in non_overview:
        if ann.get("dimension") not in allowed:
            continue
        ann_text = str(ann.get("contentMarkdown") or "") + str(ann.get("title") or "")
        if fallback and fallback[:12] in ann_text:
            return True
        if dimension == "Permission and risk" and ann.get("dimension") in {"Permission and risk", "Table and list"}:
            return True
    return False


def candidate_is_promoted(
    candidate: dict,
    annotation_index: dict[str, list[dict]],
    annotations: list[dict] | None = None,
) -> bool:
    if any(annotation_index.get(key) for key in candidate_keys(candidate)):
        return True
    if annotations and dimension_covered_by_existing(candidate, annotations):
        return True
    return False


def validate_dev_handoff(
    data: dict,
    *,
    candidates: dict | None = None,
    as_errors: bool = True,
) -> tuple[int, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    def emit(message: str, *, warning: bool = False) -> None:
        if warning:
            warnings.append(message)
        elif as_errors:
            errors.append(message)
        else:
            warnings.append(message)

    pages = data.get("pages") if isinstance(data.get("pages"), list) else []
    pages_by_key = {str(page.get("pageKey") or ""): page for page in pages if page.get("pageKey")}
    grouped_ann = annotations_by_page(data)
    selected_by_page = selected_candidates_by_page(candidates or {"pages": []})

    for ann in data.get("annotations", []):
        ann_id = str(ann.get("id") or "<missing id>")
        review = ann.get("review") if isinstance(ann.get("review"), dict) else {}
        content = str(ann.get("contentMarkdown") or "")
        target = ann.get("target") if isinstance(ann.get("target"), dict) else {}
        selector = str(target.get("selector") or ann.get("selector") or "").strip()

        if ann.get("createdBy") == "ai" and not review.get("required"):
            emit(f"{ann_id}: AI-generated annotation must keep review.required=true until explicitly approved for delivery")

        if has_placeholder_content(content) and not is_page_overview(ann):
            emit(f"{ann_id}: dev-handoff annotation still contains draft placeholder text")

        if not is_page_overview(ann) and is_coarse_selector(selector):
            emit(f"{ann_id}: dev-handoff annotation uses coarse selector '{selector}'; bind to id/data-ann/button-level target")

        if ann.get("dimension") == "Primary action" or ann.get("annotationType") == "A":
            compact = normalize_key(content)
            if not any(token in compact for token in ["交互规则", "页面流转", "点击后", "成功", "失败", "toast", "跳转", "抽屉", "弹窗"]):
                emit(f"{ann_id}: primary action should describe click result and success/failure feedback")

        evidence = ann.get("evidence")
        if not is_page_overview(ann) and (not isinstance(evidence, list) or not any(str(item).strip() for item in evidence)):
            emit(f"{ann_id}: dev-handoff annotation should include evidence[] with selector/PRD/code references", warning=True)

    if candidates:
        for page_key, page in pages_by_key.items():
            selected = selected_by_page.get(page_key, [])
            annotations = grouped_ann.get(page_key, [])
            min_required = page_min_annotations(page, selected)
            if len(annotations) < min_required:
                emit(
                    f"{page_key}: expected at least {min_required} annotation(s) for dev-handoff, found {len(annotations)} "
                    f"({page.get('route') or page.get('path') or page.get('title') or 'unknown route'})"
                )

            non_overview_selected = [item for item in selected if item.get("dimension") != "Page overview"]
            if non_overview_selected and len([ann for ann in annotations if not is_page_overview(ann)]) == 0:
                emit(f"{page_key}: page has {len(non_overview_selected)} selected element candidate(s) but no element-level annotations")

            annotation_index = build_annotation_index(annotations)
            for candidate in non_overview_selected:
                if not should_require_promotion(candidate):
                    if is_scan_artifact_candidate(candidate):
                        emit(
                            f"{page_key}: selected candidate {candidate.get('candidateId')} looks like a scan artifact; "
                            "consider deselecting it in annotation-candidates.json",
                            warning=True,
                        )
                    continue
                candidate_id = str(candidate.get("candidateId") or "<missing candidate>")
                if not candidate_is_promoted(candidate, annotation_index, annotations):
                    label = candidate.get("fallbackText") or candidate.get("dimension") or candidate_id
                    emit(f"{page_key}: selected candidate {candidate_id} ({label}) was not promoted into annotations.json")

    only_p_pages = [
        page_key
        for page_key, page in pages_by_key.items()
        if grouped_ann.get(page_key)
        and all(is_page_overview(ann) for ann in grouped_ann.get(page_key, []))
        and len(selected_by_page.get(page_key, [])) > 1
    ]
    for page_key in only_p_pages:
        emit(f"{page_key}: page only has page overview annotations but candidates include additional selected points")

    return len(errors), errors, warnings


def audit_summary(data: dict, candidates: dict | None = None) -> dict:
    pages = data.get("pages") if isinstance(data.get("pages"), list) else []
    pages_by_key = {str(page.get("pageKey") or ""): page for page in pages if page.get("pageKey")}
    grouped_ann = annotations_by_page(data)
    selected_by_page = selected_candidates_by_page(candidates or {"pages": []})

    unpromoted: list[dict] = []
    only_overview_pages: list[str] = []
    coarse_anchor_ids: list[str] = []
    placeholder_ids: list[str] = []
    review_bypass_ids: list[str] = []

    for ann in data.get("annotations", []):
        ann_id = str(ann.get("id") or "")
        review = ann.get("review") if isinstance(ann.get("review"), dict) else {}
        target = ann.get("target") if isinstance(ann.get("target"), dict) else {}
        selector = str(target.get("selector") or "").strip()
        if ann.get("createdBy") == "ai" and not review.get("required"):
            review_bypass_ids.append(ann_id)
        if has_placeholder_content(str(ann.get("contentMarkdown") or "")) and not is_page_overview(ann):
            placeholder_ids.append(ann_id)
        if not is_page_overview(ann) and is_coarse_selector(selector):
            coarse_anchor_ids.append(ann_id)

    if candidates:
        for page_key, selected in selected_by_page.items():
            annotations = grouped_ann.get(page_key, [])
            annotation_index = build_annotation_index(annotations)
            for candidate in selected:
                if not should_require_promotion(candidate):
                    continue
                if not candidate_is_promoted(candidate, annotation_index, annotations):
                    unpromoted.append(
                        {
                            "pageKey": page_key,
                            "candidateId": candidate.get("candidateId"),
                            "label": candidate.get("fallbackText") or candidate.get("dimension"),
                            "dimension": candidate.get("dimension"),
                        }
                    )
            if annotations and all(is_page_overview(ann) for ann in annotations) and len(selected) > 1:
                only_overview_pages.append(page_key)

    page_rows = []
    for page_key, page in pages_by_key.items():
        selected = selected_by_page.get(page_key, [])
        annotations = grouped_ann.get(page_key, [])
        page_rows.append(
            {
                "pageKey": page_key,
                "title": page.get("title") or page_key,
                "route": page.get("route") or page.get("path"),
                "annotationCount": len(annotations),
                "selectedCandidateCount": len(selected),
                "minRequired": page_min_annotations(page, selected),
                "onlyOverview": page_key in only_overview_pages,
            }
        )

    return {
        "annotationMode": annotation_mode(data),
        "pages": page_rows,
        "unpromotedCandidates": unpromoted,
        "onlyOverviewPages": only_overview_pages,
        "coarseAnchorIds": coarse_anchor_ids,
        "placeholderIds": placeholder_ids,
        "reviewBypassIds": review_bypass_ids,
    }
