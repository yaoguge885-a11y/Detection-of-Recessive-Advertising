# P3 Engineering Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the non-data-dependent P3 engineering scope with deterministic hybrid legal retrieval, version-bound evaluation reports, classification error analysis, MCP timeout fallback, and synchronized handoff/test documentation.

**Architecture:** Keep the existing `LegalRetriever.retrieve()` boundary and wrap the Chroma baseline with an in-memory lexical index plus deterministic RRF fusion. Put version-bound benchmark orchestration in a separate RAG reporting module, put classification error reporting next to existing classification metrics, and expose both through one zero-network CLI with explicit subcommands.

**Tech Stack:** Python 3.10, Pydantic v2, ChromaDB with existing deterministic hash embeddings, pytest, argparse, JSON.

## Global Constraints

- Work in the current `P2_Tool-Compartment-Model-Tooling` checkout as explicitly requested; do not create a second worktree that omits the six local commits already ahead of origin.
- Keep default validation zero-key and zero-network.
- Add no dependency and do not expand the official legal corpus.
- Keep the `LegalRetriever` protocol signature unchanged.
- Keep LightRAG out of the runtime and requirements; it remains a future evidence-gated A/B candidate.
- Preserve exact indexed quotes and validate all final citations with `CitationGuard`.
- Missing or invalid evidence means abstention/degradation, never negative proof or an invented citation.
- Deterministic runs keep `token_usage={}` and `cost_usd=None`.
- Synthetic/fixture metrics validate engineering behavior only; they are not research findings.
- Formal M3 remains blocked by M1 Gold, blind annotation, leakage-safe split, terms, and privacy evidence.
- Use the project interpreter: `.\.venv\Scripts\python.exe`.
- Baseline before implementation: `276 passed, 2 skipped, 1 warning`.

---

### Task 1: Deterministic Hybrid Legal Retriever

**Files:**

- Create: `implicit-ad-agent/impad/rag/hybrid_retriever.py`
- Modify: `implicit-ad-agent/impad/rag/corpus.py`
- Modify: `implicit-ad-agent/impad/rag/__init__.py`
- Create: `implicit-ad-agent/tests/rag/test_hybrid_retriever.py`
- Modify: `implicit-ad-agent/tests/rag/test_official_corpus.py`

**Interfaces:**

- Consumes: `LegalDocument`, `LegalRetriever.retrieve(query: str, top_k: int = 5) -> list[LawEvidence]`, `CitationGuard`.
- Produces: `HybridLegalRetriever(documents, vector_retriever, *, rrf_k=60, vector_candidates=10, minimum_lexical_score=0.1)` implementing the unchanged retrieval protocol.
- Produces: `tokenize_legal_text(text: str) -> list[str]` for deterministic English/alphanumeric tokens plus Chinese unigrams and adjacent bigrams.
- Produces: `build_default_legal_retriever()` returning an indexed `HybridLegalRetriever`.

- [x] **Step 1: Write failing hybrid retrieval tests**

Create tests that use real `LegalDocument` and `LawEvidence` values. The tests must prove these observable behaviors:

```python
def test_hybrid_retriever_unions_paths_and_sets_stable_rerank_scores():
    retriever = HybridLegalRetriever(
        documents=_documents(),
        vector_retriever=FixedVectorRetriever([_vector_evidence()]),
    )
    result = retriever.retrieve("正文显著位置广告合作", top_k=2)
    assert [(item.source_id, item.article_id) for item in result] == [
        ("fixture_disclosure", "D1"),
        ("fixture_platform", "P1"),
    ]
    assert result[0].rerank_score == 1.0
    assert all(
        item.rerank_score is not None
        and 0 <= item.rerank_score <= 1
        for item in result
    )
```

```python
def test_vector_failure_uses_lexical_evidence_without_inventing_quote():
    retriever = HybridLegalRetriever(
        documents=_documents(),
        vector_retriever=FailingVectorRetriever(),
    )
    result = retriever.retrieve("商业推广正文广告合作", top_k=1)
    assert result[0].quote == _documents()[0].sections[0].text
    assert "Vector retrieval unavailable; lexical fallback used." in (
        result[0].limitations
    )
```

