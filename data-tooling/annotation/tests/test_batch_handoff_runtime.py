from __future__ import annotations

import json
import sys
from pathlib import Path
import threading
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import batch_pre_annotate as batch
from batch_annotation_runtime import BatchSession, run_ordered
from auto_judge import determine_media_evidence_status, normalize_suggestion


def _record(pid):
    return {'audit': {'post_id': pid, 'tier': 'manual', 'label_normalized': 'uncertain',
                      'fallback': False, 'error': None}, 'auto': None, 'suggest': None}


def test_parallel_completion_exports_manifest_order_and_resume_does_not_repeat(tmp_path):
    posts = [{'post_id': str(i)} for i in range(4)]
    config = {'post_ids': [post['post_id'] for post in posts], 'guide_sha': 'synthetic'}
    barrier = threading.Barrier(2)
    calls = []

    def worker(post):
        calls.append(post['post_id'])
        barrier.wait(timeout=5)
        if post['post_id'] in {'0', '2'}:
            time.sleep(0.03)
        return _record(post['post_id'])

    with BatchSession(tmp_path, config, None) as session:
        run_ordered(posts, session, worker, 2)
        paths = session.export()
        batch_id = session.batch_id
    with BatchSession(tmp_path, config, batch_id) as session:
        run_ordered(posts, session, lambda _: pytest.fail('completed item repeated'), 2)
        session.export()
    assert len(calls) == 4
    rows = [json.loads(line) for line in paths['audit'].read_text().splitlines()]
    assert [row['post_id'] for row in rows] == config['post_ids']


def test_failed_batch_can_resume_completed_prefix_and_reject_changed_guide(tmp_path):
    config = {'post_ids': ['a', 'b'], 'guide_sha': 'original'}
    with BatchSession(tmp_path, config, None) as session:
        session.save(0, _record('a'))
        batch_id = session.batch_id
    with pytest.raises(ValueError, match='mismatch'):
        with BatchSession(tmp_path, dict(config, guide_sha='changed'), batch_id):
            pass
    with BatchSession(tmp_path, config, batch_id) as session:
        run_ordered([{'post_id': 'a'}, {'post_id': 'b'}], session,
                    lambda post: _record(post['post_id']), 2)
        assert len(session.records) == 2


def test_legacy_or_corrupt_checkpoints_fail_closed(tmp_path):
    (tmp_path / 'progress_20260802_120000.jsonl').write_text('{}\n')
    with pytest.raises(ValueError, match='legacy'):
        with BatchSession(tmp_path, {'post_ids': ['a']}, 'latest'):
            pass
    with BatchSession(tmp_path, {'post_ids': ['a']}, None) as session:
        checkpoint = session.checkpoints / '00000000.json'
        batch_id = session.batch_id
    checkpoint.write_text('{bad json')
    with pytest.raises(ValueError):
        with BatchSession(tmp_path, {'post_ids': ['a']}, batch_id):
            pass


def test_batch_cli_propagates_guide_context_and_audits_manual_results(tmp_path, monkeypatch):
    source = tmp_path / 'source.jsonl'
    source.write_text('{"post_id":"a","text":"synthetic"}\n')
    guide = tmp_path / 'guide.md'
    guide.write_text('Synthetic guide')
    seen = []

    def fake_judge(post, **kwargs):
        seen.append(kwargs)
        return {'tier': 'manual', 'suggestion': {'label': 'uncertain', 'confidence': 0},
                'record': None, 'fallback': False, 'error': None, 'backend': 'test_stub',
                'label_raw': 'uncertain'}

    monkeypatch.setattr(batch, 'run_auto_judge', fake_judge)
    args = ['--input', str(source), '--guide', str(guide), '--output-dir', str(tmp_path / 'out'),
            '--no-images', '--no-warmup', '--num-parallel', '2', '--num-ctx', '8192']
    assert batch.main(args) == 0
    assert batch.main(args + ['--resume']) == 0
    assert len(seen) == 1
    assert seen[0]['guide_text'] == 'Synthetic guide'
    assert seen[0]['num_ctx'] == 8192
    assert seen[0]['media_analysis_requested'] is False
    audit = next((tmp_path / 'out').glob('audit_*.jsonl'))
    row = json.loads(audit.read_text())
    assert row['backend'] == 'test_stub' and row['label_normalized'] == 'uncertain'


def test_partial_media_and_nonfinite_confidence_cannot_look_complete():
    post = {'media': [{'ref': 'one.png'}, {'ref': 'two.png'}]}
    assert determine_media_evidence_status(post, {0: {}}, True) == 'partial'
    assert determine_media_evidence_status(post, {0: {}, 1: {}}, True) == 'provided'
    for value in ('nan', 'inf', '-inf'):
        assert normalize_suggestion({'label': '非广', 'confidence': value})['confidence'] == 0
