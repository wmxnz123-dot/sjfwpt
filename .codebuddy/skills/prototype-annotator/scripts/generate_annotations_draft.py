#!/usr/bin/env python3
"""Generate reviewable annotations.json drafts from annotation candidates."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from annotation_copywriter import (
    DEFAULT_AUDIENCE_MODE,
    VALID_AUDIENCE_MODES,
    annotation_review_reason,
    generate_ai_content,
    generate_annotation_content,
    generate_dev_notes,
    generate_fallback_content,
    normalize_annotation_title,
)
from annotation_types import ANNOTATION_TYPE_BY_DIMENSION, TOPICS_BY_DIMENSION


ANNOTATION_DIR_NAME = "prototype-annotator"
LEGACY_ANNOTATION_DIR_NAME = ".prototype-annotations"
SKILL_DIR = Path(__file__).resolve().parents[1]
PUBLIC_RUNTIME_FILES = (
    "prototype-annotator.css",
    "markdown-renderer.js",
    "mermaid-loader.js",
    "prototype-annotator.js",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def annotation_root(target: Path) -> Path:
    return target.parent if target.is_file() else target


def default_candidates(target: Path) -> Path:
    preferred = annotation_root(target) / ANNOTATION_DIR_NAME / "annotation-candidates.json"
    if preferred.exists():
        return preferred
    legacy = annotation_root(target) / LEGACY_ANNOTATION_DIR_NAME / "annotation-candidates.json"
    if legacy.exists():
        return legacy
    return preferred


def default_annotations(target: Path) -> Path:
    return annotation_root(target) / ANNOTATION_DIR_NAME / "annotations.json"


def default_existing_annotations(target: Path) -> Path:
    preferred = default_annotations(target)
    if preferred.exists():
        return preferred
    legacy = annotation_root(target) / LEGACY_ANNOTATION_DIR_NAME / "annotations.json"
    if legacy.exists():
        return legacy
    return preferred


def detect_framework(target: Path) -> str | None:
    package_json = annotation_root(target) / "package.json"
    if not package_json.exists():
        return None
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    deps = {}
    deps.update(data.get("dependencies") or {})
    deps.update(data.get("devDependencies") or {})
    if "vue" in deps:
        return "vue"
    if "react" in deps:
        return "react"
    return None


def public_annotations_path(target: Path) -> Path:
    return annotation_root(target) / "public" / "prototype-annotator" / "annotations.json"


def sync_public_prototype_annotator(target: Path, output: Path, default_output: Path) -> list[Path]:
    if output.resolve() != default_output.resolve():
        return []
    if not detect_framework(target):
        return []
    public_dir = annotation_root(target) / "public" / "prototype-annotator"
    public_dir.mkdir(parents=True, exist_ok=True)
    synced: list[Path] = []
    template_runtime = SKILL_DIR / "templates" / "runtime"
    for name in PUBLIC_RUNTIME_FILES:
        source = template_runtime / name
        if source.exists():
            destination = public_dir / name
            shutil.copy2(source, destination)
            synced.append(destination)
    annotations_copy = public_dir / "annotations.json"
    shutil.copy2(output, annotations_copy)
    synced.append(annotations_copy)
    return synced


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise SystemExit(f"Invalid JSON in {path}: {err}") from err


def normalize_product_profile(payload: dict) -> dict:
    profile = payload.get("productProfile") if isinstance(payload.get("productProfile"), dict) else payload
    return dict(profile) if isinstance(profile, dict) else {}


def default_product_context_path(target: Path) -> Path:
    preferred = annotation_root(target) / ANNOTATION_DIR_NAME / "product-context.json"
    if preferred.exists():
        return preferred
    legacy = annotation_root(target) / LEGACY_ANNOTATION_DIR_NAME / "product-context.json"
    if legacy.exists():
        return legacy
    return preferred


def load_product_context(path: Path | None) -> dict | None:
    if not path or not path.exists():
        return None
    payload = read_json(path)
    return payload if isinstance(payload, dict) else None


def default_product_profile_path(target: Path) -> Path | None:
    root = annotation_root(target)
    candidates = [
        root / "product-profile.json",
        root.parent / "product-profile.json",
        root / "input" / "product-profile.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def load_product_profile(path: Path | None) -> dict | None:
    if not path:
        return None
    if not path.exists():
        raise SystemExit(f"Product profile file does not exist: {path}")
    return normalize_product_profile(read_json(path))


def profile_signal_text(candidates: dict, product_context: dict | None, target: Path) -> str:
    parts: list[str] = [annotation_root(target).name]
    if product_context:
        parts.extend(
            [
                str(product_context.get("productName") or ""),
                str(product_context.get("productType") or ""),
                " ".join(str(item) for item in product_context.get("roles") or []),
            ]
        )
        for page in product_context.get("pages") or []:
            if isinstance(page, dict):
                parts.extend(
                    [
                        str(page.get("pageName") or ""),
                        str(page.get("purpose") or ""),
                        " ".join(str(item) for item in page.get("primaryTasks") or []),
                    ]
                )
    for page in candidates.get("pages", []):
        parts.extend([str(page.get("title") or ""), str(page.get("route") or ""), str(page.get("path") or "")])
        for candidate in page.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            parts.extend(
                [
                    str(candidate.get("fallbackText") or ""),
                    " ".join(str(item) for item in candidate.get("evidence") or []),
                ]
            )
    return "\n".join(part for part in parts if part)


def inferred_enabled_types(product_forms: list[str]) -> list[str]:
    enabled = ["P", "E", "C", "A", "J", "S", "R", "PERM", "DATA"]
    forms_text = " ".join(product_forms).lower()
    if "ai" in forms_text or "智能体" in forms_text:
        enabled.extend(["AI", "PROMPT", "CTX", "HITL", "FALLBACK"])
    if "数据" in forms_text or "bi" in forms_text:
        enabled.extend(["METRIC", "SOURCE", "FILTER", "REFRESH", "DRILL"])
    if "saas" in forms_text:
        enabled.extend(["ROLE", "PLAN", "TENANT"])
    if "内容" in forms_text or "社区" in forms_text:
        enabled.extend(["CONTENT", "PUBLISH", "MOD", "REC", "TRACK"])
    deduped: list[str] = []
    for item in enabled:
        if item not in deduped:
            deduped.append(item)
    return deduped


def infer_product_profile(candidates: dict, product_context: dict | None, target: Path) -> dict:
    text = profile_signal_text(candidates, product_context, target)
    lowered = text.lower().replace("interaction-plan", "")
    product_name = ""
    if product_context:
        product_name = str(product_context.get("productName") or "").strip()
    if not product_name:
        product_name = annotation_root(target).name

    ai_hits = len(re.findall(r"\bai\b|agent|copilot|prompt|提示词|智能体|智能生成|智能推荐|智能审核|生成类|大模型", lowered, re.I))
    enterprise_hits = len(re.findall(r"/admin|后台|管理|审核|审批|权限|角色|企业|b端|enterprise|review|settings|users", lowered, re.I))
    data_hits = len(re.findall(r"指标|看板|报表|图表|analytics|metric|dashboard|数据来源|刷新频率", lowered, re.I))
    saas_hits = len(re.findall(r"\bsaas\b|多租户|租户|套餐|订阅套餐|\bplan\b|\btenant\b", lowered, re.I))
    content_hits = len(re.findall(r"内容|社区|发布|审核机制|推荐|素材|资源广场|市场", lowered, re.I))

    forms: list[str] = []
    if enterprise_hits >= 3:
        forms.append("B端应用")
    if ai_hits >= 2:
        forms.append("AI产品")
    if data_hits >= 4:
        forms.append("数据产品")
    if saas_hits >= 2:
        forms.append("SaaS产品")
    if content_hits >= 4:
        forms.append("内容/工具产品")
    if not forms:
        forms.append("通用产品")

    if "AI产品" in forms and "B端应用" in forms:
        product_type = "ai_enterprise_app"
    elif "AI产品" in forms:
        product_type = "ai_product"
    elif "数据产品" in forms:
        product_type = "data_product"
    elif "SaaS产品" in forms:
        product_type = "saas"
    elif "B端应用" in forms:
        product_type = "enterprise_app"
    else:
        product_type = "general"

    primary_users = []
    if product_context and isinstance(product_context.get("roles"), list):
        primary_users = [str(item) for item in product_context.get("roles") or [] if str(item).strip()]
    if not primary_users:
        primary_users = ["业务用户"]
    return {
        "productName": product_name,
        "productType": product_type,
        "productForms": forms,
        "primaryUsers": primary_users[:8],
        "annotationMode": "standard",
        "enabledAnnotationTypes": inferred_enabled_types(forms),
        "inferred": True,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def compact(value: str, limit: int = 28) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def is_table_row_selector(selector: str) -> bool:
    return bool(re.search(r"tr:nth-of-type\(\d+\)", selector or ""))


def candidate_label(candidate: dict, fallback: str = "该元素") -> str:
    return compact(str(candidate.get("fallbackText") or candidate.get("title") or fallback), 32)


def topics_for(candidate: dict) -> list[str]:
    topics = candidate.get("topics") if isinstance(candidate.get("topics"), list) else None
    if topics:
        return [str(topic) for topic in topics if str(topic).strip()]
    return list(TOPICS_BY_DIMENSION.get(str(candidate.get("dimension") or "")) or ["business"])


def annotation_type_for(candidate: dict, product_profile: dict | None = None) -> str:
    raw = str(candidate.get("annotationType") or "").strip()
    if raw:
        ann_type = raw
    else:
        dimension = str(candidate.get("dimension") or "")
        if dimension == "Page overview":
            ann_type = "P"
        else:
            ann_type = ANNOTATION_TYPE_BY_DIMENSION.get(dimension) or "C"
    enabled = enabled_annotation_types(product_profile)
    if enabled and ann_type not in enabled:
        selector = str(candidate.get("selector") or "")
        tag = str(candidate.get("tag") or "")
        if ann_type == "AI" and "METRIC" in enabled and (tag == "canvas" or "chart" in selector):
            return "METRIC"
        if ann_type == "AI" and "DATA" in enabled:
            return "DATA"
    return ann_type


def enabled_annotation_types(product_profile: dict | None) -> set[str] | None:
    if not product_profile:
        return None
    enabled = product_profile.get("enabledAnnotationTypes")
    if not isinstance(enabled, list) or not enabled:
        return None
    return {str(item).strip() for item in enabled if str(item).strip()}


def candidate_allowed(candidate: dict, product_profile: dict | None) -> bool:
    enabled = enabled_annotation_types(product_profile)
    if not enabled:
        return True
    ann_type = annotation_type_for(candidate, product_profile)
    return ann_type in enabled


def downstream_action_for(candidate: dict) -> list[str]:
    dimension = str(candidate.get("dimension") or "")
    label = candidate_label(candidate)
    if dimension == "Primary action":
        return [f"点击 `{label}` 后需要确认页面/弹窗/状态变化、成功反馈和失败处理。"]
    if dimension == "Flow and navigation":
        return [f"触发 `{label}` 后需要确认目标页面、返回路径或二级承载面。"]
    return []


def dependencies_for(candidate: dict) -> list[str]:
    dimension = str(candidate.get("dimension") or "")
    if dimension == "Form and validation":
        return ["需确认字段必填性、默认值、校验时机、选项来源和提交阻断条件。"]
    if dimension == "Permission and risk":
        return ["需确认角色权限、状态限制、二次确认和操作后的数据影响。"]
    if dimension == "Page overview":
        return ["需确认本页在完整业务流程中的入口、出口和服务对象。"]
    return []


def risks_for(candidate: dict) -> list[str]:
    if str(candidate.get("dimension") or "") == "Permission and risk":
        return ["风险或权限敏感操作，需确认是否可撤销、是否记录审计和是否触发通知。"]
    return []


def open_questions_for(candidate: dict) -> list[str]:
    source = candidate.get("source") if isinstance(candidate.get("source"), dict) else {}
    source_type = source.get("type") or ""
    questions: list[str] = []
    if source_type in {"prototype", "local-rule-draft"}:
        questions.append("该说明基于原型结构推断，需确认 PRD、上游页面级需求说明文档或人工评审中的最终规则。")
    if str(candidate.get("selectorQuality", {}).get("level") if isinstance(candidate.get("selectorQuality"), dict) else "") == "fragile":
        questions.append("当前 selector 较脆弱，建议补充 data-ann 或 data-testid。")
    return questions


def load_existing(path: Path, target: Path) -> dict:
    if path.exists():
        return read_json(path)
    page_path = target.name if target.is_file() else "index.html"
    return {
        "version": 1,
        "project": {"id": annotation_root(target).name, "name": annotation_root(target).name, "source": "local-rule-draft"},
        "pages": [{"pageKey": "P01", "title": annotation_root(target).name, "path": page_path, "route": "/" + page_path}],
        "annotations": [],
    }


def pages_from_candidates(candidates: dict) -> list[dict]:
    pages = []
    for page in candidates.get("pages", []):
        if not page.get("pageKey"):
            continue
        pages.append(
            {
                "pageKey": page.get("pageKey"),
                "title": page.get("title") or page.get("pageKey"),
                "path": page.get("path") or "",
                "route": page.get("route") or "",
            }
        )
    return pages


def next_ids(existing: list[dict]) -> dict[str, int]:
    counters: dict[str, int] = {}
    for ann in existing:
        ann_id = str(ann.get("id") or "")
        match = re.match(r"ANN-(.+)-(\d{3,})$", ann_id)
        if not match:
            continue
        page_key, raw_number = match.groups()
        counters[page_key] = max(counters.get(page_key, 0), int(raw_number))
    return counters


def next_id(page_key: str, counters: dict[str, int]) -> str:
    counters[page_key] = counters.get(page_key, 0) + 1
    return f"ANN-{page_key}-{counters[page_key]:03d}"


def annotation_key(ann: dict) -> tuple[str, str]:
    target = ann.get("target") if isinstance(ann.get("target"), dict) else {}
    return str(ann.get("pageKey") or ""), str(target.get("sourceElementId") or target.get("selector") or ann.get("selector") or "")


def candidate_key(candidate: dict) -> tuple[str, str]:
    return str(candidate.get("pageKey") or ""), str(candidate.get("elementId") or candidate.get("selector") or "")


def existing_by_target(annotations: list[dict]) -> dict[tuple[str, str], dict]:
    by_key: dict[tuple[str, str], dict] = {}
    for ann in annotations:
        key = annotation_key(ann)
        if key[0] and key[1]:
            by_key[key] = ann
    return by_key


def is_protected(ann: dict) -> bool:
    target = ann.get("target") if isinstance(ann.get("target"), dict) else {}
    review = ann.get("review") if isinstance(ann.get("review"), dict) else {}
    return (
        ann.get("createdBy") == "manual"
        or target.get("strategy") == "manual"
        or review.get("status") == "approved"
    )


def title_for(candidate: dict) -> str:
    return normalize_annotation_title(candidate)


def surface_fields_for(candidate: dict) -> dict:
    fields: dict = {}
    if candidate.get("surfaceId"):
        fields["surfaceId"] = candidate.get("surfaceId")
    if candidate.get("displayWhenClosed"):
        fields["displayWhenClosed"] = candidate.get("displayWhenClosed")
    if candidate.get("fallbackAnchorSelector"):
        fields["fallbackAnchorSelector"] = candidate.get("fallbackAnchorSelector")
    return fields


def merge_surfaces(existing: dict, candidates: dict) -> None:
    incoming = candidates.get("surfaces") if isinstance(candidates.get("surfaces"), list) else []
    if not incoming:
        return
    merged: dict[str, dict] = {}
    for surface in existing.get("surfaces") or []:
        if isinstance(surface, dict) and surface.get("id"):
            merged[str(surface["id"])] = surface
    for surface in incoming:
        if not isinstance(surface, dict) or not surface.get("id"):
            continue
        surface_id = str(surface["id"])
        current = merged.get(surface_id)
        if current and str(current.get("scanSource") or "") == "manual":
            continue
        merged[surface_id] = {**(current or {}), **surface}
    existing["surfaces"] = list(merged.values())


def candidate_to_annotation(
    candidate: dict,
    ann_id: str,
    *,
    product_context: dict | None = None,
    product_profile: dict | None = None,
    audience_mode: str = DEFAULT_AUDIENCE_MODE,
) -> dict:
    source = candidate.get("source") if isinstance(candidate.get("source"), dict) else {}
    source_type = source.get("type") or "local-rule-draft"
    dev_notes = generate_dev_notes(candidate, audience_mode)
    annotation = {
        "id": ann_id,
        "pageKey": candidate.get("pageKey"),
        "target": {
            "selector": candidate.get("selector") or "body",
            "fallbackText": candidate.get("fallbackText") or "",
            "strategy": candidate.get("strategy") or "path",
            "sourceElementId": candidate.get("elementId"),
            "boundsHint": {
                "text": candidate.get("fallbackText") or "",
                "tag": candidate.get("tag") or "",
            },
        },
        "title": title_for(candidate),
        "contentMarkdown": generate_annotation_content(
            candidate=candidate,
            product_context=product_context,
            audience_mode=audience_mode,
        ),
        "devNotesMarkdown": dev_notes or None,
        "audienceMode": audience_mode,
        "annotationType": annotation_type_for(candidate, product_profile),
        "kind": candidate.get("kind") or "note",
        "topics": topics_for(candidate),
        "dimension": candidate.get("dimension") or "",
        "priority": candidate.get("priority") or "medium",
        "visible": True,
        "source": {
            "type": source_type if source_type in {"prd", "prototype", "page-spec", "mixed"} else "local-rule-draft",
            "ref": source.get("ref") or candidate.get("candidateId"),
        },
        "evidence": candidate.get("evidence") or [],
        "nextActions": downstream_action_for(candidate),
        "dependencies": dependencies_for(candidate),
        "risks": risks_for(candidate),
        "openQuestions": open_questions_for(candidate),
        "candidateId": candidate.get("candidateId"),
        "selectorQuality": candidate.get("selectorQuality"),
        "createdBy": "ai",
        "review": {
            "required": True,
            "status": "pending",
            "reason": annotation_review_reason(audience_mode),
        },
        "updatedAt": now_iso(),
    }
    annotation.update(surface_fields_for(candidate))
    return annotation


def selected_candidates(payload: dict) -> list[dict]:
    items: list[dict] = []
    for page in payload.get("pages", []):
        for candidate in page.get("candidates", []):
            if candidate.get("selected"):
                items.append(candidate)
    return items


def profile_text(product_profile: dict | None) -> str:
    if not product_profile:
        return ""
    parts = [
        str(product_profile.get("productType") or ""),
        " ".join(str(item) for item in product_profile.get("productForms") or []),
    ]
    return " ".join(parts).lower()


def is_ai_product(product_profile: dict | None) -> bool:
    text = profile_text(product_profile)
    return any(token in text for token in ["ai", "agent", "copilot", "ai_product", "ai_enterprise_app", "智能"])


def is_enterprise_product(product_profile: dict | None) -> bool:
    text = profile_text(product_profile)
    return any(token in text for token in ["enterprise", "admin", "workflow", "approval", "mdm", "b端", "企业", "后台", "审批"])


def is_data_product(product_profile: dict | None) -> bool:
    text = profile_text(product_profile)
    return any(token in text for token in ["data", "bi", "dashboard", "analytics", "数据", "看板", "指标"])


def pick_ai_anchor(annotations: list[dict]) -> dict | None:
    for ann in annotations:
        title = str(ann.get("title") or "")
        if ann.get("annotationType") == "AI":
            return ann
        if re.search(r"ai|agent|skill|智能|模型", title, re.I):
            return ann
    for ann in annotations:
        if ann.get("annotationType") == "P":
            return ann
    return annotations[0] if annotations else None


def pick_data_anchor(annotations: list[dict]) -> dict | None:
    for ann in annotations:
        title = str(ann.get("title") or "")
        dimension = str(ann.get("dimension") or "")
        if ann.get("annotationType") in {"DATA", "METRIC", "SOURCE"}:
            return ann
        if dimension in {"Data explanation", "Table and list"}:
            return ann
        if re.search(r"指标|图表|报表|数据|列表|看板|analytics|metric|chart", title, re.I):
            return ann
    return next((ann for ann in annotations if ann.get("annotationType") == "P"), None)


def ensure_ai_processing_annotation(
    annotations: list[dict],
    counters: dict[str, int],
    product_profile: dict | None,
    *,
    product_context: dict | None = None,
    audience_mode: str = DEFAULT_AUDIENCE_MODE,
) -> int:
    if not is_ai_product(product_profile):
        return 0
    enabled = enabled_annotation_types(product_profile)
    if enabled and "AI" not in enabled:
        return 0
    if any(str(ann.get("annotationType") or "") == "AI" for ann in annotations):
        return 0
    anchor = pick_ai_anchor(annotations)
    if not anchor:
        return 0
    page_key = str(anchor.get("pageKey") or "P01")
    target = dict(anchor.get("target") if isinstance(anchor.get("target"), dict) else {})
    fallback = target.get("fallbackText") or anchor.get("title") or "AI 能力"
    ai_candidate = {
        "fallbackText": fallback,
        "dimension": "AI and automation",
        "annotationType": "AI",
        "pageKey": page_key,
    }
    annotations.append(
        {
            "id": next_id(page_key, counters),
            "pageKey": page_key,
            "target": target,
            "title": normalize_annotation_title(ai_candidate),
            "contentMarkdown": generate_ai_content(ai_candidate, product_context=product_context),
            "audienceMode": audience_mode,
            "annotationType": "AI",
            "kind": "ai",
            "topics": ["ai", "business", "exception"],
            "dimension": "AI and automation",
            "priority": "high",
            "visible": True,
            "source": {"type": "mixed", "ref": "productProfile.ai"},
            "evidence": ["productProfile 表明当前产品包含 AI 产品形态。"],
            "nextActions": [],
            "dependencies": ["需确认 AI 输入来源、输出展示、人工确认与失败兜底规则。"],
            "risks": [],
            "openQuestions": ["AI 结果是否需要置信度展示与人工确认后才能提交？"],
            "candidateId": None,
            "selectorQuality": anchor.get("selectorQuality"),
            "createdBy": "ai",
            "review": {
                "required": True,
                "status": "pending",
                "reason": annotation_review_reason(audience_mode),
            },
            "updatedAt": now_iso(),
        }
    )
    return 1


def ensure_data_annotation(
    annotations: list[dict],
    counters: dict[str, int],
    product_profile: dict | None,
    *,
    product_context: dict | None = None,
    audience_mode: str = DEFAULT_AUDIENCE_MODE,
) -> int:
    if not is_data_product(product_profile):
        return 0
    enabled = enabled_annotation_types(product_profile)
    if enabled and not (enabled & {"DATA", "METRIC", "SOURCE"}):
        return 0
    if any(str(ann.get("annotationType") or "") in {"DATA", "METRIC", "SOURCE"} for ann in annotations):
        return 0
    anchor = pick_data_anchor(annotations)
    if not anchor:
        return 0
    page_key = str(anchor.get("pageKey") or "P01")
    target = dict(anchor.get("target") if isinstance(anchor.get("target"), dict) else {})
    label = target.get("fallbackText") or anchor.get("title") or "数据口径"
    candidate = {
        "fallbackText": label,
        "dimension": "Data explanation",
        "annotationType": "DATA",
        "pageKey": page_key,
    }
    annotations.append(
        {
            "id": next_id(page_key, counters),
            "pageKey": page_key,
            "target": target,
            "title": "数据口径",
            "contentMarkdown": generate_annotation_content(
                candidate,
                product_context=product_context,
                audience_mode=audience_mode,
            ),
            "audienceMode": audience_mode,
            "annotationType": "DATA",
            "kind": "data",
            "topics": ["data", "business", "dependency"],
            "dimension": "Data explanation",
            "priority": "high",
            "visible": True,
            "source": {"type": "mixed", "ref": "productProfile.data"},
            "evidence": ["productProfile 表明当前产品包含数据、指标或看板形态。"],
            "nextActions": [],
            "dependencies": ["需确认数据来源、刷新时机、统计口径和权限过滤范围。"],
            "risks": [],
            "openQuestions": ["指标口径、数据来源和刷新频率是否已确认？"],
            "candidateId": None,
            "selectorQuality": anchor.get("selectorQuality"),
            "createdBy": "ai",
            "review": {
                "required": True,
                "status": "pending",
                "reason": annotation_review_reason(audience_mode),
            },
            "updatedAt": now_iso(),
        }
    )
    return 1


def ensure_enterprise_risk_annotation(
    annotations: list[dict],
    counters: dict[str, int],
    product_profile: dict | None,
    *,
    product_context: dict | None = None,
    audience_mode: str = DEFAULT_AUDIENCE_MODE,
) -> int:
    if not is_enterprise_product(product_profile):
        return 0
    enabled = enabled_annotation_types(product_profile)
    if enabled and "PERM" not in enabled:
        return 0
    existing_types = {str(ann.get("annotationType") or "") for ann in annotations}
    if existing_types & {"PERM", "WF", "R", "S"}:
        return 0
    anchor = next((ann for ann in annotations if ann.get("annotationType") == "A" and ann.get("title") == "行级操作"), None)
    anchor = anchor or next((ann for ann in annotations if ann.get("dimension") == "Permission and risk"), None)
    anchor = anchor or next((ann for ann in annotations if ann.get("annotationType") == "A"), None)
    anchor = anchor or next((ann for ann in annotations if ann.get("annotationType") == "P"), None)
    if not anchor:
        return 0
    page_key = str(anchor.get("pageKey") or "P01")
    target = dict(anchor.get("target") if isinstance(anchor.get("target"), dict) else {})
    risk_candidate = {
        "fallbackText": target.get("fallbackText") or anchor.get("title") or "高风险操作",
        "dimension": "Permission and risk",
        "annotationType": "PERM",
        "pageKey": page_key,
    }
    annotations.append(
        {
            "id": next_id(page_key, counters),
            "pageKey": page_key,
            "target": target,
            "title": "权限与风险",
            "contentMarkdown": generate_annotation_content(
                risk_candidate,
                product_context=product_context,
                audience_mode=audience_mode,
            ),
            "audienceMode": audience_mode,
            "annotationType": "PERM",
            "kind": "permission",
            "topics": ["risk", "dependency", "interaction"],
            "dimension": "Permission and risk",
            "priority": "high",
            "visible": True,
            "source": {"type": "mixed", "ref": "productProfile.enterprise"},
            "evidence": ["productProfile 表明当前产品包含企业级权限或风险操作。"],
            "nextActions": [],
            "dependencies": ["需确认角色权限、状态限制、二次确认和操作后的数据影响。"],
            "risks": ["风险或权限敏感操作，需确认是否可撤销、是否记录审计和是否触发通知。"],
            "openQuestions": ["高风险操作是否需要二次确认与审计日志？"],
            "candidateId": None,
            "selectorQuality": anchor.get("selectorQuality"),
            "createdBy": "ai",
            "review": {
                "required": True,
                "status": "pending",
                "reason": annotation_review_reason(audience_mode),
            },
            "updatedAt": now_iso(),
        }
    )
    return 1


def ensure_ai_fallback_annotation(
    annotations: list[dict],
    counters: dict[str, int],
    product_profile: dict | None,
    *,
    product_context: dict | None = None,
    audience_mode: str = DEFAULT_AUDIENCE_MODE,
) -> int:
    if not is_ai_product(product_profile):
        return 0
    existing_types = {str(ann.get("annotationType") or "") for ann in annotations}
    if existing_types & {"HITL", "FALLBACK"}:
        return 0
    ai_ann = next((ann for ann in annotations if ann.get("annotationType") == "AI"), None)
    anchor = ai_ann or next((ann for ann in annotations if ann.get("annotationType") == "P"), None)
    if not anchor:
        return 0
    page_key = str(anchor.get("pageKey") or "P01")
    target = dict(anchor.get("target") if isinstance(anchor.get("target"), dict) else {})
    fallback = target.get("fallbackText") or anchor.get("title") or "AI 处理结果"
    fallback_candidate = {
        "fallbackText": fallback,
        "dimension": "AI and automation",
        "annotationType": "FALLBACK",
        "pageKey": page_key,
    }
    annotations.append(
        {
            "id": next_id(page_key, counters),
            "pageKey": page_key,
            "target": target,
            "title": "AI 失败兜底",
            "contentMarkdown": generate_fallback_content(
                fallback_candidate,
                product_context=product_context,
            ),
            "audienceMode": audience_mode,
            "annotationType": "FALLBACK",
            "kind": "ai",
            "topics": ["ai", "exception"],
            "dimension": "AI and automation",
            "priority": "high",
            "visible": True,
            "source": {"type": "mixed", "ref": "productProfile.ai"},
            "evidence": ["productProfile 表明当前产品包含 AI 产品形态。"],
            "nextActions": [],
            "dependencies": ["需确认 AI 失败后的人工修正、重试和提交阻断规则。"],
            "risks": [],
            "openQuestions": ["AI 失败或低置信度时是否允许人工确认后继续提交？"],
            "candidateId": None,
            "selectorQuality": anchor.get("selectorQuality"),
            "createdBy": "ai",
            "review": {
                "required": True,
                "status": "pending",
                "reason": annotation_review_reason(audience_mode),
            },
            "updatedAt": now_iso(),
        }
    )
    return 1


def merge_annotations(
    existing: dict,
    candidates: dict,
    force: bool,
    replace_generated: bool = False,
    product_profile: dict | None = None,
    product_context: dict | None = None,
    audience_mode: str = DEFAULT_AUDIENCE_MODE,
) -> tuple[dict, int, int]:
    annotations = list(existing.get("annotations") if isinstance(existing.get("annotations"), list) else [])
    if replace_generated:
        annotations = [ann for ann in annotations if is_protected(ann)]
    by_key = existing_by_target(annotations)
    counters = next_ids(annotations)
    created = 0
    updated = 0

    for candidate in selected_candidates(candidates):
        if not candidate_allowed(candidate, product_profile):
            continue
        key = candidate_key(candidate)
        current = by_key.get(key)
        if current and is_protected(current) and not force:
            continue
        if current:
            draft = candidate_to_annotation(
                candidate,
                current.get("id") or next_id(str(candidate.get("pageKey")), counters),
                product_context=product_context,
                product_profile=product_profile,
                audience_mode=audience_mode,
            )
            current.update(
                {
                    "title": draft["title"],
                    "contentMarkdown": draft["contentMarkdown"],
                    "devNotesMarkdown": draft.get("devNotesMarkdown"),
                    "audienceMode": draft.get("audienceMode"),
                    "annotationType": draft["annotationType"],
                    "kind": draft["kind"],
                    "topics": draft["topics"],
                    "dimension": draft["dimension"],
                    "priority": draft["priority"],
                    "source": draft["source"],
                    "evidence": draft["evidence"],
                    "nextActions": draft["nextActions"],
                    "dependencies": draft["dependencies"],
                    "risks": draft["risks"],
                    "openQuestions": draft["openQuestions"],
                    "candidateId": draft["candidateId"],
                    "selectorQuality": draft.get("selectorQuality"),
                    "review": draft["review"],
                    "updatedAt": draft["updatedAt"],
                    **surface_fields_for(candidate),
                }
            )
            current.setdefault("target", {}).update(draft["target"])
            updated += 1
            continue
        ann = candidate_to_annotation(
            candidate,
            next_id(str(candidate.get("pageKey")), counters),
            product_context=product_context,
            product_profile=product_profile,
            audience_mode=audience_mode,
        )
        annotations.append(ann)
        by_key[key] = ann
        created += 1

    created += ensure_ai_processing_annotation(
        annotations,
        counters,
        product_profile,
        product_context=product_context,
        audience_mode=audience_mode,
    )
    created += ensure_ai_fallback_annotation(
        annotations,
        counters,
        product_profile,
        product_context=product_context,
        audience_mode=audience_mode,
    )
    created += ensure_data_annotation(
        annotations,
        counters,
        product_profile,
        product_context=product_context,
        audience_mode=audience_mode,
    )
    created += ensure_enterprise_risk_annotation(
        annotations,
        counters,
        product_profile,
        product_context=product_context,
        audience_mode=audience_mode,
    )
    merge_surfaces(existing, candidates)
    pages = pages_from_candidates(candidates) or existing.get("pages") or []
    existing["version"] = existing.get("version") or 1
    existing["project"] = existing.get("project") or {"id": "prototype", "name": "Prototype", "source": "local-rule-draft"}
    if product_profile:
        existing["productProfile"] = product_profile
    elif isinstance(existing.get("productProfile"), dict):
        existing["productProfile"] = existing["productProfile"]
    existing["audienceMode"] = audience_mode
    if product_context:
        existing["productContext"] = product_context
    existing["pages"] = pages
    existing["annotations"] = sorted(annotations, key=lambda item: (str(item.get("pageKey")), str(item.get("id"))))
    return existing, created, updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Prototype Annotator annotations.json draft from candidates.")
    parser.add_argument("prototype_path", help="HTML file or static directory")
    parser.add_argument("--candidates", help="Path to annotation-candidates.json")
    parser.add_argument("--annotations", help="Existing annotations.json path")
    parser.add_argument("--out", help="Output annotations.json path")
    parser.add_argument("--product-profile", help="Path to product-profile.json. Defaults to nearby product-profile.json when present.")
    parser.add_argument("--product-context", help="Path to product-context.json. Defaults to prototype-annotator/product-context.json when present.")
    parser.add_argument(
        "--audience",
        choices=list(VALID_AUDIENCE_MODES),
        default=DEFAULT_AUDIENCE_MODE,
        help="Audience mode for generated annotation copy. Defaults to product-review.",
    )
    parser.add_argument("--force", action="store_true", help="Allow updating manual or approved annotations")
    parser.add_argument(
        "--replace-generated",
        action="store_true",
        help="Replace existing generated annotations before merging candidates, while preserving manual or approved annotations.",
    )
    parser.add_argument(
        "--promote-all-selected",
        action="store_true",
        help="Alias for the default behavior: merge every selected candidate from annotation-candidates.json into annotations.json.",
    )
    args = parser.parse_args()

    target = Path(args.prototype_path).resolve()
    if not target.exists():
        parser.error(f"Path does not exist: {target}")
    candidates_path = Path(args.candidates).resolve() if args.candidates else default_candidates(target)
    if not candidates_path.exists():
        parser.error(f"Candidates file does not exist: {candidates_path}. Run scripts/build_annotation_candidates.py first.")
    default_output_path = default_annotations(target)
    annotations_path = Path(args.annotations).resolve() if args.annotations else default_existing_annotations(target)
    output = Path(args.out).resolve() if args.out else default_output_path
    product_profile_path = Path(args.product_profile).resolve() if args.product_profile else default_product_profile_path(target)
    product_profile = load_product_profile(product_profile_path)
    product_context_path = (
        Path(args.product_context).resolve()
        if args.product_context
        else default_product_context_path(target)
    )
    product_context = load_product_context(product_context_path)
    candidates_payload = read_json(candidates_path)
    existing_payload = load_existing(annotations_path, target)
    if not product_profile:
        existing_profile = existing_payload.get("productProfile")
        product_profile = (
            existing_profile
            if isinstance(existing_profile, dict) and existing_profile and not existing_profile.get("inferred")
            else infer_product_profile(candidates_payload, product_context, target)
        )
    payload, created, updated = merge_annotations(
        existing_payload,
        candidates_payload,
        args.force,
        args.replace_generated,
        product_profile,
        product_context,
        args.audience,
    )
    write_json(output, payload)
    public_synced = sync_public_prototype_annotator(target, output, default_output_path)
    print(f"Wrote annotations draft: {output}")
    if public_synced:
        print(f"Synced public prototype-annotator assets: {len(public_synced)} file(s)")
    print(f"Created: {created}; updated: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
