import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { z } from "zod";
import { api } from "./api";
import {
  historyItemSchema,
  type AnalysisReport,
  type AnalyzeRequest,
  type Capabilities,
  type HistoryItem,
} from "./contracts";

const historyKey = "impad.recent-runs.v1";
const historyLimit = 20;
const coverageNames: Record<string, string> = {
  text: "文本",
  image: "图片",
  comment: "评论",
  disclosure: "披露",
  history: "创作者历史",
  metadata: "元数据",
};
const coverageStatuses: Record<string, string> = {
  covered: "已覆盖",
  partial: "部分覆盖",
  missing: "缺失",
  unsupported: "不支持",
  not_applicable: "不适用",
};
const statusNames: Record<string, string> = {
  pending: "等待中",
  running: "运行中",
  completed: "已完成",
  degraded: "已降级",
  failed: "失败",
};

function readHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(historyKey);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    const result = z.array(historyItemSchema).safeParse(parsed);
    if (!result.success) {
      notifyToast("本地历史格式不正确，已忽略损坏的摘要记录。");
      return [];
    }
    return result.data.slice(0, historyLimit);
  } catch (error) {
    notifyToast(`无法读取本地历史：${errorText(error)}`);
    return [];
  }
}

function saveHistory(report: AnalysisReport): void {
  const item: HistoryItem = {
    run_id: report.run_metadata.run_id,
    post_id: report.verdict_report.post_id,
    label: report.verdict_report.label,
    confidence: report.verdict_report.confidence,
    created_at: report.run_metadata.finished_at ?? report.run_metadata.started_at ?? new Date().toISOString(),
  };
  const history = [
    item,
    ...readHistory().filter((entry) => entry.run_id !== item.run_id),
  ].slice(0, historyLimit);
  try {
    localStorage.setItem(historyKey, JSON.stringify(history));
  } catch (error) {
    notifyToast(`报告已保存，但无法更新本地历史：${errorText(error)}`);
  }
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "发生未知错误。";
}

function safeHttpUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

function notifyToast(message: string): void {
  window.dispatchEvent(new CustomEvent("app:toast", { detail: message }));
}

function AppShell() {
  const location = useLocation();
  const runId = location.pathname.match(/^\/runs\/([^/]+)/)?.[1];
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const [toast, setToast] = React.useState("");

  React.useEffect(() => {
    const show = (event: Event) => {
      const custom = event as CustomEvent<string>;
      setToast(custom.detail);
      window.setTimeout(() => setToast(""), 6000);
    };
    window.addEventListener("app:toast", show);
    return () => window.removeEventListener("app:toast", show);
  }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" to="/analyze" aria-label="隐性广告分析首页">
          <span className="brand-mark">◈</span>
          <span>隐性广告分析<small>Evidence Workspace</small></span>
        </Link>
        <div className="topbar-right">
          <span className="local-badge"><i />本机单用户</span>
          <span className={`api-health ${health.isError ? "is-error" : ""}`}>
            <i />{health.isPending ? "连接检查中" : health.isError ? "API 不可用" : "API 正常"}
          </span>
          {runId && <Link className="run-pill" to={`/runs/${encodeURIComponent(runId)}`}>当前运行 · {runId}</Link>}
        </div>
      </header>
      <div className="app-layout">
        <aside className="sidebar">
          <div className="nav-label">工作空间</div>
          <nav aria-label="主导航">
            <NavLink to="/analyze"><span>◫</span>单条分析</NavLink>
            <NavLink to="/batch"><span>▤</span>批量分析</NavLink>
            <NavLink to="/import"><span>↗</span>URL 导入</NavLink>
            <NavLink to="/history"><span>◷</span>最近运行</NavLink>
            <NavLink to="/settings"><span>⚙</span>能力与设置</NavLink>
          </nav>
          <div className="side-note">
            <strong>本机研究原型</strong>
            <p>报告是系统辅助分析，不是人工标注或法律结论。不要将服务暴露到公网。</p>
            <Link to="/settings">查看安全边界 →</Link>
          </div>
          <a className="workbench-link" href="/workbench">开发者研究工作台 ↗</a>
        </aside>
        <main className="main-content">
          {toast && <div className="toast" role="status">{toast}</div>}
          <Routes>
            <Route path="/" element={<Navigate to="/analyze" replace />} />
            <Route path="/analyze" element={<AnalyzePage />} />
            <Route path="/batch" element={<BatchPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/runs/:runId" element={<RunPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
          <footer>研究辅助工具 · 结论与证据以人工复核为准</footer>
        </main>
      </div>
    </div>
  );
}

function PageHeading({ eyebrow, title, description }: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="page-heading">
      <div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>
      <span className="version-badge">本机分析 · 研究原型</span>
    </div>
  );
}

