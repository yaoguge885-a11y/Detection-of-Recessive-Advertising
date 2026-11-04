"""Regression tests for source-aware privacy scanning."""

from __future__ import annotations

import sys
from pathlib import Path


ANNOTATION_DIR = Path(__file__).resolve().parent.parent
if str(ANNOTATION_DIR) not in sys.path:
    sys.path.insert(0, str(ANNOTATION_DIR))

from privacy_scan import scan_record  # noqa: E402


def finding_types(text: str) -> list[str]:
    return [item["type"] for item in scan_record({"text": text})]


def test_raw_email_is_detected() -> None:
    assert "邮箱地址" in finding_types("联系 test.user@example.com 获取资料")


def test_star_masked_email_suffix_is_not_detected() -> None:
    assert "邮箱地址" not in finding_types("投简历至 s***n@dxy.cn")


def test_uid_is_account_not_bank_card() -> None:
    types = finding_types("UID:3461562994002412")
    assert "UID/账号标识" in types
    assert "银行卡号（疑似）" not in types


def test_qq_group_is_detected() -> None:
    assert "QQ号" in finding_types("交流群 QQ群：123456789")


def test_url_path_is_not_base64_secret() -> None:
    types = finding_types(
        "资料：https://theicct.org/publications/electrification"
    )
    assert "Base64 长字符串（疑似密钥）" not in types


def test_bare_domain_url_path_is_not_base64_secret() -> None:
    types = finding_types("theguardian.com/technology/2014/mar/06/dyson-silent-fan")
    assert "Base64 长字符串（疑似密钥）" not in types


def test_network_address_is_not_physical_address() -> None:
    types = finding_types("下载地址：https://example.com/files/package.zip")
    assert "物理地址" not in types


def test_real_location_is_still_detected() -> None:
    types = finding_types("活动地点：北京市海淀区中关村大街27号")
    assert "物理地址" in types


def test_three_digit_media_index_is_safe() -> None:
    record = {
        "text": "普通正文",
        "media": [{"ref": "media/569638f5edc35ed7e4e76944/100.jpg"}],
    }
    assert not [item for item in scan_record(record) if item["severity"] != "low"]


def test_standalone_base64_secret_is_still_detected() -> None:
    token = "QWxhZGRpbjpPcGVuU2VzYW1lQWxhZGRpbjpPcGVuU2VzYW1l"
    assert "Base64 长字符串（疑似密钥）" in finding_types(f"token: {token}")
