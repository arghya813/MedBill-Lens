/**
 * Response and request shapes for the MedBill Lens API.
 *
 * These mirror the FastAPI schemas one-for-one. Every numeric money field is
 * a plain number in major units (rupees), never a formatted string, so the UI
 * can do arithmetic and delegate display to `formatMoney`.
 */

export type FlagStatus =
  | "within_range"
  | "below_range"
  | "review"
  | "above_range"
  | "attention"
  | "insufficient_data"
  | "not_comparable";

export type BillStatus =
  | "uploaded"
  | "extracting"
  | "awaiting_confirmation"
  | "confirmed"
  | "analyzing"
  | "completed"
  | "failed";

export interface CategoryOption {
  value: string;
  label: string;
}

/** Normalised shape for dropdowns, regardless of how the API encodes them. */
export interface SelectOption {
  value: string;
  label: string;
}

export interface EnumOptionsResponse {
  categories: CategoryOption[];
  hospital_categories: CategoryOption[];
  room_categories: CategoryOption[];
  /** Plain strings, not `CategoryOption` objects. */
  cities: string[];
  countries: CategoryOption[];
  /** Plain strings, not `CategoryOption` objects. */
  treatments: string[];
  demo_scenarios: DemoScenarioInfo[];
}

export interface DemoScenarioInfo {
  key: string;
  title: string;
  description: string;
  expectation: string;
  is_demo_data: boolean;
}

export interface DisclaimerResponse {
  main: string;
  tool_notice: string;
  dataset_notice: string;
  privacy_notice: string;
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  environment: string;
  demo_mode: boolean;
  auth_enabled: boolean;
  database: string;
  ai_provider: string;
  ai_provider_ready: boolean;
  ai_provider_is_real: boolean;
  ai_fallback_enabled: boolean;
  benchmark_records: number;
  benchmark_label: string;
  max_upload_size_mb: number;
  raw_file_retention_minutes: number;
  server_time: string;
}

export interface ExtractionMetaOut {
  provider: string;
  is_real_provider: boolean;
  method: string;
  ocr_used: boolean;
  text_length: number;
  low_confidence_items: number;
  warnings: string[];
  duration_ms: number;
}

export interface BillItemOut {
  id: string;
  position: number;
  description: string;
  category: string;
  service_name: string | null;
  quantity: number;
  unit_price: number;
  total_price: number;
  confidence: number;
  is_user_verified: boolean;
  user_edited: boolean;
  needs_confirmation: boolean;
  source: string;
  notes: string | null;
}

export interface BillTotalsOut {
  items_total: number;
  subtotal: number;
  taxes_total: number;
  discounts_total: number;
  insurance_deduction: number;
  grand_total: number;
  stated_grand_total: number | null;
  mismatch_amount: number;
  total_mismatch: boolean;
}

export interface BillOut {
  id: string;
  status: BillStatus;
  source: string;
  is_demo: boolean;
  hospital_name: string | null;
  hospital_location: string | null;
  city: string | null;
  country: string | null;
  hospital_category: string | null;
  treatment: string | null;
  room_category: string | null;
  patient_name: string | null;
  patient_id: string | null;
  bill_number: string | null;
  bill_date: string | null;
  admission_date: string | null;
  discharge_date: string | null;
  length_of_stay_days: number | null;
  diagnosis: string | null;
  subtotal: number | null;
  taxes_total: number | null;
  discounts_total: number | null;
  insurance_deduction: number | null;
  grand_total: number | null;
  stated_grand_total: number | null;
  currency_code: string;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
  items: BillItemOut[];
  totals: BillTotalsOut;
  extraction: ExtractionMetaOut;
  has_analysis: boolean;
}

export interface UploadResponse {
  bill: BillOut;
  next_step: string;
  warnings: string[];
}

export interface ExtractResponse {
  bill: BillOut;
  warnings: string[];
  requires_confirmation: boolean;
}

export interface BillItemInput {
  id?: string | null;
  description: string;
  category: string;
  service_name?: string | null;
  quantity: number;
  unit_price: number;
  total_price?: number | null;
}

export interface BillMetadataInput {
  hospital_name?: string | null;
  hospital_location?: string | null;
  patient_name?: string | null;
  patient_id?: string | null;
  bill_number?: string | null;
  bill_date?: string | null;
  admission_date?: string | null;
  discharge_date?: string | null;
  room_category?: string | null;
  diagnosis?: string | null;
}

/** Comparison context. These fields pick which benchmark records apply. */
export interface BillContextInput {
  city?: string | null;
  country?: string | null;
  hospital_category?: string | null;
  treatment?: string | null;
  room_category?: string | null;
}

export interface UpdateBillItemsRequest {
  items: BillItemInput[];
  metadata?: BillMetadataInput | null;
  context?: BillContextInput | null;
  mark_confirmed?: boolean;
}

export interface ManualBillCreateRequest {
  items: BillItemInput[];
  metadata?: BillMetadataInput | null;
  context?: BillContextInput | null;
}

/**
 * One review-table row sent for a live comparison.
 *
 * `key` is the client's row key; the response echoes it as the comparison `id`
 * so a status stays attached to its row when rows are added or removed.
 */
export interface PreviewItemInput extends BillItemInput {
  key: string;
}

export interface PreviewRequest {
  bill_id?: string | null;
  items: PreviewItemInput[];
  context?: BillContextInput | null;
}

export interface PreviewResponse {
  bill_id: string | null;
  comparisons: ChargeComparisonOut[];
  counts: AnalysisCounts;
  coverage_percent: number;
  headline: string;
  dataset_label: string;
  is_demo_data: boolean;
  notices: string[];
  disclaimer: string;
  context: AnalysisContextOut;
}

