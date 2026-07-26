#!/usr/bin/env python3
"""Schema 校验器 —— 读取权威 Schema 文件校验 JSONL 数据。

v1.1 改进：
  - 读取 data/schema/data_schema_v1_1.json（权威 schema），不维护另一套手写字段集合
  - 支持 --target-schema 指定校验版本（1.0 / 1.1）
  - 增加敏感字段扫描、高熵/密钥模式扫描、直接身份与 URL 参数脱敏检查
  - 支持 raw/interim/public 三层输出校验

用法：
  python scripts/data/validate_schema.py data/interim/candidates_v1.jsonl
  python scripts/data/validate_schema.py data/interim/candidates_v1.jsonl --target-schema 1.1 --privacy-scan
"""
import json
import re
import math
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from jsonschema import Draft202012Validator, FormatChecker


FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time", raises=(TypeError, ValueError))
def _is_rfc3339_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return True
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


@FORMAT_CHECKER.checks("date", raises=(TypeError, ValueError))
def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if len(value) != 10:
        return False
    date.fromisoformat(value)
    return True


# ═══════════════════════════════════════════════════════════════
# Schema 加载
# ═══════════════════════════════════════════════════════════════

def resolve_schema_path(
    project_root: Path,
    version: str = "1.0",
    explicit_path: Optional[Path] = None,
) -> Path:
    """Resolve the schema in either the repository or standalone tool cabin."""
    if explicit_path is not None:
        path = explicit_path if explicit_path.is_absolute() else project_root / explicit_path
        if path.is_file():
            return path
        raise FileNotFoundError(f"Schema file not found: {path}")

    filename = "data_schema_v1.json" if version == "1.0" else "data_schema_v1_1.json"
    candidates = (
        project_root / "data" / "schema" / filename,
        project_root / "data-tooling" / "schema" / filename,
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(f"Schema file not found for version {version}")


def load_authoritative_schema(
    project_root: Path,
    version: str = "1.0",
    explicit_path: Optional[Path] = None,
) -> Dict:
    """从权威 schema 文件加载 schema 定义。"""
    schema_path = resolve_schema_path(project_root, version, explicit_path)
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_required_fields(schema: Dict) -> List[str]:
    """从 schema 定义中提取 content_record 的必填字段。"""
    content = schema.get("$defs", {}).get("content_record", {})
    return content.get("required", [])


def get_property_names(schema: Dict) -> List[str]:
    """从 schema 定义中提取 content_record 的所有属性名。"""
    content = schema.get("$defs", {}).get("content_record", {})
    return list(content.get("properties", {}).keys())


def get_platform_enum(schema: Dict) -> List[str]:
    """从 schema 中提取 platform 枚举值。"""
    content = schema.get("$defs", {}).get("content_record", {})
    platform_prop = content.get("properties", {}).get("platform", {})
    return platform_prop.get("enum", [])


# ═══════════════════════════════════════════════════════════════
# 敏感信息扫描
# ═══════════════════════════════════════════════════════════════

# 敏感字段模式
SENSITIVE_PATTERNS = [
    (r"\b1[3-9]\d{9}\b", "手机号"),
    (r"\b\d{3}[-.]?\d{4}[-.]?\d{4}\b", "固定电话"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "邮箱地址"),
    (r"\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b", "身份证号"),
    (r"\b(?:\d{3,4}-?){2,3}\d{3,4}\b", "疑似电话号码"),
    (r"\bhttps?://[^\s]*(\b(?:token|key|secret|password|auth|api_key|access_token)\b)[^\s]*", "含凭证的URL"),
]

# 高熵/密钥模式
HIGH_ENTROPY_PATTERNS = [
    (r"\b[A-Za-z0-9+/]{32,}={0,2}\b", "Base64 长字符串（疑似密钥）"),
    (r"\b[a-fA-F0-9]{32,64}\b", "十六进制长字符串（疑似哈希/密钥）"),
    (r"\b(?:sk-|pk-|AKIA)[A-Za-z0-9_\-+/]{20,}\b", "API 密钥模式"),
    (r"\b(?:Bearer|Basic)\s+[A-Za-z0-9_\-+.=/]{20,}\b", "认证令牌"),
]

# 直接身份信息模式
PII_PATTERNS = [
    (r"(?:微信|WeChat)\s*(?:号|ID)?\s*[：:]\s*[A-Za-z0-9_-]{6,}", "微信号"),
    (r"(?:QQ|qq)\s*(?:号|号码)?\s*[：:]\s*\d{5,}", "QQ号"),
    (r"(?:地址|位置|地点)\s*[：:]\s*.{5,50}", "物理地址"),
]


def shannon_entropy(text: str) -> float:
    """计算文本的香农熵。"""
    if not text:
        return 0.0
    counter = Counter(text)
    length = len(text)
    entropy = 0.0
    for count in counter.values():
        prob = count / length
        entropy -= prob * math.log2(prob)
    return entropy


def scan_sensitive_content(record: Dict) -> List[Dict[str, str]]:
    """扫描记录中的敏感内容。返回发现列表。"""
    findings = []

    # 检查 text 字段
    text = record.get("text", "")
    if text:
        for pattern, label in SENSITIVE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                findings.append({
                    "field": "text",
                    "type": label,
                    "match": str(match)[:50],
                    "severity": "high",
                })

        for pattern, label in HIGH_ENTROPY_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                findings.append({
                    "field": "text",
                    "type": label,
                    "match": str(match)[:50],
                    "severity": "medium",
                })

        for pattern, label in PII_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                findings.append({
                    "field": "text",
                    "type": label,
                    "match": str(match)[:50],
                    "severity": "high",
                })

        # 高熵检测
        if len(text) > 20:
            entropy = shannon_entropy(text)
            if entropy > 5.5:
                findings.append({
                    "field": "text",
                    "type": "高熵文本（疑似编码/加密内容）",
                    "match": f"entropy={entropy:.2f}",
                    "severity": "low",
                })

    # 检查 media 中的 source_url（URL 参数可能含 PII）
    for i, m in enumerate(record.get("media", [])):
        if isinstance(m, dict):
            ref = m.get("ref", "") or ""
            for pattern, label in PII_PATTERNS:
                matches = re.findall(pattern, str(ref), re.IGNORECASE)
                for match in matches:
                    findings.append({
                        "field": f"media[{i}].ref",
                        "type": label,
                        "match": str(match)[:50],
                        "severity": "high",
                    })

    # 检查 title
    title = record.get("title", "") or ""
    if title:
        for pattern, label in SENSITIVE_PATTERNS:
            matches = re.findall(pattern, str(title), re.IGNORECASE)
            for match in matches:
                findings.append({
                    "field": "title",
                    "type": label,
                    "match": str(match)[:50],
                    "severity": "high",
                })

    return findings


# ═══════════════════════════════════════════════════════════════
# Schema 校验
# ═══════════════════════════════════════════════════════════════

def validate_record(record: Dict[str, Any], schema: Dict) -> List[str]:
    """Validate one complete record with the authoritative Draft 2020-12 schema."""
    validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
    errors: List[str] = []
    for error in sorted(
        validator.iter_errors(record),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    ):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{error.validator}: {location}: {error.message}")
    return errors


def load_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    """加载 JSONL 文件，兼容标准 JSONL 和美化打印拼接格式。"""
    raw_text = path.read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    idx = 0
    content_len = len(raw_text)
    while idx < content_len:
        while idx < content_len and raw_text[idx] in " \t\n\r":
            idx += 1
        if idx >= content_len:
            break
        obj, end = decoder.raw_decode(raw_text, idx)
        if not isinstance(obj, dict):
            raise TypeError(f"record must be an object at position {idx}")
        yield obj
        idx = end


def write_jsonl(records: Iterable[Dict], path: Path) -> None:
    """写入标准 JSONL（一行一个有效 JSON 对象）。"""
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _repository_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "schema").is_dir() and (parent / "data-tooling").is_dir():
            return parent
    return Path(__file__).resolve().parent.parent.parent


