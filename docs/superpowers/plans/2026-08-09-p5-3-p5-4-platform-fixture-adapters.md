# P5.3/P5.4 Platform Synthetic Fixture Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic, zero-network Xiaohongshu and Bilibili synthetic-fixture adapters that emit one audited `PostRecord + CaptureStatus` contract, support disclosure correction, and preserve the real-platform approval boundary.

**Architecture:** Platform-specific parsers decode minimal synthetic HTML/embedded JSON into a strict shared `ParsedPlatformPost`. A shared builder creates `PostRecord`; the existing `URLImportService` owns source-hash normalization, preview, correction, and confirm. The default registry remains empty, so only tests with an injected fixture fetcher can invoke these adapters.

**Tech Stack:** Python 3.10+, Pydantic v2, pytest, FastAPI schemas, browser-free JavaScript workbench tests, standard-library JSON/HTML string parsing.

## Global Constraints

- First fixtures are structural synthetic data and must not be described as real-page captures.
- Cover Xiaohongshu `normal` and `video`; cover Bilibili `video`, `opus`, and `article`.
- Preserve `partial`; add `unsupported`; the four platform modalities are `text`, `image`, `comment`, and `disclosure`.
- A remote image reference without a safe local file is `partial`, never `complete`.
- Fixtures must contain non-empty anonymized `post_id` and `creator_id`; never generate unknown identity placeholders.
- Do not import the crawler modules or add Playwright, Cookie, captcha, login, comment-API, media-download, or live-network behavior.
- Do not register either adapter in the default application registry.
- Preserve unrelated dirty-worktree changes. Execute in the current checkout; do not create a worktree that omits them.
- Tests demonstrate only synthetic fixture engineering behavior, not real-platform compatibility, terms approval, M5, A2A, or research validity.

---

## File Structure

**Create production files:**

- `implicit-ad-agent/impad/adapters/platforms/embedded_json.py` — string-aware extraction of assigned embedded JSON.
- `implicit-ad-agent/impad/adapters/platforms/normalization.py` — strict shared platform payload and PostRecord builder.
- `implicit-ad-agent/impad/adapters/platforms/xiaohongshu.py` — Xiaohongshu state parser and adapter.
- `implicit-ad-agent/impad/adapters/platforms/bilibili.py` — Bilibili state parser, content-type routing, and adapter.

**Create tests:**

- `implicit-ad-agent/tests/adapters/platforms/test_platform_contract_extensions.py`
- `implicit-ad-agent/tests/adapters/platforms/test_embedded_json.py`
- `implicit-ad-agent/tests/adapters/platforms/test_platform_normalization.py`
- `implicit-ad-agent/tests/adapters/platforms/test_xiaohongshu.py`
- `implicit-ad-agent/tests/adapters/platforms/test_bilibili.py`
- `implicit-ad-agent/tests/adapters/platforms/test_fixture_governance.py`

**Create fixture case directories:**

- `implicit-ad-agent/tests/fixtures/platforms/xiaohongshu/normal_complete/`
- `implicit-ad-agent/tests/fixtures/platforms/xiaohongshu/video_missing_comments/`
- `implicit-ad-agent/tests/fixtures/platforms/bilibili/video_no_images/`
- `implicit-ad-agent/tests/fixtures/platforms/bilibili/opus_partial_images/`
- `implicit-ad-agent/tests/fixtures/platforms/bilibili/article_missing_disclosure_surface/`

Each case contains `source.html`, `source_state.json`, `manifest.json`, and `expected_post.json`.

**Modify existing files:**

- `implicit-ad-agent/impad/contracts/post.py:16-113` — capture enums, `DisclosureRecord`, and `PostRecord.disclosures`.
- `implicit-ad-agent/impad/contracts/evidence.py:12-15` — disclosure modality and unsupported coverage.
- `implicit-ad-agent/impad/contracts/__init__.py:9-47` — export `DisclosureRecord`.
- `implicit-ad-agent/impad/adapters/platforms/contracts.py:10-92` — allow disclosure corrections.
- `implicit-ad-agent/impad/adapters/platforms/__init__.py:1-43` — export both adapters.
- `implicit-ad-agent/impad/orchestration/evidence_adapters.py:32-44,177-229` — map new modality/status.
- `implicit-ad-agent/impad/orchestration/adequacy.py:63-113` — fail conservatively for unsupported text and ignore unsupported image as provided image evidence.
- `implicit-ad-agent/impad/web/index.html:99-112` — disclosure JSON editor.
- `implicit-ad-agent/impad/web/workbench.js:186-207` — fill and submit disclosure corrections.
- `implicit-ad-agent/tests/contracts/test_post_record.py` — strict disclosure contract regression.
- `implicit-ad-agent/tests/adapters/platforms/test_url_import.py` — disclosure correction audit.
- `implicit-ad-agent/tests/api/test_routes.py` — API allowlist regression.
- `implicit-ad-agent/tests/orchestration/test_evidence_adapters.py` — coverage mapping.
- `implicit-ad-agent/tests/orchestration/test_adequacy.py` — unsupported-state adequacy.
- `implicit-ad-agent/tests/web/workbench_behavior.test.cjs:153-175` — disclosure editor behavior.
- `implicit-ad-agent/tests/web/test_workbench.py` — rendered field presence.
- `docs/隐性广告识别项目_分阶段计划表.md:159-173` — verified synthetic-fixture status only.
- `HANDOFF.md:94-104,307-317` — handoff and remaining real-platform boundary.
- `docs/已有功能测试指令库.md:34-48` — focused verification commands and claims boundary.

