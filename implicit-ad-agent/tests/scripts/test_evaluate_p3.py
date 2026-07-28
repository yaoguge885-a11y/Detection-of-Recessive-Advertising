import json
from pathlib import Path

import pytest

from scripts.evaluate_p3 import main


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_retrieval_command_writes_a_version_bound_report(tmp_path):
    output = tmp_path / "reports" / "retrieval.json"

    exit_code = main([
        "retrieval",
        "--corpus",
        str(FIXTURES / "legal_rag_documents.json"),
        "--benchmark",
        str(FIXTURES / "legal_rag_eval_30.json"),
        "--output",
        str(output),
    ])

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["corpus_version"] == "synthetic-legal-v1"
    assert payload["benchmark_version"] == "synthetic-30-v1"
    assert payload["metrics"]["total_questions"] == 30
    assert payload["metrics"]["recall_at_1"] >= 0


def test_retrieval_command_does_not_write_a_mismatched_report(tmp_path):
    benchmark = json.loads(
        (FIXTURES / "legal_rag_eval_30.json").read_text(encoding="utf-8")
    )
    benchmark["corpus_version"] = "synthetic-legal-v2"
    benchmark_path = tmp_path / "mismatched.json"
    benchmark_path.write_text(
        json.dumps(benchmark, ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "retrieval.json"

    with pytest.raises(
        ValueError,
        match=(
            "benchmark expects corpus synthetic-legal-v2, "
            "got synthetic-legal-v1"
        ),
    ):
        main([
            "retrieval",
            "--corpus",
            str(FIXTURES / "legal_rag_documents.json"),
            "--benchmark",
            str(benchmark_path),
            "--output",
            str(output),
        ])

    assert not output.exists()


def test_classification_command_writes_error_analysis(tmp_path):
    output = tmp_path / "classification.json"

    exit_code = main([
        "classification",
        "--predictions",
        str(FIXTURES / "classification_eval_v1.json"),
        "--output",
        str(output),
    ])

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["benchmark_version"] == "synthetic-classification-v1"
    assert payload["metrics"]["sample_count"] == 6
    assert payload["misclassified_sample_ids"] == ["4", "5", "6"]
    assert payload["review_sample_ids"] == ["4"]
