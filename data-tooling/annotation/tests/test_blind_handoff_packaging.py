from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'data-tooling' / 'annotation'))
import build_m1_qwen_blind_remote_v2_manifest as builder
import package_m1_qwen_blind_role as packager


def test_portable_demo_has_valid_hashes_and_only_its_own_role(tmp_path):
    spec = importlib.util.spec_from_file_location('handoff_demo', ROOT / 'scripts' / 'demo_m1_handoff.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / 'demo'
    report = module.run_demo(root)
    assert report['status'] == 'passed' and report['formal_evidence'] is False
    for role, archive in report['archives'].items():
        with zipfile.ZipFile(archive) as bundle:
            records_name = next(name for name in bundle.namelist() if name.endswith(f'{role}_PACKAGE_MANIFEST.json'))
            records = json.loads(bundle.read(records_name))
            for item in records['files_excluding_package_manifest_and_sha256s']:
                assert hashlib.sha256(bundle.read(item['path'])).hexdigest().upper() == item['sha256']
            readme = bundle.read(next(name for name in bundle.namelist()
                                     if name.endswith(f'{role}_PACKAGE_README.md'))).decode('utf-8')
            html_path = records_name.split('/')[0] + '/' + readme.split('`')[3]
            assert html_path in bundle.namelist()
    with pytest.raises(FileExistsError):
        module.run_demo(root)
    source = root / 'data/run_outputs/synthetic/candidates.jsonl'
    source.write_text(source.read_text(encoding='utf-8') + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        packager.build_role_archive(repo_root=root,
            delivery_root=root / 'data/reports/m1/synthetic_blind_demo/delivery',
            input_path=source, media_base=source.parent, output_path=root / 'changed.zip', role='A')


def test_manifest_does_not_invent_unknown_blindness_attestation(tmp_path):
    source = tmp_path / 'source.jsonl'
    source.write_text('{"post_id":"synthetic_one","media":[]}\n')
    manifest = tmp_path / 'parent.json'
    manifest.write_text(json.dumps({'qwen_run_performed': False,
        'items': [{'post_id': 'synthetic_one', 'ordinal': 1}]}))
    with pytest.raises(ValueError, match='explicitly attest'):
        builder.build_manifest(repo_root=tmp_path, parent_manifest_path=manifest,
            input_path=source, media_base=tmp_path, output_path=tmp_path / 'v2.json')
