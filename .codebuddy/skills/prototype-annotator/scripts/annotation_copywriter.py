#!/usr/bin/env python3
"""Generate audience-aware annotation content in product-manager language."""

from __future__ import annotations

import re
from typing import Any


FILTER_RE = re.compile(r"搜索|筛选|查询|过滤|filter|search|query", re.I)
SEARCH_PLACEHOLDER_RE = re.compile(r"搜索|请输入关键词|search", re.I)
HIGH_RISK_RE = re.compile(r"删除|移除|清空|驳回|下架|取消授权|重置密钥|remove|delete|reject", re.I)
STATUS_TOGGLE_RE = re.compile(r"启用|停用|禁用|开关|toggle|switch|enable|disable", re.I)
ROW_ACTION_RE = re.compile(r"编辑|删除|启用|停用|授权|下载|查看|详情|重置|密钥|edit|delete|enable|disable|download", re.I)
CLOSE_ACTION_RE = re.compile(r"^(×|x|关闭|取消)$|close|cancel", re.I)
SAVE_ACTION_RE = re.compile(r"保存|提交|确认|发布|save|submit|confirm|publish", re.I)

VALID_AUDIENCE_MODES = ("product-review", "dev-handoff", "qa-acceptance", "customer-demo")
DEFAULT_AUDIENCE_MODE = "product-review"


def compact(value: str, limit: int = 32) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def candidate_label(candidate: dict, fallback: str = "当前区域") -> str:
    return compact(str(candidate.get("fallbackText") or candidate.get("title") or fallback), 32)


def label_text(candidate: dict) -> str:
    return normalize(str(candidate.get("fallbackText") or candidate.get("title") or ""))


def candidate_topics(candidate: dict) -> list[str]:
    topics = candidate.get("topics")
    if isinstance(topics, list):
        return [str(item) for item in topics if str(item).strip()]
    return []


def evidence_items(candidate: dict, limit: int = 4) -> list[str]:
    evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), list) else []
    result: list[str] = []
    for item in evidence:
        text = normalize(str(item))
        if not text or text in result:
            continue
        result.append(text)
        if len(result) >= limit:
            break
    return result


def candidate_reason(candidate: dict) -> str:
    reason = normalize(str(candidate.get("reason") or ""))
    if not reason or re.search(r"适合说明|候选|缺少明确业务规则", reason):
        return ""
    return reason.rstrip("。")


def page_name_for(candidate: dict, product_context: dict | None) -> str:
    page = page_context(candidate, product_context)
    return normalize(str(page.get("pageName") or candidate.get("pageTitle") or candidate.get("pageRoute") or candidate.get("pagePath") or "当前页面"))


def is_status_filter_candidate(candidate: dict) -> bool:
    tag = str(candidate.get("tag") or "")
    if tag != "select":
        return False
    attrs = candidate.get("attrs") if isinstance(candidate.get("attrs"), dict) else {}
    element_id = str(attrs.get("id") or "")
    visible = normalize(str(candidate.get("fallbackText") or ""))
    if "status" in element_id.lower() or "filter" in element_id.lower():
        return True
    return bool(re.search(r"全部状态|状态筛选|启用|停用", visible))


def is_search_candidate(candidate: dict) -> bool:
    if is_status_filter_candidate(candidate):
        return False
    tag = str(candidate.get("tag") or "")
    if tag in {"section", "main", "header", "div", "nav", "aside"}:
        return False
    topics = {topic.lower() for topic in candidate_topics(candidate)}
    if topics & {"search"}:
        return True
    if topics & {"filter"} and tag in {"input", "textarea"}:
        return True
    attrs = candidate.get("attrs") if isinstance(candidate.get("attrs"), dict) else {}
    placeholder = str(attrs.get("placeholder") or "")
    return tag in {"input", "textarea"} and bool(SEARCH_PLACEHOLDER_RE.search(placeholder))


def page_context(candidate: dict, product_context: dict | None) -> dict:
    page_key = str(candidate.get("pageKey") or "")
    if not product_context:
        return {}
    for page in product_context.get("pages") or []:
        if str(page.get("pageKey") or "") == page_key:
            return page if isinstance(page, dict) else {}
    return {}


def product_name(product_context: dict | None) -> str:
    if not product_context:
        return ""
    return normalize(str(product_context.get("productName") or ""))


def main_user(product_context: dict | None) -> str:
    if not product_context:
        return "业务用户"
    roles = product_context.get("roles")
    if isinstance(roles, list) and roles:
        return normalize(str(roles[0]))
    return "业务用户"


def join_lines(*parts: str) -> str:
    return "\n".join(parts).rstrip() + "\n"


def section(title: str, body: str) -> str:
    body = body.strip()
    if not body:
        return ""
    return f"### {title}\n\n{body}\n"


def bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items if item)


def mermaid_block(lines: list[str]) -> str:
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def generate_status_filter_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "状态筛选")
    return join_lines(
        section("业务含义", f"「{label}」用于按对象当前状态缩小列表范围，帮助用户快速定位目标数据。"),
        section(
            "交互规则",
            bullet_list(
                [
                    "用户选择状态条件后，系统应刷新列表并仅展示符合条件的记录。",
                    "切换为「全部状态」时，应恢复默认列表范围。",
                    "不同状态选项应与业务状态枚举保持一致。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                [
                    "筛选后无结果时，应展示空状态并提示调整筛选条件。",
                    "筛选失败时，应保留用户已选条件并提示重试。",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "状态枚举是否完整？",
                    "是否需要记住用户上一次筛选条件？",
                ]
            ),
        ),
    )


def generate_search_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "搜索")
    page = page_context(candidate, product_context)
    purpose = normalize(str(page.get("purpose") or ""))
    biz = f"「{label}」用于帮助用户快速定位目标内容，减少逐项浏览成本。"
    if purpose:
        biz = f"「{label}」用于帮助用户在当前页面快速查找与业务目标相关的内容。{purpose}"
    return join_lines(
        section("业务含义", biz),
        section(
            "使用场景",
            "当用户已经知道关键词、名称、类型或部分条件时，可以通过搜索或筛选快速缩小结果范围。",
        ),
        section(
            "交互规则",
            bullet_list(
                [
                    f"用户输入关键词或筛选条件后，点击「{label}」或确认操作触发查询。",
                    "系统根据条件刷新结果列表。",
                    "清空条件后，应恢复默认列表或推荐内容。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                [
                    "搜索中：展示加载状态。",
                    "无结果：展示空状态，并提示用户调整关键词。",
                    "搜索失败：保留用户输入，并提示稍后重试。",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "是否支持模糊搜索？",
                    "是否需要保留用户上一次搜索条件？",
                    "是否需要按资源类型进一步筛选？",
                ]
            ),
        ),
    )