def _configure_console_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main(
    path: str,
    target_schema: str = "1.0",
    privacy_scan: bool = False,
    report_path: Optional[str] = None,
    schema_path: Optional[str] = None,
) -> int:
    _configure_console_output()
    project_root = _repository_root()
    path_obj = Path(path)
    if not path_obj.is_absolute():
        path_obj = project_root / path

    if not path_obj.exists():
        print(f"ERROR: path does not exist: {path_obj}")
        return 1

    # 加载权威 schema
    explicit_schema = Path(schema_path) if schema_path else None
    schema = load_authoritative_schema(project_root, target_schema, explicit_schema)
    print(f"📋 使用 schema: data_schema_v{target_schema}.json")

    total = 0
    invalid = 0
    privacy_findings_total = 0
    validator_counts: Counter[str] = Counter()

    for record in load_jsonl(path_obj):
        total += 1
        errors = validate_record(record, schema)

        # 隐私扫描
        privacy_findings = []
        if privacy_scan:
            privacy_findings = scan_sensitive_content(record)
            if privacy_findings:
                privacy_findings_total += len(privacy_findings)

        if errors or privacy_findings:
            if errors:
                invalid += 1
                print(f"\n[record {total - 1}] ❌ errors:")
                for error in errors:
                    validator_counts[error.split(":", 1)[0]] += 1
                    print(f"  - {error}")
            if privacy_findings:
                print(f"  🔒 隐私警告:")
                for pf in privacy_findings:
                    print(f"    [{pf['severity']}] {pf['field']}: {pf['type']} ({pf['match']})")
    # 摘要
    print(f"\n{'='*60}")
    print(f"📊 校验完成: {path_obj.name}")
    print(f"   总记录:   {total}")
    print(f"   有效:     {total - invalid}")
    print(f"   无效:     {invalid}")
    if privacy_scan:
        print(f"   隐私告警: {privacy_findings_total}")
    print(f"{'='*60}")

    # 保存校验日志
    if report_path:
        log_path = Path(report_path)
        if not log_path.is_absolute():
            log_path = project_root / report_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as f:
            json.dump({
                "validated_at": __import__("datetime").datetime.now().isoformat(),
                "schema_version": target_schema,
                "total_records": total,
                "valid_records": total - invalid,
                "invalid_records": invalid,
                "validator_counts": dict(sorted(validator_counts.items())),
                "privacy_findings": privacy_findings_total if privacy_scan else "disabled",
            }, f, ensure_ascii=False, indent=2)
        print(f"📝 校验日志: {log_path}")

    return 0 if invalid == 0 else 2


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Schema 校验器（读取权威 schema）")
    parser.add_argument("input", nargs="?", default="data/interim/candidates_v1.jsonl",
                        help="待校验的 JSONL 文件路径")
    parser.add_argument("--target-schema", default="1.0", choices=["1.0", "1.1"],
                        help="目标 schema 版本")
    parser.add_argument("--schema", default=None,
                        help="显式权威 schema 文件路径")
    parser.add_argument("--privacy-scan", action="store_true",
                        help="启用敏感信息扫描")
    parser.add_argument("--report", "--output-log", dest="report", default=None,
                        help="聚合校验报告输出路径")
    args = parser.parse_args()
    sys.exit(main(
        args.input,
        args.target_schema,
        args.privacy_scan,
        args.report,
        args.schema,
    ))
