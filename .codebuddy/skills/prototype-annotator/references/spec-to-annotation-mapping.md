# Page Spec to Annotation Mapping

Use this reference when a target project already contains page-level Markdown specs, usually from `prototype-spec-annotator`:

```text
prototype-specs/current/*.md
src/page-specs/current/*.md
```

Page specs are evidence, not final annotations. Convert them into element-level candidates only when the page map has a matching selector or fallback text. This skill must not create, rewrite, or maintain those page spec Markdown files; that belongs to `prototype-spec-annotator`.

When communicating with users, call the generated `P` annotation a "页面级说明标注" or "页面功能介绍标注". Do not call it "页面说明文档" or imply that this skill generated page-level requirement documents.

## Mapping Rules

| Page spec section | Annotation target | Suggested kind | Notes |
| --- | --- | --- | --- |
| `## 页面摘要` | Main page region or primary CTA | `note` or `flow` | Use sparingly. Prefer a concrete action over annotating the whole page; if used as `P`, it is still a page-level annotation, not a spec document. |
| `## 二级承载面` | Modal, drawer, popover, step panel | `flow` | Explain open/close, return path, and subtask boundary. |
| `【筛选条件】` | Search, filter, date range, select | `form` or `table` | Explain option source, default value, and query behavior. |
| `【结果区】` | Table, list, card grid, chart | `table` or `data` | Explain columns, empty state, pagination, or refresh behavior. |
| `【字段说明】` | Input, select, upload, textarea | `form` | Convert important fields and validation rules only. |
| `【功能操作】` | Button, menu item, batch action | `interaction` | Prioritize primary, destructive, async, or state-changing actions. |
| `【状态与异常】` | Badge, alert, empty state, disabled action | `state` | Include visible failure, loading, empty, or no-permission states. |
| `【权限】` | Disabled/hidden/role-specific entry | `permission` | Only write facts visible in UI or explicitly stated in specs. |
| `【AI】` / generation rules | Prompt input, generate button, result area | `ai` | Cover generation state, retry/cancel, result handling, and model boundary if stated. |

## Evidence Matching

For each page spec section:

1. Extract names of modules, fields, buttons, statuses, tables, drawers, and dialogs.
2. Match them against `page-map.json` by visible text, selector attributes, placeholder, `aria-label`, `name`, route, and page title.
3. Promote only matched elements into candidates.
4. If the spec mentions a rule but no element can be found, do not create an annotation. Add a candidate with `selected: false` and `skipReason: "unstable-target"` only when the gap is useful for review.

## Content Conversion

Keep annotation cards compact:

- Convert long page-level sections into 2-5 short bullets.
- Keep field tables only when multiple field rules belong to the same form target.
- Put uncertain or unmatched spec details under `### 待确认`.
- Do not copy the entire page spec into one annotation.

## Source Object

When an annotation uses page specs as evidence, set:

```json
{
  "source": {
    "type": "page-spec",
    "ref": "prototype-specs/current/app-management.md#【功能操作】交互规则说明"
  }
}
```

If PRD, page spec, and page-map evidence are all used, set `source.type` to `mixed` and include the concrete refs in `evidence`.
