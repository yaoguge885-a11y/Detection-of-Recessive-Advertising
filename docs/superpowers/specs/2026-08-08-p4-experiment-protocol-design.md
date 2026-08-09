# P4 CreatorShift Frozen Experiment Protocol

**Date:** 2026-08-08

**Protocol version:** `p4_experiment_protocol_v1`

**Status:** Frozen before formal test evaluation

**Scope:** Formal comparison, uncertainty estimation, ablation, reproducibility,
and claim governance for P4 CreatorShift research experiments

## 1. Purpose and binding boundary

This protocol freezes the P4 experiment decisions that can be made without
opening, running, or inspecting the formal test results. It covers:

1. the `single_post`, `history_mean`, `history_max`, `history_ema`, and
   `creator_shift` comparison matrix;
2. the fixed metric definitions;
3. dev-only tuning and one-shot formal test evaluation;
4. seeds, exact model parameters, environment records, and SHA-256 input
   fingerprints;
5. paired creator-cluster bootstrap confidence intervals;
6. the cumulative `text -> vision -> history -> full` ablation;
7. claim-reduction rules when CreatorShift does not demonstrate stable gain.

This document is a research protocol, not a result report. It contains no
formal test metric and does not authorize a formal test run. Formal execution
remains blocked until M1 has passed, the approved Gold and leakage-safe split
artifacts exist, the final dev-selected configuration has been frozen, and the
one-shot test preflight in Section 7 has passed.

The current isolated `baseline/` package remains an engineering baseline. It
implements four methods and point estimates only. Consistent with the boundary
in `2026-08-08-merged-history-baseline-design.md` Section 8, the current package
cannot support a claim of stable gain or statistical significance before the
creator-cluster bootstrap defined here is implemented and run on an approved
formal test cohort.

## 2. Frozen hypotheses and comparison references

### 2.1 Confirmatory question

The single confirmatory question is:

> On the same leakage-safe common test cohort, does `creator_shift` improve
> three-class Macro-F1 over the strongest simple-history pooling method chosen
> on dev, while keeping dark-ad Recall within the frozen non-inferiority margin?

The confirmatory reference, `simple_history_reference`, is selected on dev
from `history_mean`, `history_max`, and `history_ema` using this deterministic
order:

1. highest dev Macro-F1;
2. if tied, highest dev dark-ad F1;
3. if still tied, highest dev dark-ad AUPRC;
4. if still tied, prefer `history_mean`, then `history_max`, then
   `history_ema`.

The selected method name is written into the frozen model manifest before any
formal test access. Test results cannot change the reference method.

### 2.2 Secondary questions

The following are secondary and descriptive:

- whether any history method improves over `single_post`;
- which of mean, max, and chronological EMA is strongest;
- whether CreatorShift changes dark-ad Precision, F1, or AUPRC;
- whether CreatorShift changes dark-ad-score ECE or Brier loss;
- how the cumulative ablation changes each metric.

Secondary comparisons do not independently authorize a general claim that
CreatorShift is superior. No secondary metric may replace Macro-F1 after test
results are visible.

## 3. Common data and cohort contract

All five methods use the same approved train/dev/test split and the same target
posts in each paired comparison. The split must satisfy the formal M1 and
leakage gates, including zero creator, content-group, post, and checked
near-duplicate leakage.

Every history item used by any method must:

- belong to the target post's creator;
- exist in the approved content input exactly once;
- not be the target post;
- have a timezone-aware publication time;
- satisfy `history.published_at < target.published_at` strictly;
- not repeat within a target's history list;
- belong to the permitted training-side information boundary.

The confirmatory comparison uses one common cohort whose members have all
modalities and the minimum historical sufficiency required by the frozen
CreatorShift configuration. `single_post` must be evaluated on this same
cohort, even though it does not consume history. A broader-coverage
`single_post` result may be reported separately as coverage context, but it is
not a paired comparator and cannot be substituted into the confirmatory table.

The formal common test cohort must contain at least 30 distinct creators. This
is a conservative project governance threshold, not a universal statistical
theorem. If the threshold is not met, point estimates and exploratory
creator-cluster intervals may still be reported, but stable-gain and
significance wording is prohibited.

## 4. Frozen comparison matrix

