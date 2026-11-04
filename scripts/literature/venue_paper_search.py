"""按会议检索与"隐性广告/创作者历史/合规证据"相关的论文，并落盘 DOI。

数据源为 Crossref 公开 API（https://api.crossref.org，无需 Key），按 DOI 前缀
分组 + 会议 proceedings 的 container-title 正则把条目归到具体会议，因此每条
记录都自带可解析的 DOI。

覆盖的会议（每个都对应项目文档里的一条研究/工程主线）：

* 10.18653 ACL Anthology：ACL / EMNLP / NAACL / EACL / COLING（含 Findings）
* 10.1609  AAAI / ICWSM
* 10.1145  ACM：KDD / WWW / WSDM / CIKM / SIGIR / MM / CHI / CSCW
* 10.1109  IEEE：CVPR / ICCV
* 10.1007  Springer：ECCV
* 10.24963 IJCAI

NeurIPS / ICLR / ICML(PMLR) 不给论文注册 DOI，因此不进入本脚本；这三个会议
需要按 OpenReview / arXiv 编号单独检索（见 docs/literature/ 的说明）。

用法（仓库根目录）：

    python scripts/literature/venue_paper_search.py
    python scripts/literature/venue_paper_search.py --venues emnlp icwsm kdd
    python scripts/literature/venue_paper_search.py --limit-venues 2      # 冒烟

只读 HTTP 请求；输出只有题录元数据（题名/作者/年份/会议/DOI），不含任何平台正文。
"""

from __future__ import annotations

import argparse
import http.client
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable

USER_AGENT = "impad-lit-review/1.0 (mailto:research@example.org)"
CROSSREF_WORKS = "https://api.crossref.org/works"
ANTHOLOGY_VOLUME = "https://aclanthology.org/volumes/{volume}.bib"
ARXIV_API = "http://export.arxiv.org/api/query"


# ---------------------------------------------------------------------------
# 语料侧：从 docs/ 的项目定位提炼出的主题词
# ---------------------------------------------------------------------------

TOPICS: dict[str, list[str]] = {
    "covert_advertising": [
        r"covert ad", r"implicit ad", r"undisclosed", r"ad disclosure",
        r"advertising disclosure", r"sponsor(ed|ship)", r"native ad",
        r"advertorial", r"brand placement", r"product placement",
        r"promoted post", r"influencer market", r"stealth market",
        r"paid partnership", r"ad labelling",
        r"disclosure (classification|detection|label)", r"paid content",
    ],
    "ad_detection": [
        r"ad detection", r"advertising detection", r"detect\w* ad",
        r"commercial intent", r"promotional intent", r"advertisement classification",
        r"spam detection", r"commercial content", r"ad classification", r"advertis",
    ],
    "multimodal": [
        r"multimodal", r"image[- ]text", r"vision[- ]language",
        r"visual advertis", r"\bocr\b", r"cross[- ]modal",
    ],
    "creator_history": [
        r"influencer", r"creator econom", r"user history", r"temporal",
        r"preference (shift|drift|change)", r"topic drift", r"longitudinal",
        r"author profile", r"style (change|shift)",
    ],
    "compliance_rag": [
        r"regulat", r"compliance", r"legal", r"statute", r"retrieval[- ]augmented",
        r"citation", r"grounded",
    ],
    "agent_system": [
        r"multi[- ]agent", r"\bagent", r"tool (use|call)", r"function call",
        r"\bmcp\b", r"a2a",
    ],
}

# 会议清单之外的高精度短语检索：有些最贴题的工作发表在 workshop/期刊上，
# 只按会议前缀检索会漏掉，所以额外做一轮不限 prefix 的检索。
GLOBAL_QUERIES = [
    "covert advertising detection",
    "implicit advertising detection",
    "undisclosed advertising social media",
    "advertorial detection",
    "influencer disclosure compliance",
]