export interface ChargeComparisonOut {
  id: string;
  bill_item_id: string | null;
  sort_index: number;
  description: string;
  category: string;
  quantity: number;
  actual_amount: number;
  matched_service_name: string | null;
  match_score: number;
  match_reason: string | null;
  match_scope: string | null;
  benchmark_min: number | null;
  benchmark_median: number | null;
  benchmark_max: number | null;
  benchmark_unit_price_median: number | null;
  benchmark_display: string;
  benchmark_available: boolean;
  difference_from_median: number | null;
  difference_display: string;
  percentage_above_max: number | null;
  percentage_below_min: number | null;
  percentage_difference: number | null;
  flag_status: FlagStatus;
  flag_label: string;
  flag_reason: string | null;
  is_flagged: boolean;
  verification_status: string | null;
  dataset_label: string;
  source_name: string | null;
  source_url: string | null;
  source_date: string | null;
  ai_explanation: string | null;
  ai_explanation_source: string | null;
  ai_questions: string[];
}

export interface AnalysisTotals {
  bill_total: number;
  comparable_subtotal: number;
  benchmark_min_total: number | null;
  benchmark_median_total: number | null;
  benchmark_max_total: number | null;
  difference_min: number | null;
  difference_max: number | null;
  benchmark_display: string;
  difference_display: string;
  coverage_percent: number;
}

export interface AnalysisCounts {
  analyzed: number;
  within_range: number;
  below_range: number;
  review: number;
  above_range: number;
  attention: number;
  insufficient_data: number;
  not_comparable: number;
}

export interface AnalysisContextOut {
  city: string | null;
  country: string | null;
  hospital_category: string | null;
  treatment: string | null;
  room_category: string | null;
}

export interface CategorySpend {
  category: string;
  label: string;
  actual: number;
  benchmark_min: number | null;
  benchmark_max: number | null;
  difference: number | null;
  has_benchmark: boolean;
  percent_of_bill: number;
}

export interface ChargeVsBenchmark {
  charge: string;
  category: string;
  actual: number;
  benchmark_min: number | null;
  benchmark_median: number | null;
  benchmark_max: number | null;
  status: string;
}

export interface ChartData {
  actual_vs_benchmark: ChargeVsBenchmark[];
  category_spend: CategorySpend[];
}

export interface AnalysisOut {
  id: string;
  bill_id: string;
  status: string;
  created_at: string;
  context: AnalysisContextOut;
  totals: AnalysisTotals;
  counts: AnalysisCounts;
  comparisons: ChargeComparisonOut[];
  flagged: ChargeComparisonOut[];
  chart_data: ChartData;
  questions: string[];
  summary: string | null;
  headline: string | null;
  dataset_label: string;
  is_demo_data: boolean;
  provider_name: string;
  provider_is_real: boolean;
  thresholds: Record<string, number>;
  engine_version: string;
  disclaimer: string;
  notices: string[];
}

export interface AnalyzeResponse {
  analysis: AnalysisOut;
  messages: string[];
}

/**
 * Report sections are intentionally loose on the backend: different sections
 * carry different optional blocks (a paragraph, a label/value table, a grid or
 * a bullet list). These types describe the union of blocks the server emits.
 */
export interface ReportField {
  label: string;
  value: string | null;
}

export interface ReportSection {
  key: string;
  title: string;
  text?: string;
  headline?: string;
  fields?: ReportField[];
  columns?: string[];
  rows?: (string | number | null)[][];
  items?: string[];
}

export type ReportFormat = "json" | "html" | "markdown";

export interface ReportResponse {
  bill_id: string;
  generated_at: string;
  anonymized: boolean;
  redaction_applied: Record<string, boolean>;
  title: string;
  sections: ReportSection[];
  disclaimer: string;
  dataset_notice: string;
  ai_notice: string;
  provider_name: string;
  provider_is_real: boolean;
  /** Only populated when `format` is `markdown` or `html`. */
  markdown?: string | null;
  html?: string | null;
  chart_data?: ChartData | null;
}

export interface QuestionsResponse {
  bill_id: string;
  questions: string[];
}

export interface BenchmarkPriceOut {
  id: string;
  service_name: string;
  service_category: string;
  city: string;
  city_tier: string | null;
  country_code: string;
  hospital_category: string | null;
  room_category: string | null;
  treatment: string | null;
  unit: string;
  min_price: number;
  median_price: number;
  max_price: number;
  record_count: number;
  currency_code: string;
  verification_status: string;
  dataset_label: string;
  source_name: string | null;
  source_url: string | null;
  source_date: string | null;
  notes: string | null;
}

export interface BenchmarkListResponse {
  items: BenchmarkPriceOut[];
  total: number;
  limit: number;
  offset: number;
  dataset_label: string;
  is_demo_data: boolean;
  notice: string;
}

export interface DatasetStatsResponse {
  total_records: number;
  demo_records: number;
  verified_records: number;
  dataset_label: string;
  is_demo_data: boolean;
  notice: string;
  min_source_date: string | null;
  max_source_date: string | null;
  cities: string[];
  service_categories: string[];
  hospital_categories: string[];
  sources: string[];
}

export interface DemoScenarioListResponse {
  scenarios: DemoScenarioInfo[];
  dataset_label: string;
  notice: string;
}

export interface SampleBillFile {
  filename: string;
  size_bytes: number;
  format: string;
  scenario: string | null;
}

export interface SampleBillListResponse {
  files: SampleBillFile[];
}

/** The single error shape every 4xx/5xx response uses. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    detail: string | null;
    hint: string | null;
  };
}
