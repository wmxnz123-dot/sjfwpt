#!/usr/bin/env python3
"""Validate annotations.json against static HTML or rendered SPA page maps."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

from annotation_types import VALID_ANNOTATION_TYPES
from dev_handoff import candidates_file_for, is_dev_handoff_mode, load_json as load_dev_json, validate_dev_handoff
from scan_prototype import scan_html


PRODUCT_REVIEW_BANNED_TERMS = [
    ".js",
    "api.",
    "checkvalidity",
    "confirm(",
    "handler",
    "opendrawer",
    "showtoast",
    "src/",
    "store",
    "state",
    "selector",
    "mock",
    "zustand",
    "component",
    "代码",
    "函数",
    "源码",
    "以源码为准",
    "以组件 state 为准",
    "本地规则草稿",
    "待补",
    "该元素",
]
PRODUCT_REVIEW_GENERIC_TERMS = [
    "影响本页筛选范围或表单提交内容",
    "根据业务需要处理",
    "具体规则后续确认",
    "按实际情况展示",
    "待业务确认",
]
GENERIC_TEMPLATE_PATTERNS = [
    "用于提交、保存、取消或关闭当前二级界面中的处理结果",
    "用于在二级界面中补充或确认当前业务对象的关键信息",
    "用户应根据业务要求填写或选择该字段",
    "校验通过后执行保存、提交或关闭操作",
]
DISALLOWED_CLOSE_ACTION_TERMS = [
    "提交",
    "保存",
    "校验通过",
    "刷新主页面",
    "loading",
    "避免重复提交",
]
SURFACE_PART_RE = re.compile(r"(?:^|[\s_-])(header|body|footer|title|content)(?:[\s_-]|$)", re.I)
TECHNICAL_SURFACE_NAME_RE = re.compile(
    r"^(?:surface-)?(?:drawer|modal|dialog|popover|dropdown|confirm|popup)(?:[-_\w]*|\d*)$",
    re.I,
)
COMPOUND_TITLE_TEXT_RE = re.compile(r"[/／|｜]")
DESCENDANT_ATTR_SELECTOR_RE = re.compile(
    r"""#(?P<id>[A-Za-z0-9_\-:\\.]+)\s+\[(?P<attr>[A-Za-z0-9_-]+)(?:[*^$~|]?=)["'](?P<value>[^"']+)["']\]"""
)
ATTR_SELECTOR_RE = re.compile(
    r"""^\[(?P<attr>[A-Za-z0-9_-]+)(?:[*^$~|]?=)["'](?P<value>[^"']+)["']\]$"""
)
ANN_ID_RE = re.compile(r"^ANN-(?P<page>.+)-(?P<num>\d{3,})$")
STRUCTURED_MARKDOWN_HEADINGS = [
    "### 业务含义",
    "### 使用场景",
    "### 交互规则",
    "### 状态与异常",
    "### 待确认",
    "### 页面功能介绍",
    "### 页面说明",
    "### 页面目标",
]
PAGE_OVERVIEW_REQUIRED_HEADINGS = [
    "页面功能介绍",
    "核心内容",
    "业务流程",
    "主要操作",
    "待确认",
]
ROW_ACTION_TEXT_RE = re.compile(
    r"编辑|删除|启用|停用|授权|下载|查看|详情|重置|密钥|edit|delete|enable|disable|download",
    re.I,
)
TOAST_SELECTOR_TOKENS = ("toast", "message", "snackbar", "notification", "success-toast")
INLINE_DATA_RE = re.compile(
    r"<script[^>]+id=[\"']prototype-annotations-data[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
NOT_FOUND_TEXT_RE = re.compile(r"不存在|not\s*found|404", re.I)
UNSTABLE_SELECTOR_RE = re.compile(r":nth-of-type|^table$|#radix-")
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
ANNOTATION_ASSET_RE = re.compile(r"^(?:/|\.\/)?\.prototype-annotations/assets/([a-zA-Z0-9._/-]+)$")
PUBLIC_ANNOTATION_ASSET_RE = re.compile(r"^(?:/|\.\/)?prototype-annotator/assets/([a-zA-Z0-9._/-]+)$")
HTML_LOCAL_ANNOTATION_REF_RE = re.compile(
    r"""(?:src|href)=["']([^"']*(?:\.prototype-annotations|prototype-annotator)/[^"']*)["']""",
    re.IGNORECASE,
)
ANNOTATION_DATA_URL_RE = re.compile(r"""dataUrl\s*:\s*["']([^"']+)["']""")
STATIC_RUNTIME_FILE_RE = re.compile(r"(?:^|/)(?:markdown-renderer|mermaid-loader|prototype-annotator)\.js$|(?:^|/)prototype-annotator\.css$")
DEPLOY_PUBLIC_FRAMEWORKS = {"react", "vue", "vite"}


def annotation_file_for(target: Path) -> Path:
    root = target.parent if target.is_file() else target
    preferred = root / "prototype-annotator" / "annotations.json"
    if preferred.exists():
        return preferred
    legacy = root / ".prototype-annotations" / "annotations.json"
    if legacy.exists():
        return legacy
    return preferred


def page_map_file_for(target: Path) -> Path:
    root = target.parent if target.is_file() else target
    preferred = root / "prototype-annotator" / "page-map.json"
    if preferred.exists():
        return preferred
    return root / ".prototype-annotations" / "page-map.json"


def detect_framework(target: Path) -> str:
    root = target.parent if target.is_file() else target
    package_json = root / "package.json"
    if not package_json.exists():
        return "html"
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "html"
    deps = {}
    deps.update(data.get("dependencies") or {})
    deps.update(data.get("devDependencies") or {})
    if "vue" in deps:
        return "vue"
    if "react" in deps:
        return "react"
    if "vite" in deps:
        return "vite"
    return "html"


def find_html_files(target: Path) -> tuple[Path, List[Path]]:
    if target.is_file():
        return target.parent, [target]
    files = sorted(
        path for path in target.rglob("*.html")
        if ".prototype-annotations" not in path.parts
        and "prototype-annotator" not in path.parts
        and "node_modules" not in path.parts
        and not any(part.startswith(".") for part in path.relative_to(target).parts)
        and not path.name.endswith("-annotated.html")
    )
    return target, files


def page_path_map(target: Path, data: dict) -> Dict[str, str]:
    pages = data.get("pages") or []
    if pages:
        return {page.get("pageKey"): page.get("path") for page in pages if page.get("pageKey") and page.get("path")}
    if target.is_file():
        return {"P01": target.name}
    return {}


def selector_matches(selector: str, nodes) -> bool:
    selector = (selector or "").strip()
    if not selector:
        return False
    generated = {node.get("selector") for node in nodes}
    if selector in generated:
        return True

    id_match = re.fullmatch(r"#([A-Za-z0-9_\-:\\.]+)", selector)
    if id_match:
        wanted = id_match.group(1).replace("\\", "")
        return any(node.get("attrs", {}).get("id") == wanted or node.get("selector") == selector for node in nodes)

    attr_match = re.fullmatch(r'(?:([a-zA-Z0-9_-]+))?\[([a-zA-Z0-9_-]+)([*^$~|]?=)"([^"]*)"\]', selector)
    if attr_match:
        tag, attr, operator, value = attr_match.groups()

        def attr_ok(actual: str | None) -> bool:
            actual = actual or ""
            if operator == "=":
                return actual == value
            if operator == "*=":
                return value in actual
            if operator == "^=":
                return actual.startswith(value)
            if operator == "$=":
                return actual.endswith(value)
            return actual == value

        return any((not tag or node.get("tag") == tag) and attr_ok(node.get("attrs", {}).get(attr)) for node in nodes)

    if ">" in selector or ":nth-of-type" in selector:
        return any(node.get("selector") == selector for node in nodes)

    if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9-]*", selector):
        return any(node.get("tag") == selector.lower() for node in nodes)

    return selector in generated