---

### Task 1: Extend Capture, Disclosure, and Evidence Coverage Contracts

**Files:**

- Modify: `implicit-ad-agent/impad/contracts/post.py:16-113`
- Modify: `implicit-ad-agent/impad/contracts/evidence.py:12-15`
- Modify: `implicit-ad-agent/impad/contracts/__init__.py:9-47`
- Modify: `implicit-ad-agent/impad/orchestration/evidence_adapters.py:32-44,177-229`
- Modify: `implicit-ad-agent/impad/orchestration/adequacy.py:63-113`
- Test: `implicit-ad-agent/tests/adapters/platforms/test_platform_contract_extensions.py`
- Test: `implicit-ad-agent/tests/contracts/test_post_record.py`
- Test: `implicit-ad-agent/tests/orchestration/test_evidence_adapters.py`
- Test: `implicit-ad-agent/tests/orchestration/test_adequacy.py`

**Interfaces:**

- Produces: `DisclosureRecord(kind, text, source)`, `PostRecord.disclosures`, capture status `unsupported`, capture modality `disclosure`, evidence source `disclosure`, coverage status `unsupported`.
- Preserves: every existing manual/P1 PostRecord remains valid because `disclosures` defaults to an empty list.

- [ ] **Step 1: Write failing strict-contract tests**

Add tests equivalent to:

```python
from pydantic import ValidationError

from impad.contracts import DisclosureRecord
from impad.contracts.post import CaptureModality


def test_disclosure_record_is_strict_and_capture_supports_unsupported():
    marker = DisclosureRecord(
        kind="platform_badge",
        text="品牌合作",
        source="platform_metadata",
    )
    assert marker.text == "品牌合作"
    assert CaptureModality(status="unsupported").status == "unsupported"
    with pytest.raises(ValidationError):
        DisclosureRecord(
            kind="inferred_signal",
            text="可能是广告",
            source="classifier",
        )


def test_existing_manual_post_defaults_to_no_structured_disclosures():
    post = post_record_from_manual({"text": "普通记录"})
    assert post.disclosures == []
```

Add evidence/adequacy assertions:

```python
def test_disclosure_and_unsupported_capture_are_preserved_in_coverage():
    post = post_record_from_manual({"text": "普通记录"})
    post.capture_status.modalities["disclosure"] = CaptureModality(
        status="unsupported",
        issues=["disclosure_surface_unsupported"],
    )
    bundle = build_evidence_bundle(post, [])
    disclosure = next(
        item for item in bundle.coverage
        if item.modality == "disclosure"
    )
    assert disclosure.status == "unsupported"
    assert "capture:disclosure:unsupported" in bundle.missing_requirements


def test_unsupported_text_requires_review_but_unsupported_image_is_not_provided():
    post = post_record_from_manual({"text": "普通记录"})
    post.capture_status.modalities["text"] = CaptureModality(
        status="unsupported"
    )
    post.capture_status.modalities["image"] = CaptureModality(
        status="unsupported"
    )
    result = assess_evidence_adequacy(post, build_evidence_bundle(post, []))
    assert "text_capture_incomplete" in result.reason_codes
    assert "image_evidence_missing" not in result.reason_codes
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
cd implicit-ad-agent
python -m pytest tests/contracts/test_post_record.py tests/adapters/platforms/test_platform_contract_extensions.py tests/orchestration/test_evidence_adapters.py tests/orchestration/test_adequacy.py -q
```

Expected: failures because `DisclosureRecord`, `unsupported`, and `disclosure` do not exist.

- [ ] **Step 3: Implement the minimal contract extension**

Add strict literals and model:

```python
CaptureState = Literal[
    "complete", "partial", "missing", "unsupported", "not_applicable"
]
CaptureModalityName = Literal[
    "text", "image", "comment", "disclosure", "history", "metadata"
]
DisclosureKind = Literal[
    "platform_badge", "hashtag", "text_statement"
]
DisclosureSource = Literal["platform_metadata", "post_text"]


class DisclosureRecord(_StrictModel):
    kind: DisclosureKind
    text: str = Field(min_length=1)
    source: DisclosureSource
```

Add `disclosures: list[DisclosureRecord] = Field(default_factory=list)` immediately after `comments` in `PostRecord`, export it, then extend:

```python
EvidenceSourceType = Literal[
    "text", "image", "comment", "disclosure", "history", "metadata"
]
CoverageStatus = Literal[
    "covered", "partial", "missing", "unsupported", "not_applicable"
]

_CAPTURE_TO_COVERAGE["unsupported"] = "unsupported"
_MODALITY_MAP["disclosure"] = "disclosure"
```

Update `_missing_requirements` so `unsupported` is explicit:

```python
if capture.status not in {"partial", "missing", "unsupported"}:
    continue
```

Update adequacy conditions:

```python
if text_capture is None or text_capture.status in {
    "partial", "missing", "unsupported"
}:
    reasons.append("text_capture_incomplete")

image_was_provided = (
    image_capture is not None
    and image_capture.status not in {"not_applicable", "unsupported"}
)
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2. Expected: all selected tests pass with no warnings introduced by this task.

- [ ] **Step 5: Commit only Task 1 files**

```powershell
git add -- implicit-ad-agent/impad/contracts/post.py implicit-ad-agent/impad/contracts/evidence.py implicit-ad-agent/impad/contracts/__init__.py implicit-ad-agent/impad/orchestration/evidence_adapters.py implicit-ad-agent/impad/orchestration/adequacy.py implicit-ad-agent/tests/contracts/test_post_record.py implicit-ad-agent/tests/adapters/platforms/test_platform_contract_extensions.py implicit-ad-agent/tests/orchestration/test_evidence_adapters.py implicit-ad-agent/tests/orchestration/test_adequacy.py
git commit -m "feat: extend platform capture contracts"
```

---

### Task 2: Add String-Aware Embedded JSON Parsing and Shared Normalization

**Files:**

- Create: `implicit-ad-agent/impad/adapters/platforms/embedded_json.py`
- Create: `implicit-ad-agent/impad/adapters/platforms/normalization.py`
- Create: `implicit-ad-agent/tests/adapters/platforms/test_embedded_json.py`
- Create: `implicit-ad-agent/tests/adapters/platforms/test_platform_normalization.py`

**Interfaces:**

- Produces: `extract_assigned_json(html: str, marker: str) -> dict`.
- Produces: `ParsedPlatformPost` and `build_platform_post(payload, source_ref_hash, adapter_version) -> PostRecord`.
- Consumes: contract extensions from Task 1.

- [ ] **Step 1: Write failing embedded-JSON tests**

```python
from impad.adapters.platforms.embedded_json import extract_assigned_json


def test_extract_assigned_json_handles_nested_braces_inside_strings():
    html = (
        '<script>window.__INITIAL_STATE__ = '
        '{"note":{"text":"brace } and escaped \\\" quote",'
        '"nested":{"items":[1,{"ok":true}]}}};</script>'
    )
    assert extract_assigned_json(html, "window.__INITIAL_STATE__") == {
        "note": {
            "text": 'brace } and escaped " quote',
            "nested": {"items": [1, {"ok": True}]},
        }
    }


def test_extract_assigned_json_fails_when_assignment_is_absent():
    with pytest.raises(ValueError, match="embedded JSON marker not found"):
        extract_assigned_json("<html></html>", "window.__INITIAL_STATE__")
```

- [ ] **Step 2: Write failing shared-normalization tests**

```python
def test_build_platform_post_requires_all_target_modalities():
    with pytest.raises(ValidationError, match="missing target modalities"):
        ParsedPlatformPost(
            **_payload_fields(),
            modalities={
                "text": CaptureModality(status="complete"),
            },
        )


def test_remote_image_reference_is_partial_and_blocks_disclosure_absence():
    post = build_platform_post(
        _payload(
            media=[MediaRecord(
                media_id="image-1",
                type="image",
                ref="https://media.example.test/image-1.jpg",
            )],
            modalities=_target_modalities(image="partial"),
        ),
        source_ref_hash="a" * 64,
        adapter_version="fixture-v1",
    )
    assert post.capture_status.modalities["image"].status == "partial"
    assert post.capture_status.can_assess_disclosure is False
    assert post.privacy.anonymized is True
