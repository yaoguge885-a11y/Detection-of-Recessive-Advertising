# P5.1 Batch and URL Service Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded batch analysis and a safe, adapter-driven URL preview/confirm workflow while preserving the single `AnalysisService` path and zero-network defaults.

**Architecture:** `AnalysisService.analyze_batch()` isolates item failures but delegates every successful item to `analyze()`. A new `impad.adapters.platforms` package validates URLs, resolves explicit adapters, stores bounded process-local previews, applies allowlisted corrections, and calls the same analysis service only after confirmation. The default adapter registry remains empty until P5.3/P5.4.

**Tech Stack:** Python 3.10, Pydantic v2, FastAPI, pytest, standard-library `urllib.parse`, `ipaddress`, `hashlib`, and `collections.OrderedDict`.

## Global Constraints

- Default validation remains zero-key and zero-network.
- Batch size is 1-50 and processing is sequential.
- Batch item failures are isolated and expose only safe error summaries.
- URL import accepts HTTPS only and fails closed for unsafe or unsupported destinations.
- Query/fragment values must not enter preview responses, run records, fixtures, or documentation.
- Preview does not analyze; confirmation consumes the preview only after successful analysis.
- Live Xiaohongshu/Bilibili adapters, Web, A2A, and M5 passage remain out of scope.
- Formal M1 and M4 remain incomplete.

---

### Task 1: Batch analysis service

**Files:**
- Modify: `implicit-ad-agent/impad/services/analyze.py`
- Modify: `implicit-ad-agent/impad/services/__init__.py`
- Modify: `implicit-ad-agent/tests/services/test_analysis_service.py`

**Interfaces:**
- Consumes: `AnalysisService.analyze(post, runtime_mode=...)`.
- Produces:
  - `BATCH_MAX_ITEMS = 50`;
  - `BatchAnalysisInput(post, runtime_mode)`;
  - `BatchAnalysisError(code, message)`;
  - `BatchAnalysisItem(index, result, error)`;
  - `BatchAnalysisResult(total, succeeded, failed, items)`;
  - `AnalysisService.analyze_batch(items)`.

- [ ] **Step 1: Write failing service tests**

Add tests that prove delegation, order, isolation, safe error text, and direct
service bounds:

```python
def test_batch_analysis_reuses_single_analysis_and_preserves_order(
    tmp_path,
):
    service = _service(tmp_path)
    items = [
        BatchAnalysisInput(post={"text": "普通记录"}),
        BatchAnalysisInput(post={"text": "品牌合作，广告"}),
    ]

    result = service.analyze_batch(items)

    assert result.total == 2
    assert result.succeeded == 2
    assert result.failed == 0
    assert [item.index for item in result.items] == [0, 1]
    assert all(item.result is not None for item in result.items)
    assert len({
        item.result.run_metadata.run_id for item in result.items
    }) == 2


def test_batch_analysis_isolates_invalid_input(tmp_path):
    service = _service(tmp_path)
    result = service.analyze_batch([
        BatchAnalysisInput(post={
            "post_id": "target",
            "creator_id": "creator-a",
            "text": "invalid",
            "published_at": "2026-07-30T00:00:00Z",
            "history": [{
                "post_id": "history",
                "creator_id": "creator-b",
                "text": "other creator",
                "published_at": "2026-07-29T00:00:00Z",
            }],
        }),
        BatchAnalysisInput(post={"text": "valid"}),
    ])

    assert result.failed == 1
    assert result.succeeded == 1
    assert result.items[0].error.code == "invalid_input"
    assert result.items[0].error.message == (
        "Input could not be normalized."
    )
    assert result.items[1].result is not None


@pytest.mark.parametrize("count", [0, 51])
def test_batch_analysis_rejects_out_of_bounds_count(tmp_path, count):
    service = _service(tmp_path)
    with pytest.raises(ValueError, match="between 1 and 50"):
        service.analyze_batch([
            BatchAnalysisInput(post={"text": str(index)})
            for index in range(count)
        ])
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
cd implicit-ad-agent
.\.venv\Scripts\python.exe -m pytest `
  tests\services\test_analysis_service.py -q