# 各 DOI 前缀在 Crossref 里的条目类型不同：ACL/ACM/IEEE/IJCAI 用
# proceedings-article，AAAI 与 ICWSM 注册为 journal-article，Springer LNCS
# 混用 proceedings-article/book-chapter，因此这两组不做类型过滤。
PREFIX_TYPES: dict[str, str | None] = {
    "10.18653": "proceedings-article",
    "10.1609": "journal-article",
    "10.1145": "proceedings-article",
    "10.1109": "proceedings-article",
    "10.1007": None,
    "10.24963": "proceedings-article",
}

# 广告/推广语义的"硬门槛"：只有命中这些词条的题录才进入结果集。
# 否则 multimodal / compliance / agent 这类泛术语会把整届会议都捞进来（实测
# AAAI 一届就能命中上百条无关记录）。
CORE_PATTERNS = [
    r"advertis", r"\bads?\b", r"sponsor", r"promoted (post|content|tweet)",
    r"brand placement", r"product placement", r"advertorial", r"native ad",
    r"commercial intent", r"promotional (content|intent|post)",
    r"influencer", r"creator econom", r"ad disclosure", r"undisclosed",
    r"paid partnership", r"ad labelling", r"advertising detection",
    r"ad classification", r"ad targeting",
    r"disclosure (classification|detection|label)", r"paid content", r"brand mention",
]

# Crossref 的相关性检索式（自然语言，不是布尔式）
CROSSREF_QUERIES = [
    "covert advertising detection social media",
    "implicit advertising undisclosed sponsorship",
    "influencer advertising disclosure",
    "native advertising detection",
    "promoted post commercial intent detection",
    "multimodal advertising detection image text",
    "influencer creator history modeling",
    "advertising regulation compliance",
]


# ---------------------------------------------------------------------------
# 会议侧：候选会议 + DOI 前缀 + proceedings container 正则
# ---------------------------------------------------------------------------


@dataclass
class Venue:
    key: str
    label: str
    prefix: str
    patterns: list[str]
    rationale: str
    hits: int = 0


VENUES: list[Venue] = [
    Venue(
        "acl", "ACL (Annual Meeting of the ACL)", "10.18653",
        [r"Annual Meeting of the Association for Computational Linguistics"],
        "NLP 主会：披露文本、隐性广告的文本证据、RAG 引用",
    ),
    Venue(
        "emnlp", "EMNLP (+ Findings)", "10.18653",
        [r"Empirical Methods in Natural Language Processing"],
        "应用 NLP 主战场：推广意图分类、误导性内容检测",
    ),
    Venue(
        "naacl", "NAACL (+ Findings)", "10.18653",
        [r"North American Chapter of the Association for Computational Linguistics"],
        "北美 ACL 分会，社交媒体文本任务集中",
    ),
    Venue(
        "eacl", "EACL (+ Findings)", "10.18653",
        [r"European Chapter of the Association for Computational Linguistics"],
        "欧洲 ACL 分会",
    ),
    Venue(
        "coling", "COLING", "10.18653",
        [r"International Conference on Computational Linguistics"],
        "COLING 主会，多语言/社会媒体",
    ),
    Venue(
        "icwsm", "ICWSM", "10.1609",
        [r"Web and Social Media"],
        "最贴题：社交媒体推广内容、影响者披露的实证研究",
    ),
    Venue(
        "aaai", "AAAI", "10.1609",
        [r"AAAI Conference on Artificial Intelligence"],
        "通用 AI：检测模型、多模态方法",
    ),
    Venue(
        "kdd", "KDD", "10.1145",
        [r"Knowledge Discovery and Data Mining"],
        "广告/垃圾内容检测、图学习与行为建模",
    ),
    Venue(
        "www", "WWW / The Web Conference", "10.1145",
        [r"Web Conference", r"World Wide Web Conference"],
        "Web 广告生态、影响者营销、虚假推广",
    ),
    Venue(
        "wsdm", "WSDM", "10.1145",
        [r"Web Search and Data Mining"],
        "检索/推荐中的商业意图与赞助内容",
    ),
    Venue(
        "cikm", "CIKM", "10.1145",
        [r"Information and Knowledge Management"],
        "多模态内容理解与广告应用",
    ),
    Venue(
        "sigir", "SIGIR", "10.1145",
        [r"Research and Development in Information Retrieval"],
        "赞助搜索、广告检索与排序",
    ),
    Venue(
        "mm", "ACM Multimedia", "10.1145",
        [r"ACM (International Conference on )?Multimedia"],
        "多模态（图像+文本）广告与商品理解",
    ),
    Venue(
        "chi", "CHI", "10.1145",
        [r"Human Factors in Computing Systems"],
        "人因侧：用户能否识别披露、暗广感知实验",
    ),
    Venue(
        "cscw", "CSCW", "10.1145",
        [r"Computer[- ]Supported Cooperative Work"],
        "创作者经济、平台劳动与披露规范",
    ),
    Venue(
        "cvpr", "CVPR", "10.1109",
        [r"Computer Vision and Pattern Recognition"],
        "视觉广告/品牌/LOGO 检测、场景文字 OCR",
    ),
    Venue(
        "iccv", "ICCV", "10.1109",
        [r"International Conference on Computer Vision"],
        "视觉广告检测",
    ),
    Venue(
        "eccv", "ECCV", "10.1007",
        [r"Computer Vision\s*.?\s*ECCV"],
        "视觉广告检测（Springer LNCS 卷）",
    ),
    Venue(
        "ijcai", "IJCAI", "10.24963",
        [r"International Joint Conference on Artificial Intelligence"],
        "通用 AI：检测与社会计算",
    ),
]