Within a given formal comparison, every method receives the same frozen
per-post target representation, labels, split, common cohort, preprocessing
fit boundary, and tuning budget. Only the history aggregation or longitudinal
component differs.

| Method ID | Target post | Eligible creator history | History operation | Temporal/shift component | Formal role | Current engineering state |
|---|---|---|---|---|---|---|
| `single_post` | Frozen target representation | None | None | None | No-history reference | Implemented in `baseline/` with `keyword_weights_v1` text features |
| `history_mean` | Same target representation | Same pre-target history | Element-wise mean | None | Simple-history comparator | Implemented in `baseline/` |
| `history_max` | Same target representation | Same pre-target history | Element-wise max | None | Simple-history comparator | Implemented in `baseline/` |
| `history_ema` | Same target representation | Same pre-target history in ascending time order | EMA with dev-frozen alpha | Order-sensitive pooling only | Simple-history comparator | Implemented in `baseline/` with `alpha=0.5` |
| `creator_shift` | Same target representation | Same pre-target history | Frozen CreatorShift history encoder | Explicit longitudinal shift representation/model | Proposed method and confirmatory candidate | Deterministic evidence kernel exists; final formal classification model is not yet frozen |

The table does not treat the current deterministic CreatorShift evidence score
as an advertising probability. The final `creator_shift` classifier may enter
formal test only after its complete architecture and parameters are selected
on dev and recorded in the freeze manifest.

The current fixed baseline classifier remains:

```text
StandardScaler fit on train only
LogisticRegression(
    solver="lbfgs",
    C=1.0,
    max_iter=1000,
    random_state=0,
    class_weight=None,
)
```

If the formal CreatorShift study changes the target encoder or classifier
family, all five comparison rows must be rebuilt with the same new target
encoder and the same classifier-head family. Results from incompatible target
representations cannot be placed in the confirmatory matrix as if they were a
controlled history-only comparison.

## 5. Frozen metrics

The fixed class order is `明广`, `暗广`, `非广`. `暗广` is the positive class
for all one-vs-rest metrics.

| Metric | Frozen definition | Direction | Role |
|---|---|---|---|
| Macro-F1 | Arithmetic mean of the three per-class F1 values with the complete fixed class set | Higher is better | Confirmatory primary metric |
| Dark-ad Precision | `暗广` one-vs-rest precision | Higher is better | Secondary |
| Dark-ad Recall | `暗广` one-vs-rest recall | Higher is better | Confirmatory safety guardrail |
| Dark-ad F1 | Harmonic mean of dark-ad Precision and Recall | Higher is better | Secondary |
| Dark-ad AUPRC | Average precision from the continuous `暗广` probability/score | Higher is better | Secondary |
| Dark-ad ECE | Ten equal-width bins over the `暗广` score: `[0.0,0.1)`, ..., `[0.9,1.0]`; sample-weighted absolute accuracy-confidence gap | Lower is better | Secondary calibration metric |
| Dark-ad Brier | Mean squared error between the binary `暗广` indicator and the `暗广` probability/score | Lower is better | Secondary proper scoring rule |

Confusion counts for all three classes, cohort counts, creator counts,
coverage, and exclusions are mandatory context fields but are not additional
optimization targets.

For F1-family metrics, absent denominators use the existing explicit
`zero_division=0` convention. A dark-ad AUPRC bootstrap replicate containing
no dark-ad positives is recorded as `0.0`, matching the current baseline
implementation. The report must count such replicates so readers can see when
class support limits interpretation.

For higher-is-better metrics, improvement is:

```text
delta = creator_shift - reference
```

For ECE and Brier, improvement is oriented so positive still means better:

```text
delta = reference - creator_shift
```

Every formal table reports the point estimate, oriented delta, 95%
creator-cluster confidence interval, number of creators, number of posts, and
bootstrap seed/resample count.

## 6. Dev-only tuning and model freeze

### 6.1 Allowed uses of train and dev

- Model weights and preprocessing statistics are fit on train only.
- Dev may be used for model-family selection, feature selection, history
  window/minimum-history selection, EMA alpha, regularization, early stopping,
  classification threshold, calibration method, and selection of
  `simple_history_reference`.
