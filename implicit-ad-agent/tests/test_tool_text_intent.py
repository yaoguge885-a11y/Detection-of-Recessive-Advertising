import json
import pytest

from impad.tools.text_intent import TextIntentInput, _analyze_text_intent_core, analyze_text_intent
from impad.tools.disclosure import disclosure_evidence


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


def test_plain_peer_collaboration_is_not_disclosure():
    result = _analyze_text_intent_core(
        TextIntentInput(text="今天和同学合作完成课程作业")
    )

    assert not any(
        item.kind == "explicit_ad_marker" for item in result.evidence
    )


@pytest.mark.parametrize("text", [
    "今天聊聊广告套路，不代表这是广告。",
    "如何获得品牌合作机会？",
    "这是给第三方拍的付费广告片。",
    "这不是品牌合作，我是自费买的。",
])
def test_discussion_third_party_and_denial_are_not_disclosure(text):
    evidence = disclosure_evidence(text)
    assert not any(item.kind == "explicit_ad_marker" for item in evidence)


def test_ambiguous_candidate_keeps_the_complete_sentence_and_span():
    text = "今天分享使用感受。这次合作安排还没有说明。"
    evidence = disclosure_evidence(text)
    candidates = [item for item in evidence if item.kind == "disclosure_candidate"]

    assert len(candidates) == 1
    assert candidates[0].quote == "这次合作安排还没有说明。"
    assert text[candidates[0].span[0]:candidates[0].span[1]] == candidates[0].quote


def test_explicit_post_disclosure_is_sentence_level_evidence():
    text = "本篇为品牌付费合作。后面是产品体验。"
    evidence = disclosure_evidence(text)
    marker = next(item for item in evidence if item.kind == "explicit_ad_marker")

    assert marker.quote == "本篇为品牌付费合作。"
    assert text[marker.span[0]:marker.span[1]] == marker.quote


@pytest.mark.parametrize("text", [
    "这是品牌合作吗？",
    "我在分析这条付费合作的案例。",
    "现在还能接商务合作吗？",
    "他这期是付费合作。",
])
def test_questions_discussion_and_third_party_are_not_explicit_disclosure(text):
    evidence = disclosure_evidence(text)

    assert not any(item.kind == "explicit_ad_marker" for item in evidence)


@pytest.mark.parametrize("text", [
    "本篇为品牌付费合作。",
    "本期由某品牌赞助。",
])
def test_current_post_disclosure_is_explicit(text):
    evidence = disclosure_evidence(text)

    assert any(item.kind == "explicit_ad_marker" for item in evidence)


def test_negative_clause_does_not_hide_later_explicit_disclosure():
    text = "这不是品牌合作，但本篇为品牌付费合作。"
    evidence = disclosure_evidence(text)
    markers = [item for item in evidence if item.kind == "explicit_ad_marker"]

    assert len(markers) == 1
    assert markers[0].quote == text


@pytest.mark.parametrize("text", [
    "本期是品牌合作吗？",
    "品牌合作？",
    "她引用了‘本篇为品牌付费合作’这句话。",
])
def test_question_or_quote_is_a_candidate_not_explicit_disclosure(text):
    evidence = disclosure_evidence(text)

    assert not any(item.kind == "explicit_ad_marker" for item in evidence)
    assert any(item.kind == "disclosure_candidate" for item in evidence)


def test_teaching_an_ad_label_is_not_post_disclosure():
    evidence = disclosure_evidence("我教你识别 #ad 标签。")

    assert not any(item.kind == "explicit_ad_marker" for item in evidence)


def test_standalone_short_labels_and_regular_ad_hashtag_remain_explicit():
    labels = disclosure_evidence("品牌合作，广告，限时购买")
    regular_post = disclosure_evidence("新品体验，记录一下 #ad")

    assert any(item.kind == "explicit_ad_marker" for item in labels)
    assert any(item.kind == "explicit_ad_marker" for item in regular_post)


def test_intent_empty_text_is_validation_error():
    with pytest.raises(ValueError):
        TextIntentInput(text="")


def test_intent_tool_can_invoke_independently():
    result = analyze_text_intent.invoke({"text": "品牌合作推广"})
    assert result["tool_name"] == "analyze_text_intent"