function Alert({ error, stale = false }: { error: unknown; stale?: boolean }) {
  if (!error) return null;
  return (
    <div className="alert error-alert" role="alert">
      <strong>请求未成功</strong>
      <span>{errorText(error)}{stale ? "；当前仍显示上次成功的报告。" : ""}</span>
    </div>
  );
}

function AsyncState({ loading, error, children }: {
  loading: boolean;
  error?: unknown;
  children?: React.ReactNode;
}) {
  if (loading) return <div className="async-state"><span className="spinner" />正在连接本机服务…</div>;
  if (error) return <Alert error={error} />;
  return <>{children}</>;
}

function SectionTitle({ number, title, detail }: {
  number?: string;
  title: string;
  detail?: string;
}) {
  return (
    <div className="section-title">
      {number && <span className="step">{number}</span>}
      <h2>{title}</h2>
      {detail && <span className="section-detail">{detail}</span>}
    </div>
  );
}

function parseJsonArray(value: string, label: string): unknown[] {
  if (!value.trim()) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(`${label}必须是合法 JSON 数组。`);
  }
  if (!Array.isArray(parsed)) throw new Error(`${label}必须是 JSON 数组。`);
  return parsed;
}

function AnalyzePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: api.analyze,
    onSuccess: (report) => {
      saveHistory(report);
      queryClient.setQueryData(["run", report.run_metadata.run_id], report);
      navigate(`/runs/${encodeURIComponent(report.run_metadata.run_id)}`);
    },
  });
  const [formError, setFormError] = React.useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const form = new FormData(event.currentTarget);
    const text = String(form.get("text") ?? "").trim();
    if (!text) {
      setFormError("请先输入帖子正文。");
      return;
    }
    try {
      const comments = parseJsonArray(String(form.get("comments") ?? ""), "评论");
      const history = parseJsonArray(String(form.get("history") ?? ""), "创作者历史");
      const creator = String(form.get("creator_id") ?? "").trim();
      const publishedInput = String(form.get("published_at") ?? "");
      const request: AnalyzeRequest = {
        text,
        platform: String(form.get("platform") ?? "other"),
        capture_complete: form.get("capture_complete") === "on",
        runtime_mode: "local",
        ...(creator ? { creator_id: creator, blogger: creator } : {}),
        ...(publishedInput ? { published_at: new Date(publishedInput).toISOString() } : {}),
        ...(comments.length ? { comments: comments as AnalyzeRequest["comments"] } : {}),
        ...(history.length ? { history: history as AnalyzeRequest["history"] } : {}),
      };
      mutation.mutate(request);
    } catch (error) {
      setFormError(errorText(error));
    }
  }

  return (
    <>
      <PageHeading eyebrow="ANALYSIS WORKSPACE" title="单条内容分析"
        description="提交已采集的帖子材料，查看系统结论、证据和采集边界。" />
      <div className="workspace-grid analyze-grid">
        <section className="card">
          <SectionTitle number="01" title="输入内容" detail="不保存草稿" />
          <p className="card-description">仅提交你有权处理的材料。图片路径和远程媒体加载暂未开放。</p>
          <form className="form-stack" onSubmit={submit}>
            <label htmlFor="post-text">帖子正文 <span className="required">必填</span></label>
            <textarea id="post-text" name="text" required maxLength={50_000}
              placeholder="粘贴已采集的帖子正文…" />
            <div className="two-fields">
              <div><label htmlFor="platform">平台</label>
                <select id="platform" name="platform">
                  <option value="other">其他 / 未指定</option><option value="bilibili">哔哩哔哩</option>
                  <option value="wechat">微信公众号</option><option value="xiaohongshu">小红书</option>
                </select>
              </div>
              <div><label htmlFor="creator-id">创作者 ID <span className="optional">选填</span></label>
                <input id="creator-id" name="creator_id" maxLength={200} placeholder="creator_id" />
              </div>
            </div>
            <label htmlFor="published-at">发布时间 <span className="optional">选填</span></label>
            <input id="published-at" name="published_at" type="datetime-local" />
            <details className="optional-inputs">
              <summary>补充评论和创作者历史</summary>
              <label htmlFor="comments">评论 JSON 数组 <span className="optional">选填</span></label>
              <textarea className="json-input" id="comments" name="comments" placeholder={'["评论文字", {"text":"评论内容"}]'} />
              <label htmlFor="history">历史帖子 JSON 数组 <span className="optional">选填</span></label>
              <textarea className="json-input" id="history" name="history"
                placeholder={'[{"post_id":"history-1","creator_id":"同一创作者ID","text":"历史正文","published_at":"2026-01-01T00:00:00Z"}]'} />
              <p className="field-hint">历史记录须属于同一创作者，且早于当前帖子；避免输入未核验历史材料。</p>
            </details>
            <label className="checkbox-row">
              <input type="checkbox" name="capture_complete" />
              我确认当前采集范围完整
            </label>
            <p className="field-hint">不确定时保持未勾选；未采集或不可读的材料不会被当成“未发现”。</p>
            {formError && <Alert error={new Error(formError)} />}
            <Alert error={mutation.error} />
            <button className="primary-button" disabled={mutation.isPending}>
              {mutation.isPending ? "正在分析…" : "提交并分析"} <span>→</span>
            </button>
          </form>
        </section>
        <section className="card info-card">
          <SectionTitle number="02" title="分析边界" detail="本机同步运行" />
          <div className="empty-result">
            <div className="empty-icon">◎</div><h3>结果将以只读报告呈现</h3>
            <p>后端生成结论；页面不重算标签或置信度。<br />每次成功分析均生成可恢复的运行 ID。</p>
          </div>
          <div className="notice-box">
            <strong>请注意</strong>
            <ul><li>页面不会自动抓取或提交远程媒体。</li><li>浏览器不会保存帖子正文或评论草稿。</li><li>分析输出不构成正式标注或法律意见。</li></ul>
          </div>
        </section>
      </div>
    </>
  );
}

