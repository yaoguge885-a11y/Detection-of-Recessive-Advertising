from pathlib import Path
import hashlib
import importlib.util
import json
import re
import sys
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'data-tooling/annotation'))
import build_assisted_review as builder


def demo_at(path):
    spec = importlib.util.spec_from_file_location('assisted_demo', ROOT / 'scripts/demo_assisted_review.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_demo(path)


def test_synthetic_demo_preserves_original_fields_and_media_paths(tmp_path):
    out = tmp_path / 'demo'
    result = demo_at(out)
    assert result['status'] == 'passed' and result['formal_evidence'] is False
    seed = json.loads((out / 'review/seed.json').read_text(encoding='utf-8'))
    source = (out / 'synthetic_inputs/draft.json').read_bytes()
    assert (out / 'review/original_user_draft.json').read_bytes() == source
    assert hashlib.sha256(source).hexdigest() == seed['source_snapshot_sha256']
    assert seed['records']['synthetic_assisted_1'] == seed['original_records']['synthetic_assisted_1']
    assert seed['records']['synthetic_assisted_2']['confidence'] == '0.6'
    assert seed['records']['synthetic_assisted_3']['reviewed'] is False
    html = Path(result['entrypoint']).read_text(encoding='utf-8')
    payload = re.search(r'<script id="seed" type="application/json">([\s\S]*?)</script>', html).group(1)
    assert json.loads(payload) == seed
    for item in seed['items']:
        for media in item['source']['media']:
            if media['local_exists']:
                assert (out / 'review' / unquote(media['local_url'])).is_file()
    with pytest.raises(FileExistsError):
        demo_at(out)


def test_wrong_context_or_media_path_is_rejected_without_writing_output(tmp_path):
    out = tmp_path / 'demo'
    demo_at(out)
    draft_path = out / 'synthetic_inputs/draft.json'
    draft = json.loads(draft_path.read_text(encoding='utf-8'))
    draft['guide_sha256'] = 'wrong'
    draft_path.write_text(json.dumps(draft), encoding='utf-8')
    target = out / 'bad_review'
    with pytest.raises(ValueError, match='fingerprint'):
        builder.build_assisted_review(draft_path=draft_path, page_path=out / 'synthetic_inputs/delivery/B/M1_Blind_Human_Review_B.html',
            suggestions_path=out / 'synthetic_inputs/suggestions.json', media_base=out / 'synthetic_inputs', output_root=target)
    assert not target.exists()


def test_suggestions_cannot_certify_human_review(tmp_path):
    out = tmp_path / 'demo'
    demo_at(out)
    suggestions = out / 'synthetic_inputs/suggestions.json'
    payload = json.loads(suggestions.read_text(encoding='utf-8'))
    payload['items'][0]['fields']['reviewed'] = True
    suggestions.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError, match='declarations'):
        builder.build_assisted_review(draft_path=out / 'synthetic_inputs/draft.json',
            page_path=out / 'synthetic_inputs/delivery/B/M1_Blind_Human_Review_B.html', suggestions_path=suggestions,
            media_base=out / 'synthetic_inputs', output_root=out / 'bad_review')
