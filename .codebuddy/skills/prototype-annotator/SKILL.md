---
name: prototype-annotator
description: 为已有 HTML、React、Vue、Vite 或静态产品原型生成、注入、编辑和维护可视化页面标注层。用于根据原型与 PRD、产品说明书、上游页面级需求说明文档或交互文档生成结构化标注，给页面元素添加可显隐编号、Markdown 富文本说明卡片、表格、高亮和 Mermaid 图；支持浏览器内新增、编辑、删除、显隐标注，并回写本地 prototype-annotator/annotations.json。适用于原型评审、产品交付、研发交接、测试验收和客户演示；页面级需求文档只作为标注证据来源，不把本 skill 当作需求说明文档生成器使用。
---

# Prototype Annotator

## 目标与边界

为已有原型叠加可交互、可编辑、可交付的标注层。静态 HTML 默认产物写在目标项目的 `prototype-annotator/`，该目录同时满足本地编辑/评审和静态发布；旧 `.prototype-annotations/` 仅作为兼容读取目录。React/Vue/Vite 项目通过 adapter 与 Vite 写入插件接入。

不要用本 skill 单独生成 PRD、页面级需求说明文档或设计稿。已有 `prototype-specs/current/*.md`、`src/page-specs/current/*.md`、PRD、会议纪要或 README 只能作为标注证据来源。

术语边界必须明确：本 skill 里的 `P` 类型是“页面级说明标注”或“页面功能介绍标注”，它是写入标注数据目录的 `annotations.json` 并显示在原型页面上的一条标注，不是 `prototype-spec-annotator` 维护的 `prototype-specs/current/*.md` / `src/page-specs/current/*.md` 页面说明或需求说明文档。用户说“添加页面说明”时，除非明确要求生成文档，否则应改述为“添加页面级说明标注”；如果用户要生成或维护页面级需求说明文档，应建议使用 `prototype-spec-annotator`。

## 默认决策

- 默认受众模式是 `product-review`。用户说“交付研发 / 给前端 / 研发交接”时切到 `dev-handoff` 并读取 `references/dev-handoff-standard.md`。
- 默认就地接入，不生成 `*-annotated` 副本；只有用户明确要求保留副本时才给 `inject_annotations.py` 传 `--output`。
- 默认不依赖 Chrome 插件、Supabase 或外部服务。
- 默认保护人工内容：不要静默覆盖 `createdBy: "manual"` 或 `target.strategy: "manual"` 的标注。
- 默认使用产品经理语言；`dev-handoff` 才补充源码、store、API、mock 边界等研发信息。
- 默认不为所有 DOM 元素生成标注，只标注影响理解、实现、评审、验收和交付的内容。

## 目标路径与任务推断

先解析目标路径，不要在可推断时要求用户重复提供项目目录：

- 用户给出路径时，使用该路径作为 `<prototype_path>` 或 `<project_root>`。
- 用户未给出路径时，先运行 `pwd`。如果当前目录包含 `package.json`、`vite.config.*`、`src/`、`index.html`、任意 `.html` 文件、`prototype-annotator/` 或 `.prototype-annotations/`，默认把当前目录作为目标项目。
- 只有当前目录明显不是原型或前端项目（例如当前目录就是本 skill 目录、没有 HTML/前端项目特征、或存在多个候选子项目且无法判断）时，才询问用户目标路径。
- 推断出目标后，在命令中使用解析后的绝对路径；不要把占位符 `<prototype_path>`、`<project_root>` 原样传给脚本。

再解析任务目标：

- 用户说明“从零生成、扫描、标注、接入、评审、研发交付、校验、增量更新”等目标时，按用户目标执行。
- 用户只说“使用这个 skill”“给当前项目做标注”或类似泛化请求时，不要停下来询问任务目标。若目标项目没有 `prototype-annotator/annotations.json` 或 `.prototype-annotations/annotations.json`，默认执行扫描、生成 `product-review` 标注草稿、接入运行时并给出本地评审方式；若已有标注，默认执行增量扫描、候选更新、质量校验，并给出继续人工评审或回写的下一步。

## 任务路由

先识别任务类型，只读取相关参考文件：