# ---------------------------------------------------------------------------
# HTTP：标准库实现，带退避重试与截断容忍
# ---------------------------------------------------------------------------


def http_get(url: str, params: dict | None = None, *, retries: int = 4, timeout: int = 120) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    delay = 2.0
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except http.client.IncompleteRead:
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError(f"GET failed after retries: {url}")


def http_get_json(url: str, params: dict | None = None) -> dict:
    return json.loads(http_get(url, params).decode("utf-8", errors="replace"))


# ---------------------------------------------------------------------------
# 归会与相关度
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip()


def match_topics(text: str) -> list[str]:
    lowered = text.lower()
    if not any(re.search(p, lowered) for p in CORE_PATTERNS):
        return []
    topics = [topic for topic, patterns in TOPICS.items() if any(re.search(p, lowered) for p in patterns)]
    return topics or ["advertising_general"]


def correct_year(doi: str, year: str) -> str:
    """AAAI / ICWSM 的 Crossref issued 是上线日期，用 DOI 卷号还原会议年份。"""
    match = re.search(r"(aaai|icwsm)\.v(\d+)i", doi)
    if not match:
        return year
    volume = int(match.group(2))
    return str(1986 + volume) if match.group(1) == "aaai" else str(2006 + volume)


def venue_of(container: str, prefix: str) -> Venue | None:
    for venue in VENUES:
        if venue.prefix != prefix:
            continue
        if any(re.search(pattern, container, re.I) for pattern in venue.patterns):
            return venue
    return None


def collect(prefix: str, group: list[Venue], min_year: int, max_year: int, rows: int) -> list[dict]:
    records: list[dict] = []
    for query in CROSSREF_QUERIES:
        type_filter = PREFIX_TYPES.get(prefix)
        params = {
            "query.bibliographic": query,
            "filter": ",".join(
                part
                for part in (
                    f"prefix:{prefix}",
                    f"type:{type_filter}" if type_filter else "",
                    f"from-pub-date:{min_year}-01-01",
                    f"until-pub-date:{max_year}-12-31",
                )
                if part
            ),
            "rows": rows,
            "select": "DOI,title,container-title,issued,abstract,author,type",
            "mailto": "research@example.org",
        }
        try:
            payload = http_get_json(CROSSREF_WORKS, params)
        except Exception as error:
            print(f"  ! {prefix} '{query}' failed: {error}", file=sys.stderr)
            continue
        for item in payload.get("message", {}).get("items", []):
            container = " ".join(item.get("container-title") or [])
            venue = venue_of(container, prefix)
            if venue is None:
                continue
            title = normalize_text((item.get("title") or [""])[0])
            abstract = re.sub(r"<[^>]+>", " ", item.get("abstract") or "")
            topics = match_topics(f"{title} {abstract}")
            if not topics:
                continue
            issued = item.get("issued", {}).get("date-parts", [[None]])[0]
            year = str(issued[0]) if issued and issued[0] else ""
            doi = item.get("DOI", "")
            year = correct_year(doi, year)
            if year.isdigit() and not (min_year <= int(year) <= max_year):
                continue
            authors = "; ".join(
                normalize_text(f"{a.get('given','')} {a.get('family','')}").strip()
                for a in item.get("author") or []
            )
            records.append(
                {
                    "venue_key": venue.key,
                    "venue": normalize_text(container) or venue.label,
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "doi": doi,
                    "doi_url": f"https://doi.org/{doi}" if doi else "",
                    "topics": topics,
                    "query": query,
                    "source": "crossref",
                }
            )
            venue.hits += 1
        time.sleep(1.0)  # Crossref 公开池礼貌间隔
    return records


