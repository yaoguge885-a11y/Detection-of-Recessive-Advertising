"""A local trained classifier changes intent without inventing disclosure."""
from __future__ import annotations

import math
import sys
from types import SimpleNamespace

import pytest

from impad.adapters.manual import post_record_from_manual
from impad.config import settings
from impad.orchestration.evidence_adapters import build_evidence_bundle
from impad.orchestration.judgment import build_verdict_report
from impad.tools import text_intent
from impad.tools.text_intent import TextIntentInput, _analyze_text_intent_core


@pytest.fixture(autouse=True)
def disable_local_classifier(monkeypatch):
    monkeypatch.setattr(settings, "text_intent_model_path", "")


def _enable_classifier(monkeypatch, score):
    monkeypatch.setattr(settings, "text_intent_model_path", "local/ad-detector")
    monkeypatch.setattr(text_intent, "predict_commercial_intent", lambda *args, **kwargs: score)


def test_unconfigured_tool_remains_the_rule_baseline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("An unconfigured model must never load")

    monkeypatch.setattr(text_intent, "predict_commercial_intent", forbidden)
    result = _analyze_text_intent_core(TextIntentInput(text="今天记录读书生活"))
    assert result.status == "degraded"
    assert result.model_info == "rule_v2"
    assert result.score == 0


@pytest.mark.parametrize(("text", "score", "label"), [
    ("今天记录读书生活", 0.9, "暗广"),
    ("限时抢购，扫码下单，闭眼入", 0.1, "非广"),
])
def test_model_score_reaches_the_verdict(monkeypatch, text, score, label):
    _enable_classifier(monkeypatch, score)
    post = post_record_from_manual({"text": text, "capture_complete": True})
    result = _analyze_text_intent_core(TextIntentInput(text=text))
    bundle = build_evidence_bundle(post, [result])
    verdict = build_verdict_report(post, bundle)

    assert result.status == "ok"
    assert result.score == score
    assert result.payload["classifier_score"] == score
    assert result.payload["rule_score"] != score
    prediction = next(item for item in bundle.items if item.kind == "commercial_intent_prediction")
    assert prediction.metadata["model_info"] == "local_sequence_classifier:ad-detector"
    assert verdict.label == label
    assert verdict.disclosure.status == "not_disclosed"
    assert not any(item.kind == "explicit_ad_marker" for item in result.evidence)


def test_model_cannot_erase_a_confirmed_disclosure(monkeypatch):
    _enable_classifier(monkeypatch, 0.1)
    result = _analyze_text_intent_core(TextIntentInput(text="本篇为品牌付费合作。"))
    assert result.score == 0.75
    assert result.payload["classifier_score"] == 0.1
    assert any(item.kind == "explicit_ad_marker" for item in result.evidence)


def test_missing_model_dependency_falls_back_with_a_visible_warning(monkeypatch):
    monkeypatch.setattr(settings, "text_intent_model_path", "local/ad-detector")

    def unavailable(*args, **kwargs):
        raise ImportError("transformers is not installed")

    monkeypatch.setattr(text_intent, "predict_commercial_intent", unavailable)
    result = _analyze_text_intent_core(TextIntentInput(text="今天记录读书生活"))
    assert result.status == "degraded"
    assert result.model_info == "rule_v2"
    assert result.payload["classifier_score"] is None
    assert any("ImportError" in warning for warning in result.warnings)


@pytest.mark.parametrize("score", [math.nan, math.inf, -0.1, 1.1])
def test_invalid_classifier_scores_do_not_enter_a_verdict(monkeypatch, score):
    _enable_classifier(monkeypatch, score)
    result = _analyze_text_intent_core(TextIntentInput(text="今天记录读书生活"))
    assert result.status == "degraded"
    assert result.score == 0
    assert result.payload["classifier_score"] is None


def test_classifier_rejects_a_remote_model_identifier():
    from impad.tools.text_classifier import predict_commercial_intent

    with pytest.raises(ValueError, match="local model directory"):
        predict_commercial_intent("正文", "organization/remote-model", positive_label_id=1)


def _local_checkpoint_double(monkeypatch, *, loading=None, labels=2):
    import torch
    from impad.tools.text_classifier import _load_local_classifier

    def tokenizer(text, *, truncation, max_length, return_tensors):
        assert (truncation, max_length, return_tensors) == (True, 4, "pt")
        return {"input_ids": torch.tensor([[1, 2, 3, 4]])}

    class Model:
        config = SimpleNamespace(num_labels=labels, max_position_embeddings=4)

        def to(self, device):
            return self

        def eval(self):
            return self

        def __call__(self, *, input_ids):
            assert not torch.is_grad_enabled()
            return SimpleNamespace(logits=torch.tensor([[0.0, 2.0]]))

    def load_tokenizer(path, *, local_files_only, trust_remote_code):
        assert local_files_only is True and trust_remote_code is False
        return tokenizer

    def load_model(path, *, local_files_only, trust_remote_code, output_loading_info):
        assert local_files_only is True and trust_remote_code is False
        assert output_loading_info is True
        return Model(), loading or {}

    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=load_tokenizer),
        AutoModelForSequenceClassification=SimpleNamespace(from_pretrained=load_model),
    ))
    _load_local_classifier.cache_clear()
    return _load_local_classifier


def test_local_classifier_maps_the_training_label_and_bounds_input(monkeypatch, tmp_path):
    from impad.tools.text_classifier import predict_commercial_intent

    loader = _local_checkpoint_double(monkeypatch)
    try:
        ad = predict_commercial_intent("正文", str(tmp_path), positive_label_id=1)
        normal = predict_commercial_intent("正文", str(tmp_path), positive_label_id=0)
        assert ad == pytest.approx(0.880797, abs=1e-6)
        assert normal == pytest.approx(0.119203, abs=1e-6)
    finally:
        loader.cache_clear()


@pytest.mark.parametrize(("loading", "labels"), [
    ({"missing_keys": ["classifier.weight"]}, 2),
    ({"mismatched_keys": ["classifier.bias"]}, 2),
    ({}, 3),
])
def test_untrained_or_wrong_task_heads_are_rejected(monkeypatch, tmp_path, loading, labels):
    loader = _local_checkpoint_double(monkeypatch, loading=loading, labels=labels)
    try:
        with pytest.raises(ValueError):
            loader(str(tmp_path))
    finally:
        loader.cache_clear()