- **静态 HTML / 多页目录标注**：读取 `references/annotation-workflow.md`、`references/annotation-selection-policy.md`、`references/annotation-schema.md`；需要接入细节时读 `references/prototype-adapters.md`。
- **React / Vue / Vite / SPA 标注**：先读 `references/prototype-adapters.md`，必须用渲染路由扫描，不要只扫 `index.html`。
- **抽屉、弹窗、Popover、Dropdown、确认框**：读取 `references/surface-annotation-guide.md`；需要点击后扫描内部内容时再读 `references/interaction-plan-guide.md`。
- **从 PRD、产品说明或交互文档生成标注**：读取 `references/annotation-workflow.md`、`references/annotation-evidence-scan.md`、`references/product-annotation-writing-standard.md`。
- **已有 page specs 转标注证据**：项目存在 `prototype-specs/current/*.md` 或 `src/page-specs/current/*.md` 时读取 `references/spec-to-annotation-mapping.md`；只把这些文档当作证据，不在本 skill 中创建或改写页面级需求说明文档。
- **研发交付**：读取 `references/dev-handoff-standard.md`，并运行 dev-handoff 门禁。
- **selector 不稳定或大量结构选择器**：读取 `references/selector-strategy.md`，再运行 `scripts/suggest_data_ann_anchors.py`。
- **标注正文需要表格、高亮、Mermaid 或长内容**：读取 `references/rich-content-guide.md`。
- **按产品形态调整覆盖重点**：读取 `references/product-type-strategy.md`；修改类型枚举时读取 `references/annotation-type-taxonomy.md` 和 `references/annotation-types.json`。

## 最短工作流

### 1. 扫描原型

HTML 文件或静态目录：

```bash
python3 scripts/scan_prototype.py <prototype_path>
```

React / Vue / Vite / SPA：

```bash
node scripts/scan_rendered_routes.mjs <project_root> --base-url <dev_server_url>
```

`--interaction-plan` 只适用于 `scan_rendered_routes.mjs`。静态 `scan_prototype.py` 不支持点击打开二级界面；静态 HTML 只能扫描当前 DOM 和伴随 JS 行为提示。

React / Vue / Vite 项目如果包含 Sheet、Dialog、Drawer、Popover、Dropdown 等二级界面，先生成 interaction-plan 建议草案，再人工补齐稳定 trigger selector：

```bash
python3 scripts/suggest_interaction_plan.py <project_root>
```

建议草案默认写入 `prototype-annotator/interaction-plan.suggestions.json`。确认并补齐后，另存为 `prototype-annotator/interaction-plan.json` 再执行渲染扫描。

```bash
node scripts/scan_rendered_routes.mjs <project_root> --base-url <dev_server_url> --interaction-plan prototype-annotator/interaction-plan.json
```

### 2. 构建上下文与候选

```bash
python3 scripts/build_product_context.py <prototype_path> --docs <PRD.md>
python3 scripts/build_annotation_candidates.py <prototype_path> --docs <PRD.md>
```

候选必须解释生成或跳过原因。Toast / Message 不生成独立标注点，写入触发操作正文的“状态与异常”。

### 3. 生成与润色标注

```bash
python3 scripts/generate_annotations_draft.py <prototype_path> --audience product-review
```

每页至少保留 1 条 `P` 页面级说明标注，用作页面功能介绍。其他标注只保留高价值说明点，不按固定数量凑标注。草稿生成后，结合 PRD、上游页面级需求说明文档和原型做最后润色；除非用户明确只要机器草稿。

### 4. 注入或接入运行时

HTML 文件或静态目录：

```bash
python3 scripts/inject_annotations.py <html_or_dir>
```

React / Vue / Vite：

```bash
python3 scripts/install_framework_adapter.py <project_root> --framework react
python3 scripts/install_framework_adapter.py <project_root> --framework vue
```

安装脚本只复制 adapter 和 Vite 写入插件；如果提示入口未接入，必须把 `PrototypeAnnotatorProvider` 或 Vue plugin 接到应用入口，并把 `prototypeAnnotatorWritePlugin()` 加入 `vite.config.ts`。

### 5. 本地评审和回写

HTML / 静态构建产物：

```bash
python3 scripts/serve_annotation_review.py <prototype_path>
```

不要用普通静态服务做人工编辑；静态服务不能处理回写请求，运行时只能把修改暂存到浏览器 `localStorage`。

React / Vue / Vite 项目使用 dev server，并确认 Vite 写入插件已接入。保存验证时检查 `prototype-annotator/history.jsonl` 与 `prototype-annotator/annotations.json` 是否更新。

