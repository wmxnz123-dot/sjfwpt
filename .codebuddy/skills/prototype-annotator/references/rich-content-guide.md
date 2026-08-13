# Rich Content Guide

Annotation cards render `contentMarkdown`.

## Supported Markdown

- `#`, `##`, `###`, `####` headings.
- `**bold**`, `*italic*`, inline `` `code` ``.
- `==highlight==` for highlighted text.
- Bulleted and numbered lists.
- Links.
- Images via `![alt](/prototype-annotator/assets/name.png)` or `![alt](./prototype-annotator/assets/name.png)` for static HTML prototypes. Legacy `.prototype-annotations/assets/...` references are still accepted during migration.
- Blockquotes.
- Fenced code blocks.
- Tables.
- Mermaid fenced blocks.

## Recommended Structure

Keep cards compact, but use structure for implementation-critical details:

```md
### 业务含义
这是创建申请的主入口。

### 状态与异常
| 状态 | 表现 | 触发条件 |
| --- | --- | --- |
| 默认 | 可点击 | 表单有效 |
| 禁用 | 置灰 | 必填项缺失 |

### 流转
```mermaid
flowchart LR
  A[填写表单] --> B[提交]
  B --> C[详情页]
```
```

## Table Rules

- Use tables for states, permissions, validations, fields, and status mappings.
- Keep table columns under 4 when possible.
- Avoid long paragraphs inside table cells.

## Mermaid Rules

- Use Mermaid only when a flow is easier to understand visually.
- Prefer simple `flowchart LR` or `flowchart TD`.
- Use `stateDiagram-v2` only for explicit status transitions.
- Keep node labels short.
- In `stateDiagram-v2`, prefer ASCII state ids with Chinese display labels, e.g. `state "待审核" as Pending`.
- If Mermaid is not essential, use a plain list.
- Do not use Mermaid for simple field explanations, static component descriptions, or one-step actions.
- Keep generated diagrams to roughly 4-8 nodes so annotation cards remain readable.

## Mermaid Fit Matrix

| Annotation module | Recommended Mermaid | Use for |
| --- | --- | --- |
| `P` Page overview | `flowchart LR` | Entry, main task, feedback, next step |
| `J` Flow and navigation | `flowchart LR` | Current page, trigger, target page, fallback |
| `S` State explanation | `stateDiagram-v2` | Default, loading, success, failure, empty, disabled |
| `R` Business rule | `flowchart TD` | Rule checks, pass/block branches, recovery |
| `PERM` / `ROLE` | `flowchart TD` | Role check, state check, allowed/blocked result |
| `AI` / `HITL` / `FALLBACK` | `flowchart TD` | Input, AI processing, review, retry, manual fallback |
| `DATA` / `METRIC` / `SOURCE` | `flowchart LR` | Source, permission filtering, metric/query logic, display |
| Surface overview/action/confirm | `flowchart TD` | Open, edit/confirm, save/cancel, refresh main page |

## Highlight Rules

Use `==...==` to call out:

- Blocking validation.
- Permission constraints.
- Known assumptions.
- User-visible risk.

Example:

```md
==待确认：是否允许审批人修改申请金额。==
```

## Image Rules

- Use images only when a screenshot materially helps explain the marked UI, state, exception, or visual evidence.
- In online review mode for static HTML, paste clipboard images directly into the product or dev Markdown editor. The runtime uploads the file to `prototype-annotator/assets/` and inserts Markdown image syntax.
- Keep image references local to `prototype-annotator/assets/` for deliverable static HTML prototypes. Avoid embedding large `data:image/...` strings in `annotations.json`.
- For React / Vue / Vite deploys, sync images before building:

```bash
python3 scripts/sync_deploy_assets.py <project_root>
python3 scripts/validate_annotations.py <project_root> --deploy-check
```

This copies the deliverable image assets to `public/prototype-annotator/assets/` so Vite includes them in `dist/prototype-annotator/assets/`.
- Add a short alt text when editing the generated Markdown if the default `粘贴图片` label is not descriptive enough.

## Card Size Guidance

Runtime cards auto-size up to viewport limits:

- Desktop width: 360-520 px.
- Mobile width: `calc(100vw - 32px)`.
- Max height: `70vh`.
- Long content scrolls inside the card.
- View and edit cards include a fullscreen toggle for dense Markdown, tables, and Mermaid diagrams.
- Fullscreen edit mode should give the Markdown textarea most of the viewport so product managers can maintain long annotation content comfortably.

Do not force manual height in annotation content.
