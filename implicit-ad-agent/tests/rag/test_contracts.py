import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from impad.contracts.verdict import LawEvidence
from impad.rag.contracts import LegalDocument, LegalSection


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_law_evidence_uses_canonical_retrieval_fields():
    evidence = LawEvidence(
        source_id="fixture_ad_rules",
        document_title="合成广告规则",
        article_id="A1",
        quote="广告内容应当标明。",
        source_path_or_url="fixture://ad-rules",
        document_version="fixture-v1",
        effective_date=date(2026, 1, 1),
        retrieval_score=0.9,
        rerank_score=0.85,
        limitations=["Synthetic test fixture."],
    )

    dumped = evidence.model_dump(mode="json")
    assert dumped["source_id"] == "fixture_ad_rules"
    assert dumped["document_title"] == "合成广告规则"
    assert dumped["source_path_or_url"] == "fixture://ad-rules"
    assert "reference_id" not in dumped
    json.dumps(dumped, ensure_ascii=False)


def test_law_evidence_accepts_legacy_input_names():
    evidence = LawEvidence(
        reference_id="legacy_rules",
        title="旧字段规则",
        source_url="fixture://legacy",
    )

    assert evidence.source_id == "legacy_rules"
    assert evidence.document_title == "旧字段规则"
    assert evidence.source_path_or_url == "fixture://legacy"
    assert evidence.reference_id == "legacy_rules"
    assert evidence.title == "旧字段规则"
    assert evidence.source_url == "fixture://legacy"


def test_legal_document_keeps_versioned_section_provenance():
    document = LegalDocument(
        source_id="fixture_ad_rules",
        document_title="合成广告规则",
        source_path_or_url="fixture://ad-rules",
        document_version="fixture-v1",
        effective_date=date(2026, 1, 1),
        authority_level="synthetic_fixture",
        fixture_only=True,
        sections=[
            LegalSection(
                article_id="A1",
                title="披露",
                text="广告内容应当标明。",
            )
        ],
    )

    assert document.sections[0].article_id == "A1"
    assert document.fixture_only is True
    json.dumps(document.model_dump(mode="json"), ensure_ascii=False)


def test_contracts_can_be_imported_without_optional_chromadb_dependency():
    script = """
import sys

class BlockChroma:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "chromadb" or fullname.startswith("chromadb."):
            raise ModuleNotFoundError("chromadb blocked for contract-only import")
        return None

sys.meta_path.insert(0, BlockChroma())
from impad.rag.contracts import LegalDocument
print(LegalDocument.__name__)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "LegalDocument"