_BIB_FIELD = re.compile(
    r"^\s*(\w+)\s*=\s*(?:\"((?:[^\"]|\n)*?)\"|\{((?:[^{}]|\{[^{}]*\})*)\})\s*,?\s*$",
    re.M | re.S,
)


def parse_bib(text: str) -> list[dict]:
    """极简 BibTeX 解析：只取题名/作者/年份/DOI/会议名/摘要。"""
    entries: list[dict] = []
    starts = [(m.start(), m.group(1), m.group(2)) for m in re.finditer(r"^@(\w+)\{([^,]+),", text, re.M)]
    for index, (start, entry_type, key) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        fields: dict[str, str] = {}
        for match in _BIB_FIELD.finditer(text[start:end]):
            value = match.group(2) if match.group(2) is not None else match.group(3)
            if value:
                fields[match.group(1).lower()] = normalize_text(value)
        if fields:
            entries.append(
                {
                    "type": entry_type.lower(),
                    "title": fields.get("title", ""),
                    "authors": fields.get("author", ""),
                    "year": fields.get("year", ""),
                    "doi": fields.get("doi", "").lower(),
                    "url": fields.get("url", ""),
                    "booktitle": fields.get("booktitle", ""),
                    "abstract": fields.get("abstract", ""),
                }
            )
    return entries


ANTHOLOGY_VOLUME_SUFFIXES: dict[str, list[str]] = {
    "acl": ["acl-long", "acl-short", "acl-main", "findings-acl"],
    "emnlp": ["emnlp-main", "emnlp-short", "findings-emnlp"],
    "naacl": ["naacl-long", "naacl-main", "findings-naacl"],
    "eacl": ["eacl-main", "eacl-long", "findings-eacl"],
    "coling": ["coling-main", "coling-1", "coling-2"],
}


def collect_anthology(venue: Venue, min_year: int, max_year: int) -> list[dict]:
    """ACL Anthology 逐卷抓取：ACL 系会议的全量主会/Findings 论文都带 DOI。"""
    records: list[dict] = []
    for year in range(min_year, max_year + 1):
        for suffix in ANTHOLOGY_VOLUME_SUFFIXES.get(venue.key, []):
            volume = f"{year}.{suffix}"
            try:
                raw = http_get(ANTHOLOGY_VOLUME.format(volume=volume), timeout=180)
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    continue
                print(f"  ! anthology {volume}: HTTP {error.code}", file=sys.stderr)
                continue
            except Exception as error:
                print(f"  ! anthology {volume}: {error}", file=sys.stderr)
                continue
            for entry in parse_bib(raw.decode("utf-8", errors="replace")):
                if entry["type"] != "inproceedings":
                    continue
                topics = match_topics(f"{entry['title']} {entry['abstract']}")
                if not topics:
                    continue
                records.append(
                    {
                        "venue_key": venue.key,
                        "venue": entry["booktitle"] or venue.label,
                        "title": entry["title"],
                        "authors": entry["authors"],
                        "year": entry["year"] or str(year),
                        "doi": entry["doi"],
                        "doi_url": f"https://doi.org/{entry['doi']}" if entry["doi"] else "",
                        "topics": topics,
                        "query": f"anthology:{volume}",
                        "source": "acl-anthology",
                    }
                )
            time.sleep(0.3)
    venue.hits += len(records)
    return records


