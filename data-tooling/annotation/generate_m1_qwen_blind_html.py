"""Generate isolated HTML interfaces for the M1 Qwen blind human review.

The generated pages deliberately contain only source evidence and the fixed
annotation guide.  They do not contain model labels, model confidence, model
reasoning, or the other reviewer's answers.  A reviewer works in one role
directory, exports a JSON file locally, and hands that JSON to the coordinator
without exposing it to the other reviewer.

This module uses only the Python standard library so it can be run from the
repository's existing annotation environment or from a clean interpreter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote, urlsplit, urlunsplit


SCHEMA_VERSION = "m1_blind_html_delivery_v2"
REVIEW_SCHEMA_VERSION = "m1_blind_human_review_v2"
DEFAULT_ROLES = ("A", "B")
_BILIBILI_VIDEO_PATH = re.compile(r"^/video/(BV[0-9A-Za-z]{8,20})/?$")
LABELS = (
    ("明广", "明广 — 明确商业/推广表达"),
    ("暗广", "暗广 — 商业推广但表达较隐蔽"),
    ("非广", "非广 — 当前证据不足以认定广告"),
    ("uncertain", "uncertain — 证据不足或存在冲突"),
    ("out_of_scope", "out_of_scope — 不在本批任务范围"),
)
EVIDENCE_CODES = (
    ("D", "披露/广告标识"),
    ("C", "行动号召或转化路径"),
    ("P", "价格、优惠或购买信息"),
    ("A", "品牌/商品/服务指向"),
    ("V", "媒体中的可见推广证据"),
    ("M", "评论或互动中的推广证据"),
    ("B", "账号/主体/背景证据"),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _json_for_script(value: Any) -> str:
    """Serialize JSON while preventing data from prematurely closing script."""

    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL record at {path}:{line_number} is not an object")
            rows.append(value)
    return rows


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, indent=2)


def _safe_relative_media_path(media_base: Path, ref: str) -> Path:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("media reference must be a non-empty relative string")
    candidate = Path(ref)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"media reference escapes media base: {ref!r}")
    base_resolved = media_base.resolve()
    resolved = (media_base / candidate).resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError(f"media reference escapes media base: {ref!r}") from exc
    return resolved


def _safe_remote_video_url(value: Any) -> str:
    """Return a canonical allowlisted Bilibili video URL or an empty string.

    Remote evidence is deliberately narrower than arbitrary source links.  The
    generated HTML may only navigate to a normal HTTPS Bilibili ``/video/BV``
    page; credentials, ports, unrelated paths and active URL schemes are never
    copied into the page.  Query strings and fragments are discarded so both
    reviewers receive the same stable entry URL.
    """

    raw = _as_text(value).strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return ""
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or hostname not in {"bilibili.com", "www.bilibili.com"}
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
    ):
        return ""
    match = _BILIBILI_VIDEO_PATH.fullmatch(parsed.path)
    if not match:
        return ""
    return urlunsplit(("https", "www.bilibili.com", f"/video/{match.group(1)}", "", ""))


def _media_type(raw: Mapping[str, Any], ref: str) -> str:
    kind = _as_text(raw.get("type") or raw.get("media_type") or "").lower()
    if kind in {"video", "视频", "mp4", "mov", "webm"}:
        return "video"
    if kind in {"audio", "音频", "mp3", "wav"}:
        return "audio"
    suffix = Path(ref).suffix.lower()
    if suffix in {".mp4", ".mov", ".webm", ".m4v", ".avi", ".mkv"}:
        return "video"
    if suffix in {".mp3", ".wav", ".m4a", ".ogg"}:
        return "audio"
    return "image"


def _source_comments(row: Mapping[str, Any]) -> list[dict[str, str]]:
    comments = row.get("comments")
    if not isinstance(comments, list):
        return []
    output: list[dict[str, str]] = []
    for index, comment in enumerate(comments, 1):
        if isinstance(comment, Mapping):
            comment_id = _as_text(comment.get("comment_id") or comment.get("id") or f"comment_{index}")
            text = _as_text(comment.get("text") or comment.get("content") or "")
        else:
            comment_id = f"comment_{index}"
            text = _as_text(comment)
        output.append({"comment_id": comment_id, "text": text})
    return output


def _source_media(
    row: Mapping[str, Any], media_base: Path, html_parent: Path
) -> list[dict[str, Any]]:
    raw_media = row.get("media")
    if not isinstance(raw_media, list):
        raw_media = row.get("media_items")
    if not isinstance(raw_media, list):
        return []
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_media, 1):
        if not isinstance(raw, Mapping):
            continue
        ref = _as_text(raw.get("ref") or raw.get("path") or raw.get("media_ref"))
        media_type = _media_type(raw, ref)
        remote_url = (
            _safe_remote_video_url(raw.get("source_url") or raw.get("url"))
            if media_type == "video"
            else ""
        )
        remote_key = (
            "remote_"
            + str(index)
            + "_"
            + hashlib.sha256(remote_url.encode("utf-8")).hexdigest()[:12]
            if remote_url
            else ""
        )
        if not ref:
            # A narrowly allowlisted source page is usable as unpinned remote
            # evidence.  Everything else remains an explicit evidence gap.
            result.append(
                {
                    "number": index,
                    "type": media_type,
                    "ref": "",
                    "local_url": "",
                    "local_exists": False,
                    "remote_url": remote_url,
                    "remote_key": remote_key,
                    "remote_available": bool(remote_url),
                    "evidence_mode": "remote_link" if remote_url else "unavailable",
                    "missing_reason": "" if remote_url else "source_record_has_no_local_ref",
                }
            )
            continue
        local_path = _safe_relative_media_path(media_base, ref)
        try:
            relative = os.path.relpath(local_path, html_parent.resolve())
        except ValueError:
            relative = ""
        local_url = quote(relative.replace(os.sep, "/"), safe="/-._~") if local_path.is_file() else ""
        local_exists = local_path.is_file()
        # Prefer the pinned local copy.  Only expose the allowlisted source
        # link as a fallback when the declared local ref cannot be opened.
        fallback_remote_url = "" if local_exists else remote_url
        fallback_remote_key = "" if local_exists else remote_key
        result.append(
            {
                "number": index,
                "type": media_type,
                "ref": ref,
                "local_url": local_url,
                "local_exists": local_exists,
                "remote_url": fallback_remote_url,
                "remote_key": fallback_remote_key,
                "remote_available": bool(fallback_remote_url),
                "evidence_mode": (
                    "local"
                    if local_exists
                    else "remote_link"
                    if fallback_remote_url
                    else "unavailable"
                ),
                "missing_reason": (
                    "" if local_exists or fallback_remote_url else "local_file_not_found"
                ),
            }
        )
    return result


def _prepare_items(
    manifest: Mapping[str, Any],
    source_rows: Sequence[Mapping[str, Any]],
    media_base: Path,
    html_parent: Path,
) -> list[dict[str, Any]]:
    manifest_items = manifest.get("items")
    if not isinstance(manifest_items, list) or not manifest_items:
        raise ValueError("blind manifest must contain a non-empty items list")
    by_id: dict[str, Mapping[str, Any]] = {}
    for row in source_rows:
        post_id = _as_text(row.get("post_id"))
        if not post_id:
            continue
        if post_id in by_id:
            raise ValueError(f"duplicate post_id in source JSONL: {post_id}")
        by_id[post_id] = row

    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for fallback_ordinal, selected in enumerate(manifest_items, 1):
        if not isinstance(selected, Mapping):
            raise ValueError("manifest item is not an object")
        post_id = _as_text(selected.get("post_id"))
        if not post_id or post_id in seen:
            raise ValueError(f"invalid or duplicate manifest post_id: {post_id!r}")
        seen.add(post_id)
        row = by_id.get(post_id)
        if row is None:
            raise ValueError(f"manifest post_id is absent from source JSONL: {post_id}")
        media = _source_media(row, media_base, html_parent)
        comments = _source_comments(row)
        item = {
            "ordinal": int(selected.get("ordinal") or fallback_ordinal),
            "post_id": post_id,
            "platform": _as_text(row.get("platform") or selected.get("platform")),
            "published_at": _as_text(row.get("published_at")),
            "title": _as_text(row.get("title")),
            "text": _as_text(row.get("text") or row.get("content")),
            "comments": comments,
            "media": media,
            "evidence_state": {
                "media_collection_completeness": "unknown",
                "comment_collection_completeness": "unknown",
                "disclosure_collection_completeness": "unknown",
            },
        }
        items.append(item)
    expected_count = manifest.get("sample_count")
    if expected_count is not None and int(expected_count) != len(items):
        raise ValueError(
            f"manifest sample_count={expected_count} does not match items={len(items)}"
        )
    return items


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _role_readme(
    role: str,
    manifest_sha: str,
    guide_sha: str,
    remote_link_media_count: int,
    unavailable_media_count: int,
) -> str:
    return f"""# M1 全新独立人工盲测 — 角色 {role}

