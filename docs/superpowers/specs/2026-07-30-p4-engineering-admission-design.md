# P4 Engineering Admission Design

**Date:** 2026-07-30  
**Status:** Approved by the user's autonomous-execution instruction  
**Scope:** P1-independent CreatorShift runtime integration and evaluation infrastructure

## 1. Goal

Complete a P4 engineering admission package that can be verified with
versioned synthetic fixtures while formal M1 data remains unavailable:

1. connect the existing leakage-safe CreatorShift kernel to the Agent evidence
   chain;
2. provide a deterministic, version-bound CreatorShift benchmark and run
   manifest;
3. provide deterministic bootstrap intervals and a risk-coverage evaluation
   report;
4. synchronize `HANDOFF.md` and `docs/已有功能测试指令库.md`.

This package must make future real-data experiments easier without claiming
that CreatorShift improves classification, that Judge is calibrated, or that
M4 has passed.

## 2. Current Facts

- `PostRecord` already rejects duplicate history IDs, target-post reuse,
  cross-creator history, and known timestamps that are not strictly earlier
  than the target.
- `impad.creator_shift` already implements `CreatorHistoryView`,
  mean/max/EMA pooling, and interpretable shift calculation over numeric
  features.
- the current graph runs NLP, vision, and behavior tool groups before a
  deterministic Judge.
- `VerdictReport.creator_shift_evidence_ids` exists, but no runtime node
  currently creates those evidence items.
- the full zero-key baseline is `299 passed, 2 skipped, 1 warning`.
- formal M1 remains `passed=false`; real Gold, formal blind agreement,
  leakage-safe splits, terms completion, and privacy approval are absent.

## 3. Considered Approaches

### A. Register CreatorShift as an eighth tool

This would reuse Function Calling, ToolGateway, and MCP, but it would change
the stable seven-tool boundary and treat a research expert/model as a regular
detection tool. It is rejected.

### B. Fold CreatorShift into `behavior_agent`

This is the smallest diff, but it mixes the existing topic-drift tool with a
separate P4 research capability and makes runtime traces harder to interpret.
It is rejected.

### C. Add a dedicated deterministic CreatorShift node

The graph runs a dedicated node after the existing tool groups. The node uses
the current CreatorShift kernel, writes a structured summary, and contributes
neutral supplemental evidence. The Judge records the evidence but does not use
the uncalibrated score to change the label. This is the selected approach.

## 4. Runtime Architecture

```text
PostRecord
  -> existing NLP / vision / behavior tool groups
  -> CreatorShift node
       -> deterministic text feature adapter
       -> CreatorHistoryView
       -> mean/max/EMA baseline (runtime default: EMA alpha=0.5)
       -> CreatorShiftSummary
       -> neutral EvidenceItem when sufficient
  -> EvidenceBundle
  -> existing adequacy gate and deterministic Judge
  -> VerdictReport
  -> readable report and run persistence
```

### 4.1 Feature adapter

The first runtime adapter reuses `compute_keyword_weights()` for target and
historical text. It does not introduce a learned embedding or another keyword
table. The feature version is `keyword_weights_v1`.

History with missing timestamps is excluded and reported as a limitation.
Missing target time makes the assessment `unavailable`. Fewer than three valid
historical posts makes it `insufficient`. Neither state creates numeric
evidence or a zero shift.

### 4.2 Structured result

`CreatorShiftSummary` records:

- `status`: `sufficient`, `insufficient`, or `unavailable`;
- observed and required history counts;
- feature and runtime versions;
- pooling method and shift score when sufficient;
- history IDs, time window, top features, and limitations.

When sufficient, the node creates one `EvidenceItem`:

- `kind=creator_shift`;
- `source_type=history`;
- `polarity=neutral`;
- `producer=agent:creator_shift`;
- metadata containing the structured summary.

The score remains evidence only. It must not alter commercial intent,
disclosure, label, confidence, or the adequacy gate in this round.

### 4.3 Evidence assembly

`build_evidence_bundle()` accepts optional supplemental evidence in addition
to the seven ToolResult adapters. Existing callers remain valid. Coverage and
evidence-reference validation include the supplemental items.

The CreatorShift node and Judge both rebuild the bundle with the same
supplemental evidence, so later nodes cannot silently drop it.

## 5. Versioned CreatorShift Benchmark

A synthetic fixture contains normalized `PostRecord` cases and a
`benchmark_version`. The benchmark:

- computes a canonical SHA-256 fixture hash;
- runs mean, max, and EMA for every case;
- records status, history sufficiency, shift score, top features, and
  limitations;
- records feature version, runtime version, methods, minimum history, and EMA
  alpha;
- writes a JSON report through `scripts/evaluate_p4.py creator-shift`.

The fixture is an engineering contract only. It contains no research labels
and produces no classification accuracy claim.

## 6. Calibration and Selective Evaluation

A separate versioned calibration fixture contains explicit:

- sample ID;
- three-class true label;
- three-class predicted label before abstention;
- decision confidence;
- dark-ad score.

The report:

- reuses existing classification metrics;
- computes deterministic percentile bootstrap intervals with an explicit seed
  and resample count;
- computes a risk-coverage curve by retaining predictions from highest to
  lowest decision confidence, with sample ID as the tie breaker;
- records every configuration value and writes JSON through
  `scripts/evaluate_p4.py calibration`.

Risk is the classification error rate among retained predictions. Coverage is
the retained fraction. This framework does not choose a production threshold;
real threshold selection requires a leakage-safe validation split.

## 7. Error and Degradation Rules

- missing or naive target timestamps produce `unavailable`, not exceptions in
  the runtime node;
- invalid `PostRecord` history such as cross-creator or future records remains
  a contract error at normalization;
- insufficient valid history produces no CreatorShift evidence item;
- a benchmark fixture with duplicate case/sample IDs is rejected;
- non-finite features or scores are rejected by Pydantic/domain validation;
- bootstrap resamples must be positive and the confidence level must be
  between 0 and 1;
- default tests remain zero-key and zero-network.

## 8. Acceptance Criteria

1. A synthetic graph run with three valid historical posts persists a
   sufficient CreatorShift summary and one neutral history evidence item.
2. The same classification input produces the same label and confidence with
   or without CreatorShift evidence.
3. Missing target time, no history, and short history remain explicit
   unavailable/insufficient states without numeric shift evidence.
4. Future, equal-time, cross-creator, and duplicate history remain rejected.
5. The CreatorShift benchmark report is version-bound, hash-bound, and covers
   mean/max/EMA.
6. The calibration report contains classification metrics, deterministic
   bootstrap intervals, and a monotonic coverage curve.
7. Focused and full tests, compilation, `pip check`, both P1 validators, report
   regeneration, report safety scan, and `git diff --check` pass.
8. `HANDOFF.md`, `docs/已有功能测试指令库.md`, and phase/status documentation
   state both the new engineering facts and the formal M1/M4 boundary.

## 9. Non-goals

- training or selecting a learned CreatorShift model;
- using CreatorShift score as an advertising probability;
- changing Judge thresholds or classification logic;
- publishing real data or adding real creator identifiers;
- claiming real classification gain, calibration, statistical significance,
  M3 passage, or M4 passage;
- implementing A2A, platform URL adapters, Web, or LightRAG in this package.
