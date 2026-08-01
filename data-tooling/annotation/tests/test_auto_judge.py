"""分置信度自动判断系统核心模块单元测试（co-pilot-auto-judge-design v1.0）。

运行：
  python -m pytest data-tooling/annotation/tests/test_auto_judge.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 让 pytest 能 import 同级的 auto_judge 模块
ANNOTATION_DIR = Path(__file__).resolve().parent.parent
if str(ANNOTATION_DIR) not in sys.path:
    sys.path.insert(0, str(ANNOTATION_DIR))

from auto_judge import (  # noqa: E402
    DEFAULT_AUTO_THRESHOLD,
    SUGGESTION_LOWER_BOUND,
    build_auto_record,
    build_user_prompt,
    classify_confidence,
    compute_keyword_weights_for_post,
    has_explicit_ad_marker,
    keyword_fallback,
    normalize_label,
    normalize_suggestion,
    run_auto_judge,
    summarize_image_analyses,
    summarize_keyword_weights,
)


# ── 测试帖子 ──
AD_POST = {
    "post_id": "post_ad", "title": "感谢品牌方", "platform": "wechat_official_account",
    "text": "#广告 感谢品牌方赞助。这款产品真的很好用，限时优惠价只要99元，点击下方链接立即下单！",
}
LIFE_POST = {
    "post_id": "post_life", "title": "周末爬山", "platform": "wechat_official_account",
    "text": "今天周末和朋友们去爬山，天气很好，心情舒畅。记录一下这个愉快的周末。",
}
SOFT_POST = {
    "post_id": "post_soft", "title": "护肤心得", "platform": "wechat_official_account",
    "text": "分享我的护肤心得，这款面霜自费买的，用了三个月真的很好用，价格实惠，强烈推荐，链接在评论区",
}
HIGH_PRESSURE_POST = {
    "post_id": "post_high", "title": "好物分享", "platform": "wechat_official_account",
    "text": "限时优惠！这款产品无限回购闭眼入，强烈推荐大家种草，赶紧点击链接立即下单，价格超值，扫码领取优惠券！",
}


# ════════════════════════════════════════════════════════════════════
# 三级置信度分类（设计文档 §3）
# ════════════════════════════════════════════════════════════════════
class TestClassifyConfidence:
    def test_high_confidence_auto(self):
        assert classify_confidence(0.90, 0.85) == "auto"

    def test_boundary_auto(self):
        assert classify_confidence(0.85, 0.85) == "auto"

    def test_mid_confidence_suggest(self):
        assert classify_confidence(0.70, 0.85) == "suggest"

    def test_lower_bound_suggest(self):
        assert classify_confidence(0.55, 0.85) == "suggest"

    def test_low_confidence_manual(self):
        assert classify_confidence(0.40, 0.85) == "manual"

    def test_custom_threshold(self):
        assert classify_confidence(0.80, 0.75) == "auto"
        assert classify_confidence(0.74, 0.75) == "suggest"


# ════════════════════════════════════════════════════════════════════
# 标签归一化
# ════════════════════════════════════════════════════════════════════
class TestNormalizeLabel:
    def test_chinese_labels_kept(self):
        for label in ("明广", "暗广", "非广", "out_of_scope"):
            assert normalize_label(label) == label

    def test_code_to_chinese(self):
        assert normalize_label("mingguang") == "明广"
        assert normalize_label("anguang") == "暗广"
        assert normalize_label("feiguang") == "非广"

    def test_invalid_falls_back(self):
        assert normalize_label("不确定") == "非广"
        assert normalize_label("") == "非广"
        assert normalize_label(None) == "非广"


# ════════════════════════════════════════════════════════════════════
# 关键词特征（设计文档 §4.3 / §6.1）
# ════════════════════════════════════════════════════════════════════
class TestKeywordWeights:
    def test_compute_weights_shape(self):
        w = compute_keyword_weights_for_post(SOFT_POST["text"])
        assert set(w.keys()) == {
            "promotion_words", "price_mentions", "urgency_expressions",
            "brand_mentions", "action_words", "natural_expression",
        }
        for v in w.values():
            assert 0.0 <= v <= 1.0

    def test_explicit_marker_detected(self):
        assert has_explicit_ad_marker(AD_POST["text"]) is True
        assert has_explicit_ad_marker(LIFE_POST["text"]) is False

    def test_summarize_weights(self):
        w = compute_keyword_weights_for_post(SOFT_POST["text"])
        s = summarize_keyword_weights(w)
        assert "促销种草" in s
        assert "行动召唤" in s


# ════════════════════════════════════════════════════════════════════
# 关键词回退（设计文档 §4.4）
# ════════════════════════════════════════════════════════════════════
class TestKeywordFallback:
    def test_explicit_marker_returns_mingguang_090(self):
        fb = keyword_fallback(AD_POST)
        assert fb is not None
        assert fb["label"] == "明广"
        assert fb["confidence"] == 0.90
        assert fb["confidence"] >= DEFAULT_AUTO_THRESHOLD  # 可自动保存
        assert "D" in fb["evidence_codes"]

    def test_high_pressure_no_marker_returns_anguang_045(self):
        fb = keyword_fallback(HIGH_PRESSURE_POST)
        assert fb is not None
        assert fb["label"] == "暗广"
        assert fb["confidence"] == 0.45
        assert fb["confidence"] < SUGGESTION_LOWER_BOUND  # 强制人工

    def test_low_pressure_returns_none(self):
        assert keyword_fallback(LIFE_POST) is None  # 不做建议，纯人工


# ════════════════════════════════════════════════════════════════════
# 自动保存记录（设计文档 §5.1 / §5.2）
# ════════════════════════════════════════════════════════════════════
class TestBuildAutoRecord:
    def test_auto_record_structure(self):
        suggestion = normalize_suggestion({
            "label": "暗广", "confidence": 0.92,
            "evidence_codes": ["V", "P"],
            "evidence": ["图片2中品牌Logo特写", "文案含回购话术"],
            "reasoning": "无广告标识但品牌为核心，判定暗广",
            "uncertain_reason": None,
            "information_gaps": [],
        })
        record = build_auto_record(SOFT_POST, suggestion, model="qwen3.5:9b", auto_accepted=True)

        assert record["post_id"] == "post_soft"
        assert record["annotator_id"] == "system"
        assert record["annotation_method"] == "auto_accepted"
        assert record["label"] == "暗广"
        assert record["confidence"] == 0.92
        assert "annotated_at" in record

        llm = record["_llm_suggestion"]
        assert llm["model"] == "qwen3.5:9b"
        assert llm["auto_accepted"] is True
        assert llm["label"] == "暗广"
        assert set(llm["evidence_codes"]) == {"V", "P"}

    def test_manual_flag_record(self):
        suggestion = normalize_suggestion({"label": "非广", "confidence": 0.7})
        record = build_auto_record(LIFE_POST, suggestion, auto_accepted=False)
        assert record["annotation_method"] == "human"
        assert record["_llm_suggestion"]["auto_accepted"] is False


# ════════════════════════════════════════════════════════════════════
# 提示词构建（设计文档 §4.3）
# ════════════════════════════════════════════════════════════════════
class TestPromptBuilding:
    def test_user_prompt_contains_sections(self):
        w = compute_keyword_weights_for_post(LIFE_POST["text"])
        prompt = build_user_prompt(LIFE_POST, "无图片分析结果", w)
        assert "## 帖子信息" in prompt
        assert "## 帖子正文" in prompt
        assert "## 图片分析结果" in prompt
        assert "## 关键词特征向量" in prompt
        assert "周末爬山" in prompt

    def test_image_summary(self):
        analyses = {
            0: {"detected_elements": {"has_logo": True}, "visual_evidence_codes": ["V"],
                "description": "品牌Logo特写", "analysis_method": "yolo_ocr_auto"},
            1: {"error": "file missing"},
        }
        s = summarize_image_analyses(analyses)
        assert "图片1" in s
        assert "V" in s
        assert "图片2" in s and "失败" in s
        assert summarize_image_analyses(None) == "无图片分析结果"


# ════════════════════════════════════════════════════════════════════
# 完整管线（mock 掉 Ollama，验证回退与分级）
# ════════════════════════════════════════════════════════════════════
class TestRunAutoJudge:
    def test_ollama_failure_falls_back(self, monkeypatch):
        def fake_judge(*a, **k):
            raise RuntimeError("model not found")
        monkeypatch.setattr("auto_judge.run_ollama_judge", fake_judge)

        # 明广帖：回退 → 自动保存
        result = run_auto_judge(AD_POST, auto_threshold=0.85)
        assert result["fallback"] is True
        assert result["tier"] == "auto"
        assert result["record"] is not None
        assert result["record"]["annotation_method"] == "auto_accepted"
        assert result["record"]["label"] == "明广"

        # 生活帖：回退 → 无建议，纯人工
        result = run_auto_judge(LIFE_POST, auto_threshold=0.85)
        assert result["fallback"] is True
        assert result["tier"] == "manual"
        assert result["suggestion"] is None

    def test_ollama_suggestion_tiers(self, monkeypatch):
        def fake_judge_high(*a, **k):
            return normalize_suggestion({"label": "暗广", "confidence": 0.92})
        monkeypatch.setattr("auto_judge.run_ollama_judge", fake_judge_high)
        result = run_auto_judge(SOFT_POST, auto_threshold=0.85)
        assert result["fallback"] is False
        assert result["tier"] == "auto"
        assert result["record"]["label"] == "暗广"

        def fake_judge_mid(*a, **k):
            return normalize_suggestion({"label": "暗广", "confidence": 0.70})
        monkeypatch.setattr("auto_judge.run_ollama_judge", fake_judge_mid)
        result = run_auto_judge(SOFT_POST, auto_threshold=0.85)
        assert result["tier"] == "suggest"
        assert result["record"] is None  # 中置信度不自动保存

        def fake_judge_low(*a, **k):
            return normalize_suggestion({"label": "非广", "confidence": 0.40})
        monkeypatch.setattr("auto_judge.run_ollama_judge", fake_judge_low)
        result = run_auto_judge(SOFT_POST, auto_threshold=0.85)
        assert result["tier"] == "manual"
        assert result["suggestion"] is not None  # 有建议但低于展示下限


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