def generate_page_overview_product(candidate: dict, product_context: dict | None) -> str:
    page_title = normalize(str(candidate.get("pageTitle") or candidate.get("fallbackText") or candidate.get("pageKey") or "当前页面"))
    page = page_context(candidate, product_context)
    user = normalize(str(page.get("mainUser") or main_user(product_context)))
    purpose = normalize(str(page.get("purpose") or candidate.get("pageSummary") or f"帮助{user}完成与「{page_title}」相关的业务操作。"))
    tasks = page.get("primaryTasks") if isinstance(page.get("primaryTasks"), list) else []
    task_lines = [f"- {normalize(str(item))}" for item in tasks[:5] if normalize(str(item))]
    if not task_lines:
        focus = candidate.get("readingFocus") if isinstance(candidate.get("readingFocus"), list) else []
        task_lines = [f"- {normalize(str(item))}" for item in focus[:5] if normalize(str(item))]
    if not task_lines:
        task_lines = [f"- 围绕「{page_title}」确认页面职责、主要对象和关键操作边界。"]
    core_lines = [
        f"- 页面对象：围绕「{page_title}」呈现核心业务信息、状态和可执行操作。",
        f"- 页面目标：{purpose}",
    ]
    flow_lines = [
        f"- 进入页面：用户进入「{page_title}」后先识别当前对象、状态和可处理事项。",
        "- 完成任务：用户通过页面中的关键操作推进业务处理，系统同步反馈成功、失败或待确认状态。",
        "- 离开页面：用户完成处理后返回上级页面或进入下一步业务流程。",
    ]
    return join_lines(
        section("页面功能介绍", f"本页面用于帮助【{user}】完成与「{page_title}」相关的核心任务。"),
        section("核心内容", "\n".join(core_lines)),
        section(
            "业务流程",
            "\n".join(flow_lines)
            + "\n\n"
            + mermaid_block(
                [
                    "flowchart LR",
                    "  A[进入页面] --> B[识别对象与状态]",
                    "  B --> C[执行关键操作]",
                    "  C --> D[查看系统反馈]",
                    "  D --> E[进入下一步]",
                ]
            ),
        ),
        section("主要操作", "\n".join(task_lines)),
        section(
            "待确认",
            bullet_list(
                [
                    "页面是否还需要区分不同角色的展示内容？",
                    "是否需要补充空状态、异常状态或权限不足状态？",
                ]
            ),
        ),
    )


def generate_component_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate)
    page = page_context(candidate, product_context)
    page_name = normalize(str(page.get("pageName") or candidate.get("pageTitle") or "当前页面"))
    return join_lines(
        section(
            "业务含义",
            f"「{label}」用于展示或填写相关信息，帮助用户完成「{page_name}」页面的核心任务。",
        ),
        section(
            "使用场景",
            f"用户在处理「{page_name}」相关任务时，需要通过该区域查看、输入或确认相关信息。",
        ),
        section(
            "展示规则",
            bullet_list(
                [
                    "默认展示与当前任务相关的数据。",
                    "数据为空时应展示空状态提示。",
                    "内容较多时应支持分页、折叠或滚动查看。",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "该区域是否需要支持编辑？",
                    "数据来源和刷新时机是否已明确？",
                ]
            ),
        ),
    )


def normalize_annotation_title(candidate: dict) -> str:
    raw = normalize(str(candidate.get("fallbackText") or candidate.get("title") or ""))
    dimension = str(candidate.get("dimension") or "")
    annotation_type = str(candidate.get("annotationType") or "")

    if dimension == "Page overview" or annotation_type == "P":
        page_title = compact(str(candidate.get("pageTitle") or raw or ""), 18)
        return f"{page_title} · 页面介绍" if page_title else "页面功能介绍"

    if is_status_filter_candidate(candidate) or re.search(r"全部状态.*启用.*停用|状态筛选", raw):
        return "状态筛选"
    if dimension == "Table row actions":
        return "行级操作"
    if dimension == "Table and list" or str(candidate.get("tag") or "") == "table":
        return "数据列表"

    mappings = (
        (re.compile(r"搜索.*|请输入.*|search", re.I), "搜索筛选"),
        (re.compile(r"^全部状态$|^状态筛选$", re.I), "状态筛选"),
        (re.compile(r"^\+?\s*新建", re.I), "新建入口"),
        (re.compile(r"行级操作|操作组", re.I), "行级操作"),
        (re.compile(r"^状态[:：]", re.I), "状态说明"),
        (re.compile(r"识别值|置信度|AI识别", re.I), "AI识别结果确认"),
        (re.compile(r"通过并上架|审批通过", re.I), "审批通过并上架"),
        (re.compile(r"^驳回$", re.I), "审批驳回"),
        (re.compile(r"^下载$", re.I), "下载操作"),
        (re.compile(r"^授权$", re.I), "授权操作"),
        (re.compile(r"^删除$", re.I), "删除操作"),
        (re.compile(r"^停用$|^禁用$", re.I), "停用操作"),
        (re.compile(r"^启用$", re.I), "启用操作"),
        (re.compile(r"^编辑$", re.I), "编辑操作"),
    )
    for pattern, title in mappings:
        if pattern.search(raw):
            return compact(title, 12)

    if str(candidate.get("tag") or "") == "canvas":
        return "指标图表"
    if annotation_type in {"HITL", "FALLBACK", "AI", "METRIC"}:
        type_titles = {
            "HITL": "人工确认",
            "FALLBACK": "失败兜底",
            "AI": "AI处理逻辑",
            "METRIC": "指标图表",
        }
        return compact(type_titles.get(annotation_type, "AI处理逻辑"), 12)

    cleaned = re.sub(r"[.…:：]+$", "", raw)
    if cleaned:
        return compact(cleaned, 12) or "未命名标注"
    return "未命名标注"


