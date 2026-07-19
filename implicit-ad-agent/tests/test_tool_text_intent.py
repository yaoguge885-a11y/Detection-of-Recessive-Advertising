import json
import pytest

from impad.tools.text_intent import TextIntentInput, _analyze_text_intent_core, analyze_text_intent


def test_intent_returns_spans_and_pressure():
    result = _analyze_text_intent_core(TextIntentInput(text="限时抢购，扫码下单，闭眼入"))
    assert result.status == "degraded"
    assert 0.5 <= result.score <= 1
    assert any(item.span for item in result.evidence)
    json.dumps(result.model_dump(mode="json"), ensure_ascii=False)


def test_intent_natural_text_is_low():
    result = _analyze_text_intent_core(TextIntentInput(text="今天和朋友去图书馆学习，记录生活"))
    assert result.score < 0.5
    assert result.payload["commercial_intent_score"] == result.score


def test_intent_empty_text_is_validation_error():
    with pytest.raises(ValueError):
        TextIntentInput(text="")


def test_intent_tool_can_invoke_independently():
    result = analyze_text_intent.invoke({"text": "品牌合作推广"})
    assert result["tool_name"] == "analyze_text_intent"

