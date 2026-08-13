# Interaction Plan 使用说明

## 1. 作用

`interaction-plan.json` 用于指导扫描器打开抽屉、弹窗、确认框、Popover、Dropdown 等二级界面，并扫描其内部元素。

它是**扫描辅助配置**，不是最终交付物。扫描结果写入 `page-map.json`，再经候选生成与草稿脚本合并到 `annotations.json`。

## 2. 默认路径

```text
prototype-annotator/interaction-plan.json
```

## 3. 使用场景

以下情况需要提供 interaction plan：

- 抽屉/弹窗需要点击后才挂载到 DOM
- 内部字段在静态 HTML 中为 `hidden` 或 `display: none`
- React / Vue 项目通过 Portal 渲染 Modal / Drawer
- 需要扫描确认框、Popover、Dropdown 内部控件

以下情况可以不提供：

- 所有待标注元素在主页面初始 DOM 中可见
- 仅需标注触发按钮和整体说明，不需要自动发现内部字段

## 4. 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 交互名称，便于日志和调试 |
| `pageRoute` | 否 | 页面路由或 HTML 路径，如 `/index.html` |
| `triggerSelector` | 是 | 打开 surface 的触发控件 |
| `triggerAction` | 否 | `click`（默认）/ `hover` / `focus` |
| `preconditionSelector` | 否 | 触发前需满足的前置条件，如先选中表格行 |
| `waitForSelector` | 否 | 打开后等待出现的 surface 根节点 |
| `surfaceId` | 是 | 对应 `surfaces[].id` |
| `surfaceName` | 否 | 人类可读名称 |
| `surfaceType` | 是 | `modal` / `drawer` / `confirm` / `popover` / `dropdown` |
| `closeSelector` | 否 | 关闭按钮选择器 |
| `waitMs` | 否 | 打开后额外等待毫秒数，默认 300 |
| `scope` | 否 | `document`（默认）或 `trigger-parent` |

## 5. 示例

```json
{
  "interactions": [
    {
      "name": "打开新建应用抽屉",
      "pageRoute": "/index.html",
      "triggerSelector": "[data-ann='create-app']",
      "triggerAction": "click",
      "waitForSelector": "[data-ann='create-app-drawer']",
      "surfaceId": "surface-P01-create-app-drawer",
      "surfaceName": "新建应用抽屉",
      "surfaceType": "drawer",
      "closeSelector": "[data-ann='close-create-app']",
      "waitMs": 300
    }
  ]
}
```

## 6. 扫描命令

先启动原型 dev server 或静态服务，再执行：

```bash
node scripts/scan_rendered_routes.mjs \
  <project_root> \
  --base-url http://127.0.0.1:8765 \
  --interaction-plan prototype-annotator/interaction-plan.json
```

省略 `--interaction-plan` 时，扫描器会尝试读取默认路径；文件不存在则跳过 interaction 扫描，保持原有行为。

## 7. 扫描输出

成功执行后，`page-map.json` 会包含：

- 顶层 `surfaces[]`
- `pages[].elements[].surfaceId`（属于二级界面的元素）

## 8. 注意事项

- 仅配置需要扫描的交互，不要让扫描器自动点击所有按钮
- 删除、发布、重置等高风险操作只有在 plan 中明确配置时才触发
- 单条 interaction 失败会记录 warning，不阻断整个扫描流程
- 静态 `scan_prototype.py` 只能辅助识别关键词，不能替代 interaction plan

## 9. 进一步阅读

- 标注策略：`references/surface-annotation-guide.md`
- Schema：`schemas/interaction-plan.schema.json`