def selector_matched_nodes(selector: str, nodes) -> list[dict]:
    selector = (selector or "").strip()
    if not selector:
        return []
    matched = [node for node in nodes if node.get("selector") == selector]
    id_match = re.fullmatch(r"#([A-Za-z0-9_\-:\\.]+)", selector)
    if id_match:
        wanted = id_match.group(1).replace("\\", "")
        matched.extend(node for node in nodes if node.get("attrs", {}).get("id") == wanted)
    attr_match = re.fullmatch(r'(?:([a-zA-Z0-9_-]+))?\[([a-zA-Z0-9_-]+)([*^$~|]?=)"([^"]*)"\]', selector)
    if attr_match:
        tag, attr, operator, value = attr_match.groups()

        def attr_ok(actual: str | None) -> bool:
            actual = actual or ""
            if operator == "=":
                return actual == value
            if operator == "*=":
                return value in actual
            if operator == "^=":
                return actual.startswith(value)
            if operator == "$=":
                return actual.endswith(value)
            return actual == value

        matched.extend(
            node for node in nodes
            if (not tag or node.get("tag") == tag)
            and attr_ok(node.get("attrs", {}).get(attr))
        )
    if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9-]*", selector):
        matched.extend(node for node in nodes if node.get("tag") == selector.lower())
    seen = set()
    unique = []
    for node in matched:
        key = (node.get("elementId"), node.get("selector"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(node)
    return unique


def selector_matches_visible(selector: str, nodes) -> bool:
    matched = selector_matched_nodes(selector, nodes)
    if not matched:
        return False
    return any(node.get("visible") is not False for node in matched)


def load_data(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise SystemExit(f"Invalid JSON in {path}: {err}") from err


def annotation_image_sources(data: dict) -> dict[str, set[str]]:
    sources: dict[str, set[str]] = {}
    for ann in data.get("annotations") or []:
        if not isinstance(ann, dict):
            continue
        ann_id = str(ann.get("id") or "<missing id>")
        for field in ("contentMarkdown", "devNotesMarkdown"):
            content = str(ann.get(field) or "")
            for match in MARKDOWN_IMAGE_RE.finditer(content):
                src = match.group(1).strip()
                asset_match = ANNOTATION_ASSET_RE.match(src) or PUBLIC_ANNOTATION_ASSET_RE.match(src)
                if not asset_match:
                    continue
                sources.setdefault(ann_id, set()).add(asset_match.group(1).strip("/"))
    return sources


def json_equal(left: Path, right: Path) -> bool:
    try:
        return json.loads(left.read_text(encoding="utf-8")) == json.loads(right.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False


def resolve_static_reference(html_file: Path, root_dir: Path, ref: str) -> Path | None:
    ref = (ref or "").strip()
    if not ref or ref.startswith("//") or re.match(r"^[a-z][a-z0-9+.-]*:", ref, re.I):
        return None
    ref = ref.split("#", 1)[0].split("?", 1)[0]
    if not ref:
        return None
    if ref.startswith("/"):
        return root_dir / ref.lstrip("/")
    return html_file.parent / ref


def validate_static_runtime_assets(
    root_dir: Path,
    html_files: list[Path],
    annotation_path: Path,
    *,
    deploy_check: bool,
) -> tuple[int, list[str]]:
    if not deploy_check:
        return 0, []

    errors: list[str] = []
    injected_files: list[Path] = []
    for html_file in html_files:
        try:
            html = html_file.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            errors.append(f"Could not read HTML for deploy check: {html_file}: {exc}")
            continue
        has_runtime = (
            "Prototype Annotator runtime" in html
            or "prototype-annotations-data" in html
            or ".prototype-annotations/runtime/" in html
            or "prototype-annotator/prototype-annotator.js" in html
        )
        if not has_runtime:
            continue

        injected_files.append(html_file)
        rel_html = str(html_file.relative_to(root_dir))
        refs = {match.group(1) for match in HTML_LOCAL_ANNOTATION_REF_RE.finditer(html)}
        refs.update(
            match.group(1)
            for match in ANNOTATION_DATA_URL_RE.finditer(html)
            if ".prototype-annotations/" in match.group(1) or "prototype-annotator/" in match.group(1)
        )

        runtime_refs = [ref for ref in refs if ".prototype-annotations/runtime/" in ref or STATIC_RUNTIME_FILE_RE.search(ref)]
        if not runtime_refs:
            errors.append(f"{rel_html}: injected runtime block has no local Prototype Annotator runtime references")

        for ref in sorted(refs):
            path = resolve_static_reference(html_file, root_dir, ref)
            if path is None:
                continue
            if not path.is_file():
                errors.append(f"{rel_html}: static deploy file is missing: {path}")
            elif path.name == "annotations.json" and (".prototype-annotations/" in ref or "prototype-annotator/" in ref):
                if "prototype-annotator/" in ref:
                    try:
                        json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        errors.append(f"{rel_html}: public runtime annotations JSON is invalid: {path}")
                elif not json_equal(annotation_path, path):
                    errors.append(f"{rel_html}: static deploy annotations copy is stale: {path}")

    if html_files and not injected_files:
        errors.append(
            "No HTML files contain Prototype Annotator runtime injection. "
            "Run scripts/inject_annotations.py before deploying static HTML."
        )

    return len(errors), errors


def validate_deploy_assets(
    data: dict,
    root_dir: Path,
    annotation_path: Path,
    *,
    framework: str,
    deploy_check: bool,
) -> tuple[int, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    image_sources = annotation_image_sources(data)
    if not image_sources and not deploy_check:
        return 0, []

    source_assets = annotation_path.parent / "assets"
    public_assets = root_dir / "public" / "prototype-annotator" / "assets"
    for ann_id, rel_paths in sorted(image_sources.items()):
        for rel_path in sorted(rel_paths):
            source_file = source_assets / rel_path
            public_file = public_assets / rel_path
            if not source_file.is_file():
                errors.append(f"{ann_id}: Markdown image source file is missing: {source_file}")
            if framework in DEPLOY_PUBLIC_FRAMEWORKS and not public_file.is_file():
                message = (
                    f"{ann_id}: deploy asset is missing: {public_file}. "
                    "Run scripts/sync_deploy_assets.py before building a Vite/React/Vue deploy."
                )
                if deploy_check or framework in DEPLOY_PUBLIC_FRAMEWORKS:
                    errors.append(message) if deploy_check else warnings.append(f"WARNING: {message}")
                else:
                    warnings.append(f"WARNING: {message}")

    if deploy_check and framework in DEPLOY_PUBLIC_FRAMEWORKS:
        public_annotations = root_dir / "public" / "prototype-annotator" / "annotations.json"
        if not public_annotations.is_file():
            errors.append(f"Deploy annotations copy is missing: {public_annotations}")
        elif not json_equal(annotation_path, public_annotations):
            errors.append(f"Deploy annotations copy is stale: {public_annotations}")
    return len(errors), errors + warnings


def load_page_map_nodes(page_map_path: Path) -> tuple[dict[str, list], dict[str, str]]:
    page_map = load_data(page_map_path)
    nodes_by_page: dict[str, list] = {}
    paths_by_page: dict[str, str] = {}
    for page in page_map.get("pages", []):
        page_key = page.get("pageKey")
        if not page_key:
            continue
        nodes_by_page[page_key] = page.get("elements") or []
        paths_by_page[page_key] = page.get("path") or page.get("route") or page_key
    return nodes_by_page, paths_by_page


def normalize_quality_key(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip().lower()


def is_table_row_selector(selector: str) -> bool:
    return bool(re.search(r"tr:nth-of-type\(\d+\)", selector or ""))


def selector_parts(selector: str) -> list[str]:
    return [part.strip() for part in str(selector or "").split(",") if part.strip()]


def is_single_action_selector(selector: str) -> bool:
    selector = str(selector or "")
    return bool(re.search(r"\bbutton\b|\bsvg\b|aria-label|title=|onclick", selector, re.I))


def surfaces_by_id(data: dict) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for surface in data.get("surfaces") or []:
        if not isinstance(surface, dict):
            continue
        surface_id = str(surface.get("id") or "").strip()
        if surface_id:
            indexed[surface_id] = surface
    return indexed


def surface_has_content_signature(surface: dict) -> bool:
    for key in ("contentSelector", "activeSelector", "titleSelector", "activeTitle", "titleText", "textIncludes", "matchText", "stateText", "expectedText"):
        value = surface.get(key)
        if isinstance(value, list) and any(str(item).strip() for item in value):
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def surface_has_non_title_signature(surface: dict) -> bool:
    for key in ("contentSelector", "activeSelector", "textIncludes", "matchText", "stateText", "expectedText"):
        value = surface.get(key)
        if isinstance(value, list) and any(str(item).strip() for item in value):
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def has_compound_title_text(surface: dict) -> bool:
    value = surface.get("titleText")
    return isinstance(value, str) and bool(COMPOUND_TITLE_TEXT_RE.search(value))


def normalize_surface_name_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value or "").strip("-").lower()


def is_technical_surface_name(surface: dict) -> bool:
    name = str(surface.get("name") or "").strip()
    if not name:
        return True
    surface_id = str(surface.get("id") or "").strip()
    if name == surface_id or normalize_surface_name_key(name) == normalize_surface_name_key(surface_id):
        return True
    if TECHNICAL_SURFACE_NAME_RE.match(name):
        return True
    if re.fullmatch(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+){1,}", name, re.I):
        return True
    return False


def html_attr_count(html: str, attr: str, value: str) -> int:
    pattern = re.compile(
        rf"""<[^>]+\s{re.escape(attr)}\s*=\s*["']{re.escape(value)}["'][^>]*>""",
        re.I,
    )
    return len(pattern.findall(html))


def html_descendant_attr_count(html: str, root_id: str, attr: str, value: str) -> int | None:
    root_pattern = re.compile(
        rf"""<(?P<tag>[a-zA-Z][\w:-]*)[^>]*\sid\s*=\s*["']{re.escape(root_id)}["'][^>]*>""",
        re.I,
    )
    root_match = root_pattern.search(html)
    if not root_match:
        return None
    tag = root_match.group("tag")
    tag_pattern = re.compile(rf"""</?{re.escape(tag)}(?:\s[^>]*)?>""", re.I)
    depth = 0
    end = len(html)
    for match in tag_pattern.finditer(html, root_match.start()):
        token = match.group(0)
        if token.startswith("</"):
            depth -= 1
            if depth <= 0:
                end = match.end()
                break
        else:
            depth += 1
    scope = html[root_match.start():end]
    return html_attr_count(scope, attr, value)


def simple_selector_match_count(html_path: Path | None, selector: str) -> int | None:
    if not html_path or not html_path.exists():
        return None
    selector = str(selector or "").strip()
    if not selector:
        return None
    try:
        html = html_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    descendant = DESCENDANT_ATTR_SELECTOR_RE.fullmatch(selector)
    if descendant:
        return html_descendant_attr_count(
            html,
            descendant.group("id").replace("\\", ""),
            descendant.group("attr"),
            descendant.group("value"),
        )
    attr = ATTR_SELECTOR_RE.fullmatch(selector)
    if attr:
        return html_attr_count(html, attr.group("attr"), attr.group("value"))
    return None


def is_toast_like_annotation(ann: dict) -> bool:
    target = ann.get("target") if isinstance(ann.get("target"), dict) else {}
    selector = str(target.get("selector") or ann.get("selector") or "").lower()
    fallback = str(target.get("fallbackText") or "").lower()
    title = str(ann.get("title") or "").lower()
    topics = ann.get("topics") if isinstance(ann.get("topics"), list) else []
    topic_text = " ".join(str(item).lower() for item in topics)
    haystack = " ".join([selector, fallback, title, topic_text])
    return any(token in haystack for token in TOAST_SELECTOR_TOKENS)


def is_close_like_annotation(ann: dict) -> bool:
    target = ann.get("target") if isinstance(ann.get("target"), dict) else {}
    selector = str(target.get("selector") or ann.get("selector") or "").lower()
    fallback = str(target.get("fallbackText") or "")
    title = str(ann.get("title") or "")
    combined = " ".join([selector, fallback, title])
    return bool(
        "data-close-" in selector
        or "aria-label=\"关闭\"" in selector
        or "aria-label='关闭'" in selector
        or fallback.strip() in {"×", "x", "关闭", "取消"}
        or title.strip() in {"×", "x", "关闭", "取消"}
    )


def annotation_id_number(ann: dict, page_key: str) -> int | None:
    match = ANN_ID_RE.match(str(ann.get("id") or ""))
    if not match or match.group("page") != page_key:
        return None
    try:
        return int(match.group("num"))
    except ValueError:
        return None


def validate_surface_annotation(
    ann: dict,
    *,
    surfaces: dict[str, dict],
    nodes: list,
    strict_quality: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    ann_id = str(ann.get("id") or "<missing id>")
    surface_id = str(ann.get("surfaceId") or "").strip()
    if not surface_id:
        return errors, warnings

    surface = surfaces.get(surface_id)
    if not surface:
        message = f"{ann_id}: surfaceId {surface_id} not found in surfaces[]"
        add_quality_message(warnings, errors, message, strict_quality)
        return errors, warnings

    display_when_closed = str(ann.get("displayWhenClosed") or "").strip()
    if not display_when_closed:
        message = f"{ann_id}: surface annotation is missing displayWhenClosed"
        add_quality_message(warnings, errors, message, strict_quality)

    if display_when_closed == "on-trigger":
        fallback = str(ann.get("fallbackAnchorSelector") or surface.get("triggerSelector") or "").strip()
        if not fallback:
            message = f"{ann_id}: on-trigger surface annotation requires fallbackAnchorSelector or surface.triggerSelector"
            add_quality_message(warnings, errors, message, strict_quality)

    target = ann.get("target") if isinstance(ann.get("target"), dict) else {}
    selector = str(target.get("selector") or ann.get("selector") or "").strip()
    if not selector:
        return errors, warnings

    matched = selector_matches(selector, nodes)
    if matched:
        return errors, warnings

    if display_when_closed in {"sidebar-only", "hidden-until-open"}:
        warnings.append(f"WARNING: {ann_id}: surface-closed-or-hidden selector not visible in static scan ({selector})")
        return errors, warnings

    warnings.append(f"WARNING: {ann_id}: needs-interaction-plan-scan selector not found in page-map ({selector})")
    return errors, warnings


def add_quality_message(messages: list[str], errors: list[str], message: str, strict_quality: bool) -> None:
    if strict_quality:
        errors.append(message)
    else:
        messages.append(message)


def has_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def has_topic(ann: dict, topic: str) -> bool:
    topics = ann.get("topics") if isinstance(ann.get("topics"), list) else []
    return topic in {str(item) for item in topics}


def source_type_of(ann: dict) -> str:
    source = ann.get("source") if isinstance(ann.get("source"), dict) else {}
    return str(source.get("type") or "")


def product_profile_text(data: dict) -> str:
    profile = data.get("productProfile") if isinstance(data.get("productProfile"), dict) else {}
    parts = [
        str(profile.get("productType") or ""),
        " ".join(str(item) for item in profile.get("productForms") or []),
    ]
    return " ".join(parts).lower()


def product_profile_enabled_types(data: dict) -> set[str]:
    profile = data.get("productProfile") if isinstance(data.get("productProfile"), dict) else {}
    enabled = profile.get("enabledAnnotationTypes") if isinstance(profile.get("enabledAnnotationTypes"), list) else []
    return {str(item) for item in enabled if str(item).strip()}


def contains_any(text: str, tokens: list[str]) -> bool:
    return any(token.lower() in text for token in tokens)


def validate_product_type_coverage(data: dict, strict_quality: bool) -> tuple[int, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    text = product_profile_text(data)
    if not text:
        return 0, []
    annotation_types = {
        str(ann.get("annotationType") or "")
        for ann in data.get("annotations", [])
        if str(ann.get("annotationType") or "").strip()
    }

    def require(message: str, required_any: set[str]) -> None:
        if annotation_types & required_any:
            return
        add_quality_message(warnings, errors, message, strict_quality)

    if contains_any(text, ["ai", "agent", "copilot", "ai_product", "ai_enterprise_app", "智能"]):
        require("productProfile indicates an AI product but no AI annotationType is present", {"AI"})
        require("productProfile indicates an AI product but no HITL or FALLBACK annotationType is present", {"HITL", "FALLBACK"})
    if contains_any(text, ["data", "bi", "dashboard", "analytics", "数据", "看板", "指标"]):
        require("productProfile indicates a data product but no METRIC, SOURCE, or DATA annotationType is present", {"METRIC", "SOURCE", "DATA"})
    if contains_any(text, ["saas", "multi_tenant", "多租户"]):
        require("productProfile indicates a SaaS product but no ROLE, PLAN, or TENANT annotationType is present", {"ROLE", "PLAN", "TENANT"})
    if contains_any(text, ["enterprise", "admin", "workflow", "approval", "b端", "企业", "后台", "审批"]):
        require("productProfile indicates an enterprise/workflow product but no PERM, WF, R, or S annotationType is present", {"PERM", "WF", "R", "S"})
    return len(errors), errors + warnings


def page_key_for_html(html_path: Path, root_dir: Path, data: dict) -> str | None:
    try:
        rel = str(html_path.relative_to(root_dir))
    except ValueError:
        rel = html_path.name
    name = html_path.name
    for page in data.get("pages", []):
        page_path = str(page.get("path") or "")
        if page_path == rel or page_path == name or page_path.endswith("/" + name):
            return str(page.get("pageKey") or "") or None
    return None


def expected_snapshot_ids(data: dict, page_key: str | None) -> tuple[set[str], set[str], set[str]]:
    pages = data.get("pages") or []
    annotations = data.get("annotations") or []
    surfaces = data.get("surfaces") or []
    if page_key:
        pages = [page for page in pages if page.get("pageKey") == page_key]
        annotations = [ann for ann in annotations if ann.get("pageKey") == page_key]
        surfaces = [surface for surface in surfaces if surface.get("pageKey") == page_key]
    return (
        {str(page.get("pageKey")) for page in pages if page.get("pageKey")},
        {str(ann.get("id")) for ann in annotations if ann.get("id")},
        {str(surface.get("id")) for surface in surfaces if surface.get("id")},
    )


def validate_inline_snapshots(root_dir: Path, html_files: list[Path], data: dict, strict_quality: bool) -> tuple[int, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for html_file in html_files:
        html = html_file.read_text(encoding="utf-8", errors="ignore")
        match = INLINE_DATA_RE.search(html)
        if not match:
            continue
        try:
            inline = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            add_quality_message(warnings, errors, f"{html_file}: inline prototype-annotations-data is invalid JSON", strict_quality)
            continue
        page_key = page_key_for_html(html_file, root_dir, data)
        expected_pages, expected_annotations, expected_surfaces = expected_snapshot_ids(data, page_key)
        actual_pages = {str(page.get("pageKey")) for page in inline.get("pages", []) if page.get("pageKey")}
        actual_annotations = {str(ann.get("id")) for ann in inline.get("annotations", []) if ann.get("id")}
        actual_surfaces = {str(surface.get("id")) for surface in inline.get("surfaces", []) if surface.get("id")}
        if (
            actual_pages != expected_pages
            or actual_annotations != expected_annotations
            or actual_surfaces != expected_surfaces
        ):
            message = (
                f"{html_file}: inline prototype-annotations-data is stale "
                f"(pages {len(actual_pages)}/{len(expected_pages)}, "
                f"annotations {len(actual_annotations)}/{len(expected_annotations)}, "
                f"surfaces {len(actual_surfaces)}/{len(expected_surfaces)})"
            )
            add_quality_message(warnings, errors, message, strict_quality)
    return len(errors), errors + warnings


def validate_surface_definitions(data: dict, strict_quality: bool) -> tuple[int, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    grouped_by_open: dict[tuple[str, str], list[dict]] = {}
    for surface in data.get("surfaces") or []:
        if not isinstance(surface, dict):
            continue
        surface_id = str(surface.get("id") or "<missing surface id>")
        surface_name = str(surface.get("name") or "")
        open_selector = str(surface.get("openSelector") or "").strip()
        if is_technical_surface_name(surface):
            add_quality_message(
                warnings,
                errors,
                f"{surface_id}: surface.name must be a product-readable label, not a technical id ({surface_name or '<empty>'})",
                strict_quality,
            )
        if has_compound_title_text(surface) and not surface_has_non_title_signature(surface):
            add_quality_message(
                warnings,
                errors,
                f"{surface_id}: titleText uses a compound label; use an array of actual rendered titles or add textIncludes/stateText/contentSelector to distinguish surface modes",
                strict_quality,
            )
        if SURFACE_PART_RE.search(" ".join([surface_id, surface_name])):
            add_quality_message(
                warnings,
                errors,
                f"{surface_id}: header/body/footer/title/content should not be registered as a top-level surface",
                strict_quality,
            )
        if not str(surface.get("triggerSelector") or "").strip():
            add_quality_message(
                warnings,
                errors,
                f"{surface_id}: surface is missing triggerSelector; internal annotations cannot guide users to open the right UI",
                strict_quality,
            )
        trigger_selector = str(surface.get("triggerSelector") or "").strip()
        if len(selector_parts(trigger_selector)) > 1:
            add_quality_message(
                warnings,
                errors,
                f"{surface_id}: triggerSelector contains multiple selectors; split distinct business drawers/modals into separate surfaces instead of merging triggers",
                strict_quality,
            )
        if open_selector:
            grouped_by_open.setdefault((str(surface.get("pageKey") or ""), open_selector), []).append(surface)
    for (_page_key, open_selector), surfaces in grouped_by_open.items():
        if len(surfaces) <= 1:
            continue
        missing_signature = [
            str(surface.get("id") or "<missing surface id>")
            for surface in surfaces
            if not surface_has_content_signature(surface)
        ]
        if missing_signature:
            add_quality_message(
                warnings,
                errors,
                f"Multiple surfaces share openSelector {open_selector}; add contentSelector/titleText/textIncludes to distinguish: {', '.join(missing_signature[:8])}",
                strict_quality,
            )
    return len(errors), errors + warnings


def framework_source_text(root: Path) -> str:
    src = root / "src"
    if not src.exists():
        return ""
    chunks: list[str] = []
    for path in src.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx", ".vue"}:
            continue
        if "prototype-annotator" in path.parts:
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(chunks)


def validate_framework_page_key_mapping(data: dict, root: Path, strict_quality: bool) -> tuple[int, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    pages = data.get("pages") if isinstance(data.get("pages"), list) else []
    if len(pages) <= 1:
        return 0, []
    source_text = framework_source_text(root)
    if not source_text:
        return 0, []
    for page in pages:
        page_key = str(page.get("pageKey") or "").strip()
        route = str(page.get("route") or "").strip()
        if not page_key:
            continue
        if page_key in source_text:
            continue
        if route and route != "/" and route in source_text:
            continue
        add_quality_message(
            warnings,
            errors,
            f"{page_key}: pageKey/route is not referenced by React/Vue source; ensure PrototypeAnnotatorProvider maps this route explicitly",
            strict_quality,
        )
    return len(errors), errors + warnings


def validate_delivery_content(ann: dict) -> list[str]:
    ann_id = str(ann.get("id") or "<missing id>")
    content = str(ann.get("contentMarkdown") or "")
    compact_content = normalize_quality_key(content)
    open_questions = ann.get("openQuestions") if isinstance(ann.get("openQuestions"), list) else []
    open_question_text = normalize_quality_key(" ".join(str(item) for item in open_questions))
    kind = str(ann.get("kind") or "")
    dimension = str(ann.get("dimension") or "")
    priority = str(ann.get("priority") or "")
    messages: list[str] = []

    annotation_type = str(ann.get("annotationType") or "")
    if dimension == "Page overview" or (annotation_type == "P" and not str(ann.get("surfaceId") or "").strip()):
        missing_headings = [
            heading
            for heading in PAGE_OVERVIEW_REQUIRED_HEADINGS
            if f"###{heading}" not in compact_content
        ]
        if missing_headings:
            messages.append(
                f"{ann_id}: page overview should use the required sections: "
                + "、".join(PAGE_OVERVIEW_REQUIRED_HEADINGS)
            )
        return messages

    if dimension == "Primary action" and not has_any(compact_content, ["交互规则", "页面流转", "点击后", "成功", "失败", "待确认"]):
        messages.append(f"{ann_id}: primary action should describe click result, downstream flow, success/failure handling, or mark it as pending confirmation")
    if (kind == "form" or has_topic(ann, "field-rule")) and not has_any(compact_content, ["字段规则", "校验", "必填", "默认值", "选项来源", "错误反馈", "待确认"]):
        messages.append(f"{ann_id}: form annotation should include field meaning, required/default/validation/option-source rules, or mark them pending")
    if (kind == "state" or has_topic(ann, "state")) and not has_any(compact_content, ["状态与异常", "触发条件", "切换", "空", "加载", "失败", "无权限", "待确认"]):
        messages.append(f"{ann_id}: state annotation should explain state meaning, trigger, transition, exception handling, or mark it pending")
    if (dimension == "Flow and navigation" or has_topic(ann, "flow")) and not has_any(compact_content, ["页面流转", "来源", "目标", "返回", "弹窗", "抽屉", "下一步", "待确认"]):
        messages.append(f"{ann_id}: flow annotation should explain source/target/return path or mark it pending")
    if (kind == "permission" or has_topic(ann, "risk")) and priority not in {"high", "medium"}:
        messages.append(f"{ann_id}: risk or permission annotation should use medium or high priority")
    if (kind == "permission" or has_topic(ann, "risk")) and not has_any(compact_content, ["风险提示", "权限", "二次确认", "不可逆", "撤销", "审计", "待确认"]):
        messages.append(f"{ann_id}: risk or permission annotation should explain impact, confirmation, permission boundary, rollback/audit, or mark it pending")
    target = ann.get("target") if isinstance(ann.get("target"), dict) else {}
    selector = str(target.get("selector") or ann.get("selector") or "")
    if dimension == "Table row actions" and is_single_action_selector(selector):
        messages.append(f"{ann_id}: table row action group should anchor to the action group container or action cell, not a single icon/button")
    if source_type_of(ann) in {"prototype", "ai-inference", "local-rule-draft"} and not has_any(compact_content + open_question_text, ["待确认", "根据原型结构推断", "需确认"]):
        messages.append(f"{ann_id}: inferred annotation should keep a pending-confirmation note")
    return messages


def validate_quality(data: dict, strict_quality: bool) -> tuple[int, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    annotations_by_page: dict[str, list[dict]] = {}
    for ann in data.get("annotations", []):
        page_key = ann.get("pageKey")
        if page_key:
            annotations_by_page.setdefault(str(page_key), []).append(ann)

    for page_key, annotations in annotations_by_page.items():
        repeated_content: dict[tuple[str, str, str], list[str]] = {}
        repeated_row_actions: dict[str, list[str]] = {}
        fragile_selector_ids: list[str] = []
        id_numbers = sorted(
            number
            for number in (annotation_id_number(ann, page_key) for ann in annotations)
            if number is not None
        )
        if id_numbers:
            expected = list(range(1, len(id_numbers) + 1))
            if id_numbers != expected:
                missing = [str(number) for number in expected if number not in id_numbers]
                add_quality_message(
                    warnings,
                    errors,
                    f"{page_key}: annotation id sequence has gaps; runtime display numbers must remain continuous and report should distinguish displayNo from stable id. Missing display ids: {', '.join(missing[:12]) or 'none'}",
                    strict_quality,
                )
        auto_approved_ai = [
            str(ann.get("id") or "<missing id>")
            for ann in annotations
            if str(ann.get("createdBy") or "") == "ai"
            and isinstance(ann.get("review"), dict)
            and ann.get("review", {}).get("required") is False
            and str(ann.get("review", {}).get("status") or "") == "approved"
        ]
        if auto_approved_ai:
            add_quality_message(
                warnings,
                errors,
                f"{page_key}: AI annotations bypass review.required/status gate. Examples: {', '.join(auto_approved_ai[:8])}",
                strict_quality,
            )
        page_overviews = [
            ann for ann in annotations
            if not ann.get("surfaceId")
            and (
                ann.get("dimension") == "Page overview"
                or "页面介绍" in str(ann.get("title") or "")
                or "页面功能" in str(ann.get("contentMarkdown") or "")
            )
        ]
        if len(page_overviews) != 1:
            add_quality_message(
                warnings,
                errors,
                f"{page_key}: expected exactly one page overview annotation, found {len(page_overviews)}",
                strict_quality,
            )
        for ann in annotations:
            ann_id = str(ann.get("id") or "<missing id>")
            target = ann.get("target") if isinstance(ann.get("target"), dict) else {}
            title = normalize_quality_key(str(ann.get("title") or ""))
            fallback = normalize_quality_key(str(target.get("fallbackText") or ""))
            content = normalize_quality_key(str(ann.get("contentMarkdown") or ""))[:160]
            if title or fallback or content:
                repeated_content.setdefault((title, fallback, content), []).append(ann_id)
            selector = str(target.get("selector") or ann.get("selector") or "")
            if is_table_row_selector(selector) and fallback:
                repeated_row_actions.setdefault(fallback, []).append(ann_id)
            selector_quality = ann.get("selectorQuality") if isinstance(ann.get("selectorQuality"), dict) else {}
            selector_is_stable = selector.startswith("#") or "[data-" in selector or "aria-label" in selector
            if selector_quality.get("level") == "fragile" and not selector_is_stable:
                fragile_selector_ids.append(ann_id)
            is_page_overview = ann.get("dimension") == "Page overview" or "页面介绍" in str(ann.get("title") or "")
            if not is_page_overview and UNSTABLE_SELECTOR_RE.search(selector):
                fragile_selector_ids.append(ann_id)
            for message in validate_delivery_content(ann):
                add_quality_message(warnings, errors, message, strict_quality)
            content_md = str(ann.get("contentMarkdown") or "")
            for pattern in GENERIC_TEMPLATE_PATTERNS:
                if pattern in content_md:
                    add_quality_message(
                        warnings,
                        errors,
                        f"{ann_id}: content uses generic template text instead of element-specific product facts: {pattern}",
                        strict_quality,
                    )
            if is_close_like_annotation(ann):
                close_compact = normalize_quality_key(content_md)
                bad_terms = [term for term in DISALLOWED_CLOSE_ACTION_TERMS if normalize_quality_key(term) in close_compact]
                if "保存" in bad_terms and any(token in close_compact for token in ["不保存", "不会保存", "不提交或保存", "不提交不保存"]):
                    bad_terms = [term for term in bad_terms if term != "保存"]
                if "提交" in bad_terms and any(token in close_compact for token in ["不提交", "不会提交", "不提交或保存", "不提交不保存"]):
                    bad_terms = [term for term in bad_terms if term != "提交"]
                if bad_terms:
                    add_quality_message(
                        warnings,
                        errors,
                        f"{ann_id}: close/cancel annotation should not describe submit/save/validation behavior without explicit evidence: {', '.join(bad_terms)}",
                        strict_quality,
                    )
            if content_md and not any(heading in content_md for heading in STRUCTURED_MARKDOWN_HEADINGS):
                warnings.append(
                    f"WARNING: {ann_id} contentMarkdown 缺少结构化 Markdown 标题，建议补充 ### 业务含义 等小节。"
                )
        for ids in repeated_content.values():
            if len(ids) > 1:
                add_quality_message(
                    warnings,
                    errors,
                    f"{page_key}: duplicate annotation meaning across {len(ids)} annotations ({', '.join(ids[:6])})",
                    strict_quality,
                )
        for action_text, ids in repeated_row_actions.items():
            if len(ids) > 1:
                add_quality_message(
                    warnings,
                    errors,
                    f"{page_key}: 当前页面存在多个重复的行级操作标注「{action_text}」，建议合并为「行级操作组」标注 ({', '.join(ids[:6])})",
                    strict_quality,
                )
        row_action_titles = [
            ann for ann in annotations
            if ROW_ACTION_TEXT_RE.search(str(ann.get("title") or ""))
            and ann.get("dimension") != "Table row actions"
            and is_table_row_selector(str((ann.get("target") or {}).get("selector") or ""))
        ]
        if len(row_action_titles) > 2:
            ids = [str(ann.get("id") or "") for ann in row_action_titles[:8]]
            warnings.append(
                f"WARNING: {page_key}: 当前页面存在多个重复的行级操作标注，建议合并为「行级操作组」标注 ({', '.join(ids)})"
            )
        if fragile_selector_ids:
            add_quality_message(
                warnings,
                errors,
                f"{page_key}: {len(set(fragile_selector_ids))} fragile selector(s) should be replaced with data-ann or data-testid when possible. "
                f"Examples: {', '.join(list(dict.fromkeys(fragile_selector_ids))[:6])}",
                strict_quality,
            )

    return len(errors), errors + warnings


def validate_product_language(
    data: dict,
    lint_language: str | None,
    strict_quality: bool,
) -> tuple[int, list[str]]:
    if lint_language != "product-review":
        return 0, []
    errors: list[str] = []
    warnings: list[str] = []
    audience_mode = str(data.get("audienceMode") or "product-review").strip()
    for ann in data.get("annotations", []):
        ann_id = str(ann.get("id") or "<missing id>")
        ann_audience = str(ann.get("audienceMode") or audience_mode).strip()
        if ann_audience != "product-review":
            continue
        content = str(ann.get("contentMarkdown") or "")
        lowered = content.lower()
        for term in PRODUCT_REVIEW_BANNED_TERMS:
            if term.lower() in lowered:
                message = f"WARNING: {ann_id} 内容偏技术实现语言，建议改写为产品经理语言。（命中：{term}）"
                if strict_quality:
                    errors.append(message.replace("WARNING: ", ""))
                else:
                    warnings.append(message)
                break
        for term in PRODUCT_REVIEW_GENERIC_TERMS:
            if term in content:
                warnings.append(f"WARNING: {ann_id} 内容偏泛化表达，建议补充更具体的业务说明。（命中：{term}）")
                break
    if lint_language == "product-review" and not data.get("productContext"):
        warnings.append("WARNING: annotations.json 缺少 productContext，产品语境可能不完整。")
    return len(errors), errors + warnings


def validate(
    target: Path,
    annotation_path: Path,
    mode: str = "auto",
    page_map_path: Path | None = None,
    allow_empty_pages: bool = False,
    strict_quality: bool = False,
    fail_on_pending_review: bool = False,
    dev_handoff: bool = False,
    lint_language: str | None = None,
    deploy_check: bool = False,
) -> Tuple[int, List[str]]:
    data = load_data(annotation_path)
    root_dir, html_files = find_html_files(target)
    html_by_rel = {str(path.relative_to(root_dir)): path for path in html_files}
    page_map_file = page_map_path or page_map_file_for(target)
    if page_map_file.exists():
        page_map_data = load_data(page_map_file)
    else:
        page_map_data = {}
    page_paths = page_path_map(target, page_map_data) or page_path_map(target, data)
    nodes_by_page: Dict[str, list] = {}
    page_map_paths: Dict[str, str] = {}
    errors: List[str] = []
    warnings: List[str] = []
    pending_review_ids: list[str] = []
    local_draft_ids: list[str] = []
    framework = detect_framework(target)
    use_rendered_page_map = mode == "rendered" or (mode == "auto" and framework in {"react", "vue"})
    annotation_counts: dict[str, int] = {}
    page_type_p_counts: dict[str, int] = {}
    enabled_types = product_profile_enabled_types(data)
    surfaces = surfaces_by_id(data)

    if use_rendered_page_map:
        resolved_page_map = page_map_path or page_map_file_for(target)
        if not resolved_page_map.exists():
            errors.append(
                f"Missing rendered page-map for {framework} project: {resolved_page_map}. "
                "Run scripts/scan_rendered_routes.mjs against a running dev server first."
            )
        else:
            nodes_by_page, page_map_paths = load_page_map_nodes(resolved_page_map)
        mapping_error_count, mapping_messages = validate_framework_page_key_mapping(data, root_dir, strict_quality)
        if mapping_error_count:
            errors.extend(mapping_messages[:mapping_error_count])
            warnings.extend(mapping_messages[mapping_error_count:])
        else:
            warnings.extend(mapping_messages)

    ids = set()
    for ann in data.get("annotations", []):
        ann_id = ann.get("id")
        if not ann_id:
            errors.append("Annotation is missing id.")
        elif ann_id in ids:
            errors.append(f"Duplicate annotation id: {ann_id}")
        else:
            ids.add(ann_id)

        page_key = ann.get("pageKey")
        if not page_key:
            errors.append(f"{ann_id or '<missing id>'}: missing pageKey")
            continue
        annotation_counts[page_key] = annotation_counts.get(page_key, 0) + 1
        annotation_type = str(ann.get("annotationType") or "").strip()
        if not annotation_type:
            add_quality_message(
                warnings,
                errors,
                f"{ann_id}: missing annotationType",
                strict_quality,
            )
        elif annotation_type not in VALID_ANNOTATION_TYPES:
            errors.append(f"{ann_id}: invalid annotationType {annotation_type}")
        else:
            if annotation_type == "P" and not str(ann.get("surfaceId") or "").strip():
                page_type_p_counts[page_key] = page_type_p_counts.get(page_key, 0) + 1
            if enabled_types and annotation_type not in enabled_types:
                add_quality_message(
                    warnings,
                    errors,
                    f"{ann_id}: annotationType {annotation_type} is not enabled by productProfile.enabledAnnotationTypes",
                    strict_quality,
                )
        if page_key not in page_paths:
            errors.append(f"{ann_id}: unknown pageKey {page_key}")
            continue

        if not ann.get("title"):
            errors.append(f"{ann_id}: missing title")
        if not ann.get("contentMarkdown"):
            errors.append(f"{ann_id}: missing contentMarkdown")
        evidence = ann.get("evidence")
        if evidence is not None and not isinstance(evidence, list):
            warnings.append(f"{ann_id}: evidence should be a list")
        source = ann.get("source") if isinstance(ann.get("source"), dict) else {}
        review = ann.get("review") if isinstance(ann.get("review"), dict) else {}
        if source.get("type") == "local-rule-draft":
            local_draft_ids.append(str(ann_id))
        if review.get("required") and review.get("status") in {None, "", "pending"}:
            pending_review_ids.append(str(ann_id))

        page_path = page_paths[page_key]
        if use_rendered_page_map:
            if page_key not in nodes_by_page:
                warnings.append(f"{ann_id}: pageKey {page_key} not found in rendered page-map")
                continue
            if not nodes_by_page[page_key]:
                warnings.append(f"{ann_id}: rendered page-map has no elements for {page_key} ({page_map_paths.get(page_key) or page_path})")
        else:
            html_path = html_by_rel.get(page_path)
            if not html_path and target.is_file() and page_path == target.name:
                html_path = target
            if not html_path:
                warnings.append(f"{ann_id}: page HTML not found for {page_key} ({page_path})")
                continue

            if page_key not in nodes_by_page:
                page_index = list(page_paths.keys()).index(page_key) + 1
                nodes_by_page[page_key] = scan_html(html_path, root_dir, page_index).get("elements", [])

        selector = ((ann.get("target") or {}).get("selector") or ann.get("selector") or "").strip()
        if not selector:
            errors.append(f"{ann_id}: missing target.selector")
        else:
            surface_id = str(ann.get("surfaceId") or "").strip()
            nodes = nodes_by_page.get(page_key) or []
            matched_nodes = selector_matched_nodes(selector, nodes)
            html_path_for_count = None
            if not use_rendered_page_map:
                html_path_for_count = html_by_rel.get(page_paths.get(page_key, ""))
                if not html_path_for_count and target.is_file() and page_paths.get(page_key) == target.name:
                    html_path_for_count = target
            match_count = simple_selector_match_count(html_path_for_count, selector)
            if match_count and match_count > 1 and is_close_like_annotation(ann):
                add_quality_message(
                    warnings,
                    errors,
                    f"{ann_id}: close/cancel selector matches {match_count} elements; use a footer/header-specific selector or stable data-ann/id ({selector})",
                    strict_quality,
                )
            if surface_id:
                surface_errors, surface_warnings = validate_surface_annotation(
                    ann,
                    surfaces=surfaces,
                    nodes=nodes,
                    strict_quality=strict_quality,
                )
                errors.extend(surface_errors)
                warnings.extend(surface_warnings)
                if not selector_matches(selector, nodes):
                    if str(ann.get("displayWhenClosed") or "").strip() not in {"sidebar-only", "hidden-until-open"}:
                        if strict_quality:
                            errors.append(f"{ann_id}: selector did not match {page_path}: {selector}")
                        elif not any("needs-interaction-plan-scan" in item for item in surface_warnings):
                            warnings.append(f"WARNING: {ann_id}: selector did not match {page_path}: {selector}")
            elif not selector_matches(selector, nodes):
                errors.append(f"{ann_id}: selector did not match {page_path}: {selector}")
            elif matched_nodes and not selector_matches_visible(selector, nodes):
                add_quality_message(
                    warnings,
                    errors,
                    f"{ann_id}: selector matches hidden content but annotation has no surfaceId ({selector}); move it to a surface or anchor it to the trigger",
                    strict_quality,
                )
            elif not ann.get("surfaceId") and is_toast_like_annotation(ann):
                warnings.append(
                    f"WARNING: {ann_id}: toast/message-like annotation should be merged into trigger action state/exception instead of standalone badge"
                )

    for page in data.get("pages", []):
        page_key = page.get("pageKey")
        if not page_key:
            continue
        if annotation_counts.get(page_key, 0) == 0:
            message = f"{page_key}: page has no annotations ({page.get('route') or page.get('path') or page.get('title') or 'unknown route'})"
            if allow_empty_pages:
                warnings.append(message)
            else:
                errors.append(message)
        if page_type_p_counts.get(page_key, 0) == 0:
            add_quality_message(
                warnings,
                errors,
                f"{page_key}: page has no annotationType=P page overview annotation",
                strict_quality,
            )
        if use_rendered_page_map and page_key in nodes_by_page and not nodes_by_page[page_key]:
            message = f"{page_key}: rendered page-map has no elements ({page.get('route') or page.get('path') or page.get('title') or 'unknown route'})"
            if allow_empty_pages:
                warnings.append(message)
            else:
                errors.append(message)
        if use_rendered_page_map and page_key in nodes_by_page:
            route = str(page.get("route") or page.get("path") or "")
            text = " ".join(str(node.get("text") or "") for node in nodes_by_page.get(page_key, []))
            has_dynamic_route = bool(re.search(r"/[^/]+/[A-Za-z0-9_-]+", route))
            if has_dynamic_route and NOT_FOUND_TEXT_RE.search(text):
                add_quality_message(
                    warnings,
                    errors,
                    f"{page_key}: rendered dynamic route appears to be a not-found page ({route}); use a real sample id before generating annotations",
                    strict_quality,
                )

    if local_draft_ids:
        message = f"{len(local_draft_ids)} local-rule-draft annotation(s) require AI or manual review. Examples: {', '.join(local_draft_ids[:8])}"
        if fail_on_pending_review:
            errors.append(message)
        else:
            warnings.append(message)
    if pending_review_ids:
        message = f"{len(pending_review_ids)} annotation(s) are still pending review. Examples: {', '.join(pending_review_ids[:8])}"
        if fail_on_pending_review:
            errors.append(message)
        else:
            warnings.append(message)

    quality_error_count, quality_messages = validate_quality(data, strict_quality)
    product_error_count, product_messages = validate_product_type_coverage(data, strict_quality)
    language_error_count, language_messages = validate_product_language(data, lint_language, strict_quality)
    surface_error_count, surface_messages = validate_surface_definitions(data, strict_quality)
    deploy_error_count, deploy_messages = validate_deploy_assets(
        data,
        root_dir,
        annotation_path,
        framework=framework,
        deploy_check=deploy_check,
    )
    static_deploy_error_count = 0
    static_deploy_messages: list[str] = []
    if framework == "html":
        static_deploy_error_count, static_deploy_messages = validate_static_runtime_assets(
            root_dir,
            html_files,
            annotation_path,
            deploy_check=deploy_check,
        )
    inline_error_count = 0
    inline_messages: list[str] = []
    if framework == "html":
        inline_error_count, inline_messages = validate_inline_snapshots(root_dir, html_files, data, strict_quality)

    dev_handoff_active = dev_handoff or is_dev_handoff_mode(data)
    if dev_handoff_active:
        candidates_path = candidates_file_for(target)
        if not candidates_path.exists():
            errors.append(
                f"Missing annotation-candidates.json for dev-handoff validation: {candidates_path}. "
                "Run scripts/build_annotation_candidates.py first."
            )
        else:
            _, dev_errors, dev_warnings = validate_dev_handoff(
                data,
                candidates=load_dev_json(candidates_path),
                as_errors=True,
            )
            errors.extend(dev_errors)
            warnings.extend(dev_warnings)

    return (
        len(errors)
        + quality_error_count
        + product_error_count
        + language_error_count
        + surface_error_count
        + deploy_error_count
        + static_deploy_error_count
        + inline_error_count,
        errors
        + quality_messages
        + product_messages
        + language_messages
        + surface_messages
        + deploy_messages
        + static_deploy_messages
        + inline_messages
        + warnings,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Prototype Annotator annotations.")
    parser.add_argument("prototype_path", help="HTML file or static directory")
    parser.add_argument("--annotations", help="Path to annotations.json")
    parser.add_argument("--page-map", help="Path to rendered prototype-annotator/page-map.json")
    parser.add_argument("--mode", choices=["auto", "html", "rendered"], default="auto", help="Validation mode. auto uses rendered page-map for React/Vue projects.")
    parser.add_argument("--allow-empty-pages", dest="allow_empty_pages", action="store_true", default=False, help="Allow pages with no annotations or no scanned rendered elements.")
    parser.add_argument("--require-page-annotations", dest="allow_empty_pages", action="store_false", help="Fail when any declared page has no annotations. This is the default.")
    parser.add_argument("--strict-quality", action="store_true", help="Fail on repeated semantic annotations, repeated table row actions, and other quality issues.")
    parser.add_argument("--fail-on-pending-review", action="store_true", help="Fail when generated local-rule-draft annotations or pending review annotations remain.")
    parser.add_argument(
        "--dev-handoff",
        action="store_true",
        help="Apply研发交付门禁：候选转正、页面密度、锚点精度、占位正文、review.required 等。也可由 productProfile.annotationMode=dev-handoff 自动启用。",
    )
    parser.add_argument(
        "--lint-language",
        choices=["product-review"],
        help="Check annotation copy for product-manager language quality.",
    )
    parser.add_argument(
        "--deploy-check",
        action="store_true",
        help="Fail when static HTML runtime files or Vite/public deploy copies are missing or stale.",
    )
    args = parser.parse_args()

    target = Path(args.prototype_path).resolve()
    if not target.exists():
        parser.error(f"Path does not exist: {target}")
    annotation_path = Path(args.annotations).resolve() if args.annotations else annotation_file_for(target)
    if not annotation_path.exists():
        parser.error(f"Annotation file does not exist: {annotation_path}")

    page_map_path = Path(args.page_map).resolve() if args.page_map else None
    error_count, messages = validate(
        target,
        annotation_path,
        args.mode,
        page_map_path,
        args.allow_empty_pages,
        args.strict_quality,
        args.fail_on_pending_review,
        args.dev_handoff,
        args.lint_language,
        args.deploy_check,
    )
    if messages:
        for message in messages:
            print(message)
    if error_count:
        print(f"Validation failed with {error_count} error(s).")
        return 1
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