def collect_arxiv_ml(min_year: int, max_year: int) -> list[dict]:
    """NeurIPS/ICLR/ICML 不注册 DOI，用 arXiv 条目补位（记录 arXiv ID）。"""
    records: list[dict] = []
    ml_venue = re.compile(r"\b(neurips|nips|iclr|icml)\b", re.I)
    for query in CROSSREF_QUERIES:
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": 60,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        try:
            raw = http_get(ARXIV_API, params, timeout=120).decode("utf-8", errors="replace")
        except Exception as error:
            print(f"  ! arxiv '{query}': {error}", file=sys.stderr)
            continue
        for block in re.findall(r"<entry>(.*?)</entry>", raw, re.S):
            def pick(tag: str) -> str:
                found = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
                return normalize_text(re.sub(r"<[^>]+>", " ", found.group(1))) if found else ""

            meta = " ".join([pick("arxiv:comment"), pick("arxiv:journal_ref"), pick("title")])
            if not ml_venue.search(meta):
                continue
            if not match_topics(f"{pick('title')} {pick('summary')}"):
                continue
            identifier = pick("id").rsplit("/", 1)[-1]
            year = pick("published")[:4]
            if not year.isdigit() or not (min_year <= int(year) <= max_year):
                continue
            records.append(
                {
                    "venue_key": "ml_preprint",
                    "venue": pick("arxiv:comment")[:120] or "NeurIPS/ICLR/ICML (arXiv)",
                    "title": pick("title"),
                    "authors": "; ".join(
                        normalize_text(re.sub(r"<[^>]+>", " ", a)).strip()
                        for a in re.findall(r"<name>(.*?)</name>", block, re.S)
                    ),
                    "year": year,
                    "doi": "",
                    "doi_url": f"https://arxiv.org/abs/{identifier}",
                    "topics": match_topics(f"{pick('title')} {pick('summary')}"),
                    "query": query,
                    "source": "arxiv",
                    "arxiv_id": identifier,
                }
            )
        time.sleep(3.0)  # arXiv 要求查询间隔
    return records


def collect_global_queries(min_year: int, max_year: int, rows: int = 40) -> list[dict]:
    """不限 DOI 前缀的高精度短语检索，用来兜住 workshop/期刊上的同题工作。

    只保留"计算/实证"口径的条目：广告营销与语言学的纯理论文章不进代码仓库的
    文献台账（它们可以另行人工补，但会淹没机器检索结果）。
    """
    specific = re.compile(
        r"covert ad|implicit ad|undisclosed (ad|sponsor|partner)|advertorial|"
        r"native ad|ad disclosure|advertising disclosure|paid partnership|advert",
        re.I,
    )
    computational = re.compile(
        r"detect|classif|model|\bllm\b|large language|dataset|benchmark|deep learning|"
        r"machine learning|neural|embedding|annotation|empirical|evidence|regulation|"
        r"compliance|law|policy",
        re.I,
    )
    records: list[dict] = []
    for query in GLOBAL_QUERIES:
        params = {
            "query.bibliographic": query,
            "filter": f"from-pub-date:{min_year}-01-01,until-pub-date:{max_year}-12-31",
            "rows": rows,
            "select": "DOI,title,container-title,issued,abstract,author,type",
            "mailto": "research@example.org",
        }
        try:
            payload = http_get_json(CROSSREF_WORKS, params)
        except Exception as error:
            print(f"  ! global '{query}' failed: {error}", file=sys.stderr)
            continue
        for item in payload.get("message", {}).get("items", []):
            title = normalize_text((item.get("title") or [""])[0])
            if not specific.search(title):
                continue
            abstract = re.sub(r"<[^>]+>", " ", item.get("abstract") or "")
            if not computational.search(f"{title} {abstract}"):
                continue
            if not match_topics(title):
                continue
            issued = item.get("issued", {}).get("date-parts", [[None]])[0]
            year = str(issued[0]) if issued and issued[0] else ""
            if not year.isdigit() or not (min_year <= int(year) <= max_year):
                continue
            doi = item.get("DOI", "")
            records.append(
                {
                    "venue_key": "other_venue",
                    "venue": normalize_text(" ".join(item.get("container-title") or [])) or "(unknown)",
                    "title": title,
                    "authors": "; ".join(
                        normalize_text(f"{a.get('given','')} {a.get('family','')}").strip()
                        for a in item.get("author") or []
                    ),
                    "year": year,
                    "doi": doi,
                    "doi_url": f"https://doi.org/{doi}" if doi else "",
                    "topics": match_topics(title),
                    "query": query,
                    "source": "crossref-global",
                }
            )
        time.sleep(1.0)
    return records


