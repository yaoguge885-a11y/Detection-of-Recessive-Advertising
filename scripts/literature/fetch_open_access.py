"""给检索结果补充"能不能拿到 PDF"的信息。

数据源：

* Unpaywall（https://api.unpaywall.org/v2/{doi}?email=...）：公开、免费、无需 Key，
  返回 `is_oa` / `oa_status` / `best_oa_location.url_for_pdf`。
* ACL Anthology：`10.18653/v1/<volume>.<id>` 的 PDF 可以直接拼出来
  （`https://aclanthology.org/<volume>.<id>.pdf`），不依赖任何第三方。

用法（先跑 venue_paper_search.py 生成 results JSON）：

    python scripts/literature/fetch_open_access.py
    python scripts/literature/fetch_open_access.py --limit 20        # 冒烟
    python scripts/literature/fetch_open_access.py --email you@example.org

只读 HTTP 请求；输出只包含题录与链接，不下载 PDF 正文。
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "impad-lit-review/1.0"
UNPAYWALL = "https://api.unpaywall.org/v2/{doi}"
ACL_DOI = re.compile(r"^10\.18653/v1/(.+)$", re.I)


def http_get_json(url: str, *, retries: int = 4, timeout: int = 60) -> dict:
    delay = 2.0
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise
            if error.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError, http.client.IncompleteRead):
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError(f"GET failed after retries: {url}")


def acl_pdf(doi: str) -> tuple[str, str]:
    """从 ACL Anthology DOI 直接拼出 landing page 与 PDF。"""
    match = ACL_DOI.match(doi)
    if not match:
        return "", ""
    slug = match.group(1).rstrip("/")
    return f"https://aclanthology.org/{slug}/", f"https://aclanthology.org/{slug}.pdf"


def classify(host: str, url: str) -> tuple[bool, str]:
    """判断链接是"直链 PDF"还是"出版社/落地页"。"""
    lowered = url.lower()
    if not url:
        return False, ""
    if any(token in lowered for token in ("aclanthology.org", "arxiv.org/pdf", "/article/download/")):
        return True, "direct-pdf"
    if lowered.endswith(".pdf"):
        return True, "direct-pdf"
    if "dl.acm.org" in lowered or "doi.org" in lowered or "ieeexplore" in lowered or "springer" in lowered:
        return False, "publisher-page"
    return False, host or "other"


def unpaywall(doi: str, email: str) -> dict:
    payload = http_get_json(UNPAYWALL.format(doi=urllib.parse.quote(doi)) + f"?email={urllib.parse.quote(email)}")
    best = payload.get("best_oa_location") or {}
    return {
        "is_oa": bool(payload.get("is_oa")),
        "oa_status": payload.get("oa_status") or "unknown",
        "license": best.get("license") or "",
        "pdf_url": best.get("url_for_pdf") or "",
        "landing_url": best.get("url") or "",
        "host": best.get("host_type") or "",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", default="docs/literature/venue_search_results.json")
    parser.add_argument("--output", default="docs/literature/open_access_report.json")
    parser.add_argument("--markdown", default="docs/literature/open_access_report.md")
    parser.add_argument("--email", default="research@example.org", help="Unpaywall 要求带一个联系邮箱")
    parser.add_argument("--limit", type=int, default=0, help="冒烟用：只查前 N 条")
    parser.add_argument("--download-dir", default="", help="可选：把直链 PDF 下载到该目录（只存本地，不入库）")
    parser.add_argument("--sleep", type=float, default=0.4, help="每次请求之间的间隔（秒）")
    args = parser.parse_args(argv)

    source = Path(args.results)
    if not source.exists():
        print(f"! {source} 不存在，先跑 venue_paper_search.py", file=sys.stderr)
        return 2
    data = json.loads(source.read_text(encoding="utf-8"))
    records = data["records"]
    if args.limit:
        records = records[: args.limit]

    enriched: list[dict] = []
    failures = 0
    for index, record in enumerate(records, 1):
        doi = record.get("doi") or ""
        info = {"is_oa": False, "oa_status": "no-doi" if not doi else "unknown",
                "license": "", "pdf_url": "", "landing_url": "", "host": ""}
        landing, pdf = acl_pdf(doi)
        if pdf:
            info.update({"is_oa": True, "oa_status": "gold", "pdf_url": pdf, "landing_url": landing, "host": "acl-anthology"})
        elif doi:
            try:
                remote = unpaywall(doi, args.email)
                # ACL Anthology 命中优先保留（免第三方）
                if not info["pdf_url"] or remote["is_oa"]:
                    info = {**info, **{k: v for k, v in remote.items() if v}}
                if remote["is_oa"] and not info["pdf_url"]:
                    info["pdf_url"] = remote["landing_url"]
            except urllib.error.HTTPError as error:
                failures += 1
                info["oa_status"] = f"http-{error.code}"
            except Exception as error:  # 网络抖动不阻断整批
                failures += 1
                info["oa_status"] = f"error-{type(error).__name__}"
            time.sleep(args.sleep)
        if record.get("arxiv_id"):
            info.update({"is_oa": True, "oa_status": info.get("oa_status") or "green",
                         "pdf_url": f"https://arxiv.org/pdf/{record['arxiv_id']}",
                         "landing_url": f"https://arxiv.org/abs/{record['arxiv_id']}", "host": "arxiv"})
        enriched.append({**record, "open_access": info})
        if index % 25 == 0:
            print(f"  ... {index}/{len(records)}", flush=True)

    for record in enriched:
        oa = record["open_access"]
        url = oa["pdf_url"] or oa["landing_url"]
        direct, kind = classify(oa["host"], oa["pdf_url"])
        if not oa["pdf_url"] and oa["landing_url"]:
            direct, kind = False, "publisher-page"
        oa["direct_pdf"] = direct
        oa["link_kind"] = kind
        if not url:
            oa["link_kind"] = "none"

    with_pdf = [r for r in enriched if r["open_access"]["direct_pdf"]]
    with_link = [r for r in enriched if r["open_access"]["pdf_url"] or r["open_access"]["landing_url"]]
    summary = {
        "checked": len(enriched),
        "with_direct_pdf": len(with_pdf),
        "with_any_link": len(with_link),
        "no_link": len(enriched) - len(with_link),
        "failures": failures,
        "by_status": {},
        "by_kind": {},
    }
    for record in enriched:
        status = record["open_access"]["oa_status"]
        summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
        kind = record["open_access"]["link_kind"]
        summary["by_kind"][kind] = summary["by_kind"].get(kind, 0) + 1

    output = {
        "generated_by": "scripts/literature/fetch_open_access.py",
        "sources": ["unpaywall", "acl-anthology", "arxiv"],
        "summary": summary,
        "records": enriched,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 可下载 PDF 情况（自动生成）",
        "",
        "> 生成脚本：`scripts/literature/fetch_open_access.py`；来源：Unpaywall + ACL Anthology + arXiv。",
        f"> 检查 {summary['checked']} 条：{summary['with_direct_pdf']} 条有**可直接下载的 PDF 直链**，"
        f"{summary['with_any_link'] - summary['with_direct_pdf']} 条只能给出版社页面（可能需机构订阅），"
        f"{summary['no_link']} 条查不到开放版本。",
        "",
        "> ACL Anthology（`10.18653`）、AAAI/ICWSM 的 OJS、arXiv 都是直链；ACM DL / IEEE Xplore / Springer 的链接",
        "> 多为出版社页面，校园网或订阅下可下载，脚本不代为绕过。",
        "",
        "| 年份 | 会议 | 题名 | DOI | 开放状态 | 链接类型 | 链接 |",
        "| ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for record in enriched:
        oa = record["open_access"]
        doi = record.get("doi") or "—"
        url = oa["pdf_url"] or oa["landing_url"]
        link = f"[{'PDF' if oa['direct_pdf'] else '页面'}]({url})" if url else "—"
        title = record["title"].replace("|", "\\|")[:110]
        lines.append(
            f"| {record['year']} | {record['venue_key']} | {title} | {doi} | {oa['oa_status']} | {oa['link_kind']} | {link} |"
        )
    Path(args.markdown).write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.download_dir:
        target = Path(args.download_dir)
        target.mkdir(parents=True, exist_ok=True)
        saved = 0
        for record in enriched:
            oa = record["open_access"]
            if not oa["direct_pdf"] or not oa["pdf_url"]:
                continue
            name = re.sub(r"[^A-Za-z0-9._-]+", "_", (record.get("doi") or record["title"]))[:80] + ".pdf"
            destination = target / name
            if destination.exists():
                continue
            try:
                request = urllib.request.Request(oa["pdf_url"], headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(request, timeout=120) as response:
                    payload = response.read()
                if payload[:4] != b"%PDF":
                    continue
                destination.write_bytes(payload)
                saved += 1
                time.sleep(0.5)
            except Exception as error:
                print(f"  ! download failed {oa['pdf_url'][:80]}: {error}", file=sys.stderr)
        print(f"downloaded {saved} PDFs into {target}")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote {out_path} and {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