```

Expected: import/attribute failures for the missing batch contracts and method.

- [ ] **Step 3: Implement minimal batch contracts and delegation**

In `services/analyze.py`, add Pydantic contracts and the method:

```python
BATCH_MAX_ITEMS = 50


class BatchAnalysisInput(BaseModel):
    post: dict | PostRecord
    runtime_mode: RuntimeMode = "local"


class BatchAnalysisError(BaseModel):
    code: Literal["invalid_input", "analysis_failed"]
    message: str


class BatchAnalysisItem(BaseModel):
    index: int = Field(ge=0)
    result: AnalysisResult | None = None
    error: BatchAnalysisError | None = None

    @model_validator(mode="after")
    def exactly_one_outcome(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("batch item requires exactly one outcome")
        return self


class BatchAnalysisResult(BaseModel):
    total: int = Field(ge=1, le=BATCH_MAX_ITEMS)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    items: list[BatchAnalysisItem]


def _safe_batch_error(exc: Exception) -> BatchAnalysisError:
    if isinstance(exc, (ValueError, ValidationError)):
        return BatchAnalysisError(
            code="invalid_input",
            message="Input could not be normalized.",
        )
    return BatchAnalysisError(
        code="analysis_failed",
        message="Analysis failed.",
    )
```

Add to `AnalysisService`:

```python
def analyze_batch(
    self,
    items: list[BatchAnalysisInput],
) -> BatchAnalysisResult:
    if not 1 <= len(items) <= BATCH_MAX_ITEMS:
        raise ValueError("batch size must be between 1 and 50")
    outcomes = []
    for index, item in enumerate(items):
        try:
            result = self.analyze(
                item.post,
                runtime_mode=item.runtime_mode,
            )
            outcomes.append(BatchAnalysisItem(
                index=index,
                result=result,
            ))
        except Exception as exc:
            outcomes.append(BatchAnalysisItem(
                index=index,
                error=_safe_batch_error(exc),
            ))
    succeeded = sum(item.result is not None for item in outcomes)
    return BatchAnalysisResult(
        total=len(outcomes),
        succeeded=succeeded,
        failed=len(outcomes) - succeeded,
        items=outcomes,
    )
```

Export the new contracts from `services/__init__.py`.

- [ ] **Step 4: Run service tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\services\test_analysis_service.py -q
```

Expected: all service tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- `
  implicit-ad-agent/impad/services/analyze.py `
  implicit-ad-agent/impad/services/__init__.py `
  implicit-ad-agent/tests/services/test_analysis_service.py
git diff --cached --check
git commit -m "feat: add isolated batch analysis service"
```

---

### Task 2: Batch HTTP API

**Files:**
- Modify: `implicit-ad-agent/impad/api/schemas.py`
- Modify: `implicit-ad-agent/impad/api/routes.py`
- Modify: `implicit-ad-agent/impad/api/__init__.py`
- Modify: `implicit-ad-agent/tests/api/test_routes.py`

**Interfaces:**
- Consumes: Task 1 batch contracts and `AnalysisService.analyze_batch()`.
- Produces:
  - `BatchAnalyzeRequest(items)`;
  - `BatchAnalyzeItemResponse(index, ok, result, error)`;
  - `BatchAnalyzeResponse(total, succeeded, failed, items)`;
  - `POST /api/v1/analyze/batch`.

- [ ] **Step 1: Write failing API tests**

```python
def test_batch_route_returns_per_item_outcomes(tmp_path):
    client = _client(tmp_path)
    response = client.post("/api/v1/analyze/batch", json={
        "items": [
            {"text": "普通记录"},
            {"text": "品牌合作，广告", "capture_complete": True},
        ]
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["succeeded"] == 2
    assert payload["failed"] == 0
    assert [item["index"] for item in payload["items"]] == [0, 1]
    assert all(item["ok"] for item in payload["items"])


@pytest.mark.parametrize("items", [[], [{"text": "x"}] * 51])
def test_batch_route_rejects_invalid_size(tmp_path, items):
    response = _client(tmp_path).post(
        "/api/v1/analyze/batch",
        json={"items": items},
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\api\test_routes.py -q
```

Expected: `404` for the missing batch route.

- [ ] **Step 3: Add request/response models and route**

In `api/schemas.py`:

```python
class BatchAnalyzeRequest(BaseModel):
    items: list[AnalyzeRequest] = Field(
        min_length=1,
        max_length=BATCH_MAX_ITEMS,
    )


class BatchAnalyzeItemResponse(BaseModel):
    index: int
    ok: bool
    result: AnalyzeResponse | None = None
    error: BatchAnalysisError | None = None


class BatchAnalyzeResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    items: list[BatchAnalyzeItemResponse]
```

Add a private conversion helper that builds `AnalyzeResponse` from one
`AnalysisResult`, and reuse it in both single and batch routes.

In `api/routes.py`:

```python
@router.post("/analyze/batch", response_model=BatchAnalyzeResponse)
def analyze_batch(request: BatchAnalyzeRequest):
    batch = active_service().analyze_batch([
        BatchAnalysisInput(
            post=item.post_payload(),
            runtime_mode=item.runtime_mode,
        )
        for item in request.items
    ])
    return BatchAnalyzeResponse(
        total=batch.total,
        succeeded=batch.succeeded,
        failed=batch.failed,
        items=[
            BatchAnalyzeItemResponse(
                index=item.index,
                ok=item.result is not None,
                result=(
                    _analyze_response(item.result)
                    if item.result is not None
                    else None
                ),
                error=item.error,
            )
            for item in batch.items
        ],
    )
```

Export the public API models from `api/__init__.py`.

- [ ] **Step 4: Run API and service tests**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\api\test_routes.py `
  tests\services\test_analysis_service.py -q
```

Expected: all tests pass and the original single-item route remains green.

- [ ] **Step 5: Commit**

```powershell
git add -- `
  implicit-ad-agent/impad/api `
  implicit-ad-agent/tests/api/test_routes.py
git diff --cached --check
git commit -m "feat: expose bounded batch analysis API"
```

---

### Task 3: URL safety and adapter registry

**Files:**
- Create: `implicit-ad-agent/impad/adapters/platforms/__init__.py`
- Create: `implicit-ad-agent/impad/adapters/platforms/contracts.py`
- Create: `implicit-ad-agent/impad/adapters/platforms/url_safety.py`
- Create: `implicit-ad-agent/impad/adapters/platforms/registry.py`
- Create: `implicit-ad-agent/tests/adapters/platforms/__init__.py`
- Create: `implicit-ad-agent/tests/adapters/platforms/test_url_safety.py`
- Create: `implicit-ad-agent/tests/adapters/platforms/test_registry.py`

**Interfaces:**
- Produces:
  - `ValidatedSourceURL(fetch_url, display_url, hostname, source_ref_hash,
    sensitive_tokens)`;
  - `validate_public_https_url(url)`;
  - `PlatformAdapter` protocol;
  - `PlatformAdapterRegistry.resolve(source)`;
  - `URLImportError(code, message, status_code)`.

- [ ] **Step 1: Write failing URL safety tests**

```python
@pytest.mark.parametrize("url", [
    "http://example.test/post/1",
    "https://user:pass@example.test/post/1",
    "https://example.test:8443/post/1",
    "https://localhost/post/1",
    "https://service.internal/post/1",
    "https://127.0.0.1/post/1",
    "https://10.0.0.1/post/1",
    "https://169.254.1.1/post/1",
    "https://[::1]/post/1",
])
def test_url_validator_rejects_unsafe_destinations(url):
    with pytest.raises(URLImportError, match="URL"):
        validate_public_https_url(url)


def test_url_validator_keeps_fetch_query_but_hides_display_query():
    result = validate_public_https_url(
        "https://EXAMPLE.test/post/1?token=secret#fragment"
    )

    assert result.fetch_url == (
        "https://example.test/post/1?token=secret"
    )
    assert result.display_url == "https://example.test/post/1"
    assert result.hostname == "example.test"
    assert len(result.source_ref_hash) == 64
    assert result.sensitive_tokens == ("token=secret", "fragment")
```

- [ ] **Step 2: Write failing registry tests**

```python
class StaticAdapter:
    name = "static"
    version = "1"
    platform = "fixture"
    supported_hosts = ("example.test",)

    def preview(self, source):
        raise AssertionError("not used by registry resolution")


def test_registry_matches_exact_host_and_subdomain():
    registry = PlatformAdapterRegistry([StaticAdapter()])
    assert registry.resolve(
        validate_public_https_url("https://example.test/a")
    ).name == "static"
    assert registry.resolve(
        validate_public_https_url("https://www.example.test/a")
    ).name == "static"


def test_registry_rejects_unsupported_host():
    registry = PlatformAdapterRegistry([StaticAdapter()])
    with pytest.raises(
        URLImportError,
        match="No registered platform adapter",
    ):
        registry.resolve(
            validate_public_https_url("https://other.test/a")
        )
```

- [ ] **Step 3: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\adapters\platforms -q
```

Expected: imports fail because `impad.adapters.platforms` does not exist.

- [ ] **Step 4: Implement URL contracts and validator**

In `contracts.py`:

```python
@dataclass(frozen=True)
class ValidatedSourceURL:
    fetch_url: str
    display_url: str
    hostname: str
    source_ref_hash: str
    sensitive_tokens: tuple[str, ...] = ()


class URLImportError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 422,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class PlatformAdapter(Protocol):
    name: str
    version: str
    platform: str
    supported_hosts: tuple[str, ...]

    def preview(self, source: ValidatedSourceURL) -> PostRecord:
        ...
```

In `url_safety.py`, use `urlsplit`, IDNA host normalization, `ip_address`,
and `urlunsplit`. Hash the fragment-free fetch URL with SHA-256. Reject
non-HTTPS, credentials, non-443 ports, forbidden local suffixes, and IP
literals where `is_global` is false.

- [ ] **Step 5: Implement registry**

```python
class PlatformAdapterRegistry:
    def __init__(
        self,
        adapters: Iterable[PlatformAdapter] = (),
    ):
        self._adapters = tuple(adapters)
        claimed = {}
        for adapter in self._adapters:
            for host in adapter.supported_hosts:
                normalized = host.lower().rstrip(".")
                if normalized in claimed:
                    raise ValueError(
                        f"duplicate platform host: {normalized}"
                    )
                claimed[normalized] = adapter
        self._claimed_hosts = claimed

    def resolve(
        self,
        source: ValidatedSourceURL,
    ) -> PlatformAdapter:
        matches = [
            (host, adapter)
            for host, adapter in self._claimed_hosts.items()
            if (
                source.hostname == host
                or source.hostname.endswith("." + host)
            )
        ]
        if not matches:
            raise URLImportError(
                "unsupported_url_host",
                "No registered platform adapter supports this URL.",
            )
        return max(matches, key=lambda item: len(item[0]))[1]

    @property
    def adapters(self) -> tuple[PlatformAdapter, ...]:
        return self._adapters
```

Export the public symbols from `platforms/__init__.py`.

- [ ] **Step 6: Run platform adapter tests**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\adapters\platforms -q
```

Expected: all URL and registry tests pass without network access.

- [ ] **Step 7: Commit**

```powershell
git add -- `
  implicit-ad-agent/impad/adapters/platforms `
  implicit-ad-agent/tests/adapters/platforms
git diff --cached --check
git commit -m "feat: add safe platform adapter boundary"
```

---

### Task 4: URL preview and confirmation service

**Files:**
- Create: `implicit-ad-agent/impad/adapters/platforms/url_import.py`
- Modify: `implicit-ad-agent/impad/adapters/platforms/contracts.py`
- Modify: `implicit-ad-agent/impad/adapters/platforms/__init__.py`
- Create: `implicit-ad-agent/tests/adapters/platforms/test_url_import.py`

**Interfaces:**
- Consumes: Task 1 `AnalysisService`; Task 3 validator and registry.
- Produces:
  - `URLImportPreview`;
  - `URLImportCorrections`;
  - `InMemoryURLPreviewStore`;
  - `URLImportService.preview(url)`;
  - `URLImportService.confirm(preview_id, corrections, runtime_mode)`.

- [ ] **Step 1: Write failing preview tests**

Create a static adapter whose `preview()` returns a complete deterministic
`PostRecord` with no source URL text:

```python
def test_preview_normalizes_source_without_running_analysis(tmp_path):
    analysis = _analysis_service(tmp_path)
    adapter = StaticAdapter()
    service = URLImportService(
        analysis_service=analysis,
        registry=PlatformAdapterRegistry([adapter]),
    )

    preview = service.preview(
        "https://example.test/post/1?token=secret#fragment"
    )

    assert preview.display_url == "https://example.test/post/1"
    assert preview.post.provenance.source_ref_hash == (
        preview.source_ref_hash
    )
    assert preview.post.capture_status.adapter_version == adapter.version
    assert "token=secret" not in preview.model_dump_json()
    assert analysis.get_run("missing") is None
```

Also assert an unsupported host does not call the adapter.

- [ ] **Step 2: Write failing confirmation tests**

```python
def test_confirm_applies_audited_corrections_and_consumes_preview(
    tmp_path,
):
    service = _url_service(tmp_path)
    preview = service.preview("https://example.test/post/1")

    result = service.confirm(
        preview.preview_id,
        URLImportCorrections(text="人工修正后的正文"),
        runtime_mode="local",
    )

    assert result.post.text == "人工修正后的正文"
    assert "text" in result.post.capture_status.user_corrections
    assert service.analysis_service.get_run(
        result.run_metadata.run_id
    ) is not None
    with pytest.raises(URLImportError) as exc:
        service.confirm(
            preview.preview_id,
            URLImportCorrections(),
        )
    assert exc.value.code == "preview_not_found"


def test_invalid_correction_does_not_consume_preview(tmp_path):
    service = _url_service(tmp_path)
    preview = service.preview("https://example.test/post/1")

    with pytest.raises(URLImportError) as exc:
        service.confirm(
            preview.preview_id,
            URLImportCorrections(
                creator_id="different",
            ),
        )
    assert exc.value.code == "invalid_corrections"

    result = service.confirm(
        preview.preview_id,
        URLImportCorrections(),
    )
    assert result.run_metadata.run_id
```

- [ ] **Step 3: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\adapters\platforms\test_url_import.py -q
```

Expected: import failures for the missing preview service/contracts.

- [ ] **Step 4: Implement preview/correction contracts**

In `contracts.py`:

```python
class URLImportPreview(BaseModel):
    preview_id: str = Field(pattern=r"^preview_[0-9a-f]{32}$")
    platform: str
    adapter_name: str
    adapter_version: str
    display_url: str
    source_ref_hash: str = Field(min_length=64, max_length=64)
    created_at: datetime
    post: PostRecord


class URLImportCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = None
    creator_id: str | None = None
    published_at: datetime | None = None
    media: list[MediaRecord] | None = None
    comments: list[CommentRecord] | None = None
    history: list[HistoryPost] | None = None
    capture_status: CaptureStatus | None = None
```

Use `model_fields_set` so omitted fields differ from explicitly supplied
`null`.

- [ ] **Step 5: Implement bounded preview store**

```python
class InMemoryURLPreviewStore:
    def __init__(self, *, max_entries: int = 100):
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._records = OrderedDict()

    def put(self, preview: URLImportPreview) -> None:
        self._records[preview.preview_id] = preview
        self._records.move_to_end(preview.preview_id)
        while len(self._records) > self.max_entries:
            self._records.popitem(last=False)

    def get(self, preview_id: str) -> URLImportPreview | None:
        return self._records.get(preview_id)

    def delete(self, preview_id: str) -> None:
        self._records.pop(preview_id, None)
```

- [ ] **Step 6: Implement URL import orchestration**

Use this constructor so the API can inspect the same registry used by the
workflow:

```python
class URLImportService:
    def __init__(
        self,
        *,
        analysis_service: AnalysisService,
        registry: PlatformAdapterRegistry | None = None,
        preview_store: InMemoryURLPreviewStore | None = None,
    ):
        self.analysis_service = analysis_service
        self.registry = registry or PlatformAdapterRegistry()
        self.preview_store = (
            preview_store or InMemoryURLPreviewStore()
        )
```

`URLImportService.preview()` must:

1. validate the URL;
2. resolve the adapter before calling it;
3. validate the returned `PostRecord`;
4. reject the record if any sensitive query/fragment token appears in its
   serialized content;
5. replace provenance `source_ref_hash` with the validator hash;
6. record the adapter version in `CaptureStatus`;
7. store and return the preview.

`confirm()` must build a fresh payload, apply only fields present in
`corrections.model_fields_set`, append sorted changed fields to
`user_corrections`, call `PostRecord.model_validate()`, call
`analysis_service.analyze()`, and delete the preview only after success.
Convert validation failures to:

```python
URLImportError(
    "invalid_corrections",
    "URL preview corrections are invalid.",
)
```

- [ ] **Step 7: Run URL import tests**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\adapters\platforms -q
```

Expected: all platform adapter tests pass.

- [ ] **Step 8: Commit**

```powershell
git add -- `
  implicit-ad-agent/impad/adapters/platforms `
  implicit-ad-agent/tests/adapters/platforms
git diff --cached --check
git commit -m "feat: add audited URL preview and confirm service"
```

---

### Task 5: URL HTTP API and capabilities

**Files:**
- Modify: `implicit-ad-agent/impad/api/schemas.py`
- Modify: `implicit-ad-agent/impad/api/routes.py`
- Modify: `implicit-ad-agent/impad/api/__init__.py`
- Modify: `implicit-ad-agent/app.py`
- Modify: `implicit-ad-agent/tests/api/test_routes.py`

**Interfaces:**
- Consumes: Task 4 `URLImportService`.
- Produces:
  - `URLPreviewRequest(url)`;
  - `URLPreviewResponse`;
  - `URLConfirmRequest(preview_id, corrections, runtime_mode)`;
  - preview/confirm endpoints;
  - capability metadata.

- [ ] **Step 1: Write failing route tests**

Inject a `URLImportService` with the static adapter into `create_app()`:

```python
def test_url_preview_and_confirm_routes(tmp_path):
    client = _url_client(tmp_path)
    preview_response = client.post(
        "/api/v1/import/url/preview",
        json={
            "url": (
                "https://example.test/post/1"
                "?token=secret#fragment"
            )
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["display_url"] == (
        "https://example.test/post/1"
    )
    assert "secret" not in preview_response.text

    confirmed = client.post(
        "/api/v1/import/url/confirm",
        json={
            "preview_id": preview["preview_id"],
            "corrections": {"text": "人工修正"},
            "runtime_mode": "local",
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["run_metadata"]["run_id"]


def test_default_app_rejects_unsupported_url_before_fetch():
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/import/url/preview",
        json={"url": "https://example.test/post/1"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == (
        "unsupported_url_host"
    )
```

Add tests for `preview_not_found` (`404`), invalid corrections (`422`), and
capabilities listing only the injected adapter.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\api\test_routes.py -q
```

Expected: missing endpoint and `create_app()` parameter failures.

- [ ] **Step 3: Add API models and route injection**

In `api/schemas.py`:

```python
class URLPreviewRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)


