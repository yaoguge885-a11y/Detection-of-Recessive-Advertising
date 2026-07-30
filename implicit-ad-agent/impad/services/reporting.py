"""Readable P3 report rendering from authoritative structured contracts."""
from __future__ import annotations

from ..contracts import EvidenceBundle, PostRecord, RunMetadata, VerdictReport


def legal_query(post: PostRecord, report: VerdictReport) -> str:
    """Build a post-judgment retrieval query without feeding law into Judge."""

    health_terms = ("医疗", "药品", "保健", "养生", "减肥", "功效")
    if any(term in post.text for term in health_terms):
        return "健康 养生 知识 变相广告 医疗 药品 保健食品 购物链接"
    if report.commercial_intent.status == "absent":
        return "商业广告活动 定义 直接或者间接 推销商品或者服务"
    return "体验分享 消费测评 推销商品 购物链接 广告可识别性 显著标明广告"


def render_readable_report(
    post: PostRecord,
    bundle: EvidenceBundle,
    report: VerdictReport,
    metadata: RunMetadata,
) -> str:
    lines = [
        f"# 帖子 {post.post_id} 分析报告",
        "",
        f"- 结论：{report.label}",
        f"- 置信度：{report.confidence:.3f}",
        f"- 商业意图：{report.commercial_intent.status}",
        f"- 披露状态：{report.disclosure.status}",
        f"- 是否需复核：{'是' if report.review_required else '否'}",
    ]
    summary = report.creator_shift
    lines.extend([
        "",
        "## CreatorShift",
        "",
    ])
    if summary is None:
        lines.append("- 状态：unavailable")
        lines.append("- 限制：CreatorShift未运行。")
    else:
        lines.extend([
            f"- 状态：{summary.status}",
            f"- 历史数量：{summary.history_count}/{summary.required_history}",
        ])
        if summary.shift_score is not None:
            lines.extend([
                f"- Shift分数：{summary.shift_score:.3f}",
                f"- 池化方法：{summary.pooling_method}",
                "- 主要变化维度："
                + (", ".join(summary.top_features[:3]) or "无"),
            ])
        if summary.limitations:
            lines.extend(
                f"- 限制：{item}" for item in summary.limitations
            )
    lines.extend([
        "",
        "## 判定依据",
        "",
        *[f"- `{reason}`" for reason in report.reasons],
        "",
        "## 证据链",
        "",
    ])
    if bundle.items:
        lines.extend(
            f"- [{item.tool_name}] {item.kind}："
            f"{item.quote or item.source_ref}"
            for item in bundle.items
        )
    else:
        lines.append("- 无可用正向证据。")
    lines.extend(["", "## 缺失与限制", ""])
    missing = [
        *bundle.missing_requirements,
        *report.disclosure.limitations,
        *(item.message for item in bundle.limitations),
    ]
    lines.extend(
        [f"- {item}" for item in dict.fromkeys(missing)]
        or ["- 无已记录的关键缺失。"]
    )
    lines.extend(["", "## 法规引用", ""])
    if report.law_evidence:
        for item in report.law_evidence:
            article = f" {item.article_id}" if item.article_id else ""
            lines.extend([
                f"- [{item.document_title}{article}]"
                f"({item.source_path_or_url})",
                f"  - 原文：{item.quote}",
                f"  - 版本：{item.document_version or '未记录'}；"
                f"检索分数：{item.retrieval_score or 0:.3f}",
            ])
    else:
        lines.append("- 检索器拒答：未返回达到阈值且可由语料核验的条款。")
    lines.extend([
        "",
        "## 运行信息",
        "",
        f"- run_id：`{metadata.run_id}`",
        f"- 状态：{metadata.status}",
        f"- 运行模式：{metadata.runtime_mode}",
        f"- 耗时：{metadata.duration_ms or 0} ms",
        f"- MCP 本地回落次数：{metadata.fallback_count}",
        f"- Judge：{report.judgment_method}",
    ])
    return "\n".join(lines)