def dedupe(records: Iterable[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for record in records:
        key = (record.get("doi") or "").lower() or re.sub(r"\W+", "", record["title"].lower())
        if key in merged:
            merged[key]["topics"] = sorted(set(merged[key]["topics"]) | set(record["topics"]))
            continue
        merged[key] = record
    return sorted(merged.values(), key=lambda r: (r["venue_key"], -int(r["year"] or 0), r["title"]))


def write_markdown(records: list[dict], venues: list[Venue], meta: dict, path: Path) -> None:
    """生成按会议分组的 Markdown 表格（自动产出，不手写）。"""
    lines = [
        "# 按会议检索结果（自动生成）",
        "",
        f"> 生成脚本：`{meta['generated_by']}`；数据源：{'/'.join(meta['sources'])}；"
        f"年份窗口：{meta['year_range'][0]}–{meta['year_range'][1]}。",
        f"> 共 {meta['total_records']} 条记录，其中 {meta['records_with_doi']} 条带 DOI。",
        "",
        "## 按会议计数",
        "",
        "| 会议 | 命中条数 | 会议定位 |",
        "| --- | ---: | --- |",
    ]
    counts = {}
    for record in records:
        counts[record["venue_key"]] = counts.get(record["venue_key"], 0) + 1
    for venue in venues:
        if not counts.get(venue.key):
            continue
        lines.append(f"| {venue.label} | {counts[venue.key]} | {venue.rationale} |")
    if counts.get("ml_preprint"):
        lines.append(f"| NeurIPS/ICLR/ICML（arXiv 补位，无 DOI） | {counts['ml_preprint']} | 方法侧参考 |")
    if counts.get("other_venue"):
        lines.append(f"| 会议清单之外（workshop/期刊兜底） | {counts['other_venue']} | 同题工作的补充来源 |")
    lines.append("")

    extra = [Venue("other_venue", "会议清单之外（workshop / 期刊）", "", [], "高精度短语兜底检索命中")]
    for venue in venues + [Venue("ml_preprint", "NeurIPS/ICLR/ICML（arXiv）", "", [], "无 DOI，按 arXiv ID 引用")] + extra:
        rows = [r for r in records if r["venue_key"] == venue.key]
        if not rows:
            continue
        lines.append(f"## {venue.label}（{len(rows)} 条）")
        lines.append("")
        lines.append("| 年份 | 题名 | DOI | 主题标签 |")
        lines.append("| ---: | --- | --- | --- |")
        for record in rows:
            doi = record.get("doi") or "—"
            link = f"[{doi}](https://doi.org/{doi})" if record.get("doi") else f"[arXiv:{record.get('arxiv_id','')}]({record['doi_url']})"
            title = record["title"].replace("|", "\\|")[:160]
            lines.append(f"| {record['year']} | {title} | {link} | {', '.join(record['topics'])} |")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default="docs/literature/venue_search_results.json")
    parser.add_argument("--markdown", default="", help="同时输出按会议分组的 Markdown 表")
    parser.add_argument("--min-year", type=int, default=2019)
    parser.add_argument("--max-year", type=int, default=2026)
    parser.add_argument("--rows", type=int, default=500, help="Crossref 每次查询取回条数")
    parser.add_argument("--venues", nargs="*", help="只跑指定会议 key；默认全部")
    parser.add_argument("--limit-venues", type=int, default=0, help="冒烟用：只跑前 N 个会议")
    parser.add_argument("--no-anthology", action="store_true", help="跳过 ACL Anthology 逐卷抓取")
    parser.add_argument("--with-arxiv", action="store_true", help="额外补 NeurIPS/ICLR/ICML 的 arXiv 条目")
    parser.add_argument("--stage", choices=["all", "global"], default="all",
                        help="all=完整检索；global=只重跑兜底短语并合并进已有 JSON")
    args = parser.parse_args(argv)

    wanted = set(args.venues or [])
    selected = [v for v in VENUES if not wanted or v.key in wanted]
    if args.limit_venues:
        selected = selected[: args.limit_venues]

    all_records: list[dict] = []
    existing: dict = {}

    if args.stage == "global":
        # 只重跑兜底短语：保留已有 JSON 的其余记录，替换 other_venue 部分
        existing_path = Path(args.output)
        if not existing_path.exists():
            print(f"! {existing_path} 不存在，无法只重跑 global 阶段", file=sys.stderr)
            return 2
        existing = json.loads(existing_path.read_text(encoding="utf-8"))
        all_records = [r for r in existing.get("records", []) if r["venue_key"] != "other_venue"]
        print(f"[global] 保留已有 {len(all_records)} 条非兜底记录", flush=True)
        found = collect_global_queries(args.min_year, args.max_year)
        print(f"  -> {len(found)} matched records", flush=True)
        all_records.extend(found)
    else:
        # 1) ACL 系会议走 Anthology 全量卷（召回高、DOI 原生）
        if not args.no_anthology:
            for venue in selected:
                if venue.key not in ANTHOLOGY_VOLUME_SUFFIXES:
                    continue
                print(f"[anthology] {venue.key}", flush=True)
                try:
                    found = collect_anthology(venue, args.min_year, args.max_year)
                except Exception as error:
                    print(f"  ! {venue.key} anthology failed: {error}", file=sys.stderr)
                    continue
                print(f"  -> {len(found)} matched records", flush=True)
                all_records.extend(found)

        # 2) 其余会议走 Crossref（按 DOI 前缀分组）
        by_prefix: dict[str, list[Venue]] = {}
        for venue in selected:
            by_prefix.setdefault(venue.prefix, []).append(venue)

        for prefix, group in by_prefix.items():
            label = "/".join(v.key for v in group)
            print(f"[crossref {prefix}] {label}", flush=True)
            found = collect(prefix, group, args.min_year, args.max_year, args.rows)
            print(f"  -> {len(found)} matched records", flush=True)
            all_records.extend(found)

        # 3) 无 DOI 的三个 ML 会议：用 arXiv 条目补位
        if args.with_arxiv:
            print("[arxiv] NeurIPS/ICLR/ICML", flush=True)
            found = collect_arxiv_ml(args.min_year, args.max_year)
            print(f"  -> {len(found)} matched records", flush=True)
            all_records.extend(found)

        # 4) 不限 prefix 的高精度短语检索（workshop / 期刊兜底）
        print("[crossref] 高精度短语（不限会议）", flush=True)
        found = collect_global_queries(args.min_year, args.max_year)
        print(f"  -> {len(found)} matched records", flush=True)
        all_records.extend(found)

    deduped = dedupe(all_records)
    with_doi = [r for r in deduped if r["doi"]]
    output = {
        "generated_by": "scripts/literature/venue_paper_search.py",
        "sources": existing.get("sources", ["acl-anthology", "crossref", "arxiv"]),
        "year_range": [args.min_year, args.max_year],
        "queries": CROSSREF_QUERIES,
        "topics": TOPICS,
        "total_records": len(deduped),
        "records_with_doi": len(with_doi),
        "venues": existing.get("venues")
        or [
            {
                "key": v.key,
                "label": v.label,
                "doi_prefix": v.prefix,
                "rationale": v.rationale,
                "matches": v.hits,
            }
            for v in selected
        ],
        "records": deduped,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown:
        write_markdown(deduped, selected, output, Path(args.markdown))
        print(f"wrote {args.markdown}")
    print(f"wrote {path} ({len(deduped)} records, {len(with_doi)} with DOI)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