class URLPreviewResponse(URLImportPreview):
    pass


class URLConfirmRequest(BaseModel):
    preview_id: str = Field(pattern=r"^preview_[0-9a-f]{32}$")
    corrections: URLImportCorrections = Field(
        default_factory=URLImportCorrections
    )
    runtime_mode: Literal["local", "mcp"] = "local"
```

Update:

```python
def create_api_router(
    service: AnalysisService | None = None,
    url_import_service: URLImportService | None = None,
) -> APIRouter:
```

Resolve both services once at router construction so preview and confirmation
share one process-local store. If no URL service is injected, construct one
with an empty `PlatformAdapterRegistry`.

- [ ] **Step 4: Implement endpoints and safe error mapping**

```python
def _raise_url_error(exc: URLImportError):
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


@router.post(
    "/import/url/preview",
    response_model=URLPreviewResponse,
)
def preview_url(request: URLPreviewRequest):
    try:
        return active_url_service().preview(request.url)
    except URLImportError as exc:
        _raise_url_error(exc)


@router.post(
    "/import/url/confirm",
    response_model=AnalyzeResponse,
)
def confirm_url(request: URLConfirmRequest):
    try:
        result = active_url_service().confirm(
            request.preview_id,
            request.corrections,
            runtime_mode=request.runtime_mode,
        )
    except URLImportError as exc:
        _raise_url_error(exc)
    return _analyze_response(result)