- Repeated dev runs are allowed, but every compared method receives the same
  declared tuning budget and search protocol.
- Dev decisions and failed configurations are logged before formal test.

### 6.2 Prohibited uses of test

Test labels, predictions, metrics, examples, error buckets, and bootstrap
intervals cannot be used to:

- select a method or feature;
- change prompts, keyword tables, encoders, history windows, EMA alpha, model
  parameters, thresholds, or calibration;
- choose which simple-history comparator to report;
- change the primary metric, Recall margin, creator threshold, confidence
  level, bootstrap method, or claim rule;
- decide which test examples to include.

### 6.3 Frozen final configuration

After dev selection and before any formal test access, one final manifest is
written, reviewed, marked `frozen=true`, and hashed. Any change to a
metric-affecting field invalidates the freeze and is permitted only while test
remains unopened. Once test output is visible, configuration changes create a
post-hoc experiment and cannot replace the official result.

## 7. One-shot formal test rule

The formal test is evaluated once as one atomic experiment containing all five
methods and all four ablation stages. Running methods separately after seeing
earlier results is prohibited.

Before test labels are joined to predictions, the runner must atomically create
a test-run registry entry containing:

- protocol version and protocol SHA-256;
- frozen-manifest SHA-256;
- test input hashes;
- `test_run_id` and UTC start time;
- status `started_before_metrics`.

A completed or metrics-visible registry entry for the same frozen manifest and
test hashes blocks another official run. The existing
`--confirm-test-evaluation` flag is necessary but not sufficient for this
one-shot rule; the future formal runner must also enforce the registry.

A rerun can remain official only when an infrastructure failure occurred before
any joined prediction, per-sample evaluation artifact, aggregate metric, or
bootstrap output became readable. The failed attempt must be retained in the
registry as `failed_before_metrics` with an aggregate reason. Once any test
result becomes readable, all later runs are post-hoc sensitivity analyses;
they must preserve the original result and cannot be presented as the single
official test.

The creator-cluster bootstrap does not rerun or retrain the model. It resamples
the immutable predictions produced by this one formal test invocation.

## 8. Reproducibility manifest

The formal test is blocked unless the frozen manifest contains every field
below with an exact value and a valid SHA-256. Empty, missing, placeholder, or
wildcard values are forbidden.

### 8.1 Seeds and deterministic settings

The v1 protocol freezes:

```text
python_hash_seed = 0
python_random_seed = 0
numpy_seed = 0
model_seed = 0
bootstrap_seed = 20260808
bootstrap_resamples = 10000
bootstrap_confidence_level = 0.95
```

If PyTorch or another stochastic framework is used, its CPU, CUDA, data-loader,
and deterministic-algorithm settings must all be recorded and derived from
`model_seed=0`. Any nondeterministic operation that cannot be disabled is
listed explicitly as a limitation.

The creator-cluster interval estimates sampling uncertainty over creators; it
does not establish training-seed stability. The paper must not convert this
single frozen model seed into a claim of cross-seed robustness.

### 8.2 Exact model and preprocessing parameters

For each method, the manifest records:

- model/encoder/classifier class names and version identifiers;
- every constructor and training parameter, including defaults that affect
  results;
- feature names, order, dimensionality, and feature artifact hash;
- tokenizer/image processor/OCR/model weight identifiers and hashes when used;
- history minimum, maximum/window rule, ordering rule, pooling method, and EMA
  alpha where applicable;
- optimizer, scheduler, learning rate, batch size, epochs, early-stopping rule,
  loss, class weighting, and calibration method where applicable;
- selected threshold and the dev-only selection rule;
- label order and dark-ad positive-class mapping.

Because the final learned CreatorShift configuration does not yet exist, the
formal test remains blocked rather than substituting unspecified defaults. The
protocol is frozen now; the exact dev-selected values are frozen later in the
manifest, still before any test access.

### 8.3 Required input and environment hashes

Byte-level SHA-256 values are recorded for:

- content JSONL;
- formal Gold JSONL;
- train, dev, and test ID files separately;
- split report;
- M1 gate report;
- Schema and Dataset Card versions used for admission;
- model/config manifest;
- feature, tokenizer, processor, calibration, and model-weight artifacts;
- protocol document;
- private immutable prediction artifact after the one-shot run.

