# 研发交付标注标准

当 `productProfile.annotationMode = dev-handoff`，或用户明确要求「交付研发 / 给前端 / 研发交接」时，按本标准生成与验收标注。

## 目录

- [目标](#目标)
- [正文模板](#正文模板)
- [页面最低覆盖](#页面最低覆盖)
- [候选转正](#候选转正)
- [锚点要求](#锚点要求)
- [证据与评审字段](#证据与评审字段)
- [正例](#正例)
- [验收命令](#验收命令)

## 目标

交付给研发时，标注必须让读者在原型页面上直接回答：

1. 这个模块为什么存在、服务什么业务任务。
2. 点击后发生什么：路由、抽屉、参数、同步/异步、成功/失败反馈。
3. 对应哪些业务规则：字段校验、状态机、权限、数据写入点。
4. 哪些是 mock、哪些待确认。

## 正文模板

按标注类型选用小节，不要求每条都写全，但非页面介绍标注至少覆盖 **业务含义 + 交互规则 +（字段规则或状态与异常）**。

```md
### 业务含义
### 前置条件
### 交互规则
### 字段规则
### 状态与异常
### 数据落点
### 页面流转
### 前后依赖
### 风险提示
### 待确认
```

### 数据落点写法

优先写清：

- 前端状态：如 `appState.searchQuery`、`authorizedModels`
- 调用方法：如 `API.createApp`、`handleBatchDelete`
- 持久化边界：mock 仅前端移除 / 正式需接口
- 关联字段：如 `status: enabled|disabled`

## 页面最低覆盖

| 页面类型 | 最低标注 |
|---|---|
| 列表 + 操作页 | P + 筛选/搜索 + 表格/行操作规则 + 主 CTA |
| 表单/抽屉页 | P + 提交 CTA + 字段规则 |
| 审批/风险页 | P + 工作流 + 权限/风险 + 异常分支 |
| 仪表盘 | P + 指标口径 + 数据来源 |
| 只读详情 | P + 核心模块说明 + 必要跳转 |

## 候选转正

`dev-handoff` 模式下：

1. 运行 `build_annotation_candidates.py` 后，读取全部 `selected: true` 候选。
2. 用 `generate_annotations_draft.py --promote-all-selected` 先机械落入 `annotations.json`。
3. 智能体必须逐条补全正文，可读 HTML/JS 或 React 源码作为证据。
4. 允许把表格行级操作、抽屉内字段折叠进一条规则说明，但须在正文中写清「适用于全部同名行操作」。

## 锚点要求

- 非页面介绍标注禁止只绑 `main` / `h1` / `body`。
- HTML 优先 `#id`、`[data-ann]`、按钮级 selector。
- React/Vue 优先 `data-testid`、`data-ann`、稳定按钮文本。
- 运行 `suggest_data_ann_anchors.py` 并在交付前处理高优先级建议。

## 证据与评审字段

每条非 P 标注建议写入：

```json
{
  "evidence": ["app-management.js:handleBatchDelete", "#batchDeleteBtn"],
  "risks": ["删除不可撤销"],
  "openQuestions": ["正式版是否改为服务端搜索"],
  "review": { "required": true, "status": "approved" }
}
```

规则：

- `createdBy: "ai"` 的标注在交付前必须 `review.required: true`。
- 只有正文补全且人工确认后，才可设 `review.status: "approved"`。
- 禁止把 `review.required` 设为 `false` 来绕过 `--fail-on-pending-review`。

## 正例

HTML 项目 `prototype_test-2` 中以下标注可作为研发交付参考：

- `ANN-P01-004` 新建应用：抽屉流程、字段表、`API.createApp`、成功 Toast
- `ANN-P01-005` 批量删除：启用态拦截、confirm、错误/成功反馈、风险
- `ANN-P01-006` 应用列表与行操作：列说明、行级操作矩阵、空态
- `ANN-P01-007` 主数据授权：二级抽屉流转、Mermaid

## 验收命令

```bash
python3 scripts/validate_annotations.py <prototype_path> \
  --strict-quality --dev-handoff --fail-on-pending-review
python3 scripts/audit_annotation_coverage.py <prototype_path>
python3 scripts/render_annotation_report.py <prototype_path>
```
