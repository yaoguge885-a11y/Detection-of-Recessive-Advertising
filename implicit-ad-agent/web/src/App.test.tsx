import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import type { AnalysisReport } from "./contracts";

const report: AnalysisReport = {
  verdict_report: {
    post_id: "post-1",
    label: "需复核",
    confidence: 0.5,
    review_required: true,
    commercial_intent: { status: "present", score: 0.72, evidence_ids: ["ev-1"] },
    disclosure: { status: "unknown", confidence: null, evidence_ids: [], limitations: ["披露材料未采集"] },
    creator_shift: null,
    creator_shift_evidence_ids: [],
    evidence_ids: ["ev-1"],
    reasons: ["disclosure:unknown"],
    law_evidence: [],
    judgment_method: "deterministic_baseline_v1",
  },
  evidence_bundle: {
    post_id: "post-1",
    items: [{
      evidence_id: "ev-1",
      kind: "soft_ad_signal",
      source: "text",
      source_type: "text",
      tool_name: "analyze_text_intent",
      quote: "可能的证据摘录",
      score: 0.72,
      polarity: "supports",
      status: "observed",
      limitations: [],
      metadata: {},
    }],
    tool_results: [],
    limitations: [],
    coverage: [
      { modality: "text", status: "covered", evidence_ids: ["ev-1"], limitations: [] },
      { modality: "image", status: "missing", evidence_ids: [], limitations: [] },
    ],
    conflicts: [],
    missing_requirements: ["图片未采集"],
  },
  run_metadata: {
    run_id: "run_fixture_1",
    status: "completed",
    started_at: "2026-11-01T00:00:00Z",
    finished_at: "2026-11-01T00:00:01Z",
    duration_ms: 1000,
    tool_versions: { analyze_text_intent: "1.0" },
    model_versions: {},
    issues: [],
    trace_ids: [],
    runtime_mode: "local",
    planner_version: null,
    prompt_versions: {},
    retry_count: 0,
    fallback_count: 0,
  },
  run_events: [],
  readable_report: "read-only report",
};
const labels = ["明广", "暗广", "非广", "需复核"];

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

