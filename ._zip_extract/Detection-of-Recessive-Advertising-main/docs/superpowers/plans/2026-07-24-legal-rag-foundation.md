# Legal RAG Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a zero-network Chroma legal retrieval foundation with traceable citations and a runnable 30-question offline benchmark.

**Architecture:** Store synthetic legal sections as explicit chunks, embed with a deterministic local hashing vector, and query an Ephemeral Chroma collection with telemetry disabled. Return only indexed LawEvidence and measure retrieval/abstention behavior.

**Tech Stack:** Python 3.10+, `chromadb>=1.1,<2`, Pydantic 2, pytest.

## Global Constraints

- Test corpus is synthetic and must be labeled as non-authoritative.
- No model downloads, API keys, or network calls.
- RAG does not influence classification.
- Returned citations must correspond to indexed chunks.

---

### Task 1: Legal contracts and retriever protocol

**Files:**
- Modify: `implicit-ad-agent/pyproject.toml`
- Modify: `implicit-ad-agent/impad/contracts/verdict.py`
- Create: `implicit-ad-agent/impad/rag/__init__.py`
- Create: `implicit-ad-agent/impad/rag/contracts.py`
- Create: `implicit-ad-agent/tests/rag/__init__.py`
- Create: `implicit-ad-agent/tests/rag/test_contracts.py`

**Interfaces:**
- Produces: canonical `LawEvidence`, `LegalDocument`, `LegalSection`, `LegalRetriever`.

- [x] **Step 1: Add and install dependency**

Add:

```toml
rag = ["chromadb>=1.1,<2"]
```

Install:

```powershell
.\.venv\Scripts\python.exe -m pip install "chromadb>=1.1,<2"
```

- [x] **Step 2: Write failing contract tests**

Verify canonical LawEvidence fields:

```python
evidence = LawEvidence(
    source_id="fixture_ad_rules",
    document_title="合成广告规则",
    article_id="A1",
    quote="广告内容应当标明。",
    source_path_or_url="fixture://ad-rules",
    retrieval_score=0.9,
)
```

Also verify legacy `reference_id/title/source_url` input remains accepted.

- [x] **Step 3: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/rag/test_contracts.py -q
```

- [x] **Step 4: Implement canonical contracts**

Use `AliasChoices` for legacy input names and serialize canonical names. Define LegalDocument and LegalSection with source/version/effective-date metadata and non-empty content.

- [x] **Step 5: Verify GREEN**

Run contract tests.

---

### Task 2: Deterministic Chroma retriever and citation guard

**Files:**
- Create: `implicit-ad-agent/impad/rag/embeddings.py`
- Create: `implicit-ad-agent/impad/rag/chroma_retriever.py`
- Create: `implicit-ad-agent/tests/rag/test_chroma_retriever.py`

**Interfaces:**
- Produces: `DeterministicHashEmbedding`, `ChromaLegalRetriever`, `CitationGuard`.

- [x] **Step 1: Write failing tests**

Verify:

- embeddings are deterministic and normalized;
- indexing the same sections twice is idempotent;
- a direct query retrieves the expected source/article;
- no-match query returns an empty list at the configured threshold;
- every citation quote exactly equals an indexed section;
- no network-facing embedding function is invoked.

- [x] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/rag/test_chroma_retriever.py -q
```

- [x] **Step 3: Implement retriever**

Use a fixed-dimensional signed hashing vector over normalized Chinese character unigrams and bigrams. Create an EphemeralClient with anonymized telemetry disabled. Supply embeddings explicitly on upsert and query. Convert distance to a bounded retrieval score and apply a configurable minimum score.

- [x] **Step 4: Verify GREEN**

Run Chroma retriever tests.

---

### Task 3: 30-question benchmark

**Files:**
- Create: `implicit-ad-agent/tests/fixtures/legal_rag_documents.json`
- Create: `implicit-ad-agent/tests/fixtures/legal_rag_eval_30.json`
- Create: `implicit-ad-agent/impad/rag/evaluation.py`
- Create: `implicit-ad-agent/tests/rag/test_evaluation.py`

**Interfaces:**
- Produces: `LegalRetrievalQuestion`, `LegalRetrievalMetrics`, `evaluate_retriever()`.

- [x] **Step 1: Create fixture and failing tests**

Create exactly:

- 10 direct-clause questions with one or more expected article IDs;
- 10 cross-document questions with expected source IDs from two documents;
- 10 abstention questions with no expected sources.

Tests verify exact category counts, unique IDs, fixture source references, Recall@5 calculation, and no-answer false-citation rate.

- [x] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/rag/test_evaluation.py -q
```

- [x] **Step 3: Implement evaluator**

For answerable questions, compute set recall over expected source/article identifiers. For abstention questions, count any returned citation as a false citation. Return aggregate and per-category metrics without inventing answers.

- [x] **Step 4: Verify GREEN**

Run all RAG tests.

---

### Task 4: RAG module gate

- [x] **Step 1: Run RAG tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/rag -q
```

- [x] **Step 2: Run full suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- [x] **Step 3: Compile**

```powershell
.\.venv\Scripts\python.exe -m compileall -q impad/rag tests/rag
```

