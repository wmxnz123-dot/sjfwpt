#!/usr/bin/env python3
"""Render Markdown reports from Prototype Annotator annotations.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from dev_handoff import (
    annotation_mode,
    annotations_by_page,
    audit_summary,
    candidates_file_for,
    is_page_overview,
    load_json,
    selected_candidates_by_page,
)


ANNOTATION_DIR_NAME = "prototype-annotator"
LEGACY_ANNOTATION_DIR_NAME = ".prototype-annotations"


def annotation_root(target: Path) -> Path:
    return target.parent if target.is_file() else target


def default_annotations(target: Path) -> Path:
    root = annotation_root(target)
    preferred = root / ANNOTATION_DIR_NAME / "annotations.json"
    if preferred.exists():
        return preferred
    legacy = root / LEGACY_ANNOTATION_DIR_NAME / "annotations.json"
    if legacy.exists():
        return legacy
    return preferred


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise SystemExit(f"Invalid JSON in {path}: {err}") from err


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def value_or_missing(value) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value if str(item).strip()) or "未提供"
    text = str(value or "").strip()
    return text or "未提供"


def table_cell(value) -> str:
    return value_or_missing(value).replace("|", "\\|").replace("\n", "<br>")


def strip_markdown(value: str) -> str:
    text = re.sub(r"```.*?```", " ", value or "", flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"^[#>\-*+\s]+", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip()


def summary_for(ann: dict, limit: int = 72) -> str:
    content = strip_markdown(str(ann.get("contentMarkdown") or ""))
    if not content:
        content = str(ann.get("title") or "")
    if len(content) <= limit:
        return content
    return content[: limit - 1] + "…"


def type_for(ann: dict) -> str:
    return str(ann.get("annotationType") or ann.get("kind") or ann.get("dimension") or "未提供")


def page_label(page: dict) -> str:
    return str(page.get("title") or page.get("name") or page.get("pageKey") or "未命名页面")


def annotations_by_page(data: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for ann in data.get("annotations", []):
        grouped.setdefault(str(ann.get("pageKey") or "未分组"), []).append(ann)
    return grouped


def surfaces_by_page(data: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for surface in data.get("surfaces") or []:
        if not isinstance(surface, dict):
            continue
        grouped.setdefault(str(surface.get("pageKey") or "未分组"), []).append(surface)
    return grouped


def group_page_annotations(page_key: str, annotations: list[dict], surfaces: list[dict]) -> tuple[list[dict], dict[str, list[dict]]]:
    surface_ids = {str(surface.get("id") or "") for surface in surfaces}
    page_items: list[dict] = []
    surface_items: dict[str, list[dict]] = {surface_id: [] for surface_id in surface_ids if surface_id}
    for ann in annotations:
        surface_id = str(ann.get("surfaceId") or "").strip()
        if surface_id and surface_id in surface_items:
            surface_items[surface_id].append(ann)
        else:
            page_items.append(ann)
    return page_items, surface_items


def display_numbers_by_id(data: dict) -> dict[str, int]:
    result: dict[str, int] = {}
    for _page_key, annotations in annotations_by_page(data).items():
        ordered = sorted(
            annotations,
            key=lambda ann: (int(ann.get("order") or 0), str(ann.get("id") or "")),
        )
        for index, ann in enumerate(ordered, start=1):
            ann_id = str(ann.get("id") or "")
            if ann_id:
                result[ann_id] = index
    return result


def render_annotation_detail(ann: dict, display_no: int | None = None) -> list[str]:
    source = ann.get("source") if isinstance(ann.get("source"), dict) else {}
    topics = ann.get("topics") if isinstance(ann.get("topics"), list) else []
    related = []
    for field in ("nextActions", "dependencies", "risks", "openQuestions"):
        values = ann.get(field) if isinstance(ann.get(field), list) else []
        related.extend(str(item) for item in values if str(item).strip())
    return [
        f"#### {value_or_missing(display_no)}. {value_or_missing(ann.get('title'))}",
        "",
        f"- 稳定ID：{value_or_missing(ann.get('id'))}",
        f"- 标注类型：{value_or_missing(ann.get('annotationType'))}",
        f"- 原有类型：{value_or_missing(ann.get('kind'))}",
        f"- 维度：{value_or_missing(ann.get('dimension'))}",
        f"- 主题：{value_or_missing(topics)}",
        f"- 二级界面：{value_or_missing(ann.get('surfaceId'))}",
        f"- 未打开时展示：{value_or_missing(ann.get('displayWhenClosed'))}",
        f"- 摘要：{summary_for(ann)}",
        f"- 关联：{value_or_missing(related)}",
        f"- 来源：{value_or_missing(source.get('type'))} / {value_or_missing(source.get('ref'))}",
        "",
        "详情：",
        "",
        str(ann.get("contentMarkdown") or "未提供"),
        "",
    ]


def render_report(data: dict) -> str:
    profile = data.get("productProfile") if isinstance(data.get("productProfile"), dict) else {}
    pages = data.get("pages") if isinstance(data.get("pages"), list) else []
    pages_by_key = {str(page.get("pageKey") or ""): page for page in pages}
    grouped = annotations_by_page(data)
    display_numbers = display_numbers_by_id(data)
    lines: list[str] = [
        "# 原型标注说明文档",
        "",
        "## 1. 产品信息",
        "",
        f"- 产品名称：{value_or_missing(profile.get('productName'))}",
        f"- 产品类型：{value_or_missing(profile.get('productType'))}",
        f"- 产品形态：{value_or_missing(profile.get('productForms'))}",
        f"- 主要用户：{value_or_missing(profile.get('primaryUsers'))}",
        f"- 标注模式：{value_or_missing(profile.get('annotationMode'))}",
        f"- 启用标注类型：{value_or_missing(profile.get('enabledAnnotationTypes'))}",
        "",
        "## 2. 页面清单",
        "",
        "| 页面 | 页面名称 | 页面类型 | 路径 | 角色 |",
        "|---|---|---|---|---|",
    ]
    for page in pages:
        lines.append(
            "| "
            + " | ".join(
                [
                    table_cell(page.get("pageKey")),
                    table_cell(page_label(page)),
                    table_cell(page.get("type")),
                    table_cell(page.get("path") or page.get("route")),
                    table_cell(page.get("role")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 3. 标注总览",
            "",
            "| 序号 | 标注ID | 类型 | 标题 | 页面 | 摘要 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for ann in data.get("annotations", []):
        page = pages_by_key.get(str(ann.get("pageKey") or ""), {})
        lines.append(
            "| "
            + " | ".join(
                [
                    table_cell(display_numbers.get(str(ann.get("id") or ""))),
                    table_cell(ann.get("id")),
                    table_cell(type_for(ann)),
                    table_cell(ann.get("title")),
                    table_cell(page_label(page) if page else ann.get("pageKey")),
                    table_cell(summary_for(ann)),
                ]
            )
            + " |"
        )
    surface_grouped = surfaces_by_page(data)
    lines.extend(["", "## 4. 页面级标注详情", ""])
    for page in pages:
        key = str(page.get("pageKey") or "")
        page_items, surface_items = group_page_annotations(key, grouped.get(key, []), surface_grouped.get(key, []))
        lines.extend([f"### 页面：{page_label(page)}", ""])
        if page_items:
            lines.extend(["#### 当前页面", ""])
            for ann in page_items:
                lines.extend(render_annotation_detail(ann, display_numbers.get(str(ann.get("id") or ""))))
        for surface in surface_grouped.get(key, []):
            surface_id = str(surface.get("id") or "")
            items = surface_items.get(surface_id, [])
            if not items:
                continue
            lines.extend([
                f"#### 二级界面：{value_or_missing(surface.get('name') or surface_id)}",
                "",
                f"- surfaceId：{value_or_missing(surface_id)}",
                f"- 类型：{value_or_missing(surface.get('type'))}",
                f"- 入口：{value_or_missing(surface.get('triggerSelector'))}",
                "",
            ])
            for ann in items:
                lines.extend(render_annotation_detail(ann, display_numbers.get(str(ann.get("id") or ""))))
    all_open_questions = [
        str(item)
        for ann in data.get("annotations", [])
        for item in (ann.get("openQuestions") if isinstance(ann.get("openQuestions"), list) else [])
        if str(item).strip()
    ]
    all_risks = [
        str(item)
        for ann in data.get("annotations", [])
        for item in (ann.get("risks") if isinstance(ann.get("risks"), list) else [])
        if str(item).strip()
    ]
    all_dependencies = [
        str(item)
        for ann in data.get("annotations", [])
        for item in (ann.get("dependencies") if isinstance(ann.get("dependencies"), list) else [])
        if str(item).strip()
    ]
    lines.extend(["## 5. 待确认问题", ""])
    lines.extend([f"- {item}" for item in all_open_questions] or ["- 未提供"])
    lines.extend(["", "## 6. 风险与依赖", ""])
    lines.extend([f"- {item}" for item in [*all_risks, *all_dependencies]] or ["- 未提供"])
    return "\n".join(lines)


def checkbox(done: bool) -> str:
    return "- [x]" if done else "- [ ]"


def profile_text(data: dict) -> str:
    profile = data.get("productProfile") if isinstance(data.get("productProfile"), dict) else {}
    parts = [
        str(profile.get("productType") or ""),
        " ".join(str(item) for item in profile.get("productForms") or []),
    ]
    return " ".join(parts).lower()


def render_checklist(data: dict, candidates: dict | None = None) -> str:
    pages = data.get("pages") if isinstance(data.get("pages"), list) else []
    annotations = data.get("annotations") if isinstance(data.get("annotations"), list) else []
    grouped = annotations_by_page(data)
    selected_by_page = selected_candidates_by_page(candidates or {"pages": []})
    summary = audit_summary(data, candidates)
    text = profile_text(data)
    annotation_types = {str(ann.get("annotationType") or "") for ann in annotations}

    type_counts: dict[str, int] = {}
    page_p: set[str] = set()
    has_primary = False
    has_flow = False
    has_state = False
    has_permission = False
    has_async_feedback = False
    has_empty_state = False
    for ann in annotations:
        ann_type = type_for(ann)
        type_counts[ann_type] = type_counts.get(ann_type, 0) + 1
        if ann.get("annotationType") == "P":
            page_p.add(str(ann.get("pageKey") or ""))
        content = str(ann.get("contentMarkdown") or "")
        if ann.get("annotationType") in {"A", "J"} or ann.get("dimension") == "Primary action":
            has_primary = True
        if "页面流转" in content or ann.get("annotationType") == "J":
            has_flow = True
        if "状态与异常" in content or ann.get("annotationType") in {"S", "FALLBACK"}:
            has_state = True
        if ann.get("annotationType") in {"PERM", "ROLE"} or "权限" in content:
            has_permission = True
        if any(token in content for token in ["loading", "成功", "失败", "Toast", "toast"]):
            has_async_feedback = True
        if any(token in content for token in ["空态", "暂无数据", "无匹配", "空状态"]):
            has_empty_state = True

    missing_p = [str(page.get("pageKey") or "") for page in pages if str(page.get("pageKey") or "") not in page_p]
    surfaces = [surface for surface in (data.get("surfaces") or []) if isinstance(surface, dict)]
    surfaces_by_key = surfaces_by_page(data)
    missing_surface_coverage: list[str] = []
    for page_key, page_surfaces in surfaces_by_key.items():
        page_annotations = grouped.get(page_key, [])
        for surface in page_surfaces:
            surface_id = str(surface.get("id") or "")
            related = [ann for ann in page_annotations if str(ann.get("surfaceId") or "") == surface_id]
            has_trigger = bool(str(surface.get("triggerSelector") or "").strip()) or any(
                str(ann.get("fallbackAnchorSelector") or "").strip() for ann in related
            )
            has_overview = any(
                ann.get("dimension") in {"Surface overview", "Surface trigger"}
                or "overview" in str(ann.get("dimension") or "").lower()
                or "入口" in str(ann.get("title") or "")
                for ann in related
            )
            if not has_trigger or not has_overview:
                missing_surface_coverage.append(surface_id)
    pages_with_key_action = [
        page_key
        for page_key, items in grouped.items()
        if any(not is_page_overview(ann) and ann.get("annotationType") in {"A", "WF", "PERM", "R", "FILTER"} for ann in items)
    ]
    type_summary = "、".join(f"{key}:{value}" for key, value in sorted(type_counts.items())) or "无"
    only_overview = summary.get("onlyOverviewPages") or []
    unpromoted = summary.get("unpromotedCandidates") or []

    lines = [
        "# 原型标注检查清单",
        "",
        "## 当前标注统计",
        "",
        f"- 页面数量：{len(pages)}",
        f"- 标注数量：{len(annotations)}",
        f"- 标注模式：{annotation_mode(data)}",
        f"- 标注类型统计：{type_summary}",
        f"- 缺少页面级说明标注的页面：{value_or_missing(missing_p)}",
        f"- 仅页面介绍的页面：{value_or_missing(only_overview)}",
        f"- 未转正候选：{len(unpromoted)}",
        f"- 粗粒度锚点：{len(summary.get('coarseAnchorIds') or [])}",
        f"- review.required 绕过：{len(summary.get('reviewBypassIds') or [])}",
        f"- 二级界面数量：{len(surfaces)}",
        f"- 覆盖不完整的二级界面：{value_or_missing(missing_surface_coverage)}",
        "",
        "## 1. 页面覆盖检查",
        "",
        f"{checkbox(not missing_p)} 每个页面都有页面级说明标注",
        f"{checkbox(len(pages_with_key_action) == len(pages) or not pages)} 每个页面至少有一个关键操作标注",
        f"{checkbox(has_flow)} 每个页面的主路径跳转已标注",
        f"{checkbox(not surfaces or not missing_surface_coverage)} 每个二级界面至少有入口与概览标注",
        "",
        "## 2. 交互检查",
        "",
        f"{checkbox(has_primary)} 主按钮已标注操作结果",
        f"{checkbox(has_async_feedback)} 异步操作已标注 loading / 成功 / 失败反馈",
        f"{checkbox(has_state)} 失败状态已标注",
        f"{checkbox(has_empty_state)} 空状态已标注",
        "",
        "## 3. 状态与规则检查",
        "",
        f"{checkbox(has_state)} 关键状态已标注",
        f"{checkbox(any(ann.get('annotationType') in {'R', 'FILTER'} or '字段规则' in str(ann.get('contentMarkdown') or '') for ann in annotations))} 关键规则已标注",
        f"{checkbox(has_permission)} 权限相关操作已标注",
        f"{checkbox(has_state or any('异常' in str(ann.get('contentMarkdown') or '') for ann in annotations))} 业务规则异常分支已标注",
        "",
        "## 4. 产品形态扩展检查",
        "",
        f"{checkbox('ai' in text and bool(annotation_types & {'AI', 'HITL', 'FALLBACK'}))} AI 产品已标注 AI 输入 / 输出 / 人工确认 / 失败兜底",
        f"{checkbox(any(token in text for token in ['data', 'bi', 'dashboard', 'analytics', '数据', '看板', '指标']) and bool(annotation_types & {'METRIC', 'SOURCE', 'DATA'}))} 数据产品已标注指标口径 / 数据来源 / 刷新频率",
        f"{checkbox(any(token in text for token in ['saas', 'multi_tenant', '多租户']) and bool(annotation_types & {'ROLE', 'PLAN', 'TENANT'}))} SaaS 产品已标注角色权限 / 套餐权益 / 租户隔离",
        f"{checkbox(any(token in text for token in ['c端', 'app', '小程序', '转化']) and bool(annotation_types & {'CV', 'TRACK'}))} C端产品已标注关键转化节点 / 埋点事件",
        f"{checkbox(any(token in text for token in ['enterprise', 'admin', 'workflow', 'approval', 'b端', '企业', '后台', '审批']) and bool(annotation_types & {'PERM', 'WF', 'R', 'S'}))} B端产品已标注流程 / 权限 / 状态 / 业务规则",
        "",
        "## 5. 研发交付缺口",
        "",
    ]
    if unpromoted:
        for item in unpromoted[:12]:
            lines.append(f"- [ ] 候选 `{item.get('candidateId')}`（{item.get('pageKey')} / {item.get('label')}）尚未转正")
    else:
        lines.append("- [x] 所有需转正的候选点均已落入 annotations.json")
    if summary.get("coarseAnchorIds"):
        lines.append(f"- [ ] 以下标注仍使用粗粒度锚点：{', '.join(summary['coarseAnchorIds'][:8])}")
    else:
        lines.append("- [x] 非页面介绍标注未使用 main/h1/body 级粗锚点")
    if summary.get("reviewBypassIds"):
        lines.append(f"- [ ] 以下 AI 标注绕过了 review.required：{', '.join(summary['reviewBypassIds'][:8])}")
    else:
        lines.append("- [x] AI 标注均保留 review.required=true")
    lines.extend(
        [
            "",
            "## 6. 待确认项",
            "",
            "- [ ] 标注内容是否准确",
            "- [ ] 标注是否过多",
            "- [ ] 标注是否覆盖关键交互",
            "- [ ] 是否存在未解释的按钮",
            "- [ ] 是否存在未说明的状态",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Prototype Annotator Markdown reports.")
    parser.add_argument("prototype_path", nargs="?", help="HTML file or static directory. Used to locate prototype-annotator/annotations.json by default.")
    parser.add_argument("--annotations", help="Path to annotations.json")
    parser.add_argument("--output", help="Output annotation-report.md path")
    parser.add_argument("--checklist-output", help="Output annotation-checklist.md path")
    args = parser.parse_args()

    if args.annotations:
        annotations_path = Path(args.annotations).resolve()
        base_dir = annotations_path.parent
    elif args.prototype_path:
        target = Path(args.prototype_path).resolve()
        annotations_path = default_annotations(target)
        base_dir = annotation_root(target)
    else:
        parser.error("Provide a prototype_path or --annotations")

    if not annotations_path.exists():
        parser.error(f"Annotation file does not exist: {annotations_path}")

    report_path = Path(args.output).resolve() if args.output else base_dir / "annotation-report.md"
    checklist_path = Path(args.checklist_output).resolve() if args.checklist_output else base_dir / "annotation-checklist.md"
    data = read_json(annotations_path)
    target = Path(args.prototype_path).resolve() if args.prototype_path else annotation_root(annotations_path)
    candidates_path = candidates_file_for(target)
    candidates = read_json(candidates_path) if candidates_path.exists() else None
    write_text(report_path, render_report(data))
    write_text(checklist_path, render_checklist(data, candidates))
    print(f"Wrote annotation report: {report_path}")
    print(f"Wrote annotation checklist: {checklist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