```

Extend capabilities with:

```python
"batch_analysis": {"enabled": True, "max_items": 50},
"url_import": {
    "enabled": True,
    "workflow": ["preview", "confirm"],
    "platforms": [
        {
            "platform": adapter.platform,
            "adapter": adapter.name,
            "version": adapter.version,
            "hosts": list(adapter.supported_hosts),
        }
        for adapter in url_service.registry.adapters
    ],
},
```

Update `create_app()` to accept/pass `url_import_service`.

- [ ] **Step 5: Run API, service, and adapter tests**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\api `
  tests\services `
  tests\adapters\platforms -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add -- `
  implicit-ad-agent/impad/api `
  implicit-ad-agent/app.py `
  implicit-ad-agent/tests/api/test_routes.py
git diff --cached --check
git commit -m "feat: expose URL preview and confirm API"
```

---

### Task 6: Security and compatibility regression

**Files:**
- Modify: `implicit-ad-agent/tests/api/test_routes.py`
- Modify: `implicit-ad-agent/tests/adapters/platforms/test_url_import.py`
- Create: `implicit-ad-agent/tests/test_app.py`

**Interfaces:**
- Verifies all prior tasks and the unchanged compatibility routes.

- [ ] **Step 1: Add explicit secret and immutability tests**

Assert:

- a query value such as `api_key=do-not-store` is absent from preview JSON,
  `RunRecord.model_dump_json()`, and readable report;
- correction JSON cannot contain `post_id`, `platform`, `provenance`,
  `privacy`, or unknown fields;
- an adapter that copies a query/fragment token into a `PostRecord` is rejected
  with `adapter_failed`;
- preview IDs are not consumed after invalid corrections.

- [ ] **Step 2: Add compatibility tests**

Verify:

```python
def test_existing_health_and_compatibility_analyze_remain_available(
    tmp_path,
):
    client = _client(tmp_path)
    assert client.get("/health").status_code == 200
    assert client.post(
        "/analyze",
        json={"text": "普通记录"},
    ).status_code == 200
    assert client.post(
        "/api/v1/analyze",
        json={"text": "普通记录"},
    ).status_code == 200