The manifest also records the Git commit, dirty-worktree status, Python and
dependency versions, operating system, accelerator type, and exact command.
A dirty tree is not automatically invalid, but every metric-affecting diff must
be captured and hashed; otherwise formal test is blocked.

## 9. Paired creator-cluster bootstrap

### 9.1 Resampling unit

Let the common formal test cohort contain `C` distinct creators. One bootstrap
replicate:

1. draws `C` creator clusters with replacement from those `C` creators;
2. includes every test post belonging to each drawn creator;
3. repeats all posts when a creator is drawn more than once;
4. uses the identical creator draw for all five methods;
5. recomputes every metric and paired method delta from that replicate.

Posts are never resampled independently inside a selected creator. The point
estimate remains post-weighted; the cluster bootstrap changes the uncertainty
estimation so within-creator dependence is not treated as independent evidence.

### 9.2 Interval construction

- Resamples: `B=10000`.
- Random seed: `20260808`.
- Interval: percentile 95% CI using empirical 2.5th and 97.5th percentiles.
- Primary paired delta:
  `creator_shift Macro-F1 - simple_history_reference Macro-F1`.
- Recall guardrail delta:
  `creator_shift dark-ad Recall - simple_history_reference dark-ad Recall`.
- Secondary deltas: all remaining metrics against both
  `simple_history_reference` and `single_post`.

The bootstrap runs only over the immutable one-shot predictions. It does not
refit preprocessing, calibration, or models within a replicate.

The aggregate report records `C`, post count, creator-size distribution
summary, seed, resample count, confidence level, interval method, and count of
zero-dark-positive replicates. Raw creator IDs are not written to the public
report.

### 9.3 Privacy and audit artifact

Creator membership and per-sample predictions may exist only in the approved
private evaluation environment. They are not committed to Git or placed in the
public aggregate report. The public report stores only aggregate metrics,
cluster counts, and the SHA-256 of the access-controlled immutable prediction
artifact.

## 10. Frozen cumulative ablation

The ablation is cumulative and uses the same full common cohort at every stage:

| Stage | Included information | Excluded information | Interpretation |
|---|---|---|---|
| `text` | Target-post text representation | Target vision and all history | Text-only target baseline |
| `vision` | Target text plus target vision/OCR representation | All creator history | Single-post multimodal contribution |
| `history` | `vision` stage plus the dev-selected simple mean/max/EMA history representation | CreatorShift-specific temporal/shift component | Value of simple history |
| `full` | Target text, target vision, same eligible history, and frozen CreatorShift component with dev-frozen calibration | Nothing in the P4 model scope | Incremental value of CreatorShift over simple history |

All mean/max/EMA rows remain in the comparison matrix even though the
`history` ablation stage uses only the dev-selected
`simple_history_reference`. No ablation may use a larger or easier cohort than
`full`. Broader-coverage auxiliary results must be labeled unpaired and
descriptive.

## 11. Confirmatory gate and stop-loss rules

The dark-ad Recall non-inferiority margin is frozen at `-0.02`, measured as an
absolute difference in Recall. The main stable-gain claim is allowed only when
all conditions hold:

1. the common test cohort has at least 30 distinct creators;
2. all five methods and all ablations were produced in the single official test
   run from the frozen manifest;
3. the lower bound of the 95% creator-cluster CI for
   `delta Macro-F1` against `simple_history_reference` is greater than `0`;
4. the lower bound of the 95% creator-cluster CI for
   `delta dark-ad Recall` against `simple_history_reference` is at least
   `-0.02`;
5. no protocol, leakage, hash, privacy, or one-shot-test gate failed.

The permitted claim follows this decision table:

| Observed condition | Maximum permitted paper claim |
|---|---|
| All five confirmatory conditions pass | CreatorShift shows a stable Macro-F1 gain over the strongest dev-selected simple-history baseline under creator-cluster resampling, without exceeding the frozen dark-ad Recall non-inferiority margin |
| Macro-F1 point delta is positive but its CI includes zero | Positive point estimate with unresolved uncertainty; no stable-gain or significance claim |
| CreatorShift beats `single_post` but not the strongest simple-history baseline | Creator history helps; no claim that CreatorShift improves over simple pooling |
| Macro-F1 gate passes but Recall lower bound is below `-0.02` | Mixed discrimination/Recall trade-off; no overall-superiority claim |
| Fewer than 30 test creators | Exploratory point estimates/intervals only; no stable-gain or significance claim |
| ECE or Brier improves without Macro-F1 gain | Calibration or probability-quality claim only; no detection-accuracy gain claim |
| CreatorShift point estimate is equal to or worse than the reference | No detection gain; report the negative result and shrink the paper claim |
| Any leakage, hash, freeze, privacy, or one-shot rule fails | No formal result claim; rerun only under the invalid-run rule in Section 7 |

When stable gain is not established, the title, abstract, contribution list,
and conclusion must not say or imply that CreatorShift improves implicit-ad
detection. The paper may instead make a narrower, evidence-supported claim
about longitudinal representation, interpretable history evidence, calibrated
uncertainty, or the engineering/evaluation framework. The negative or
inconclusive comparison remains in the main results; it cannot be hidden by
switching the primary metric, comparator, cohort, seed, or test run.

The wording “statistically significant” is permitted only for the single
pre-specified confirmatory Macro-F1 comparison when its paired 95%
creator-cluster CI excludes zero and all other confirmatory gates pass. For
secondary comparisons, report estimates and intervals without uncorrected
significance language.

## 12. Required formal outputs

The future one-shot formal run produces:

1. a private, access-controlled immutable prediction artifact for all five
   methods and four ablation stages;
2. a public aggregate JSON report with method metrics, paired deltas,
   creator-cluster intervals, counts, hashes, and gate decisions;
3. a frozen manifest containing exact seeds, parameters, versions, hashes, and
   command;
4. a test-run registry showing the one-shot lifecycle;
5. a human-readable Markdown/LaTeX table generated only from the aggregate
   JSON report.

The public artifacts must not contain post text, OCR text, URLs, media paths,
raw creator/annotator/arbiter identifiers, or per-sample predictions.

## 13. Current implementation status

At protocol freeze time:

- `single_post`, `history_mean`, `history_max`, and `history_ema` point
  estimates exist in `baseline/`;
- the baseline records fixed classifier parameters and input SHA-256 values;
- test evaluation requires explicit confirmation, but a durable one-shot
  registry is not implemented;
- the existing P4 calibration fixture has deterministic sample-level
  percentile bootstrap intervals, not creator-cluster intervals for the five
  formal methods;
- the final formal `creator_shift` classifier, five-method common prediction
  artifact, and creator-cluster bootstrap report are not implemented;
- formal Gold is unavailable and M1 has not passed, so no formal dev/test
  metric, stable gain, statistical significance, or M4 passage is claimed.

These are implementation and research-status boundaries, not missing parts of
the frozen protocol. Any future implementation must satisfy this protocol
before it can produce a formal P4 claim.

## 14. Protocol acceptance checklist

The protocol is frozen only if it states all of the following without reading
formal test results:

- [x] five-method comparison matrix;
- [x] Macro-F1, dark-ad Precision/Recall/F1, AUPRC, ECE, and Brier definitions;
- [x] dev-only tuning and one-shot test rule;
- [x] exact v1 seeds plus a complete model/config/input hash manifest contract;
- [x] paired creator-cluster bootstrap unit, resample count, seed, and interval;
- [x] cumulative `text -> vision -> history -> full` ablation;
- [x] at-least-30-creator and `-0.02` Recall guardrail;
- [x] explicit no-gain claim-reduction rules;
- [x] point-estimate-only boundary for the current baseline;
- [x] privacy separation between private predictions and public aggregates.

## 15. Method references

- Field, C. A., and Welsh, A. H. (2007),
  [Bootstrapping Clustered Data](https://doi.org/10.1111/j.1467-9868.2007.00593.x),
  Journal of the Royal Statistical Society: Series B, 69(3), 369-390.
- Guo, C., Pleiss, G., Sun, Y., and Weinberger, K. Q. (2017),
  [On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html).
- scikit-learn,
  [Metrics and scoring: Brier score loss](https://scikit-learn.org/stable/modules/model_evaluation.html#brier-score-loss).