function renderApp(initialPath: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("architecture-aligned SPA", () => {
  it("submits a single item and presents the read-only evidence report", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input);
      if (path === "/health") return jsonResponse({ status: "ok", api_version: "v1" });
      if (path === "/api/v1/analyze") return jsonResponse(report);
      return jsonResponse(report);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderApp("/analyze");

    await user.type(screen.getByLabelText(/帖子正文/), "仅用于界面测试的帖子");
    await user.click(screen.getByRole("button", { name: /提交并分析/ }));

    expect(await screen.findByRole("heading", { name: "证据工作区" })).toBeInTheDocument();
    expect(screen.getAllByText("需复核").length).toBeGreaterThan(0);
    expect(screen.getByText("缺失")).toBeInTheDocument();
    expect(screen.getAllByText("图片未采集").length).toBeGreaterThan(0);
    const analyzeCall = fetchMock.mock.calls.find(([input]) => String(input) === "/api/v1/analyze");
    expect(analyzeCall).toBeDefined();
    const body = JSON.parse(String(analyzeCall?.[1]?.body));
    expect(body.text).toBe("仅用于界面测试的帖子");
    expect(body.capture_complete).toBe(false);
    const history = JSON.parse(localStorage.getItem("impad.recent-runs.v1") ?? "[]");
    expect(history).toHaveLength(1);
    expect(history[0]).not.toHaveProperty("text");
  });

  it("shows each batch success and failure without dropping failed inputs", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input);
      if (path === "/health") return jsonResponse({ status: "ok", api_version: "v1" });
      if (path === "/api/v1/capabilities") return jsonResponse({
        runtime_modes: ["local"], labels, detection_tools: 7, legal_retrieval: "local",
        run_query: true, batch_analysis: { enabled: true, max_items: 50 },
        url_import: { enabled: true, workflow: ["preview", "confirm"], platforms: [
          { platform: "fixture", adapter: "fixture-adapter", version: "1", hosts: ["example.test"] },
        ] },
      });
      if (path === "/api/v1/analyze/batch") return jsonResponse({
        total: 2, succeeded: 1, failed: 1,
        items: [
          { index: 0, ok: true, result: report, error: null },
          { index: 1, ok: false, result: null, error: { code: "invalid_input", message: "Input could not be normalized." } },
        ],
      });
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderApp("/batch");
    fireEvent.change(screen.getByLabelText(/JSON \/ CSV/), {
      target: { value: '[{"text":"ok"},{"platform":"invalid"}]' },
    });
    await user.click(screen.getByRole("button", { name: /提交批次/ }));

    const results = await screen.findByText(/1 成功 · 1 失败/);
    expect(results).toBeInTheDocument();
    expect(screen.getByText("Input could not be normalized.")).toBeInTheDocument();
    const request = fetchMock.mock.calls.find(([input]) => String(input) === "/api/v1/analyze/batch");
    expect(JSON.parse(String(request?.[1]?.body)).items).toHaveLength(2);
  });

  it("parses CSV cells and preserves commas inside quoted post text", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input);
      if (path === "/health") return jsonResponse({ status: "ok", api_version: "v1" });
      if (path === "/api/v1/capabilities") return jsonResponse({
        runtime_modes: ["local"], labels, detection_tools: 7, legal_retrieval: "local",
        run_query: true, batch_analysis: { enabled: true, max_items: 50 },
        url_import: { enabled: false, workflow: ["preview", "confirm"], platforms: [] },
      });
      if (path === "/api/v1/analyze/batch") return jsonResponse({
        total: 1, succeeded: 0, failed: 1,
        items: [{ index: 0, ok: false, result: null, error: { code: "invalid_input", message: "fixture" } }],
      });
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderApp("/batch");
    fireEvent.change(screen.getByLabelText(/JSON \/ CSV/), {
      target: { value: 'text,platform\n"品牌推广, 限时活动",other' },
    });
    await user.click(screen.getByRole("button", { name: /提交批次/ }));
    await screen.findByText("fixture");

    const request = fetchMock.mock.calls.find(([input]) => String(input) === "/api/v1/analyze/batch");
    expect(JSON.parse(String(request?.[1]?.body)).items).toEqual([
      { text: "品牌推广, 限时活动", platform: "other" },
    ]);
  });

  it("requires URL preview before confirmation and sends only edited fields", async () => {
    const preview = {
      preview_id: `preview_${"a".repeat(32)}`,
      platform: "fixture",
      adapter_name: "fixture-adapter",
      adapter_version: "1",
      display_url: "https://example.test/post/1",
      source_ref_hash: "f".repeat(64),
      created_at: "2026-11-01T00:00:00Z",
      post: {
        post_id: "post-1", platform: "fixture", creator_id: "creator-1",
        published_at: null, text: "预览正文", comments: [], history: [], disclosures: [], media: [],
      },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input);
      if (path === "/health") return jsonResponse({ status: "ok", api_version: "v1" });
      if (path === "/api/v1/capabilities") return jsonResponse({
        runtime_modes: ["local"], labels, detection_tools: 7, legal_retrieval: "local",
        run_query: true, batch_analysis: { enabled: true, max_items: 50 },
        url_import: { enabled: true, workflow: ["preview", "confirm"], platforms: [
          { platform: "fixture", adapter: "fixture-adapter", version: "1", hosts: ["example.test"] },
        ] },
      });
      if (path === "/api/v1/import/url/preview") return jsonResponse(preview);
      if (path === "/api/v1/import/url/confirm") return jsonResponse(report);
      return jsonResponse(report);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderApp("/import");
    fireEvent.change(screen.getByLabelText("帖子 URL"), {
      target: { value: "https://example.test/post/1" },
    });
    expect(screen.getByLabelText("帖子 URL")).toHaveValue("https://example.test/post/1");
    await waitFor(() => expect(screen.getByRole("button", { name: /预览 URL/ })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /预览 URL/ }));
    await screen.findByLabelText("预览正文（可修正）");
    await user.clear(screen.getByLabelText("预览正文（可修正）"));
    await user.type(screen.getByLabelText("预览正文（可修正）"), "人工修正正文");
    await user.click(screen.getByRole("button", { name: /确认内容并分析/ }));

    await screen.findByRole("heading", { name: "证据工作区" });
    const previewCall = fetchMock.mock.calls.find(([input]) => String(input) === "/api/v1/import/url/preview");
    const confirmCall = fetchMock.mock.calls.find(([input]) => String(input) === "/api/v1/import/url/confirm");
    expect(previewCall).toBeDefined();
    expect(JSON.parse(String(confirmCall?.[1]?.body))).toEqual({
      preview_id: preview.preview_id,
      corrections: { text: "人工修正正文" },
      runtime_mode: "local",
    });
  });

  it("shows a runtime response-contract error instead of rendering malformed data", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input);
      if (path === "/health") return jsonResponse({ status: "ok", api_version: "v1" });
      if (path === "/api/v1/analyze") return jsonResponse({ verdict_report: { label: "bad" } });
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderApp("/analyze");
    await user.type(screen.getByLabelText(/帖子正文/), "测试");
    await user.click(screen.getByRole("button", { name: /提交并分析/ }));
    expect(await screen.findByText(/请求未成功/)).toBeInTheDocument();
    expect(screen.getByText(/不符合接口契约/)).toBeInTheDocument();
  });

  it("keeps URL preview disabled until the backend advertises an adapter", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input);
      if (path === "/health") return jsonResponse({ status: "ok", api_version: "v1" });
      if (path === "/api/v1/capabilities") return jsonResponse({
        runtime_modes: ["local"], labels, detection_tools: 7, legal_retrieval: "local",
        run_query: true, batch_analysis: { enabled: true, max_items: 50 },
        url_import: { enabled: true, workflow: ["preview", "confirm"], platforms: [] },
      });
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/import");

    expect(await screen.findByText(/尚未注册可用的平台 URL 适配器/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /预览 URL/ })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/import/url/preview"))).toBe(false);
  });
});
