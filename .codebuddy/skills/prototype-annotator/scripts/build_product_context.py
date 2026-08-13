#!/usr/bin/env python3
"""Build product-context.json from PRD/docs and page-map scan results."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ANNOTATION_DIR_NAME = "prototype-annotator"
LEGACY_ANNOTATION_DIR_NAME = ".prototype-annotations"
ROLE_HEADINGS = re.compile(r"^(?:#+\s*)?(?:用户角色|角色|使用者|目标用户)", re.I | re.M)
FLOW_HEADINGS = re.compile(r"^(?:#+\s*)?(?:核心流程|业务流程|使用流程|主流程)", re.I | re.M)
PRODUCT_NAME_RE = re.compile(r"^#\s+(.+?)(?:\s+PRD)?\s*$", re.M)


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
    return annotation_root(target) / ANNOTATION_DIR_NAME / "product-context.json"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract_product_name(text: str) -> str:
    match = PRODUCT_NAME_RE.search(text)
    if match:
        return normalize(match.group(1))
    for line in text.splitlines():
        line = normalize(line.lstrip("# ").strip())
        if line and len(line) <= 60:
            return line
    return ""


def is_placeholder_doc(text: str) -> bool:
    lowered = text.lower()
    placeholders = [
        "welcome to your lovable project",
        "todo: document your project here",
        "this is a vite project",
        "react + typescript + vite",
    ]
    return any(item in lowered for item in placeholders)


def candidate_texts_from_page_map(page_map: dict) -> list[str]:
    texts: list[str] = []
    for page in page_map.get("pages", []):
        if not isinstance(page, dict):
            continue
        for element in page.get("elements", [])[:40]:
            if not isinstance(element, dict):
                continue
            attrs = element.get("attrs") if isinstance(element.get("attrs"), dict) else {}
            for value in (
                element.get("text"),
                attrs.get("title"),
                attrs.get("aria-label"),
                attrs.get("placeholder"),
            ):
                text = normalize(str(value or ""))
                if text:
                    texts.append(text)
    return texts


def extract_product_name_from_page_map(page_map: dict) -> str:
    nav_words = ["首页", "场景中心", "能力市场", "知识广场", "Agent广场", "提效案例", "管理后台"]
    scored: dict[str, int] = {}
    for text in candidate_texts_from_page_map(page_map):
        text = re.sub(r"^notifications\s+alt\+t\s*", "", text, flags=re.I).strip()
        if re.search(r"搜索|筛选|请输入|请选择|占位|placeholder|…|\.\.\.", text, re.I):
            continue
        for nav_word in nav_words:
            marker = f" {nav_word}"
            if marker in text:
                text = text.split(marker, 1)[0].strip()
                break
        if not (4 <= len(text) <= 80):
            continue
        if not re.search(r"平台|系统|中心|后台|console|portal|enterprise|ai|agent|copilot", text, re.I):
            continue
        if sum(1 for word in nav_words if word in text) >= 3:
            continue
        score = 1
        if re.search(r"平台|系统|后台", text):
            score += 5
        if re.search(r"enterprise|ai|agent", text, re.I):
            score += 2
        if re.search(r"[\u4e00-\u9fff]", text) and re.search(r"[A-Za-z]", text):
            score += 1
        scored[text] = scored.get(text, 0) + score
    if not scored:
        return ""
    return sorted(scored.items(), key=lambda item: (-item[1], len(item[0])))[0][0]


def extract_roles(text: str) -> list[str]:
    roles: list[str] = []
    match = ROLE_HEADINGS.search(text)
    if not match:
        return roles
    section = text[match.end() :]
    next_heading = re.search(r"\n#+\s", section)
    if next_heading:
        section = section[: next_heading.start()]
    for line in section.splitlines():
        line = normalize(line)
        if not line:
            continue
        bullet = re.match(r"^[-*•]\s*(.+?)(?:[：:].*)?$", line)
        numbered = re.match(r"^\d+[.)]\s*(.+?)(?:[：:].*)?$", line)
        if bullet:
            roles.append(normalize(bullet.group(1)))
        elif numbered:
            roles.append(normalize(numbered.group(1)))
        elif "：" in line or ":" in line:
            name = re.split(r"[：:]", line, maxsplit=1)[0].strip()
            if name:
                roles.append(name)
    return roles[:12]


def extract_flows(text: str) -> list[dict]:
    flows: list[dict] = []
    match = FLOW_HEADINGS.search(text)
    if not match:
        return flows
    section = text[match.end() :]
    next_heading = re.search(r"\n#+\s", section)
    if next_heading:
        section = section[: next_heading.start()]
    steps = []
    for line in section.splitlines():
        line = normalize(line)
        if not line:
            continue
        numbered = re.match(r"^\d+[.)]\s*(.+)$", line)
        bullet = re.match(r"^[-*•]\s*(.+)$", line)
        if numbered:
            steps.append(normalize(numbered.group(1)))
        elif bullet:
            steps.append(normalize(bullet.group(1)))
    if steps:
        flows.append({"name": "核心流程", "entry": "", "steps": steps[:20]})
    return flows


def infer_product_type(text: str) -> str:
    lowered = text.lower().replace("interaction-plan", "")
    ai_hits = len(re.findall(r"\bai\b|agent|copilot|prompt|提示词|智能体|智能生成|智能推荐|智能审核|大模型", lowered, re.I))
    enterprise_hits = len(re.findall(r"/admin|后台|管理|审核|审批|权限|角色|enterprise|b端|企业|review|settings|users", lowered, re.I))
    data_hits = len(re.findall(r"指标|看板|报表|图表|analytics|metric|数据来源|刷新频率", lowered, re.I))
    saas_hits = len(re.findall(r"\bsaas\b|多租户|租户|套餐|订阅套餐|\btenant\b|\bplan\b", lowered, re.I))
    if ai_hits >= 2 and enterprise_hits >= 3:
        return "ai_enterprise_app"
    if ai_hits >= 2:
        return "ai_product"
    if enterprise_hits >= 3:
        return "enterprise_app"
    if data_hits >= 4:
        return "data_product"
    if saas_hits >= 2:
        return "saas"
    return "general"


def product_forms_for(product_type: str) -> list[str]:
    mapping = {
        "ai_enterprise_app": ["B端应用", "AI产品"],
        "ai_product": ["AI产品"],
        "enterprise_app": ["B端应用"],
        "data_product": ["数据产品"],
        "saas": ["SaaS产品"],
    }
    return mapping.get(product_type, ["通用产品"])


def enabled_types_for(product_forms: list[str]) -> list[str]:
    enabled = ["P", "E", "C", "A", "J", "S", "R", "PERM", "DATA"]
    forms = " ".join(product_forms)
    if "AI" in forms:
        enabled.extend(["AI", "PROMPT", "CTX", "HITL", "FALLBACK"])
    if "数据" in forms:
        enabled.extend(["METRIC", "SOURCE", "FILTER", "REFRESH", "DRILL"])
    if "SaaS" in forms:
        enabled.extend(["ROLE", "PLAN", "TENANT"])
    result: list[str] = []
    for item in enabled:
        if item not in result:
            result.append(item)
    return result


def page_map_text(page_map: dict) -> str:
    parts: list[str] = []
    for page in page_map.get("pages", []):
        if not isinstance(page, dict):
            continue
        parts.extend([str(page.get("title") or ""), str(page.get("route") or ""), str(page.get("path") or "")])
        for element in page.get("elements", [])[:80]:
            if not isinstance(element, dict):
                continue
            attrs = element.get("attrs") if isinstance(element.get("attrs"), dict) else {}
            parts.extend(
                [
                    str(element.get("text") or ""),
                    str(attrs.get("placeholder") or ""),
                    str(attrs.get("title") or ""),
                    str(attrs.get("aria-label") or ""),
                ]
            )
    return "\n".join(part for part in parts if part)


def infer_page_purpose(page: dict, product_name: str) -> str:
    title = normalize(str(page.get("title") or page.get("route") or page.get("pageKey") or "当前页面"))
    if product_name:
        return f"帮助用户在 {product_name} 中完成与「{title}」相关的业务操作。"
    return f"帮助用户完成与「{title}」相关的业务任务。"


def compact_label(value: str, limit: int = 24) -> str:
    text = normalize(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def infer_primary_tasks(candidates: list[dict]) -> list[str]:
    tasks: list[str] = []
    seen: set[str] = set()
    priority_dims = ("Primary action", "AI and automation", "Form and validation", "Table and list", "State and exception")
    skip_patterns = re.compile(r"适合说明|候选|默认|字段，|区域，|元素", re.I)
    for dim in priority_dims:
        for item in candidates:
            if item.get("dimension") != dim:
                continue
            label = compact_label(str(item.get("fallbackText") or ""), 24)
            if not label or len(label) < 2 or skip_patterns.search(label):
                continue
            key = re.sub(r"\s+", "", label).lower()
            if key in seen:
                continue
            seen.add(key)
            tasks.append(label)
            if len(tasks) >= 5:
                return tasks
    return tasks


def pages_from_map(page_map: dict, candidates_by_page: dict[str, list[dict]], product_name: str, roles: list[str]) -> list[dict]:
    pages = []
    main_user = roles[0] if roles else ""
    for page in page_map.get("pages", []):
        page_key = str(page.get("pageKey") or "")
        title = normalize(str(page.get("title") or page.get("route") or page_key))
        candidates = candidates_by_page.get(page_key, [])
        pages.append(
            {
                "pageKey": page_key,
                "pageName": title,
                "purpose": infer_page_purpose(page, product_name),
                "primaryTasks": infer_primary_tasks(candidates),
                "mainUser": main_user,
            }
        )
    return pages


def load_candidates_by_page(target: Path) -> dict[str, list[dict]]:
    path = annotation_root(target) / ANNOTATION_DIR_NAME / "annotation-candidates.json"
    if not path.exists():
        legacy = annotation_root(target) / LEGACY_ANNOTATION_DIR_NAME / "annotation-candidates.json"
        if legacy.exists():
            path = legacy
    if not path.exists():
        return {}
    payload = read_json(path)
    result: dict[str, list[dict]] = {}
    for page in payload.get("pages", []):
        page_key = str(page.get("pageKey") or "")
        if page_key:
            result[page_key] = list(page.get("candidates") or [])
    return result


def build_context(target: Path, docs: list[Path], page_map: dict) -> dict:
    valid_docs: list[Path] = []
    doc_chunks: list[str] = []
    for path in docs:
        if not path.exists():
            continue
        text = read_text(path)
        if is_placeholder_doc(text):
            continue
        valid_docs.append(path)
        doc_chunks.append(text)
    docs_text = "\n\n".join(doc_chunks)
    combined_text = "\n\n".join([docs_text, page_map_text(page_map)])
    product_name = extract_product_name(docs_text) or extract_product_name_from_page_map(page_map)
    if not product_name:
        product_name = annotation_root(target).name
    roles = extract_roles(combined_text)
    core_flows = extract_flows(combined_text)
    candidates_by_page = load_candidates_by_page(target)
    pages = pages_from_map(page_map, candidates_by_page, product_name, roles)
    product_type = infer_product_type(combined_text)
    product_forms = product_forms_for(product_type)
    return {
        "productName": product_name,
        "productType": product_type,
        "productForms": product_forms,
        "primaryUsers": roles or ["业务用户"],
        "enabledAnnotationTypes": enabled_types_for(product_forms),
        "roles": roles,
        "coreObjects": [],
        "coreFlows": core_flows,
        "pages": pages,
        "generatedAt": now_iso(),
        "sources": [str(path) for path in valid_docs],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build product-context.json from docs and page-map.")
    parser.add_argument("prototype_path", help="HTML file or static directory")
    parser.add_argument("--docs", action="append", default=[], help="PRD or product spec Markdown. Repeatable.")
    parser.add_argument("--page-map", help="Path to page-map.json")
    parser.add_argument("--out", "--output", dest="output", help="Output product-context.json path")
    args = parser.parse_args()

    target = Path(args.prototype_path).resolve()
    if not target.exists():
        parser.error(f"Path does not exist: {target}")

    page_map_path = Path(args.page_map).resolve() if args.page_map else default_page_map(target)
    page_map = read_json(page_map_path) if page_map_path.exists() else {"pages": []}

    doc_paths = [Path(item).resolve() for item in args.docs]
    if not doc_paths:
        root = annotation_root(target)
        for candidate in sorted(root.rglob("*.md")):
            if "node_modules" in candidate.parts or ANNOTATION_DIR_NAME in candidate.parts or LEGACY_ANNOTATION_DIR_NAME in candidate.parts:
                continue
            if re.search(r"prd|产品|需求|spec", candidate.name, re.I):
                doc_paths.append(candidate)
                break
        if not doc_paths and (root / "README.md").exists():
            doc_paths.append(root / "README.md")

    output = Path(args.output).resolve() if args.output else default_output(target)
    payload = build_context(target, doc_paths, page_map)
    write_json(output, payload)
    print(f"Wrote product context: {output}")
    print(f"Product: {payload.get('productName') or '(unknown)'}; pages: {len(payload.get('pages') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
