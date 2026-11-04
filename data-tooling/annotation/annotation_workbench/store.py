"""Annotation persistence, batch preparation, and display-safe adapters.

The workbench is intentionally local-first:

* every annotator writes to their own append-only JSONL log;
* the log lives under the Git-ignored ``data/annotations/workbench`` tree;
* dataset, batch, annotator and batch-manifest hashes are recorded in every
  row and checked on replay, so two batches or two annotators cannot silently
  overwrite one another;
* media is resolved by index from the post record, never by a path supplied by
  the browser, and must stay under ``--media-root``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote

SCHEMA_VERSION = "1.0"
RECORD_TYPE = "annotation"
DEFAULT_GUIDE_VERSION = "1.0"
LABELS = ("明广", "暗广", "非广", "uncertain", "out_of_scope")
EVIDENCE_CODES = ("D", "C", "P", "A", "V", "M", "B")
MANIFEST_ROLES = ("exploratory", "approved")
COMMENT_DISPLAY_LIMIT = 200
TEXT_DISPLAY_LIMIT = 20000

_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class WorkbenchError(Exception):
    """Base class for workbench errors shown to the operator."""


class ManifestError(WorkbenchError):
    """The post-id list is invalid or does not match the dataset."""


class ValidationError(WorkbenchError):
    """An annotation payload violates the labelling contract."""


class ConflictError(WorkbenchError):
    """The requested state transition conflicts with recorded advice state."""


class NotFoundError(WorkbenchError):
    """A post index or media reference does not exist."""


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def safe_component(name: str, *, field_name: str) -> str:
    """Validate a dataset/batch/annotator identifier used as a directory name."""
    value = (name or "").strip()
    if not _COMPONENT_RE.match(value):
        raise ManifestError(
            f"{field_name} 只能是 1-80 位字母、数字、点、下划线或连字符，且必须以字母或数字开头：{value!r}"
        )
    if value.split(".")[0].upper() in _WINDOWS_RESERVED:
        raise ManifestError(f"{field_name} 不能使用 Windows 保留名：{value!r}")
    return value


def _json_documents(raw: str) -> List[Any]:
    """Parse one JSON document, or a stream of concatenated JSON documents."""
    try:
        return [json.loads(raw)]
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    docs: List[Any] = []
    index = 0
    length = len(raw)
    while index < length:
        while index < length and raw[index] in " \t\r\n":
            index += 1
        if index >= length:
            break
        try:
            doc, end = decoder.raw_decode(raw, index)
        except json.JSONDecodeError:
            next_object = raw.find("{", index + 1)
            next_array = raw.find("[", index + 1)
            candidates = [pos for pos in (next_object, next_array) if pos >= 0]
            if not candidates:
                raise
            index = min(candidates)
            continue
        docs.append(doc)
        index = end
    return docs


def _records_from_document(doc: Any) -> List[Dict[str, Any]]:
    if isinstance(doc, list):
        rows = doc
    elif isinstance(doc, dict):
        rows = None
        for key in ("content_records", "records", "posts", "items", "data"):
            value = doc.get(key)
            if isinstance(value, list):
                rows = value
                break
        if rows is None:
            if "post_id" in doc:
                rows = [doc]
            else:
                raise WorkbenchError("数据文件是 JSON 对象，但找不到 content_records/records/posts/items 数组")
    else:
        raise WorkbenchError("数据文件顶层必须是对象或数组")
    result: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise WorkbenchError("数据文件的每条记录必须是 JSON 对象")
        post_id = row.get("post_id")
        if not isinstance(post_id, str) or not post_id.strip():
            raise WorkbenchError(f"记录缺少非空字符串 post_id：{row!r}")
        result.append(row)
    return result


def load_dataset_records(path: Path) -> List[Dict[str, Any]]:
    """Load posts from a JSON array/object or a JSONL file.

    The crawler occasionally writes several pretty-printed JSON objects back to
    back without newline delimiters; ``_json_documents`` tolerates that.  For
    ordinary JSONL, one object per line is also accepted.
    """
    raw = path.read_text(encoding="utf-8-sig")
    if not raw.strip():
        raise WorkbenchError(f"数据文件为空：{path}")
    try:
        docs = _json_documents(raw)
    except json.JSONDecodeError as exc:
        raise WorkbenchError(f"无法解析数据文件 {path}: {exc}") from exc
    records: List[Dict[str, Any]] = []
    for doc in docs:
        records.extend(_records_from_document(doc))
    if not records:
        raise WorkbenchError(f"数据文件没有记录：{path}")
    seen: Dict[str, int] = {}
    for index, record in enumerate(records, start=1):
        post_id = record["post_id"]
        if post_id in seen:
            raise WorkbenchError(f"数据文件 post_id 重复：{post_id!r}（第 {seen[post_id]} 与第 {index} 条）")
        seen[post_id] = index
    return records


def _ids_from_rows(rows: Iterable[Any]) -> List[str]:
    ids: List[str] = []
    for row in rows:
        if isinstance(row, dict):
            value = row.get("post_id")
            if value is None:
                raise ManifestError(f"清单项缺少 post_id：{row!r}")
            value = str(value).strip()
        elif isinstance(row, str):
            value = row.strip()
        elif isinstance(row, (int, float)):
            value = str(row).strip()
        else:
            raise ManifestError(f"清单项必须是 post_id 字符串或含 post_id 的对象：{row!r}")
        if not value:
            continue
        ids.append(value)
    return ids


def load_manifest_ids(path: Path) -> List[str]:
    """Load an ordered post-id list from txt/json/jsonl/csv without deduping."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        if not rows:
            return []
        first = [cell.strip() for cell in rows[0]]
        start = 0
        if len(first) >= 1 and first[0].lower() in {"post_id", "postid", "id", "帖子id", "帖子_id"}:
            start = 1
        return [str(row[0]).strip() for row in rows[start:] if row and str(row[0]).strip()]

    raw = path.read_text(encoding="utf-8-sig")
    if suffix == ".jsonl":
        rows: List[Any] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError:
                rows.extend(doc for doc in _json_documents(stripped))
        return _ids_from_rows(rows)

    if suffix == ".json":
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"清单 JSON 无法解析：{path}: {exc}") from exc
        if isinstance(doc, dict):
            for key in ("post_ids", "items", "records", "posts"):
                value = doc.get(key)
                if isinstance(value, list):
                    return _ids_from_rows(value)
            if "post_id" in doc:
                return _ids_from_rows([doc])
            raise ManifestError("清单 JSON 对象必须含 post_ids/items/records 数组")
        if isinstance(doc, list):
            return _ids_from_rows(doc)
        raise ManifestError("清单 JSON 顶层必须是数组或对象")

    lines = []
    for line in raw.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        lines.append(value)
    return lines