def generate_row_action_group_content(candidate: dict, product_context: dict | None) -> str:
    return join_lines(
        section(
            "业务含义",
            "行级操作用于对列表中的单条数据进行查看、编辑、启用、停用、授权、下载或删除等管理动作。",
        ),
        section(
            "操作规则",
            bullet_list(
                [
                    "用户点击某一行的操作按钮时，仅影响当前行对应的数据。",
                    "高风险操作，例如删除、停用、重置密钥，需要二次确认。",
                    "不同状态下可执行操作不同，禁用状态下应隐藏或置灰不可用操作。",
                    "权限不足时，应隐藏操作入口或置灰展示。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                [
                    "操作成功后刷新当前列表或更新当前行状态。",
                    "操作失败时保留当前列表状态，并提示失败原因。",
                    "高风险操作应记录操作日志。",
                ]
            ),
        ),
        section(
            "操作流程",
            mermaid_block(
                [
                    "flowchart TD",
                    "  A[选择行记录] --> B[点击行级操作]",
                    "  B --> C{是否高风险}",
                    "  C -->|是| D[二次确认]",
                    "  C -->|否| E[直接执行]",
                    "  D --> E",
                    "  E --> F[刷新列表状态]",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "哪些角色可以执行编辑、删除、启用、停用、授权等操作？",
                    "删除后是否允许恢复？",
                    "下载或密钥类操作是否需要二次验证？",
                ]
            ),
        ),
    )


def generate_status_toggle_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "状态切换")
    return join_lines(
        section(
            "业务含义",
            f"「{label}」用于控制当前对象是否可用，并影响相关业务流程是否可以继续使用该对象。",
        ),
        section(
            "操作规则",
            bullet_list(
                [
                    "用户切换状态后，系统应更新当前对象状态。",
                    "停用或禁用操作可能影响正在使用该对象的业务流程。",
                    "高风险状态变更建议进行二次确认。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                [
                    "切换成功后，当前行状态立即更新。",
                    "切换失败时，状态应回滚到操作前，并提示失败原因。",
                    "权限不足时，不展示切换入口或置灰展示。",
                ]
            ),
        ),
        section(
            "状态流转",
            mermaid_block(
                [
                    "stateDiagram-v2",
                    "  state \"启用\" as Enabled",
                    "  state \"停用\" as Disabled",
                    "  state \"失败\" as Failed",
                    "  [*] --> Enabled",
                    "  Enabled --> Disabled: 用户停用",
                    "  Disabled --> Enabled: 用户启用",
                    "  Enabled --> Failed: 更新失败",
                    "  Disabled --> Failed: 更新失败",
                    "  Failed --> Enabled: 回滚或重试",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "停用后是否影响历史数据？",
                    "停用后是否允许重新启用？",
                    "是否需要记录状态变更日志？",
                ]
            ),
        ),
    )


def generate_high_risk_action_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "高风险操作")
    return join_lines(
        section(
            "业务含义",
            f"「{label}」会对当前数据或业务状态产生重要影响，需要避免用户误操作。",
        ),
        section(
            "操作规则",
            bullet_list(
                [
                    "用户触发该操作后，应进行二次确认。",
                    "确认前不应立即执行。",
                    "操作成功后，应刷新列表或更新当前数据状态。",
                    "操作失败时，应保留原状态并提示失败原因。",
                ]
            ),
        ),
        section(
            "风险控制",
            bullet_list(
                [
                    "高风险操作建议记录操作日志。",
                    "涉及权限、安全或数据删除的操作，应校验用户权限。",
                    "不可逆操作需要在确认弹窗中明确提示影响范围。",
                ]
            ),
        ),
        section(
            "确认流程",
            mermaid_block(
                [
                    "flowchart TD",
                    "  A[触发高风险操作] --> B[展示影响范围]",
                    "  B --> C{用户确认}",
                    "  C -->|取消| D[返回原页面]",
                    "  C -->|确认| E[校验权限与状态]",
                    "  E --> F[执行操作并记录日志]",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "该操作是否可撤销？",
                    "是否需要管理员权限？",
                    "是否需要记录审批或操作日志？",
                ]
            ),
        ),
    )


def generate_hitl_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "AI 输出结果")
    return join_lines(
        section(
            "业务含义",
            f"「{label}」用于保证 AI 输出结果在进入正式流程前经过用户复核，降低错误结果直接生效的风险。",
        ),
        section(
            "确认规则",
            bullet_list(
                [
                    "用户需要查看 AI 输出结果。",
                    "对低置信度或关键字段进行重点提示。",
                    "用户可以修改、重新生成或确认使用 AI 结果。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                [
                    "未确认时，不允许进入下一步。",
                    "已确认后，记录确认时间和确认人。",
                    "如果用户修改 AI 结果，应保留修改后的最终结果。",
                ]
            ),
        ),
        section(
            "确认流程",
            mermaid_block(
                [
                    "flowchart TD",
                    "  A[查看AI结果] --> B{是否可信}",
                    "  B -->|是| C[确认使用]",
                    "  B -->|否| D[人工修改或重新生成]",
                    "  D --> A",
                    "  C --> E[进入正式流程]",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "哪些字段必须人工确认？",
                    "是否需要保存 AI 原始结果和人工修改结果？",
                ]
            ),
        ),
    )


def generate_prompt_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "提示词策略")
    return join_lines(
        section("业务含义", f"「{label}」定义 AI 处理时使用的提示词策略，影响生成结果的口径与边界。"),
        section(
            "策略规则",
            bullet_list(
                [
                    "提示词应明确输入范围、输出格式和业务约束。",
                    "策略变更后，应评估对历史结果和用户体验的影响。",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "提示词是否支持按角色或场景切换？",
                    "是否需要版本化管理？",
                ]
            ),
        ),
    )


def generate_context_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "上下文来源")
    return join_lines(
        section("业务含义", f"「{label}」说明 AI 或自动化能力可读取的上下文来源与使用边界。"),
        section(
            "上下文规则",
            bullet_list(
                [
                    "仅读取与当前任务相关的页面上下文和历史记录。",
                    "敏感信息应脱敏或按权限过滤后再参与处理。",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "上下文是否包含跨页面数据？",
                    "是否需要用户授权后才能读取？",
                ]
            ),
        ),
    )