Also cover:

- `retrieve("", top_k=5) == []`.
- unrelated query plus an empty vector retriever returns `[]`.
- `top_k=0` raises `ValueError("top_k must be at least 1")`.
- repeated calls return the same ordered `(source_id, article_id, rerank_score)` tuples.

- [x] **Step 2: Run the new tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/rag/test_hybrid_retriever.py -q
```

Expected: collection fails because `impad.rag.hybrid_retriever` does not exist.

- [x] **Step 3: Implement deterministic lexical indexing and RRF**

Implement only these public interfaces:

- `tokenize_legal_text(text: str) -> list[str]`
- `HybridLegalRetriever.__init__(documents: list[LegalDocument], vector_retriever: LegalRetriever, *, rrf_k: int = 60, vector_candidates: int = 10, minimum_lexical_score: float = 0.1)`
- `HybridLegalRetriever.retrieve(query: str, top_k: int = 5) -> list[LawEvidence]`

Implementation rules:

- Store a keyed section map using `(source_id, document_version, article_id)`.
- Lexical score is `len(query_tokens & section_tokens) / len(query_tokens)`.
- Discard lexical candidates below `minimum_lexical_score`.
- Ask the vector retriever for `max(top_k, vector_candidates)` candidates.
- Fuse the candidate union with `sum(1 / (rrf_k + rank))` over present paths.
- Sort by fused score descending, best path rank ascending, source ID ascending, article ID ascending.
- Normalize each fused score by the largest fused score in the candidate set and write it to `rerank_score`.
- Keep a vector candidate's `retrieval_score`; lexical-only candidates use their lexical score as `retrieval_score`.
- When the vector path raises, append exactly `Vector retrieval unavailable; lexical fallback used.` to lexical result limitations.
- Build lexical evidence only from stored document metadata and section text.
- Run `CitationGuard.validate()` on the final list.

- [x] **Step 4: Run hybrid tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/rag/test_hybrid_retriever.py tests/rag/test_chroma_retriever.py -q
```

Expected: all tests pass.

- [x] **Step 5: Wire the default corpus to the hybrid retriever**

Update `build_default_legal_retriever()` to:

1. Load `LegalCorpus`.
2. Build and index the existing `ChromaLegalRetriever`.
3. Return `HybridLegalRetriever(corpus.documents, vector_retriever)`.

Export `HybridLegalRetriever` and `tokenize_legal_text` from `impad.rag`.

Extend the official-corpus test with:

```python
retriever = build_default_legal_retriever()
assert isinstance(retriever, HybridLegalRetriever)
assert retriever.retrieve("互联网广告应当具有可识别性", top_k=1)[0].rerank_score == 1.0
```