def validate_manifest(ordered_ids: Sequence[str], dataset_ids: Sequence[str]) -> Dict[str, Any]:
    """Check duplicate and missing ids while preserving manifest order."""
    dataset_set = set(dataset_ids)
    counter = Counter(ordered_ids)
    duplicates: List[str] = []
    for post_id in ordered_ids:
        if counter[post_id] > 1 and post_id not in duplicates:
            duplicates.append(post_id)
    missing = [post_id for post_id in ordered_ids if post_id not in dataset_set]
    if duplicates or missing:
        parts = []
        if duplicates:
            parts.append(f"重复 {len(duplicates)} 个（例如 {', '.join(duplicates[:5])}）")
        if missing:
            parts.append(f"数据集中缺失 {len(missing)} 个（例如 {', '.join(missing[:5])}）")
        raise ManifestError("post_id 清单校验失败：" + "；".join(parts))
    return {
        "post_count": len(ordered_ids),
        "duplicate_count": 0,
        "missing_count": 0,
        "ordered_post_ids_sha256": sha256_text("\n".join(ordered_ids)),
    }


def _normalize_collection(value: Any) -> str:
    if isinstance(value, bool):
        return "complete" if value else "incomplete"
    text = str(value or "").strip().lower()
    if text in {"complete", "completed", "done", "full", "true", "1", "完整", "已完成", "采集完整"}:
        return "complete"
    if text in {"incomplete", "partial", "failed", "error", "blocked", "missing", "false", "0", "不完整", "未完成", "采集不完整"}:
        return "incomplete"
    return "unknown"


def _as_text(value: Any, limit: int = TEXT_DISPLAY_LIMIT) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(value)
    if len(text) > limit:
        return text[:limit] + f"\n…（已截断，共 {len(text)} 字符）"
    return text


