"""Create a role-isolated portable archive for the M1 blind HTML review."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import unquote

import generate_m1_qwen_blind_html as html_generator


PACKAGE_SCHEMA_VERSION = "m1_qwen_blind_portable_remote_links_v2"


def _role_package_readme(
    *,
    role: str,
    package_name: str,
    html_relative_path: str,
    html_sha: str,
    guide_sha: str,
    manifest_sha: str,
    local_count: int,
    remote_count: int,
) -> str:
    return f"""# M1 Qwen 盲测角色 {role} 便携包 — 远程链接 v2

解压整个 `{package_name}` 文件夹后，打开：

`{html_relative_path}`

先阅读同目录 `README_{role}.md` 和 `../COORDINATOR/annotation_guide_v1.md`。本包有 {local_count} 个已固定的本地媒体文件和 {remote_count} 个受限的在线源视频入口。

在线源视频的正确操作是：点击“在新标签页打开源视频” → 实际观看 → 返回标注页选择“已成功打开并检查视频”。如果打不开，选择“链接无法访问或内容不可用”并确认全局证据缺口。一次点击本身不等于已看完；不要搜索、下载或替换视频。

这是全新的 v2 清单。不要导入旧 v1 JSON，也不要沿用 v1 浏览器草稿；请从 v2 页面重新独立完成。只使用本角色文件，不接触另一角色的入口或答案。

本包仅用于 Qwen 工程质量校准。在线内容未纳入本包 SHA，导出状态会保留这一限制；不得据此声称最终质量通过，不得写入正式 Gold、locked_batches、正式候选或其他正式 M1 证据。

## 固定哈希