- [x] **Step 6: Run focused RAG regression**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/rag -q
```

Expected: all RAG tests pass and existing Chroma behavior remains available.

- [x] **Step 7: Commit Task 1**

```powershell
git add -- implicit-ad-agent/impad/rag/hybrid_retriever.py implicit-ad-agent/impad/rag/corpus.py implicit-ad-agent/impad/rag/__init__.py implicit-ad-agent/tests/rag/test_hybrid_retriever.py implicit-ad-agent/tests/rag/test_official_corpus.py
git commit -m "feat: add deterministic hybrid legal retrieval"
```

---

### Task 2: Version-Bound Retrieval Benchmarks and CLI Report

**Files:**

- Create: `implicit-ad-agent/impad/rag/benchmark.py`
- Modify: `implicit-ad-agent/impad/rag/evaluation.py`
- Modify: `implicit-ad-agent/impad/rag/__init__.py`
- Create: `implicit-ad-agent/scripts/evaluate_p3.py`
- Modify: `implicit-ad-agent/tests/fixtures/legal_rag_documents.json`
- Modify: `implicit-ad-agent/tests/fixtures/legal_rag_eval_30.json`
- Modify: `implicit-ad-agent/tests/fixtures/legal_rag_official_eval_15.json`
- Modify: `implicit-ad-agent/tests/rag/test_evaluation.py`
- Modify: `implicit-ad-agent/tests/rag/test_official_evaluation.py`
- Create: `implicit-ad-agent/tests/rag/test_benchmark.py`
- Create: `implicit-ad-agent/tests/scripts/test_evaluate_p3.py`

**Interfaces:**

- Consumes: `LegalCorpus`, `HybridLegalRetriever`, `ChromaLegalRetriever`, `evaluate_retriever`.
- Produces: `LegalRetrievalBenchmark(benchmark_version, corpus_version, questions)`.
- Produces: `P3RetrievalReport(retriever_name, retriever_version, corpus_version, benchmark_version, question_count, indexed_sections, indexing_time_ms, evaluation_time_ms, generated_at, deterministic_config, metrics)`.
- Produces: `load_retrieval_benchmark(path: Path) -> LegalRetrievalBenchmark`.
- Produces: `run_p3_retrieval_benchmark(corpus: LegalCorpus, benchmark: LegalRetrievalBenchmark, *, top_k: int = 5, minimum_score: float = 0.34) -> P3RetrievalReport`.
- Produces CLI: `python scripts/evaluate_p3.py retrieval --corpus PATH --benchmark PATH --output PATH`.

- [x] **Step 1: Convert fixtures to explicit versioned schemas**

Change `legal_rag_documents.json` from its current five-element array to an
object with `corpus_version` equal to `synthetic-legal-v1` and `documents`
equal to that unchanged five-element array.

Change `legal_rag_eval_30.json` from its current 30-element array to an
object with `benchmark_version` equal to `synthetic-30-v1`,
`corpus_version` equal to `synthetic-legal-v1`, and `questions` equal to
that unchanged 30-element array.

Add this field to `legal_rag_official_eval_15.json`:

```json
"corpus_version": "cn-official-v1-2026-07-27"
```

- [x] **Step 2: Write failing metric and benchmark tests**

Update fixture loaders to validate `LegalCorpus` and `LegalRetrievalBenchmark`.

Add hand-derived metric assertions proving retrieval cutoffs are independent:

```python
assert metrics.recall_at_1 == 0.5
assert metrics.recall_at_3 == 1.0
assert metrics.recall_at_5 == 1.0
```

Use a fixed retriever whose first three keys make those literals true.

Add version-binding tests:

```python
with pytest.raises(
    ValueError,
    match="benchmark expects corpus synthetic-legal-v2, got synthetic-legal-v1",
):
    run_p3_retrieval_benchmark(corpus, mismatched_benchmark)
```

Add a report test asserting:

- `indexed_sections` equals the exact section count.
- `indexing_time_ms >= 0`.
- `evaluation_time_ms >= 0`.
- `retriever_version == "hybrid_rrf_v1"`.
- report metrics contain 30 results for the synthetic fixture.

- [x] **Step 3: Run benchmark tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/rag/test_evaluation.py tests/rag/test_benchmark.py -q
```

Expected: failures for missing wrapper model/report functions and missing `recall_at_1`/`recall_at_3`.

- [x] **Step 4: Add cutoff metrics without breaking existing fields**

Extend `LegalRetrievalMetrics` with:

```python
recall_at_1: float = Field(ge=0, le=1)
recall_at_3: float = Field(ge=0, le=1)
```

Keep all current `*_at_5` fields. Derive each cutoff from the first `n` unique retrieved keys; do not run the retriever three times.

- [x] **Step 5: Implement benchmark loading, version checks, timing, and report**

Create `impad/rag/benchmark.py` with the exact interfaces above.

Rules:

- Pydantic validates the only supported object schema.
- Reject a corpus/benchmark version mismatch before indexing.
- Measure Chroma construction/indexing plus hybrid construction as `indexing_time_ms`.
- Measure `evaluate_retriever()` as `evaluation_time_ms`.
- Count indexed sections from `corpus.documents`.
- Use `retriever_name="chroma_lexical_rrf"` and `retriever_version="hybrid_rrf_v1"`.
- Store `top_k`, `minimum_score`, `rrf_k=60`, `vector_candidates=10`, and `external_embedding=False` in `deterministic_config`.
- Use an aware UTC `generated_at`.