def _nonempty(value: Any) -> Optional[str]:
    text = _as_text(value).strip()
    return text or None


def _first_text(post: Dict[str, Any], keys: Sequence[str]) -> Optional[str]:
    for key in keys:
        value = post.get(key)
        if isinstance(value, bool):
            if value:
                return key
            continue
        text = _nonempty(value)
        if text:
            return text
    return None


def disclosure_view(post: Dict[str, Any]) -> Dict[str, Any]:
    """Describe the disclosure area, distinguishing absent from uncaptured."""
    explicit_status = str(post.get("disclosure_status") or "").strip().lower()
    if explicit_status in {"present", "absent_complete", "missing", "unknown"}:
        status = explicit_status
    else:
        text = _first_text(
            post,
            (
                "disclosure", "ad_disclosure", "sponsorship_disclosure",
                "platform_label", "commercial_label", "paid_partnership",
                "branded_content_label",
            ),
        )
        if text:
            status = "present"
        else:
            collection = _normalize_collection(
                post.get("collection_complete", post.get("collection_status"))
            )
            status = "absent_complete" if collection == "complete" else (
                "missing" if collection == "incomplete" else "unknown"
            )
    messages = {
        "present": "披露区域已采集到明确披露或平台商业标识。",
        "absent_complete": "披露区域已完整采集，未发现明确披露（不是“未采集”）。",
        "missing": "披露区域缺失或采集不完整，不能视为“未发现披露”。",
        "unknown": "披露区域采集状态未知，不能视为“不存在披露”。",
    }
    return {
        "status": status,
        "label": messages[status],
        "detail": _first_text(
            post,
            (
                "disclosure", "ad_disclosure", "sponsorship_disclosure",
                "platform_label", "commercial_label", "paid_partnership",
                "branded_content_label",
            ),
        ) or "",
        "collection_complete": _normalize_collection(
            post.get("collection_complete", post.get("collection_status"))
        ),
    }


def resolve_media_path(media_root: Path, ref: Any) -> Path:
    """Resolve a record's media ref under ``media_root`` or raise ValueError."""
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("媒体 ref 为空")
    raw = ref.strip()
    if "\x00" in raw:
        raise ValueError("媒体 ref 含 NUL 字符")
    if raw.startswith(("/", "\\\\")) or re.match(r"^[A-Za-z]:", raw):
        raise ValueError("媒体 ref 不能是绝对路径、盘符路径或 UNC 路径")
    relative = Path(raw)
    if relative.is_absolute():
        raise ValueError("媒体 ref 不能是绝对路径")
    if any(part == ".." for part in relative.parts):
        raise ValueError("媒体 ref 不能包含 ..")
    root = media_root.expanduser().resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("媒体 ref 解析后越出 --media-root") from exc
    if not candidate.exists():
        raise FileNotFoundError(candidate)
    if not candidate.is_file():
        raise ValueError("媒体 ref 指向的不是普通文件")
    return candidate


def media_path_is_within(media_root: Path, candidate: Path) -> bool:
    root = media_root.expanduser().resolve()
    try:
        candidate.expanduser().resolve().relative_to(root)
        return True
    except ValueError:
        return False


def _media_kind_from_ref(ref: str) -> str:
    suffix = Path(ref).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        return "image"
    if suffix in {".mp4", ".webm", ".mov", ".mkv", ".avi"}:
        return "video"
    return "file"


def build_media_url(post_id: str, index: int) -> str:
    return f"/media?post_id={quote(post_id, safe='')}&i={int(index)}"