def generate_action_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "操作")
    text = normalize(str(candidate.get("fallbackText") or ""))
    reason = candidate_reason(candidate)
    page_name = page_name_for(candidate, product_context)
    href = ""
    attrs = candidate.get("attrs") if isinstance(candidate.get("attrs"), dict) else {}
    if attrs:
        href = normalize(str(attrs.get("href") or attrs.get("to") or ""))
    if str(candidate.get("dimension") or "") == "Table row actions":
        return generate_row_action_group_content(candidate, product_context)
    if HIGH_RISK_RE.search(text):
        return generate_high_risk_action_content(candidate, product_context)
    if STATUS_TOGGLE_RE.search(text):
        return generate_status_toggle_content(candidate, product_context)
    meaning = f"「{label}」是「{page_name}」中的关键操作入口。"
    if reason:
        meaning = f"「{label}」{reason}。"
    interaction_lines = [
        f"用户点击「{label}」后，系统应执行与该入口对应的业务动作。",
        "操作前应校验当前用户、当前对象状态和必要输入是否满足条件。",
    ]
    if href and href not in {"#", "/"}:
        interaction_lines.append(f"若该入口用于跳转，应进入 `{href}` 对应页面并保留必要上下文。")
    else:
        interaction_lines.append("若操作在当前页完成，应给出明确成功反馈并更新相关区域。")
    state_lines = feedback_exception_lines(candidate) or [
        "处理中：按钮应进入 loading 或禁用状态，避免重复触发。",
        "失败：保留当前页面状态，并提示用户可执行的修正或重试方式。",
    ]
    questions = [
        "点击后的目标页面、弹窗或状态变化是否已确认？",
        "是否存在角色权限、状态限制或二次确认要求？",
    ]
    if evidence_items(candidate):
        questions.append("候选证据是否与 PRD 或上游页面级需求说明文档一致？")
    return join_lines(
        section("业务含义", meaning),
        section("交互规则", bullet_list(interaction_lines)),
        section("状态与异常", bullet_list(state_lines)),
        section("证据", bullet_list(evidence_items(candidate))) if evidence_items(candidate) else "",
        section("待确认", bullet_list(questions)),
    )


def generate_navigation_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "跳转")
    return join_lines(
        section("业务含义", f"「{label}」用于连接当前页面与下一步业务流程。"),
        section(
            "跳转规则",
            bullet_list(
                [
                    "用户完成当前操作后进入目标页面。",
                    "跳转时需要带入当前业务对象的标识信息。",
                    "返回时应保留用户上一次的筛选或编辑状态。",
                ]
            ),
        ),
        section(
            "跳转流程",
            mermaid_block(
                [
                    "flowchart LR",
                    "  A[当前页面] --> B[触发跳转]",
                    "  B --> C{校验通过}",
                    "  C -->|是| D[目标页面]",
                    "  C -->|否| E[停留并提示]",
                    "  D --> F[返回时保留上下文]",
                ]
            ),
        ),
        section(
            "分支情况",
            bullet_list(
                [
                    "成功：进入目标页面。",
                    "失败：停留当前页面并提示原因。",
                    "权限不足：提示无权限或隐藏入口。",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "跳转目标页面是否已明确？",
                    "是否需要区分不同角色的跳转路径？",
                ]
            ),
        ),
    )


def generate_state_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "状态")
    return join_lines(
        section("业务含义", f"「{label}」用于告诉用户当前事项所处阶段，并影响页面可执行操作。"),
        section(
            "状态规则",
            bullet_list(
                [
                    "不同状态下，页面展示内容和可操作按钮可能不同。",
                    "状态变化后，应及时刷新页面或给出明确提示。",
                    "用户需要能够理解当前状态下还能做什么。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                [
                    "加载中：展示加载状态。",
                    "空状态：提示暂无数据，并提供下一步操作建议。",
                    "失败状态：提示失败原因，并支持重试或返回。",
                ]
            ),
        ),
        section(
            "状态流转",
            mermaid_block(
                [
                    "stateDiagram-v2",
                    "  state \"默认\" as Default",
                    "  state \"加载中\" as Loading",
                    "  state \"成功\" as Success",
                    "  state \"失败\" as Failed",
                    "  state \"空状态\" as Empty",
                    "  state \"禁用\" as Disabled",
                    "  [*] --> Default",
                    "  Default --> Loading: 发起操作",
                    "  Loading --> Success: 处理完成",
                    "  Loading --> Failed: 处理失败",
                    "  Success --> Default: 刷新或返回",
                    "  Failed --> Loading: 重试",
                    "  Default --> Empty: 无数据",
                    "  Default --> Disabled: 权限或条件不满足",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "当前状态枚举是否完整？",
                    "每个状态下的可操作按钮是否已明确？",
                ]
            ),
        ),
    )


def generate_rule_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "规则")
    return join_lines(
        section("业务含义", f"「{label}」用于判断当前内容是否符合业务要求，并决定用户是否可以继续操作。"),
        section(
            "判断规则",
            bullet_list(
                [
                    "系统根据当前输入、用户角色、业务状态或配置项进行判断。",
                    "符合规则时，允许用户继续操作。",
                    "不符合规则时，应给出明确原因和处理建议。",
                ]
            ),
        ),
        section(
            "异常处理",
            bullet_list(
                [
                    "普通风险：允许用户补充说明后继续。",
                    "阻断风险：必须修改后才能继续。",
                    "规则缺失：提示用户联系管理员或稍后重试。",
                ]
            ),
        ),
        section(
            "判断流程",
            mermaid_block(
                [
                    "flowchart TD",
                    "  A[收集输入与上下文] --> B{符合业务规则}",
                    "  B -->|是| C[允许继续]",
                    "  B -->|普通风险| D[提示并允许补充]",
                    "  B -->|阻断风险| E[阻止提交]",
                    "  E --> F[展示修正建议]",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "规则来源是否明确？",
                    "是否存在人工覆盖或特批流程？",
                ]
            ),
        ),
    )


