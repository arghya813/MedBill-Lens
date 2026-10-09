import type {
  AnalyzeResponse,
  AnalysisOut,
  ApiErrorBody,
  BenchmarkListResponse,
  BillOut,
  DatasetStatsResponse,
  DemoScenarioListResponse,
  DisclaimerResponse,
  EnumOptionsResponse,
  ExtractResponse,
  HealthResponse,
  ManualBillCreateRequest,
  PreviewRequest,
  PreviewResponse,
  QuestionsResponse,
  ReportFormat,
  ReportResponse,
  SampleBillListResponse,
  UpdateBillItemsRequest,
  UploadResponse,
} from "./types";

/**
 * Base URL for the API.
 *
 * In development Vite proxies `/api` to the backend (see `vite.config.ts`), so
 * a relative base works and no CORS setup is required. Set
 * `VITE_API_BASE_URL` when the API is deployed on a different origin.
 */
const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(
  /\/$/,
  "",
) ?? "";

/** Error thrown for every non-2xx response, carrying the server's envelope. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly hint: string | null;
  readonly detail: string | null;

  constructor(status: number, body: ApiErrorBody["error"] | null, fallback: string) {
    super(body?.message || fallback);
    this.name = "ApiError";
    this.status = status;
    this.code = body?.code ?? "unknown_error";
    this.detail = body?.detail ?? null;
    this.hint = body?.hint ?? null;
  }

  /** Field-level problems reported by the 422 validation handler. */
  get fieldHints(): string[] {
    if (!this.hint) return [];
    return this.hint
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean);
  }
}

/** Network failures never reach the server, so they get their own message. */
export class NetworkError extends Error {
  constructor() {
    super(
      "We couldn't reach the server. Check that the backend is running, then try again.",
    );
    this.name = "NetworkError";
  }
}

async function request<T>(
  path: string,
  init: RequestInit & { signal?: AbortSignal } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...init.headers,
      },
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new NetworkError();
  }

  if (!response.ok) {
    let body: ApiErrorBody["error"] | null = null;
    try {
      body = (await response.json())?.error ?? null;
    } catch {
      // Non-JSON error body (proxy failure, HTML error page). Keep the status.
    }
    throw new ApiError(response.status, body, `Request failed (${response.status}).`);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function query(params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export interface BenchmarkFilters extends Record<string, string | number | boolean | null | undefined> {
  city?: string;
  hospital_category?: string;
  service_category?: string;
  treatment?: string;
  room_category?: string;
  verified_only?: boolean;
  limit?: number;
  offset?: number;
}

export const api = {
  health: (signal?: AbortSignal) =>
    request<HealthResponse>("/api/health", { signal }),

  disclaimer: (signal?: AbortSignal) =>
    request<DisclaimerResponse>("/api/disclaimer", { signal }),

  options: (signal?: AbortSignal) =>
    request<EnumOptionsResponse>("/api/options", { signal }),

  benchmarks: (filters: BenchmarkFilters = {}, signal?: AbortSignal) =>
    request<BenchmarkListResponse>(`/api/benchmarks${query(filters)}`, { signal }),

  benchmarkStats: (signal?: AbortSignal) =>
    request<DatasetStatsResponse>("/api/benchmarks/stats", { signal }),

  demoScenarios: (signal?: AbortSignal) =>
    request<DemoScenarioListResponse>("/api/demo/scenarios", { signal }),

  sampleBills: (signal?: AbortSignal) =>
    request<SampleBillListResponse>("/api/demo/sample-bills", { signal }),

  /** One-click demo: creates a confirmed bill and analyses it in a single call. */
  runDemoScenario: (key: string) =>
    request<AnalyzeResponse>(`/api/demo/scenarios/${encodeURIComponent(key)}/run`, {
      method: "POST",
    }),

  loadDemoScenario: (key: string) =>
    request<UploadResponse>(`/api/demo/scenarios/${encodeURIComponent(key)}/load`, {
      method: "POST",
    }),

  uploadBill: (file: File, signal?: AbortSignal) => {
    const body = new FormData();
    body.append("file", file);
    return request<UploadResponse>("/api/bills/upload", {
      method: "POST",
      body,
      signal,
    });
  },

  extractBill: (billId: string) =>
    request<ExtractResponse>(`/api/bills/${billId}/extract`, { method: "POST" }),

  getBill: (billId: string, signal?: AbortSignal) =>
    request<BillOut>(`/api/bills/${billId}`, { signal }),

  createManualBill: (payload: ManualBillCreateRequest) =>
    request<UploadResponse>("/api/bills", { method: "POST", body: JSON.stringify(payload) }),

  /** Returns a bare `BillOut` (not an envelope). */
  updateBillItems: (billId: string, payload: UpdateBillItemsRequest) =>
    request<BillOut>(`/api/bills/${billId}/items`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  /**
   * Compare the review screen's current, unsaved charges.
   *
   * Available before confirmation and writes nothing, so the editor can call it
   * as the user corrects what extraction read.
   */
  previewBill: (payload: PreviewRequest, signal?: AbortSignal) =>
    request<PreviewResponse>("/api/bills/preview", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    }),

  analyzeBill: (billId: string) =>
    request<AnalyzeResponse>(`/api/bills/${billId}/analyze`, { method: "POST" }),

  /** Returns a bare `AnalysisOut` (not an envelope). */
  getAnalysis: (billId: string, signal?: AbortSignal) =>
    request<AnalysisOut>(`/api/bills/${billId}/analysis`, { signal }),

  regenerateQuestions: (billId: string) =>
    request<QuestionsResponse>(`/api/bills/${billId}/questions`, { method: "POST" }),

  report: (
    billId: string,
    options: {
      format?: ReportFormat;
      hide_patient_name?: boolean;
      hide_patient_id?: boolean;
      hide_bill_number?: boolean;
      hide_hospital_name?: boolean;
      include_questions?: boolean;
      include_sources?: boolean;
    } = {},
    signal?: AbortSignal,
  ) => request<ReportResponse>(`/api/bills/${billId}/report${query(options)}`, { signal }),

  deleteBill: (billId: string) =>
    request<{ deleted: boolean; bill_id: string }>(`/api/bills/${billId}`, {
      method: "DELETE",
    }),
};