def media_view(post: Dict[str, Any], media_root: Path) -> List[Dict[str, Any]]:
    """Return display-ready media entries; missing/outside is never hidden."""
    raw_media = post.get("media")
    if not isinstance(raw_media, list):
        raw_media = []
    entries: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_media):
        if not isinstance(item, dict):
            entries.append({
                "index": index,
                "type": "unknown",
                "status": "missing",
                "label": "媒体记录格式异常",
                "url": None,
                "reason": "media 数组元素不是对象",
                "caption": "",
                "ref": "",
            })
            continue
        ref = item.get("ref")
        declared_type = str(item.get("type") or "").strip().lower()
        media_type = declared_type or (_media_kind_from_ref(ref) if isinstance(ref, str) else "unknown")
        base = {
            "index": index,
            "type": media_type,
            "caption": _as_text(item.get("caption"), 1000),
            "ref": _as_text(ref, 500),
            "source_url": _as_text(item.get("source_url"), 2000),
            "is_content": bool(item.get("is_content", True)),
        }
        if isinstance(ref, str) and re.match(r"^https?://", ref.strip(), re.IGNORECASE):
            entries.append({
                **base,
                "status": "remote_only",
                "label": "仅有远程链接，本地未保存",
                "url": None,
                "reason": "记录只有远程 URL；为避免外泄真实帖文，不自动加载远程资源。",
            })
            continue
        if not isinstance(ref, str) or not ref.strip():
            if base["source_url"]:
                entries.append({
                    **base,
                    "status": "remote_only",
                    "label": "仅有远程链接，本地未保存",
                    "url": None,
                    "reason": "没有本地 ref；为避免外泄真实帖文，不自动加载远程资源。",
                })
            else:
                entries.append({
                    **base,
                    "status": "missing",
                    "label": "缺失：记录没有本地媒体路径",
                    "url": None,
                    "reason": "media.ref 为空，不能当作没有媒体。",
                })
            continue
        try:
            resolved = resolve_media_path(media_root, ref)
        except ValueError as exc:
            entries.append({
                **base,
                "status": "outside",
                "label": "路径越界，已拒绝加载",
                "url": None,
                "reason": str(exc),
            })
            continue
        except FileNotFoundError:
            entries.append({
                **base,
                "status": "missing",
                "label": "缺失：本地文件不存在",
                "url": None,
                "reason": "记录指向的本地文件不存在，不能当作没有媒体。",
            })
            continue
        entries.append({
            **base,
            "status": "ok",
            "label": "本地媒体",
            "url": build_media_url(post["post_id"], index),
            "reason": "",
            "bytes": resolved.stat().st_size,
        })
    return entries