def generate_ai_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "AI 能力")
    page_name = page_name_for(candidate, product_context)
    reason = candidate_reason(candidate)
    meaning = f"「{label}」由 AI 辅助完成信息识别、生成、推荐或判断，减少用户手动处理成本。"
    if reason:
        meaning = f"「{label}」{reason}。"
    return join_lines(
        section("业务含义", meaning),
        section(
            "AI 输入",
            f"AI 输入应限定在「{page_name}」当前任务所需的信息范围内，包括用户输入、选中的业务对象、上传资料或页面上下文。",
        ),
        section(
            "AI 输出",
            "AI 输出应以可检查、可修改或可重新生成的方式展示，不能把推断结果直接视为最终结论。",
        ),
        section(
            "人工确认",
            "AI 结果不能默认等同于最终结论。用户提交前应能检查、修改或重新生成。",
        ),
        section(
            "失败兜底",
            bullet_list(
                [
                    "AI 生成失败时，应提示用户重试。",
                    "AI 结果不准确时，应支持人工修改。",
                    "低置信度内容应高亮提示。",
                ]
            ),
        ),
        section(
            "AI处理流程",
            mermaid_block(
                [
                    "flowchart TD",
                    "  A[用户输入或上传资料] --> B[读取任务上下文]",
                    "  B --> C[AI识别或生成]",
                    "  C --> D{结果是否可用}",
                    "  D -->|可用| E[展示结果供确认]",
                    "  D -->|不可用| F[失败兜底]",
                    "  E --> G[人工确认后提交]",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "是否需要展示置信度？",
                    "是否需要保留 AI 生成过程或引用依据？",
                    "低置信度或失败时是否允许人工继续处理？",
                ]
            ),
        ),
    )


def generate_table_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "列表")
    return join_lines(
        section("业务含义", f"「{label}」承载本页列表或表格数据的浏览、筛选与操作任务。"),
        section(
            "使用场景",
            "用户需要查看多条业务记录、对比关键字段，或从列表中选择目标对象继续操作。",
        ),
        section(
            "展示规则",
            bullet_list(
                [
                    "关注列含义、排序/筛选条件、空状态和分页规则。",
                    "同名行操作应在一条说明中描述整体规则，避免逐行重复。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                [
                    "加载中：展示加载状态。",
                    "无数据：展示空状态并提示下一步操作。",
                    "接口失败：保留筛选条件并提示重试。",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "是否需要支持批量操作？",
                    "行级操作的权限边界是否已明确？",
                ]
            ),
        ),
    )


def generate_data_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "数据口径")
    reason = candidate_reason(candidate)
    meaning = f"「{label}」用于说明当前页面中数据、指标或列表内容的来源、口径和刷新边界。"
    if reason:
        meaning = f"「{label}」{reason}。"
    return join_lines(
        section("业务含义", meaning),
        section(
            "数据规则",
            bullet_list(
                [
                    "明确数据来源、统计范围和权限过滤规则。",
                    "指标或列表刷新后，应保持筛选条件和展示口径一致。",
                    "口径变更需要同步影响说明、验收用例和对外展示文案。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                [
                    "数据加载中应展示加载状态。",
                    "无数据时展示空状态，并说明用户下一步可做什么。",
                    "数据获取失败时保留当前筛选条件并提供重试入口。",
                ]
            ),
        ),
        section(
            "数据链路",
            mermaid_block(
                [
                    "flowchart LR",
                    "  A[数据来源] --> B[权限过滤]",
                    "  B --> C[统计或查询口径]",
                    "  C --> D[页面展示]",
                    "  D --> E[刷新或下钻]",
                    "  C --> F[异常提示]",
                ]
            ),
        ),
        section("证据", bullet_list(evidence_items(candidate))) if evidence_items(candidate) else "",
        section(
            "待确认",
            bullet_list(
                [
                    "数据来源、刷新频率和统计口径是否已确认？",
                    "不同角色是否看到不同数据范围？",
                ]
            ),
        ),
    )


def generate_form_content(candidate: dict, product_context: dict | None) -> str:
    if is_status_filter_candidate(candidate):
        return generate_status_filter_content(candidate, product_context)
    if is_search_candidate(candidate):
        return generate_search_content(candidate, product_context)
    label = candidate_label(candidate, "字段")
    return join_lines(
        section("业务含义", f"「{label}」用于收集或筛选与当前业务相关的信息。"),
        section(
            "使用场景",
            "用户在填写、修改或筛选业务数据时需要使用该字段或表单区域。",
        ),
        section(
            "交互规则",
            bullet_list(
                [
                    "用户输入或选择后，系统应即时或提交时进行校验。",
                    "校验失败时，应明确提示需要修正的内容。",
                    "必填项未填写时，应阻止提交并高亮提示。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                [
                    "禁用状态：说明不可编辑原因。",
                    "校验失败：保留用户输入并提示修正方式。",
                    "选项为空：提示暂无可用选项或联系管理员。",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "字段默认值和选项来源是否已明确？",
                    "是否需要支持联动或级联筛选？",
                ]
            ),
        ),
    )


def generate_permission_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate, "操作")
    return join_lines(
        section("业务含义", f"「{label}」是风险或权限敏感操作，需要明确谁可以执行以及执行后的影响。"),
        section(
            "交互规则",
            bullet_list(
                [
                    "执行前应校验用户角色、业务状态和前置条件。",
                    "高风险操作建议增加二次确认。",
                    "执行后应给出明确成功或失败反馈。",
                ]
            ),
        ),
        section(
            "风险提示",
            "重点确认该操作是否不可逆、是否影响客户可见数据、是否需要原因填写或审批留痕。",
        ),
        section(
            "权限判断",
            mermaid_block(
                [
                    "flowchart TD",
                    "  A[用户触发操作] --> B{角色有权限}",
                    "  B -->|否| C[隐藏或置灰入口]",
                    "  B -->|是| D{状态允许}",
                    "  D -->|否| E[提示不可操作原因]",
                    "  D -->|是| F[允许执行]",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "是否需要确认弹窗、操作原因或审批记录？",
                    "是否支持撤销或回滚？",
                ]
            ),
        ),
    )


