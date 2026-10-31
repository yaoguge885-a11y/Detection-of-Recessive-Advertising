import { z } from "zod";

export const runStatusSchema = z.enum([
  "pending",
  "running",
  "completed",
  "degraded",
  "failed",
]);

export const analysisReportSchema = z.object({
  verdict_report: z.object({
    post_id: z.string(),
    label: z.enum(["明广", "暗广", "非广", "需复核"]),
    confidence: z.number().finite().min(0).max(1),
    review_required: z.boolean(),
    commercial_intent: z.object({
      status: z.enum(["present", "absent", "uncertain"]),
      score: z.number().nullable().optional(),
      evidence_ids: z.array(z.string()).default([]),
    }).passthrough(),
    disclosure: z.object({
      status: z.enum(["disclosed", "not_disclosed", "unknown"]),
      confidence: z.number().nullable().optional(),
      evidence_ids: z.array(z.string()).default([]),
      limitations: z.array(z.string()).default([]),
    }).passthrough(),
    creator_shift: z.object({
      status: z.enum(["sufficient", "insufficient", "unavailable"]),
      history_count: z.number(),
      required_history: z.number(),
      shift_score: z.number().nullable(),
      pooling_method: z.string().nullable(),
      history_post_ids: z.array(z.string()).default([]),
      top_features: z.array(z.string()).default([]),
      feature_deltas: z.record(z.string(), z.number()).default({}),
      limitations: z.array(z.string()).default([]),
      window_start: z.string().nullable().optional(),
      window_end: z.string().nullable().optional(),
    }).passthrough().nullable().optional(),
    creator_shift_evidence_ids: z.array(z.string()).default([]),
    evidence_ids: z.array(z.string()).default([]),
    reasons: z.array(z.string()).default([]),
    law_evidence: z.array(z.object({
      source_id: z.string(),
      document_title: z.string(),
      source_path_or_url: z.string(),
      article_id: z.string().nullable().optional(),
      document_version: z.string().nullable().optional(),
      jurisdiction: z.string().nullable().optional(),
      effective_date: z.string().nullable().optional(),
      quote: z.string().nullable().optional(),
      retrieval_score: z.number().nullable().optional(),
      limitations: z.array(z.string()).default([]),
    }).passthrough()).default([]),
    judgment_method: z.string().default("unknown"),
  }).passthrough(),
  evidence_bundle: z.object({
    post_id: z.string(),
    items: z.array(z.object({
      evidence_id: z.string(),
      kind: z.string(),
      source: z.string(),
      source_type: z.string().nullable().optional(),
      tool_name: z.string(),
      quote: z.string().nullable().optional(),
      score: z.number().nullable().optional(),
      polarity: z.string().optional(),
      status: z.string().optional(),
      limitations: z.array(z.string()).default([]),
      metadata: z.record(z.string(), z.unknown()).default({}),
    }).passthrough()).default([]),
    tool_results: z.array(z.object({
      tool_name: z.string(),
      status: z.string(),
      score: z.number().nullable().optional(),
      latency_ms: z.number().nullable().optional(),
      warnings: z.array(z.string()).default([]),
      limitations: z.array(z.object({
        code: z.string(),
        message: z.string(),
      }).passthrough()).default([]),
    }).passthrough()).default([]),
    limitations: z.array(z.object({
      code: z.string(),
      message: z.string(),
    }).passthrough()).default([]),
    coverage: z.array(z.object({
      modality: z.string(),
      status: z.string(),
      evidence_ids: z.array(z.string()).default([]),
      limitations: z.array(z.object({
        code: z.string(),
        message: z.string(),
      }).passthrough()).default([]),
    }).passthrough()).default([]),
    conflicts: z.array(z.object({
      conflict_id: z.string(),
      evidence_ids: z.array(z.string()),
      reason: z.string(),
    }).passthrough()).default([]),
    missing_requirements: z.array(z.string()).default([]),
  }).passthrough(),
  run_metadata: z.object({
    run_id: z.string().min(1),
    status: runStatusSchema,
    started_at: z.string().optional(),
    finished_at: z.string().nullable().optional(),
    duration_ms: z.number().nullable().optional(),
    tool_versions: z.record(z.string(), z.string()).default({}),
    model_versions: z.record(z.string(), z.string()).default({}),
    issues: z.array(z.object({
      kind: z.string(),
      code: z.string(),
      message: z.string(),
      stage: z.string(),
      retryable: z.boolean().nullable().optional(),
    }).passthrough()).default([]),
    trace_ids: z.array(z.string()).default([]),
    runtime_mode: z.string().optional(),
    planner_version: z.string().nullable().optional(),
    prompt_versions: z.record(z.string(), z.string()).default({}),
    retry_count: z.number().default(0),
    fallback_count: z.number().default(0),
  }).passthrough(),
  run_events: z.array(z.object({
    event_id: z.string(),
    event_type: z.string(),
    stage: z.string(),
    timestamp: z.string(),
    call_id: z.string().nullable().optional(),
    tool_name: z.string().nullable().optional(),
    data: z.record(z.string(), z.unknown()).default({}),
  }).passthrough()).default([]),
  readable_report: z.string().optional(),
  post: z.object({
    post_id: z.string().optional(),
    platform: z.string().optional(),
    creator_id: z.string().optional(),
    published_at: z.string().nullable().optional(),
    text: z.string().optional(),
    history: z.array(z.object({
      post_id: z.string(),
      published_at: z.string().nullable().optional(),
      text: z.string().optional(),
    }).passthrough()).default([]),
  }).passthrough().optional(),
}).passthrough();