```

- [ ] **Step 3: Run the focused P5.1 gate**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\api `
  tests\services `
  tests\adapters\platforms `
  tests\test_app.py -q
```

Expected: all focused tests pass with no network access.

- [ ] **Step 4: Commit**

```powershell
git add -- `
  implicit-ad-agent/tests/api `
  implicit-ad-agent/tests/services `
  implicit-ad-agent/tests/adapters/platforms `
  implicit-ad-agent/tests/test_app.py
git diff --cached --check
git commit -m "test: close P5 service security coverage"
```

---

### Task 7: Documentation synchronization and completion gate

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/已有功能测试指令库.md`
- Modify: `docs/隐性广告识别项目_分阶段计划表.md`
- Modify: `docs/隐性广告识别项目_说明书.md`
- Modify: `docs/superpowers/specs/2026-07-30-p5-service-admission-design.md`
- Modify: `docs/superpowers/plans/2026-07-30-p5-service-admission.md`

**Interfaces:**
- Consumes: verified implementation and exact command output.
- Produces: current-state handoff, copyable commands, explicit P5.1 and
  incomplete P5.2-P5.7/M1/M4 boundaries.

- [ ] **Step 1: Update factual status**

Record:

- the bounded batch endpoint and per-item isolation;
- URL safety, adapter registry, preview/confirm, correction audit, and default
  empty registry;