- HTML SHA-256: `{html_sha}`
- 标注指南 SHA-256: `{guide_sha}`
- remote-links v2 manifest SHA-256: `{manifest_sha}`
- 包内文件哈希：`{role}_PACKAGE_MANIFEST.json` 与 `SHA256SUMS.txt`
"""


def _records(root: Path, *, excluded: Sequence[Path] = ()) -> list[dict[str, Any]]:
    excluded_resolved = {path.resolve() for path in excluded}
    return [
        {
            "path": path.relative_to(root.parent).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": html_generator.sha256_file(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.resolve() not in excluded_resolved
    ]


def _safe_repo_relative(path: Path, repo_root: Path) -> Path:
    try:
        return path.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"package source escapes repository root: {path}") from exc


def build_role_archive(
    *,
    repo_root: Path | str,
    delivery_root: Path | str,
    input_path: Path | str,
    media_base: Path | str,
    output_path: Path | str,
    role: str,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    delivery_root = Path(delivery_root).resolve()
    input_path = Path(input_path).resolve()
    media_base = Path(media_base).resolve()
    output_path = Path(output_path).resolve()
    role = str(role).upper()
    if role not in {"A", "B"}:
        raise ValueError("role must be A or B")
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing archive: {output_path}")

    role_dir = delivery_root / role
    coordinator_dir = delivery_root / "COORDINATOR"
    html_source = role_dir / f"M1_Blind_Human_Review_{role}.html"
    readme_source = role_dir / f"README_{role}.md"
    guide_source = coordinator_dir / "annotation_guide_v1.md"
    manifest_source = coordinator_dir / "manifest_blind_sample.json"
    delivery_manifest_source = coordinator_dir / "delivery_manifest.json"
    for required in (
        html_source,
        readme_source,
        guide_source,
        manifest_source,
        delivery_manifest_source,
        input_path,
    ):
        if not required.is_file():
            raise FileNotFoundError(required)
    if not media_base.is_dir():
        raise FileNotFoundError(media_base)

    delivery_manifest = json.loads(delivery_manifest_source.read_text(encoding="utf-8"))
    if delivery_manifest.get("qwen_visible") is not False:
        raise ValueError("delivery is not marked qwen_visible=false")
    if role not in (delivery_manifest.get("roles") or []):
        raise ValueError(f"role {role} is absent from delivery manifest")
    for source, key in ((input_path, "source_sha256"), (guide_source, "guide_sha256"),
                        (manifest_source, "manifest_sha256")):
        if html_generator.sha256_file(source) != delivery_manifest.get(key):
            raise ValueError(f"delivery hash mismatch: {key}")
    expected_files = {
        record["path"]: record["sha256"]
        for record in delivery_manifest.get("files_excluding_delivery_manifest_and_sha256s", [])
    }
    for source in (html_source, readme_source):
        relative = source.relative_to(delivery_root).as_posix()
        if html_generator.sha256_file(source) != expected_files.get(relative):
            raise ValueError(f"delivery file hash mismatch: {relative}")
    manifest = json.loads(manifest_source.read_text(encoding="utf-8"))
    source_rows = html_generator._read_jsonl(input_path)
    items = html_generator._prepare_items(
        manifest, source_rows, media_base, html_source.parent
    )
    local_media = [
        media for item in items for media in item["media"] if media["local_exists"]
    ]
    remote_media = [
        (item, media)
        for item in items
        for media in item["media"]
        if media["remote_available"]
    ]
    unavailable_media = [
        (item, media)
        for item in items
        for media in item["media"]
        if not media["local_exists"] and not media["remote_available"]
    ]
    if unavailable_media:
        raise ValueError("portable v2 build requires zero fixed unavailable media")
    expected_counts = (
        int(delivery_manifest["local_media_ref_count"]),
        int(delivery_manifest["remote_link_media_count"]),
        int(delivery_manifest["missing_media_count"]),
    )
    actual_counts = (len(local_media), len(remote_media), len(unavailable_media))
    if expected_counts != actual_counts:
        raise ValueError(
            f"delivery evidence counts {expected_counts} do not match source {actual_counts}"
        )

    package_name = output_path.stem.removesuffix("_portable")
    task_temp_parent = repo_root / ".codex_tmp"
    task_temp_parent.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f"package_{role.lower()}_", dir=task_temp_parent
    ) as temporary:
        package_root = Path(temporary) / package_name
        delivery_relative = _safe_repo_relative(delivery_root, repo_root)
        packaged_role_dir = package_root / delivery_relative / role
        packaged_coordinator = package_root / delivery_relative / "COORDINATOR"
        packaged_role_dir.mkdir(parents=True, exist_ok=True)
        packaged_coordinator.mkdir(parents=True, exist_ok=True)
        shutil.copy2(html_source, packaged_role_dir / html_source.name)
        shutil.copy2(readme_source, packaged_role_dir / readme_source.name)
        shutil.copy2(guide_source, packaged_coordinator / guide_source.name)
        shutil.copy2(manifest_source, packaged_coordinator / manifest_source.name)

        media_base_relative = _safe_repo_relative(media_base, repo_root)
        copied_media_paths: set[Path] = set()
        for media in local_media:
            source_media = html_generator._safe_relative_media_path(
                media_base, media["ref"]
            )
            destination = package_root / media_base_relative / Path(media["ref"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination not in copied_media_paths:
                shutil.copy2(source_media, destination)
                copied_media_paths.add(destination)

        packaged_html = packaged_role_dir / html_source.name
        unresolved_local_urls: list[str] = []
        for media in local_media:
            relative_url = media["local_url"]
            resolved = (packaged_html.parent / Path(unquote(relative_url))).resolve()
            if not resolved.is_file():
                unresolved_local_urls.append(relative_url)
        if unresolved_local_urls:
            raise ValueError(
                f"portable HTML has unresolved local URLs: {unresolved_local_urls[:3]}"
            )

        html_sha = html_generator.sha256_file(packaged_html)
        guide_sha = html_generator.sha256_file(packaged_coordinator / guide_source.name)
        manifest_sha = html_generator.sha256_file(
            packaged_coordinator / manifest_source.name
        )
        package_readme = package_root / f"{role}_PACKAGE_README.md"
        html_generator._write_text(
            package_readme,
            _role_package_readme(
                role=role,
                package_name=package_name,
                html_relative_path=(delivery_relative / role / html_source.name).as_posix(),
                html_sha=html_sha,
                guide_sha=guide_sha,
                manifest_sha=manifest_sha,
                local_count=len(local_media),
                remote_count=len(remote_media),
            ),
        )
        package_manifest_path = package_root / f"{role}_PACKAGE_MANIFEST.json"
        sums_path = package_root / "SHA256SUMS.txt"
        file_records = _records(
            package_root, excluded=(package_manifest_path, sums_path)
        )
        package_manifest = {
            "schema_version": PACKAGE_SCHEMA_VERSION,
            "role": role,
            "status": f"awaiting_{role}_blind_labels",
            "qwen_visible": False,
            "sample_count": len(items),
            "source_media_entry_count": sum(len(item["media"]) for item in items),
            "included_local_media_count": len(copied_media_paths),
            "remote_link_media_count": len(remote_media),
            "unavailable_media_count": len(unavailable_media),
            "remote_content_sha256_available": False,
            "remote_links": [
                {
                    "ordinal": item["ordinal"],
                    "post_id": item["post_id"],
                    "media_number": media["number"],
                    "url": media["remote_url"],
                    "url_sha256": hashlib.sha256(
                        media["remote_url"].encode("utf-8")
                    )
                    .hexdigest()
                    .upper(),
                }
                for item, media in remote_media
            ],
            "archive_layout": "repo_relative_subset",
            "html_relative_media_check": {
                "status": "pass",
                "resolved_local_urls": len(local_media),
                "included_local_media": len(copied_media_paths),
            },
            "source_artifact_hashes": {
                "html_sha256": html_sha,
                "guide_sha256": guide_sha,
                "manifest_sha256": manifest_sha,
                "delivery_manifest_sha256": html_generator.sha256_file(
                    delivery_manifest_source
                ),
            },
            "excluded": [
                "the other role's HTML, README, drafts, and answers",
                "Qwen suggestions or model outputs",
                "A/B labels, adjudication, or quality conclusions",
                "formal Gold, locked_batches, formal candidates, and other formal M1 evidence",
                "source JSONL and unrelated repository files",
            ],
            "files_excluding_package_manifest_and_sha256s": file_records,
        }
        html_generator._write_text(
            package_manifest_path,
            json.dumps(package_manifest, ensure_ascii=False, indent=2) + "\n",
        )
        sum_records = _records(package_root, excluded=(sums_path,))
        html_generator._write_text(
            sums_path,
            "".join(
                f"{record['sha256']}  {record['path']}\n" for record in sum_records
            ),
        )

        with zipfile.ZipFile(
            output_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for path in sorted(package_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(package_root.parent).as_posix())

    return {
        "archive": output_path.as_posix(),
        "archive_sha256": html_generator.sha256_file(output_path),
        "role": role,
        "sample_count": len(items),
        "local_media_count": len(local_media),
        "unique_local_media_files": len(copied_media_paths),
        "remote_link_media_count": len(remote_media),
        "unavailable_media_count": len(unavailable_media),
    }


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=_default_repo_root())
    parser.add_argument("--delivery-root", type=Path)
    parser.add_argument("--input", dest="input_path", type=Path)
    parser.add_argument("--media-base", type=Path)
    parser.add_argument("--output", dest="output_path", type=Path)
    parser.add_argument("--role", choices=("A", "B"), required=True)
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    blind_dir = (
        root
        / "data"
        / "reports"
        / "m1"
        / "qwen_blind_test_20260827_remote_links_v2"
    )
    output_name = f"M1_Qwen_Blind_{args.role}_20260827_remote_links_v2_portable.zip"
    try:
        result = build_role_archive(
            repo_root=root,
            delivery_root=args.delivery_root or blind_dir / "delivery",
            input_path=args.input_path
            or root
            / "data"
            / "reports"
            / "m1"
            / "privacy"
            / "formal_3312_v2"
            / "formal_eligible_candidates.jsonl",
            media_base=args.media_base
            or root / "data" / "run_outputs" / "merged_20260728",
            output_path=args.output_path or blind_dir / output_name,
            role=args.role,
        )
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
