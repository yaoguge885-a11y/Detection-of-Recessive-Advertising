from __future__ import annotations

import pytest

from impad.orchestration import LocalToolGateway
from impad.services import AnalysisService, JsonRunStore
from impad.tools.contracts import ToolEvidence, ToolResult


QUOTE = "感谢本期幕后伙伴一路支持"
POST = {
    "text": f"这是今天的分享。{QUOTE}。欢迎阅读。",
    "capture_complete": True,
}


class AmbiguousTextGateway(LocalToolGateway):
    def call(self, name, arguments, run):
        result = super().call(name, arguments, run)
        if name != "analyze_text_intent":
            return result
        start = arguments["text"].index(QUOTE)
        return result.model_copy(update={"evidence": [ToolEvidence(
            kind="disclosure_candidate", source="post.text", quote=QUOTE,
            span=(start, start + len(QUOTE)),
        )]})


class EmptyRetriever:
    def retrieve(self, query, top_k=5):
        return []


class OcrDisclosureGateway(LocalToolGateway):
    def call(self, name, arguments, run):
        if name == "ocr_extract":
            quote = "本内容由品牌方赞助"
            bbox = [12, 24, 220, 52]
            return ToolResult(
                tool_name=name,
                tool_version="test-ocr-v1",
                status="ok",
                score=0.99,
                evidence=[ToolEvidence(
                    kind="ocr_text",
                    source="image.ocr",
                    quote=quote,
                    score=0.99,
                    bbox=bbox,
                )],
                payload={
                    "vision_context": {
                        "image_name": "sponsored.jpg",
                        "model_version": "test-ocr-v1",
                        "capabilities": {"ocr": True},
                        "texts": [{
                            "text": quote,
                            "confidence": 0.99,
                            "bbox": bbox,
                        }],
                    },
                },
                call_id=run.call_id,
                run_id=run.run_id,
            )
        return super().call(name, arguments, run)


@pytest.mark.parametrize(("answer", "label", "tool_status"), [
    ({"status": "confirmed", "index": 0}, "明广", "ok"),
    ({"status": "rejected"}, "非广", "ok"),
    ({"status": "uncertain"}, "需复核", "ok"),
    ({"status": "confirmed", "index": 100}, "需复核", "error"),
    (None, "需复核", None),
])
def test_disclosure_verification_in_service(tmp_path, answer, label, tool_status):
    calls = []

    def verify(quotes):
        calls.append(quotes)
        return answer

    service = AnalysisService(
        retriever=EmptyRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
        local_gateway=AmbiguousTextGateway(),
        disclosure_verifier=verify if answer is not None else None,
    )
    result = service.analyze(POST)
    assert result.verdict_report.label == label
    checked = [tool for tool in result.evidence_bundle.tool_results if tool.tool_name == "verify_disclosure"]
    assert calls == ([[QUOTE]] if tool_status else [])
    assert [tool.status for tool in checked] == ([tool_status] if tool_status else [])
    if label == "明广":
        marker, = [item for item in result.evidence_bundle.items if item.kind == "explicit_ad_marker"]
        assert (marker.quote, POST["text"][slice(*marker.span)]) == (QUOTE, QUOTE)
        assert result.verdict_report.disclosure.evidence_ids == [marker.evidence_id]


@pytest.mark.parametrize(("text", "label"), [
    ("今天和同学合作完成了课程作业。", "非广"),
    ("这瓶是我自费买的，没有品牌合作。", "非广"),
    ("本篇为品牌付费合作。", "明广"),
])
def test_cooperation_in_context(tmp_path, text, label):
    service = AnalysisService(
        retriever=EmptyRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )
    result = service.analyze({"text": text, "capture_complete": True})
    assert result.verdict_report.label == label


def test_service_uses_ocr_disclosure_when_post_text_is_ordinary(tmp_path):
    image = tmp_path / "sponsored.jpg"
    image.write_bytes(b"fixture")
    quote = "本内容由品牌方赞助"
    bbox = [12, 24, 220, 52]

    service = AnalysisService(
        retriever=EmptyRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
        local_gateway=OcrDisclosureGateway(),
    )
    result = service.analyze({
        "text": "今天记录一下使用感受。",
        "image_path": str(image),
        "capture_complete": True,
    })

    assert result.verdict_report.label == "明广"
    ocr_item, = [
        item for item in result.evidence_bundle.items
        if item.kind == "ocr_text"
    ]
    assert (ocr_item.quote, ocr_item.bbox) == (quote, bbox)
    marker, = [
        item for item in result.evidence_bundle.items
        if item.kind == "explicit_ad_marker"
    ]
    assert (marker.quote, marker.bbox) == (quote, bbox)