```

- [ ] **Step 3: Run the tests and verify RED**

```powershell
cd implicit-ad-agent
python -m pytest tests/adapters/platforms/test_embedded_json.py tests/adapters/platforms/test_platform_normalization.py -q
```

Expected: import failures because both modules are absent.

- [ ] **Step 4: Implement `extract_assigned_json`**

Use a single-pass scanner that tracks `depth`, `in_string`, and `escaped`. Start at the first `{` after the exact marker and return `json.loads` of the balanced object. Raise these stable `ValueError` messages:

```text
embedded JSON marker not found
embedded JSON object not found
embedded JSON object is incomplete
embedded JSON object is invalid
```

Do not replace arbitrary `undefined` text. Synthetic fixtures are valid JSON; invalid source must fail explicitly.

- [ ] **Step 5: Implement strict shared normalization**

Define:

```python
TargetModality = Literal["text", "image", "comment", "disclosure"]


class ParsedPlatformPost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    post_id: str = Field(min_length=1)
    creator_id: str = Field(min_length=1)
    published_at: datetime | None = None
    text: str
    media: list[MediaRecord] = Field(default_factory=list)
    comments: list[CommentRecord] = Field(default_factory=list)
    disclosures: list[DisclosureRecord] = Field(default_factory=list)
    modalities: dict[TargetModality, CaptureModality]
    captured_at: datetime

    @model_validator(mode="after")
    def require_target_modalities(self):
        required = {"text", "image", "comment", "disclosure"}
        missing = sorted(required - set(self.modalities))
        if missing:
            raise ValueError(
                "missing target modalities: " + ", ".join(missing)
            )
        return self
```

Implement builder semantics:

```python
def build_platform_post(
    payload: ParsedPlatformPost,
    *,
    source_ref_hash: str,
    adapter_version: str,
) -> PostRecord:
    disclosure_complete = (
        payload.modalities["disclosure"].status == "complete"
        and payload.modalities["text"].status == "complete"
        and payload.modalities["image"].status in {
            "complete", "unsupported"
        }
        and all(item.type == "image" for item in payload.media)
    )
    return PostRecord(
        schema_version="1.0",
        post_id=payload.post_id,
        platform=payload.platform,
        source_type="platform_fixture",
        creator_id=payload.creator_id,
        published_at=payload.published_at,
        text=payload.text,
        media=payload.media,
        comments=payload.comments,
        disclosures=payload.disclosures,
        provenance=ProvenanceRecord(
            source_ref_hash=source_ref_hash,
            collected_at=payload.captured_at,
            collector="synthetic_fixture",
        ),
        privacy=PrivacyRecord(
            anonymized=True,
            contains_sensitive_data=False,
        ),
        capture_status=CaptureStatus(
            source=f"fixture:{payload.platform}",
            modalities=payload.modalities,
            can_assess_disclosure=disclosure_complete,
            adapter_version=adapter_version,
            captured_at=payload.captured_at,
        ),
    )
```

- [ ] **Step 6: Run focused tests and verify GREEN**

Run the Step 3 command. Expected: all selected tests pass.

- [ ] **Step 7: Commit only Task 2 files**

```powershell
git add -- implicit-ad-agent/impad/adapters/platforms/embedded_json.py implicit-ad-agent/impad/adapters/platforms/normalization.py implicit-ad-agent/tests/adapters/platforms/test_embedded_json.py implicit-ad-agent/tests/adapters/platforms/test_platform_normalization.py
git commit -m "feat: add deterministic platform normalization"
```

---

### Task 3: Implement Xiaohongshu Synthetic Fixtures and Adapter

**Files:**

- Create: `implicit-ad-agent/impad/adapters/platforms/xiaohongshu.py`
- Create: `implicit-ad-agent/tests/adapters/platforms/test_xiaohongshu.py`
- Create: `implicit-ad-agent/tests/fixtures/platforms/xiaohongshu/normal_complete/*`
- Create: `implicit-ad-agent/tests/fixtures/platforms/xiaohongshu/video_missing_comments/*`
- Modify: `implicit-ad-agent/impad/adapters/platforms/__init__.py`

**Interfaces:**

- Produces: `parse_xiaohongshu_state(state, source_ref_hash) -> PostRecord`.
- Produces: `XiaohongshuAdapter.preview(source, fetcher) -> PostRecord`.
- Consumes: Task 2 `extract_assigned_json`, `ParsedPlatformPost`, and `build_platform_post`.

- [ ] **Step 1: Add the two fixture bundles**

Use fixed synthetic identifiers and times:

```json
{
  "note": {
    "noteDetailMap": {
      "xhs_note_normal_001": {
        "note": {
          "noteId": "xhs_note_normal_001",
          "type": "normal",
          "title": "Synthetic morning routine",
          "desc": "Synthetic fixture body #品牌合作",
          "time": 1786176000000,
          "user": {"userId": "xhs_creator_001"},
          "imageList": [
            {"urlDefault": "https://media.example.test/xhs/image-1.jpg"}
          ],
          "interactInfo": {"commentCount": 1},
          "comments": [
            {
              "id": "xhs_comment_001",
              "user": {"userId": "xhs_commenter_001"},
              "content": "Synthetic comment",
              "likeCount": 2,
              "isPinned": false
            }
          ],
          "disclosureLabels": ["品牌合作"]
        }
      }
    }
  },
  "fixtureCapturedAt": "2026-08-08T08:00:00+08:00"
}
```

The video state is fixed to this shape:

```json
{
  "note": {
    "noteDetailMap": {
      "xhs_note_video_001": {
        "note": {
          "noteId": "xhs_note_video_001",
          "type": "video",
          "title": "Synthetic video note",
          "desc": "Synthetic video fixture body",
          "time": 1786176600000,
          "user": {"userId": "xhs_creator_002"},
          "video": {"durationSeconds": 12},
          "interactInfo": {"commentCount": 3},
          "disclosureLabels": []
        }
      }
    }
  },
  "fixtureCapturedAt": "2026-08-08T08:10:00+08:00"
}
```

Every manifest contains exactly:

```json
{
  "fixture_version": "platform-fixture-v1",
  "synthetic": true,
  "contains_real_user_data": false,
  "network_required": false,
  "platform": "xiaohongshu",
  "content_type": "normal",
  "expected_modalities": {
    "text": "complete",
    "image": "partial",
    "comment": "complete",
    "disclosure": "complete"
  },
  "real_platform_compatibility_verified": false,
  "terms_approved": false
}
```

The video manifest differs from the normal manifest only in these exact values:

```json
{
  "platform": "xiaohongshu",
  "content_type": "video",
  "expected_modalities": {
    "text": "complete",
    "image": "unsupported",
    "comment": "missing",
    "disclosure": "complete"
  }
}
```

It retains the same five governance fields and their values from the normal manifest. Embed each `source_state.json` byte-for-byte as the JSON value assigned to `window.__INITIAL_STATE__` in its `source.html`.

- [ ] **Step 2: Write failing golden and adapter tests**

```python
@pytest.mark.parametrize(
    "case",
    ["normal_complete", "video_missing_comments"],
)
def test_xiaohongshu_fixture_matches_expected_post(case):
    fixture = _fixture(case)
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    expected = PostRecord.model_validate_json(
        (fixture / "expected_post.json").read_text("utf-8")
    )
    first = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)
    second = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)
    assert first == expected
    assert first.model_dump_json() == second.model_dump_json()


def test_xiaohongshu_adapter_reads_injected_html_without_network():
    fetcher = FixtureFetcher(_fixture("normal_complete") / "source.html")
    adapter = XiaohongshuAdapter()
    post = adapter.preview(
        validate_public_https_url(
            "https://www.xiaohongshu.com/explore/xhs_note_normal_001"
        ),
        fetcher=fetcher,
    )
    assert fetcher.calls == [
        "https://www.xiaohongshu.com/explore/xhs_note_normal_001"
    ]
    assert post.platform == "xiaohongshu"
```

Also test missing note ID and creator ID separately; both must raise `ValueError` and must not create placeholder strings.

- [ ] **Step 3: Run Xiaohongshu tests and verify RED**

```powershell
cd implicit-ad-agent
python -m pytest tests/adapters/platforms/test_xiaohongshu.py -q
```

Expected: import failure because the adapter does not exist.

- [ ] **Step 4: Implement minimal Xiaohongshu parsing**

Define exact adapter metadata:

```python
class XiaohongshuAdapter:
    name = "xiaohongshu_fixture"
    version = "xiaohongshu-fixture-v1"
    platform = "xiaohongshu"
    supported_hosts = ("xiaohongshu.com",)

    def preview(self, source, *, fetcher):
        result = fetcher.fetch(source.fetch_url)
        html = result.body.decode("utf-8")
        state = extract_assigned_json(html, "window.__INITIAL_STATE__")
        return parse_xiaohongshu_state(
            state,
            source_ref_hash=result.source_ref_hash,
        )
```

The parser must:

- select exactly one note from `note.noteDetailMap`;
- require `noteId` and `user.userId`;
- normalize milliseconds to timezone-aware `+08:00`;
- combine non-empty title, description, and `<图片N>` markers with newline separators;
- preserve image order and create stable `media_id` values from the platform image index;
- map comments with strict allowed `CommentRecord` fields only;
- create disclosures from `disclosureLabels` and exact hashtags `#广告`, `#品牌合作`, `#赞助` without soft-signal inference;
- set modality statuses exactly as declared by the fixture facts.

- [ ] **Step 5: Generate and verify exact `expected_post.json` snapshots**

Use the parser output once to inspect the complete JSON, then add the reviewed fixed JSON via `apply_patch`. Re-run the golden tests. Do not make the tests rewrite snapshots.

- [ ] **Step 6: Run Xiaohongshu and shared tests and verify GREEN**

```powershell
python -m pytest tests/adapters/platforms/test_embedded_json.py tests/adapters/platforms/test_platform_normalization.py tests/adapters/platforms/test_xiaohongshu.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit only Task 3 files**

```powershell
git add -- implicit-ad-agent/impad/adapters/platforms/xiaohongshu.py implicit-ad-agent/impad/adapters/platforms/__init__.py implicit-ad-agent/tests/adapters/platforms/test_xiaohongshu.py implicit-ad-agent/tests/fixtures/platforms/xiaohongshu
git commit -m "feat: add Xiaohongshu fixture adapter"
```

---

### Task 4: Implement Bilibili Synthetic Fixtures and Adapter

**Files:**

- Create: `implicit-ad-agent/impad/adapters/platforms/bilibili.py`
- Create: `implicit-ad-agent/tests/adapters/platforms/test_bilibili.py`
- Create: `implicit-ad-agent/tests/fixtures/platforms/bilibili/video_no_images/*`
- Create: `implicit-ad-agent/tests/fixtures/platforms/bilibili/opus_partial_images/*`
- Create: `implicit-ad-agent/tests/fixtures/platforms/bilibili/article_missing_disclosure_surface/*`
- Modify: `implicit-ad-agent/impad/adapters/platforms/__init__.py`

**Interfaces:**

- Produces: `parse_bilibili_state(state, content_type, source_ref_hash) -> PostRecord`.
- Produces: `BilibiliAdapter.preview(source, fetcher) -> PostRecord`.
- Consumes: Task 2 shared parser/normalizer contracts.

- [ ] **Step 1: Add three Bilibili fixture bundles**

Use the known content-specific state keys. The video state is:

```json
{
  "fixtureCapturedAt": "2026-08-08T09:00:00+08:00",
  "videoData": {
    "bvid": "BV_SYNTHETIC_001",
    "title": "Synthetic Bilibili video",
    "desc": "Synthetic description #赞助",
    "pubdate": 1786179600,
    "owner": {"mid": "bili_creator_001"},
    "disclosureLabels": ["赞助"]
  }
}
```

The opus state is:

```json
{
  "fixtureCapturedAt": "2026-08-08T09:10:00+08:00",
  "opusModule": {
    "dynamic_id": "bili_opus_001",
    "title": "Synthetic Bilibili opus",
    "description": "Synthetic opus fixture body",
    "published_at": "2026-08-08T09:00:00+08:00",
    "author": {"mid": "bili_creator_002"},
    "pictures": [
      {"url": "https://media.example.test/bilibili/opus-1.jpg"}
    ],
    "disclosureLabels": []
  }
}
```

The article state is:

```json
{
  "fixtureCapturedAt": "2026-08-08T09:20:00+08:00",
  "readInfo": {
    "id": "bili_article_001",
    "title": "Synthetic Bilibili article",
    "body": "Synthetic article fixture body",
    "publish_time": 1786180800,
    "author": {"mid": "bili_creator_003"},
    "images": [
      {"url": "https://media.example.test/bilibili/article-1.jpg"}
    ],
    "disclosureSurfaceCaptured": false
  }
}
```

All Bilibili comments are `unsupported` because the fixture adapter does not call a comment API. Manifests use the approved state matrix.

- [ ] **Step 2: Write failing routing, golden, and adapter tests**

```python
@pytest.mark.parametrize(
    ("case", "content_type"),
    [
        ("video_no_images", "video"),
        ("opus_partial_images", "opus"),
        ("article_missing_disclosure_surface", "article"),
    ],
)
def test_bilibili_fixture_matches_expected_post(case, content_type):
    fixture = _fixture(case)
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    post = parse_bilibili_state(
        state,
        content_type=content_type,
        source_ref_hash="b" * 64,
    )
    expected = PostRecord.model_validate_json(
        (fixture / "expected_post.json").read_text("utf-8")
    )
    assert post == expected
    assert post.capture_status.modalities["comment"].status == "unsupported"


def test_bilibili_rejects_unknown_fixture_content_type():
    with pytest.raises(ValueError, match="unsupported Bilibili content type"):
        parse_bilibili_state(
            {},
            content_type="live",
            source_ref_hash="b" * 64,
        )
```

Add an adapter test for `https://www.bilibili.com/video/BV_SYNTHETIC_001` using the injected fixture fetcher. Add separate required-ID tests for bvid/dynamic_id/cv_id and creator ID.

- [ ] **Step 3: Run Bilibili tests and verify RED**

```powershell
cd implicit-ad-agent
python -m pytest tests/adapters/platforms/test_bilibili.py -q
```

Expected: import failure because the adapter does not exist.

- [ ] **Step 4: Implement minimal Bilibili routing and parsing**

```python
class BilibiliAdapter:
    name = "bilibili_fixture"
    version = "bilibili-fixture-v1"
    platform = "bilibili"
    supported_hosts = ("bilibili.com",)

    def preview(self, source, *, fetcher):
        result = fetcher.fetch(source.fetch_url)
        html = result.body.decode("utf-8")
        state = extract_assigned_json(html, "window.__INITIAL_STATE__")
        content_type = content_type_from_url(source.display_url)
        return parse_bilibili_state(
            state,
            content_type=content_type,
            source_ref_hash=result.source_ref_hash,
        )
```

`content_type_from_url` accepts `/video/`, `/opus/` or `t.bilibili.com/`, and `/read/cv`; every other path raises `ValueError("unsupported Bilibili content type")`. Each parser branch must also require its matching state key (`videoData`, `opusModule`, or `readInfo`) and explicitly map native IDs, creator ID, time, text, media, comments, disclosures, and the four target modalities. Do not fall back from an unknown branch to video.

- [ ] **Step 5: Add reviewed fixed expected snapshots**

Inspect parser output, add exact JSON snapshots with `apply_patch`, and keep snapshot rewriting out of tests.

- [ ] **Step 6: Run all platform parser tests and verify GREEN**

```powershell
python -m pytest tests/adapters/platforms/test_embedded_json.py tests/adapters/platforms/test_platform_normalization.py tests/adapters/platforms/test_xiaohongshu.py tests/adapters/platforms/test_bilibili.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit only Task 4 files**

```powershell
git add -- implicit-ad-agent/impad/adapters/platforms/bilibili.py implicit-ad-agent/impad/adapters/platforms/__init__.py implicit-ad-agent/tests/adapters/platforms/test_bilibili.py implicit-ad-agent/tests/fixtures/platforms/bilibili
git commit -m "feat: add Bilibili fixture adapter"
```

---

### Task 5: Wire Disclosure Corrections Through API and Workbench

**Files:**

- Modify: `implicit-ad-agent/impad/adapters/platforms/contracts.py:10-92`
- Modify: `implicit-ad-agent/impad/web/index.html:99-112`
- Modify: `implicit-ad-agent/impad/web/workbench.js:186-207`
- Modify: `implicit-ad-agent/tests/adapters/platforms/test_url_import.py`
- Modify: `implicit-ad-agent/tests/api/test_routes.py`
- Modify: `implicit-ad-agent/tests/web/workbench_behavior.test.cjs:153-175`
- Modify: `implicit-ad-agent/tests/web/test_workbench.py`

**Interfaces:**

- Consumes: `DisclosureRecord` from Task 1.
- Produces: `URLImportCorrections.disclosures: list[DisclosureRecord] | None` and workbench `correction-disclosures` JSON array.

- [ ] **Step 1: Write failing URL correction tests**

```python
def test_confirm_applies_and_audits_disclosure_corrections(tmp_path):
    service, _ = _url_service(tmp_path)
    preview = service.preview("https://example.test/post/1")
    disclosures = [DisclosureRecord(
        kind="platform_badge",
        text="品牌合作",
        source="platform_metadata",
    )]
    result = service.confirm(
        preview.preview_id,
        URLImportCorrections(disclosures=disclosures),
    )
    assert result.post.disclosures == disclosures
    assert "disclosures" in result.post.capture_status.user_corrections
```

Add `disclosures` to an API confirm payload and assert the returned run contains it. Keep `post_id`, `platform`, `source_type`, `provenance`, and `privacy` in the rejected correction parameterization.

- [ ] **Step 2: Write failing workbench behavior tests**

Add `correction-disclosures` to the fake DOM IDs and initial value. Assert preview fill writes `post.disclosures`, and confirm submits:

```javascript
disclosures: [
  {kind: "platform_badge", text: "品牌合作", source: "platform_metadata"},
]
```

Add an invalid non-array JSON case and assert no confirm request is sent.

- [ ] **Step 3: Run correction/Web tests and verify RED**

```powershell
cd implicit-ad-agent
python -m pytest tests/adapters/platforms/test_url_import.py tests/api/test_routes.py tests/web/test_workbench.py -q
node --test tests/web/workbench_behavior.test.cjs
```

Expected: Python schema rejects `disclosures` and the workbench field is absent.

- [ ] **Step 4: Implement minimal schema and UI wiring**

Import `DisclosureRecord` in platform contracts and add:

```python
disclosures: list[DisclosureRecord] | None = None
```

Add HTML between comments and history:

```html
<label for="correction-disclosures">披露标记 JSON 数组</label>
<textarea id="correction-disclosures">[]</textarea>
```

Add JS preview and correction wiring:

```javascript
byId("correction-disclosures").value = jsonText(post.disclosures || []);

disclosures: parseJsonArray(
  byId("correction-disclosures").value,
  "披露标记",
),
```

No URLImportService loop change is required because it already applies every allowlisted model field and audits actual changed fields.

- [ ] **Step 5: Run correction/Web tests and verify GREEN**

Run the Step 3 commands. Expected: all selected Python and Node tests pass.

- [ ] **Step 6: Commit only Task 5 files**

```powershell
git add -- implicit-ad-agent/impad/adapters/platforms/contracts.py implicit-ad-agent/impad/web/index.html implicit-ad-agent/impad/web/workbench.js implicit-ad-agent/tests/adapters/platforms/test_url_import.py implicit-ad-agent/tests/api/test_routes.py implicit-ad-agent/tests/web/workbench_behavior.test.cjs implicit-ad-agent/tests/web/test_workbench.py
git commit -m "feat: support disclosure corrections"
```

---

### Task 6: Enforce Fixture Governance and Default-Offline Registration

**Files:**

- Create: `implicit-ad-agent/tests/adapters/platforms/test_fixture_governance.py`
- Modify: `implicit-ad-agent/tests/adapters/platforms/test_registry.py`
- Modify: `implicit-ad-agent/tests/api/test_routes.py`

**Interfaces:**

- Consumes: both adapters and all five fixture bundles.
- Produces: executable proof that manifests are synthetic/no-network/no-real-user-data and that default capabilities remain empty.

- [ ] **Step 1: Write failing manifest and secret-scan tests**

```python
CASES = sorted(
    (FIXTURE_ROOT / "xiaohongshu").iterdir()
) + sorted((FIXTURE_ROOT / "bilibili").iterdir())


def test_all_platform_fixture_manifests_are_explicitly_synthetic():
    assert len(CASES) == 5
    for case in CASES:
        manifest = json.loads((case / "manifest.json").read_text("utf-8"))
        assert manifest["synthetic"] is True
        assert manifest["contains_real_user_data"] is False
        assert manifest["network_required"] is False
        assert manifest["real_platform_compatibility_verified"] is False
        assert manifest["terms_approved"] is False


def test_platform_fixtures_contain_no_secret_or_direct_identifier_patterns():
    forbidden = re.compile(
        r"(?i)(cookie\s*:|authorization\s*:|bearer\s+|"
        r"api[_-]?key|secret[_-]?key|BEGIN (RSA |EC )?PRIVATE KEY|"
        r"\b1[3-9]\d{9}\b|[A-Z0-9._%+-]+@(?!example\.test))"
    )
    for case in CASES:
        for path in case.iterdir():
            assert forbidden.search(path.read_text("utf-8")) is None, path
```

- [ ] **Step 2: Write failing explicit-registry/default-registry tests**

```python
def test_fixture_adapters_resolve_only_when_explicitly_registered():
    registry = PlatformAdapterRegistry([
        XiaohongshuAdapter(),
        BilibiliAdapter(),
    ])
    assert registry.resolve(validate_public_https_url(
        "https://www.xiaohongshu.com/explore/x"
    )).platform == "xiaohongshu"
    assert registry.resolve(validate_public_https_url(
        "https://www.bilibili.com/video/x"
    )).platform == "bilibili"


def test_default_capabilities_still_claim_no_live_platforms():
    payload = TestClient(create_app()).get("/api/v1/capabilities").json()
    assert payload["url_import"]["platforms"] == []
```

- [ ] **Step 3: Run governance/security tests and verify RED**

```powershell
cd implicit-ad-agent
python -m pytest tests/adapters/platforms/test_fixture_governance.py tests/adapters/platforms/test_registry.py tests/api/test_routes.py tests/security/test_artifact_scan.py -q
```

Expected before fixture completion: manifest or export failures. After Tasks 3/4, ensure the tests fail for any missing governance assertion rather than passing vacuously.

- [ ] **Step 4: Make the minimum export/test integration changes**

Export `XiaohongshuAdapter` and `BilibiliAdapter` from the platform package. Do not edit `create_app`, `create_api_router`, or default `URLImportService` construction to register them.

Keep the platform-specific fixture regex in `test_fixture_governance.py`; do not add or modify a second production artifact scanner. Run the existing artifact scanner tests unchanged as a regression in Steps 3 and 5.

- [ ] **Step 5: Run governance/security tests and verify GREEN**

Run the Step 3 command. Expected: all selected tests pass and no network call occurs.

- [ ] **Step 6: Commit only Task 6 files**

```powershell
git add -- implicit-ad-agent/impad/adapters/platforms/__init__.py implicit-ad-agent/tests/adapters/platforms/test_fixture_governance.py implicit-ad-agent/tests/adapters/platforms/test_registry.py implicit-ad-agent/tests/api/test_routes.py
git commit -m "test: enforce platform fixture governance"
```

---

### Task 7: Synchronize P5.3/P5.4 Documentation and Run Completion Audit

**Files:**

- Modify: `docs/隐性广告识别项目_分阶段计划表.md:159-173`
- Modify: `HANDOFF.md:94-104,307-317`
- Modify: `docs/已有功能测试指令库.md:34-48`

**Interfaces:**

- Consumes: fresh verification output from all prior tasks.
- Produces: current-state documentation that separates synthetic-fixture completion from real-platform and M5 acceptance.

- [ ] **Step 1: Run the focused platform suite**

```powershell
cd implicit-ad-agent
python -m pytest tests/contracts/test_post_record.py tests/adapters/platforms tests/orchestration/test_evidence_adapters.py tests/orchestration/test_adequacy.py tests/api/test_routes.py tests/web/test_workbench.py tests/security/test_artifact_scan.py -q
node --test tests/web/workbench_behavior.test.cjs
```

Expected: zero failures. Record the exact Python passed/skipped/warning counts and the Node passed/failed counts.

- [ ] **Step 2: Run dependency and compilation checks**

```powershell
python -m pip check
python -m compileall -q impad tests
```

Expected: `No broken requirements found.` and exit code 0 from compileall.

- [ ] **Step 3: Run the full Python suite**

```powershell
python -m pytest -q
```

Expected: zero failures. Record exact passed/skipped/warning counts; do not reuse historical `495 passed` numbers.

- [ ] **Step 4: Update documentation from current evidence**

Add a dated paragraph that states only:

```text
P5.3/P5.4 synthetic fixture 工程范围已实现：小红书 normal/video 与
B站 video/opus/article 的五个结构仿真案例通过确定性解析，统一输出
PostRecord/CaptureStatus，四目标模态状态与披露人工修正有回归证据；默认应用
仍不注册真实平台适配器、未发起真实平台请求。该结果不证明真实页面兼容、
来源条款/隐私/安全审批、M5、P5.5/P5.6 或研究有效性。
```

Append the fresh focused/full counts and exact commands. Preserve all M1/M4/UAT caveats and unrelated handoff content.

- [ ] **Step 5: Run the requirements completion audit**

Verify each design completion criterion against authoritative evidence:

1. exactly five fixture cases and four files per case;
2. every manifest has all five governance booleans/identifiers;
3. both adapters parse twice to identical JSON;
4. target modalities exist on every expected PostRecord;
5. disclosure corrections reach confirmed run output and audit list;
6. default capabilities list remains empty;
7. focused/full tests, Node tests, pip check, compileall, and diff check pass;
8. docs preserve real-platform, governance, A2A, M5, M1, and M4 boundaries.

Treat any missing or indirect evidence as incomplete and fix it before continuing.

- [ ] **Step 6: Run final diff verification**

From the repository root:

```powershell
git diff --check
git status --short
git diff --stat HEAD~6..HEAD
```

Expected: `git diff --check` exits 0. Inspect status to ensure unrelated user changes remain untouched and unstaged.

- [ ] **Step 7: Commit only the documentation files**

```powershell
git add -- docs/隐性广告识别项目_分阶段计划表.md HANDOFF.md docs/已有功能测试指令库.md
git commit -m "docs: record P5.3 P5.4 fixture verification"
```

- [ ] **Step 8: Re-run final smoke verification after the documentation commit**

```powershell
cd implicit-ad-agent
python -m pytest tests/adapters/platforms tests/adapters/platforms/test_url_import.py tests/api/test_routes.py -q
cd ..
git diff --check
```

Expected: zero test failures and clean diff check. Only then may the implementation be reported as complete.