def generate_generic_product_content(candidate: dict, product_context: dict | None) -> str:
    label = candidate_label(candidate)
    reason = normalize(str(candidate.get("reason") or ""))
    biz = f"「{label}」是页面中与当前业务相关的重要区域。"
    if reason and "候选" not in reason and "元素" not in reason:
        biz = f"「{label}」{reason.rstrip('。')}。"
    return join_lines(
        section("业务含义", biz),
        section(
            "使用场景",
            "用户在完成当前页面任务时，会与此区域发生查看、输入或确认交互。",
        ),
        section(
            "交互规则",
            bullet_list(
                [
                    "用户操作后，系统应给出明确的界面反馈。",
                    "涉及提交或流转时，应先校验前置条件。",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "该区域的具体业务规则是否已与 PRD 对齐？",
                    "异常状态和权限差异是否需要补充说明？",
                ]
            ),
        ),
    )


def surface_name(candidate: dict) -> str:
    return compact(str(candidate.get("fallbackText") or candidate.get("title") or "二级界面"), 24)


def feedback_exception_lines(candidate: dict) -> list[str]:
    feedback = candidate.get("feedbackEvidence") if isinstance(candidate.get("feedbackEvidence"), list) else []
    lines: list[str] = []
    for item in feedback[:4]:
        text = normalize(str(item))
        if "成功" in text:
            lines.append("操作成功：展示成功提示，并刷新当前页面或列表。")
        elif "失败" in text:
            lines.append("操作失败：展示失败提示，保留用户当前输入或当前状态。")
        elif text:
            lines.append(f"操作完成后：{text.replace('短暂反馈：', '')}")
    return lines