这是同一仓库内的本地 HTML 人工标注入口。页面只展示固定清单中的原始证据、媒体和统一标注指南，不展示模型建议，也不展示另一位标注人的答案。

## 使用

1. 先阅读 `../COORDINATOR/annotation_guide_v1.md`，确认页面顶部的独立性声明。
2. 仅打开本目录的 `M1_Blind_Human_Review_{role}.html`；不要打开另一角色目录或其导出 JSON。
3. 逐条阅读标题、正文、评论和可用媒体。对每条选择标签、置信度、证据代码和证据说明，并勾选已复核。
4. 有媒体时必须逐个检查：本地媒体在页面内打开；在线源视频点击“在新标签页打开源视频”，观看后返回页面，明确选择“已成功打开并检查视频”或“链接无法访问或内容不可用”。仅点击链接不算完成。
5. 通过页面校验后点击“导出 JSON”，把下载的 `M1_Blind_Human_Review_{role}.json` 交给协调人。不要手工改 JSON。

## 固定输入

- manifest SHA-256: `{manifest_sha}`
- guide SHA-256: `{guide_sha}`
- 本地媒体：仓库内相对路径。
- 在线源视频：只允许页面内已固定的 HTTPS Bilibili `/video/BV...` 入口；不要搜索替代视频、下载补抓、登录后改链或替换样本。

本批有 `{remote_link_media_count}` 个媒体仅有在线源视频入口，远程内容本身没有纳入本包 SHA，导出状态会标记为 `completed_with_remote_unpinned_media_evidence`。另有 `{unavailable_media_count}` 个媒体既无可用本地文件也无允许的在线入口。若在线链接打不开或出现后者，必须选择/记录证据缺口并勾选全局缺口声明；导出状态为 `completed_with_declared_evidence_gaps`。任何一种状态都不能把未看到的媒体解释为“没有媒体”，也不能直接作为最终质量结论。

本目录的导出结果只用于 Qwen 工程质量校准，不得写入正式 Gold、locked_batches、正式候选或其他正式 M1 证据。若链接不可访问、页面提示媒体缺失或导出校验失败，请记录 `post_id` 后联系协调人；不要自行换源。
"""


def _coordinator_readme(
    roles: Sequence[str],
    manifest_sha: str,
    guide_sha: str,
    remote_link_media_count: int,
    unavailable_media_count: int,
) -> str:
    role_lines = "\n".join(
        f"- 角色 {role}: `../{role}/M1_Blind_Human_Review_{role}.html`，导出文件名为 `M1_Blind_Human_Review_{role}.json`"
        for role in roles
    )
    return f"""# M1 HTML 盲测交付包（协调人说明）

状态：`awaiting_A_B_blind_labels`。本包是 Qwen 工程质量校准用的全新 A/B 独立人工盲测入口，当前没有任何人工标签、裁决或模型运行结果。

## 入口

{role_lines}

每个角色只能使用自己的目录；协调人在两份 JSON 都交付前只保存文件路径和 SHA-256，不向任一标注人展示另一份 JSON。

## 固定输入和完整性

- `manifest_blind_sample.json`：固定 21 条样本清单，SHA-256 `{manifest_sha}`。
- `annotation_guide_v1.md`：只读标注指南，SHA-256 `{guide_sha}`。
- HTML 对本地媒体使用相对路径；便携包必须保留这些文件的目录结构。
- 当前源数据中有 `{remote_link_media_count}` 个媒体仅有受限的 HTTPS Bilibili 源视频入口，远程内容未纳入 SHA。页面记录点击时间和人工查看状态；成功查看后的导出为 `completed_with_remote_unpinned_media_evidence`，仍不等同于可复现的本地媒体证据。
- 另有 `{unavailable_media_count}` 个媒体既无可用本地文件也无允许的在线入口。在线入口被标注为不可用时也属于证据缺口，导出为 `completed_with_declared_evidence_gaps`；协调人不得把它当作媒体完整的人工质量结论。
- `SHA256SUMS.txt` 覆盖交付目录内除自身外的所有文件；重新生成或移动后应重新核验。

## 交付后

