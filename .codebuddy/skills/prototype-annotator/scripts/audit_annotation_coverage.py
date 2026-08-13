#!/usr/bin/env python3
"""Audit annotation coverage gaps for dev-handoff delivery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dev_handoff import audit_summary, candidates_file_for, is_dev_handoff_mode, load_json, validate_dev_handoff


def annotation_file_for(target: Path) -> Path:
    root = target.parent if target.is_file() else target
    preferred = root / "prototype-annotator" / "annotations.json"
    if preferred.exists():
        return preferred
    legacy = root / ".prototype-annotations" / "annotations.json"
    return legacy if legacy.exists() else preferred


def render_markdown(summary: dict, error_count: int) -> str:
    lines = [
        "# 研发交付覆盖审计",
        "",
        f"- 标注模式：`{summary.get('annotationMode')}`",
        f"- 校验结果：{'通过' if error_count == 0 else f'未通过（{error_count} 项错误）'}",
        "",
        "## 页面覆盖",
        "",
        "| 页面 | 路由 | 标注数 | 候选数 | 最低要求 | 仅页面介绍 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in summary.get("pages", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("pageKey") or ""),
                    str(row.get("route") or ""),
                    str(row.get("annotationCount") or 0),
                    str(row.get("selectedCandidateCount") or 0),
                    str(row.get("minRequired") or 0),
                    "是" if row.get("onlyOverview") else "否",
                ]
            )
            + " |"
        )

    lines.extend(["", "## 未转正候选", ""])
    unpromoted = summary.get("unpromotedCandidates") or []
    if unpromoted:
        for item in unpromoted:
            lines.append(
                f"- `{item.get('pageKey')}` / `{item.get('candidateId')}` / "
                f"{item.get('label')} ({item.get('dimension')})"
            )
    else:
        lines.append("- 无")

    def bullet_section(title: str, values: list[str]) -> None:
        lines.extend(["", f"## {title}", ""])
        if values:
            lines.extend(f"- `{value}`" for value in values)
        else:
            lines.append("- 无")

    bullet_section("仅页面介绍页面", summary.get("onlyOverviewPages") or [])
    bullet_section("粗粒度锚点", summary.get("coarseAnchorIds") or [])
    bullet_section("占位正文", summary.get("placeholderIds") or [])
    bullet_section("review.required 绕过", summary.get("reviewBypassIds") or [])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit dev-handoff annotation coverage.")
    parser.add_argument("prototype_path", help="HTML file or static directory")
    parser.add_argument("--annotations", help="Path to annotations.json")
    parser.add_argument("--candidates", help="Path to annotation-candidates.json")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary")
    parser.add_argument("--output", help="Write Markdown audit report to this path")
    args = parser.parse_args()

    target = Path(args.prototype_path).resolve()
    if not target.exists():
        parser.error(f"Path does not exist: {target}")

    annotation_path = Path(args.annotations).resolve() if args.annotations else annotation_file_for(target)
    candidates_path = Path(args.candidates).resolve() if args.candidates else candidates_file_for(target)
    if not annotation_path.exists():
        parser.error(f"Annotation file does not exist: {annotation_path}")
    if not candidates_path.exists():
        parser.error(f"Candidates file does not exist: {candidates_path}")

    data = load_json(annotation_path)
    candidates = load_json(candidates_path)
    summary = audit_summary(data, candidates)
    error_count, errors, warnings = validate_dev_handoff(data, candidates=candidates, as_errors=True)
    summary["errors"] = errors
    summary["warnings"] = warnings
    summary["errorCount"] = error_count

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        report = render_markdown(summary, error_count)
        if args.output:
            output = Path(args.output).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(report, encoding="utf-8")
            print(f"Wrote audit report: {output}")
        else:
            print(report)
        for message in errors:
            print(message)
        for message in warnings:
            print(message)

    if error_count:
        print(f"Audit failed with {error_count} error(s).")
        return 1
    print("Audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
