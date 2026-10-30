"""Run the public, model-free P1 handoff checks from the repository root.

Install requirements-handoff.txt first. Real vision/Ollama tests are separate.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    output = ROOT / 'data' / 'run_outputs' / f'handoff_checks_{stamp}'
    output.mkdir(parents=True)
    subprocess_temp = output / 'tmp_subprocess'
    subprocess_temp.mkdir()
    environment = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8',
                   'TMP': str(subprocess_temp), 'TEMP': str(subprocess_temp)}
    python = sys.executable
    checks = [
        ('dependencies', ROOT, [python, '-m', 'pip', 'check']),
        ('annotation', ROOT, [python, '-X', 'utf8', '-m', 'pytest',
            'data-tooling/annotation/tests', '-q', '--tb=short', '--basetemp', str(output / 'tmp_annotation')]),
        ('baseline', ROOT, [python, '-X', 'utf8', '-m', 'pytest',
            'baseline/tests', '-q', '--tb=short', '--basetemp', str(output / 'tmp_baseline')]),
        ('agent', ROOT / 'implicit-ad-agent', [python, '-X', 'utf8', '-m', 'pytest',
            'tests', '-q', '--tb=short', '--basetemp', str(output / 'tmp_agent')]),
        ('submission_assets', ROOT, [python, '-X', 'utf8', 'scripts/data/validate_submission_assets.py']),
        ('tooling_assets', ROOT, [python, '-X', 'utf8', 'data-tooling/validate_submission_assets.py']),
        ('blind_demo', ROOT, [python, '-X', 'utf8', 'scripts/demo_m1_handoff.py',
            '--output-root', str(output / 'blind_demo')]),
        ('agent_demo', ROOT / 'implicit-ad-agent', [python, '-X', 'utf8', 'run_demo.py']),
    ]
    node = shutil.which('node')
    if node:
        checks.append(('web_behavior', ROOT, [node, '--test',
            'implicit-ad-agent/tests/web/workbench_behavior.test.cjs']))
    results = []
    for name, cwd, command in checks:
        print(f'Running {name} ...', flush=True)
        log = output / f'{name}.log'
        with log.open('w', encoding='utf-8') as stream:
            completed = subprocess.run(command, cwd=cwd, env=environment,
                                       stdout=stream, stderr=subprocess.STDOUT)
        results.append({'name': name, 'exit_code': completed.returncode,
                        'log': log.relative_to(ROOT).as_posix()})
        print(f'  exit={completed.returncode}: {log.relative_to(ROOT)}', flush=True)
    report = {'status': 'passed' if all(item['exit_code'] == 0 for item in results) else 'failed',
              'python': sys.version, 'formal_evidence': False, 'checks': results,
              'optional_web_behavior': 'executed' if node else 'skipped: Node.js unavailable'}
    (output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