1. 先只核验两份 JSON 的角色、清单 SHA、21 个唯一 `post_id`、标签集合、媒体审计和独立性声明。
2. 在 A/B 原始 JSON 封存并记录 SHA 后，才可以开始另一个全新的裁决文件。
3. 在人工盲测和裁决完成前，不得运行“人工后 Qwen”路线，也不得把本包写入正式 Gold、locked_batches 或正式候选。
"""


def _html_for_role(
    role: str,
    items: Sequence[Mapping[str, Any]],
    guide_text: str,
    metadata: Mapping[str, Any],
) -> str:
    meta_json = _json_for_script(metadata)
    items_json = _json_for_script(items)
    guide_json = _json_for_script(guide_text)
    labels_json = _json_for_script(
        [{"value": value, "text": text} for value, text in LABELS]
    )
    evidence_json = _json_for_script(
        [{"value": value, "text": text} for value, text in EVIDENCE_CODES]
    )
    # The template is intentionally self-contained.  Runtime evidence is
    # either a local relative media path or a narrowly allowlisted HTTPS
    # Bilibili video page embedded in each item.
    template = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>M1 全新独立人工盲测 — 角色 __ROLE__</title>
  <style>
    :root{color-scheme:light;--ink:#172033;--muted:#5b667a;--line:#d9dfeb;--bg:#f5f7fb;--card:#fff;--accent:#2457a6;--warn:#9a5b00;--bad:#a32626;--ok:#18734a}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
    header{background:#132b52;color:#fff;padding:22px max(18px,calc((100vw - 1500px)/2));position:sticky;top:0;z-index:5;box-shadow:0 2px 8px #0002}
    h1{margin:0 0 5px;font-size:23px}h2{font-size:19px;margin:0 0 10px}h3{font-size:16px;margin:0 0 8px}.sub{opacity:.85;font-size:13px}
    .toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:14px}.toolbar button,.toolbar label.button{background:#fff;color:var(--accent);border:1px solid #b9c8e4;border-radius:6px;padding:7px 11px;cursor:pointer;font-weight:600}.toolbar button.primary{background:#ffd45c;border-color:#ffd45c;color:#172033}.toolbar button.danger{color:var(--bad)}
    .layout{max-width:1500px;margin:18px auto;padding:0 18px;display:grid;grid-template-columns:290px minmax(0,1fr);gap:18px}.panel,.item{background:var(--card);border:1px solid var(--line);border-radius:9px;box-shadow:0 1px 2px #18233a0a}.panel{padding:14px;align-self:start;position:sticky;top:145px}.panel h2{font-size:16px}.panel p{margin:7px 0;color:var(--muted)}.panel .notice{background:#fff8e7;border:1px solid #efd39c;padding:9px;border-radius:6px;color:#714900;font-size:13px}.nav-list{max-height:48vh;overflow:auto;margin-top:10px}.nav-row{display:flex;width:100%;text-align:left;border:0;border-bottom:1px solid #edf0f5;background:transparent;padding:8px 5px;cursor:pointer;gap:7px;align-items:center}.nav-row:hover,.nav-row.active{background:#edf4ff}.nav-row .state{margin-left:auto;font-size:12px;color:var(--muted)}.nav-row.done .state{color:var(--ok)}
    .attestation{background:#eef5ff;border:1px solid #c6d8f5;padding:12px;border-radius:8px;margin-bottom:18px}.attestation-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px}.field{display:flex;flex-direction:column;gap:4px}.field.inline{display:flex;flex-direction:row;align-items:center}.field input[type=text],.field input[type=number],select,textarea{border:1px solid #bfc9da;border-radius:5px;padding:7px;font:inherit;background:#fff;color:var(--ink)}textarea{min-height:74px;resize:vertical}.attestation label{font-size:13px}.attestation .checks{display:grid;gap:5px;margin-top:9px}.progress{height:10px;background:#e5eaf2;border-radius:99px;overflow:hidden;margin:8px 0}.progress>span{display:block;height:100%;background:#2e8b63;width:0;transition:width .2s}.summary{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:13px}
    .item{padding:18px;margin-bottom:18px;scroll-margin-top:150px}.item-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:10px}.item-title{font-size:18px;font-weight:700;white-space:pre-wrap}.item-meta{color:var(--muted);font-size:13px}.badge{display:inline-block;padding:2px 7px;border-radius:99px;background:#edf0f5;color:#47536a;font-size:12px}.badge.warn{background:#fff0d1;color:#825000}.evidence-warning{margin:12px 0;background:#fff8e7;border-left:4px solid #d99327;padding:9px 11px;color:#714900}.post-text{white-space:pre-wrap;overflow-wrap:anywhere;background:#fafbfe;border:1px solid #edf0f5;border-radius:6px;padding:12px;max-height:520px;overflow:auto}.comments{margin-top:12px}.comment{border-left:3px solid #d9e2f2;padding:4px 10px;margin:5px 0;white-space:pre-wrap;overflow-wrap:anywhere}.media-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:9px;margin-top:8px}.media-card{border:1px solid var(--line);border-radius:7px;padding:8px;background:#fbfcff}.media-card button.media-open{display:block;width:100%;border:0;background:transparent;padding:0;cursor:pointer}.media-card img,.media-card video{display:block;width:100%;height:120px;object-fit:contain;background:#10141d;border-radius:4px}.media-card audio{width:100%;margin:45px 0 40px}.media-ref{font-size:11px;color:var(--muted);word-break:break-all;margin-top:4px}.media-card.viewed{border-color:#44a77a;background:#f0fff7}.media-card.remote{border-color:#9ebbe8;background:#f2f7ff}.media-card.missing{border-color:#e2a2a2;background:#fff3f3}.remote-link{display:block;text-align:center;background:var(--accent);color:#fff;border-radius:6px;padding:10px 8px;text-decoration:none;font-weight:700;margin-bottom:8px}.remote-status{display:grid;gap:5px;margin-top:8px;font-size:12px}.remote-status label{display:flex;gap:5px;align-items:flex-start}.media-count{font-size:13px;color:var(--muted)}.controls{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;border-top:1px solid var(--line);margin-top:15px;padding-top:14px}.label-options,.code-options{display:flex;gap:7px;flex-wrap:wrap}.label-options label,.code-options label{border:1px solid #c8d0df;border-radius:6px;padding:6px 8px;background:#fff;cursor:pointer}.label-options label:has(input:checked),.code-options label:has(input:checked){border-color:var(--accent);background:#edf4ff}.label-options input,.code-options input{margin-right:4px}.review-row{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-top:10px}.review-row label{display:flex;gap:6px;align-items:center}.errors{color:var(--bad);font-size:13px;margin-top:7px;white-space:pre-wrap}.saved{color:var(--ok);font-size:12px}.hidden{display:none!important}
    dialog{border:0;border-radius:9px;padding:0;max-width:min(94vw,1100px);max-height:94vh;background:#10141d;color:#fff;box-shadow:0 8px 40px #0008}.lightbox{position:relative;padding:38px 50px 18px;text-align:center}.lightbox img,.lightbox video{max-width:86vw;max-height:76vh;object-fit:contain}.lightbox audio{width:min(75vw,800px);margin:25vh 0}.lightbox button{position:absolute;background:#ffffff22;color:#fff;border:1px solid #fff7;border-radius:5px;padding:8px 12px;cursor:pointer}.lightbox .close{right:10px;top:10px}.lightbox .prev{left:10px;top:50%;}.lightbox .next{right:10px;top:50%}.lightbox .caption{font-size:12px;color:#d4d8e0;word-break:break-all;margin-top:8px}
    @media(max-width:900px){.layout{grid-template-columns:1fr}.panel{position:static}.nav-list{max-height:220px}header{position:static}}
  </style>
</head>
<body>
  <header>
    <h1>M1 全新独立人工盲测 — 角色 __ROLE__</h1>
    <div class="sub">固定样本、固定指南、独立草稿。此页面不提供任何预填答案；完成后仅导出本角色 JSON。</div>
    <div class="toolbar">
      <button id="saveBtn">保存草稿</button><button id="exportBtn" class="primary">校验并导出 JSON</button>
      <label class="button">导入本角色 JSON<input id="importInput" type="file" accept="application/json" hidden></label>
      <button id="resetBtn" class="danger">清空本角色草稿</button>
      <label>筛选 <select id="filterSelect"><option value="all">全部</option><option value="todo">未完成</option><option value="done">已完成</option><option value="uncertain">uncertain</option></select></label>
    </div>
  </header>
  <div class="layout">
    <aside class="panel">
      <h2>当前批次</h2>
      <p id="batchInfo"></p>
      <div class="notice">只使用本角色入口。评论、媒体和披露完整性均按“未知”处理；不能把未采集到的证据当作不存在。</div>
      <div class="progress"><span id="progressBar"></span></div>
      <div class="summary"><span id="progressText"></span><span id="mediaText"></span></div>
      <div class="nav-list" id="navList"></div>
    </aside>
    <main>
      <section class="attestation">
        <h2>独立性声明（导出前全部勾选）</h2>
        <div class="attestation-grid">
          <label class="field">标注人姓名/代号<input id="reviewerName" type="text" autocomplete="off"></label>
          <label class="field">标注人 ID<input id="reviewerId" type="text" autocomplete="off"></label>
        </div>
        <div class="checks">
          <label><input id="attGuide" type="checkbox"> 我已阅读页面内固定标注指南，并按指南独立判断。</label>
          <label><input id="attNoAnswers" type="checkbox"> 我未查看另一位标注人的答案、旧答案或模型建议。</label>
          <label><input id="attIndependent" type="checkbox"> 本次标签、置信度和证据说明由我本人完成，没有让 AI 代填。</label>
          <label><input id="attEvidence" type="checkbox"> 我逐条检查了可见正文、评论和全部可用媒体；远程视频仅在成功打开并观看后标记为已检查，并理解“集合完整性未知”。</label>
          <label><input id="attMediaGaps" type="checkbox"> 若页面存在不可用媒体或在线链接无法访问，我已逐条记录证据缺口，没有把缺失误认为“没有媒体”。</label>
        </div>
        <div id="globalMessage" class="errors"></div>
      </section>
      <section id="guideSection" class="panel" style="position:static;margin-bottom:18px">
        <h2>固定标注指南</h2>
        <details><summary>展开/收起指南全文</summary><pre id="guideText" class="post-text"></pre></details>
      </section>
      <div id="items"></div>
    </main>
  </div>
  <dialog id="lightbox"><div class="lightbox"><button class="close" id="lightboxClose">关闭</button><button class="prev" id="lightboxPrev">上一项</button><button class="next" id="lightboxNext">下一项</button><div id="lightboxBody"></div><div id="lightboxCaption" class="caption"></div></div></dialog>
  <script>
  "use strict";
  const META=__META_JSON__;
  const ITEMS=__ITEMS_JSON__;
  const GUIDE_TEXT=__GUIDE_JSON__;
  const LABELS=__LABELS_JSON__;
  const EVIDENCE_CODES=__EVIDENCE_JSON__;
  const ROLE=__ROLE_JSON__;
  const REVIEW_SCHEMA_VERSION=__REVIEW_SCHEMA_JSON__;
  const STORAGE_KEY="m1_blind_review_v2:"+META.manifest_sha256+":"+ROLE;
  const state={attestation:{reviewer_name:"",reviewer_id:"",read_guide:false,no_other_answers:false,independent:false,evidence_checked:false,media_gaps_ack:false},records:{}};
  let filter="all";let lightboxItem=null;let lightboxIndex=0;
  const $=id=>document.getElementById(id);
  const esc=value=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch]));
  const itemKey=item=>item.post_id;
  function emptyRecord(){return {label:"",confidence:"",evidence_codes:[],evidence:"",uncertain_reason:"",reviewed:false,media_review_confirmed:false,viewed_media_refs:[],remote_media_statuses:{},remote_open_attempts:{},reviewed_at:""};}
  function ensureRecords(){ITEMS.forEach(item=>{if(!state.records[itemKey(item)])state.records[itemKey(item)]=emptyRecord();const r=state.records[itemKey(item)];if(!Array.isArray(r.viewed_media_refs))r.viewed_media_refs=[];if(!r.remote_media_statuses||typeof r.remote_media_statuses!=="object"||Array.isArray(r.remote_media_statuses))r.remote_media_statuses={};if(!r.remote_open_attempts||typeof r.remote_open_attempts!=="object"||Array.isArray(r.remote_open_attempts))r.remote_open_attempts={};});}
  function save(){localStorage.setItem(STORAGE_KEY,JSON.stringify({schema_version:REVIEW_SCHEMA_VERSION,role:ROLE,manifest_sha256:META.manifest_sha256,state}));setMessage("草稿已保存在本浏览器的本角色隔离空间。",false);renderNav();}
  function load(){try{const raw=localStorage.getItem(STORAGE_KEY);if(!raw)return;const parsed=JSON.parse(raw);if(parsed.role!==ROLE||parsed.manifest_sha256!==META.manifest_sha256)return;if(parsed.state&&typeof parsed.state==="object"){Object.assign(state,parsed.state);}}catch(error){setMessage("已有草稿无法读取，已使用空白草稿："+error,false);}ensureRecords();}
  function setMessage(message,bad=true){$("globalMessage").textContent=message||"";$("globalMessage").style.color=bad?"var(--bad)":"var(--ok)";}
  function recordFor(item){return state.records[itemKey(item)];}
  function fixedMediaMissing(item){return item.media.some(media=>!media.local_exists&&!media.remote_available);}
  function remoteMediaGap(item,r){return item.media.some(media=>media.remote_available&&r.remote_media_statuses[media.remote_key]==="unavailable");}
  function allMediaViewed(item,r){return item.media.filter(media=>media.local_exists).every(media=>r.viewed_media_refs.includes(media.ref));}
  function allRemoteMediaResolved(item,r){return item.media.filter(media=>media.remote_available).every(media=>{const status=r.remote_media_statuses[media.remote_key];return status==="unavailable"||status==="reviewed"&&Boolean(r.remote_open_attempts[media.remote_key]);});}
  function allMediaReviewed(item,r){return allMediaViewed(item,r)&&allRemoteMediaResolved(item,r);}
  function isDone(item){const r=recordFor(item);const hasGap=fixedMediaMissing(item)||remoteMediaGap(item,r);return Boolean(r&&r.label&&r.confidence!==""&&r.evidence.trim()&&r.reviewed&&(item.media.length===0||r.media_review_confirmed&&allMediaReviewed(item,r))&&(!hasGap||state.attestation.media_gaps_ack)&&(r.label!=="uncertain"||r.uncertain_reason.trim()));}
  function syncAttestation(){state.attestation={reviewer_name:$("reviewerName").value.trim(),reviewer_id:$("reviewerId").value.trim(),read_guide:$("attGuide").checked,no_other_answers:$("attNoAnswers").checked,independent:$("attIndependent").checked,evidence_checked:$("attEvidence").checked,media_gaps_ack:$("attMediaGaps").checked};}
  function loadAttestation(){const a=state.attestation||{};$("reviewerName").value=a.reviewer_name||"";$("reviewerId").value=a.reviewer_id||"";$("attGuide").checked=Boolean(a.read_guide);$("attNoAnswers").checked=Boolean(a.no_other_answers);$("attIndependent").checked=Boolean(a.independent);$("attEvidence").checked=Boolean(a.evidence_checked);$("attMediaGaps").checked=Boolean(a.media_gaps_ack);}
  function labelOptions(item,r){return LABELS.map(x=>`<label><input type="radio" name="label_${esc(item.post_id)}" value="${esc(x.value)}" ${r.label===x.value?"checked":""}>${esc(x.text)}</label>`).join("");}
  function codeOptions(item,r){return EVIDENCE_CODES.map(x=>`<label><input type="checkbox" class="evidence-code" value="${esc(x.value)}" ${r.evidence_codes.includes(x.value)?"checked":""}>${esc(x.value)} ${esc(x.text)}</label>`).join("");}
  function mediaMarkup(item,r){if(!item.media.length)return `<p class="media-count">本条没有媒体记录；请仍在“媒体已检查”处确认没有媒体需要查看。</p>`;const local=item.media.filter(media=>media.local_exists);const remote=item.media.filter(media=>media.remote_available);const unavailable=item.media.filter(media=>!media.local_exists&&!media.remote_available);const localViewed=local.filter(media=>r.viewed_media_refs.includes(media.ref)).length;const remoteResolved=remote.filter(media=>Boolean(r.remote_media_statuses[media.remote_key])).length;return `<div class="media-count">本地已打开 ${localViewed}/${local.length} · 在线源视频已确认 ${remoteResolved}/${remote.length}${unavailable.length?` · 固定证据缺口 ${unavailable.length}`:""}</div><div class="media-grid">${item.media.map((media,index)=>{if(media.local_exists&&media.local_url){const viewed=r.viewed_media_refs.includes(media.ref);let body="";if(media.type==="video")body=`<video src="${esc(media.local_url)}" preload="metadata"></video>`;else if(media.type==="audio")body=`<audio controls src="${esc(media.local_url)}"></audio>`;else body=`<img src="${esc(media.local_url)}" alt="本地媒体 ${media.number}">`;return `<div class="media-card${viewed?" viewed":""}" data-post-id="${esc(item.post_id)}" data-media-ref="${esc(media.ref)}"><button class="media-open" data-action="media" data-index="${index}">${body}</button><div class="media-ref">#${media.number} · ${esc(media.type)} · ${esc(media.ref)}</div><div class="media-ref">${viewed?"已打开":"未打开"} · 本地固定媒体</div></div>`;}if(media.remote_available&&media.remote_url){const key=media.remote_key;const status=r.remote_media_statuses[key]||"";const attempted=r.remote_open_attempts[key]||"";const cls=status==="reviewed"?" viewed":status==="unavailable"?" missing":" remote";return `<div class="media-card${cls}" data-post-id="${esc(item.post_id)}" data-remote-key="${esc(key)}"><a class="remote-link" data-action="remote-open" data-index="${index}" href="${esc(media.remote_url)}" target="_blank" rel="noopener noreferrer">在新标签页打开源视频</a><div class="media-ref">#${media.number} · ${esc(media.type)} · 在线源视频（内容未本地固定）</div><div class="media-ref">${attempted?"已记录打开尝试："+esc(attempted):"尚未点击页面内入口"}</div><div class="remote-status"><label><input type="radio" name="remote_${esc(item.post_id)}_${esc(key)}" data-action="remote-status" data-key="${esc(key)}" value="reviewed" ${status==="reviewed"?"checked":""}> 已成功打开并检查视频</label><label><input type="radio" name="remote_${esc(item.post_id)}_${esc(key)}" data-action="remote-status" data-key="${esc(key)}" value="unavailable" ${status==="unavailable"?"checked":""}> 链接无法访问或内容不可用</label></div></div>`;}return `<div class="media-card missing" data-post-id="${esc(item.post_id)}"><div style="height:120px;display:grid;place-items:center;color:var(--bad)">媒体证据不可用</div><div class="media-ref">#${media.number} · ${esc(media.type)} · ${esc(media.ref||"无 ref")}</div><div class="media-ref">既无本地文件，也无允许的在线入口；需显式记录证据缺口</div></div>`;}).join("")}</div>`;}
  function itemMarkup(item){const r=recordFor(item);const comments=item.comments.length?`<div class="comments"><h3>评论（${item.comments.length}）</h3>${item.comments.map(c=>`<div class="comment"><span class="badge">${esc(c.comment_id)}</span> ${esc(c.text)}</div>`).join("")}</div>`:"<div class=\"comments\"><h3>评论</h3><p class=\"item-meta\">当前记录没有可见评论；集合完整性未知。</p></div>";return `<article class="item" id="item_${esc(item.post_id)}" data-post-id="${esc(item.post_id)}"><div class="item-head"><div><div class="item-title">#${item.ordinal} · ${esc(item.title||"（无标题）")}</div><div class="item-meta">post_id: ${esc(item.post_id)} · 平台: ${esc(item.platform||"未知")}${item.published_at?" · 发布时间: "+esc(item.published_at):""}</div></div><span class="badge ${isDone(item)?"":"warn"}">${isDone(item)?"已完成":"待完成"}</span></div><div class="evidence-warning">正文、评论、媒体和披露的采集完整性均为未知。请只根据页面实际可见证据判断；证据不足时选择 uncertain，不要补猜。</div><h3>正文</h3><div class="post-text">${esc(item.text||"（无正文）")}</div>${comments}<h3 style="margin-top:14px">媒体</h3>${mediaMarkup(item,r)}<div class="controls"><div><h3>标签</h3><div class="label-options">${labelOptions(item,r)}</div></div><label class="field">置信度（0–1）<input class="confidence" type="number" min="0" max="1" step="0.01" value="${esc(r.confidence)}" placeholder="例如 0.80"></label><div><h3>证据代码</h3><div class="code-options">${codeOptions(item,r)}</div></div><label class="field">证据说明（必填）<textarea class="evidence" placeholder="只写本条实际看到的证据、位置和判断边界">${esc(r.evidence)}</textarea></label><label class="field uncertain-field">uncertain 原因（选择 uncertain 时必填）<textarea class="uncertain-reason" placeholder="说明缺失、冲突或无法确认之处">${esc(r.uncertain_reason)}</textarea></label></div><div class="review-row"><label><input class="reviewed" type="checkbox" ${r.reviewed?"checked":""}> 我已逐条阅读并完成判断</label><label><input class="media-confirm" type="checkbox" ${r.media_review_confirmed?"checked":""} ${item.media.length===0?"checked":""}> 我已检查本条全部可用媒体（本地逐个打开，远程逐项确认；无媒体时也请确认）</label><span class="saved" data-saved></span></div><div class="errors" data-errors></div></article>`;}
  function renderItems(){const host=$("items");const visible=ITEMS.filter(item=>filter==="all"||filter==="todo"&&!isDone(item)||filter==="done"&&isDone(item)||filter==="uncertain"&&recordFor(item).label==="uncertain");host.innerHTML=visible.map(itemMarkup).join("");visible.forEach(bindItem);renderNav();}
  function bindItem(item){const card=document.querySelector(`[data-post-id="${CSS.escape(item.post_id)}"]`);if(!card)return;const r=recordFor(item);card.querySelectorAll("input[type=radio][name^=label_]").forEach(input=>input.addEventListener("change",()=>{r.label=input.value;updateCard(item,card);}));card.querySelector(".confidence").addEventListener("input",event=>{r.confidence=event.target.value;updateCard(item,card);});card.querySelector(".evidence").addEventListener("input",event=>{r.evidence=event.target.value;});card.querySelector(".uncertain-reason").addEventListener("input",event=>{r.uncertain_reason=event.target.value;});card.querySelectorAll(".evidence-code").forEach(input=>input.addEventListener("change",()=>{r.evidence_codes=[...card.querySelectorAll(".evidence-code:checked")].map(x=>x.value);}));card.querySelector(".reviewed").addEventListener("change",event=>{r.reviewed=event.target.checked;r.reviewed_at=event.target.checked?new Date().toISOString():"";updateCard(item,card);});card.querySelector(".media-confirm").addEventListener("change",event=>{r.media_review_confirmed=event.target.checked;updateCard(item,card);});card.querySelectorAll("[data-action=media]").forEach(button=>button.addEventListener("click",event=>{event.preventDefault();const index=Number(button.dataset.index);markViewed(item,index);openLightbox(item,index);}));card.querySelectorAll("[data-action=remote-open]").forEach(link=>link.addEventListener("click",()=>{markRemoteOpened(item,Number(link.dataset.index));}));card.querySelectorAll("[data-action=remote-status]").forEach(input=>input.addEventListener("change",()=>{r.remote_media_statuses[input.dataset.key]=input.value;save();renderItems();document.querySelector(`[data-post-id="${CSS.escape(item.post_id)}"]`)?.scrollIntoView({block:"start"});}));}
  function updateCard(item,card){const r=recordFor(item);const badge=card.querySelector(".item-head .badge");badge.textContent=isDone(item)?"已完成":"待完成";badge.className="badge "+(isDone(item)?"":"warn");const errors=validateItem(item,r);card.querySelector("[data-errors]").textContent=errors.join("\n");renderNav();}
  function markViewed(item,index){const media=item.media[index];if(!media||!media.local_exists)return;const r=recordFor(item);if(!r.viewed_media_refs.includes(media.ref))r.viewed_media_refs.push(media.ref);renderItems();const card=document.querySelector(`[data-post-id="${CSS.escape(item.post_id)}"]`);if(card)card.scrollIntoView({block:"start"});save();}
  function markRemoteOpened(item,index){const media=item.media[index];if(!media||!media.remote_available||!media.remote_key)return;const r=recordFor(item);r.remote_open_attempts[media.remote_key]=new Date().toISOString();save();}
  function renderNav(){const done=ITEMS.filter(isDone).length;const mediaTotal=ITEMS.reduce((sum,item)=>sum+item.media.length,0);const mediaReviewed=ITEMS.reduce((sum,item)=>{const r=recordFor(item);const local=item.media.filter(media=>media.local_exists&&r.viewed_media_refs.includes(media.ref)).length;const remote=item.media.filter(media=>media.remote_available&&Boolean(r.remote_media_statuses[media.remote_key])).length;return sum+local+remote;},0);$("batchInfo").textContent=`${META.sample_count} 条 · 角色 ${ROLE}${META.remote_link_media_count>0?" · 在线源视频 "+META.remote_link_media_count:""}${META.missing_media_count>0?" · 固定证据缺口 "+META.missing_media_count:""}`;$("progressText").textContent=`完成 ${done}/${ITEMS.length}`;$("mediaText").textContent=`媒体已核验 ${mediaReviewed}/${mediaTotal}`;$("progressBar").style.width=(done/Math.max(1,ITEMS.length)*100)+"%";const rows=ITEMS.filter(item=>filter==="all"||filter==="todo"&&!isDone(item)||filter==="done"&&isDone(item)||filter==="uncertain"&&recordFor(item).label==="uncertain");$("navList").innerHTML=rows.map(item=>`<button class="nav-row ${isDone(item)?"done":""}" data-target="${esc(item.post_id)}"><span>#${item.ordinal}</span><span>${esc((item.title||"（无标题）").slice(0,28))}</span><span class="state">${isDone(item)?"✓":"·"}</span></button>`).join("");$("navList").querySelectorAll("[data-target]").forEach(button=>button.addEventListener("click",()=>{const target=document.querySelector(`[data-post-id="${CSS.escape(button.dataset.target)}"]`);if(target)target.scrollIntoView({behavior:"smooth",block:"start"});else{filter="all";$("filterSelect").value="all";renderItems();setTimeout(()=>document.querySelector(`[data-post-id="${CSS.escape(button.dataset.target)}"]`)?.scrollIntoView({behavior:"smooth",block:"start"}),0);}}));}
  function validateItem(item,r){const errors=[];if(!r.label)errors.push("请选择标签");const confidence=Number(r.confidence);if(r.confidence===""||!Number.isFinite(confidence)||confidence<0||confidence>1)errors.push("置信度必须是 0 到 1 之间的数字");if(!r.evidence.trim())errors.push("请填写证据说明");if(!r.reviewed)errors.push("请勾选已逐条阅读并完成判断");if(item.media.some(media=>media.local_exists)&&!allMediaViewed(item,r))errors.push("请逐个打开所有存在的本地媒体");item.media.filter(media=>media.remote_available).forEach(media=>{const status=r.remote_media_statuses[media.remote_key];if(!status)errors.push(`在线源视频 #${media.number} 必须选择查看结果`);else if(status==="reviewed"&&!r.remote_open_attempts[media.remote_key])errors.push(`在线源视频 #${media.number} 尚未通过页面入口打开，不能标记为已查看`);});if(item.media.length&&!r.media_review_confirmed)errors.push("请确认已检查本条全部可用媒体");if(r.label==="uncertain"&&!r.uncertain_reason.trim())errors.push("uncertain 必须填写原因");return errors;}
  function validateAll(){syncAttestation();const global=[];if(!state.attestation.reviewer_name)global.push("请填写标注人姓名/代号");if(!state.attestation.reviewer_id)global.push("请填写标注人 ID");if(!state.attestation.read_guide)global.push("请确认已阅读固定指南");if(!state.attestation.no_other_answers)global.push("请确认未查看另一位标注人的答案或模型建议");if(!state.attestation.independent)global.push("请确认标签由本人独立完成");if(!state.attestation.evidence_checked)global.push("请确认逐条检查了正文、评论和可用媒体");const remoteUnavailable=ITEMS.reduce((sum,item)=>sum+item.media.filter(media=>media.remote_available&&recordFor(item).remote_media_statuses[media.remote_key]==="unavailable").length,0);if((META.missing_media_count>0||remoteUnavailable>0)&&!state.attestation.media_gaps_ack)global.push(`本批当前有 ${META.missing_media_count+remoteUnavailable} 个媒体证据缺口，请逐条记录后勾选缺口声明`);const details=[];ITEMS.forEach(item=>{const errors=validateItem(item,recordFor(item));if(errors.length)details.push(`#${item.ordinal} ${item.post_id}: ${errors.join("；")}`);});return {global,details};}
  function exportJson(){
    const checked=validateAll();
    if(checked.global.length||checked.details.length){setMessage([...checked.global,...checked.details.slice(0,12)].join("\n"),true);if(checked.details.length){const first=checked.details[0].match(/post_[0-9a-z]+/i)?.[0];if(first){document.querySelector(`[data-post-id="${CSS.escape(first)}"]`)?.scrollIntoView({behavior:"smooth",block:"start"});}}return;}
    const exportedAt=new Date().toISOString();
    const hasDeclaredGap=META.missing_media_count>0||ITEMS.some(item=>remoteMediaGap(item,recordFor(item)));
    const status=hasDeclaredGap?"completed_with_declared_evidence_gaps":META.remote_link_media_count>0?"completed_with_remote_unpinned_media_evidence":"completed_independent_blind_human_review";
    const payload={schema_version:REVIEW_SCHEMA_VERSION,status,role:ROLE,annotation_method:"human",annotator_id:state.attestation.reviewer_id,reviewer_id:state.attestation.reviewer_id,reviewer_name:state.attestation.reviewer_name,exported_at:exportedAt,qwen_visible:false,manifest_sha256:META.manifest_sha256,source_sha256:META.source_sha256,guide_sha256:META.guide_sha256,sample_count:ITEMS.length,media_evidence_summary:{local_media_ref_count:META.local_media_ref_count,remote_link_media_ref_count:META.remote_link_media_count,missing_media_ref_count:META.missing_media_count,remote_content_sha256_available:false},attestation:state.attestation,items:ITEMS.map(item=>{
      const r=recordFor(item);const local=item.media.filter(media=>media.local_exists);const remote=item.media.filter(media=>media.remote_available);const missing=item.media.filter(media=>!media.local_exists&&!media.remote_available);const remoteLinks=remote.map(media=>({media_number:media.number,remote_key:media.remote_key,url:media.remote_url,status:r.remote_media_statuses[media.remote_key],open_attempted_at:r.remote_open_attempts[media.remote_key]||""}));
      return {ordinal:item.ordinal,number:item.ordinal,post_id:item.post_id,reviewed:true,notes:r.evidence.trim(),label:r.label,confidence:Number(r.confidence),evidence_codes:[...r.evidence_codes].sort(),evidence:r.evidence.trim(),uncertain_reason:r.uncertain_reason.trim(),reviewed_at:r.reviewed_at||exportedAt,media_review:{media_ref_count:item.media.length,local_media_ref_count:local.length,remote_link_media_ref_count:remote.length,missing_media_ref_count:missing.length,missing_media_refs:missing.map(media=>media.ref||("media_"+media.number+"_missing")),viewed_unique_media_count:r.viewed_media_refs.length,viewed_media_refs:[...r.viewed_media_refs],remote_media_statuses:{...r.remote_media_statuses},remote_open_attempts:{...r.remote_open_attempts},remote_links:remoteLinks,all_local_media_viewed:local.every(media=>r.viewed_media_refs.includes(media.ref)),all_remote_media_resolved:remote.every(media=>r.remote_media_statuses[media.remote_key]==="unavailable"||r.remote_media_statuses[media.remote_key]==="reviewed"&&Boolean(r.remote_open_attempts[media.remote_key])),media_gap_acknowledged:Boolean(state.attestation.media_gaps_ack),media_review_confirmed:Boolean(r.media_review_confirmed||item.media.length===0)},media_review_audit:{media_ref_count:item.media.length,opened_unique_media_count:r.viewed_media_refs.length+Object.keys(r.remote_open_attempts).length,opened_media_refs:[...r.viewed_media_refs],remote_links:remoteLinks,all_media_evidence_resolved:allMediaReviewed(item,r)}};
    })};
    const blob=new Blob([JSON.stringify(payload,null,2)],{type:"application/json;charset=utf-8"});const link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download=`M1_Blind_Human_Review_${ROLE}.json`;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(link.href),1000);setMessage("校验通过，已导出本角色 JSON。在线源视频记录的是入口、点击时间和人工确认，不代表远程内容已被本地固定。请把文件路径和 SHA-256 交给协调人，不要与另一角色交换。",false);save();
  }
  function importJson(file){const reader=new FileReader();reader.onload=()=>{try{const payload=JSON.parse(String(reader.result));if(payload.schema_version!==REVIEW_SCHEMA_VERSION)throw new Error("JSON 版本不匹配；v1 草稿不能导入远程媒体 v2 页面");if(payload.role!==ROLE||payload.manifest_sha256!==META.manifest_sha256)throw new Error("角色或 manifest SHA 不匹配");if(payload.guide_sha256!==META.guide_sha256||payload.source_sha256!==META.source_sha256)throw new Error("source/guide SHA 不匹配");if(!Array.isArray(payload.items)||payload.items.length!==ITEMS.length)throw new Error("样本数量不匹配");if(Object.keys(payload).some(key=>/model|suggestion|reasoning/i.test(key)))throw new Error("导入文件包含禁止的模型字段");const itemById=new Map(ITEMS.map(item=>[item.post_id,item]));const seen=new Set();const next={};payload.items.forEach(entry=>{const item=itemById.get(entry.post_id);if(!item||seen.has(entry.post_id))throw new Error("导入文件含未知或重复 post_id");seen.add(entry.post_id);const importedStatuses=entry.media_review?.remote_media_statuses||{};const importedAttempts=entry.media_review?.remote_open_attempts||{};const remote_media_statuses={};const remote_open_attempts={};item.media.filter(media=>media.remote_available).forEach(media=>{const status=importedStatuses[media.remote_key];if(status==="reviewed"||status==="unavailable")remote_media_statuses[media.remote_key]=status;const attempt=importedAttempts[media.remote_key];if(typeof attempt==="string"&&attempt)remote_open_attempts[media.remote_key]=attempt;});next[entry.post_id]={label:entry.label||"",confidence:entry.confidence===undefined?"":String(entry.confidence),evidence_codes:Array.isArray(entry.evidence_codes)?entry.evidence_codes:[],evidence:entry.evidence||"",uncertain_reason:entry.uncertain_reason||"",reviewed:Boolean(entry.reviewed),media_review_confirmed:Boolean(entry.media_review?.media_review_confirmed),viewed_media_refs:Array.isArray(entry.media_review?.viewed_media_refs)?entry.media_review.viewed_media_refs:[],remote_media_statuses,remote_open_attempts,reviewed_at:entry.reviewed_at||""};});Object.assign(state.records,next);if(payload.attestation&&typeof payload.attestation==="object")state.attestation=payload.attestation;ensureRecords();loadAttestation();save();renderItems();setMessage("已导入并重新渲染本角色 v2 草稿；请再次检查后导出。",false);}catch(error){setMessage("导入失败："+error.message,true);}};reader.readAsText(file,"utf-8");}
  function openLightbox(item,index){const media=item.media[index];if(!media||!media.local_exists)return;lightboxItem=item;lightboxIndex=index;const dialog=$("lightbox");const body=$("lightboxBody");const caption=$("lightboxCaption");if(media.type==="video")body.innerHTML=`<video controls autoplay src="${esc(media.local_url)}"></video>`;else if(media.type==="audio")body.innerHTML=`<audio controls autoplay src="${esc(media.local_url)}"></audio>`;else body.innerHTML=`<img src="${esc(media.local_url)}" alt="本地媒体 ${media.number}">`;caption.textContent=`#${item.ordinal} · 媒体 ${media.number} · ${media.ref}`;if(typeof dialog.showModal==="function")dialog.showModal();else dialog.setAttribute("open","");}
  function moveLightbox(delta){if(!lightboxItem)return;const count=lightboxItem.media.length;let next=lightboxIndex+delta;for(let i=0;i<count;i++){next=(next+count)%count;if(lightboxItem.media[next].local_exists){markViewed(lightboxItem,next);openLightbox(lightboxItem,next);return;}next+=delta;}}
  function closeLightbox(){const dialog=$("lightbox");if(dialog.open)dialog.close();else dialog.removeAttribute("open");$("lightboxBody").innerHTML="";lightboxItem=null;}
  $("guideText").textContent=GUIDE_TEXT;$("filterSelect").addEventListener("change",event=>{filter=event.target.value;renderItems();});$("saveBtn").addEventListener("click",()=>{syncAttestation();save();});$("exportBtn").addEventListener("click",exportJson);$("importInput").addEventListener("change",event=>{if(event.target.files?.[0])importJson(event.target.files[0]);event.target.value="";});$("resetBtn").addEventListener("click",()=>{if(confirm("确定清空本角色的本地草稿吗？此操作不会删除已导出的文件。")){localStorage.removeItem(STORAGE_KEY);Object.assign(state,{attestation:{reviewer_name:"",reviewer_id:"",read_guide:false,no_other_answers:false,independent:false,evidence_checked:false,media_gaps_ack:false},records:{}});ensureRecords();loadAttestation();renderItems();setMessage("本角色草稿已清空。",false);}});["reviewerName","reviewerId","attGuide","attNoAnswers","attIndependent","attEvidence","attMediaGaps"].forEach(id=>$(id).addEventListener("change",syncAttestation));$("lightboxClose").addEventListener("click",closeLightbox);$("lightboxPrev").addEventListener("click",()=>moveLightbox(-1));$("lightboxNext").addEventListener("click",()=>moveLightbox(1));$("lightbox").addEventListener("click",event=>{if(event.target.id==="lightbox")closeLightbox();});
  load();ensureRecords();loadAttestation();renderItems();
  </script>
</body>
</html>
'''
    html = (
        template.replace("__ROLE__", role)
        .replace("__META_JSON__", meta_json)
        .replace("__ITEMS_JSON__", items_json)
        .replace("__GUIDE_JSON__", guide_json)
        .replace("__LABELS_JSON__", labels_json)
        .replace("__EVIDENCE_JSON__", evidence_json)
        .replace("__ROLE_JSON__", _json_for_script(role))
        .replace("__REVIEW_SCHEMA_JSON__", _json_for_script(REVIEW_SCHEMA_VERSION))
    )
    return html


def _assert_clean_payload(text: str) -> None:
    # These names are intentionally forbidden in the generated page.  The
    # qwen_visible boolean is an audit marker, not model output.
    forbidden = ("model_label", "model_confidence", "_llm_suggestion", "model_reasoning")
    for token in forbidden:
        if token in text:
            raise ValueError(f"generated blind HTML contains forbidden token: {token}")


def _file_records(root: Path, *, exclude: Iterable[Path] = ()) -> list[dict[str, Any]]:
    excluded = {path.resolve() for path in exclude}
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.resolve() in excluded:
            continue
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return records


def _write_sha_sums(root: Path, output: Path) -> None:
    lines: list[str] = []
    for record in _file_records(root, exclude=(output,)):
        lines.append(f"{record['sha256']}  {record['path']}")
    _write_text(output, "\n".join(lines) + "\n")


def generate_delivery(
    *,
    repo_root: Path | str,
    manifest_path: Path | str,
    input_path: Path | str,
    guide_path: Path | str,
    media_base: Path | str,
    output_root: Path | str,
    roles: Sequence[str] = DEFAULT_ROLES,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Generate the role-isolated HTML package and return its audit summary."""

    repo_root = Path(repo_root).resolve()
    manifest_path = Path(manifest_path).resolve()
    input_path = Path(input_path).resolve()
    guide_path = Path(guide_path).resolve()
    media_base = Path(media_base).resolve()
    output_root = Path(output_root).resolve()
    normalized_roles = tuple(str(role).upper() for role in roles)
    if not normalized_roles or len(set(normalized_roles)) != len(normalized_roles):
        raise ValueError("roles must be a non-empty sequence of unique values")
    if any(not role or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in role) for role in normalized_roles):
        raise ValueError("roles contain unsafe characters")
    for required in (manifest_path, input_path, guide_path):
        if not required.exists():
            raise FileNotFoundError(required)
    if output_root.exists() and any(output_root.iterdir()) and not overwrite:
        raise FileExistsError(f"output directory is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("blind manifest must be a JSON object")
    if manifest.get("qwen_run_performed") is True:
        raise ValueError("refusing to build blind HTML from a manifest marked qwen_run_performed=true")
    source_sha = sha256_file(input_path)
    expected_source_sha = str((manifest.get("source") or {}).get("sha256") or "").upper()
    if expected_source_sha and source_sha != expected_source_sha:
        raise ValueError(f"source SHA mismatch: expected {expected_source_sha}, got {source_sha}")
    manifest_sha = sha256_file(manifest_path)
    guide_sha = sha256_file(guide_path)
    guide_text = guide_path.read_text(encoding="utf-8")
    source_rows = _read_jsonl(input_path)

    # Build each role against its own HTML parent so media links remain local
    # and the role pages have no cross-role path references.
    probe_items = _prepare_items(
        manifest, source_rows, media_base, output_root / normalized_roles[0]
    )
    local_media_ref_count = sum(
        1 for item in probe_items for media in item["media"] if media["local_exists"]
    )
    remote_link_media_count = sum(
        1
        for item in probe_items
        for media in item["media"]
        if media["remote_available"]
    )
    missing_media_count = sum(
        1
        for item in probe_items
        for media in item["media"]
        if not media["local_exists"] and not media["remote_available"]
    )
    role_paths: dict[str, str] = {}
    for role in normalized_roles:
        role_dir = output_root / role
        html_path = role_dir / f"M1_Blind_Human_Review_{role}.html"
        items = _prepare_items(manifest, source_rows, media_base, html_path.parent)
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "role": role,
            "qwen_visible": False,
            "sample_count": len(items),
            "local_media_ref_count": local_media_ref_count,
            "remote_link_media_count": remote_link_media_count,
            "missing_media_count": missing_media_count,
            "manifest_sha256": manifest_sha,
            "source_sha256": source_sha,
            "guide_sha256": guide_sha,
            "media_mode": "local_relative_paths_plus_allowlisted_remote_video_links",
            "remote_content_sha256_available": False,
            "generated_at": _now_iso(),
        }
        html = _html_for_role(role, items, guide_text, metadata)
        _assert_clean_payload(html)
        _write_text(html_path, html)
        _write_text(
            role_dir / f"README_{role}.md",
            _role_readme(
                role,
                manifest_sha,
                guide_sha,
                remote_link_media_count,
                missing_media_count,
            ),
        )
        role_paths[role] = html_path.relative_to(output_root).as_posix()

    coordinator = output_root / "COORDINATOR"
    coordinator.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(manifest_path, coordinator / "manifest_blind_sample.json")
    shutil.copyfile(guide_path, coordinator / "annotation_guide_v1.md")
    _write_text(
        coordinator / "DELIVERY_README.md",
        _coordinator_readme(
            normalized_roles,
            manifest_sha,
            guide_sha,
            remote_link_media_count,
            missing_media_count,
        ),
    )

    # delivery_manifest intentionally does not self-hash.  SHA256SUMS covers
    # it, while its files array covers the role pages and readmes plus copied
    # fixed inputs; this avoids a circular checksum.
    manifest_records = _file_records(
        output_root,
        exclude=(coordinator / "delivery_manifest.json", coordinator / "SHA256SUMS.txt"),
    )
    delivery_manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "awaiting_A_B_blind_labels",
        "qwen_visible": False,
        "roles": list(normalized_roles),
        "sample_count": len(probe_items),
        "local_media_ref_count": local_media_ref_count,
        "remote_link_media_count": remote_link_media_count,
        "remote_link_media_items": [
            {
                "ordinal": item["ordinal"],
                "post_id": item["post_id"],
                "remote_media_numbers": [
                    media["number"]
                    for media in item["media"]
                    if media["remote_available"]
                ],
                "remote_urls": [
                    media["remote_url"]
                    for media in item["media"]
                    if media["remote_available"]
                ],
            }
            for item in probe_items
            if any(media["remote_available"] for media in item["media"])
        ],
        "missing_media_count": missing_media_count,
        "missing_media_items": [
            {
                "ordinal": item["ordinal"],
                "post_id": item["post_id"],
                "missing_media_numbers": [
                    media["number"]
                    for media in item["media"]
                    if not media["local_exists"] and not media["remote_available"]
                ],
            }
            for item in probe_items
            if any(
                not media["local_exists"] and not media["remote_available"]
                for media in item["media"]
            )
        ],
        "manifest_sha256": manifest_sha,
        "source_sha256": source_sha,
        "guide_sha256": guide_sha,
        "media_mode": "local_relative_paths_plus_allowlisted_remote_video_links",
        "remote_content_sha256_available": False,
        "created_at": _now_iso(),
        "html_files": role_paths,
        "files_excluding_delivery_manifest_and_sha256s": manifest_records,
    }
    delivery_manifest_path = coordinator / "delivery_manifest.json"
    _write_text(delivery_manifest_path, json.dumps(delivery_manifest, ensure_ascii=False, indent=2) + "\n")
    sums_path = coordinator / "SHA256SUMS.txt"
    _write_sha_sums(output_root, sums_path)
    return {
        "output_root": output_root.as_posix(),
        "roles": list(normalized_roles),
        "sample_count": delivery_manifest["sample_count"],
        "local_media_ref_count": local_media_ref_count,
        "remote_link_media_count": remote_link_media_count,
        "missing_media_count": missing_media_count,
        "manifest_sha256": manifest_sha,
        "source_sha256": source_sha,
        "guide_sha256": guide_sha,
        "delivery_manifest": delivery_manifest_path.as_posix(),
        "sha256sums": sums_path.as_posix(),
        "html_files": {role: (output_root / path).as_posix() for role, path in role_paths.items()},
    }


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_roles(value: str) -> tuple[str, ...]:
    if value.lower() == "all":
        return DEFAULT_ROLES
    roles = tuple(piece.strip().upper() for piece in value.split(",") if piece.strip())
    if not roles:
        raise argparse.ArgumentTypeError("roles cannot be empty")
    return roles


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=_default_repo_root())
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--input", dest="input_path", type=Path, default=None)
    parser.add_argument("--guide", type=Path, default=None)
    parser.add_argument("--media-base", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--roles", type=_parse_roles, default=DEFAULT_ROLES, help="A,B or all")
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite files in an existing delivery directory; never removes extra files",
    )
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    blind_dir = (
        root
        / "data"
        / "reports"
        / "m1"
        / "qwen_blind_test_20260827_remote_links_v2"
    )
    paths = {
        "manifest_path": args.manifest
        or blind_dir / "blind_sample_manifest_remote_links_v2.json",
        "input_path": args.input_path or root / "data" / "reports" / "m1" / "privacy" / "formal_3312_v2" / "formal_eligible_candidates.jsonl",
        "guide_path": args.guide or root / "docs" / "annotation_guide_v1.md",
        "media_base": args.media_base or root / "data" / "run_outputs" / "merged_20260728",
        "output_root": args.output_root or blind_dir / "delivery",
    }
    try:
        result = generate_delivery(
            repo_root=root, roles=args.roles, overwrite=args.force, **paths
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