def media_summary(entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not entries:
        return {"status": "no_media", "label": "无媒体记录（不代表没有媒体）", "total": 0,
                "ok": 0, "missing": 0, "outside": 0, "remote_only": 0}
    counts = Counter(entry["status"] for entry in entries)
    missing = counts.get("missing", 0) + counts.get("outside", 0)
    if counts.get("ok", 0) == len(entries):
        status, label = "complete", "本地媒体齐全"
    elif missing:
        status, label = "missing", "存在缺失或越界媒体（见下方红色卡片）"
    elif counts.get("remote_only", 0):
        status, label = "remote_only", "只有远程链接，本地未保存"
    else:
        status, label = "unknown", "媒体状态未知"
    return {
        "status": status,
        "label": label,
        "total": len(entries),
        "ok": counts.get("ok", 0),
        "missing": counts.get("missing", 0),
        "outside": counts.get("outside", 0),
        "remote_only": counts.get("remote_only", 0),
    }


def comments_view(post: Dict[str, Any], *, limit: int = COMMENT_DISPLAY_LIMIT) -> Dict[str, Any]:
    """Expose comments with explicit missing/empty/truncated semantics."""
    collection = _normalize_collection(post.get("collection_complete", post.get("collection_status")))
    raw = post.get("comments")
    if raw is None:
        return {
            "status": "missing",
            "label": "评论未采集（不代表没有评论）",
            "total": 0,
            "items": [],
            "truncated": False,
            "collection": collection,
        }
    if not isinstance(raw, list):
        return {
            "status": "missing",
            "label": "评论字段格式异常，未采集",
            "total": 0,
            "items": [],
            "truncated": False,
            "collection": collection,
        }
    items: List[Dict[str, str]] = []
    for item in raw[:limit]:
        if isinstance(item, dict):
            author = _as_text(
                item.get("author") or item.get("user_name") or item.get("nickname") or item.get("user_id"),
                200,
            )
            text = _as_text(item.get("text") or item.get("content") or item.get("comment"), 4000)
            comment_id = _as_text(item.get("comment_id") or item.get("id"), 200)
        else:
            author, text, comment_id = "", _as_text(item, 4000), ""
        items.append({"author": author, "text": text, "comment_id": comment_id})
    total = len(raw)
    if total == 0:
        if collection == "complete":
            status, label = "empty_complete", "无评论（采集完成）"
        elif collection == "incomplete":
            status, label = "empty_uncertain", "评论为空，但采集不完整"
        else:
            status, label = "empty_unknown", "评论为空，采集状态未知"
    else:
        status = "present"
        label = f"共 {total} 条评论" + (f"，仅显示前 {limit} 条" if total > limit else "")
    return {
        "status": status,
        "label": label,
        "total": total,
        "items": items,
        "truncated": total > limit,
        "collection": collection,
    }


def display_post(post: Dict[str, Any], media_root: Path, index: int) -> Dict[str, Any]:
    """Build the JSON shape consumed by the browser (text only, no HTML)."""
    collection = _normalize_collection(post.get("collection_complete", post.get("collection_status")))
    media = media_view(post, media_root)
    title = _nonempty(post.get("title"))
    text = _nonempty(post.get("text") or post.get("content"))
    return {
        "index": index,
        "post_id": post["post_id"],
        "title": title,
        "title_missing": title is None,
        "text": text,
        "text_missing": text is None,
        "platform": _nonempty(post.get("platform")) or "未记录",
        "source_type": _nonempty(post.get("source_type")) or "未记录",
        "blogger_id": _nonempty(post.get("blogger_id")) or "未记录",
        "collection_complete": collection,
        "collection_label": {
            "complete": "采集完整",
            "incomplete": "采集不完整",
            "unknown": "采集状态未知",
        }[collection],
        "disclosure": disclosure_view(post),
        "comments": comments_view(post),
        "media": media,
        "media_summary": media_summary(media),
        "provenance": post.get("provenance") if isinstance(post.get("provenance"), dict) else {},
        "published_at": _nonempty(post.get("published_at") or post.get("publish_time")) or "",
    }


@dataclass(frozen=True)
class BatchSpec:
    dataset_id: str
    batch_id: str
    annotator_id: str
    dataset_path: Path
    output_root: Path
    media_root: Path
    manifest_path: Optional[Path] = None
    manifest_role: str = "exploratory"
    guide_version: str = DEFAULT_GUIDE_VERSION
    guide_sha256: str = ""


@dataclass
class PreparedBatch:
    spec: BatchSpec
    records: List[Dict[str, Any]]
    by_id: Dict[str, Dict[str, Any]]
    ordered_ids: List[str]
    manifest: Dict[str, Any]
    warnings: List[str]
    batch_dir: Path
    formal_gold_allowed: bool
    manifest_validation: Dict[str, Any] = field(default_factory=dict)

    @property
    def batch_manifest_sha256(self) -> str:
        return str(self.manifest.get("_sha256", ""))


def _batch_meta(prepared: PreparedBatch) -> Dict[str, Any]:
    spec = prepared.spec
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": spec.dataset_id,
        "batch_id": spec.batch_id,
        "dataset_name": spec.dataset_path.name,
        "dataset_sha256": sha256_bytes(spec.dataset_path.read_bytes()),
        "manifest_name": spec.manifest_path.name if spec.manifest_path else None,
        "manifest_sha256": sha256_bytes(spec.manifest_path.read_bytes()) if spec.manifest_path else None,
        "manifest_role": spec.manifest_role,
        "post_count": len(prepared.ordered_ids),
        "ordered_post_ids_sha256": prepared.manifest_validation["ordered_post_ids_sha256"],
        "guide_version": spec.guide_version,
        "guide_sha256": spec.guide_sha256,
        "formal_gold_allowed": prepared.formal_gold_allowed,
        "created_at": iso_now(),
    }


