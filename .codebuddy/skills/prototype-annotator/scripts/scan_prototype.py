#!/usr/bin/env python3
"""Scan HTML prototypes and create prototype-annotator/page-map.json."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional


INTERESTING_TAGS = {
    "a", "button", "input", "select", "textarea", "form", "table", "dialog",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "nav", "main", "section", "header", "footer", "aside", "canvas"
}
INTERESTING_ROLES = {"button", "link", "tab", "menuitem", "checkbox", "radio", "switch"}
TEMPLATE_LITERAL_RE = re.compile(r"\$\{|\{\{|\}\}|\.map\s*\(|=>\s*\)|columns\.map|data\.map")
BEHAVIOR_ID_RE = re.compile(r"getElementById\(\s*['\"]([^'\"]+)['\"]")
BEHAVIOR_QUERY_RE = re.compile(r"querySelector\(\s*['\"]([^'\"]+)['\"]")
BEHAVIOR_FN_RE = re.compile(r"function\s+([A-Za-z_$][\w$]*)\s*\(")
BEHAVIOR_HANDLER_RE = re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(")
SURFACE_KEYWORD_RE = re.compile(
    r"modal|dialog|drawer|popover|dropdown|confirm|popup|侧滑|弹窗|抽屉|确认|下拉|气泡",
    re.I,
)
SURFACE_CLASS_RE = re.compile(
    r"(?:^|[\s_-])(modal|drawer|dialog|popover|dropdown|popup|confirm)(?:[\s_-]|$)",
    re.I,
)


@dataclass
class Node:
    tag: str
    attrs: Dict[str, str]
    parent: Optional["Node"] = None
    children: List["Node"] = field(default_factory=list)
    text_parts: List[str] = field(default_factory=list)
    index_in_parent: int = 1

    @property
    def text(self) -> str:
        own = " ".join(part.strip() for part in self.text_parts if part.strip())
        child = " ".join(child.text for child in self.children if child.text)
        return normalize_space((own + " " + child).strip())


class PrototypeHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {})
        self.stack: List[Node] = [self.root]
        self.title_text: List[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attr_dict = {name: (value or "") for name, value in attrs}
        parent = self.stack[-1]
        same_tag_count = sum(1 for child in parent.children if child.tag == tag)
        node = Node(tag=tag, attrs=attr_dict, parent=parent, index_in_parent=same_tag_count + 1)
        parent.children.append(node)
        if tag == "title":
            self.in_title = True
        if tag not in {"meta", "link", "img", "br", "hr", "input"}:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_text.append(data)
        if self.stack:
            self.stack[-1].text_parts.append(data)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def is_template_literal_text(value: str) -> bool:
    text = value or ""
    return bool(TEMPLATE_LITERAL_RE.search(text))


def sanitize_element_text(value: str) -> tuple[str, str | None]:
    text = normalize_space(value)
    if is_template_literal_text(text):
        return "", "template-literal"
    return text[:160], None


def css_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def css_id(value: str) -> str:
    if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", value):
        return "#" + value
    return "#" + re.sub(r"([^A-Za-z0-9_-])", lambda m: "\\" + m.group(1), value)


def selector_for(
    node: Node,
    tag_counts: Dict[str, int] | None = None,
    attr_counts: Dict[tuple[str, str, str], int] | None = None,
) -> tuple[str, str]:
    tag_counts = tag_counts or {}
    attr_counts = attr_counts or {}
    if node.attrs.get("id"):
        return css_id(node.attrs["id"]), "id"
    for attr in ("data-ann", "data-testid", "data-test", "data-cy"):
        if node.attrs.get(attr):
            return f'[{attr}="{css_string(node.attrs[attr])}"]', "data"
    if node.attrs.get("aria-label"):
        return f'[aria-label="{css_string(node.attrs["aria-label"])}"]', "aria"
    if node.attrs.get("name") and node.tag in {"input", "select", "textarea"}:
        return f'{node.tag}[name="{css_string(node.attrs["name"])}"]', "name"
    if node.attrs.get("placeholder") and node.tag in {"input", "textarea"}:
        return f'{node.tag}[placeholder*="{css_string(node.attrs["placeholder"][:20])}"]', "placeholder"
    if node.attrs.get("href") and node.tag == "a" and attr_counts.get((node.tag, "href", node.attrs["href"])) == 1:
        return f'a[href="{css_string(node.attrs["href"])}"]', "href"
    if node.attrs.get("role") and attr_counts.get((node.tag, "role", node.attrs["role"])) == 1:
        return f'{node.tag}[role="{css_string(node.attrs["role"])}"]', "role"
    ancestor_selector = stable_ancestor_selector(node)
    if ancestor_selector and node.tag in {"table", "form", "nav", "header", "footer", "aside"}:
        return f"{ancestor_selector} {node.tag}", "data-descendant"
    if node.tag in {"h1", "main", "table", "form", "nav", "header", "footer", "aside"} and tag_counts.get(node.tag) == 1:
        return node.tag, "tag"
    for attr in ("onclick", "oninput", "onchange"):
        if node.attrs.get(attr) and node.tag in {"button", "input", "select", "textarea", "a"}:
            return f'{node.tag}[{attr}="{css_string(node.attrs[attr])}"]', "handler"
    return structural_selector(node), "path"


def stable_ancestor_selector(node: Node) -> str | None:
    current = node.parent
    while current and current.tag != "document":
        for attr in ("data-ann", "data-testid", "data-test", "data-cy"):
            if current.attrs.get(attr):
                return f'[{attr}="{css_string(current.attrs[attr])}"]'
        if current.attrs.get("id"):
            return css_id(current.attrs["id"])
        current = current.parent
    return None


def structural_selector(node: Node) -> str:
    parts: List[str] = []
    current: Optional[Node] = node
    while current and current.tag != "document":
        part = current.tag
        if current.parent:
            same_tag_total = sum(1 for child in current.parent.children if child.tag == current.tag)
            if same_tag_total > 1:
                part += f":nth-of-type({current.index_in_parent})"
        parts.insert(0, part)
        if len(parts) >= 5:
            break
        current = current.parent
    return " > ".join(parts)


def flatten(node: Node) -> Iterable[Node]:
    for child in node.children:
        yield child
        yield from flatten(child)


def is_interesting(node: Node) -> bool:
    if node.tag in INTERESTING_TAGS:
        return True
    if node.attrs.get("role") in INTERESTING_ROLES:
        return True
    if node.attrs.get("onclick"):
        return True
    if node.attrs.get("data-ann") or node.attrs.get("data-testid"):
        return True
    return False


def surface_tokens(node: Node) -> str:
    parts = [
        node.tag,
        node.attrs.get("id", ""),
        node.attrs.get("class", ""),
        node.attrs.get("role", ""),
        node.attrs.get("data-ann", ""),
        node.attrs.get("aria-label", ""),
    ]
    return " ".join(parts)


def is_surface_part_node(node: Node) -> bool:
    combined = surface_tokens(node)
    return bool(re.search(r"(?:^|[\s_-])(header|body|footer|title|content)(?:[\s_-]|$)", combined, re.I))


def is_surface_root(node: Node) -> bool:
    if node.tag in {"button", "a", "input", "select", "textarea", "label", "option"}:
        return False
    if is_surface_part_node(node):
        return False
    if node.tag == "dialog":
        return True
    if node.attrs.get("role") in {"dialog", "alertdialog"}:
        return True
    if node.attrs.get("aria-modal") == "true":
        return True
    combined = surface_tokens(node)
    if node.tag in {"div", "section", "aside", "main", "form"} and SURFACE_KEYWORD_RE.search(combined):
        return True
    class_name = node.attrs.get("class", "")
    return node.tag in {"div", "section", "aside", "main", "form"} and bool(SURFACE_CLASS_RE.search(class_name))


def surface_type_for_node(node: Node) -> str:
    combined = surface_tokens(node)
    if re.search(r"confirm|确认", combined, re.I):
        return "confirm"
    if re.search(r"drawer|抽屉|侧滑", combined, re.I):
        return "drawer"
    if re.search(r"popover|气泡", combined, re.I):
        return "popover"
    if re.search(r"dropdown|下拉", combined, re.I):
        return "dropdown"
    if re.search(r"modal|dialog|弹窗", combined, re.I):
        return "modal"
    return "modal"


def slugify_surface_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value or "").strip("-").lower()
    if not cleaned:
        return "surface"
    if re.search(r"[\u4e00-\u9fff]", cleaned):
        return "surface"
    return cleaned[:48]


TECHNICAL_SURFACE_NAME_RE = re.compile(
    r"^(?:surface-)?(?:drawer|modal|dialog|popover|dropdown|confirm|popup)(?:[-_\w]*|\d*)$",
    re.I,
)


def is_technical_surface_name(value: str) -> bool:
    text = normalize_space(value)
    if not text:
        return True
    if TECHNICAL_SURFACE_NAME_RE.match(text):
        return True
    if re.fullmatch(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+){1,}", text, re.I):
        return True
    return False


def first_surface_heading(node: Node) -> str:
    for child in flatten(node):
        if child.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            text = normalize_space(child.text)
            if text:
                return text
        if child.attrs.get("role") == "heading":
            text = normalize_space(child.text or child.attrs.get("aria-label", ""))
            if text:
                return text
    return ""


def surface_readable_name(node: Node, fallback: str) -> tuple[str, str | None]:
    heading = first_surface_heading(node)
    candidates = [
        node.attrs.get("aria-label", ""),
        node.attrs.get("title", ""),
        node.attrs.get("data-ann-label", ""),
        heading,
    ]
    for candidate in candidates:
        text = normalize_space(candidate)
        if text and not is_technical_surface_name(text):
            return text[:48], heading or None
    if heading:
        return heading[:48], heading
    return fallback, None


def infer_static_surfaces(nodes: List[Node], page_key: str) -> tuple[list[dict], dict[int, str]]:
    surfaces: list[dict] = []
    node_to_surface: dict[int, str] = {}
    seen_ids: set[str] = set()

    for node in nodes:
        if not is_surface_root(node):
            continue
        ancestor = node.parent
        nested_in_surface = False
        while ancestor and ancestor.tag != "document":
            if id(ancestor) in node_to_surface:
                nested_in_surface = True
                break
            ancestor = ancestor.parent
        if nested_in_surface:
            continue
        selector, _ = selector_for(node, {}, {})
        slug = slugify_surface_name(node.attrs.get("data-ann") or node.attrs.get("id") or node.attrs.get("class", "") or node.tag)
        surface_id = f"surface-{page_key}-{slug}"
        suffix = 2
        while surface_id in seen_ids:
            surface_id = f"surface-{page_key}-{slug}-{suffix}"
            suffix += 1
        seen_ids.add(surface_id)
        readable_name, title_text = surface_readable_name(node, surface_id)
        surface = {
            "id": surface_id,
            "type": surface_type_for_node(node),
            "name": readable_name,
            "pageKey": page_key,
            "openSelector": selector,
            "visibility": "on-trigger",
            "scanSource": "static-inferred",
            "scanQuality": "static-inferred",
        }
        if title_text:
            surface["titleText"] = title_text
        surfaces.append(
            surface
        )
        node_to_surface[id(node)] = surface_id

    node_surface_map: dict[int, str] = {}

    def surface_id_for_node(node: Node) -> str | None:
        current: Optional[Node] = node
        while current and current.tag != "document":
            mapped = node_to_surface.get(id(current))
            if mapped:
                return mapped
            current = current.parent
        return None

    for node in nodes:
        mapped = surface_id_for_node(node)
        if mapped:
            node_surface_map[id(node)] = mapped

    return surfaces, node_surface_map


def element_type(node: Node) -> str:
    if node.tag in {"button", "a"} or node.attrs.get("role") in {"button", "link"}:
        return "interaction"
    if node.tag in {"input", "select", "textarea", "form"}:
        return "form"
    if node.tag == "table":
        return "table"
    if node.tag in {"nav", "main", "section", "header", "footer", "aside"}:
        return "region"
    return "element"


def scan_html(path: Path, root_dir: Path, page_index: int) -> dict:
    parser = PrototypeHTMLParser()
    source = path.read_text(encoding="utf-8", errors="ignore")
    parser.feed(source)
    for fragment in extract_script_html_fragments(source, path.parent):
        parser.feed(fragment)
    title = normalize_space(" ".join(parser.title_text))
    h1 = next((node.text for node in flatten(parser.root) if node.tag == "h1" and node.text), "")
    page_key = f"P{page_index:02d}"

    nodes = list(flatten(parser.root))
    tag_counts: Dict[str, int] = {}
    attr_counts: Dict[tuple[str, str, str], int] = {}
    for node in nodes:
        tag_counts[node.tag] = tag_counts.get(node.tag, 0) + 1
        for attr in ("href", "role"):
            if node.attrs.get(attr):
                key = (node.tag, attr, node.attrs[attr])
                attr_counts[key] = attr_counts.get(key, 0) + 1

    static_surfaces, node_surface_map = infer_static_surfaces(nodes, page_key)

    elements = []
    seen_selectors = set()
    for node in nodes:
        if not is_interesting(node):
            continue
        selector, strategy = selector_for(node, tag_counts, attr_counts)
        if selector in seen_selectors:
            continue
        seen_selectors.add(selector)
        text = node.text
        if node.tag == "input":
            text = node.attrs.get("placeholder") or node.attrs.get("aria-label") or node.attrs.get("name") or text
        text, scan_issue = sanitize_element_text(text)
        entry = {
            "elementId": f"{page_key}-E{len(elements) + 1:03d}",
            "tag": node.tag,
            "type": element_type(node),
            "selector": selector,
            "strategy": strategy,
            "text": text,
            "visible": node.attrs.get("hidden") is None and node.attrs.get("aria-hidden") != "true",
            "attrs": {
                key: node.attrs[key]
                for key in (
                    "id", "data-ann", "data-testid", "aria-label", "name", "type",
                    "role", "href", "placeholder", "title", "onclick", "oninput", "onchange"
                )
                if key in node.attrs and node.attrs[key]
            }
        }
        surface_id = node_surface_map.get(id(node))
        if surface_id:
            entry["surfaceId"] = surface_id
        if scan_issue:
            entry["scanQuality"] = scan_issue
        elements.append(entry)

    page_payload = {
        "pageKey": page_key,
        "title": title or h1 or path.stem,
        "path": str(path.relative_to(root_dir)),
        "route": "/" + str(path.relative_to(root_dir)),
        "elements": elements,
    }
    if static_surfaces:
        page_payload["surfaces"] = static_surfaces
    behavior_hints = scan_behavior_hints_for_page(source, path.parent, root_dir)
    if behavior_hints:
        page_payload["behaviorHints"] = behavior_hints
    return page_payload


def extract_script_html_fragments(html: str, html_dir: Path) -> List[str]:
    fragments: List[str] = []
    for match in re.finditer(r"<script\b([^>]*)>(.*?)</script>", html, re.IGNORECASE | re.DOTALL):
        attrs = match.group(1) or ""
        body = match.group(2) or ""
        src_match = re.search(r'\bsrc=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        if src_match:
            src = src_match.group(1)
            if src.startswith(("http://", "https://", "//")):
                continue
            js_path = (html_dir / src).resolve()
            if js_path.exists() and js_path.is_file():
                fragments.extend(extract_template_literals(js_path.read_text(encoding="utf-8", errors="ignore")))
        else:
            fragments.extend(extract_template_literals(body))
    return fragments


def discover_companion_js_files(root_dir: Path, html_dir: Path, html_source: str) -> List[Path]:
    discovered: list[Path] = []
    seen: set[str] = set()

    def add_path(candidate: Path) -> None:
        resolved = candidate.resolve()
        key = str(resolved)
        if key in seen or not resolved.exists() or not resolved.is_file():
            return
        seen.add(key)
        discovered.append(resolved)

    for match in re.finditer(r'<script\b[^>]*\bsrc=["\']([^"\']+)["\']', html_source, re.IGNORECASE):
        src = match.group(1)
        if src.startswith(("http://", "https://", "//")):
            continue
        add_path((html_dir / src).resolve())

    if companion_js_enabled:
        for pattern in ("assets/js/*.js", "js/*.js", "*.js"):
            for js_file in sorted(root_dir.glob(pattern)):
                if ".prototype-annotations" not in js_file.parts and "prototype-annotator" not in js_file.parts and "node_modules" not in js_file.parts:
                    add_path(js_file)
    return discovered


def scan_js_behavior_hints(js_path: Path) -> list[dict]:
    source = js_path.read_text(encoding="utf-8", errors="ignore")
    hints: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def push(kind: str, value: str, line_hint: str) -> None:
        key = (kind, value)
        if not value or key in seen:
            return
        seen.add(key)
        hints.append({"kind": kind, "value": value, "source": f"{js_path.name}:{line_hint}"})

    for match in BEHAVIOR_ID_RE.finditer(source):
        push("id", match.group(1), "getElementById")
    for match in BEHAVIOR_QUERY_RE.finditer(source):
        push("selector", match.group(1), "querySelector")
    for match in BEHAVIOR_FN_RE.finditer(source):
        push("function", match.group(1), "function")
    for match in BEHAVIOR_HANDLER_RE.finditer(source):
        push("handler", match.group(1), "arrow-handler")
    return hints[:40]


def scan_behavior_hints_for_page(html_source: str, html_dir: Path, root_dir: Path) -> list[dict]:
    hints: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for js_path in discover_companion_js_files(root_dir, html_dir, html_source):
        for item in scan_js_behavior_hints(js_path):
            key = (item.get("kind"), item.get("value"))
            if key in seen:
                continue
            seen.add(key)
            hints.append(item)
    return hints


companion_js_enabled = True


def extract_template_literals(source: str) -> List[str]:
    fragments: List[str] = []
    index = 0
    length = len(source)
    while index < length:
        if source[index] != "`":
            index += 1
            continue
        index += 1
        chars: List[str] = []
        while index < length:
            char = source[index]
            if char == "\\":
                if index + 1 < length:
                    chars.append(source[index + 1])
                    index += 2
                    continue
            if char == "`":
                index += 1
                break
            chars.append(char)
            index += 1
        literal = "".join(chars)
        if "<" in literal and ">" in literal:
            fragments.append(literal)
    return fragments


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


def default_output(target: Path, root_dir: Path) -> Path:
    if target.is_file():
        return target.parent / "prototype-annotator" / "page-map.json"
    return root_dir / "prototype-annotator" / "page-map.json"


def main() -> int:
    global companion_js_enabled
    parser = argparse.ArgumentParser(description="Scan HTML prototype pages for annotatable elements.")
    parser.add_argument("prototype_path", help="HTML file or directory to scan")
    parser.add_argument("--out", help="Output page-map path")
    parser.add_argument(
        "--companion-js",
        action="store_true",
        help="Also scan assets/js and referenced script files for behavior hints (enabled by default).",
    )
    parser.add_argument(
        "--no-companion-js",
        action="store_true",
        help="Disable companion JavaScript behavior hint scanning.",
    )
    args = parser.parse_args()
    companion_js_enabled = not args.no_companion_js
    if args.companion_js:
        companion_js_enabled = True

    target = Path(args.prototype_path).resolve()
    if not target.exists():
        parser.error(f"Path does not exist: {target}")

    root_dir, html_files = find_html_files(target)
    if not html_files:
        parser.error("No HTML files found.")

    pages = [scan_html(path, root_dir, index + 1) for index, path in enumerate(html_files)]
    output = Path(args.out).resolve() if args.out else default_output(target, root_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    surfaces: list[dict] = []
    seen_surface_ids: set[str] = set()
    for page in pages:
        for surface in page.get("surfaces", []):
            surface_id = str(surface.get("id") or "")
            if surface_id and surface_id not in seen_surface_ids:
                seen_surface_ids.add(surface_id)
                surfaces.append(surface)
    payload = {
        "version": 2,
        "root": str(root_dir),
        "scanMode": "static-html",
        "pages": pages,
    }
    if surfaces:
        payload["surfaces"] = surfaces
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Scanned {len(html_files)} HTML file(s). Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
