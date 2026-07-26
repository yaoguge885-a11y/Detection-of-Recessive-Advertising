"""Evidence-only Judge for the P2.5 deterministic baseline."""
from __future__ import annotations

from datetime import datetime, timezone

from ..orchestration import build_evidence_bundle, build_verdict_report
from ..state import AdCheckState


def _report_text(report, bundle) -> str:
    lines = [
        f"判定：{report.label}（置信度 {report.confidence:.2f}）",
        "判定依据：",
        *(f"  - {reason}" for reason in report.reasons),
        "证据链：",
    ]
    for item in bundle.items:
        pointer = item.quote or item.source_ref
        lines.append(f"  - [{item.tool_name}] {item.kind}: {pointer}")
    if not bundle.items:
        lines.append("  - 无可用证据")
    return "\n".join(lines)


def judge(state: AdCheckState) -> AdCheckState:
    post = state["post_record"]
    bundle = build_evidence_bundle(
        post,
        list(state.get("tool_results", [])),
    )
    report = build_verdict_report(post, bundle)
    finished_at = datetime.now(timezone.utc)
    metadata = state["run_metadata"]
    duration_ms = max(
        0,
        round((finished_at - metadata.started_at).total_seconds() * 1000),
    )
    has_error = any(
        result.status == "error" for result in bundle.tool_results
    )
    metadata = metadata.model_copy(update={
        "status": "degraded" if has_error else "completed",
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "tool_versions": {
            result.tool_name: result.tool_version
            for result in bundle.tool_results
        },
    })
    evidence = [
        f"[{item.tool_name}] {item.kind}: "
        f"{item.quote or item.source_ref}"
        for item in bundle.items
    ]
    return {
        "evidence_bundle": bundle,
        "verdict_report": report,
        "run_metadata": metadata,
        "verdict": report.label,
        "confidence": report.confidence,
        "evidence": evidence,
        "report": _report_text(report, bundle),
    }