function parseCsv(text: string): Record<string, unknown>[] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted && char === '"' && text[index + 1] === '"') {
      cell += '"';
      index += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && text[index + 1] === "\n") index += 1;
      row.push(cell);
      if (row.some((value) => value.trim())) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }
  if (quoted) throw new Error("CSV 包含未闭合的引号。");
  row.push(cell);
  if (row.some((value) => value.trim())) rows.push(row);
  if (rows.length < 2) throw new Error("CSV 至少需要表头和一条数据。");
  const headers = rows[0].map((header) => header.trim());
  if (!headers.includes("text")) throw new Error("CSV 必须包含 text 列。");
  return rows.slice(1).map((cells) => Object.fromEntries(
    headers.map((header, index) => [header, cells[index] ?? ""]),
  ));
}

function parseBatch(text: string, maximum: number): unknown[] {
  const trimmed = text.trim();
  if (!trimmed) throw new Error("请粘贴 JSON 数组或 CSV 内容。");
  let items: unknown[];
  if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
    let payload: unknown;
    try {
      payload = JSON.parse(trimmed);
    } catch {
      throw new Error("批量输入不是合法 JSON。");
    }
    items = Array.isArray(payload)
      ? payload
      : payload && typeof payload === "object" && "items" in payload && Array.isArray(payload.items)
        ? payload.items
        : [];
  } else {
    items = parseCsv(trimmed);
  }
  if (!items.length) throw new Error("批量输入中没有记录。");
  if (items.length > maximum) throw new Error(`本机上限为 ${maximum} 条；当前输入 ${items.length} 条。`);
  return items;
}