def prepare_batch(spec: BatchSpec) -> PreparedBatch:
    """Load the dataset + optional manifest and reconcile the batch metadata."""
    safe_component(spec.dataset_id, field_name="dataset_id")
    safe_component(spec.batch_id, field_name="batch_id")
    safe_component(spec.annotator_id, field_name="annotator_id")
    if spec.manifest_role not in MANIFEST_ROLES:
        raise ManifestError(f"manifest_role 必须是 {MANIFEST_ROLES} 之一")
    if not spec.dataset_path.is_file():
        raise WorkbenchError(f"数据集文件不存在：{spec.dataset_path}")
    if spec.manifest_path is not None and not spec.manifest_path.is_file():
        raise WorkbenchError(f"清单文件不存在：{spec.manifest_path}")
    if not spec.media_root.is_dir():
        raise WorkbenchError(f"媒体目录不存在：{spec.media_root}")

    records = load_dataset_records(spec.dataset_path)
    by_id = {record["post_id"]: record for record in records}
    dataset_ids = [record["post_id"] for record in records]

    if spec.manifest_path is not None:
        ordered_ids = load_manifest_ids(spec.manifest_path)
        if not ordered_ids:
            raise ManifestError("post_id 清单为空")
        validation = validate_manifest(ordered_ids, dataset_ids)
    else:
        ordered_ids = dataset_ids
        validation = {
            "post_count": len(dataset_ids),
            "duplicate_count": 0,
            "missing_count": 0,
            "ordered_post_ids_sha256": sha256_text("\n".join(dataset_ids)),
        }

    formal_gold_allowed = spec.manifest_role == "approved"
    warnings: List[str] = []
    if spec.manifest_path is None:
        warnings.append(
            "未提供固定 post_id 批准清单：本次只能作为探索性试标，不能宣称正式 Gold。"
        )
        if spec.manifest_role == "approved":
            warnings.append(
                "manifest_role=approved 但没有提供固定 post_id 清单；"
                "formal_gold_allowed 已强制为 false。"
            )
    elif spec.manifest_role == "exploratory":
        warnings.append(
            "清单用途声明为 exploratory：本次只能作为探索性试标，不能宣称正式 Gold。"
        )
    else:
        warnings.append(
            "清单用途声明为 approved：工具只记录该声明，不替代人工批准审计；"
            "仍需确认清单来源与数据门禁。"
        )
    if spec.manifest_role == "approved" and spec.manifest_path is None:
        formal_gold_allowed = False

    batch_dir = spec.output_root / spec.dataset_id / spec.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    prepared = PreparedBatch(
        spec=spec,
        records=records,
        by_id=by_id,
        ordered_ids=ordered_ids,
        manifest={},
        warnings=warnings,
        batch_dir=batch_dir,
        formal_gold_allowed=formal_gold_allowed,
        manifest_validation=validation,
    )
    meta = _batch_meta(prepared)
    manifest_path = batch_dir / "batch_manifest.json"
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ManifestError(f"已有 batch_manifest.json 无法解析：{exc}") from exc
        existing_digest = sha256_text(
            json.dumps(
                {key: value for key, value in existing.items() if key != "_sha256"},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        if existing.get("_sha256") != existing_digest:
            raise ManifestError("已有 batch_manifest.json 的 _sha256 自校验失败；拒绝在可疑批次上继续标注")
        ignore = {"created_at"}
        differences = []
        for key, value in meta.items():
            if key in ignore:
                continue
            if existing.get(key) != value:
                differences.append(f"{key}: 已有={existing.get(key)!r} 当前={value!r}")
        if differences:
            raise ManifestError(
                "批次元数据不匹配，拒绝混用数据/批次/清单（防止不同批次或不同人的标签互相覆盖）：\n"
                + "\n".join(differences)
            )
        prepared.manifest = existing
    else:
        payload = dict(meta)
        payload["_sha256"] = sha256_text(json.dumps(meta, ensure_ascii=False, sort_keys=True))
        encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        try:
            fd = os.open(str(manifest_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            prepared.manifest = existing
        else:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            prepared.manifest = payload
        if prepared.manifest.get("_sha256") != sha256_text(
            json.dumps({k: v for k, v in prepared.manifest.items() if k != "_sha256"},
                       ensure_ascii=False, sort_keys=True)
        ):
            raise ManifestError("batch_manifest.json 的 _sha256 自校验失败")
    return prepared


class InstanceLock:
    """Best-effort single-process lock so two tabs cannot share one annotator."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(path, "a+b")
        try:
            self._handle.seek(0)
            if self._handle.read(1) == b"":
                self._handle.write(b"0")
                self._handle.flush()
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._handle.close()
            raise WorkbenchError(
                f"标注人 {path.parent.name!r} 已被另一个工作台实例占用；"
                "请关闭其他窗口，或为不同标注人使用不同 annotator_id。"
            ) from exc

    def close(self) -> None:
        try:
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._handle.close()


def _evidence_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = re.split(r"[\n;；]+", value)
    elif isinstance(value, list):
        raw_items = value
    else:
        raise ValidationError("evidence 必须是字符串数组或换行分隔的字符串")
    result: List[str] = []
    for item in raw_items:
        text = _as_text(item, 2000).strip()
        if text:
            result.append(text)
    return result


def validate_annotation_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the human-entered fields against the guide contract."""
    if not isinstance(payload, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    label = str(payload.get("label") or "").strip()
    if label in {"mingguang", "anguang", "feiguang", "explicit", "implicit", "non_ad"}:
        label = {
            "mingguang": "明广", "anguang": "暗广", "feiguang": "非广",
            "explicit": "明广", "implicit": "暗广", "non_ad": "非广",
        }[label]
    if label not in LABELS:
        raise ValidationError(f"label 必须是 {'/'.join(LABELS)} 之一，收到 {label!r}")

    confidence_raw = payload.get("confidence")
    if isinstance(confidence_raw, bool):
        raise ValidationError("confidence 必须是 0-1 的数字")
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError("confidence 必须是 0-1 的数字") from exc
    if not 0.0 <= confidence <= 1.0:
        raise ValidationError("confidence 必须在 0-1 之间")

    codes_raw = payload.get("evidence_codes") or []
    if isinstance(codes_raw, str):
        codes_raw = re.split(r"[\s,，;；、]+", codes_raw)
    if not isinstance(codes_raw, list):
        raise ValidationError("evidence_codes 必须是数组")
    codes: List[str] = []
    for code in codes_raw:
        value = str(code).strip().upper()
        if not value:
            continue
        if value not in EVIDENCE_CODES:
            raise ValidationError(f"未知证据码 {value!r}；只能是 {'/'.join(EVIDENCE_CODES)}")
        if value not in codes:
            codes.append(value)

    evidence = _evidence_list(payload.get("evidence"))
    uncertain_reason = _as_text(payload.get("uncertain_reason"), 4000).strip() or None
    notes = _as_text(payload.get("notes"), 4000).strip() or None

    if "B" in codes and len(codes) == 1:
        raise ValidationError("B（行为线索）只能辅助，不能单独作为证据码")
    if label == "明广" and "D" not in codes:
        raise ValidationError("明广必须包含 D（明确披露/平台商业标识）证据码")
    if label == "暗广" and "D" in codes:
        raise ValidationError("暗广不得包含 D（明确披露）证据码；若确有披露，应判明广")
    if label in {"明广", "暗广"} and not evidence:
        raise ValidationError(f"{label}至少需要一条证据说明")
    if label == "uncertain" and not uncertain_reason:
        raise ValidationError("uncertain 必须填写不确定原因")

    return {
        "label": label,
        "confidence": round(confidence, 4),
        "evidence_codes": codes,
        "evidence": evidence,
        "uncertain_reason": uncertain_reason,
        "notes": notes,
    }


class AnnotationStore:
    """Append-only per-annotator annotation log with replay."""

    def __init__(self, prepared: PreparedBatch):
        self.prepared = prepared
        self.spec = prepared.spec
        self.annotator_dir = prepared.batch_dir / self.spec.annotator_id
        self.annotator_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.annotator_dir / "annotations.jsonl"
        self.lock = InstanceLock(self.annotator_dir / ".lock")
        self._write_lock = threading.Lock()
        self._latest: Dict[str, Dict[str, Any]] = {}
        self._revision = 0
        self.warnings = list(prepared.warnings)
        self._replay()

    @classmethod
    def create(cls, spec: BatchSpec) -> "AnnotationStore":
        return cls(prepare_batch(spec))

    def _expected(self, post_id: str) -> Dict[str, Any]:
        return self.prepared.by_id[post_id]

    def _replay(self) -> None:
        if not self.log_path.exists():
            self.log_path.touch()
            return
        try:
            raw = self.log_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            self.warnings.append("annotations.jsonl 不是 UTF-8，已忽略无法读取的内容。")
            raw = ""
        lines = raw.splitlines()
        last_nonempty = max((i for i, line in enumerate(lines) if line.strip()), default=-1)
        for line_no, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                if line_no == last_nonempty:
                    self.warnings.append(
                        f"annotations.jsonl 第 {line_no + 1} 行（末行）不完整，已忽略；"
                        "该条标注需要重新保存。"
                    )
                else:
                    self.warnings.append(
                        f"annotations.jsonl 第 {line_no + 1} 行损坏，已忽略。"
                    )
                continue
            if not isinstance(record, dict):
                self.warnings.append(f"annotations.jsonl 第 {line_no + 1} 行不是对象，已忽略。")
                continue
            post_id = record.get("post_id")
            if not isinstance(post_id, str) or post_id not in self.prepared.by_id:
                self.warnings.append(
                    f"annotations.jsonl 第 {line_no + 1} 行 post_id 不在当前批次，已忽略。"
                )
                continue
            mismatch = [
                key for key in ("dataset_id", "batch_id", "annotator_id")
                if record.get(key) != getattr(self.spec, key)
            ]
            if mismatch:
                self.warnings.append(
                    f"annotations.jsonl 第 {line_no + 1} 行 {', '.join(mismatch)} 不匹配，已忽略。"
                )
                continue
            manifest_sha = self.prepared.manifest.get("_sha256")
            if record.get("batch_manifest_sha256") not in (None, manifest_sha):
                self.warnings.append(
                    f"annotations.jsonl 第 {line_no + 1} 行批次清单哈希不匹配，已忽略。"
                )
                continue
            try:
                validate_annotation_input(record)
            except ValidationError as exc:
                self.warnings.append(
                    f"annotations.jsonl 第 {line_no + 1} 行标注字段无效（{exc}），已忽略。"
                )
                continue
            try:
                revision = int(record.get("revision", 0))
            except (TypeError, ValueError):
                revision = 0
            self._revision = max(self._revision, revision)
            self._latest[post_id] = record

    def save(
        self,
        post_id: str,
        payload: Dict[str, Any],
        *,
        annotation_method: str,
        saw_model_advice: bool,
        model_advice_status: str = "not_requested",
        model: Optional[str] = None,
        model_advice_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        if post_id not in self.prepared.by_id:
            raise NotFoundError(f"post_id 不在当前批次：{post_id}")
        if annotation_method not in {"human", "human_assisted"}:
            raise ValidationError("annotation_method 只能是 human 或 human_assisted")
        cleaned = validate_annotation_input(payload)
        with self._write_lock:
            previous = self._latest.get(post_id)
            if previous and previous.get("annotation_method") == "human_assisted":
                annotation_method = "human_assisted"
            revision = max(
                int(previous.get("revision", 0)) if previous else 0,
                self._revision,
            ) + 1
            now = iso_now()
            record = {
                "schema_version": SCHEMA_VERSION,
                "record_type": RECORD_TYPE,
                "post_id": post_id,
                "dataset_id": self.spec.dataset_id,
                "batch_id": self.spec.batch_id,
                "annotator_id": self.spec.annotator_id,
                "label": cleaned["label"],
                "confidence": cleaned["confidence"],
                "evidence_codes": cleaned["evidence_codes"],
                "evidence": cleaned["evidence"],
                "uncertain_reason": cleaned["uncertain_reason"],
                "notes": cleaned["notes"],
                "annotation_method": annotation_method,
                "saw_model_advice": bool(saw_model_advice),
                "model_advice_status": model_advice_status,
                "model": model,
                "model_advice_label": model_advice_label,
                "guide_version": self.spec.guide_version,
                "guide_sha256": self.spec.guide_sha256,
                "annotated_at": (previous or {}).get("annotated_at") or now,
                "updated_at": now,
                "revision": revision,
                "batch_manifest_sha256": self.prepared.manifest.get("_sha256"),
                "manifest_role": self.spec.manifest_role,
                "formal_gold_allowed": self.prepared.formal_gold_allowed,
            }
            encoded = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            with self.log_path.open("ab") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            self._revision = revision
            self._latest[post_id] = record
            return record

    def get(self, post_id: str) -> Optional[Dict[str, Any]]:
        return self._latest.get(post_id)

    def stats(self) -> Dict[str, Any]:
        counts = Counter(record["label"] for record in self._latest.values())
        done = len(self._latest)
        return {
            "done": done,
            "total": len(self.prepared.ordered_ids),
            "remaining": len(self.prepared.ordered_ids) - done,
            "counts": {label: counts.get(label, 0) for label in LABELS},
            "assisted": sum(
                1 for record in self._latest.values()
                if record.get("annotation_method") == "human_assisted"
            ),
        }

    def export_records(self) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for index, post_id in enumerate(self.prepared.ordered_ids):
            record = self._latest.get(post_id)
            if record is None:
                continue
            exported = dict(record)
            exported["export_sequence"] = index
            records.append(exported)
        return records

    def close(self) -> None:
        self.lock.close()