def generate_surface_trigger_content(candidate: dict, product_context: dict | None = None) -> str:
    label = candidate_label(candidate)
    surface_label = surface_name(candidate)
    return join_lines(
        section("业务含义", f"该操作用于打开「{surface_label}」，帮助用户在不离开当前页面的情况下完成进一步处理。"),
        section(
            "打开规则",
            bullet_list(
                [
                    f"用户点击「{label}」后，系统打开对应的抽屉、弹窗或确认框。",
                    "二级界面打开后，用户应在其中完成信息查看、填写、确认或提交。",
                    "关闭后返回当前页面，当前页面状态应保持一致。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                feedback_exception_lines(candidate)
                + [
                    "打开失败时，应提示用户稍后重试。",
                    "如果用户在二级界面中填写了内容，关闭前应根据业务需要确认是否保存。",
                    "操作成功后，应刷新当前页面或更新相关数据状态。",
                ]
            ),
        ),
        section(
            "打开流程",
            mermaid_block(
                [
                    "flowchart LR",
                    "  A[点击入口] --> B[打开二级界面]",
                    "  B --> C[查看或填写信息]",
                    "  C --> D{保存或取消}",
                    "  D -->|保存| E[刷新主页面]",
                    "  D -->|取消| F[返回主页面]",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "关闭时未保存内容是否需要二次确认？",
                    "是否需要根据角色控制该入口是否可见？",
                ]
            ),
        ),
    )


def generate_surface_overview_content(candidate: dict, product_context: dict | None = None) -> str:
    surface_label = surface_name(candidate)
    return join_lines(
        section("业务含义", f"「{surface_label}」用于承载当前页面中的补充操作，避免用户离开主页面即可完成信息填写、确认或处理。"),
        section(
            "使用场景",
            bullet_list(
                [
                    "用户在主页面触发相关操作后进入该界面。",
                    "用于完成当前对象的新增、编辑、查看、授权、审批或确认。",
                ]
            ),
        ),
        section(
            "交互规则",
            bullet_list(
                [
                    "打开后，主页面保持背景可见，但当前操作焦点进入二级界面。",
                    "用户可以完成信息填写、确认或取消。",
                    "保存成功后关闭二级界面，并刷新主页面相关数据。",
                    "取消或关闭时，应根据是否存在未保存内容决定是否二次确认。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                [
                    "加载中：展示加载状态。",
                    "保存失败：保留用户已填写内容，并提示失败原因。",
                    "权限不足：不展示入口或提示无权限。",
                ]
            ),
        ),
        section(
            "交互流程",
            mermaid_block(
                [
                    "flowchart TD",
                    "  A[主页面触发] --> B[打开二级界面]",
                    "  B --> C[填写或确认内容]",
                    "  C --> D{用户操作}",
                    "  D -->|保存| E[校验并提交]",
                    "  D -->|取消| F[关闭并返回]",
                    "  E --> G[刷新主页面数据]",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "关闭未保存内容时是否需要二次确认？",
                    "保存成功后是否需要保留筛选条件？",
                ]
            ),
        ),
    )


def generate_surface_field_content(candidate: dict, product_context: dict | None = None) -> str:
    label = candidate_label(candidate)
    return join_lines(
        section("业务含义", f"「{label}」是当前二级界面中的业务字段，用于记录、筛选或确认与当前操作直接相关的信息。"),
        section(
            "填写规则",
            bullet_list(
                [
                    "优先以字段标签、分组标题和页面说明确定字段含义，placeholder 只能作为输入示例。",
                    "必填字段为空时，应在提交前提示用户补充；非必填字段应允许留空。",
                    "字段内容变更后，应只影响当前二级界面中的待保存内容，提交成功前不直接改动主页面数据。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                [
                    "校验失败时，应在字段附近展示错误提示。",
                    "保存失败时，应保留用户已填写内容。",
                    "关闭界面前，如果存在未保存内容，应根据业务需要提示用户确认。",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "字段是否必填？",
                    "默认值从哪里来？",
                ]
            ),
        ),
    )


def generate_surface_action_content(candidate: dict, product_context: dict | None = None) -> str:
    label = candidate_label(candidate)
    raw_label = label_text(candidate)
    if CLOSE_ACTION_RE.search(raw_label):
        return join_lines(
            section("业务含义", f"「{label}」用于关闭当前二级界面并返回主页面，不提交或保存当前内容。"),
            section(
                "交互规则",
                bullet_list(
                    [
                        "用户点击后关闭当前抽屉、弹窗或确认框。",
                        "关闭后主页面保持原有数据和筛选状态。",
                        "如果界面内存在未保存内容，是否提示确认应由业务规则决定。",
                    ]
                ),
            ),
            section(
                "状态与异常",
                bullet_list(
                    [
                        "关闭成功：二级界面消失，焦点回到触发入口或主页面。",
                        "存在未保存内容：可提示用户确认放弃修改。",
                    ]
                ),
            ),
            section(
                "待确认",
                bullet_list(
                    [
                        "关闭未保存内容时是否需要二次确认？",
                        "关闭后焦点是否需要回到打开入口？",
                    ]
                ),
            ),
        )
    if SAVE_ACTION_RE.search(raw_label):
        return join_lines(
            section("业务含义", f"「{label}」用于提交当前二级界面中的有效内容，并在成功后同步主页面状态。"),
            section(
                "交互规则",
                bullet_list(
                    [
                        "用户点击后，系统校验当前界面的必填字段、格式和业务前置条件。",
                        "校验通过后执行对应的保存、提交、确认或发布动作。",
                        "校验失败时停留在当前界面，并在对应字段或区域提示原因。",
                    ]
                ),
            ),
            section(
                "状态与异常",
                bullet_list(
                    feedback_exception_lines(candidate)
                    + [
                        "处理中：按钮进入 loading 或禁用状态，避免重复触发。",
                        "操作成功：关闭二级界面，并刷新主页面相关数据。",
                        "操作失败：保留当前输入，并提示用户如何处理。",
                    ]
                ),
            ),
            section(
                "提交流程",
                mermaid_block(
                    [
                        "flowchart TD",
                        "  A[点击操作按钮] --> B[校验二级界面内容]",
                        "  B --> C{校验通过}",
                        "  C -->|否| D[提示错误并停留]",
                        "  C -->|是| E[执行对应业务动作]",
                        "  E --> F[关闭界面并刷新]",
                    ]
                ),
            ),
            section(
                "待确认",
                bullet_list(
                    [
                        "是否需要二次确认？",
                        "成功后刷新哪些主页面区域？",
                    ]
                ),
            ),
        )
    return join_lines(
        section("业务含义", f"「{label}」是当前二级界面中的操作按钮，用于推进该界面的业务处理。"),
        section(
            "交互规则",
            bullet_list(
                [
                    "用户点击后，系统应按按钮语义执行对应操作。",
                    "如涉及数据变更，应先校验必要字段和业务状态。",
                    "如仅用于返回或切换，应保持主页面数据不被意外修改。",
                ]
            ),
        ),
        section(
            "状态与异常",
            bullet_list(
                feedback_exception_lines(candidate)
                + [
                    "操作处理中：按钮可进入 loading 或禁用状态，避免重复触发。",
                    "操作成功：根据按钮语义关闭界面、更新局部状态或保留当前界面。",
                    "操作失败：保留当前输入，并提示用户如何处理。",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "是否需要二次确认？",
                    "成功后是否关闭二级界面？",
                ]
            ),
        ),
    )


def generate_surface_confirm_content(candidate: dict, product_context: dict | None = None) -> str:
    label = candidate_label(candidate)
    return join_lines(
        section("业务含义", "确认弹窗用于在用户执行高风险操作前进行二次确认，避免误操作造成数据或业务状态异常。"),
        section(
            "确认规则",
            bullet_list(
                [
                    f"用户触发「{label}」相关操作后，不应立即执行。",
                    "系统应展示确认弹窗，说明操作对象和影响范围。",
                    "用户确认后才执行操作；用户取消后返回原页面，不改变数据状态。",
                ]
            ),
        ),
        section(
            "风险控制",
            bullet_list(
                [
                    "删除、停用、取消授权、重置密钥等操作建议记录操作日志。",
                    "不可逆操作需要明确提示影响范围。",
                    "权限不足时，不展示操作入口或禁止确认。",
                ]
            ),
        ),
        section(
            "确认流程",
            mermaid_block(
                [
                    "flowchart TD",
                    "  A[触发风险操作] --> B[展示确认弹窗]",
                    "  B --> C{用户选择}",
                    "  C -->|取消| D[不改变数据]",
                    "  C -->|确认| E[校验权限]",
                    "  E --> F[执行并反馈结果]",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "该操作是否可撤销？",
                    "是否需要管理员权限？",
                ]
            ),
        ),
    )


def generate_product_review_content(candidate: dict, product_context: dict | None = None) -> str:
    dimension = str(candidate.get("dimension") or "")
    annotation_type = str(candidate.get("annotationType") or "")

    if candidate.get("surfaceId") and dimension == "Surface trigger":
        return generate_surface_trigger_content(candidate, product_context)
    if candidate.get("surfaceId") and dimension == "Surface overview":
        return generate_surface_overview_content(candidate, product_context)
    if candidate.get("surfaceId") and dimension == "Surface field":
        return generate_surface_field_content(candidate, product_context)
    if candidate.get("surfaceId") and dimension == "Surface action":
        return generate_surface_action_content(candidate, product_context)
    if dimension == "Surface confirm":
        return generate_surface_confirm_content(candidate, product_context)

    if dimension == "Page overview" or annotation_type == "P":
        return generate_page_overview_product(candidate, product_context)
    if is_status_filter_candidate(candidate):
        return generate_status_filter_content(candidate, product_context)
    if is_search_candidate(candidate):
        return generate_search_content(candidate, product_context)
    if annotation_type == "FALLBACK":
        return generate_fallback_content(candidate, product_context)
    if annotation_type == "HITL":
        return generate_hitl_content(candidate, product_context)
    if annotation_type == "PROMPT":
        return generate_prompt_content(candidate, product_context)
    if annotation_type == "CTX":
        return generate_context_content(candidate, product_context)
    if dimension == "Table row actions":
        return generate_row_action_group_content(candidate, product_context)
    if dimension == "AI and automation" or annotation_type == "AI":
        return generate_ai_content(candidate, product_context)
    if dimension == "Data explanation" or annotation_type in {"DATA", "METRIC", "SOURCE"}:
        return generate_data_content(candidate, product_context)
    if dimension == "Primary action" or annotation_type == "A":
        return generate_action_content(candidate, product_context)
    if dimension == "Flow and navigation" or annotation_type == "J":
        return generate_navigation_content(candidate, product_context)
    if dimension == "State and exception" or annotation_type == "S":
        return generate_state_content(candidate, product_context)
    if dimension == "Permission and risk" or annotation_type in {"R", "PERM"}:
        return generate_permission_content(candidate, product_context)
    if dimension == "Table and list":
        return generate_table_content(candidate, product_context)
    if dimension == "Form and validation":
        return generate_form_content(candidate, product_context)
    if annotation_type == "C":
        return generate_component_content(candidate, product_context)
    return generate_generic_product_content(candidate, product_context)


def generate_dev_handoff_content(candidate: dict, product_context: dict | None = None) -> str:
    product_body = generate_product_review_content(candidate, product_context)
    evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), list) else []
    dev_lines = [
        section(
            "研发说明",
            bullet_list(
                [
                    f"元素定位：{candidate.get('selector') or '待补充稳定锚点'}",
                    f"页面：{candidate.get('pageRoute') or candidate.get('pagePath') or candidate.get('pageKey') or ''}",
                    f"元素 ID：{candidate.get('elementId') or candidate.get('sourceElementId') or ''}",
                ]
            ),
        ),
    ]
    if evidence:
        dev_lines.append(section("技术证据", bullet_list([normalize(str(item)) for item in evidence[:6]])))
    return product_body + "\n".join(dev_lines)


