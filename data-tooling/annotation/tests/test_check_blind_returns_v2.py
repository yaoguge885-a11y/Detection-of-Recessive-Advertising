"""Synthetic checks of receipt gates; never use real review answers."""
from copy import deepcopy
from contextlib import contextmanager
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_blind_returns_v2 as tool


@contextmanager
def synthetic_directory():
    # Keep clearly separated fixtures and logs inside the writable workspace.
    # Windows sandbox Temp directories may apply ACLs that deny later writes.
    root = tool.PACK / "private" / "synthetic_test_fixtures" / uuid4().hex
    root.mkdir(parents=True)
    yield root


def fixture(role="A"):
    meta = {"manifest_sha256": "a" * 64, "source_sha256": "b" * 64,
            "guide_sha256": "c" * 64, "missing_media_count": 0, "remote_link_media_count": 1}
    expected = [{"post_id": "synthetic_image", "ordinal": 1,
                 "media": [{"ref": "image.png", "local_exists": True, "remote_available": False}]},
                {"post_id": "synthetic_video", "ordinal": 2,
                 "media": [{"ref": "", "local_exists": False, "remote_available": True, "remote_key": "remote_1"}]}]
    payload = {"schema_version": "m1_blind_human_review_v2", "role": role, "annotation_method": "human",
               "qwen_visible": False, "sample_count": 2, "exported_at": "2026-10-26T00:00:00Z",
               "status": "completed_with_remote_unpinned_media_evidence",
               "reviewer_id": "synthetic_reviewer_" + role, "reviewer_name": "TEST " + role,
               "annotator_id": "synthetic_reviewer_" + role, **{k: v for k, v in meta.items() if k.endswith("sha256")},
               "attestation": {"reviewer_id": "synthetic_reviewer_" + role, "reviewer_name": "TEST " + role,
                               **{k: True for k in tool.ATTESTATIONS}, "media_gaps_ack": False}, "items": []}
    for e in expected:
        local = e["ordinal"] == 1
        payload["items"].append({"post_id": e["post_id"], "ordinal": e["ordinal"], "reviewed": True,
                                 "label": "非广", "confidence": 0.7, "evidence": "SYNTHETIC TEST ONLY",
                                 "reviewed_at": "2026-10-26T00:00:00Z", "uncertain_reason": "",
                                 "media_review": {"media_ref_count": 1, "local_media_ref_count": int(local),
                                 "remote_link_media_ref_count": int(not local), "missing_media_ref_count": 0,
                                 "viewed_media_refs": ["image.png"] if local else [], "all_local_media_viewed": True,
                                 "all_remote_media_resolved": True, "media_review_confirmed": True,
                                 "remote_media_statuses": {} if local else {"remote_1": "reviewed"},
                                 "remote_open_attempts": {} if local else {"remote_1": "2026-10-26T00:00:00Z"},
                                 "media_gap_acknowledged": False}})
    return meta, expected, payload


class ReceiptTests(unittest.TestCase):
    def test_complete_synthetic_export_passes_structure_only(self):
        m, e, p = fixture()
        result = tool.validate(p, "A", m, e)
        self.assertTrue(result["structurally_valid"], result["errors"])
        self.assertFalse(result["human_independence_verified"])

    def test_wrong_role_hash_ai_and_duplicate_ids_rejected(self):
        m, e, base = fixture()
        changes = [lambda p: p.update(role="B"), lambda p: p.update(manifest_sha256="0" * 64),
                   lambda p: p.update(annotation_method="system"), lambda p: p.update(qwen_visible=True),
                   lambda p: p["items"][1].update(post_id=p["items"][0]["post_id"])]
        for change in changes:
            p = deepcopy(base)
            change(p)
            self.assertFalse(tool.validate(p, "A", m, e)["structurally_valid"])

    def test_unseen_local_and_unopened_remote_rejected(self):
        m, e, base = fixture()
        for item, key, value in [(0, "viewed_media_refs", []), (1, "remote_open_attempts", {})]:
            p = deepcopy(base)
            p["items"][item]["media_review"][key] = value
            self.assertFalse(tool.validate(p, "A", m, e)["structurally_valid"])

    def test_remote_unavailable_requires_gap_declaration(self):
        m, e, p = fixture()
        p["items"][1]["media_review"]["remote_media_statuses"]["remote_1"] = "unavailable"
        self.assertFalse(tool.validate(p, "A", m, e)["structurally_valid"])
        p["status"] = "completed_with_declared_evidence_gaps"
        p["attestation"]["media_gaps_ack"] = True
        p["items"][1]["media_review"]["media_gap_acknowledged"] = True
        self.assertTrue(tool.validate(p, "A", m, e)["structurally_valid"])

    def test_uncertainty_and_nonfinite_confidence_rejected(self):
        m, e, p = fixture()
        p["items"][0]["label"] = "uncertain"
        self.assertFalse(tool.validate(p, "A", m, e)["structurally_valid"])
        p["items"][0]["uncertain_reason"] = "SYNTHETIC MISSING EVIDENCE"
        p["items"][0]["confidence"] = float("nan")
        self.assertFalse(tool.validate(p, "A", m, e)["structurally_valid"])

    def test_no_comparison_without_both_and_seal(self):
        with self.assertRaises(SystemExit) as error:
            tool.main(["--compare"])
        self.assertEqual(error.exception.code, 2)

    def test_compare_preserves_originals_and_leaves_adjudication_blank(self):
        m, e, a = fixture("A")
        _, _, b = fixture("B")
        b["items"][1]["label"] = "暗广"
        with synthetic_directory() as temp:
            root = Path(temp)
            inputs = [root / "A.json", root / "B.json"]
            for p, data in zip(inputs, (a, b)):
                p.write_text(json.dumps(data, ensure_ascii=False, indent=3), encoding="utf-8")
            originals = [p.read_bytes() for p in inputs]
            with patch.object(tool, "frozen_context", return_value=(m, e)):
                code = tool.main(["--a", str(inputs[0]), "--b", str(inputs[1]), "--seal", "--compare", "--output-dir", str(root / "out")])
            self.assertEqual(code, 0)
            self.assertEqual((root / "out/original_A.json").read_bytes(), originals[0])
            self.assertEqual((root / "out/original_B.json").read_bytes(), originals[1])
            queue = json.loads((root / "out/needs_human_adjudication.json").read_text(encoding="utf-8"))
            self.assertEqual(len(queue["items"]), 1)
            self.assertIsNone(queue["items"][0]["human_final_label"])
            stats = json.loads((root / "out/comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(stats["same_label_count"], 1)
            self.assertEqual(stats["formal_gold_count"], 0)

    def test_same_reviewer_ids_cannot_trigger_comparison(self):
        m, e, a = fixture("A")
        _, _, b = fixture("B")
        for key in ("reviewer_id", "annotator_id"):
            b[key] = a[key]
        b["attestation"]["reviewer_id"] = a["reviewer_id"]
        with synthetic_directory() as temp:
            root = Path(temp)
            for role, data in (("A", a), ("B", b)):
                (root / (role + ".json")).write_text(json.dumps(data), encoding="utf-8")
            with patch.object(tool, "frozen_context", return_value=(m, e)):
                code = tool.main(["--a", str(root / "A.json"), "--b", str(root / "B.json"), "--seal", "--compare", "--output-dir", str(root / "out")])
            self.assertEqual(code, 2)
            self.assertFalse((root / "out/comparison.json").exists())


if __name__ == "__main__":
    unittest.main()
