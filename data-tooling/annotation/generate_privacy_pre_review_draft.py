#!/usr/bin/env python3
"""Generate a masked, AI-draft privacy review packet for human B confirmation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


POST_ID_RE = re.compile(r"post_[0-9a-f]{32}")
COMMENT_FIELD_RE = re.compile(r"comments\[(\d+)]\.text")
MEDIA_FIELD_RE = re.compile(r"media\[(\d+)]\.ref")
EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+*\-])[A-Za-z0-9._%+-]+@"
    r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])",
    re.IGNORECASE,
)
MASKED_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]*\*+[A-Za-z0-9._%+*\-]*@"
    r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    re.IGNORECASE,
)
ACCOUNT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"((?:UID|用户ID|QQ(?:群|号|号码)?|WeChat(?:号|ID)?|微信号|微信|ID)"
    r"\s*[：:]\s*)"
    r"([A-Za-z0-9_-]{5,})"
)
MASKED_ACCOUNT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"(?:UID|用户ID|QQ(?:群|号|号码)?|WeChat(?:号|ID)?|微信号|微信|ID)"
    r"\s*[：:]\s*(?:[A-Za-z0-9_-]*\*+[A-Za-z0-9_*-]*|\[[A-Z_]+])"
)
MASKED_PHONE_RE = re.compile(r"(?<!\d)\d{2,4}\*{3,}\d{2,4}(?!\d)")
URL_LIKE_RE = re.compile(
    r"(?i)(?:https?://|www\.)[^\s<>]+|"
    r"(?<!@)\b(?:[A-Za-z0-9-]+\.)+"
    r"(?:com|org|net|cn|io|gov|edu|co|dev|me|info|biz)"
    r"(?:/[^\s<>]*)?"
)
PRIOR_AUDIT_ROW_RE = re.compile(
    r"^\|\s*([MS]-\d{3})\s*\|\s*(post_[0-9a-f]{32})\s*\|\s*"
    r"(allow|redact|exclude)\s*\|\s*(agree|disagree)\s*\|\s*$"
)


def load_privacy_scan(repo_root: Path):
    path = repo_root / "data-tooling" / "annotation" / "privacy_scan.py"
    spec = importlib.util.spec_from_file_location("m1_privacy_scan", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load privacy scanner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_records(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            post_id = str(record["post_id"])
            if post_id in records:
                raise ValueError(f"Duplicate post_id: {post_id}")
            records[post_id] = record
    return records


def load_queue(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = POST_ID_RE.search(line)
        if match is None or not line.startswith("- ["):
            continue
        decision_match = re.search(r"decision:\s*([A-Za-z_]+)", line)
        items.append(
            {
                "post_id": match.group(0),
                "confirmed": line.startswith("- [x]") or line.startswith("- [X]"),
                "decision": decision_match.group(1) if decision_match else None,
            }
        )
    return items


def load_prior_reviews(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    reviews: dict[str, dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = PRIOR_AUDIT_ROW_RE.fullmatch(line)
        if match is None:
            continue
        _, post_id, draft, choice = match.groups()
        reviews[post_id] = {"draft": draft, "choice": choice}
    return reviews


def record_text_values(record: dict[str, Any]) -> list[str]:
    values = [str(record.get("text") or ""), str(record.get("title") or "")]
    values.extend(
        str((comment or {}).get("text") or "")
        for comment in (record.get("comments") or [])
    )
    return values


def existing_mask_categories(record: dict[str, Any]) -> list[str]:
    text = "\n".join(record_text_values(record))
    categories: list[str] = []
    if MASKED_EMAIL_RE.search(text):
        categories.append("email")
    if MASKED_ACCOUNT_RE.search(text):
        categories.append("account identifier")
    if MASKED_PHONE_RE.search(text):
        categories.append("phone number")
    return categories


def mask_sensitive(value: Any, limit: int = 360) -> str:
    text = str(value or "")
    text = URL_LIKE_RE.sub("[URL]", text)
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = re.sub(
        r"(?:地址|位置|地点)\s*[：:]\s*[^\r\n。；;]{5,50}",
        "[PHYSICAL_ADDRESS]",
        text,
        flags=re.IGNORECASE,
    )
    text = ACCOUNT_RE.sub(lambda match: match.group(1) + "[ACCOUNT_ID]", text)
    text = re.sub(r"\b1[3-9]\d{9}\b", "[PHONE]", text)
    text = re.sub(r"\b\d{3}[-.]?\d{4}[-.]?\d{4}\b", "[PHONE]", text)
    text = re.sub(r"\b\d{6,19}\b", "[NUMBER_OR_ID]", text)
    text = re.sub(r"\b[A-Fa-f0-9]{32,64}\b", "[OPAQUE_TOKEN]", text)
    text = re.sub(r"\b[A-Za-z0-9+/]{32,}={0,2}\b", "[OPAQUE_TOKEN]", text)
    text = " ".join(text.split())
    text = text.replace("`", "'").replace("|", "/")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def field_value(record: dict[str, Any], field: str) -> str:
    if field in {"text", "title"}:
        return str(record.get(field) or "")
    match = COMMENT_FIELD_RE.fullmatch(field)
    if match:
        index = int(match.group(1))
        comments = record.get("comments") or []
        if index < len(comments):
            return str((comments[index] or {}).get("text") or "")
    match = MEDIA_FIELD_RE.fullmatch(field)
    if match:
        index = int(match.group(1))
        media = record.get("media") or []
        if index < len(media):
            return str((media[index] or {}).get("ref") or "")
    return ""


def masked_context(value: str, matched: str, radius: int = 120) -> str:
    if matched and matched in value:
        position = value.index(matched)
        start = max(0, position - radius)
        end = min(len(value), position + len(matched) + radius)
        return mask_sensitive(value[start:end], limit=320)
    return mask_sensitive(value, limit=320)


def recommendation(
    queue: str,
    record: dict[str, Any],
    blocking_findings: list[dict[str, Any]],
    masked_categories: list[str],
) -> tuple[str, str]:
    if blocking_findings and all(
        item.get("type") == "物理地址" for item in blocking_findings
    ):
        relevant_text = " ".join(
            field_value(record, str(item.get("field") or ""))
            for item in blocking_findings
        )
        private_address_cues = (
            "家庭住址",
            "住宅地址",
            "收货地址",
            "家庭地址",
            "我家地址",
            "家住",
            "宿舍地址",
            "门牌号",
            "身份证住址",
        )
        if any(cue in relevant_text for cue in private_address_cues):
            return (
                "redact",
                "The context may identify a private residence or personal location; mask the address and rescan.",
            )
        return (
            "allow",
            "Physical-address detector is a lexical hit, while the context appears to be a URL/download/project address or a public venue/store/event/work location rather than a private residence. B must verify the context.",
        )
    if blocking_findings:
        return (
            "redact",
            "A localized text/comment risk was detected. Mask or remove every occurrence, then rescan before approval.",
        )
    if bool((record.get("privacy") or {}).get("contains_sensitive_data")):
        if masked_categories:
            kinds = ", ".join(masked_categories)
            return (
                "allow",
                f"The source already masks the flagged {kinds}, and no unmasked blocking finding remains. Human B must still verify media.",
            )
        return (
            "exclude",
            "Sensitive-data flag is true but no localized blocking text finding exists; exclude unless B can identify and clear the source/media risk.",
        )
    if queue == "sample":
        return (
            "allow",
            "Rule-safe sample: no unmasked medium/high/critical finding. Human B must still verify source and media.",
        )
    return "allow", "No unmasked blocking finding or unresolved sensitive-data flag was found."


def source_state(
    ai_decision: str,
    blocking_findings: list[dict[str, Any]],
    masked_categories: list[str],
) -> tuple[str, str]:
    if ai_decision == "redact":
        kinds = sorted({str(item.get("type") or "risk") for item in blocking_findings})
        return "cleartext risk", ", ".join(kinds)
    if ai_decision == "exclude":
        return "unresolved", "sensitive flag remains, but the scanner cannot localize a safe edit"
    if blocking_findings:
        return "public/non-private context", "lexical location hit reviewed as non-residential"
    if masked_categories:
        return "already masked", ", ".join(masked_categories)
    return "clear", "no unmasked textual risk found"


def render_item(
    number: int,
    queue: str,
    queue_item: dict[str, Any],
    record: dict[str, Any],
    scan_module,
    prior_reviews: dict[str, dict[str, str]],
) -> str:
    all_findings = scan_module.scan_record(record)
    blocking = [item for item in all_findings if item.get("severity") != "low"]
    masked_categories = existing_mask_categories(record)
    ai_decision, ai_reason = recommendation(
        queue,
        record,
        blocking,
        masked_categories,
    )
    state_label, state_reason = source_state(
        ai_decision,
        blocking,
        masked_categories,
    )
    confirmed = bool(queue_item.get("confirmed"))
    human_decision = queue_item.get("decision")

    finding_summary = "; ".join(
        f"{item.get('severity')}:{item.get('type')}@{item.get('field')}"
        for item in blocking
    ) or "none"

    contexts: list[str] = []
    for item in blocking:
        field = str(item.get("field") or "")
        value = field_value(record, field)
        context = masked_context(value, str(item.get("match") or ""))
        entry = f"{field}: {context}"
        if entry not in contexts:
            contexts.append(entry)
    if not contexts:
        contexts.append("text: " + mask_sensitive(record.get("text"), limit=260))

    comments = record.get("comments") or []
    masked_comments = [
        f"c{index}: {mask_sensitive((comment or {}).get('text'), limit=260)}"
        for index, comment in enumerate(comments)
    ]
    if not masked_comments:
        masked_comments = ["none"]

    media = record.get("media") or []
    media_count = len(media)
    local_media_count = sum(bool((item or {}).get("ref")) for item in media)
    source_only_count = sum(
        not bool((item or {}).get("ref")) and bool((item or {}).get("source_url"))
        for item in media
    )
    media_note = (
        f"{media_count} total; {local_media_count} local; "
        f"{source_only_count} source-only; B must inspect every available item"
        if media_count
        else "0"
    )
    prefix = "M" if queue == "mandatory" else "S"
    agree = False
    disagree = False
    change_to = "____"
    migration_note = ""
    if confirmed and human_decision:
        if str(human_decision) == ai_decision:
            agree = True
        else:
            disagree = True
            change_to = str(human_decision)
        status = "B-confirmed in source queue"
    else:
        prior = prior_reviews.get(str(record["post_id"]))
        if prior and prior.get("draft") == ai_decision:
            agree = prior.get("choice") == "agree"
            disagree = prior.get("choice") == "disagree"
            status = (
                "B-confirmed (migrated; AI draft unchanged)"
                if agree
                else "B-disagreed (migrated; change_to still required)"
            )
            migration_note = "Previous B choice retained because the AI draft did not change."
        elif prior:
            status = "AI draft revised; prior choice archived; pending B"
            migration_note = (
                f"Previous {prior.get('choice')} on {prior.get('draft')} was cleared "
                f"because the revised AI draft is {ai_decision}."
            )
        else:
            status = "AI draft; pending B"

    agree_box = "[x]" if agree else "[ ]"
    disagree_box = "[x]" if disagree else "[ ]"

    lines = [
        f"### {prefix}-{number:03d} `{record['post_id']}`",
        "",
        f"- Status: {status}",
        f"- AI draft: **{ai_decision}** — {ai_reason}",
        f"- Source state: **{state_label}** — {state_reason}",
        f"- Findings: {finding_summary}",
        f"- Sensitive flag: {bool((record.get('privacy') or {}).get('contains_sensitive_data'))}",
        f"- Masked evidence: {' / '.join(contexts)}",
        f"- Masked comments: {' / '.join(masked_comments)}",
        f"- Media: {media_note}",
        "- B confirmation（两项只能勾选一项）:",
        f"  - {agree_box} agree（同意 AI 建议）",
        f"  - {disagree_box} disagree（不同意 AI 建议）",
        f"- If disagree: change_to: {change_to}; notes: ____",
        "",
    ]
    if migration_note:
        lines.insert(-1, f"- Migration note: {migration_note}")
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--queue", choices=("mandatory", "sample"), required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument(
        "--prior-review-audit",
        type=Path,
        help="Optional compact audit table used to migrate unchanged B choices.",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    privacy_dir = repo_root / "data" / "reports" / "m1" / "privacy"
    queue_path = privacy_dir / (
        "privacy_mandatory_review_B_draft.md"
        if args.queue == "mandatory"
        else "privacy_low_risk_sample_B_draft.md"
    )
    records = load_records(
        repo_root
        / "data"
        / "run_outputs"
        / "merged_20260728"
        / "anonymized_posts.jsonl"
    )
    queue_items = load_queue(queue_path)
    prior_reviews = load_prior_reviews(args.prior_review_audit)
    scan_module = load_privacy_scan(repo_root)
    selected = queue_items[args.start : args.start + args.count]
    for offset, item in enumerate(selected, start=args.start + 1):
        post_id = str(item["post_id"])
        if post_id not in records:
            raise KeyError(f"Queue post_id missing from canonical data: {post_id}")
        print(
            render_item(
                offset,
                args.queue,
                item,
                records[post_id],
                scan_module,
                prior_reviews,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
