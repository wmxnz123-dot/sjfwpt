# Annotation Schema

`annotations.json` is the source of truth for generated and manually edited annotations.

## 目录

- [File Shape](#file-shape)
- [Required Fields](#required-fields)
- [Product Profile](#product-profile)
- [Annotation Type](#annotation-type)
- [Recommended Traceability Fields](#recommended-traceability-fields)
- [Recommended Annotation Kinds](#recommended-annotation-kinds)
- [Priority](#priority)
- [Target Object](#target-object)
- [Surface Model](#surface-model)
- [Markdown Body Sections](#markdown-body-sections)
- [Content Topics](#content-topics)
- [Source Object](#source-object)
- [Candidate File](#candidate-file)
- [History](#history)

## File Shape

```json
{
  "version": 1,
  "project": {
    "id": "prototype-annotator-demo",
    "name": "Prototype Annotator Demo",
    "source": "local"
  },
  "productProfile": {
    "productName": "智能报销助手",
    "productType": "ai_enterprise_app",
    "productForms": ["B端应用", "AI产品", "审批系统"],
    "primaryUsers": ["员工", "领导", "财务"],
    "annotationMode": "standard",
    "enabledAnnotationTypes": ["P", "E", "C", "A", "J", "S", "R", "AI", "PERM", "WF", "DATA", "HITL", "FALLBACK"]
  },
  "pages": [
    {
      "pageKey": "P01",
      "title": "Home",
      "path": "index.html",
      "route": "/"
    }
  ],
  "annotations": [
    {
      "id": "ANN-P01-001",
      "pageKey": "P01",
      "target": {
        "selector": "#submit-btn",
        "fallbackText": "提交",
        "strategy": "id",
        "sourceElementId": "P01-E003"
      },
      "title": "提交申请",
      "contentMarkdown": "### 业务含义\n点击后完成申请提交。",
      "annotationType": "A",
      "kind": "interaction",
      "topics": ["business", "interaction", "flow"],
      "priority": "high",
      "visible": true,
      "source": {
        "type": "prd",
        "ref": "6.1.3 核心操作"
      },
      "evidence": [
        "按钮文本：提交",
        "PRD：提交后进入审核"
      ],
      "review": {
        "required": true,
        "status": "pending"
      },
      "createdBy": "ai",
      "updatedAt": "2026-06-10T00:00:00Z"
    }
  ]
}
```

## Required Fields

- `version`: Schema version. Use `1`.
- `pages[]`: Known prototype pages.
- `annotations[]`: Flat list of annotations across pages.
- `annotation.id`: Stable id in the format `ANN-{pageKey}-{3 digit number}`.
- `annotation.pageKey`: Page key from `pages[]`.
- `annotation.target.selector`: CSS selector used first.
- `annotation.title`: Short title shown in badge card and list.
- `annotation.contentMarkdown`: Markdown body rendered in the card and editor.
- `annotation.visible`: `true` unless the user hides the annotation.

`productProfile` and `annotation.annotationType` are optional for old files. New generated annotations should include them when product context is available.

`annotation.id` is a stable data identifier, not the user-facing badge number. Runtime and reports should compute a continuous display number for the current page or opened surface context, and may show the stable id only as secondary metadata. If annotations `ANN-P03-002` and `ANN-P03-004` are skipped or deleted, the visible badges must still render as `1, 2, 3...` for the remaining annotations.

## Product Profile

`productProfile` is a top-level optional object:

```json
{
  "productName": "智能报销助手",
  "productType": "ai_enterprise_app",
  "productForms": ["B端应用", "AI产品", "审批系统"],
  "primaryUsers": ["员工", "领导", "财务"],
  "annotationMode": "standard",
  "enabledAnnotationTypes": ["P", "E", "C", "A", "J", "S", "R", "AI", "PERM", "WF", "DATA", "HITL", "FALLBACK"]
}
```

When `productProfile.enabledAnnotationTypes` is present, validation checks whether each annotation's `annotationType` belongs to that enabled set.

## Annotation Type

`annotationType` describes the product delivery meaning of an annotation. It complements, but does not replace, `kind`, `dimension`, and `topics`.

Common values:

- `P`: Page overview.
- `E`: Entry source.
- `C`: Component or module explanation.
- `A`: Action or interaction.
- `J`: Page jump or flow transition.
- `S`: State explanation.
- `R`: Business rule.

Extended values:

- `AI`, `PROMPT`, `CTX`, `HITL`, `FALLBACK`
- `PERM`, `WF`, `DATA`
- `TRACK`, `CV`, `REC`
- `METRIC`, `SOURCE`, `FILTER`, `REFRESH`, `DRILL`
- `PLAN`, `ROLE`, `TENANT`
- `CONTENT`, `PUBLISH`, `MOD`

## Recommended Traceability Fields

- `annotation.target.sourceElementId`: Element id from `prototype-annotator/page-map.json`.
- `annotation.annotationType`: Product-semantic annotation type such as `P`, `A`, `AI`, or `FALLBACK`.
- `annotation.evidence[]`: Short evidence strings from page text, PRD, page specs, or candidate generation.
- `annotation.candidateId`: Candidate id from `prototype-annotator/annotation-candidates.json`.
- `annotation.topics[]`: Content topics covered by this annotation.
- `annotation.nextActions[]`: Known downstream actions, route changes, modal changes, or state changes after interaction.
- `annotation.dependencies[]`: Preconditions, upstream pages, roles, status requirements, field dependencies, or data dependencies.
- `annotation.risks[]`: Destructive, irreversible, sensitive, compliance, permission, or customer-facing risks.
- `annotation.openQuestions[]`: Items that must be confirmed before delivery or implementation.
- `annotation.review.required`: `true` when generated from local-rule draft or uncertain evidence.
- `annotation.review.status`: `pending`, `completed`, `approved`, or `skipped`.

## Recommended Annotation Kinds

- `interaction`: Button, link, menu item, primary action.
- `form`: Input, select, upload area, validation rule.
- `state`: Status badge, empty/loading/error/disabled state.
- `table`: Table, row action, batch action, pagination.
- `flow`: Navigation, stepper, page transition, business flow.
- `permission`: Role difference, disabled action, hidden entry.
- `data`: Metric, chart, data object, API-backed content.
- `ai`: AI-generated content, prompt input, confidence, automation.
- `note`: General explanation or open question.

## Priority

- `high`: Must be reviewed by product or engineering.
- `medium`: Useful explanation for implementation.
- `low`: Contextual note, secondary interaction, copy detail.

## Target Object

```json
{
  "selector": "#submit-btn",
  "fallbackText": "提交",
  "strategy": "id",
  "sourceElementId": "P01-E003",
  "boundsHint": {
    "text": "提交申请",
    "tag": "button"
  }
}
```

Selector strategy values:

- `id`: `#id`.
- `data`: `[data-testid="..."]`, `[data-ann="..."]`, or similar.
- `aria`: `[aria-label="..."]`.
- `text`: selector plus fallback text.
- `path`: structural selector such as `main > section:nth-of-type(2) button`.
- `manual`: user-created or manually corrected.

## Surface Model

Secondary UI such as drawers, modals, confirms, popovers, and dropdowns use the
top-level `surfaces[]` array plus optional per-annotation surface fields.

### Top-level surfaces

```json
{
  "surfaces": [
    {
      "id": "surface-P01-create-app-drawer",
      "type": "drawer",
      "name": "新建应用抽屉",
      "pageKey": "P01",
      "triggerSelector": "[data-ann='create-app']",
      "openSelector": "[data-ann='create-app-drawer']",
      "closeSelector": "[data-ann='close-create-app']",
      "visibility": "on-trigger",
      "description": "点击新建应用后打开，用于填写应用信息并保存。"
    }
  ]
}
```

Surface id format: `surface-{pageKey}-{slug}`.

Supported `type` values:

- `modal`, `drawer`, `confirm`, `popover`, `dropdown`
- `toast`, `message` (usually not independently annotated)
- `notification`, `alert`, `banner`

### Per-annotation surface fields

```json
{
  "id": "ANN-P01-003",
  "pageKey": "P01",
  "surfaceId": "surface-P01-create-app-drawer",
  "displayWhenClosed": "sidebar-only",
  "fallbackAnchorSelector": "[data-ann='create-app']",
  "target": {
    "selector": "[data-ann='app-name-input']"
  },
  "dimension": "Surface field",
  "annotationType": "C"
}
```

`displayWhenClosed` values:

- `on-trigger`: show on the trigger control while the surface is closed.
- `sidebar-only`: sidebar only while closed; page badge appears after open.
- `hidden-until-open`: hidden from the main list until the surface opens.

Confirm dialogs use `annotationType: "A"` and `dimension: "Surface confirm"`.
Do not introduce a separate `CONFIRM` annotation type.

### page-map linkage

`prototype-annotator/page-map.json` may also contain `surfaces[]` and
`elements[].surfaceId` from rendered scanning. `generate_annotations_draft.py`
merges scan-time surfaces into `annotations.json`.

### Manual annotations inside an open surface

When a user creates an annotation by clicking an element inside an already open
drawer or modal, the runtime should auto-fill:

- `surfaceId`
- `displayWhenClosed: "sidebar-only"`
- `fallbackAnchorSelector` from the matched surface `triggerSelector`

When multiple business surfaces reuse the same DOM container, do not merge
their triggers into one surface. Use one surface per business task. These
surfaces may share `openSelector`, but each must include a stable content
signature such as `titleText`, `textIncludes`, or `contentSelector`.
When the rendered title changes by mode, prefer actual rendered title
candidates such as `titleText: ["新建记录", "编辑记录"]` or
`titleText: ["创建应用", "编辑应用"]` instead of one compound label such as
`新建/编辑对象` or `新增/修改记录`. `containerSelector` may point to the open
root itself or to a stable child container.

Further guidance: `references/surface-annotation-guide.md`.

## Markdown Body Sections

Use sections only when they add value. Common sections:

```md
### 页面来源

### 业务含义

### 交互规则

### 字段规则

### 状态与异常

### 前后依赖

### 页面流转

### 风险提示

### 待确认
```

`contentMarkdown` remains the display source of truth. Optional structured fields
such as `topics`, `nextActions`, `dependencies`, `risks`, and `openQuestions`
help export, search, and quality validation, but the runtime must not require
them to render annotation cards.

## Content Topics

Use concise topic names:

- `source`: Page source, route, upstream document, or entry point.
- `business`: Business meaning, module purpose, or product object.
- `interaction`: Click, submit, save, confirm, open, close, or edit behavior.
- `field-rule`: Field meaning, required state, validation, default value, or option source.
- `state`: Status, empty/loading/error/disabled state, or state transition.
- `risk`: Destructive, irreversible, permission-sensitive, or customer-impacting behavior.
- `dependency`: Upstream/downstream dependency, role, status, data, or integration condition.
- `flow`: Page transition, modal/drawer flow, stepper, or business process.
- `exception`: Failure handling, retry, fallback, timeout, or abnormal path.
- `ai`: AI generation, prompt, model/provider boundary, confidence, retry, or export.

## Source Object

- `type`: `prd`, `prototype`, `page-spec`, `manual`, `ai-inference`, `local-rule-draft`, or `mixed`.
- `ref`: Section heading, file path, page-map element id, or free text.

If the content is inferred without explicit PRD support, use:

```json
{
  "type": "ai-inference",
  "ref": "根据原型结构推断"
}
```

Use `local-rule-draft` when a bundled script creates a placeholder annotation without AI or human review. These annotations should also set:

```json
{
  "review": {
    "required": true,
    "status": "pending",
    "reason": "local-rule-draft"
  }
}
```

## Candidate File

`prototype-annotator/annotation-candidates.json` stores explainable pre-annotation decisions:

```json
{
  "version": 1,
  "generatedAt": "2026-06-10T00:00:00Z",
  "root": "/path/to/prototype",
  "sources": {
    "pageMap": "page-map.json",
    "docs": ["PRD.md", "prototype-specs/current/home.md"]
  },
  "pages": [
    {
      "pageKey": "P01",
      "title": "Home",
      "path": "index.html",
      "route": "/index.html",
      "candidates": [
        {
          "candidateId": "CAND-P01-001",
          "pageKey": "P01",
          "elementId": "P01-E003",
          "selector": "#submit-btn",
          "strategy": "id",
          "fallbackText": "提交",
          "annotationType": "A",
          "kind": "interaction",
          "dimension": "Primary action",
          "priority": "high",
          "reason": "主 CTA，触发提交动作。",
          "evidence": ["按钮文本：提交"],
          "selected": true,
          "skipReason": null
        }
      ]
    }
  ]
}
```

Candidates with `selected: false` should keep `skipReason` so reviewers can understand why a scanned element was not promoted.

## History

The review server appends JSON lines to `prototype-annotator/history.jsonl`:

```json
{"at":"2026-06-10T00:00:00Z","action":"update","id":"ANN-P01-001","title":"提交申请"}
```