- [x] **Step 6: Run benchmark tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/rag/test_evaluation.py tests/rag/test_benchmark.py tests/rag/test_official_evaluation.py -q
```

Expected: all tests pass; synthetic Recall@5 remains at least 0.6, direct Recall@5 at least 0.8, cross-document Recall@5 at least 0.3, and official Recall/MRR at least 0.6 with zero false citations.

- [x] **Step 7: Write failing CLI behavior tests**

Test `scripts.evaluate_p3.main()` with explicit temporary paths:

```python
exit_code = main([
    "retrieval",
    "--corpus", str(corpus_path),
    "--benchmark", str(benchmark_path),
    "--output", str(output_path),
])
assert exit_code == 0
payload = json.loads(output_path.read_text(encoding="utf-8"))
assert payload["corpus_version"] == "synthetic-legal-v1"
assert payload["metrics"]["total_questions"] == 30
```

Also assert that a version mismatch raises a visible `ValueError` and does not create the output.

- [x] **Step 8: Run CLI tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/scripts/test_evaluate_p3.py -q
```

Expected: failure because `scripts.evaluate_p3` does not exist.

- [x] **Step 9: Implement the retrieval CLI**

Use `argparse` with a required `retrieval` subcommand and required `--corpus`, `--benchmark`, `--output`. Resolve inputs as `Path`, call the benchmark interfaces, create the output parent, and write:

```python
report.model_dump_json(indent=2)
```

with UTF-8 encoding. Return exit code 0. Do not read `.env`, invoke an LLM, or access the network.

- [x] **Step 10: Run CLI and full RAG tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/rag tests/scripts/test_evaluate_p3.py -q
```

Expected: all tests pass.

- [x] **Step 11: Commit Task 2**

```powershell
git add -- implicit-ad-agent/impad/rag/benchmark.py implicit-ad-agent/impad/rag/evaluation.py implicit-ad-agent/impad/rag/__init__.py implicit-ad-agent/scripts/evaluate_p3.py implicit-ad-agent/tests/fixtures/legal_rag_documents.json implicit-ad-agent/tests/fixtures/legal_rag_eval_30.json implicit-ad-agent/tests/fixtures/legal_rag_official_eval_15.json implicit-ad-agent/tests/rag/test_evaluation.py implicit-ad-agent/tests/rag/test_official_evaluation.py implicit-ad-agent/tests/rag/test_benchmark.py implicit-ad-agent/tests/scripts/test_evaluate_p3.py
git commit -m "feat: add version-bound P3 retrieval reports"
```

---

### Task 3: Classification Error Analysis and CLI Subcommand

**Files:**

- Create: `implicit-ad-agent/impad/evaluation/reporting.py`
- Modify: `implicit-ad-agent/impad/evaluation/__init__.py`
- Modify: `implicit-ad-agent/scripts/evaluate_p3.py`
- Create: `implicit-ad-agent/tests/fixtures/classification_eval_v1.json`
- Create: `implicit-ad-agent/tests/evaluation/test_reporting.py`
- Modify: `implicit-ad-agent/tests/scripts/test_evaluate_p3.py`

**Interfaces:**

- Consumes: `ClassificationPrediction`, `ClassificationMetrics`, `evaluate_classification`.
- Produces: `ClassificationEvaluationFixture(benchmark_version, predictions)`.
- Produces: `ClassificationErrorReport(benchmark_version, generated_at, metrics, multiclass_confusion, binary_confusion, misclassified_sample_ids, review_sample_ids, error_buckets)`.
- Produces: `build_classification_report(fixture: ClassificationEvaluationFixture, *, calibration_bins: int = 10) -> ClassificationErrorReport`.
- Produces CLI: `python scripts/evaluate_p3.py classification --predictions PATH --output PATH`.

- [x] **Step 1: Create a six-row explicit fixture**

Create `classification_eval_v1.json` with:

```json
{
  "benchmark_version": "synthetic-classification-v1",
  "predictions": [
    {"sample_id": "1", "true_label": "明广", "predicted_label": "明广", "dark_ad_score": 0.05},
    {"sample_id": "2", "true_label": "暗广", "predicted_label": "暗广", "dark_ad_score": 0.9},
    {"sample_id": "3", "true_label": "非广", "predicted_label": "非广", "dark_ad_score": 0.1},
    {"sample_id": "4", "true_label": "暗广", "predicted_label": "需复核", "dark_ad_score": 0.6},
    {"sample_id": "5", "true_label": "明广", "predicted_label": "暗广", "dark_ad_score": 0.7},
    {"sample_id": "6", "true_label": "非广", "predicted_label": "明广", "dark_ad_score": 0.2}
  ]
}
```

- [x] **Step 2: Write failing classification report tests**

Assert literal, hand-counted outputs:

```python
assert report.multiclass_confusion["暗广"]["暗广"] == 1
assert report.multiclass_confusion["暗广"]["需复核"] == 1
assert report.multiclass_confusion["明广"]["暗广"] == 1
assert report.binary_confusion["dark_ad"]["review_required"] == 1
assert report.misclassified_sample_ids == ["4", "5", "6"]
assert report.review_sample_ids == ["4"]
assert report.error_buckets == {
    "明广->暗广": ["5"],
    "暗广->需复核": ["4"],
    "非广->明广": ["6"],
}
```

Also assert `report.metrics == evaluate_classification(fixture.predictions)`. Pydantic must reject a missing or out-of-range `dark_ad_score`; no fallback from confidence is accepted.

- [x] **Step 3: Run report tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/evaluation/test_reporting.py -q
```

