#!/usr/bin/env python3
"""
Flet GUI —— 

   - / 
   - <图片N> 
   - YOLO+OCR 
   -  +  + Markdown 
   -  + 

:

  python scripts/data/annotation/flet_annotator.py \
    --input data/interim/candidates_v1_dedup.jsonl \
    --output-dir data/annotations \
    --media-base data

: pip install flet ultralytics easyocr
"""
from __future__ import annotations

import json, os, re, sys, threading, time, base64
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CST = timezone(timedelta(hours=8))
import flet as ft

def _border_all(width=1, color=None):
    """Flet 0.86.x compatible border helper (ft.border.all removed)."""
    if color is None: color = ft.Colors.GREY_300
    side = ft.BorderSide(width, color)
    return ft.Border(top=side, bottom=side, left=side, right=side)

VALID_LABELS = ["mingguang", "anguang", "feiguang", "out_of_scope"]
LABEL_NAMES = {"mingguang": "明广", "anguang": "暗广", "feiguang": "非广", "out_of_scope": "范围外"}
EVIDENCE_CODES = {
    "D": "明示商业关系（广告/赞助/合作标识）",
    "C": "明确商业对象（单一品牌/商品/店铺/服务）",
    "P": "劝服/促销话术（夸赞、限时、价格刺激）",
    "A": "转化动作（下单、扫码、优惠码、链接）",
    "V": "视觉商业证据（产品特写、Logo、价格表）",
    "B": "行为偏移（与博主既往人设/主题不符）",
    "M": "评论异常（置顶导流、格式化赞美）",
}

def load_posts(input_path: Path) -> List[Dict]:
    records = []
    with input_path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                try: records.append(json.loads(line))
                except json.JSONDecodeError: pass
    return records

