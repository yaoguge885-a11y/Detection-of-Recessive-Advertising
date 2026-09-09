# Merged-history baseline

`baseline/` is an isolated engineering baseline. It compares a target-post
feature vector with the same vector plus creator-history mean, max, or
chronological EMA pooling. The input gate is fail-closed: formal runs require a
passed M1 gate, complete Gold, and leakage-zero split evidence before training.

## Reproduce the engineering check

Run these PowerShell commands from the repository root:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m pip install -r baseline\requirements.txt
.\implicit-ad-agent\.venv\Scripts\python.exe -m pytest baseline\tests -q
.\implicit-ad-agent\.venv\Scripts\python.exe -m baseline.cli synthetic --content baseline\tests\fixtures\synthetic_content.jsonl --gold baseline\tests\fixtures\synthetic_gold.jsonl --train-ids baseline\tests\fixtures\train_ids.txt --dev-ids baseline\tests\fixtures\dev_ids.txt --test-ids baseline\tests\fixtures\test_ids.txt --split-report baseline\tests\fixtures\synthetic_split_report.json --m1-gate baseline\tests\fixtures\synthetic_gate.json --fixture-metadata baseline\tests\fixtures\fixture_metadata.json --output baseline\synthetic_report.json
```

The synthetic command exercises loading, leakage-safe history construction,
four fixed classifiers, metrics, and atomic UTF-8 report writing. The generated
`baseline\synthetic_report.json` is an aggregate engineering artifact only;
inspect it and remove it manually after the check. It is not formal Gold and
cannot support paper claims, CreatorShift gains, or M4 acceptance.

## Formal evaluation boundary

After M1 has passed, provide named paths to the approved formal artifacts. The
formal command uses the same input arguments, except it does not take fixture
metadata:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m baseline.cli formal --content <approved-content.jsonl> --gold <approved-gold.jsonl> --train-ids <approved-train-ids.txt> --dev-ids <approved-dev-ids.txt> --test-ids <approved-test-ids.txt> --split-report <approved-split-report.json> --m1-gate <approved-m1-gate.json> --output <formal-report.json>
```

Formal `test` evaluation additionally requires
`--evaluation-split test --confirm-test-evaluation`. A failed input or gate
prints only an aggregate reason to stderr and exits with status 2; an existing
final report is never replaced on that path. Current M1 status, approved Gold,
privacy/terms review, and research reporting remain independent formal gates.