Expected: import failure because `impad.evaluation.reporting` does not exist.

- [x] **Step 4: Implement the minimal report layer**

Use stable row/column orders:

```python
TRUE_LABELS = ("明广", "暗广", "非广")
PREDICTED_LABELS = ("明广", "暗广", "非广", "需复核")
```

For binary dark-ad analysis:

- true rows are `dark_ad`, `not_dark_ad`.
- predicted columns are `dark_ad`, `not_dark_ad`, `review_required`.
- `需复核` maps only to `review_required`.
- `暗广` maps to `dark_ad`.
- `明广` and `非广` map to `not_dark_ad`.

Sort sample IDs within each output by their input order. Sort error-bucket keys lexicographically before model construction.

- [x] **Step 5: Run report tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/evaluation -q
```

Expected: all tests pass.

- [x] **Step 6: Extend CLI tests and implement `classification`**

Add a test that calls:

```python
main([
    "classification",
    "--predictions", str(fixture_path),
    "--output", str(output_path),
])
```

Assert the output benchmark version, `sample_count == 6`, and the literal error IDs.

Implement the subcommand by validating `ClassificationEvaluationFixture`, calling `build_classification_report`, and writing UTF-8 JSON. Keep retrieval behavior unchanged.

- [x] **Step 7: Run all P3 evaluation tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/evaluation tests/rag tests/scripts/test_evaluate_p3.py -q
```

Expected: all tests pass.

- [x] **Step 8: Commit Task 3**

```powershell
git add -- implicit-ad-agent/impad/evaluation/reporting.py implicit-ad-agent/impad/evaluation/__init__.py implicit-ad-agent/scripts/evaluate_p3.py implicit-ad-agent/tests/fixtures/classification_eval_v1.json implicit-ad-agent/tests/evaluation/test_reporting.py implicit-ad-agent/tests/scripts/test_evaluate_p3.py
git commit -m "feat: add P3 classification error reports"
```

---

### Task 4: MCP Timeout Fallback and Deterministic Usage Semantics

**Files:**

- Modify: `implicit-ad-agent/impad/orchestration/mcp_gateway.py`
- Modify: `implicit-ad-agent/tests/orchestration/test_mcp_gateway.py`
- Modify: `implicit-ad-agent/tests/services/test_analysis_service.py`

**Interfaces:**

- Consumes: existing `StdioDetectionMCPClient._request()` and `MCPToolGateway` exception fallback.
- Produces: `StdioDetectionMCPClient(*, python_executable: str | None = None, project_root: Path | None = None, timeout_seconds: float = 30.0)`.
- Preserves: `MCPToolGateway.call()` fallback limitation code `mcp_transport_fallback`.

- [x] **Step 1: Write failing timeout tests**

Use a real subclass boundary, not mock assertions:

```python
class SlowStdioClient(StdioDetectionMCPClient):
    async def _request(self, **kwargs):
        await asyncio.sleep(0.05)
```