- exact focused/full counts from fresh output;
- that no live platform URL adapter, Web, A2A, real URL integration, or M5
  acceptance has been completed.

- [ ] **Step 2: Add copyable test commands**

Add commands for:

- batch and URL focused tests;
- default unsupported-host behavior;
- URL security matrix;
- query/fragment secret scan;
- full default regression;
- both P1 validators.

- [ ] **Step 3: Run dependency and compilation checks**

```powershell
cd implicit-ad-agent
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q `
  impad tests scripts app.py run_demo.py run_tools_demo.py
```

- [ ] **Step 4: Run focused and full tests**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\api `
  tests\services `
  tests\adapters\platforms `
  tests\test_app.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

- [ ] **Step 5: Run both P1 validators**

From the repository root:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe `
  scripts\data\validate_submission_assets.py
.\implicit-ad-agent\.venv\Scripts\python.exe `
  data-tooling\validate_submission_assets.py
```

Both must output `VALIDATION PASSED`.

- [ ] **Step 6: Run security and repository scans**

```powershell
rg -n `
  "api_key=do-not-store|token=secret|#fragment" `
  . `
  -g "!docs/superpowers/plans/2026-07-30-p5-service-admission.md" `
  -g "!implicit-ad-agent/tests/**"
git diff --check
```

The secret scan must find no runtime artifact, fixture, report, or user-facing
documentation occurrence. Test inputs and the implementation plan are explicit
exceptions.

- [ ] **Step 7: Review the cumulative diff**

Compare every acceptance criterion in the design against production code,
tests, HTTP behavior, docs, and current command output. Fix every Critical or
Important issue and rerun the affected gate.

- [ ] **Step 8: Commit factual documentation**

```powershell
git add -- `
  HANDOFF.md `
  docs/已有功能测试指令库.md `
  docs/隐性广告识别项目_分阶段计划表.md `
  docs/隐性广告识别项目_说明书.md `
  docs/superpowers/specs/2026-07-30-p5-service-admission-design.md `
  docs/superpowers/plans/2026-07-30-p5-service-admission.md
git diff --cached --check
git commit -m "docs: record P5 service admission"
```

- [ ] **Step 9: Final repository audit**

```powershell
git status --short --branch
git log -12 --oneline
git diff --check
```

Completion requires a clean worktree, all plan checkboxes complete, direct
evidence for every design acceptance criterion, synchronized required
documents, and explicit incomplete P5.2-P5.7/M1/M4 boundaries.
