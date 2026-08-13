# Surface 二级界面标注指南

## 1. Surface 定义

Surface 是页面主内容之外，由用户操作触发或临时出现的二级承载面，包括：

- 抽屉 Drawer
- 弹窗 Modal
- 确认框 Confirm
- 气泡卡片 Popover
- 下拉菜单 Dropdown
- Toast / Message（短暂反馈，默认不独立打点）
- Notification / Alert / Banner（常驻提示可正常标注）

## 2. 何时使用 surface 模型

当页面包含以下情况时，应使用 `surfaces[]` 与 `surfaceId` 标注：

- 点击按钮后才出现的抽屉或弹窗
- 确认删除/停用等二次确认框
- 展开后才可见的 Popover 或 Dropdown 菜单项
- 通过 React / Vue Portal 挂载到 `body` 外的二级界面

普通主页面元素继续按现有页面标注规则处理，不必强行挂 `surfaceId`。

## 3. 抽屉和弹窗如何标注

`surfaces[]` 只能登记真实二级界面容器，例如 `#drawer-plan-form`、`#modal-sync-diff`、`.drawer-overlay`、`.modal-overlay` 或组件库的 Drawer/Dialog root。不要把 header、body、footer、title、content 等内部区域登记为独立 surface；这些区域只作为字段和按钮的 DOM 上下文，内部标注统一挂到父级 surface。

每个二级界面建议至少包含：

| 类型 | dimension | displayWhenClosed |
|------|-----------|-------------------|
| 打开入口 | Surface trigger | `on-trigger` |
| 整体说明 | Surface overview | `on-trigger` |
| 内部字段 | Surface field | `sidebar-only` |
| 保存/取消/确认 | Surface action | `sidebar-only` |
| 删除确认说明 | Surface confirm | `on-trigger` |

正文应覆盖：业务含义、打开/关闭规则、字段规则、状态与异常、待确认问题。

## 4. 未打开时如何展示

- **整体说明 / 入口说明**：标注点挂在触发按钮（`fallbackAnchorSelector` 或 `surface.triggerSelector`）
- **内部字段 / 内部操作**：不在页面打点，只在侧栏「二级界面」分组展示
- **Dropdown / Popover 菜单项**：使用 `hidden-until-open`，打开后再显示页面标注点
- **不要**把隐藏 DOM 的 selector 强行显示在页面左上角

用户点击侧栏中的内部标注且 surface 未打开时，应提示先打开对应入口。

## 5. 打开后如何展示

- surface 打开后，runtime 在 surface root 内查找 `target.selector` 并显示标注点
- surface 关闭后，内部页面标注点消失，侧栏分组保留
- 用户手动打开/关闭 drawer 时，标注点应自动切换
- 当任意抽屉、弹窗或下级承载面打开时，页面上默认只展示当前打开 surface 的标注，隐藏主页面和其他 surface 的标注。
- `on-trigger` 标注在 surface 打开后应优先锚定到 surface root，而不是继续挂在入口按钮上，避免打开抽屉后标注仍显示在主页面按钮附近。

## 5.1 共用容器的业务 surface 拆分

很多原型会用同一个 DOM 容器承载多个业务抽屉，例如统一的 `#drawer-container`。这种情况下必须按业务语义拆分 surface：

- 不要把多个入口合并成一个 `triggerSelector`，例如 `button[onclick="openCreateApp()"], button[title="主数据授权"], button[title="查看凭证"]`。
- 每个业务抽屉单独设置 `surfaceId`、`name`、`triggerSelector` 和 `titleText` / `textIncludes`。
- 多个 surface 可以共用同一个 `openSelector`，但必须通过 `titleText`、`textIncludes` 或 `contentSelector` 区分当前打开的是哪个业务界面。
- 如果标题会随业务模式变化，不要把“创建/编辑对象”“新增/修改记录”这类复合文案作为唯一严格匹配条件。优先写成实际渲染标题的候选数组，例如 `titleText: ["新建记录", "编辑记录"]`、`titleText: ["创建应用", "编辑应用"]`；如果 `openSelector` 已经是唯一业务容器，可以只保留 `containerSelector` / `openSelector`。
- `containerSelector` 可以匹配 surface 根节点本身，也可以匹配根节点内部的稳定内容容器。

## 6. 手动在抽屉内新增标注

用户在**已打开**的抽屉/弹窗内点击新增标注时，runtime 应自动：

- 写入 `surfaceId`
- 设置 `displayWhenClosed: sidebar-only`
- 设置 `fallbackAnchorSelector` 为 surface 的 `triggerSelector`

这样保存后关闭抽屉，标注仍可在侧栏看到；再次打开抽屉后，页面标注点正常显示。

## 7. Toast / Message 如何标注

Toast / Message 通常是短暂反馈，**不建议**作为独立长期标注点。

推荐写入触发操作（如保存、删除、提交）正文的「状态与异常」：

```markdown
### 状态与异常

- 操作成功：展示成功 toast，并刷新当前列表。
- 操作失败：展示失败 toast，保留用户当前输入。
```

## 8. 常驻 Alert / Banner / Notification

若提示内容是常驻的、可关闭的或业务流程相关的，可以正常生成独立标注，例如：

- 页面顶部风险提示
- 审核失败原因
- 权限不足提示
- 数据同步异常提示

## 9. surface ID 命名

格式：`surface-{pageKey}-{slug}`

示例：`surface-P01-create-app-drawer`

## 10. 相关文件

- 数据结构：`references/annotation-schema.md`
- 扫描辅助：`references/interaction-plan-guide.md`
- 选择策略：`references/annotation-selection-policy.md`