Test:

```python
gateway = MCPToolGateway(client=SlowStdioClient(timeout_seconds=0.001))
result = gateway.call(
    "analyze_text_intent",
    {"text": "品牌合作，限时购买"},
    RunContext(run_id="run_timeout"),
)
assert gateway.fallback_count == 1
assert any(
    item.code == "mcp_transport_fallback"
    for item in result.limitations
)
```

Also assert `timeout_seconds=0` and `timeout_seconds=-1` raise `ValueError("timeout_seconds must be greater than 0")`.

- [x] **Step 2: Run timeout tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_mcp_gateway.py -q
```

Expected: failures because the constructor does not accept `timeout_seconds`.

- [x] **Step 3: Implement one timeout wrapper**

Add:

```python
def _run_request(self, **kwargs):
    return asyncio.run(asyncio.wait_for(
        self._request(**kwargs),
        timeout=self.timeout_seconds,
    ))
```

Validate the constructor value and route both `list_tools()` and `call_tool()` through `_run_request()`. Do not change `MCPToolGateway`'s broad transport fallback semantics.

- [x] **Step 4: Run timeout and orchestration tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_mcp_gateway.py tests/orchestration -q
```

Expected: all tests pass; timeout and existing connection failure both use the same local fallback contract.

- [x] **Step 5: Lock existing deterministic usage semantics**

Add these assertions to the real local `AnalysisService` test:

```python
assert result.run_metadata.token_usage == {}
assert result.run_metadata.cost_usd is None
```

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_analysis_service.py -q
```

Expected: PASS immediately because this documents an existing contract and requires no production change.

- [x] **Step 6: Commit Task 4**

```powershell
git add -- implicit-ad-agent/impad/orchestration/mcp_gateway.py implicit-ad-agent/tests/orchestration/test_mcp_gateway.py implicit-ad-agent/tests/services/test_analysis_service.py
git commit -m "feat: bound MCP stdio requests with timeout"
```

---

### Task 5: Generate P3 Evidence and Synchronize Handoff/Test Documentation

**Files:**

- Create: `data/reports/p3/retrieval_synthetic_30.json`
- Create: `data/reports/p3/retrieval_official_15.json`
- Create: `data/reports/p3/classification_fixture.json`
- Modify: `README.md`
- Modify: `HANDOFF.md`
- Modify: `docs/隐性广告识别项目_分阶段计划表.md`
- Modify: `docs/已有功能测试指令库.md`

**Interfaces:**

- Consumes: completed `scripts/evaluate_p3` CLI and all actual test outputs.
- Produces: three privacy-safe aggregate/fixture-only JSON reports.
- Produces: copyable zero-network verification commands and explicit unfinished boundaries.

- [ ] **Step 1: Generate the synthetic retrieval report**

Run from `implicit-ad-agent`:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_p3.py retrieval --corpus tests\fixtures\legal_rag_documents.json --benchmark tests\fixtures\legal_rag_eval_30.json --output ..\data\reports\p3\retrieval_synthetic_30.json
```

Expected: exit code 0 and a 30-question report bound to `synthetic-legal-v1`.

- [ ] **Step 2: Generate the official small-corpus report**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_p3.py retrieval --corpus impad\rag\data\legal_corpus_v1.json --benchmark tests\fixtures\legal_rag_official_eval_15.json --output ..\data\reports\p3\retrieval_official_15.json
```

Expected: exit code 0, corpus version `cn-official-v1-2026-07-27`, Recall@5 and MRR@5 at least 0.6, false-citation rate 0.

- [ ] **Step 3: Generate the classification fixture report**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_p3.py classification --predictions tests\fixtures\classification_eval_v1.json --output ..\data\reports\p3\classification_fixture.json
```

Expected: exit code 0, six fixture rows, and misclassified IDs `4`, `5`, `6`.

- [ ] **Step 4: Inspect report safety and metrics**

Read the three JSON files and verify:

- no raw post text, URLs, creator IDs, annotator IDs, secrets, or environment values.
- retrieval reports contain version binding, indexing latency, P95 latency, Recall@1/3/5, MRR@5, citation precision, false-citation rate, and per-question IDs/keys only.
- classification report is explicitly named as a synthetic fixture result.