如果页面提示“已暂存浏览器，未写入项目文件”，说明当前服务不可写；必须改用 `serve_annotation_review.py` 或已接入写入插件的 Vite dev server。下次打开页面时可选择加载浏览器草稿，再导出或重新保存。

### 6. 发布前校验静态资产

静态 HTML / 多页目录要发布到 Netlify、Vercel 或其他静态托管前，必须确认发布目录包含已注入 HTML 与整套 `prototype-annotator/` 资源：

```bash
python3 scripts/inject_annotations.py <prototype_path>
python3 scripts/validate_annotations.py <prototype_path> --deploy-check
```

静态 HTML 发布目录必须包含同一个 `prototype-annotator/` 标注目录：

```text
prototype-annotator/
  annotations.json
  assets/
  runtime/
    prototype-annotator.css
    markdown-renderer.js
    mermaid-loader.js
    prototype-annotator.js
  history.jsonl                  # 本地编辑后产生，可随原型交付或按需排除
  page-map.json                  # 扫描结果，可随原型交付或按需排除
  annotation-candidates.json     # 候选标注证据，可随原型交付或按需排除
```

静态线上 HTML 应引用 `./prototype-annotator/annotations.json` 与 `./prototype-annotator/runtime/*.js/css`。本地编辑/评审服务也默认读写同一份 `prototype-annotator/annotations.json`。旧 `.prototype-annotations/` 只用于兼容历史项目，不再作为静态 HTML 推荐目录。

React / Vue / Vite 项目要发布到 Netlify、Vercel 或其他静态托管前，必须把剪贴板图片和标注数据同步到 Vite `public` 目录：

```bash
python3 scripts/sync_deploy_assets.py <project_root>
python3 scripts/sync_deploy_assets.py <project_root> --check
python3 scripts/validate_annotations.py <project_root> --deploy-check
```

该脚本会把 `prototype-annotator/assets/` 与 `prototype-annotator/annotations.json` 同步到 `public/prototype-annotator/`。构建后应能在 `dist/prototype-annotator/assets/` 中看到标注 Markdown 引用的图片。旧 `.prototype-annotations/` 项目会被读取并迁移到新目录。

### 7. 校验和报告

```bash
python3 scripts/validate_annotations.py <prototype_path> --lint-language product-review
python3 scripts/validate_annotations.py <prototype_path> --strict-quality
python3 scripts/validate_annotations.py <prototype_path> --strict-quality --lint-language product-review
python3 scripts/validate_annotations.py <prototype_path> --deploy-check
python3 scripts/render_annotation_report.py <prototype_path>
```

研发交付必须运行：

```bash
python3 scripts/generate_annotations_draft.py <prototype_path> --promote-all-selected
python3 scripts/validate_annotations.py <prototype_path> --strict-quality --dev-handoff --fail-on-pending-review
python3 scripts/audit_annotation_coverage.py <prototype_path>
```

## 内容规则

标注正文使用 Markdown，不要改成富文本编辑器。卡片默认展示产品说明；只有存在研发说明和证据时才展示对应 Tab。编辑模式支持维护 `title`、`selector`、`annotationType`、`audienceMode`、`contentMarkdown`、`devNotesMarkdown`、`evidence`。

默认优先说明：

- 业务含义
- 使用场景
- 用户操作
- 系统反馈
- 页面跳转
- 状态变化
- 业务规则
- 异常处理
- 待确认问题

不要把源码路径、selector、store、state、mock 数据作为 `product-review` 主说明。关键假设写入“待确认”，不要把不确定内容写成事实。

当标注内容包含跨步骤流程、状态流转、权限/规则分支、AI 处理链路、数据链路或二级界面交互链路时，可以在对应小节中追加简短 Mermaid 图。自动生成正文时优先使用：

- `flowchart LR`：页面主流程、页面跳转、数据链路。
- `flowchart TD`：规则判断、权限分支、AI 处理、二级界面提交/确认流程。
- `stateDiagram-v2`：状态枚举和状态流转。

不要为了装饰添加 Mermaid。普通字段、简单按钮、搜索筛选、静态组件说明优先使用列表或表格。Mermaid 节点标签应短、可读、无实现细节；复杂图应拆成多条标注或改用列表。

`P` 页面级说明标注必须使用统一模板，避免不同 AI 执行器输出结构漂移：

```md
### 页面功能介绍

### 核心内容

### 业务流程

### 主要操作

### 待确认
```

## Annotation 数据要点

`annotationType` 表达产品语义，不替代 `kind`、`dimension`、`topics`。核心类型：

