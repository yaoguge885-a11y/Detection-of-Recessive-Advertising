"""FastAPI 封装：POST /analyze 传入一条帖子 → 返回结构化审查结果。

本地启动：
    uvicorn app:app --reload
然后浏览器打开 http://127.0.0.1:8000/docs 直接在网页上试。
注意：/analyze 用的是 LLM 图（graph.py），需先配好 .env。
（想零成本先跑通，把下面 import 改成 impad.hello_graph 即可。）
"""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from impad.graph import graph

app = FastAPI(title="隐性广告识别 · 起步骨架")


@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>隐性广告识别 API</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 40px 20px; background: #f5f5f5; }
            .card { background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 15px rgba(0,0,0,0.08); }
            h1 { color: #1a1a2e; margin-bottom: 20px; }
            p { color: #666; line-height: 1.6; margin-bottom: 20px; }
            .links { display: flex; gap: 15px; flex-wrap: wrap; }
            a { display: inline-block; padding: 10px 20px; background: #3b82f6; color: white; text-decoration: none; border-radius: 6px; transition: background 0.2s; }
            a:hover { background: #2563eb; }
            .api-link { background: #10b981; }
            .api-link:hover { background: #059669; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>隐性广告识别 API</h1>
            <p>融合多模态行为特征与文本推断的隐性广告识别服务。</p>
            <p>提供 <code>POST /analyze</code> 接口，传入帖子内容即可获得结构化审查结果。</p>
            <div class="links">
                <a href="/docs">📖 API 文档</a>
                <a href="/redoc" class="api-link">📋 ReDoc 文档</a>
                <a href="/health">❤️ 健康检查</a>
            </div>
        </div>
    </body>
    </html>
    """


class PostIn(BaseModel):
    text: str
    blogger: str = "未知"
    image_url: str | None = None
    image_path: str | None = None  # 本地图片路径，供视觉专家做 OCR/物体/焦点分析
    comments: list[str] = []
    history: list[str] = []  # 该博主的历史帖正文，供行为专家判断人设偏移


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(post: PostIn):
    result = graph.invoke({"post": post.model_dump()})
    return {
        "verdict": result.get("verdict"),
        "confidence": result.get("confidence"),
        "keyword_weights": result.get("keyword_weights"),
        "vision_findings": result.get("vision_findings"),
        "agent_votes": result.get("agent_votes"),
        "evidence": result.get("evidence"),
        "report": result.get("report"),
    }