- [ ] **Step 5: Update root README**

Add:

- P3 non-data engineering status.
- both retrieval and classification CLI commands.
- report paths.
- zero-key/zero-network boundary.
- statement that official corpus is only a two-document, seven-section engineering corpus.
- statement that formal M3 remains blocked by M1.

- [ ] **Step 6: Update HANDOFF**

Record:

- exact implemented modules and report paths.
- actual focused/full test counts from Task 6.
- MCP timeout default and fallback limitation code.
- deterministic token/cost semantics.
- remaining M1, remote MCP, legal coverage, LightRAG, and P4 boundaries.

- [ ] **Step 7: Update phase plan**

Fix the stale summary claiming the Agent main chain is not connected. Mark only the non-data P3 engineering rows complete. Keep formal M3 incomplete and link it to M1 evidence.

- [ ] **Step 8: Update existing-function test library**

Add copyable commands for:

- hybrid RAG focused tests.
- synthetic and official report generation.
- classification report generation.
- MCP timeout focused test.
- complete pytest.

For every command include expected evidence, optional/risky flags, and the boundary that tests do not prove research accuracy or legal completeness.

- [ ] **Step 9: Run Markdown and report diff checks**

Run:

```powershell
git diff --check
git diff --stat
```

Expected: no whitespace errors; only task files appear.

- [ ] **Step 10: Commit Task 5**

```powershell
git add -- data/reports/p3/retrieval_synthetic_30.json data/reports/p3/retrieval_official_15.json data/reports/p3/classification_fixture.json README.md HANDOFF.md docs/隐性广告识别项目_分阶段计划表.md docs/已有功能测试指令库.md
git commit -m "docs: close P3 engineering handoff"
```

---

### Task 6: Full Verification, Review, and Final Implementation Commit

**Files:**

- Verify all files changed in Tasks 1-5.
- Modify documentation only if an actual test count or report value differs.

**Interfaces:**

- Consumes: every implementation and report above.
- Produces: verified branch state with no uncommitted task changes.

- [ ] **Step 1: Run dependency and syntax checks**

Run from `implicit-ad-agent`:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q impad tests scripts
```

Expected: `No broken requirements found.` and exit code 0.

- [ ] **Step 2: Run focused P3 tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/rag tests/evaluation tests/orchestration/test_mcp_gateway.py tests/services/test_analysis_service.py tests/scripts/test_evaluate_p3.py -q
```

Expected: all pass, no new skip.

- [ ] **Step 3: Run complete tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all pass; skipped count remains exactly 2. The existing Starlette/httpx deprecation warning may remain but no new warning is accepted.

- [ ] **Step 4: Run P1 validators**

Run from repository root:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe .\scripts\validate_data_contracts.py
.\implicit-ad-agent\.venv\Scripts\python.exe .\scripts\validate_annotation_gold.py
```

Expected: both exit 0. These validators prove schema/fixture invariants only and do not pass M1.

- [ ] **Step 5: Re-run generated report commands**

Re-run all three Task 5 commands and confirm:

- corpus/benchmark versions are unchanged.
- threshold assertions still hold.
- output schema is stable.

Update documentation only with the observed final values and test counts.

- [ ] **Step 6: Review the complete diff**

Run:

```powershell
git status --short
git diff --check
git diff HEAD~5 --stat
git log -6 --oneline
```

Review every changed line against the approved design. Remove no unrelated code and do not reformat adjacent files.

- [ ] **Step 7: Commit any verification-only documentation correction**

Only if test counts/report values required a correction:

```powershell
git add -- README.md HANDOFF.md docs/隐性广告识别项目_分阶段计划表.md docs/已有功能测试指令库.md
git commit -m "docs: record final P3 verification"
```

- [ ] **Step 8: Invoke completion skills**

Use:

- `superpowers:verification-before-completion`
- `superpowers:requesting-code-review`
- `superpowers:finishing-a-development-branch`

Report the exact test evidence, report paths, commit IDs, remaining formal M3 blockers, and branch-ahead state. Do not push or merge without a separate explicit request.
