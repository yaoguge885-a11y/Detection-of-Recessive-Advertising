"""Generate synthetic A/B blind-review packages without private data or network.

Run from any directory: python scripts/demo_m1_handoff.py
Outputs are local synthetic examples, never formal M1 annotation evidence.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'data-tooling' / 'annotation'))
import build_m1_qwen_blind_remote_v2_manifest as manifest_builder
import generate_m1_qwen_blind_html as generator
import package_m1_qwen_blind_role as packager


def run_demo(output_root: Path) -> dict:
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError('choose a new output directory; existing results are preserved')
    output_root.mkdir(parents=True)
    media = output_root / 'data' / 'run_outputs' / 'synthetic' / 'media'
    media.mkdir(parents=True)
    # A fixed 1x1 PNG fixture, with no external image or personal data.
    (media / 'pixel.png').write_bytes(base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='))
    source = media.parent / 'candidates.jsonl'
    rows = [
        {'post_id': 'synthetic_demo_image', 'platform': 'synthetic', 'title': 'Synthetic image case',
         'text': 'Synthetic content for testing the review interface only.',
         'media': [{'type': 'image', 'ref': 'media/pixel.png'}], 'comments': []},
        {'post_id': 'synthetic_demo_text', 'platform': 'synthetic', 'title': 'Synthetic text case',
         'text': 'No real advertisement or person is represented.', 'media': [], 'comments': []},
    ]
    source.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    parent = output_root / 'parent_manifest.json'
    parent.write_text(json.dumps({
        'sample_count': len(rows), 'qwen_run_performed': False, 'labels_known_to_sampler': False,
        'source': {'sha256': generator.sha256_file(source), 'record_count': len(rows)},
        'items': [{'ordinal': i + 1, 'post_id': row['post_id']} for i, row in enumerate(rows)],
    }), encoding='utf-8')
    blind = output_root / 'data' / 'reports' / 'm1' / 'synthetic_blind_demo'
    manifest = blind / 'manifest_v2.json'
    manifest_builder.build_manifest(repo_root=output_root, parent_manifest_path=parent,
        input_path=source, media_base=media.parent, output_path=manifest)
    delivery = blind / 'delivery'
    result = generator.generate_delivery(repo_root=output_root, manifest_path=manifest,
        input_path=source, guide_path=ROOT / 'docs' / 'annotation_guide_v1.md',
        media_base=media.parent, output_root=delivery, roles=('A', 'B'))
    archives = {}
    for role in ('A', 'B'):
        archive = output_root / f'synthetic_{role}_portable.zip'
        packager.build_role_archive(repo_root=output_root, delivery_root=delivery,
            input_path=source, media_base=media.parent, output_path=archive, role=role)
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            other = 'B' if role == 'A' else 'A'
            assert not any(f'/delivery/{other}/' in name for name in names)
            assert any(f'M1_Blind_Human_Review_{role}.html' in name for name in names)
            assert any(name.endswith('media/pixel.png') for name in names)
            assert bundle.testzip() is None
        archives[role] = str(archive)
    report = {'status': 'passed', 'dataset_kind': 'synthetic_fixture',
              'formal_evidence': False, 'network_requests': 0, 'model_calls': 0,
              'sample_count': len(rows), 'html_files': result['html_files'], 'archives': archives}
    (output_root / 'demo_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, default=None)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    output = args.output_root or ROOT / 'data' / 'run_outputs' / f'handoff_demo_{stamp}'
    try:
        print(json.dumps(run_demo(output), ensure_ascii=True, indent=2))
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