- `P` 页面级说明标注（页面功能介绍，不是页面说明文档）
- `A` 操作交互
- `J` 页面跳转
- `S` 状态说明
- `R` 规则说明
- `PERM` 权限控制
- `AI` AI 处理逻辑

完整枚举和维度映射以 `references/annotation-types.json` 为准。修改类型时同步检查 `references/annotation-type-taxonomy.md`、`schemas/annotations.schema.json` 和相关脚本。

生成标注时保留旧字段并补充新字段：

```json
{
  "annotationType": "A",
  "kind": "interaction",
  "dimension": "Primary action",
  "topics": ["interaction", "flow"]
}
```

可以额外写入 `topics`、`nextActions`、`dependencies`、`risks`、`openQuestions` 等字段；旧运行时只依赖 `contentMarkdown`，这些增强字段不得作为显示标注的唯一数据源。

## 产物结构

```text
prototype-annotator/
  README.md          # 标注目录说明与编辑入口
  annotations.json  # 标注数据源，人工新增/编辑/删除最终写这里
  assets/           # 标注 Markdown 引用的本地图片资产，例如剪贴板粘贴截图
  page-map.json      # 扫描原型得到的页面与元素索引
  annotation-candidates.json # 证据扫描得到的候选标注点和跳过原因
  data-ann-plan.json # 源码稳定锚点建议，默认不直接修改业务源码
  history.jsonl      # 本地评审服务写入的编辑历史
  runtime/           # 注入后的静态运行时资源
    prototype-annotator.css
    prototype-annotator.js
    markdown-renderer.js
    mermaid-loader.js
```

静态注入的 HTML 会包含一份内嵌 JSON 快照，但正式数据源仍是 `prototype-annotator/annotations.json`。HTTP 预览时运行时优先读取该文件；只有离线打开或读取失败时才用内嵌快照。使用 `serve_annotation_review.py` 保存静态 HTML 标注时，服务会同步刷新已注入 HTML 的内嵌快照；如果用户用其他方式直接改 `annotations.json`，需要重新执行 `inject_annotations.py` 或重新打开评审服务保存一次，避免离线快照过期。

Vite / React / Vue 发布副本由 `scripts/sync_deploy_assets.py` 维护：

```text
public/
  prototype-annotator/
    annotations.json
    assets/
```

不要手动维护 `dist/`；构建产物应由 `public/prototype-annotator/` 进入 `dist/prototype-annotator/`。

## Skill 资源目录

- `scripts/`：确定性命令行工具，负责扫描、候选生成、草稿生成、注入、评审服务、校验、清理和报告导出。
- `references/`：按需读取的标注策略、schema 说明、产品形态策略、适配方式和富文本规则。
- `references/annotation-types.json`：`annotationType` 枚举、维度到类型映射和维度 topics 的权威定义。
- `templates/`：注入到原型中的运行时资源和 React/Vue/Vite 接入片段；不要把这些文件加载进上下文，除非需要修改运行时或 adapter。
- `schemas/`：机器可读 JSON Schema，用于维护 `annotations.json`、`page-map.json` 和候选策略结构；修改数据结构时同步检查这些 schema。
- `examples/`：保留为回归验证资产。不要在真实任务中复制示例输出；需要验证 skill 主链路时运行 `python3 scripts/smoke_test.py`，该脚本会把示例复制到临时目录。

## 验收清单

