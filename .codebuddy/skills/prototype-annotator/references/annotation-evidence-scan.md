# Annotation Evidence Scan

Use this reference before generating `prototype-annotator/annotation-candidates.json` or promoting candidates into `annotations.json`.

The goal is not to annotate every scanned element or fill a per-page quota. The goal is to provide one page-level overview for orientation, then add only the element-level explanations that make the prototype easier to review, implement, or hand off.

## 目录

- [Promotion Rule](#promotion-rule)
- [High-Value Dimensions](#high-value-dimensions)
- [Delivery Explanation Coverage](#delivery-explanation-coverage)
- [Priority Guidance](#priority-guidance)
- [Skip Reasons](#skip-reasons)
- [Candidate Shape](#candidate-shape)
- [Coverage Rule](#coverage-rule)

## Promotion Rule

Promote an element into a selected annotation candidate only when all conditions are true:

1. The page contains the element or region.
2. The point explains business meaning, interaction rules, state, validation, permission, flow, data, or AI/automation behavior.
3. The target has a stable selector or useful `fallbackText`.
4. The point is not already covered by an existing annotation on the same page.
5. A normal user or developer would not already understand it from the visible UI alone.

If a point is important but unsupported by PRD, page specs, or visible UI, write it as a `待确认` item or skip it. Do not invent backend rules.

Do not select ordinary headings, common navigation, repeated row actions, visible-only labels, decorative regions, or self-explanatory buttons just to reach a count. Cross-page chrome such as app branding, global header search, user profile entry, and side navigation should be skipped unless the task is specifically to document the shell.

Exception: every page should have exactly one selected `Page overview` candidate. This candidate is a page-level reading guide, preferably anchored to the page `h1`, and explains page responsibility, main content, and reading focus.

## High-Value Dimensions

1. **Primary action**: submit, save, create, publish, generate, run, delete, import, export, upload, download, confirm, approve, reject.
2. **Form and validation**: field meaning, required state, default value, option source, placeholder, upload restrictions, validation timing, blocking error.
3. **Table and list**: search, filter, sort, pagination, row action, batch action, empty state, no-result state, loading state.
4. **State and exception**: disabled, loading, failed, empty, no permission, offline, generated, processing, retry.
5. **Flow and navigation**: stepper, next/back, route transition, modal trigger, drawer trigger, close/return path.
6. **Permission and risk**: destructive operation, second confirmation, role-specific visibility, sensitive data, disabled action.
7. **Data explanation**: metric, chart, status label, API-backed content, data object, calculation hint.
8. **AI and automation**: prompt input, model/provider boundary, generation state, retry, cancel, confidence, generated asset export.

## Delivery Explanation Coverage

Use candidates to answer handoff questions, not only to point at UI. Map common
delivery explanations to annotation kinds and topics:

| Explanation | Preferred kind | Topics |
| --- | --- | --- |
| Page source, route, entry, upstream document | `note` or `flow` | `source`, `business`, `flow` |
| Button click result or jump target | `interaction` or `flow` | `interaction`, `flow`, `state` |
| Module business meaning | `note` or `data` | `business`, `dependency` |
| Field rule, required state, validation | `form` | `field-rule`, `exception` |
| Status meaning and transition | `state` | `state`, `exception` |
| Risk warning and irreversible impact | `permission` or `interaction` | `risk`, `dependency` |
| Previous/next dependency | `flow` or `permission` | `dependency`, `flow` |
| Page flow logic | `flow` | `flow`, `interaction` |
| Exception handling | `state` | `exception`, `state` |

If a selected candidate cannot answer at least one of these handoff questions,
keep it unselected unless it is the required page overview candidate.

## Priority Guidance

- `high`: primary CTA, destructive operation, blocking validation, permission-critical rule, status transition, AI generation entry.
- `medium`: table operation, filter, secondary action, drawer or modal rule, data explanation, empty/error state.
- `low`: contextual note, navigation hint, copy detail, secondary visual element.

## Skip Reasons

Use one of these concise reasons when a scanned element should not become an annotation:

- `low-value-structure`: layout wrapper or region without distinct product rule.
- `common-chrome`: cross-page header, sidebar, app branding, global search, or profile entry that should not be repeated on every page.
- `duplicate-meaning`: already covered by another annotation.
- `no-business-rule`: visible element has no clear business or implementation rule.
- `unstable-target`: selector is too fragile and no useful fallback text exists.
- `unsupported-inference`: would require guessing backend, permission, notification, audit, or integration details.
- `scan-artifact`: visible text comes from JS template literals or rendered-scan noise, not a stable UI label.
- `out-of-scope`: element is outside the requested page or processing scope.

## Candidate Shape

```json
{
  "candidateId": "CAND-P01-001",
  "pageKey": "P01",
  "elementId": "P01-E003",
  "selector": "[data-ann=\"submit-application\"]",
  "strategy": "data",
  "fallbackText": "提交申请",
  "tag": "button",
  "kind": "interaction",
  "topics": ["business", "interaction", "flow"],
  "dimension": "Primary action",
  "priority": "high",
  "reason": "主 CTA，触发申请提交。",
  "evidence": ["按钮文本：提交申请", "PRD：提交后进入审核流程"],
  "selected": true,
  "skipReason": null,
  "source": {
    "type": "mixed",
    "ref": "page-map:P01-E003"
  }
}
```

## Coverage Rule

Coverage is value-driven, not count-driven:

- Every page has 1 selected `Page overview` candidate.
- Simple or self-explanatory pages often need only the page overview, or 3-5 total annotations when there are a few non-obvious rules.
- Normal product pages often have 1 page overview plus 1-4 additional candidates, but only when those candidates explain different rules.
- Complex forms, dashboards, approval flows, AI workflows, or admin pages can use more, usually 1 page overview plus 3-7 additional candidates.
- A repeated row action such as `删除`, `停用`, `启用`, or `编辑权限` should normally become one annotation for the table operation, not one annotation per row.

For complex pages, add more only when each candidate explains a different rule. Do not exceed 8 selected candidates per page unless the user explicitly asks for dense annotations.
