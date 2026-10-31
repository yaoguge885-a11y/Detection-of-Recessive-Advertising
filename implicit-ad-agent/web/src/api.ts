import { z } from "zod";
import {
  analysisReportSchema,
  batchResponseSchema,
  capabilitiesSchema,
  healthSchema,
  urlPreviewSchema,
  type AnalyzeRequest,
  type AnalysisReport,
  type BatchResponse,
  type Capabilities,
  type URLPreview,
} from "./contracts";

async function requestJson<T>(
  path: string,
  schema: { parse(value: unknown): T },
  options: RequestInit = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 30_000);
  try {
    const signal = options.signal
      ? AbortSignal.any([controller.signal, options.signal])
      : controller.signal;
    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      signal,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
    const payload: unknown = await response.json().catch(() => {
      throw new Error(`服务器返回了无法解析的响应（HTTP ${response.status}）`);
    });
    if (!response.ok) {
      const detail = payload && typeof payload === "object" && "detail" in payload
        ? payload.detail
        : undefined;
      const message = detail && typeof detail === "object" && "message" in detail
        ? String(detail.message)
        : typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail
              .filter((item): item is { loc: unknown[]; msg: string } =>
                Boolean(item && typeof item === "object" && "msg" in item && "loc" in item
                  && typeof item.msg === "string" && Array.isArray(item.loc))
              )
              .slice(0, 3)
              .map((item) => `${item.loc.slice(1).join(".") || "请求"}：${item.msg}`)
              .join("；") || `请求失败（HTTP ${response.status}）`
          : `请求失败（HTTP ${response.status}）`;
      throw new Error(message);
    }
    try {
      return schema.parse(payload);
    } catch (error) {
      if (error instanceof z.ZodError) {
        const issues = error.issues.slice(0, 3).map((issue) => {
          const field = issue.path.length ? issue.path.join(".") : "response";
          return `${field}: ${issue.message}`;
        });
        throw new Error(`服务器返回的数据不符合接口契约（${issues.join("；")}）`);
      }
      throw error;
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("请求超过 30 秒仍未完成，请检查本机服务后重试。");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

const jsonBody = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
});

export const api = {
  health: () => requestJson("/health", healthSchema),
  capabilities: (): Promise<Capabilities> =>
    requestJson("/api/v1/capabilities", capabilitiesSchema),
  analyze: (request: AnalyzeRequest): Promise<AnalysisReport> =>
    requestJson("/api/v1/analyze", analysisReportSchema, jsonBody(request)),
  run: (runId: string, signal?: AbortSignal): Promise<AnalysisReport> =>
    requestJson(`/api/v1/runs/${encodeURIComponent(runId)}`, analysisReportSchema, { signal }),
  batch: (items: unknown[]): Promise<BatchResponse> =>
    requestJson("/api/v1/analyze/batch", batchResponseSchema, jsonBody({ items })),
  previewUrl: (url: string): Promise<URLPreview> =>
    requestJson("/api/v1/import/url/preview", urlPreviewSchema, jsonBody({ url })),
  confirmUrl: (
    previewId: string,
    corrections: Record<string, unknown>,
  ): Promise<AnalysisReport> =>
    requestJson(
      "/api/v1/import/url/confirm",
      analysisReportSchema,
      jsonBody({ preview_id: previewId, corrections, runtime_mode: "local" }),
    ),
};
