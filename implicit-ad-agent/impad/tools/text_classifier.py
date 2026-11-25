"""Optional, local-only inference for an advertisement-trained binary encoder."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _load_local_classifier(model_path: str):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False,
    )
    model, loading = AutoModelForSequenceClassification.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False,
        output_loading_info=True,
    )
    if loading.get("missing_keys") or loading.get("mismatched_keys"):
        raise ValueError("A complete fine-tuned classifier checkpoint is required")
    if model.config.num_labels != 2:
        raise ValueError("The commercial-intent classifier must have two labels")
    model.to(torch.device("cpu")).eval()
    return tokenizer, model


def predict_commercial_intent(
    text: str, model_path: str, *, positive_label_id: int = 1,
) -> float:
    """Return P(commercial), with label polarity set by the training task.

    Only an existing local model directory is accepted. Models and tokenizers
    are never downloaded, and custom checkpoint code is never executed.
    """
    path = Path(model_path)
    if not path.is_dir():
        raise ValueError("An existing local model directory is required")
    if positive_label_id not in {0, 1}:
        raise ValueError("positive_label_id must be 0 or 1")

    import torch

    tokenizer, model = _load_local_classifier(str(path.resolve()))
    tokens = tokenizer(
        text, truncation=True,
        max_length=min(512, model.config.max_position_embeddings),
        return_tensors="pt",
    )
    with torch.inference_mode():
        logits = model(**tokens).logits
        return float(logits.float().softmax(dim=-1)[0, positive_label_id].item())
