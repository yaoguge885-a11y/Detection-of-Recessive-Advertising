#!/usr/bin/env python3
"""Generate a local, resumable HTML UI for B supplemental privacy review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mask_sensitive_pii import load_objects  # noqa: E402


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__PAGE_TITLE__</title>
<style>
:root{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#1f2937;background:#f3f4f6}
body{margin:0}header{position:sticky;top:0;z-index:20;background:#111827;color:#fff;padding:12px 18px;box-shadow:0 2px 8px #0004}
h1{font-size:18px;margin:0 0 9px}.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
button,select{font:inherit;border:1px solid #9ca3af;border-radius:7px;padding:7px 11px;background:#fff;cursor:pointer}
button:hover{filter:brightness(.96)}main{max-width:1180px;margin:16px auto;padding:0 12px 40px}
.guide,.card{background:#fff;border-radius:10px;padding:15px;margin-bottom:14px;box-shadow:0 1px 5px #0002}
.guide{border-left:5px solid #2563eb;line-height:1.65}.meta{color:#6b7280;font-size:13px;word-break:break-all}
.ai{border-left:5px solid #7c3aed;background:#f5f3ff;border-radius:8px;padding:10px 12px;margin:12px 0;line-height:1.55}.ai b{color:#5b21b6}
.pill{display:inline-block;background:#e5e7eb;border-radius:999px;padding:2px 8px;margin-right:6px}
.content{white-space:pre-wrap;line-height:1.7;max-height:48vh;overflow:auto;border:1px solid #d1d5db;border-radius:7px;padding:11px;background:#fafafa}
.comments{white-space:pre-wrap;line-height:1.6}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px;margin-top:10px}
.thumb{padding:5px;background:#fff;display:flex;flex-direction:column;gap:4px}.thumb img,.thumb video{width:100%;height:180px;object-fit:contain;background:#111}
.thumb span{font-size:11px;word-break:break-all}.review{border-top:2px solid #e5e7eb;margin-top:15px;padding-top:13px}
textarea{width:100%;box-sizing:border-box;min-height:90px;padding:9px;border:1px solid #9ca3af;border-radius:7px;font:inherit}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}.allow{background:#15803d;color:#fff;border-color:#15803d}.redact{background:#d97706;color:#fff;border-color:#d97706}.exclude{background:#b91c1c;color:#fff;border-color:#b91c1c}.reset{margin-left:auto}
.status{font-weight:700}.done{color:#16a34a}.warning{color:#b45309;font-weight:700}.risk-help{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;margin:10px 0}.risk-help div{padding:8px;border-radius:7px;background:#f3f4f6}
details{margin-top:12px}summary{cursor:pointer;font-weight:700}.empty{color:#6b7280}.source{font-size:12px}.kbd{font-family:ui-monospace,monospace;background:#374151;color:#fff;border-radius:4px;padding:1px 5px}
#lightbox{position:fixed;inset:0;z-index:50;background:#000d;display:none;align-items:center;justify-content:center;padding:20px}#lightbox.open{display:flex}#lightbox img{max-width:96vw;max-height:94vh;object-fit:contain}
@media(max-width:650px){.content{max-height:55vh}.grid{grid-template-columns:1fr 1fr}.thumb img,.thumb video{height:140px}}
</style></head><body>
<header><h1>__PAGE_TITLE__</h1><div class="bar">
<span id="progress"></span><select id="filter"><option value="pending">未完成</option><option value="all">全部</option><option value="done">已完成</option><option value="redact">已判 redact</option><option value="exclude">已判 exclude</option></select>
<button id="prev">← 上一条</button><span id="counter"></span><button id="next">下一条 →</button><button id="export">校验并导出 JSON</button>
</div></header><main>
<div class="guide">__GUIDE_INTRO__逐条查看正文、评论和全部可用媒体后再选择：
<div class="risk-help"><div><b>allow</b>：没有未遮罩的个人联系方式、账号、私人身份或私聊截图风险。</div><div><b>redact</b>：存在风险，但遮罩文字/头像/昵称后仍可保留记录；备注写明位置。</div><div><b>exclude</b>：风险遍布视频/大量图片，或遮罩后内容失去意义，整条排除。</div></div>
公开人物、帖子宣传对象的姓名、普通公开出镜和穿搭露脸通常不算隐私；私人聊天、朋友圈截图中的普通用户头像昵称、完整 UID/QQ/邮箱/电话通常需要 redact。快捷键：<span class="kbd">Alt+A</span> allow、<span class="kbd">Alt+R</span> redact、<span class="kbd">Alt+E</span> exclude。</div>
<div id="view"></div></main><div id="lightbox"><img alt="放大媒体"></div>
<script>
const items=__ITEMS__;
const manifest=__MANIFEST__;
const key='m1-privacy-supplemental-B-'+manifest.post_ids_sha256.slice(0,16);
let saved=JSON.parse(localStorage.getItem(key)||'{}'),filtered=[],current=0;
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const complete=x=>{const v=saved[x.post_id]||{};return !!(v.decision&&v.reviewed)};
function persist(id,patch){saved[id]={...(saved[id]||{}),...patch,updated_at:new Date().toISOString()};localStorage.setItem(key,JSON.stringify(saved));updateProgress()}
function updateProgress(){const done=items.filter(complete).length;$('progress').innerHTML=`完成：<b class="${done===items.length?'done':''}">${done} / ${items.length}</b>`}
function apply(keep){const mode=$('filter').value;filtered=items.filter(x=>mode==='all'||(mode==='pending'?!complete(x):mode==='done'?complete(x):(saved[x.post_id]||{}).decision===mode));const i=keep?filtered.findIndex(x=>x.post_id===keep):-1;current=i>=0?i:Math.min(current,Math.max(0,filtered.length-1));render()}
function mediaHtml(m){const local='../../../run_outputs/merged_20260728/'+String(m.ref||'').replaceAll('\\','/');const ext=String(m.ref||'').split('.').pop().toLowerCase();const remote=m.source_url?`<a class="source" target="_blank" rel="noreferrer" href="${esc(m.source_url)}">打开来源</a>`:'';if(m.ref&&(['mp4','webm','mov','m4v'].includes(ext)||m.type==='video')){return `<div class="thumb"><video controls preload="metadata" src="${esc(local)}"></video><span>媒体 ${m.number}: ${esc(m.ref)}</span>${remote}</div>`}if(m.ref){return `<button class="thumb zoom" data-src="${esc(local)}"><img loading="lazy" src="${esc(local)}"><span>媒体 ${m.number}: ${esc(m.ref)}</span>${remote}</button>`}return `<div class="thumb"><span>媒体 ${m.number} 无本地引用</span>${remote}</div>`}
function render(){updateProgress();$('counter').textContent=filtered.length?`${current+1} / ${filtered.length}`:'0 / 0';if(!filtered.length){$('view').innerHTML='<div class="card">当前筛选没有记录。</div>';return}const x=filtered[current],v=saved[x.post_id]||{};const comments=x.comments.length?x.comments.map((c,i)=>`<p><b>评论 ${i+1}：</b>${esc(c.text)}</p>`).join(''):'<span class="empty">无评论</span>';const media=x.media.length?`<div class="grid">${x.media.map(mediaHtml).join('')}</div>`:'<p class="empty">无媒体</p>';const ai=x.ai?`<div class="ai"><b>AI 初审（不是正式批准）</b><br>队列：${esc(x.ai.queue)}；建议：<b>${esc(x.ai.ai_recommendation)}</b>；置信度：${esc(x.ai.confidence)}<br>理由：${esc(x.ai.reason)}${x.ai.suggested_action?`<br>建议处理：${esc(x.ai.suggested_action)}`:''}</div>`:'';$('view').innerHTML=`<section class="card"><h2>${String(x.number).padStart(4,'0')}. ${esc(x.title||'(无标题)')}</h2><div class="meta"><span class="pill">${esc(x.platform)}</span>${esc(x.post_id)}；评论 ${x.comments.length}；媒体 ${x.media.length}；规则预筛：无 medium/high/critical 文本命中</div>${ai}<h3>正文</h3><div class="content">${esc(x.text)}</div><details open><summary>评论（${x.comments.length}）</summary><div class="comments">${comments}</div></details><details open><summary>媒体（${x.media.length}，有图必须逐张查看）</summary>${media}</details><div class="review"><h3>人工决定 <span class="status ${complete(x)?'done':'warning'}">${complete(x)?'已完成：'+esc(v.decision):'待复核'}</span></h3><label><b>备注：</b><textarea id="notes" placeholder="allow 可留空；redact/exclude 必须写明风险位于正文、评论或媒体几，以及处理理由">${esc(v.notes||'')}</textarea></label><div class="actions"><button class="allow" id="allow">确认 allow 并完成</button><button class="redact" id="redact">判为 redact 并完成</button><button class="exclude" id="exclude">判为 exclude 并完成</button><button class="reset" id="reset">清除此条决定</button></div></div></section>`;
$('notes').oninput=e=>persist(x.post_id,{notes:e.target.value});$('allow').onclick=()=>finish('allow');$('redact').onclick=()=>finish('redact');$('exclude').onclick=()=>finish('exclude');$('reset').onclick=()=>{delete saved[x.post_id];localStorage.setItem(key,JSON.stringify(saved));apply()};document.querySelectorAll('.zoom').forEach(b=>b.onclick=e=>{if(e.target.tagName==='A')return;$('lightbox').querySelector('img').src=b.dataset.src;$('lightbox').classList.add('open')})}
function finish(decision){const x=filtered[current],notes=$('notes').value.trim();if(decision!=='allow'&&!notes){alert('redact/exclude 必须在备注中写明风险位置和理由。');return}persist(x.post_id,{decision,notes,reviewed:true});if($('filter').value==='pending'){apply()}else{render()}}
$('filter').onchange=()=>{current=0;apply()};$('prev').onclick=()=>{if(filtered.length){current=(current-1+filtered.length)%filtered.length;render()}};$('next').onclick=()=>{if(filtered.length){current=(current+1)%filtered.length;render()}};
$('lightbox').onclick=()=>{$('lightbox').classList.remove('open');$('lightbox').querySelector('img').src=''};
document.addEventListener('keydown',e=>{if(!e.altKey)return;if(e.key.toLowerCase()==='a')finish('allow');if(e.key.toLowerCase()==='r')finish('redact');if(e.key.toLowerCase()==='e')finish('exclude')});
$('export').onclick=()=>{const missing=items.filter(x=>!complete(x));if(missing.length){alert(`还有 ${missing.length} 条未完成；当前第一个：${missing[0].number} ${missing[0].post_id}`);return}const rows=items.map(x=>({number:x.number,post_id:x.post_id,platform:x.platform,...saved[x.post_id]}));const counts={allow:0,redact:0,exclude:0};rows.forEach(x=>counts[x.decision]++);const payload={status:manifest.export_status,reviewer:'B',exported_at:new Date().toISOString(),manifest_sha256:manifest.post_ids_sha256,dataset_sha256:manifest.dataset_sha256,sample_count:items.length,decision_counts:counts,items:rows};const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=manifest.export_name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
apply();
</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate B supplemental privacy review HTML")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--triage")
    parser.add_argument("--queue-prefix", action="append", default=[])
    parser.add_argument("--page-title", default="M1 B 补充隐私人工复核（规则低风险待审队列）")
    parser.add_argument("--export-name", default="privacy_supplemental_review_B.json")
    parser.add_argument("--export-status", default="completed_B_supplemental_privacy_review")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    manifest_path = Path(args.manifest)
    output_path = Path(args.output)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite: {output_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    post_ids = [str(value) for value in manifest.get("post_ids", [])]
    if not post_ids or len(post_ids) != len(set(post_ids)):
        raise ValueError("manifest post_ids must be non-empty and unique")

    triage_by_id = {}
    if args.triage:
        triage = json.loads(Path(args.triage).read_text(encoding="utf-8-sig"))
        triage_by_id = {
            str(item.get("post_id", "")): item
            for item in triage.get("items", [])
            if isinstance(item, dict)
        }
        if args.queue_prefix:
            post_ids = [
                post_id
                for post_id in post_ids
                if any(
                    str(triage_by_id.get(post_id, {}).get("queue", "")).startswith(prefix)
                    for prefix in args.queue_prefix
                )
            ]
            if not post_ids:
                raise ValueError("queue-prefix filter selected no records")

    records, _ = load_objects(dataset_path)
    by_id = {str(record.get("post_id", "")): record for record in records}
    missing = [post_id for post_id in post_ids if post_id not in by_id]
    if missing:
        raise ValueError("manifest post_ids missing from dataset: " + ", ".join(missing[:10]))

    items = []
    for number, post_id in enumerate(post_ids, start=1):
        record = by_id[post_id]
        items.append(
            {
                "number": number,
                "post_id": post_id,
                "platform": record.get("platform", ""),
                "title": record.get("title", ""),
                "text": record.get("text", ""),
                "comments": [
                    {"text": item.get("text", "")}
                    for item in (record.get("comments") or [])
                    if isinstance(item, dict)
                ],
                "media": [
                    {
                        "number": index,
                        "type": item.get("type", ""),
                        "ref": item.get("ref", ""),
                        "source_url": item.get("source_url", ""),
                    }
                    for index, item in enumerate(record.get("media") or [], start=1)
                    if isinstance(item, dict)
                ],
                "ai": triage_by_id.get(post_id),
            }
        )

    safe_items = json.dumps(items, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    safe_manifest = json.dumps(
        {
            "post_ids_sha256": manifest.get("post_ids_sha256", ""),
            "dataset_sha256": manifest.get("dataset_sha256", ""),
            "selected_count": len(post_ids),
            "export_name": args.export_name,
            "export_status": args.export_status,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    guide_intro = (
        f"<b>当前页面共 {len(post_ids)} 条。</b>AI 初审只负责分流，不能替代 B 的正式批准。"
        if args.triage
        else f"<b>这 {len(post_ids)} 条只是规则低风险，仍必须由 B 人工确认。</b>"
    )
    html = (
        HTML_TEMPLATE.replace("__ITEMS__", safe_items)
        .replace("__MANIFEST__", safe_manifest)
        .replace("__PAGE_TITLE__", args.page_title)
        .replace("__GUIDE_INTRO__", guide_intro)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Review items: {len(items)}")
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