function BatchPage() {
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  const maximum = capabilities.data?.batch_analysis.max_items ?? 50;
  const [input, setInput] = React.useState("");
  const [parseError, setParseError] = React.useState("");
  const mutation = useMutation({ mutationFn: api.batch });
  const queryClient = useQueryClient();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setParseError("");
    try {
      const items = parseBatch(input, maximum);
      mutation.mutate(items, {
        onSuccess: (result) => {
          result.items.forEach((item) => {
            if (item.ok && item.result) {
              saveHistory(item.result);
              queryClient.setQueryData(["run", item.result.run_metadata.run_id], item.result);
            }
          });
        },
      });
    } catch (error) {
      setParseError(errorText(error));
    }
  }

  return (
    <>
      <PageHeading eyebrow="BATCH ANALYSIS" title="批量分析"
        description={`粘贴 JSON 数组或 CSV。最多 ${maximum} 条；每条成功或失败都会单独显示。`} />
      <section className="card">
        <SectionTitle number="01" title="批量输入" detail="同步 · 逐条结果" />
        <form className="form-stack" onSubmit={submit}>
          <label htmlFor="batch-input">JSON / CSV <span className="required">必填</span></label>
          <textarea className="batch-editor" id="batch-input" value={input} onChange={(event) => setInput(event.target.value)}
            placeholder={'JSON 示例：\n[{"text":"帖子正文","platform":"other"}]\n\nCSV 示例：\ntext,platform\n"帖子正文",other'} />
          <p className="field-hint">CSV 至少需要 text 列。输入会按原顺序提交，不会静默跳过无效项。</p>
          {parseError && <Alert error={new Error(parseError)} />}
          <Alert error={mutation.error} />
          <button className="primary-button" disabled={mutation.isPending}>
            {mutation.isPending ? "正在分析批次…" : `提交批次（上限 ${maximum}）`} <span>→</span>
          </button>
        </form>
      </section>
      {mutation.data && (
        <section className="card batch-results">
          <SectionTitle number="02" title="逐条结果"
            detail={`${mutation.data.succeeded} 成功 · ${mutation.data.failed} 失败 · 共 ${mutation.data.total} 条`} />
          <div className="batch-list">
            {mutation.data.items.map((item) => (
              <article className={`batch-item ${item.ok ? "" : "batch-failed"}`} key={item.index}>
                <div><strong>第 {item.index + 1} 条</strong>
                  <span>{item.ok ? item.result?.verdict_report.label : item.error?.message ?? "分析失败"}</span>
                </div>
                {item.ok && item.result
                  ? <Link to={`/runs/${encodeURIComponent(item.result.run_metadata.run_id)}`}>
                    查看报告 · {item.result.run_metadata.run_id}
                  </Link>
                  : <span className="error-code">{item.error?.code ?? "analysis_failed"}</span>}
              </article>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

function ImportPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  const platforms = capabilities.data?.url_import.platforms ?? [];
  const urlImportEnabled = Boolean(capabilities.data?.url_import.enabled && platforms.length);
  const [url, setUrl] = React.useState("");
  const [preview, setPreview] = React.useState<Awaited<ReturnType<typeof api.previewUrl>> | null>(null);
  const [previewError, setPreviewError] = React.useState<unknown>(null);
  const previewMutation = useMutation({
    mutationFn: api.previewUrl,
    onSuccess: (value) => { setPreview(value); setPreviewError(null); },
    onError: (error) => { setPreviewError(error); setPreview(null); },
  });
  const confirmMutation = useMutation({
    mutationFn: ({ previewId, corrections }: { previewId: string; corrections: Record<string, unknown> }) =>
      api.confirmUrl(previewId, corrections),
    onSuccess: (report) => {
      saveHistory(report);
      queryClient.setQueryData(["run", report.run_metadata.run_id], report);
      navigate(`/runs/${encodeURIComponent(report.run_metadata.run_id)}`);
    },
  });

  async function requestPreview(event: React.FormEvent) {
    event.preventDefault();
    if (!platforms.length) return;
    setPreviewError(null);
    await previewMutation.mutateAsync(url.trim()).catch(() => undefined);
  }

  async function confirm(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!preview) return;
    const form = new FormData(event.currentTarget);
    const text = String(form.get("text") ?? "");
    const creatorId = String(form.get("creator_id") ?? "");
    const publishedAt = String(form.get("published_at") ?? "");
    const corrections: Record<string, unknown> = {};
    if (text !== preview.post.text) corrections.text = text;
    if (creatorId !== preview.post.creator_id) corrections.creator_id = creatorId;
    if (publishedAt) corrections.published_at = new Date(publishedAt).toISOString();
    await confirmMutation.mutateAsync({ previewId: preview.preview_id, corrections }).catch(() => undefined);
  }

  return (
    <>
      <PageHeading eyebrow="SAFE URL IMPORT" title="URL 导入"
        description="先预览采集字段并人工修正，再明确确认分析；不会直接从 URL 得出结论。" />
      <section className="card">
        <SectionTitle number="01" title="预览采集内容" detail="preview → confirm" />
        <p className="card-description">
          仅支持后端已注册平台：{capabilities.isPending ? "读取能力中" : platforms.length ? platforms.map((item) => item.platform).join("、") : "当前没有已注册适配器"}。
          不支持的 URL 会由服务端拒绝。
        </p>
        {!capabilities.isPending && !urlImportEnabled && (
          <div className="notice-box warning-box">
            后端尚未注册可用的平台 URL 适配器，因此预览功能暂不可用。可先使用单条分析手动录入正文。
          </div>
        )}
        <form className="form-inline" onSubmit={requestPreview}>
          <label className="sr-only" htmlFor="source-url">帖子 URL</label>
          <input id="source-url" type="url" required maxLength={4096} value={url}
            onChange={(event) => setUrl(event.target.value)} placeholder="https://…" disabled={!urlImportEnabled} />
          <button className="primary-button" disabled={!urlImportEnabled || previewMutation.isPending}>
            {previewMutation.isPending ? "正在预览…" : "预览 URL"} <span>→</span>
          </button>
        </form>
        <Alert error={previewError} />
        {preview && (
          <form className="preview-form" onSubmit={confirm}>
            <div className="preview-meta">
              <span>{preview.post.platform} · {preview.adapter_name} {preview.adapter_version}</span>
              <span>来源摘要哈希：{preview.source_ref_hash}</span>
              <a href={preview.display_url} target="_blank" rel="noreferrer">查看来源 ↗</a>
            </div>
            <label htmlFor="preview-text">预览正文（可修正）</label>
            <textarea id="preview-text" name="text" defaultValue={preview.post.text} maxLength={50_000} />
            <div className="two-fields">
              <div><label htmlFor="preview-creator">创作者 ID</label>
                <input id="preview-creator" name="creator_id" defaultValue={preview.post.creator_id} />
              </div>
              <div><label htmlFor="preview-published">发布时间</label>
                <input id="preview-published" name="published_at" type="datetime-local"
                  defaultValue={preview.post.published_at ? toLocalDateTime(preview.post.published_at) : ""} />
              </div>
            </div>
            <div className="notice-box warning-box">
              已采集：{preview.post.media.length} 个媒体引用、{preview.post.comments.length} 条评论、
              {preview.post.history.length} 条历史、{preview.post.disclosures.length} 条披露记录。
              请检查预览字段和采集状态后再提交。
            </div>
            <Alert error={confirmMutation.error} />
            <button className="primary-button" disabled={confirmMutation.isPending}>
              {confirmMutation.isPending ? "正在确认并分析…" : "确认内容并分析"} <span>→</span>
            </button>
          </form>
        )}
      </section>
    </>
  );
}

function toLocalDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function RunPage() {
  const { runId = "" } = useParams();
  const query = useQuery({
    queryKey: ["run", runId],
    queryFn: ({ signal }) => api.run(runId, signal),
    enabled: /^[A-Za-z0-9_-]+$/.test(runId),
  });
  React.useEffect(() => {
    if (query.data) {
      try { saveHistory(query.data); } catch { /* local history is optional */ }
    }
  }, [query.data]);

  return (
    <>
      <PageHeading eyebrow="READ-ONLY EVIDENCE REPORT" title="运行报告"
        description="报告只读展示后端结果；不会在浏览器中重新计算标签或置信度。" />
      <Alert error={query.error} stale={Boolean(query.data)} />
      {!/^[A-Za-z0-9_-]+$/.test(runId)
        ? <Alert error={new Error("运行 ID 格式无效。")} />
        : query.isPending && !query.data
          ? <AsyncState loading />
          : query.data
            ? <RunReport report={query.data} />
            : <button type="button" className="secondary-button retry-button" onClick={() => query.refetch()}>
              重新加载报告
            </button>}
    </>
  );
}

function RunReport({ report }: { report: AnalysisReport }) {
  const { verdict_report: verdict, run_metadata: metadata } = report;
  const download = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `${metadata.run_id}.json`;
    anchor.click();
    URL.revokeObjectURL(href);
  };
  const duration = metadata.duration_ms === null || metadata.duration_ms === undefined
    ? "未记录"
    : `${(metadata.duration_ms / 1000).toFixed(2)} 秒`;
  const shift = verdict.creator_shift;

  return (
    <div className="report-stack">
      <section className="card report-header">
        <div className="report-header-top">
          <div><span className="eyebrow">RUN · {metadata.status.toUpperCase()}</span>
            <h2 className={`verdict-label verdict-${verdict.label === "需复核" ? "review" : verdict.label === "暗广" ? "risk" : "default"}`}>
              {verdict.label}
            </h2>
            <p className="review-note">{verdict.review_required ? "需要人工复核；不可作为独立金标。" : "系统输出仅供辅助参考，不替代人工判断。"}</p>
          </div>
          <div className="report-actions"><span className="confidence-chip">置信度 · {verdict.confidence.toFixed(3)}</span>
            <button type="button" className="secondary-button" onClick={download}>导出 JSON</button>
          </div>
        </div>
        <div className="meta-grid">
          <Meta label="运行 ID" value={metadata.run_id} />
          <Meta label="运行状态" value={statusNames[metadata.status] ?? metadata.status} />
          <Meta label="运行耗时" value={duration} />
          <Meta label="判断方法" value={verdict.judgment_method} />
          <Meta label="商业意图" value={verdict.commercial_intent.status} />
          <Meta label="披露状态" value={verdict.disclosure.status === "disclosed" ? "已披露" : verdict.disclosure.status === "not_disclosed" ? "未披露" : "未知"} />
        </div>
        <p className="timestamp">开始：{metadata.started_at ? new Date(metadata.started_at).toLocaleString() : "未记录"} · 结束：{metadata.finished_at ? new Date(metadata.finished_at).toLocaleString() : "未记录"}</p>
      </section>

      <section className="card">
        <SectionTitle title="结论与依据" detail="后端只读报告" />
        <ul className="reason-list">{verdict.reasons.length
          ? verdict.reasons.map((reason, index) => <li key={`${index}-${reason}`}>{reason}</li>)
          : <li className="muted">后端未提供判断依据。</li>}</ul>
        {verdict.disclosure.limitations.length > 0 && (
          <div className="notice-box warning-box"><strong>披露证据限制</strong>
            <ul>{verdict.disclosure.limitations.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
          </div>
        )}
      </section>

      <section className="card">
        <SectionTitle title="证据工作区" detail="证据覆盖与原始条目" />
        <EvidenceCanvas report={report} />
      </section>

      <div className="report-two-col">
        <section className="card">
          <SectionTitle title="CreatorShift 历史" detail="不推断缺失历史" />
          {shift ? (
            <CreatorShiftTimeline shift={shift} history={report.post?.history ?? []} />
          ) : <p className="muted">本次报告未提供创作者历史评估。</p>}
        </section>
        <section className="card">
          <SectionTitle title="法规与平台依据" detail="仅展示可追溯引用" />
          {verdict.law_evidence.length ? verdict.law_evidence.map((law) => {
            const sourceUrl = safeHttpUrl(law.source_path_or_url);
            return (
              <article className="law-item" key={law.source_id}>
                <strong>{law.document_title}{law.article_id ? ` · ${law.article_id}` : ""}</strong>
                <p>{law.quote || "未返回引用原文。"}</p>
                <small>{law.document_version ?? "版本未记录"} · {law.jurisdiction ?? "管辖区未记录"}</small>
                {sourceUrl
                  ? <a href={sourceUrl} target="_blank" rel="noreferrer">来源 ↗</a>
                  : <span className="muted">{law.source_path_or_url}</span>}
              </article>
            );
          }) : <p className="muted">报告未包含可展示的法规引用；页面不会补写法条。</p>}
        </section>
      </div>

      <section className="card">
        <SectionTitle title="Agent 执行轨迹" detail="不展示模型思维链" />
        {report.run_events.length ? (
          <ol className="event-list">{report.run_events.map((event) => (
            <li key={event.event_id}>
              <time>{new Date(event.timestamp).toLocaleTimeString()}</time>
              <div><strong>{event.stage}</strong><span>{event.tool_name ? `${event.event_type} · ${event.tool_name}` : event.event_type}</span></div>
            </li>
          ))}</ol>
        ) : <p className="muted">没有可展示的执行事件。</p>}
      </section>

      <section className="card">
        <SectionTitle title="运行元数据与限制" detail="审计信息" />
        <div className="meta-grid">
          <Meta label="运行模式" value={metadata.runtime_mode ?? "未记录"} />
          <Meta label="重试次数" value={String(metadata.retry_count)} />
          <Meta label="降级次数" value={String(metadata.fallback_count)} />
          <Meta label="工具版本" value={Object.entries(metadata.tool_versions).map(([name, version]) => `${name} ${version}`).join(" · ") || "未记录"} />
          <Meta label="模型版本" value={Object.entries(metadata.model_versions).map(([name, version]) => `${name} ${version}`).join(" · ") || "未记录"} />
        </div>
        <Limitations report={report} />
      </section>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return <div className="meta-cell"><span>{label}</span><strong>{value}</strong></div>;
}

function EvidenceCanvas({ report }: { report: AnalysisReport }) {
  const { evidence_bundle: bundle, verdict_report: verdict } = report;
  const polarity: Record<string, string> = {
    supports: "支持性证据",
    contradicts: "矛盾证据",
    neutral: "中性证据",
  };
  return (
    <>
      <div className="coverage-grid">
        {bundle.coverage.map((item) => {
          return (
            <div className="coverage-card" key={item.modality}>
              <div><span>{coverageNames[item.modality] ?? item.modality}</span>
                <strong className={`coverage-status coverage-${item.status}`}>{coverageStatuses[item.status] ?? item.status}</strong></div>
              <div className="coverage-track"><span className={`coverage-fill coverage-fill-${item.status}`} /></div>
              <small>{item.evidence_ids.length} 条关联证据</small>
            </div>
          );
        })}
      </div>
      {bundle.missing_requirements.length > 0 && (
        <div className="notice-box warning-box"><strong>缺失要求</strong>
          <ul>{bundle.missing_requirements.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
        </div>
      )}
      {bundle.conflicts.length > 0 && (
        <div className="notice-box warning-box"><strong>证据冲突</strong>
          <ul>{bundle.conflicts.map((item) => <li key={item.conflict_id}>{item.reason}（{item.evidence_ids.join(", ")}）</li>)}</ul>
        </div>
      )}
      <div className="evidence-list">
        {bundle.items.map((item) => {
          const cited = verdict.evidence_ids.includes(item.evidence_id)
            || verdict.creator_shift_evidence_ids.includes(item.evidence_id)
            || verdict.disclosure.evidence_ids.includes(item.evidence_id)
            || verdict.commercial_intent.evidence_ids.includes(item.evidence_id);
          return (
            <article className="evidence-item" key={item.evidence_id}>
              <div className="evidence-heading"><strong>{item.kind}</strong><span>{coverageNames[item.source_type ?? ""] ?? item.source_type ?? item.source}</span></div>
              <p className="quote">{item.quote || "没有引用文本；请检查来源记录。"}</p>
              <div className="evidence-meta"><span>ID · {item.evidence_id}</span><span>{item.tool_name}</span>
                <span>{polarity[item.polarity ?? "neutral"] ?? item.polarity}</span>
                {cited && <span className="cited-badge">被结论引用</span>}
              </div>
              {item.limitations.length > 0 && <p className="limitation-text">{item.limitations.join("；")}</p>}
            </article>
          );
        })}
        {!bundle.items.length && <p className="muted">没有证据条目；这不表示未发现证据。</p>}
      </div>
      <div className="tool-grid">
        {bundle.tool_results.map((tool, index) => (
          <div className="tool-card" key={`${tool.tool_name}-${index}`}>
            <strong>{tool.tool_name}</strong><span>{tool.status}</span>
            <small>{tool.latency_ms === null || tool.latency_ms === undefined ? "耗时未记录" : `${tool.latency_ms} ms`}</small>
            {tool.warnings.map((warning) => <small key={warning}>{warning}</small>)}
          </div>
        ))}
      </div>
    </>
  );
}

function CreatorShiftTimeline({ shift, history }: {
  shift: NonNullable<AnalysisReport["verdict_report"]["creator_shift"]>;
  history: NonNullable<AnalysisReport["post"]>["history"];
}) {
  if (!shift) return null;
  return (
    <div>
      <div className="shift-summary">
        <strong>{shift.status === "sufficient" ? "历史充分" : shift.status === "insufficient" ? "历史不足" : "不可用"}</strong>
        <span>{shift.history_count} / {shift.required_history} 条历史</span>
        {shift.shift_score !== null && <span>变化分值 · {shift.shift_score.toFixed(3)}</span>}
      </div>
      {shift.window_start && <p className="field-hint">窗口：{shift.window_start} — {shift.window_end ?? "未记录"}</p>}
      <ol className="timeline">
        {history.map((item) => (
          <li key={item.post_id}><time>{item.published_at ?? "时间未记录"}</time>
            <div><strong>{item.post_id}</strong><p>{item.text ?? "正文未提供"}</p></div>
          </li>
        ))}
      </ol>
      {shift.top_features.length > 0 && <p className="field-hint">主要特征：{shift.top_features.join("、")}</p>}
      {shift.limitations.length > 0 && <ul className="reason-list">{shift.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}
      {!history.length && <p className="muted">报告没有可显示的逐条历史内容。</p>}
    </div>
  );
}

function Limitations({ report }: { report: AnalysisReport }) {
  const { evidence_bundle: bundle, run_metadata: metadata, verdict_report: verdict } = report;
  const values = [
    ...bundle.missing_requirements,
    ...bundle.limitations.map((item) => item.message),
    ...bundle.coverage.flatMap((item) => item.limitations.map((limit) => limit.message)),
    ...bundle.tool_results.flatMap((tool) => [
      ...tool.warnings,
      ...tool.limitations.map((item) => item.message),
    ]),
    ...bundle.items.flatMap((item) => item.limitations),
    ...metadata.issues.map((item) => item.message),
    ...bundle.conflicts.map((item) => `证据冲突：${item.reason}`),
    ...verdict.disclosure.limitations,
    ...(verdict.creator_shift?.limitations ?? []),
  ];
  const unique = [...new Set(values.filter(Boolean))];
  return unique.length
    ? <ul className="reason-list">{unique.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
    : <p className="muted">后端未报告其他限制；这不代表证据完整。</p>;
}

function HistoryPage() {
  const [history, setHistory] = React.useState(readHistory);
  const clear = () => {
    try {
      localStorage.removeItem(historyKey);
      setHistory([]);
    } catch (error) {
      notifyToast(`无法清除本地历史：${errorText(error)}`);
    }
  };
  return (
    <>
      <PageHeading eyebrow="LOCAL HISTORY" title="最近运行"
        description="仅在此浏览器保存运行 ID 和摘要，不保存正文、评论或报告内容。" />
      <section className="card">
        <div className="section-title section-title-split"><SectionTitle title="最近 20 次运行" detail="仅本机浏览器存储" />
          <button className="secondary-button" type="button" onClick={clear} disabled={!history.length}>清除历史</button>
        </div>
        {history.length ? <div className="history-list">{history.map((item) => (
          <Link className="history-row" to={`/runs/${encodeURIComponent(item.run_id)}`} key={item.run_id}>
            <span className="history-label">{item.label}</span>
            <span className="history-run"><strong>{item.post_id}</strong><small>{item.run_id}</small></span>
            <span>{item.confidence.toFixed(3)}</span>
            <time>{new Date(item.created_at).toLocaleString()}</time>
            <span>打开 →</span>
          </Link>
        ))}</div> : <div className="empty-inline">暂无记录。成功分析后只保存摘要和运行 ID。</div>}
      </section>
    </>
  );
}

function SettingsPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  return (
    <>
      <PageHeading eyebrow="LOCAL CAPABILITIES" title="能力与设置"
        description="查看当前本机 API 暴露的能力；这里不会猜测未公开的模型或服务状态。" />
      <div className="report-two-col">
        <section className="card"><SectionTitle title="服务健康" detail="GET /health" />
          <AsyncState loading={health.isPending} error={health.error}>
            {health.data && <div className="meta-grid"><Meta label="服务状态" value={health.data.status} /><Meta label="API 版本" value={health.data.api_version} /></div>}
          </AsyncState>
        </section>
        <section className="card"><SectionTitle title="后端能力" detail="GET /api/v1/capabilities" />
          <AsyncState loading={capabilities.isPending} error={capabilities.error}>
            {capabilities.data && <CapabilitiesView capabilities={capabilities.data} />}
          </AsyncState>
        </section>
      </div>
      <section className="card security-card">
        <SectionTitle title="隐私与部署边界" />
        <ul className="reason-list">
          <li>页面与 API 同源；默认以 127.0.0.1 运行，不应暴露到公网。</li>
          <li>最近运行仅在 localStorage 保存 run_id、post_id、标签、置信度和时间；不保存正文。</li>
          <li>图片路径和任意远程媒体未开放；URL 导入只走后端 preview → confirm。</li>
          <li>不接入外部埋点、字体或第三方云服务。</li>
        </ul>
      </section>
    </>
  );
}

function CapabilitiesView({ capabilities }: { capabilities: Capabilities }) {
  return (
    <div className="capability-list">
      <Meta label="可用标签" value={capabilities.labels.join("、")} />
      <Meta label="运行模式" value={capabilities.runtime_modes.join("、")} />
      <Meta label="检测工具数" value={String(capabilities.detection_tools)} />
      <Meta label="法规检索" value={capabilities.legal_retrieval} />
      <Meta label="运行恢复" value={capabilities.run_query ? "支持" : "不支持"} />
      <Meta label="批量上限" value={capabilities.batch_analysis.enabled ? `${capabilities.batch_analysis.max_items} 条` : "关闭"} />
      <Meta label="URL 导入" value={capabilities.url_import.enabled
        ? capabilities.url_import.platforms.map((item) => `${item.platform} (${item.hosts.join(", ")})`).join("；") || "已启用，暂无适配器"
        : "关闭"} />
    </div>
  );
}

function NotFoundPage() {
  return <section className="card empty-inline"><h2>页面不存在</h2><p>请从左侧导航选择一个工作区。</p><Link className="primary-link" to="/analyze">返回单条分析 →</Link></section>;
}

export default function App() {
  return <AppShell />;
}
