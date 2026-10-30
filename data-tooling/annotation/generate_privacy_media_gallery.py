#!/usr/bin/env python3
"""Generate a local, source-linked media gallery for M1 privacy review."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote


HEADING_RE = re.compile(r"^### ([MS]-\d{3}) `(post_[0-9a-f]{32})`$")
DRAFT_RE = re.compile(r"^- AI draft: \*\*(allow|redact|exclude)\*\*")
STATE_RE = re.compile(r"^- Source state: \*\*([^*]+)\*\*")
STATUS_RE = re.compile(r"^- Status: (.+)$")


def load_review_index(path: Path) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        heading = HEADING_RE.fullmatch(line)
        if heading:
            item, post_id = heading.groups()
            current = {
                "item": item,
                "post_id": post_id,
                "queue": "mandatory" if item.startswith("M-") else "sample",
                "draft": "unknown",
                "source_state": "unknown",
                "text_status": "unknown",
            }
            index[post_id] = current
            continue
        if current is None:
            continue
        draft = DRAFT_RE.match(line)
        if draft:
            current["draft"] = draft.group(1)
            continue
        state = STATE_RE.match(line)
        if state:
            current["source_state"] = state.group(1)
            continue
        status = STATUS_RE.match(line)
        if status:
            current["text_status"] = status.group(1)
    return index


def load_records(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            records[str(record["post_id"])] = record
    return records


def relative_file_url(path: Path, output_dir: Path) -> str:
    relative = os.path.relpath(path, output_dir).replace(os.sep, "/")
    return quote(relative, safe="/.")


def build_gallery_data(
    review_index: dict[str, dict[str, str]],
    records: dict[str, dict[str, Any]],
    media_root: Path,
    output_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    items: list[dict[str, Any]] = []
    stats = {
        "records": len(review_index),
        "records_with_media": 0,
        "local_media": 0,
        "source_only_media": 0,
        "missing_local_media": 0,
    }
    ordered = sorted(
        review_index.values(),
        key=lambda item: (item["item"][0], int(item["item"].split("-")[1])),
    )
    for review in ordered:
        post_id = review["post_id"]
        record = records.get(post_id)
        if record is None:
            raise KeyError(f"Review post_id missing from source records: {post_id}")
        media_entries: list[dict[str, str]] = []
        for number, media in enumerate(record.get("media") or [], start=1):
            media = media or {}
            ref = str(media.get("ref") or "")
            source_url = str(media.get("source_url") or "")
            media_type = str(media.get("type") or "unknown")
            entry = {
                "number": str(number),
                "type": media_type,
                "ref": ref,
                "source_url": source_url,
                "local_url": "",
                "availability": "unavailable",
            }
            if ref:
                local_path = media_root / ref
                if local_path.is_file():
                    entry["local_url"] = relative_file_url(local_path, output_dir)
                    entry["availability"] = "local"
                    stats["local_media"] += 1
                else:
                    entry["availability"] = "missing"
                    stats["missing_local_media"] += 1
            elif source_url:
                entry["availability"] = "source_only"
                stats["source_only_media"] += 1
            media_entries.append(entry)
        if not media_entries:
            continue
        stats["records_with_media"] += 1
        items.append(
            {
                **review,
                "title": str(record.get("title") or "(无标题)"),
                "platform": str(record.get("platform") or "unknown"),
                "media": media_entries,
                "local_count": sum(
                    item["availability"] == "local" for item in media_entries
                ),
                "source_only_count": sum(
                    item["availability"] == "source_only" for item in media_entries
                ),
            }
        )
    return items, stats


def render_html(items: list[dict[str, Any]], stats: dict[str, int]) -> str:
    data_json = json.dumps(items, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    stats_json = json.dumps(stats, ensure_ascii=False, separators=(",", ":"))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>M1 隐私媒体审核图库</title>
<style>
:root {{ color-scheme: light dark; --bg:#f5f6f8; --card:#fff; --text:#20242b; --muted:#667085; --line:#d9dee7; --blue:#2563eb; --red:#c62828; --green:#18794e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#15171b; --card:#202329; --text:#f1f3f5; --muted:#a8b0bd; --line:#39404a; --blue:#75a7ff; --red:#ff8a80; --green:#71d5a5; }} }}
* {{ box-sizing:border-box; }} body {{ margin:0; font-family:system-ui,"Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); }}
header {{ position:sticky; top:0; z-index:20; background:var(--card); border-bottom:1px solid var(--line); padding:12px 18px; }}
.title-row,.toolbar,.nav,.review-row {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }} h1 {{ font-size:20px; margin:0 12px 0 0; }}
.stats {{ color:var(--muted); font-size:13px; }} .toolbar {{ margin-top:10px; }} select,input,button,textarea {{ font:inherit; border:1px solid var(--line); border-radius:7px; background:var(--card); color:var(--text); padding:7px 9px; }}
button {{ cursor:pointer; }} button:hover {{ border-color:var(--blue); }} input[type=search] {{ min-width:180px; }}
main {{ max-width:1500px; margin:16px auto; padding:0 16px 50px; }} .record {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }}
.record h2 {{ margin:0 0 8px; font-size:19px; }} .meta {{ color:var(--muted); line-height:1.7; font-size:14px; }} .pill {{ display:inline-block; padding:2px 8px; border:1px solid var(--line); border-radius:999px; margin-right:5px; }}
.review-row {{ border:1px solid var(--line); border-radius:9px; padding:10px; margin:14px 0; }} .clean.active {{ background:var(--green); color:white; }} .risk.active {{ background:var(--red); color:white; }} textarea {{ flex:1; min-width:240px; min-height:40px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:12px; margin-top:14px; }} .thumb {{ padding:0; overflow:hidden; text-align:left; background:var(--card); }}
.thumb img {{ width:100%; height:180px; object-fit:contain; display:block; background:#0b0c0e; }} .thumb span {{ display:block; padding:7px; color:var(--muted); font-size:12px; }}
.source-list {{ display:grid; gap:8px; margin-top:12px; }} .source-link {{ border:1px solid var(--line); border-radius:8px; padding:10px; overflow-wrap:anywhere; }} a {{ color:var(--blue); }}
.empty {{ color:var(--muted); padding:40px; text-align:center; }} #lightbox {{ display:none; position:fixed; inset:0; z-index:50; background:rgba(0,0,0,.9); align-items:center; justify-content:center; padding:30px; }}
#lightbox.open {{ display:flex; }} #lightbox img {{ max-width:96vw; max-height:92vh; object-fit:contain; }} #lightbox button {{ position:absolute; top:15px; right:18px; font-size:22px; }}
.warning {{ color:var(--red); }} .counter {{ min-width:110px; text-align:center; color:var(--muted); }}
</style>
</head>
<body>
<header>
  <div class="title-row"><h1>M1 隐私媒体审核图库</h1><span class="stats" id="stats"></span></div>
  <div class="toolbar">
    <select id="queue"><option value="all">全部队列</option><option value="mandatory">强制 M</option><option value="sample">抽样 S</option></select>
    <select id="draft"><option value="all">全部建议</option><option value="allow">allow</option><option value="redact">redact</option><option value="exclude">exclude</option></select>
    <select id="mediaKind"><option value="all">全部媒体</option><option value="local">有本地图片</option><option value="source_only">仅来源视频</option></select>
    <select id="reviewFilter"><option value="all">全部媒体进度</option><option value="unreviewed">未审核</option><option value="clean">媒体正常</option><option value="risk">发现风险</option></select>
    <input id="search" type="search" placeholder="跳转 M020 / post_id / 标题">
    <button id="export">导出媒体审核 JSON</button>
  </div>
  <div class="nav" style="margin-top:10px"><button id="prev">← 上一条</button><span class="counter" id="counter"></span><button id="next">下一条 →</button></div>
</header>
<main><div id="content"></div></main>
<div id="lightbox"><button id="close">×</button><img id="large" alt="放大预览"></div>
<script>
const items={data_json}; const buildStats={stats_json}; const storageKey='m1-privacy-media-review-v1';
let saved=JSON.parse(localStorage.getItem(storageKey)||'{{}}'); let filtered=[]; let current=0;
const $=id=>document.getElementById(id); const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[c]));
function reviewOf(item){{return saved[item.post_id]?.status||'unreviewed';}}
function applyFilters(keepId){{
 const q=$('queue').value,d=$('draft').value,m=$('mediaKind').value,r=$('reviewFilter').value,s=$('search').value.trim().toLowerCase();
 filtered=items.filter(x=>(q==='all'||x.queue===q)&&(d==='all'||x.draft===d)&&(m==='all'||(m==='local'?x.local_count>0:x.source_only_count>0))&&(r==='all'||reviewOf(x)===r)&&(!s||x.item.toLowerCase().replace('-','').includes(s.replace('-',''))||x.item.toLowerCase().includes(s)||x.post_id.includes(s)||x.title.toLowerCase().includes(s)));
 let found=keepId?filtered.findIndex(x=>x.post_id===keepId):-1; current=found>=0?found:Math.min(current,Math.max(0,filtered.length-1)); render();
}}
function saveReview(item,status,note){{saved[item.post_id]={{status,note:note||'',reviewed_at:new Date().toISOString(),item:item.item}};localStorage.setItem(storageKey,JSON.stringify(saved));applyFilters(item.post_id);}}
function render(){{
 $('stats').textContent=`${{buildStats.records_with_media}} 条有媒体；${{buildStats.local_media}} 个本地文件；${{buildStats.source_only_media}} 个仅来源视频；进度保存在本浏览器`;
 $('counter').textContent=filtered.length?`${{current+1}} / ${{filtered.length}}`:'0 / 0';
 if(!filtered.length){{$('content').innerHTML='<div class="empty">当前筛选没有记录</div>';return;}}
 const x=filtered[current],rv=saved[x.post_id]||{{status:'unreviewed',note:''}};
 const local=x.media.filter(m=>m.availability==='local'); const remote=x.media.filter(m=>m.availability==='source_only'); const missing=x.media.filter(m=>m.availability==='missing');
 $('content').innerHTML=`<section class="record"><h2>${{esc(x.item)}} · ${{esc(x.title)}}</h2><div class="meta"><span class="pill">${{esc(x.draft)}}</span><span class="pill">${{esc(x.source_state)}}</span><span class="pill">${{esc(x.platform)}}</span><br>${{esc(x.post_id)}}<br>文本状态：${{esc(x.text_status)}}；媒体共 ${{x.media.length}}，本地 ${{x.local_count}}，仅来源 ${{x.source_only_count}}</div>
 <div class="review-row"><strong>媒体结论：</strong><button class="clean ${{rv.status==='clean'?'active':''}}" id="markClean">媒体正常</button><button class="risk ${{rv.status==='risk'?'active':''}}" id="markRisk">发现隐私风险</button><button id="clearReview">清空</button><textarea id="note" placeholder="可选：风险位于第几张、是什么内容">${{esc(rv.note||'')}}</textarea></div>
 ${{missing.length?`<p class="warning">有 ${{missing.length}} 个本地文件缺失。</p>`:''}}
 ${{local.length?`<h3>本地图片（点击放大）</h3><div class="grid">${{local.map(m=>`<button class="thumb" data-src="${{m.local_url}}"><img loading="lazy" src="${{m.local_url}}" alt="媒体 ${{m.number}}"><span>媒体 ${{m.number}} · ${{esc(m.type)}} · ${{esc(m.ref)}}</span></button>`).join('')}}</div>`:''}}
 ${{remote.length?`<h3>仅来源链接的视频</h3><p class="meta">这些记录没有本地视频文件，需要点击来源链接在浏览器中检查画面、字幕、二维码和账号水印。</p><div class="source-list">${{remote.map(m=>`<div class="source-link">媒体 ${{m.number}} · ${{esc(m.type)}} · <a target="_blank" rel="noreferrer" href="${{esc(m.source_url)}}">打开来源视频</a></div>`).join('')}}</div>`:''}}</section>`;
 document.querySelectorAll('.thumb').forEach(b=>b.onclick=()=>{{$('large').src=b.dataset.src;$('lightbox').classList.add('open');}});
 $('markClean').onclick=()=>saveReview(x,'clean',$('note').value); $('markRisk').onclick=()=>saveReview(x,'risk',$('note').value); $('clearReview').onclick=()=>{{delete saved[x.post_id];localStorage.setItem(storageKey,JSON.stringify(saved));applyFilters(x.post_id);}};
}}
['queue','draft','mediaKind','reviewFilter'].forEach(id=>$(id).onchange=()=>applyFilters()); $('search').oninput=()=>applyFilters();
$('prev').onclick=()=>{{if(filtered.length){{current=(current-1+filtered.length)%filtered.length;render();window.scrollTo(0,0);}}}}; $('next').onclick=()=>{{if(filtered.length){{current=(current+1)%filtered.length;render();window.scrollTo(0,0);}}}};
$('close').onclick=()=>{{$('lightbox').classList.remove('open');$('large').src='';}}; $('lightbox').onclick=e=>{{if(e.target===$('lightbox'))$('close').click();}}; document.onkeydown=e=>{{if(e.key==='Escape')$('close').click();if(e.key==='ArrowLeft')$('prev').click();if(e.key==='ArrowRight')$('next').click();}};
$('export').onclick=()=>{{const payload={{reviewer:'B',exported_at:new Date().toISOString(),scope:'M1 privacy media review',items:Object.entries(saved).map(([post_id,v])=>({{post_id,...v}}))}};const blob=new Blob([JSON.stringify(payload,null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='privacy_media_review_B.json';a.click();URL.revokeObjectURL(a.href);}};
applyFilters();
</script>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output = args.output or (
        repo_root
        / "data"
        / "reports"
        / "m1"
        / "privacy"
        / "privacy_media_gallery_B.html"
    )
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    privacy_dir = repo_root / "data" / "reports" / "m1" / "privacy"
    review_index = load_review_index(privacy_dir / "privacy_AI_pre_review_B.md")
    records = load_records(
        repo_root
        / "data"
        / "run_outputs"
        / "merged_20260728"
        / "anonymized_posts.jsonl"
    )
    items, stats = build_gallery_data(
        review_index,
        records,
        repo_root / "data" / "run_outputs" / "merged_20260728",
        output.parent,
    )
    output.write_text(render_html(items, stats), encoding="utf-8")
    print(json.dumps({"output": str(output), **stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
