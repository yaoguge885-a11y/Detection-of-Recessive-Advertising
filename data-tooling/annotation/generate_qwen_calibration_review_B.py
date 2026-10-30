#!/usr/bin/env python3
"""Generate an isolated local review page for the 20-item Qwen calibration sample."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def relative_url(path: Path, output_dir: Path) -> str:
    return quote(os.path.relpath(path, output_dir).replace(os.sep, "/"), safe="/.")


def suggestion_index(auto_path: Path, suggest_path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in load_jsonl(auto_path):
        suggestion = row.get("_llm_suggestion") or {}
        result[str(row["post_id"])] = {
            "label": str(row.get("label") or suggestion.get("label") or "无建议"),
            "confidence": row.get("confidence"),
            "reasoning": str(suggestion.get("reasoning") or ""),
            "evidence_codes": suggestion.get("evidence_codes") or row.get("evidence_codes") or [],
            "evidence": suggestion.get("evidence") or row.get("evidence") or [],
        }
    for row in load_jsonl(suggest_path):
        suggestion = row.get("suggestion") or {}
        result[str(row["post_id"])] = {
            "label": str(suggestion.get("label") or "无建议"),
            "confidence": suggestion.get("confidence"),
            "reasoning": str(suggestion.get("reasoning") or ""),
            "evidence_codes": suggestion.get("evidence_codes") or [],
            "evidence": suggestion.get("evidence") or [],
        }
    return result


def build_items(repo: Path, output: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    report_root = repo / "data" / "reports" / "m1"
    run_root = repo / "data" / "run_outputs"
    manifest = json.loads(
        (report_root / "qwen_calibration_20_review_manifest.json").read_text(encoding="utf-8-sig")
    )
    records = {
        str(row["post_id"]): row
        for row in load_jsonl(run_root / "merged_20260728" / "anonymized_posts.jsonl")
    }
    suggestions = suggestion_index(
        run_root / "m1_calibration_50" / "auto_20260806_235155.jsonl",
        run_root / "m1_calibration_50" / "suggest_20260806_235155.jsonl",
    )
    items: list[dict[str, Any]] = []
    local_media = source_only = missing_media = 0
    for number, sample in enumerate(manifest["items"], start=1):
        post_id = str(sample["post_id"])
        record = records.get(post_id)
        if record is None:
            raise ValueError(f"Manifest post_id missing from canonical data: {post_id}")
        suggestion = suggestions.get(post_id, {})
        media_rows: list[dict[str, Any]] = []
        for media_number, media in enumerate(record.get("media") or [], start=1):
            media = media or {}
            ref = str(media.get("ref") or "")
            source_url = str(media.get("source_url") or "")
            local_path = run_root / "merged_20260728" / ref if ref else None
            availability = "unavailable"
            local_url = ""
            if local_path and local_path.is_file():
                availability = "local"
                local_url = relative_url(local_path, output.parent)
                local_media += 1
            elif ref:
                availability = "missing"
                missing_media += 1
            elif source_url:
                availability = "source_only"
                source_only += 1
            media_rows.append(
                {
                    "number": media_number,
                    "type": str(media.get("type") or "unknown"),
                    "ref": ref,
                    "source_url": source_url,
                    "availability": availability,
                    "local_url": local_url,
                }
            )
        comments = [
            {
                "comment_id": str((comment or {}).get("comment_id") or ""),
                "text": str((comment or {}).get("text") or ""),
            }
            for comment in (record.get("comments") or [])
        ]
        items.append(
            {
                "number": number,
                "post_id": post_id,
                "tier": str(sample["tier"]),
                "platform": str(record.get("platform") or "unknown"),
                "title": str(record.get("title") or "(无标题)"),
                "text": str(record.get("text") or ""),
                "comments": comments,
                "media": media_rows,
                "model": {
                    "label": str(suggestion.get("label") or sample.get("model_label") or "无建议"),
                    "confidence": suggestion.get("confidence", sample.get("confidence")),
                    "reasoning": str(suggestion.get("reasoning") or "未生成有效模型建议。"),
                    "evidence_codes": suggestion.get("evidence_codes") or [],
                    "evidence": suggestion.get("evidence") or [],
                },
            }
        )
    stats = {
        "records": len(items),
        "records_with_media": sum(bool(item["media"]) for item in items),
        "local_media": local_media,
        "source_only_media": source_only,
        "missing_media": missing_media,
    }
    return items, stats


def render(
    items: list[dict[str, Any]],
    stats: dict[str, int],
    fingerprint: str,
    reviewer_id: str,
) -> str:
    data = json.dumps(items, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    stats_json = json.dumps(stats, ensure_ascii=False, separators=(",", ":"))
    fingerprint_json = json.dumps(fingerprint)
    reviewer_json = json.dumps(reviewer_id)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>M1 Qwen 20 条合理性复核 — {html.escape(reviewer_id)}</title>
<style>
:root{{--bg:#f4f6f8;--card:#fff;--text:#20242b;--muted:#667085;--line:#d8dee8;--blue:#1769e0;--green:#177a4f;--red:#c33;}}
*{{box-sizing:border-box}}body{{margin:0;font-family:system-ui,"Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text)}}
header{{position:sticky;top:0;z-index:10;background:var(--card);border-bottom:1px solid var(--line);padding:12px 18px}}h1{{font-size:20px;margin:0}}
.bar,.nav,.choices{{display:flex;gap:9px;align-items:center;flex-wrap:wrap}}.bar{{margin-top:9px}}button,select,input,textarea{{font:inherit;border:1px solid var(--line);border-radius:7px;padding:7px 9px;background:#fff;color:var(--text)}}button{{cursor:pointer}}button:hover{{border-color:var(--blue)}}
main{{max-width:1450px;margin:16px auto;padding:0 16px 50px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:17px}}h2{{margin:0 0 8px;font-size:19px}}.meta,.hint{{color:var(--muted);font-size:13px;line-height:1.7}}.pill{{display:inline-block;border:1px solid var(--line);border-radius:99px;padding:2px 8px;margin-right:5px}}
.guide{{background:#eef5ff;border-left:4px solid var(--blue);padding:10px 12px;margin:12px 0;line-height:1.6}}.content{{white-space:pre-wrap;line-height:1.65;max-height:360px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:12px;background:#fafafa}}details{{margin:12px 0}}summary{{cursor:pointer;font-weight:600}}
.review{{border:2px solid var(--line);border-radius:10px;padding:13px;margin:14px 0}}.field{{margin:10px 0}}label{{margin-right:12px}}textarea{{width:100%;min-height:70px}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}}.thumb{{padding:0;overflow:hidden;text-align:left}}.thumb img{{display:block;width:100%;height:180px;object-fit:contain;background:#111}}.thumb span{{display:block;padding:6px;font-size:12px;color:var(--muted)}}
.model{{background:#fff8e8;border:1px solid #eed59a;border-radius:9px;padding:12px}}.ok{{color:var(--green)}}.warning{{color:var(--red)}}#lightbox{{display:none;position:fixed;inset:0;z-index:30;background:rgba(0,0,0,.9);align-items:center;justify-content:center}}#lightbox.open{{display:flex}}#lightbox img{{max-width:96vw;max-height:94vh}}#lightbox button{{position:absolute;right:18px;top:15px;font-size:22px}}a{{color:var(--blue)}}
</style></head><body>
<header><h1>M1 Qwen 20 条合理性复核 — {html.escape(reviewer_id)}</h1><div class="bar"><span id="progress"></span><select id="filter"><option value="all">全部</option><option value="pending">未完成</option><option value="done">已完成</option></select><button id="prev">← 上一条</button><span id="counter"></span><button id="next">下一条 →</button><button id="export">校验并导出 JSON</button></div></header>
<main><div class="guide"><b>标签顺序：</b>先判断是否在范围内，再判断是否有充分商业推广意图，最后看是否有明确广告/赞助/合作/赠送/受邀/平台商业标识。明广=商业意图充分且有明确披露；暗广=商业意图充分、披露区域完整但无明确披露；非广=商业意图证据不足。建议先独立选 {html.escape(reviewer_id)} 标签，再展开 Qwen 建议。</div><div id="view"></div></main>
<div id="lightbox"><button id="close">×</button><img id="large" alt="放大预览"></div>
<script>
const items={data},stats={stats_json},fingerprint={fingerprint_json},reviewer={reviewer_json},key=`m1-qwen-calibration-20-${{reviewer}}-v1`;let saved=JSON.parse(localStorage.getItem(key)||'{{}}'),filtered=[],current=0;
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function complete(x){{const v=saved[x.post_id]||{{}};return !!(v.label&&v.reasonable&&v.saved_time&&v.reviewed);}}
function persist(id,patch){{saved[id]={{...(saved[id]||{{}}),...patch,updated_at:new Date().toISOString()}};localStorage.setItem(key,JSON.stringify(saved));updateProgress();}}
function apply(keep){{const mode=$('filter').value;filtered=items.filter(x=>mode==='all'||(mode==='done'?complete(x):!complete(x)));const i=keep?filtered.findIndex(x=>x.post_id===keep):-1;current=i>=0?i:Math.min(current,Math.max(0,filtered.length-1));render();}}
function updateProgress(){{const done=items.filter(complete).length;$('progress').innerHTML=`完成：<b class="${{done===items.length?'ok':''}}">${{done}} / ${{items.length}}</b>；媒体记录 ${{stats.records_with_media}} 条，本地媒体 ${{stats.local_media}} 个，仅来源 ${{stats.source_only_media}} 个`}}
function radios(name,values,selected){{return values.map(([v,t])=>`<label><input type="radio" name="${{name}}" value="${{v}}" ${{selected===v?'checked':''}}> ${{t}}</label>`).join('')}}
function render(){{updateProgress();$('counter').textContent=filtered.length?`${{current+1}} / ${{filtered.length}}`:'0 / 0';if(!filtered.length){{$('view').innerHTML='<div class="card">当前筛选没有记录。</div>';return}}const x=filtered[current],v=saved[x.post_id]||{{}};
const comments=x.comments.length?x.comments.map((c,i)=>`<div><b>评论 ${{i+1}}：</b>${{esc(c.text)}}</div>`).join(''):'无评论';
const local=x.media.filter(m=>m.availability==='local'),remote=x.media.filter(m=>m.availability==='source_only'),missing=x.media.filter(m=>m.availability==='missing');
$('view').innerHTML=`<section class="card"><h2>${{String(x.number).padStart(2,'0')}}. ${{esc(x.title)}}</h2><div class="meta"><span class="pill">${{esc(x.tier)}}</span><span class="pill">${{esc(x.platform)}}</span>${{esc(x.post_id)}}；媒体 ${{x.media.length}}</div>
<h3>原文</h3><div class="content">${{esc(x.text)}}</div><details><summary>评论（${{x.comments.length}}）</summary><div class="content">${{comments}}</div></details>
${{local.length?`<details open><summary>本地媒体（${{local.length}}，点击放大）</summary><div class="grid">${{local.map(m=>`<button class="thumb" data-src="${{m.local_url}}"><img loading="lazy" src="${{m.local_url}}"><span>媒体 ${{m.number}} · ${{esc(m.ref)}}</span></button>`).join('')}}</div></details>`:''}}
${{remote.length?`<details open><summary>仅来源媒体（${{remote.length}}）</summary>${{remote.map(m=>`<p>媒体 ${{m.number}}：<a target="_blank" rel="noreferrer" href="${{esc(m.source_url)}}">打开来源</a></p>`).join('')}}</details>`:''}}${{missing.length?`<p class="warning">缺失本地媒体：${{missing.length}}</p>`:''}}
<div class="review"><h3>${{esc(reviewer)}} 独立复核</h3><div class="field"><b>1. ${{esc(reviewer)}} 人工标签：</b>${{radios('label',[['明广','明广'],['暗广','暗广'],['非广','非广'],['uncertain','uncertain'],['out_of_scope','out_of_scope']],v.label)}}</div>
<details id="modelBox"><summary>2. 展开 Qwen 建议并判断合理性</summary><div class="model"><b>Qwen：</b>${{esc(x.model.label)}}；confidence=${{x.model.confidence??'null'}}；evidence codes=${{esc((x.model.evidence_codes||[]).join(','))}}<p>${{esc(x.model.reasoning)}}</p>${{(x.model.evidence||[]).map(e=>`<div>• ${{esc(e)}}</div>`).join('')}}</div><div class="field"><b>建议是否合理：</b>${{radios('reasonable',[['yes','yes'],['no','no'],['na','n/a（无有效建议）']],v.reasonable)}}</div><div class="field"><b>是否节省判断时间：</b>${{radios('saved_time',[['yes','yes'],['no','no'],['na','n/a（无有效建议）']],v.saved_time)}}</div></details>
<div class="field"><b>主要错误类型：</b><select id="error"><option value="">请选择/无错误</option>${{[['none','无错误'],['wrong_label','标签错误'],['unsupported_evidence','证据不支持'],['missing_evidence','漏掉关键证据'],['model_error','模型无有效输出'],['other','其他']].map(([a,b])=>`<option value="${{a}}" ${{v.error_type===a?'selected':''}}>${{b}}</option>`).join('')}}</select></div>
<div class="field"><b>备注：</b><textarea id="notes" placeholder="简要写支持人工标签的证据，或说明模型为什么错">${{esc(v.notes||'')}}</textarea></div><label><input id="reviewed" type="checkbox" ${{v.reviewed?'checked':''}}> 我已查看原文、评论和所有可用媒体，并完成本条复核</label></div></section>`;
document.querySelectorAll('input[name=label]').forEach(e=>e.onchange=()=>persist(x.post_id,{{label:e.value}}));document.querySelectorAll('input[name=reasonable]').forEach(e=>e.onchange=()=>persist(x.post_id,{{reasonable:e.value}}));document.querySelectorAll('input[name=saved_time]').forEach(e=>e.onchange=()=>persist(x.post_id,{{saved_time:e.value}}));$('error').onchange=e=>persist(x.post_id,{{error_type:e.target.value}});$('notes').oninput=e=>persist(x.post_id,{{notes:e.target.value}});$('reviewed').onchange=e=>{{persist(x.post_id,{{reviewed:e.target.checked}});if($('filter').value!=='all')apply(x.post_id)}};document.querySelectorAll('.thumb').forEach(b=>b.onclick=()=>{{$('large').src=b.dataset.src;$('lightbox').classList.add('open')}});
}}
$('filter').onchange=()=>apply();$('prev').onclick=()=>{{if(filtered.length){{current=(current-1+filtered.length)%filtered.length;render();scrollTo(0,0)}}}};$('next').onclick=()=>{{if(filtered.length){{current=(current+1)%filtered.length;render();scrollTo(0,0)}}}};
$('close').onclick=()=>{{$('lightbox').classList.remove('open');$('large').src=''}};$('lightbox').onclick=e=>{{if(e.target===$('lightbox'))$('close').click()}};
$('export').onclick=()=>{{const missing=items.filter(x=>!complete(x));if(missing.length){{alert(`还有 ${{missing.length}} 条未完成：${{missing.map(x=>String(x.number).padStart(2,'0')).join(', ')}}`);return}}const rows=items.map(x=>({{number:x.number,post_id:x.post_id,tier:x.tier,model_label:x.model.label,model_confidence:x.model.confidence,...saved[x.post_id]}}));const payload={{status:'completed_independent_human_review',reviewer,exported_at:new Date().toISOString(),dataset_fingerprint_sha256:fingerprint,sample_count:items.length,items:rows}};const blob=new Blob([JSON.stringify(payload,null,2)],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`qwen_calibration_20_human_review_${{reviewer}}.json`;a.click();URL.revokeObjectURL(a.href)}};
apply();
</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reviewer-id", choices=("A", "B"), default="B")
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (
        args.output
        or repo / "data" / "reports" / "m1" / f"qwen_calibration_20_review_{args.reviewer_id}.html"
    ).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(
        (repo / "data" / "reports" / "m1" / "qwen_calibration_20_review_manifest.json").read_text(encoding="utf-8-sig")
    )
    items, stats = build_items(repo, output)
    output.write_text(
        render(items, stats, str(manifest["dataset_fingerprint_sha256"]), args.reviewer_id),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), **stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