- 每个页面至少有 1 条 `P` 页面级说明标注，作为页面功能介绍；其他标注只保留高价值说明点，数量由页面复杂度决定，不要求每页固定条数。简单页通常 3-5 条，核心页可到 4-8 条，低价值页允许只有页面级说明标注。
- 不存在同页重复语义标注，表格行级 `删除/停用/启用/编辑` 等重复操作已折叠为一条规则说明。
- 每条 AI 标注能追溯到 selector、页面文本、PRD 或上游页面级需求说明文档证据。
- 每条新生成标注都应包含合法 `annotationType`；旧数据缺少时普通校验只给 warning。
- `productProfile` 存在时，严格校验会按项目级检查 AI、数据、SaaS、企业/审批等产品形态的必要标注类型覆盖。
- `annotation-candidates.json` 能解释核心候选点为什么生成或为什么跳过。
- 标注徽章可显隐，隐藏不会删除数据。
- 标注徽章编号和侧栏编号必须按当前页面/当前二级界面上下文连续展示；`ANN-Pxx-NNN` 只作为稳定数据 ID，不能直接替代用户可见序号。
- 标注列表必须支持拖动避让页面关键信息，并提供位置复位；拖动位置可在同一路径下持久化。
- 信息卡片能根据内容调整大小，长内容可滚动，并支持全屏查看。
- 编辑卡片支持全屏编辑，长 Markdown 内容在大编辑区内可维护。
- 标注可在页面内新增、编辑、删除。
- 浏览器内保存失败时不能提示“已保存”；应明确提示仅暂存浏览器，并能在下次打开时恢复草稿。
- 运行 `clear_annotations.py` 后，标注数据与静态注入块已清理，原型页面仍能正常打开和展示。
- 重生成时不覆盖人工创建或人工修正 selector 的标注。
- 在 React/Vue/Vite 源码项目中，`vite.config.ts` 已接入 `prototypeAnnotatorWritePlugin()`，保存后会生成 `prototype-annotator/history.jsonl`。
- Markdown 标题、加粗、高亮、表格和 Mermaid 能正常展示。
- Markdown 图片能正常展示；在线评审或已接入 Vite 写入插件时，可在产品说明/研发说明编辑区直接粘贴剪贴板图片，图片写入 `prototype-annotator/assets/`，正文插入 `![...](./prototype-annotator/assets/...)` 或 `![...](/prototype-annotator/assets/...)`。
- 静态 HTML 发布静态托管前已运行 `scripts/inject_annotations.py` 与 `scripts/validate_annotations.py --deploy-check`，发布目录包含单一 `prototype-annotator/` 标注目录。
- React / Vue / Vite 发布静态托管前已运行 `scripts/sync_deploy_assets.py`，`public/prototype-annotator/assets/` 包含全部 Markdown 图片，`validate_annotations.py --deploy-check` 通过。
- `annotations.json` 可被导出、复用和继续维护。
- `annotation-report.md` 和 `annotation-checklist.md` 可由 `render_annotation_report.py` 生成。
- 使用 `serve_annotation_review.py` 保存静态 HTML 标注时，`annotation-report.md` 和 `annotation-checklist.md` 会自动刷新；React/Vue/Vite 项目保存后仍应重新运行 `render_annotation_report.py`。
- HTML、React 和 Vue 三类项目都必须完成校验；React/Vue 校验前必须有渲染路由扫描得到的 `page-map.json`。
- 二级界面标注必须有 trigger selector；多个业务 surface 共用同一个抽屉/弹窗容器时，必须补充 `contentSelector`、`titleText` 或 `textIncludes` 等内容签名，避免打开一个抽屉时显示其他抽屉的标注。
- 不允许把多个业务入口合并到同一个 surface 的 `triggerSelector` 中（例如 `buttonA, buttonB, buttonC`）。同一个容器承载不同业务抽屉时，应拆成多个 surface，并分别配置 `triggerSelector` 与 `titleText` / `textIncludes`。
- 当抽屉、弹窗或下级承载面打开时，页面上默认只展示当前 surface 的标注；其他页面或其他 surface 的标注应隐藏，避免影响评审视线。
- 表格行级操作组不得锚定到单个 icon / svg / 按钮，应锚定到操作组容器或操作单元格；若需要解释单个高风险操作，应单独生成明确标题的操作标注。
- 手动新增标注的稳定 ID 必须按当前页已有 `ANN-Pxx-NNN` 顺延；页面徽标号和侧栏编号按当前可见列表重新连续计算，保存前后不能出现 1、3、6 这类跳号。
- 静态 HTML 的内嵌 `prototype-annotations-data` 快照必须与 `prototype-annotator/annotations.json` 对应页面一致。
- 草稿结果至少通过 `--strict-quality`；交付级结果必须通过 `--strict-quality --fail-on-pending-review`。严格校验必须拦截 AI 标注批量绕过 `review.required`、关闭/取消按钮泛写提交保存、通用模板正文、二级界面 header/body/footer/title 误注册 surface、展示编号跳号等问题。
- 研发交付结果必须通过 `--strict-quality --dev-handoff --fail-on-pending-review`，且 `annotation-checklist.md` 中「研发交付缺口」无未勾选项。
- selector 校验通过，页面结构变化后有 fallback 定位。
- 修改运行时、注入或回写链路后运行 `python3 scripts/smoke_test.py`；如环境安装了 Playwright，运行 `python3 scripts/smoke_test.py --require-browser` 强制验证真实浏览器新增标注和文件回写。