def load_existing(output_dir: Path, aid: str) -> Tuple[Optional[Path], Set[str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = sorted(
        list(output_dir.glob(f"{aid}_*.json")) + list(output_dir.glob(f"{aid}_*.jsonl")),
        key=os.path.getmtime, reverse=True)
    if not candidates: return None, set()
    latest = candidates[0]
    completed = set()
    # Use raw_decode to handle pretty-printed multi-line JSON
    raw = latest.read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    idx = 0
    n = len(raw)
    while idx < n:
        while idx < n and raw[idx] in " \t\n\r": idx += 1
        if idx >= n: break
        try:
            obj, end = decoder.raw_decode(raw, idx)
            pid = obj.get("post_id", "")
            if pid: completed.add(pid)
            idx = end
        except json.JSONDecodeError:
            next_brace = raw.find("{", idx + 1)
            if next_brace == -1: break
            idx = next_brace
    return latest, completed

def save_annotation(output_dir: Path, aid: str, record: Dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
    fpath = output_dir / f"{aid}_{ts}.json"
    with fpath.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return fpath

def run_image_analysis_bg(post: Dict, media_base: Path, callback):
    try:
        from scripts.data.annotation.image_prefilter import extract_content_image_indices
        text = post.get("text", "")
        indices = extract_content_image_indices(text)
        media = post.get("media", [])
        results = {}
        for i in indices:
            if i >= len(media): continue
            ref = media[i].get("ref", "")
            img_path = media_base / ref
            if not img_path.exists():
                results[i] = {"error": "file missing"}
                continue
            try:
                from scripts.data.annotation.auto_image_annotate import load_yolo, load_ocr, analyze_image
                yolo = load_yolo()
                ocr = load_ocr()
                analysis = analyze_image(yolo, ocr, img_path, i + 1, ref, "")
                results[i] = {
                    "detected_elements": analysis.get("detected_elements", {}),
                    "visual_evidence_codes": analysis.get("visual_evidence_codes", []),
                    "description": analysis.get("description", ""),
                    "ocr_text": analysis.get("ocr_text"),
                }
            except Exception as e:
                results[i] = {"error": str(e)[:100]}
        if callback: callback(results)
    except Exception as e:
        if callback: callback({"__error__": str(e)[:200]})

class AnnotatorApp:
    def __init__(self, posts, output_dir, media_base, aid="D", completed=None):
        self.posts = posts
        self.output_dir = output_dir
        self.media_base = media_base
        self.aid = aid
        self.completed = completed or set()
        self.idx = 0
        self.image_analyses = {}
        self.analyzing = False
        self.page = None
        for i, p in enumerate(posts):
            if p.get("post_id") not in self.completed:
                self.idx = i; break

    @property
    def post(self): return self.posts[self.idx] if self.posts else {}
    @property
    def pid(self): return self.post.get("post_id", "?")

    # ---- UI Build ----
    def build(self, page: ft.Page):
        self.page = page
        page.title = "隐性广告标注工作台"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.window_width = 1400
        page.window_height = 900
        page.padding = 10

        # Top bar
        self.progress_text = ft.Text("", size=14)
        self.analyze_btn = ft.Button("分析图片", icon=ft.Icons.IMAGE_SEARCH, on_click=self.run_analysis)
        self.save_btn = ft.Button("保存标注", icon=ft.Icons.SAVE, on_click=self.save_current)
        top_bar = ft.Row([
            ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Previous (Ctrl+Left)", on_click=lambda e: self.go(-1)),
            ft.IconButton(ft.Icons.ARROW_FORWARD, tooltip="Next (Ctrl+Right)", on_click=lambda e: self.go(1)),
            self.progress_text,
            ft.Container(expand=True),
            self.analyze_btn, self.save_btn,
        ])

        # Left: text
        self.title_text = ft.Text("", size=20, weight=ft.FontWeight.BOLD)
        self.meta_text = ft.Text("", size=12, color=ft.Colors.GREY_600)
        self.body_md = ft.Markdown("", selectable=True, extension_set=ft.MarkdownExtensionSet.NONE)
        left_col = ft.Column([
            self.title_text, self.meta_text, ft.Divider(), self.body_md,
        ], scroll=ft.ScrollMode.AUTO, expand=True)

        # Right: images
        self.gallery = ft.GridView(expand=True, max_extent=250, child_aspect_ratio=1.0, spacing=8, run_spacing=8)
        self.img_info = ft.Text("", size=12, color=ft.Colors.GREY_600)
        self.analysis_text = ft.Text("", size=12)
        right_col = ft.Column([
            ft.Text("图片 (仅内容图)", size=16, weight=ft.FontWeight.BOLD),
            self.img_info, self.gallery,
            ft.Divider(),
            ft.Text("图像分析结果", size=14, weight=ft.FontWeight.BOLD),
            self.analysis_text,
        ], scroll=ft.ScrollMode.AUTO, expand=True)

        # Bottom: annotation panel
        self.label_btns = ft.Row([
            ft.Button(n, on_click=lambda e, l=k: self.select_label(l))
            for k, n in LABEL_NAMES.items()
        ], spacing=8)
        self.selected_label = ft.Text("未选择", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE)

        self.evidence_cbs = {}
        ev_row = ft.Row([ft.Text("证据:", size=14)], spacing=4)
        for code, desc in EVIDENCE_CODES.items():
            cb = ft.Checkbox(label=code, tooltip=desc, value=False)
            self.evidence_cbs[code] = cb
            ev_row.controls.append(cb)

        self.conf_slider = ft.Slider(min=0, max=1, value=0.8, divisions=10, label="{value}", width=200)
        self.conf_text = ft.Text("0.8", size=14)
        self.evidence_input = ft.TextField(label="证据描述（一行一条）", multiline=True, min_lines=2, max_lines=4, expand=True)
        self.notes_input = ft.TextField(label="备注 (Markdown)", multiline=True, min_lines=2, max_lines=6, expand=True)

        annotation_panel = ft.Column([
            ft.Divider(),
            ft.Row([ft.Text("标签:", size=14), self.selected_label, ft.Container(expand=True)]),
            self.label_btns, ev_row,
            ft.Row([ft.Text("确信度:", size=14), self.conf_slider, self.conf_text, ft.Container(expand=True)]),
            self.evidence_input, self.notes_input,
        ])

        main_row = ft.Row([
            ft.Container(left_col, expand=2, padding=10),
            ft.VerticalDivider(),
            ft.Container(right_col, expand=3, padding=10),
        ], expand=True)

        page.add(top_bar, ft.Divider(), main_row, annotation_panel)
        page.on_keyboard_event = self._on_keyboard
        self._refresh()

    # ---- Refresh ----
    def _refresh(self):
        if not self.posts: return
        p = self.post
        pid = p.get("post_id", "?")
        self.progress_text.value = f"  [{self.idx + 1}/{len(self.posts)}]  {pid[:20]}..."
        if pid in self.completed: self.progress_text.value += "  DONE"
        self.title_text.value = p.get("title") or "(no title)"
        plat = p.get("platform", "?")
        blogger = (p.get("blogger_id") or "?")[:20]
        pub = p.get("published_at") or "unknown"
        mn = len(p.get("media", []))
        self.meta_text.value = f"Platform: {plat} | Blogger: {blogger}... | Published: {pub} | Images: {mn}"
        text = p.get("text", "")
        if len(text) > 5000: text = text[:5000] + "\n\n*...(truncated)*"
        text = re.sub(r'<图片(\d+)>', r' [Pic\1](marker:\1) ', text)
        self.body_md.value = text
        self._refresh_images()
        self.selected_label.value = "未选择"
        self.selected_label.color = ft.Colors.ORANGE
        for cb in self.evidence_cbs.values(): cb.value = False
        self.conf_slider.value = 0.8; self.conf_text.value = "0.8"
        self.evidence_input.value = ""; self.notes_input.value = ""
        self.image_analyses = {}
        self.analysis_text.value = "点击 '分析图片' 开始"
        self.page.update()

    def _refresh_images(self):
        self.gallery.controls.clear()
        text = self.post.get("text", "")
        ci = set()
        if text:
            for m in re.finditer(r'<图片(\d+)>', text): ci.add(int(m.group(1)) - 1)
        media = self.post.get("media", [])
        shown = 0
        errors = []
        for i, m in enumerate(media):
            if ci and i not in ci: continue
            ref = m.get("ref", ""); ip = self.media_base / ref; num = i + 1
            if ip.exists():
                try:
                    ext = ip.suffix.lower().lstrip(".")
                    mime_map = {"jpg":"jpeg","jpeg":"jpeg","png":"png","gif":"gif","webp":"webp","bmp":"bmp"}
                    mime = mime_map.get(ext, "jpeg")
                    b64 = base64.b64encode(ip.read_bytes()).decode()
                    img = ft.Image(src=f"data:image/{mime};base64,{b64}", tooltip=f"Pic{num}")
                    img.fit = ft.BoxFit.CONTAIN
                    img.border_radius = 8
                except Exception as exc:
                    errors.append(f"Pic{num}: {exc}")
                    img = ft.Container(
                        ft.Text(f"Pic{num}\n读取失败\n{str(exc)[:50]}", size=11, text_align=ft.TextAlign.CENTER),
                        width=200, height=200,
                        border=_border_all(1, ft.Colors.RED_300), border_radius=8,
                        alignment=ft.alignment.Alignment(0, 0))
            else:
                errors.append(f"Pic{num}: 文件缺失 ({ref[:40]})")
                img = ft.Container(
                    ft.Text(f"Pic{num}\n文件缺失", size=12, text_align=ft.TextAlign.CENTER),
                    width=200, height=200,
                    border=_border_all(1, ft.Colors.GREY_300), border_radius=8,
                    alignment=ft.alignment.Alignment(0, 0))
            analysis = self.image_analyses.get(i, {})
            badge = f" [{','.join(analysis.get('visual_evidence_codes',[]))}]" if analysis.get("visual_evidence_codes") else ""
            cap = ft.Text(f"Pic{num}{badge}", size=11)
            self.gallery.controls.append(ft.Container(ft.Column([img, cap], spacing=4, alignment=ft.MainAxisAlignment.CENTER)))
            shown += 1
        status = f"Showing {shown}/{len(media)} images"
        if errors:
            status += f"  |  Errors: {'; '.join(errors[:3])}"
        self.img_info.value = status

    # ---- Actions ----
    def run_analysis(self, e=None):
        if self.analyzing: return
        self.analyzing = True; self.analyze_btn.disabled = True
        self.analysis_text.value = "分析中..."; self.page.update()
        def cb(results):
            self.analyzing = False; self.analyze_btn.disabled = False
            if "__error__" in results:
                self.analysis_text.value = f"Error: {results['__error__']}"
            else:
                self.image_analyses = results
                lines = []
                for idx, a in sorted(results.items()):
                    if "error" in a: lines.append(f"Pic{idx+1}: err {a['error']}")
                    else:
                        el = a.get("detected_elements", {}); codes = a.get("visual_evidence_codes", [])
                        active = [k.replace("has_","") for k,v in el.items() if v]
                        lines.append(f"Pic{idx+1}: {'V' if codes else '-'} {', '.join(active) if active else 'no commercial features'}")
                        if a.get("ocr_text"): lines.append(f"    OCR: {a['ocr_text'][:80]}")
                self.analysis_text.value = "\n".join(lines) if lines else "No content images"
            self._refresh_images(); self.page.update()
        threading.Thread(target=run_image_analysis_bg, args=(self.post, self.media_base, cb), daemon=True).start()

    def select_label(self, label: str):
        self.selected_label.value = LABEL_NAMES.get(label, label)
        color_map = {"mingguang": ft.Colors.RED, "anguang": ft.Colors.ORANGE, "feiguang": ft.Colors.GREEN, "out_of_scope": ft.Colors.GREY}
        self.selected_label.color = color_map.get(label, ft.Colors.ORANGE)
        self.page.update()

    def save_current(self, e=None):
        label = self.selected_label.value
        for k, v in LABEL_NAMES.items():
            if label == v: label = k; break
        if label not in VALID_LABELS:
            self._snack("请先选择标签", ft.Colors.RED); return
        record = {
            "post_id": self.pid, "annotator_id": self.aid, "guide_version": "1.1",
            "label": label, "confidence": round(self.conf_slider.value, 2),
            "evidence_codes": [c for c, cb in self.evidence_cbs.items() if cb.value],
            "evidence": [e.strip() for e in self.evidence_input.value.split("\n") if e.strip()] if self.evidence_input.value else [],
            "uncertain_reason": None,
            "annotated_at": datetime.now(CST).isoformat(),
            "markdown_notes": self.notes_input.value,
            "image_analyses": [
                {"media_ref": self.post.get("media",[])[i].get("ref",""), "image_index": i+1, "analysis_method": "yolo_ocr_auto", **a}
                for i, a in self.image_analyses.items() if "error" not in a
            ] if self.image_analyses else [],
        }
        save_annotation(self.output_dir, self.aid, record)
        self.completed.add(self.pid)
        self._snack(f"Saved: {self.pid[:24]}...", ft.Colors.GREEN)
        self.go(1)

    def _snack(self, msg, color=ft.Colors.GREEN):
        self.page.snack_bar = ft.SnackBar(ft.Text(msg, color=color), duration=2000)
        self.page.snack_bar.open = True; self.page.update()

    # ---- Navigation ----
    def go(self, delta):
        new_idx = self.idx + delta
        if 0 <= new_idx < len(self.posts):
            self.idx = new_idx; self._refresh()

    def _on_keyboard(self, e: ft.KeyboardEvent):
        if e.ctrl and e.key == "Arrow Left": self.go(-1)
        elif e.ctrl and e.key == "Arrow Right": self.go(1)
        elif e.ctrl and e.key == "S": self.save_current()
        elif e.ctrl and e.key == "A": self.run_analysis()
        elif e.key in ("1","2","3","4"):
            idx = int(e.key) - 1
            if idx < len(VALID_LABELS): self.select_label(VALID_LABELS[idx])

def main():
    import argparse
    p = argparse.ArgumentParser(description="Flet Annotation Workbench")
    p.add_argument("--input", default="data/interim/candidates_v1_dedup.jsonl")
    p.add_argument("--output-dir", default="data/annotations")
    p.add_argument("--media-base", default="data")
    p.add_argument("--annotator-id", default="D")
    args = p.parse_args()

    ip = PROJECT_ROOT / args.input; od = PROJECT_ROOT / args.output_dir; mb = PROJECT_ROOT / args.media_base
    print(f"Loading: {ip}")
    posts = load_posts(ip)
    print(f"  {len(posts)} posts loaded")
    _, completed = load_existing(od, args.annotator_id)
    print(f"  {len(completed)} already completed")

    app = AnnotatorApp(posts, od, mb, args.annotator_id, completed)
    print(f"\nStarting workbench (desktop)...")
    print(f"  Shortcuts: Ctrl+Arrows=Navigate | Ctrl+S=Save | Ctrl+A=Analyze | 1-4=Quick label")
    ft.app(target=app.build)  # legacy entry, ok for 0.86.x desktop

if __name__ == "__main__":
    main()