def generate_qa_acceptance_content(candidate: dict, product_context: dict | None = None) -> str:
    label = candidate_label(candidate)
    return join_lines(
        section("前置条件", "用户已进入相关页面，且具备执行该操作所需的角色权限与业务数据。"),
        section(
            "操作步骤",
            bullet_list(
                [
                    f"定位到「{label}」对应区域。",
                    "按产品规则完成用户操作。",
                    "观察系统反馈与页面状态变化。",
                ]
            ),
        ),
        section(
            "预期结果",
            bullet_list(
                [
                    "操作成功后，界面展示与 PRD 一致的结果。",
                    "相关列表、状态或下游页面同步更新。",
                ]
            ),
        ),
        section(
            "异常路径",
            bullet_list(
                [
                    "前置条件不满足时，应阻断操作并提示原因。",
                    "接口失败时，应保留用户输入并支持重试。",
                ]
            ),
        ),
        section(
            "验收标准",
            bullet_list(
                [
                    "主路径、失败路径和空状态均有明确反馈。",
                    "权限不足、重复提交和异常恢复行为可复现且符合规则。",
                ]
            ),
        ),
    )


def generate_customer_demo_content(candidate: dict, product_context: dict | None = None) -> str:
    label = candidate_label(candidate)
    page = page_context(candidate, product_context)
    pname = product_name(product_context)
    purpose = normalize(str(page.get("purpose") or f"提升用户在「{label}」相关场景下的操作效率。"))
    return join_lines(
        section("页面价值", purpose if page else f"「{label}」帮助用户更高效地完成关键业务步骤。"),
        section(
            "用户收益",
            bullet_list(
                [
                    "减少重复手工操作，缩短业务处理时间。",
                    "降低理解成本，让用户快速知道下一步该做什么。",
                ]
            ),
        ),
        section(
            "功能亮点",
            bullet_list(
                [
                    f"围绕「{label}」提供清晰、可理解的业务操作体验。",
                    "关键状态、结果反馈和异常提示对用户友好。",
                ]
            ),
        ),
        section(
            "演示说明",
            f"演示时可重点说明「{label}」如何支撑{pname or '当前产品'}的核心业务流程，以及它带来的效率提升。",
        ),
    )


def generate_fallback_content(candidate: dict, product_context: dict | None = None) -> str:
    return join_lines(
        section(
            "业务含义",
            "失败兜底用于保证 AI 能力不可用、生成失败或结果不准确时，用户仍然可以继续完成业务流程。",
        ),
        section(
            "触发场景",
            bullet_list(
                [
                    "AI 处理失败。",
                    "AI 返回结果为空。",
                    "AI 结果明显不准确。",
                    "网络异常或服务不可用。",
                ]
            ),
        ),
        section(
            "兜底规则",
            bullet_list(
                [
                    "支持用户重新生成或重新识别。",
                    "支持用户手动填写或修改结果。",
                    "保留用户已输入内容，避免重复录入。",
                    "必要时提示用户转人工处理。",
                ]
            ),
        ),
        section(
            "兜底流程",
            mermaid_block(
                [
                    "flowchart TD",
                    "  A[AI处理失败] --> B[提示失败原因]",
                    "  B --> C{用户选择}",
                    "  C -->|重试| D[重新生成]",
                    "  C -->|手动处理| E[人工填写或修改]",
                    "  D --> F[再次确认结果]",
                    "  E --> F",
                ]
            ),
        ),
        section(
            "待确认",
            bullet_list(
                [
                    "是否需要记录 AI 失败原因？",
                    "是否需要展示重试次数限制？",
                    "是否需要进入人工审核流程？",
                ]
            ),
        ),
    )


def generate_dev_notes(candidate: dict, audience_mode: str) -> str:
    if audience_mode != "dev-handoff":
        return ""
    evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), list) else []
    lines = [
        f"- selector：`{candidate.get('selector') or ''}`",
        f"- sourceElementId：`{candidate.get('elementId') or candidate.get('sourceElementId') or ''}`",
        f"- pageRoute：`{candidate.get('pageRoute') or candidate.get('pagePath') or ''}`",
    ]
    for item in evidence[:5]:
        text = normalize(str(item))
        if text:
            lines.append(f"- {text}")
    return "### 研发说明\n\n" + "\n".join(lines) + "\n"


def generate_annotation_content(
    candidate: dict,
    product_context: dict | None = None,
    audience_mode: str = DEFAULT_AUDIENCE_MODE,
) -> str:
    mode = audience_mode if audience_mode in VALID_AUDIENCE_MODES else DEFAULT_AUDIENCE_MODE
    if mode == "product-review":
        return generate_product_review_content(candidate, product_context)
    if mode == "dev-handoff":
        return generate_dev_handoff_content(candidate, product_context)
    if mode == "qa-acceptance":
        return generate_qa_acceptance_content(candidate, product_context)
    if mode == "customer-demo":
        return generate_customer_demo_content(candidate, product_context)
    return generate_product_review_content(candidate, product_context)


def annotation_review_reason(audience_mode: str) -> str:
    if audience_mode == "dev-handoff":
        return "dev-handoff-draft"
    return "product-copy-draft"
