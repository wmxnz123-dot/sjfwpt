#!/usr/bin/env python3
"""Build explainable annotation candidates from page-map and optional docs."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from annotation_types import ANNOTATION_TYPE_BY_DIMENSION, TOPICS_BY_DIMENSION


ANNOTATION_DIR_NAME = "prototype-annotator"
LEGACY_ANNOTATION_DIR_NAME = ".prototype-annotations"
SPEC_DIRS = ("prototype-specs/current", "src/page-specs/current")

PRIMARY_ACTION_RE = re.compile(
    r"提交|保存|创建|新建|新增|编辑|修改|生成|运行|执行|发布|删除|导入|导出|上传|下载|确认|审批|审核|通过|拒绝|启用|停用|"
    r"\bsubmit\b|\bsave\b|\bcreate\b|\bgenerate\b|\brun\b|\bpublish\b|\bdelete\b|"
    r"\bimport\b|\bexport\b|\bupload\b|\bdownload\b|\bconfirm\b|\bapprove\b|\breject\b|\bedit\b|\bupdate\b",
    re.I,
)
FILTER_RE = re.compile(r"搜索|筛选|查询|过滤|filter|search|query", re.I)
SEARCH_PLACEHOLDER_RE = re.compile(r"搜索|请输入关键词|search", re.I)
STATE_RE = re.compile(r"状态|加载|失败|错误|异常|为空|无数据|无权限|禁用|生成中|处理中|loading|failed|error|empty|disabled|permission", re.I)
AI_RE = re.compile(r"AI|模型|提示词|Prompt|生成|重新生成|智能|assistant|model|prompt", re.I)
RISK_LABEL_RE = re.compile(
    r"删除|移除|停用|禁用|驳回|清空|批量删除|取消授权|重置密钥|授权|下架|"
    r"\bdelete\b|\bdisable\b|\breject\b|\bclear\b",
    re.I,
)
JS_ROW_ACTION_FN_RE = re.compile(
    r"deleteApp|exportCredentials|openCredentials|editApp|toggleApp|handleBatchDelete|batchDelete|resetKey|revoke",
    re.I,
)
STATUS_FILTER_RE = re.compile(r"全部状态|状态筛选|启用|停用", re.I)
USER_PROFILE_RE = re.compile(r"^[\u4e00-\u9fff]{1,4}\s*[\u4e00-\u9fff]{1,8}$|用户头像|个人资料|张明|Avatar|Profile")
ROW_ACTION_TEXT_RE = re.compile(
    r"编辑|删除|启用|停用|授权|下载|查看|详情|重置|密钥|edit|delete|enable|disable|download|authorize|view",
    re.I,
)
COMMON_NAV_RE = re.compile(
    r"^(首页|主页|仪表盘|控制台|工作台|设置|配置|帮助|文档|通知|消息|个人中心|用户中心|账号|退出|登录|注册|返回|菜单|Home|Dashboard|Console|Settings|Help|Docs|Profile|Account|Logout|Login|Menu|Toggle Sidebar)$",
    re.I,
)
COMMON_CHROME_RE = re.compile(
    r"^(搜索|全局搜索|Search)(?:\s|[:：]|$)|用户头像|个人资料|用户菜单|通知|设置|User menu|Profile menu|Account menu|Avatar|Notifications?|Settings?",
    re.I,
)
TYPE_PRIORITY = {
    "AI": 0,
    "R": 1,
    "A": 2,
    "J": 3,
    "S": 4,
    "PERM": 5,
    "DATA": 6,
    "C": 7,
    "E": 8,
    "P": 9,
}
AI_REGION_RE = re.compile(r"AI\s*识别结果|AI\s*结果|智能|模型|提示词|Prompt|生成结果|自动化|assistant|model|prompt", re.I)

SELECTED_SCORE_THRESHOLD = 64
COARSE_SELECTORS = {"main", "h1", "h2", "h3", "body"}
TEMPLATE_LITERAL_RE = re.compile(r"\$\{|\{\{|\}\}|\.map\s*\(|columns\.map|data\.map")
ADMIN_ROUTE_TOKENS = ("/admin", "management", "/me/", "edit", "new", "review", "market", "resource", "case", "scene")
DIMENSION_LIMITS = {
    "Page overview": 1,
    "Table row actions": 1,
    "Primary action": 2,
    "Form and validation": 3,
    "Table and list": 3,
    "State and exception": 2,
    "Flow and navigation": 1,
    "Permission and risk": 2,
    "Data explanation": 2,
    "AI and automation": 2,
    "Context": 1,
    "Surface trigger": 2,
    "Surface overview": 2,
    "Surface field": 6,
    "Surface action": 4,
    "Surface confirm": 2,
}
SURFACE_TRIGGER_RE = re.compile(
    r"新建|创建|新增|编辑|查看详情|授权|删除|驳回|通过|上架|下架|配置|设置|分配|绑定|解绑|重置|下载|"
    r"\bcreate\b|\bedit\b|\bdelete\b|\bconfigure\b|\bsettings\b",
    re.I,
)
SURFACE_ACTION_RE = re.compile(
    r"保存|取消|确认|关闭|提交|下一步|完成|知道了|"
    r"\bsave\b|\bcancel\b|\bconfirm\b|\bclose\b|\bsubmit\b",
    re.I,
)
TRANSIENT_FEEDBACK_RE = re.compile(
    r"toast|message|notify|notification-popup|\.ant-message|\.el-message|\.van-toast|success-toast",
    re.I,
)
TECHNICAL_SURFACE_NAME_RE = re.compile(
    r"^(?:surface-)?(?:drawer|modal|dialog|popover|dropdown|confirm|popup)(?:[-_\w]*|\d*)$",
    re.I,
)

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def annotation_root(target: Path) -> Path:
    return target.parent if target.is_file() else target


def default_page_map(target: Path) -> Path:
    preferred = annotation_root(target) / ANNOTATION_DIR_NAME / "page-map.json"
    if preferred.exists():
        return preferred
    legacy = annotation_root(target) / LEGACY_ANNOTATION_DIR_NAME / "page-map.json"
    if legacy.exists():
        return legacy
    return preferred


def default_output(target: Path) -> Path:
    return annotation_root(target) / ANNOTATION_DIR_NAME / "annotation-candidates.json"


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


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_surface_name_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value or "").strip("-").lower()


def normalize_text_values(value) -> list[str]:
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(normalize_text_values(item))
        return items
    text = normalize(str(value or ""))
    return [text] if text else []


def is_technical_surface_name(surface: dict) -> bool:
    name = normalize(str(surface.get("name") or ""))
    if not name:
        return True
    surface_id = str(surface.get("id") or "")
    if name == surface_id or normalize_surface_name_key(name) == normalize_surface_name_key(surface_id):
        return True
    if TECHNICAL_SURFACE_NAME_RE.match(name):
        return True
    if re.fullmatch(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+){1,}", name, re.I):
        return True
    return False


def surface_display_name(surface: dict) -> str:
    name = normalize(str(surface.get("name") or ""))
    if name and not is_technical_surface_name(surface):
        return name
    for key in ("titleText", "activeTitle", "textIncludes", "matchText", "stateText", "expectedText"):
        values = normalize_text_values(surface.get(key))
        if values:
            return values[0]
    return name or str(surface.get("id") or "二级界面")


def normalize_key(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip().lower()


def normalize_selector_key(value: str) -> str:
    return normalize_key(str(value or "").replace("'", '"'))


def doc_paths(root: Path, docs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for item in docs:
        path = Path(item).resolve()
        if path.is_file():
            paths.append(path)
        elif path.is_dir():
            paths.extend(sorted(path.rglob("*.md")))
            paths.extend(sorted(path.rglob("*.txt")))
    for rel in SPEC_DIRS:
        spec_dir = root / rel
        if spec_dir.is_dir():
            paths.extend(sorted(spec_dir.glob("*.md")))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def load_docs(paths: list[Path], limit_per_doc: int = 20000) -> list[dict]:
    docs: list[dict] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:limit_per_doc]
        except OSError:
            continue
        if text.strip():
            docs.append({"path": str(path), "text": text})
    return docs


def text_tokens(text: str) -> list[str]:
    raw = normalize(text)
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{2,}", raw)
    return [token.lower() for token in tokens[:12]]


def doc_evidence(element_text: str, docs: list[dict]) -> tuple[list[str], str]:
    tokens = text_tokens(element_text)
    evidence: list[str] = []
    source_type = "prototype"
    for doc in docs:
        lower = doc["text"].lower()
        matched = [token for token in tokens if token and token in lower]
        if not matched:
            continue
        path = doc["path"]
        if "prototype-specs/current" in path or "src/page-specs/current" in path:
            source_type = "page-spec"
        else:
            source_type = "mixed" if source_type == "page-spec" else "prd"
        evidence.append(f"文档匹配：{Path(path).name} -> {', '.join(matched[:4])}")
        if len(evidence) >= 3:
            break
    return evidence, source_type


def attrs_text(attrs: dict) -> str:
    return " ".join(str(value) for value in attrs.values() if value)


def is_template_artifact_text(value: str) -> bool:
    return bool(TEMPLATE_LITERAL_RE.search(value or ""))


def is_template_artifact_selector(selector: str, attrs: dict) -> bool:
    selector = selector or ""
    onclick = str(attrs.get("onclick") or "")
    return "${" in selector or "${" in onclick or is_template_artifact_text(selector) or is_template_artifact_text(onclick)


def is_dismiss_interaction(attrs: dict) -> bool:
    onclick = str(attrs.get("onclick") or "")
    return "parentElement.remove" in onclick or "parentElement?.remove" in onclick


def is_risk_action(visible: str, attrs: dict) -> bool:
    if is_dismiss_interaction(attrs):
        return False
    title = str(attrs.get("title") or "")
    onclick = str(attrs.get("onclick") or "")
    label = normalize(f"{visible} {title}")
    if label and RISK_LABEL_RE.search(label):
        return True
    if onclick and RISK_LABEL_RE.search(onclick):
        return True
    return False


def is_status_filter_element(tag: str, visible: str, attrs: dict) -> bool:
    if tag != "select":
        return False
    element_id = str(attrs.get("id") or "")
    if "status" in element_id.lower() or "filter" in element_id.lower():
        return True
    return bool(STATUS_FILTER_RE.search(visible))


def is_coarse_selector(selector: str) -> bool:
    return (selector or "").strip().lower() in COARSE_SELECTORS


def is_dense_page(page: dict) -> bool:
    route = str(page.get("route") or page.get("path") or "").lower()
    return any(token in route for token in ADMIN_ROUTE_TOKENS)


def selector_quality(selector: str, strategy: str | None) -> dict:
    selector = selector or ""
    strategy = strategy or ""
    issues: list[str] = []
    if is_coarse_selector(selector) and strategy == "tag":
        level = "coarse"
        issues.append("区域级 tag 选择器仅适合页面介绍，元素级标注应改用 id/data-ann/按钮级 selector")
    elif strategy in {"id", "data", "aria", "name", "handler", "href", "placeholder"}:
        level = "stable"
    elif ":nth-of-type" in selector or re.search(r"(?:^|>)\s*(?:div|span)(?:\s|>|:|$)", selector):
        level = "fragile"
        issues.append("结构路径选择器容易随布局变化失效，建议补充 data-ann 或 data-testid")
    elif selector:
        level = "acceptable"
    else:
        level = "missing"
        issues.append("缺少 selector")
    return {"level": level, "issues": issues}


def topics_for(kind: str, dimension: str, reason: str = "") -> list[str]:
    topics = list(TOPICS_BY_DIMENSION.get(dimension) or [])
    if kind == "form" and "field-rule" not in topics:
        topics.append("field-rule")
    if kind == "state" and "state" not in topics:
        topics.append("state")
    if kind == "flow" and "flow" not in topics:
        topics.append("flow")
    if kind == "permission" and "risk" not in topics:
        topics.append("risk")
    if kind == "ai" and "ai" not in topics:
        topics.append("ai")
    if re.search(r"异常|失败|错误|重试|error|failed|retry", reason or "", re.I) and "exception" not in topics:
        topics.append("exception")
    if re.search(r"依赖|前置|后置|权限|角色|dependency|permission|role", reason or "", re.I) and "dependency" not in topics:
        topics.append("dependency")
    return topics or ["business"]


def annotation_type_for(kind: str, dimension: str) -> str:
    if dimension == "Page overview":
        return "P"
    if dimension == "Table row actions":
        return "A"
    return ANNOTATION_TYPE_BY_DIMENSION.get(dimension) or "C"


def is_common_chrome(element: dict, visible: str, selector: str, attrs: dict) -> bool:
    tag = str(element.get("tag") or "")
    combined = normalize(" ".join([visible, attrs_text(attrs), selector]))
    shell_hint = re.search(r"header|nav|sidebar|side-nav|sidenav|topbar|toolbar|menu|breadcrumb", selector, re.I)
    if COMMON_NAV_RE.fullmatch(visible):
        return True
    if USER_PROFILE_RE.search(visible) and (shell_hint or tag in {"form", "button", "a", "div"}):
        return True
    if COMMON_CHROME_RE.search(combined) and (shell_hint or tag in {"header", "nav", "aside"}):
        return True
    if shell_hint and tag in {"form", "input"} and FILTER_RE.search(combined) and not attrs.get("id", "").startswith("search"):
        return True
    if tag == "a" and shell_hint and re.search(r"Enterprise|平台|Portal|Logo|品牌", visible, re.I):
        return True
    placeholder = str(attrs.get("placeholder") or "")
    if tag in {"input", "textarea"} and SEARCH_PLACEHOLDER_RE.search(placeholder) and shell_hint:
        return True
    return False


def infer_trigger_selector(surface: dict, elements: list[dict]) -> str | None:
    if surface.get("triggerSelector"):
        return str(surface.get("triggerSelector"))
    open_selector = str(surface.get("openSelector") or "")
    match = re.search(r'data-ann=(?:"|\')([^"\']+)(?:"|\')', open_selector)
    if not match:
        return None
    ann = match.group(1)
    trigger_candidates = [ann]
    for suffix in ("-drawer", "-modal", "-confirm-modal", "-popover", "-dropdown"):
        if ann.endswith(suffix):
            trigger_candidates.insert(0, ann[: -len(suffix)])
    element_anns = {
        str((element.get("attrs") or {}).get("data-ann") or "")
        for element in elements
        if isinstance(element.get("attrs"), dict)
    }
    for trigger_ann in trigger_candidates:
        if trigger_ann in element_anns:
            return f'[data-ann="{trigger_ann}"]'
    surface_id = str(surface.get("id") or "").lower()
    if "delete" in surface_id or str(surface.get("type") or "") == "confirm":
        for ann in sorted(element_anns):
            if ann and "delete" in ann.lower():
                return f'[data-ann="{ann}"]'
    if "create" in surface_id or "new" in surface_id:
        for ann in sorted(element_anns):
            if ann and ("create" in ann.lower() or "new" in ann.lower()):
                return f'[data-ann="{ann}"]'
    return None


def selector_strategy_for(selector: str) -> str:
    selector = (selector or "").strip()
    if selector.startswith("#"):
        return "id"
    if "[data-" in selector:
        return "data"
    if "aria-label" in selector:
        return "aria"
    if ":nth-of-type" in selector or ">" in selector:
        return "path"
    return "text" if selector else "path"


def surface_display_fields(surface: dict) -> dict:
    trigger = str(surface.get("triggerSelector") or "").strip()
    if trigger:
        strategy = selector_strategy_for(trigger)
        return {
            "selector": trigger,
            "strategy": strategy,
            "displayWhenClosed": "on-trigger",
            "fallbackAnchorSelector": trigger,
            "selectorQuality": selector_quality(trigger, strategy),
        }
    open_selector = str(surface.get("openSelector") or "").strip() or "body"
    strategy = selector_strategy_for(open_selector)
    return {
        "selector": open_selector,
        "strategy": strategy,
        "displayWhenClosed": "sidebar-only",
        "fallbackAnchorSelector": None,
        "selectorQuality": selector_quality(open_selector, strategy),
    }


def enrich_page_surfaces(page: dict, surfaces: list[dict]) -> list[dict]:
    elements = page.get("elements") if isinstance(page.get("elements"), list) else []
    enriched: list[dict] = []
    for surface in surfaces:
        copy = dict(surface)
        trigger = infer_trigger_selector(copy, elements)
        if trigger:
            copy["triggerSelector"] = trigger
        enriched.append(copy)
    return enriched


def surfaces_for_page(page_map: dict, page: dict) -> list[dict]:
    page_key = str(page.get("pageKey") or "")
    surfaces: list[dict] = []
    seen: set[str] = set()
    for source in (page_map.get("surfaces") or [], page.get("surfaces") or []):
        if not isinstance(source, list):
            continue
        for surface in source:
            if not isinstance(surface, dict):
                continue
            surface_id = str(surface.get("id") or "")
            if not surface_id or surface.get("pageKey") != page_key or surface_id in seen:
                continue
            seen.add(surface_id)
            surfaces.append(surface)
    return enrich_page_surfaces(page, surfaces)


def selectors_equivalent(left: str, right: str) -> bool:
    return normalize_selector_key(left) == normalize_selector_key(right)


def is_transient_feedback_element(element: dict) -> bool:
    selector = str(element.get("selector") or "")
    attrs = element.get("attrs") if isinstance(element.get("attrs"), dict) else {}
    combined = normalize(" ".join([selector, attrs_text(attrs), str(element.get("text") or "")]))
    if TRANSIENT_FEEDBACK_RE.search(combined):
        return True
    if str(attrs.get("data-ann") or "").lower().endswith("toast"):
        return True
    surface_id = str(element.get("surfaceId") or "")
    if surface_id and re.search(r"toast|message", surface_id, re.I):
        return True
    return False


def surface_for_trigger(element: dict, surfaces: list[dict]) -> dict | None:
    selector = str(element.get("selector") or "")
    for surface in surfaces:
        trigger = str(surface.get("triggerSelector") or "")
        if trigger and selectors_equivalent(selector, trigger):
            return surface
    return None


def classify_surface_element(element: dict, surface: dict, docs: list[dict]) -> dict:
    tag = str(element.get("tag") or "")
    visible = normalize(str(element.get("text") or ""))
    attrs = element.get("attrs") if isinstance(element.get("attrs"), dict) else {}
    combined = normalize(" ".join([visible, attrs_text(attrs), tag]))
    evidence = []
    if visible:
        evidence.append(f"页面文本：{visible[:80]}")
    if element.get("selector"):
        evidence.append(f"selector：{element.get('selector')}")
    evidence.append(f"二级界面：{surface_display_name(surface)}")
    matched_docs, source_type = doc_evidence(combined, docs)
    evidence.extend(matched_docs)

    surface_type = str(surface.get("type") or "modal")
    scan_source = str(surface.get("scanSource") or "")
    needs_plan = scan_source == "static-inferred" and not element.get("visible", True)

    if tag in {"button", "a"} and SURFACE_ACTION_RE.search(combined):
        dimension = "Surface confirm" if surface_type == "confirm" else "Surface action"
        return {
            "kind": "interaction",
            "dimension": dimension,
            "priority": "high" if surface_type == "confirm" else "medium",
            "score": 88 if surface_type == "confirm" else 82,
            "reason": "二级界面内部操作，适合说明提交、保存、取消或确认规则",
            "evidence": evidence,
            "selected": not needs_plan,
            "skipReason": "needs-interaction-plan" if needs_plan else None,
            "sourceType": source_type,
            "surfaceId": surface.get("id"),
            "displayWhenClosed": "sidebar-only",
            "fallbackAnchorSelector": surface.get("triggerSelector"),
        }

    if tag in {"input", "select", "textarea", "form"} or element.get("type") == "form":
        return {
            "kind": "form",
            "dimension": "Surface field",
            "priority": "medium",
            "score": 80,
            "reason": "二级界面内部字段，适合说明填写规则、校验和保存影响",
            "evidence": evidence,
            "selected": not needs_plan,
            "skipReason": "needs-interaction-plan" if needs_plan else None,
            "sourceType": source_type,
            "surfaceId": surface.get("id"),
            "displayWhenClosed": "sidebar-only",
            "fallbackAnchorSelector": surface.get("triggerSelector"),
        }

    return {
        "kind": "note",
        "dimension": "Surface field",
        "priority": "low",
        "score": 62,
        "reason": "二级界面内部元素，可作为补充说明候选",
        "evidence": evidence,
        "selected": False,
        "skipReason": "needs-interaction-plan" if needs_plan else "no-business-rule",
        "sourceType": source_type,
        "surfaceId": surface.get("id"),
        "displayWhenClosed": "sidebar-only",
        "fallbackAnchorSelector": surface.get("triggerSelector"),
    }


def classify_surface_trigger(element: dict, surface: dict, docs: list[dict]) -> dict:
    visible = normalize(str(element.get("text") or ""))
    attrs = element.get("attrs") if isinstance(element.get("attrs"), dict) else {}
    combined = normalize(" ".join([visible, attrs_text(attrs)]))
    surface_label = surface_display_name(surface)
    evidence = [f"触发入口：{visible[:80] or surface_label}"]
    if element.get("selector"):
        evidence.append(f"selector：{element.get('selector')}")
    matched_docs, source_type = doc_evidence(combined, docs)
    evidence.extend(matched_docs)
    return {
        "kind": "interaction",
        "dimension": "Surface trigger",
        "priority": "high",
        "score": 92,
        "reason": f"打开{surface_label or '二级界面'}的入口，适合说明打开规则与返回路径",
        "evidence": evidence,
        "selected": True,
        "skipReason": None,
        "sourceType": source_type,
        "surfaceId": surface.get("id"),
        "displayWhenClosed": "on-trigger",
        "fallbackAnchorSelector": element.get("selector") or surface.get("triggerSelector"),
    }


def make_surface_overview_candidate(page: dict, surface: dict, docs: list[dict]) -> dict:
    page_key = str(page.get("pageKey") or "")
    surface_label = surface_display_name(surface)
    evidence = [f"二级界面：{surface_label}"]
    if surface.get("triggerSelector"):
        evidence.append(f"触发入口：{surface.get('triggerSelector')}")
    else:
        evidence.append("未识别到触发入口：需要 interaction-plan 或人工补充 triggerSelector")
    matched_docs, source_type = doc_evidence(surface_label, docs)
    evidence.extend(matched_docs)
    display_fields = surface_display_fields(surface)
    missing_trigger = not str(surface.get("triggerSelector") or "").strip()
    needs_plan = missing_trigger and str(surface.get("scanSource") or "") == "static-inferred"
    return {
        "candidateId": f"CAND-{page_key}-SURF-{surface.get('id')}-OV",
        "pageKey": page_key,
        "pagePath": page.get("path") or "",
        "pageRoute": page.get("route") or "",
        "elementId": None,
        "selector": display_fields["selector"],
        "strategy": display_fields["strategy"],
        "fallbackText": surface_label or "二级界面说明",
        "tag": "surface",
        "type": "surface",
        "kind": "flow",
        "annotationType": "P",
        "topics": list(TOPICS_BY_DIMENSION.get("Surface overview") or ["surface", "business", "flow"]),
        "dimension": "Surface overview",
        "priority": "high",
        "score": 90,
        "reason": "二级界面整体说明，适合描述打开、关闭、职责与状态异常",
        "evidence": evidence[:6],
        "selected": not needs_plan,
        "skipReason": "needs-interaction-plan" if needs_plan else None,
        "source": {"type": source_type, "ref": f"surface:{surface.get('id')}"},
        "selectorQuality": display_fields["selectorQuality"],
        "surfaceId": surface.get("id"),
        "displayWhenClosed": display_fields["displayWhenClosed"],
        "fallbackAnchorSelector": display_fields["fallbackAnchorSelector"],
    }


def attach_feedback_evidence(candidates: list[dict], feedback_items: list[dict]) -> None:
    if not feedback_items:
        return
    action_candidates = [
        item
        for item in candidates
        if item.get("selected")
        and str(item.get("dimension") or "") in {"Primary action", "Surface action", "Surface trigger", "Surface confirm"}
    ]
    for feedback in feedback_items:
        label = normalize(str(feedback.get("text") or "操作反馈"))
        evidence_line = f"短暂反馈：{label}"
        target = None
        for item in reversed(action_candidates):
            if str(item.get("surfaceId") or "") and str(item.get("surfaceId")) == str(feedback.get("surfaceId") or ""):
                target = item
                break
        if not target:
            for item in reversed(action_candidates):
                text = normalize(str(item.get("fallbackText") or ""))
                if re.search(r"保存|提交|删除|确认", text):
                    target = item
                    break
        if not target and action_candidates:
            target = action_candidates[-1]
        if not target:
            continue
        feedback_list = list(target.get("feedbackEvidence") or [])
        if evidence_line not in feedback_list:
            feedback_list.append(evidence_line)
        target["feedbackEvidence"] = feedback_list
        evidence = list(target.get("evidence") or [])
        if evidence_line not in evidence:
            evidence.append(evidence_line)
        target["evidence"] = evidence[:8]


def ensure_surface_structure_candidates(page: dict, surfaces: list[dict], candidates: list[dict], docs: list[dict]) -> None:
    page_key = str(page.get("pageKey") or "")
    existing_overview = {
        str(item.get("surfaceId") or "")
        for item in candidates
        if str(item.get("dimension") or "") == "Surface overview"
    }
    existing_trigger = {
        str(item.get("surfaceId") or "")
        for item in candidates
        if str(item.get("dimension") or "") == "Surface trigger"
    }
    for surface in surfaces:
        surface_id = str(surface.get("id") or "")
        if not surface_id:
            continue
        if surface_id not in existing_overview:
            candidates.append(make_surface_overview_candidate(page, surface, docs))
        if surface_id not in existing_trigger and surface.get("triggerSelector"):
            trigger_candidate = next(
                (
                    item
                    for item in candidates
                    if selectors_equivalent(str(item.get("selector") or ""), str(surface.get("triggerSelector") or ""))
                ),
                None,
            )
            if trigger_candidate:
                trigger_candidate.update(classify_surface_trigger(
                    {
                        "selector": trigger_candidate.get("selector"),
                        "text": trigger_candidate.get("fallbackText"),
                        "attrs": trigger_candidate.get("attrs") or {},
                        "tag": trigger_candidate.get("tag"),
                    },
                    surface,
                    docs,
                ))
                trigger_candidate["dimension"] = "Surface trigger"
                trigger_candidate["annotationType"] = "A"
                trigger_candidate["topics"] = list(TOPICS_BY_DIMENSION.get("Surface trigger") or ["surface", "interaction", "flow"])
                trigger_candidate["selected"] = True
                trigger_candidate["skipReason"] = None
                trigger_candidate["score"] = max(int(trigger_candidate.get("score") or 0), 92)
            else:
                candidates.append(
                    {
                        **make_surface_overview_candidate(page, surface, docs),
                        "candidateId": f"CAND-{page_key}-SURF-{surface_id}-TR",
                        "dimension": "Surface trigger",
                        "annotationType": "A",
                        "topics": list(TOPICS_BY_DIMENSION.get("Surface trigger") or ["surface", "interaction", "flow"]),
                        "title": f"打开{surface_display_name(surface) or '二级界面'}",
                        "fallbackText": f"打开{surface_display_name(surface) or '二级界面'}",
                        "reason": f"打开{surface_display_name(surface) or '二级界面'}的入口，适合说明打开规则与返回路径",
                        "selected": True,
                    }
                )


def classify_element(element: dict, docs: list[dict]) -> dict:
    tag = element.get("tag", "")
    element_type = element.get("type", "element")
    attrs = element.get("attrs") if isinstance(element.get("attrs"), dict) else {}
    selector = str(element.get("selector") or "")
    visible = normalize(str(element.get("text") or ""))
    combined = normalize(" ".join([visible, attrs_text(attrs), tag, element_type]))
    evidence = []
    if visible:
        evidence.append(f"页面文本：{visible[:80]}")
    if element.get("selector"):
        evidence.append(f"selector：{element.get('selector')}")
    matched_docs, source_type = doc_evidence(combined, docs)
    evidence.extend(matched_docs)

    kind = "note"
    dimension = "Context"
    priority = "low"
    score = 0
    reason = ""
    skip_reason = "no-business-rule"
    extra_topics: list[str] = []

    if is_template_artifact_text(visible) or is_template_artifact_selector(selector, attrs):
        return {
            "kind": "note",
            "dimension": "Context",
            "priority": "low",
            "score": 10,
            "reason": "扫描到 JS 模板字面量文本，不能作为稳定业务证据",
            "evidence": evidence,
            "selected": False,
            "skipReason": "scan-artifact",
            "sourceType": source_type,
        }

    if is_dismiss_interaction(attrs):
        return {
            "kind": "note",
            "dimension": "Context",
            "priority": "low",
            "score": 15,
            "reason": "关闭通知或提示的轻量操作，默认不需要单独标注",
            "evidence": evidence,
            "selected": False,
            "skipReason": "low-value-structure",
            "sourceType": source_type,
        }

    if is_common_chrome(element, visible, selector, attrs):
        return {
            "kind": "note",
            "dimension": "Context",
            "priority": "low",
            "score": 20,
            "reason": "公共页眉、全局搜索或导航框架在多页重复出现，默认不作为页面业务标注",
            "evidence": evidence,
            "selected": False,
            "skipReason": "common-chrome",
            "sourceType": source_type,
        }

    if tag in {"button", "a"} or element_type == "interaction" or attrs.get("role") in {"button", "link", "menuitem"}:
        is_table_row_action = "tr:nth-of-type(" in selector and tag in {"button", "a"}
        is_table_row_link = tag == "a" and is_table_row_action
        if is_table_row_action and ROW_ACTION_TEXT_RE.search(visible):
            return {
                "kind": "interaction",
                "dimension": "Table row actions",
                "priority": "medium",
                "score": 55,
                "reason": "表格行级操作，将合并为行级操作组标注",
                "evidence": evidence,
                "selected": False,
                "skipReason": "folded-into-row-action-group",
                "sourceType": source_type,
            }
        is_primary = bool(PRIMARY_ACTION_RE.search(combined)) and not is_table_row_link
        is_risk = is_risk_action(visible, attrs)
        kind = "interaction"
        dimension = "Primary action" if is_primary else "Flow and navigation"
        priority = "high" if is_primary else "medium"
        score = 90 if is_primary else 40
        reason = "关键操作入口" if priority == "high" else "页面跳转或次要操作"
        skip_reason = None if is_primary else "no-business-rule"
        if COMMON_NAV_RE.fullmatch(visible):
            score = min(score, 35)
            skip_reason = "low-value-structure"
            reason = "常规导航或布局操作，默认不需要标注"
        elif not is_primary and matched_docs:
            score = 48
            skip_reason = "no-business-rule"
            reason = "普通页面流转或链接，即使文本命中文档也默认不标注"
        if is_risk:
            kind = "permission"
            dimension = "Permission and risk"
            priority = "high"
            score = max(score, 95)
            reason = "风险操作，需要说明确认、权限或后续影响"
            skip_reason = None

    elif tag in {"input", "select", "textarea", "form"} or element_type == "form":
        kind = "form"
        dimension = "Form and validation"
        is_status_filter = is_status_filter_element(tag, visible, attrs)
        is_search = (
            tag in {"input", "textarea"}
            and (SEARCH_PLACEHOLDER_RE.search(str(attrs.get("placeholder") or "")) or FILTER_RE.search(visible))
        )
        is_filter = is_status_filter or is_search
        if is_status_filter:
            reason = "状态筛选，适合说明筛选条件与列表刷新规则"
            extra_topics.extend(["filter", "state"])
        priority = "high" if tag == "form" or is_filter else "medium"
        score = 72 if tag == "form" or is_filter else 58
        if not is_status_filter:
            reason = "搜索或筛选能力，适合说明查询条件与结果刷新" if is_search else "表单或字段，适合说明输入、默认值、校验或选项来源"
        skip_reason = None if score >= SELECTED_SCORE_THRESHOLD else "no-business-rule"

    elif tag == "table" or element_type == "table":
        if not visible and str(element.get("scanQuality") or "") == "template-literal":
            return {
                "kind": "note",
                "dimension": "Context",
                "priority": "low",
                "score": 15,
                "reason": "JS 动态渲染的空表格壳，缺少稳定列与行级操作证据",
                "evidence": evidence,
                "selected": False,
                "skipReason": "scan-artifact",
                "sourceType": source_type,
            }
        kind = "table"
        dimension = "Table and list"
        priority = "medium"
        score = 70
        reason = "表格或列表区域，适合说明列、分页、空状态或行操作"
        skip_reason = None

    elif tag in {"dialog"} or re.search(r"弹窗|抽屉|侧滑|modal|drawer|dialog", combined, re.I):
        kind = "flow"
        dimension = "Flow and navigation"
        priority = "medium"
        score = 68
        reason = "二级承载面，适合说明打开、关闭和子流程"
        skip_reason = None

    elif (
        FILTER_RE.search(combined)
        and tag in {"input", "textarea", "select", "form"}
        and tag not in {"section", "main", "div", "header", "nav"}
    ):
        kind = "form"
        dimension = "Form and validation"
        priority = "medium"
        score = 68
        reason = "搜索或筛选能力，适合说明查询条件与结果刷新"
        skip_reason = None

    elif tag in {"section", "main", "div"} and element_type == "region" and FILTER_RE.search(combined):
        return {
            "kind": "note",
            "dimension": "Context",
            "priority": "low",
            "score": 25,
            "reason": "营销/介绍区域仅提及搜索能力，不等同于可交互搜索控件",
            "evidence": evidence,
            "selected": False,
            "skipReason": "low-value-structure",
            "sourceType": source_type,
        }

    elif STATE_RE.search(combined) and element_type != "region" and tag not in {"header", "main", "section", "nav", "footer"}:
        kind = "state"
        dimension = "State and exception"
        priority = "medium"
        score = 64
        reason = "状态或异常相关元素，适合说明展示条件和处理方式"
        skip_reason = None

    elif (
        AI_RE.search(combined)
        and tag not in {"header", "main", "nav", "footer", "section", "div", "h1", "h2", "h3", "h4", "h5", "h6"}
        and not COMMON_NAV_RE.search(visible)
        and (element_type != "region" or AI_REGION_RE.search(combined))
    ):
        kind = "ai"
        dimension = "AI and automation"
        priority = "high"
        score = 78
        reason = "AI 或自动化相关元素，适合说明生成态、重试和结果处理"
        skip_reason = None

    elif element_type == "region":
        skip_reason = "low-value-structure"
        if matched_docs and len(visible) >= 8:
            kind = "note"
            dimension = "Data explanation"
            priority = "low"
            score = 42
            reason = "区域文本与文档匹配，可作为上下文候选但默认不优先"
            skip_reason = None

    if matched_docs:
        score += 12
    if element.get("strategy") in {"id", "data", "aria", "name"}:
        score += 8
    elif not visible and element.get("strategy") == "path":
        score -= 20
        if skip_reason is None:
            skip_reason = "unstable-target"

    if tag in {"input", "textarea"} and (
        FILTER_RE.search(combined) or SEARCH_PLACEHOLDER_RE.search(str(attrs.get("placeholder") or ""))
    ):
        for topic in ("search", "filter"):
            if topic not in extra_topics:
                extra_topics.append(topic)

    selected = skip_reason is None and score >= SELECTED_SCORE_THRESHOLD
    if selected and dimension != "Page overview" and is_coarse_selector(selector):
        selected = False
        skip_reason = "unstable-target"
        reason = "区域级 selector 不适合元素级研发交付标注，请改用更精确的锚点"
        score = min(score, 20)
    return {
        "kind": kind,
        "dimension": dimension,
        "priority": priority,
        "score": score,
        "reason": reason or "缺少明确业务规则",
        "evidence": evidence,
        "selected": selected,
        "skipReason": None if selected else skip_reason,
        "sourceType": source_type,
        "extraTopics": extra_topics,
    }


def selector_without_row_index(selector: str) -> str:
    value = re.sub(r"tr:nth-of-type\(\d+\)", "tr:nth-of-type(*)", selector or "")
    value = re.sub(r"li:nth-of-type\(\d+\)", "li:nth-of-type(*)", value)
    return value


def is_table_row_action_candidate(candidate: dict) -> bool:
    selector = str(candidate.get("selector") or "")
    tag = str(candidate.get("tag") or "")
    text = normalize(str(candidate.get("fallbackText") or ""))
    if "tr:nth-of-type(" not in selector or tag not in {"button", "a"}:
        return False
    return bool(ROW_ACTION_TEXT_RE.search(text))


def is_js_row_action_candidate(candidate: dict) -> bool:
    selector = str(candidate.get("selector") or "")
    attrs = candidate.get("attrs") if isinstance(candidate.get("attrs"), dict) else {}
    onclick = str(attrs.get("onclick") or "")
    title = str(attrs.get("title") or "")
    if "${" not in selector and "${" not in onclick:
        return False
    combined = f"{onclick} {title} {selector}"
    return bool(JS_ROW_ACTION_FN_RE.search(combined) or ROW_ACTION_TEXT_RE.search(title))


def fold_table_row_actions(candidates: list[dict]) -> None:
    row_actions = [
        item
        for item in candidates
        if is_table_row_action_candidate(item)
        or is_js_row_action_candidate(item)
        or (
            item.get("skipReason") == "scan-artifact"
            and is_js_row_action_candidate(item)
        )
    ]
    if not row_actions:
        return
    if any(item.get("dimension") == "Table row actions" and item.get("selected") for item in candidates):
        for item in row_actions:
            item["selected"] = False
            item["skipReason"] = "folded-into-row-action-group"
        return
    table_anchor = next(
        (
            item
            for item in candidates
            if str(item.get("tag") or "") == "table"
            or str(item.get("selector") or "") in {"#tableContainer", "table"}
        ),
        None,
    )
    anchor = table_anchor or sorted(row_actions, key=candidate_sort_key)[0]
    for item in row_actions:
        item["selected"] = False
        item["skipReason"] = "folded-into-row-action-group"
    labels = unique_labels(row_actions, "行级操作")
    evidence = list(anchor.get("evidence") or [])
    if labels:
        evidence.insert(0, f"合并操作：{'、'.join(labels[:6])}")
    page_key = str(anchor.get("pageKey") or "P01")
    table_selector = next(
        (
            str(item.get("selector") or "")
            for item in candidates
            if str(item.get("selector") or "") in {"#tableContainer", "table"}
        ),
        "",
    )
    group_selector = table_selector or str(anchor.get("selector") or "")
    candidates.append(
        {
            "candidateId": f"CAND-{page_key}-ROW-GROUP",
            "pageKey": anchor.get("pageKey"),
            "pagePath": anchor.get("pagePath") or "",
            "pageRoute": anchor.get("pageRoute") or "",
            "elementId": anchor.get("elementId"),
            "selector": group_selector,
            "strategy": anchor.get("strategy"),
            "fallbackText": "行级操作",
            "tag": anchor.get("tag"),
            "type": anchor.get("type"),
            "kind": "interaction",
            "annotationType": "A",
            "topics": ["table", "row-action", "permission", "risk"],
            "dimension": "Table row actions",
            "priority": "high",
            "score": max(int(anchor.get("score") or 0), 88),
            "reason": "表格行级操作组，合并编辑、删除、启用、停用等重复操作",
            "evidence": evidence[:6],
            "selected": True,
            "skipReason": None,
            "source": anchor.get("source") or {"type": "prototype", "ref": "table-row-actions"},
            "selectorQuality": anchor.get("selectorQuality"),
        }
    )


def is_search_filter_candidate(candidate: dict) -> bool:
    dimension = str(candidate.get("dimension") or "")
    if dimension != "Form and validation":
        return False
    tag = str(candidate.get("tag") or "")
    if tag not in {"input", "textarea", "select", "form"}:
        return False
    topics = {str(topic).lower() for topic in (candidate.get("topics") or [])}
    if topics & {"search", "filter"}:
        return True
    attrs = candidate.get("attrs") if isinstance(candidate.get("attrs"), dict) else {}
    placeholder = str(attrs.get("placeholder") or "")
    visible = str(candidate.get("fallbackText") or "")
    return bool(SEARCH_PLACEHOLDER_RE.search(placeholder) or FILTER_RE.search(visible))


def meaning_signature(candidate: dict) -> tuple[str, ...]:
    text = normalize_key(str(candidate.get("fallbackText") or ""))
    selector = str(candidate.get("selector") or "")
    kind = str(candidate.get("kind") or "")
    dimension = str(candidate.get("dimension") or "")
    tag = str(candidate.get("tag") or "")
    if is_search_filter_candidate(candidate):
        return ("search-filter", str(candidate.get("pageKey") or ""))
    if dimension == "Table row actions" or is_js_row_action_candidate(candidate) or (
        "tr:nth-of-type(" in selector and tag in {"button", "a"} and ROW_ACTION_TEXT_RE.search(text)
    ):
        return ("table-row-action-group",)
    if "tr:nth-of-type(" in selector and tag in {"button", "a"}:
        return ("table-row-action", text, kind)
    if text:
        return (kind, dimension, text)
    return (kind, dimension, selector_without_row_index(selector))


def candidate_sort_key(candidate: dict) -> tuple[int, int, int, str]:
    strategy = str(candidate.get("strategy") or "")
    stable_bonus = 1 if strategy in {"id", "data", "aria", "name", "href", "placeholder", "role", "tag"} else 0
    ann_type = str(candidate.get("annotationType") or annotation_type_for(str(candidate.get("kind") or ""), str(candidate.get("dimension") or "")))
    type_rank = TYPE_PRIORITY.get(ann_type, 50)
    return (type_rank, -int(candidate.get("score") or 0), -stable_bonus, str(candidate.get("candidateId") or ""))


def page_overview_rank(candidate: dict) -> tuple[int, int, str]:
    tag = str(candidate.get("tag") or "")
    text = normalize(str(candidate.get("fallbackText") or ""))
    strategy = str(candidate.get("strategy") or "")
    tag_rank = {
        "h1": 0,
        "h2": 1,
        "main": 2,
        "header": 3,
        "section": 4,
    }.get(tag, 8)
    empty_penalty = 1 if not text else 0
    stable_penalty = 0 if strategy in {"id", "data", "aria", "name"} else 1
    return (tag_rank, empty_penalty, stable_penalty, str(candidate.get("candidateId") or ""))


def infer_page_summary(page: dict, candidates: list[dict], page_title: str) -> tuple[str, list[str]]:
    page_title = normalize(page_title or str(page.get("title") or page.get("route") or page.get("pageKey") or "当前页面"))
    route = normalize(str(page.get("route") or ""))
    selected_like = [
        item for item in candidates
        if item.get("selected")
        and not COMMON_NAV_RE.fullmatch(normalize(str(item.get("fallbackText") or "")))
    ]
    tables = [item for item in selected_like if item.get("dimension") == "Table and list" or item.get("tag") == "table"]
    forms = [item for item in selected_like if item.get("dimension") == "Form and validation"]
    primary = [item for item in selected_like if item.get("dimension") == "Primary action"]
    risks = [item for item in selected_like if item.get("dimension") == "Permission and risk"]
    states = [item for item in selected_like if item.get("dimension") == "State and exception"]

    summary_parts = [f"`{page_title}` 是本原型中的一个页面"]
    if route:
        summary_parts.append(f"路由为 `{route}`")
    if tables:
        summary_parts.append("包含列表/表格数据的浏览与操作")
    if forms:
        summary_parts.append("包含查询、筛选或表单输入")
    if primary:
        labels = "、".join(unique_labels(primary, "关键操作")[:3])
        summary_parts.append(f"关键操作包括：{labels}")
    if risks:
        labels = "、".join(unique_labels(risks, "风险操作")[:3])
        summary_parts.append(f"需要重点关注权限/风险操作：{labels}")
    if len(summary_parts) <= 2 and selected_like:
        labels = "、".join(unique_labels(selected_like, "页面内容")[:3])
        summary_parts.append(f"主要阅读对象包括：{labels}")
    summary = "，".join(summary_parts) + "。"

    focus = [
        "先确认本页在业务流程中的入口、出口和服务对象。",
        "阅读页面内其他标注时，重点关注非显而易见的交互规则、状态、权限和数据变化。",
    ]
    if tables:
        focus.append("表格/列表区域关注列含义、筛选条件、行级操作、空状态和分页规则。")
    if forms:
        focus.append("输入和筛选区域关注字段含义、默认值、校验规则和选项来源。")
    if states:
        focus.append("状态类内容关注展示条件、状态切换和异常处理。")
    if risks:
        focus.append("风险操作需要确认权限范围、二次确认、撤销路径和后续影响。")
    return summary, focus[:5]


def compact_label(value: str, limit: int = 16) -> str:
    text = normalize(str(value or ""))
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def unique_labels(candidates: list[dict], fallback: str) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        label = compact_label(str(item.get("fallbackText") or item.get("reason") or fallback))
        key = normalize_key(label)
        if not key or key in seen:
            continue
        seen.add(key)
        labels.append(label)
    return labels


def ensure_page_overview_candidate(page: dict, candidates: list[dict]) -> None:
    page_key = str(page.get("pageKey") or "")
    if not page_key or any(item.get("dimension") == "Page overview" and item.get("selected") for item in candidates):
        return
    eligible = [
        item for item in candidates
        if item.get("selector")
        and str(item.get("tag") or "") in {"h1", "h2", "main", "header", "section"}
    ]
    if not eligible:
        eligible = [item for item in candidates if item.get("selector")]
    if not eligible:
        return
    intro = sorted(eligible, key=page_overview_rank)[0]
    fallback = normalize(str(intro.get("fallbackText") or ""))
    page_title = fallback or normalize(str(page.get("title") or page.get("route") or page_key))
    page_summary, reading_focus = infer_page_summary(page, candidates, page_title)
    if not fallback:
        intro["fallbackText"] = page_title
    intro.update(
        {
            "kind": "note",
            "topics": topics_for("note", "Page overview", page_summary),
            "annotationType": "P",
            "dimension": "Page overview",
            "priority": "high",
            "score": max(intro.get("score") or 0, 110),
            "reason": page_summary,
            "selected": True,
            "skipReason": None,
            "pageTitle": page_title,
            "pageSummary": page_summary,
            "readingFocus": reading_focus,
        }
    )
    evidence = list(intro.get("evidence") or [])
    evidence.insert(0, f"页面：{page_title}")
    route = page.get("route")
    if route:
        evidence.insert(1, f"路由：{route}")
    intro["evidence"] = evidence[:6]


def apply_annotation_types(candidates: list[dict]) -> None:
    for item in candidates:
        extra_topics = item.pop("extraTopics", None)
        item["annotationType"] = annotation_type_for(str(item.get("kind") or ""), str(item.get("dimension") or ""))
        if extra_topics:
            topics = list(item.get("topics") or [])
            for topic in extra_topics:
                if topic not in topics:
                    topics.append(topic)
            item["topics"] = topics
            if "search" in topics or "filter" in topics:
                item["annotationType"] = "C"


def mark_duplicate_meanings(candidates: list[dict]) -> None:
    selected = [item for item in candidates if item.get("selected")]
    groups: dict[tuple[str, ...], list[dict]] = {}
    for item in selected:
        groups.setdefault(meaning_signature(item), []).append(item)
    for group in groups.values():
        if len(group) <= 1:
            continue
        group.sort(key=candidate_sort_key)
        for item in group[1:]:
            item["selected"] = False
            item["skipReason"] = "duplicate-meaning"


def cap_selected(candidates: list[dict], max_per_page: int) -> None:
    mark_duplicate_meanings(candidates)
    selected = [item for item in candidates if item["selected"]]
    selected.sort(key=candidate_sort_key)
    keep: set[str] = set()
    dimension_counts: dict[str, int] = {}
    protected_dimensions = {"Page overview", "Surface trigger", "Surface overview"}
    for item in selected:
        dimension = str(item.get("dimension") or "Context")
        if dimension in protected_dimensions:
            keep.add(str(item["candidateId"]))
            dimension_counts[dimension] = dimension_counts.get(dimension, 0) + 1
    for item in selected:
        candidate_id = str(item["candidateId"])
        if candidate_id in keep:
            continue
        dimension = str(item.get("dimension") or "Context")
        limit = DIMENSION_LIMITS.get(dimension, 2)
        if len(keep) >= max_per_page:
            item["selected"] = False
            item["skipReason"] = "out-of-scope"
            continue
        if dimension_counts.get(dimension, 0) >= limit:
            item["selected"] = False
            item["skipReason"] = "duplicate-meaning"
            continue
        keep.add(candidate_id)
        dimension_counts[dimension] = dimension_counts.get(dimension, 0) + 1
    for item in selected:
        if str(item["candidateId"]) in keep:
            continue
        item["selected"] = False
        item.setdefault("skipReason", "out-of-scope")
    for item in candidates:
        if item["candidateId"] in keep:
            item["selected"] = True
            item["skipReason"] = None


def infer_page_cap(candidates: list[dict], max_per_page: int, page: dict | None = None) -> int:
    selected = [
        item for item in candidates
        if item.get("selected") and item.get("dimension") != "Page overview"
    ]
    if not selected:
        return min(max_per_page, 1)
    dimensions = {str(item.get("dimension") or "") for item in selected}
    high_value_count = sum(
        1 for item in selected
        if item.get("dimension") in {
            "Primary action",
            "Form and validation",
            "Table and list",
            "State and exception",
            "Permission and risk",
            "AI and automation",
        }
    )
    has_secondary_ui = bool(
        dimensions
        & {"Surface trigger", "Surface overview", "Surface field", "Surface action", "Surface confirm"}
    )
    if has_secondary_ui:
        return min(max_per_page, 12)
    has_core_surface = bool(dimensions & {"Table and list", "Form and validation"})
    has_critical_logic = bool(dimensions & {"Primary action", "Permission and risk", "AI and automation", "State and exception"})
    if has_core_surface and has_critical_logic and high_value_count >= 6:
        return min(max_per_page, 8)
    if high_value_count >= 4:
        return min(max_per_page, 6)
    if high_value_count >= 2:
        base_cap = min(max_per_page, 5)
    else:
        base_cap = min(max_per_page, 3)
    if page and is_dense_page(page):
        return min(max_per_page, max(base_cap, 6))
    return base_cap


def build_dev_handoff_hints(page: dict, candidates: list[dict]) -> dict:
    selected = [item for item in candidates if item.get("selected")]
    non_overview = [item for item in selected if item.get("dimension") != "Page overview"]
    coarse = [
        item.get("candidateId")
        for item in non_overview
        if is_coarse_selector(str(item.get("selector") or ""))
    ]
    return {
        "pageKey": page.get("pageKey"),
        "route": page.get("route") or page.get("path"),
        "selectedCount": len(selected),
        "minSuggested": max(1, len(non_overview) + 1),
        "densePage": is_dense_page(page),
        "coarseSelectedIds": coarse,
    }


def build_candidates(page_map: dict, docs: list[dict], max_per_page: int) -> dict:
    pages_payload = []
    flat_candidates: list[dict] = []
    all_surfaces: list[dict] = []
    seen_surface_ids: set[str] = set()
    for page in page_map.get("pages", []):
        page_candidates: list[dict] = []
        feedback_items: list[dict] = []
        seen_selectors: set[str] = set()
        page_surfaces = surfaces_for_page(page_map, page)
        surfaces_by_id = {str(surface.get("id") or ""): surface for surface in page_surfaces if surface.get("id")}
        for index, element in enumerate(page.get("elements", []), start=1):
            selector = element.get("selector") or ""
            if selector in seen_selectors:
                continue
            seen_selectors.add(selector)
            if is_transient_feedback_element(element):
                feedback_items.append(
                    {
                        "selector": selector,
                        "text": element.get("text") or "",
                        "surfaceId": element.get("surfaceId"),
                    }
                )
                continue
            surface_id = str(element.get("surfaceId") or "")
            trigger_surface = surface_for_trigger(element, page_surfaces)
            if surface_id and surface_id in surfaces_by_id:
                open_selector = str(surfaces_by_id[surface_id].get("openSelector") or "")
                if open_selector and selectors_equivalent(selector, open_selector):
                    continue
                classified = classify_surface_element(element, surfaces_by_id[surface_id], docs)
            elif trigger_surface:
                classified = classify_surface_trigger(element, trigger_surface, docs)
            else:
                classified = classify_element(element, docs)
            candidate = {
                "candidateId": f"CAND-{page.get('pageKey')}-{len(page_candidates) + 1:03d}",
                "pageKey": page.get("pageKey"),
                "pagePath": page.get("path") or "",
                "pageRoute": page.get("route") or "",
                "elementId": element.get("elementId"),
                "selector": selector,
                "strategy": element.get("strategy"),
                "fallbackText": element.get("text") or "",
                "tag": element.get("tag"),
                "type": element.get("type"),
                "attrs": element.get("attrs") if isinstance(element.get("attrs"), dict) else {},
                "kind": classified["kind"],
                "annotationType": annotation_type_for(classified["kind"], classified["dimension"]),
                "topics": topics_for(classified["kind"], classified["dimension"], classified["reason"]),
                "dimension": classified["dimension"],
                "priority": classified["priority"],
                "score": classified["score"],
                "reason": classified["reason"],
                "evidence": classified["evidence"],
                "selected": classified["selected"],
                "skipReason": classified["skipReason"],
                "source": {
                    "type": classified["sourceType"],
                    "ref": f"page-map:{element.get('elementId')}",
                },
                "selectorQuality": selector_quality(selector, element.get("strategy")),
            }
            if classified.get("surfaceId"):
                candidate["surfaceId"] = classified["surfaceId"]
            if classified.get("displayWhenClosed"):
                candidate["displayWhenClosed"] = classified["displayWhenClosed"]
            if classified.get("fallbackAnchorSelector"):
                candidate["fallbackAnchorSelector"] = classified["fallbackAnchorSelector"]
            page_candidates.append(candidate)
        ensure_surface_structure_candidates(page, page_surfaces, page_candidates, docs)
        attach_feedback_evidence(page_candidates, feedback_items)
        fold_table_row_actions(page_candidates)
        ensure_page_overview_candidate(page, page_candidates)
        apply_annotation_types(page_candidates)
        cap_selected(page_candidates, infer_page_cap(page_candidates, max_per_page, page))
        pages_payload.append(
            {
                "pageKey": page.get("pageKey"),
                "title": page.get("title"),
                "path": page.get("path"),
                "route": page.get("route"),
                "candidates": page_candidates,
            }
        )
        flat_candidates.extend(page_candidates)
        for surface in page_surfaces:
            surface_id = str(surface.get("id") or "")
            if surface_id and surface_id not in seen_surface_ids:
                seen_surface_ids.add(surface_id)
                all_surfaces.append(surface)
    pages_by_key = {page.get("pageKey"): page for page in page_map.get("pages", []) if page.get("pageKey")}
    dev_handoff_hints = [
        build_dev_handoff_hints(pages_by_key.get(page_entry.get("pageKey"), {}), page_entry["candidates"])
        for page_entry in pages_payload
    ]
    payload = {
        "version": 1,
        "generatedAt": now_iso(),
        "root": page_map.get("root"),
        "sources": {
            "pageMap": "page-map.json",
            "docs": [doc["path"] for doc in docs],
        },
        "devHandoffHints": dev_handoff_hints,
        "candidates": flat_candidates,
        "pages": pages_payload,
    }
    if all_surfaces:
        payload["surfaces"] = all_surfaces
    return payload


def count_selected(pages: Iterable[dict]) -> int:
    return sum(1 for page in pages for item in page.get("candidates", []) if item.get("selected"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Prototype Annotator candidate annotations.")
    parser.add_argument("prototype_path", help="HTML file or static directory")
    parser.add_argument("--page-map", help="Path to prototype-annotator/page-map.json")
    parser.add_argument("--docs", action="append", default=[], help="PRD, product spec, Markdown spec file, or directory. Repeatable.")
    parser.add_argument("--out", help="Output annotation-candidates.json path")
    parser.add_argument("--max-per-page", type=int, default=10, help="Quality ceiling for selected candidates per page; the script does not fill this quota mechanically")
    args = parser.parse_args()

    target = Path(args.prototype_path).resolve()
    if not target.exists():
        parser.error(f"Path does not exist: {target}")
    page_map_path = Path(args.page_map).resolve() if args.page_map else default_page_map(target)
    if not page_map_path.exists():
        parser.error(f"Page map does not exist: {page_map_path}. Run scripts/scan_prototype.py first.")
    root = annotation_root(target)
    docs = load_docs(doc_paths(root, args.docs))
    payload = build_candidates(read_json(page_map_path), docs, max(1, args.max_per_page))
    output = Path(args.out).resolve() if args.out else default_output(target)
    write_json(output, payload)
    print(f"Wrote candidates: {output}")
    print(f"Selected candidates: {count_selected(payload.get('pages', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