export type AnalysisReport = z.infer<typeof analysisReportSchema>;
export type AnalyzeRequest = {
  text: string;
  platform: string;
  blogger?: string;
  creator_id?: string;
  published_at?: string;
  comments?: Array<string | Record<string, unknown>>;
  history?: Array<string | Record<string, unknown>>;
  capture_complete: boolean;
  runtime_mode: "local" | "mcp";
};

export const capabilitiesSchema = z.object({
  runtime_modes: z.array(z.string()),
  labels: z.array(z.string()),
  detection_tools: z.number(),
  legal_retrieval: z.string(),
  run_query: z.boolean(),
  batch_analysis: z.object({
    enabled: z.boolean(),
    max_items: z.number().int().positive(),
  }),
  url_import: z.object({
    enabled: z.boolean(),
    workflow: z.array(z.string()),
    platforms: z.array(z.object({
      platform: z.string(),
      adapter: z.string(),
      version: z.string(),
      hosts: z.array(z.string()),
    }).passthrough()),
  }),
}).passthrough();
export type Capabilities = z.infer<typeof capabilitiesSchema>;

export const healthSchema = z.object({
  status: z.string(),
  api_version: z.string(),
}).passthrough();

export const batchResponseSchema = z.object({
  total: z.number(),
  succeeded: z.number(),
  failed: z.number(),
  items: z.array(z.object({
    index: z.number(),
    ok: z.boolean(),
    result: analysisReportSchema.nullable().optional(),
    error: z.object({
      code: z.string(),
      message: z.string(),
    }).nullable().optional(),
  }).passthrough()),
}).passthrough();
export type BatchResponse = z.infer<typeof batchResponseSchema>;

export const urlPreviewSchema = z.object({
  preview_id: z.string(),
  platform: z.string(),
  adapter_name: z.string(),
  adapter_version: z.string(),
  display_url: z.string(),
  source_ref_hash: z.string(),
  created_at: z.string(),
  post: z.object({
    post_id: z.string(),
    platform: z.string(),
    creator_id: z.string(),
    published_at: z.string().nullable(),
    text: z.string(),
    comments: z.array(z.unknown()).default([]),
    history: z.array(z.unknown()).default([]),
    disclosures: z.array(z.unknown()).default([]),
    media: z.array(z.unknown()).default([]),
  }).passthrough(),
}).passthrough();
export type URLPreview = z.infer<typeof urlPreviewSchema>;

export const historyItemSchema = z.object({
  run_id: z.string(),
  post_id: z.string(),
  label: z.string(),
  confidence: z.number(),
  created_at: z.string(),
});
export type HistoryItem = z.infer<typeof historyItemSchema>;
