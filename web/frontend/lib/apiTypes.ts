// ============================================================================
// AUTONOMOUS AI-FACTORY v2.1 — API types
// ============================================================================
// The request and response shapes of the factory API. lib/api.ts re-exports
// every name here, so `import { Product } from '@/lib/api'` keeps working.

import type { AgentLogMetricsSlice } from './pipelineStages';
export interface DemoQualityReport {
  score: number;
  grade: string;
  sandbox_ready?: boolean;
  has_index_html?: boolean;
  issues: Array<{ code: string; detail: string }>;
  spec_coverage_pct: number | null;
}

export interface StakeholderBriefTurn {
  role: string;
  display_name: string;
  title: string;
  body: string;
}

export interface StakeholderBrief {
  product_id: string;
  product_name: string;
  format_version: number;
  turns: StakeholderBriefTurn[];
  footer_note?: string;
}

export interface Product {
  id: string;
  name?: string;
  is_template?: boolean;
  idea: string;
  state: string;
  created_at: number;
  category?: string;
  tags?: string[];
  selling_description?: string;
  price_usdt?: number;
  price_tier?: string;
  monetization_scheme?: {
    free_tier?: { available: boolean; limitations: { features: string[]; usage_limits: string; users: string } };
    paid_tiers?: Array<{ name: string; price_usd_monthly: number; features: string[]; target_audience: string }>;
    recommended_tier?: string;
  };
  spec?: any;
  architecture?: any;
  /** Subset of tech stack for list cards (from architecture.tech_stack) */
  implementation_summary?: Record<string, string>;
  /** PM/storefront: marketing_landing | full_software | desktop_app */
  delivery_profile?: string | null;
  product_kind?: string | null;
  desktop_framework?: string | null;
  /** Compact tech stack line for explore cards */
  storefront_stack_label?: string | null;
  code?: any;
  marketing?: any;
  pricing?: any;
  evolution_history?: EvolutionEntry[];
  demo_quality?: DemoQualityReport;
  /** Last QA headless Chromium run (from telemetry); null if not yet run */
  browser_preview_e2e?: Record<string, unknown> | null;
  /** True/False when last QA persisted gates snapshot exists */
  qa_gates_all_passed?: boolean | null;
  /** Storefront card: demo gate score / grade (only listed products pass gates) */
  quality_score?: number;
  quality_grade?: string;
  marketplace_verified?: boolean;
  spec_coverage_pct?: number | null;
  telemetry_qa_gates_passed?: boolean | null;
  marketplace_quality?: {
    eligible?: boolean;
    reasons?: string[];
    rules?: Record<string, unknown>;
  };
  marketplace_listing_fields?: {
    quality_score?: number;
    quality_grade?: string;
    marketplace_verified?: boolean;
    spec_coverage_pct?: number | null;
    telemetry_qa_gates_passed?: boolean | null;
  };
  stakeholder_brief?: StakeholderBrief;
  production_mode?: boolean;
}

export interface EvolutionEntry {
  created_at: number;
  health_score: number;
  improvements: string[];
  auto_fixes: string[];
}

export interface DirectorReport {
  filename: string;
  period: string;
  date: string;
  summary: string;
}

export interface PipelineFailedAlert {
  product_id: string;
  title: string;
  idea?: string;
  updated_at?: number;
  headline?: string;
  cause_plain?: string;
  failure_reason?: string | null;
  failed_agent?: string | null;
}

export interface DashboardData {
  /** True when payload is the fast `?quick=1` path; full fetch clears this. */
  dashboard_partial?: boolean;
  /** Server used a minimal fallback after a metrics build error. */
  dashboard_build_degraded?: boolean;
  pipeline: {
    total_products: number;
    active_products: number;
    completed_products: number;
    /** Listed on public /api/products (code + marketplace quality gates). */
    storefront_visible_products?: number | null;
    failed_products: number;
    pending_tasks: number;
    running_tasks: number;
    timed_out_tasks: number;
    state_distribution?: Record<string, number>;
    /** Recent FAILED products with human-readable cause (dashboard alert banner). */
    failed_alerts?: PipelineFailedAlert[];
  };
  resources: {
    cpu_percent: number;
    memory_percent: number;
    disk_percent: number;
  };
  revenue: {
    last_24h: number;
    last_7d: number;
    last_30d: number;
    total_approx_usd?: number;
    total_usdt?: number;
    total_usdc?: number;
    orders_completed?: number;
    payments_pending?: number;
  };
  security: {
    status: string;
    failed_logins_15min: number;
  };
  agent_metrics?: Record<string, {
    total_entries: number;
    recent_entries: number;
    recent_errors: number;
    last_active: number | null;
    status: string;
    recent_logs?: any[];
  }>;
  director_status?: {
    report_count: number;
    last_report_time: number | null;
    pending_decisions: number;
    status: string;
    benchmark_scorecard?: Record<string, any> | null;
    benchmark_alert_count?: number;
  };
  escalation_summary?: {
    total_all_time: number;
    recent_1h: number;
    by_agent: Record<string, { total: number; retries: number; bypasses: number; escalations: number }>;
    recent_events: any[];
  };
  /** Live Monitor embedded pipeline walkthrough video (SSE + dashboard). */
  demo_replay?: {
    enabled: boolean;
    title?: string;
    play_url?: string | null;
  };
  cost_outcome_heatmap?: {
    name?: string;
    value?: number;
    children?: Array<{ name: string; value?: number; product_id?: string; children?: unknown[] }>;
  };
  factory_floor?: Record<string, unknown>;
  collected_at?: number;
}

export interface DemoReplayAdminConfig {
  enabled: boolean;
  title: string;
  source: string;
  video_url: string | null;
  media_filename: string | null;
  updated_at: number | null;
  play_url: string | null;
}

export interface BenchmarkScorecardPayload {
  scorecard: Record<string, any>;
  alerts: Array<Record<string, any>>;
  status?: Record<string, any>;
  investor_metrics?: {
    rolling_24h_pass_rate: number | null;
    rolling_7d_pass_rate: number | null;
    latest_pass_rate: number | null;
    trend_vs_7d: number;
    confidence_interval_95: { low: number; high: number; n: number };
    production_readiness_index: number;
  };
}

export type CircuitBreakerState = 'closed' | 'open' | 'half_open';

export interface CircuitBreakerRow {
  provider: string;
  state: CircuitBreakerState | string;
  failure_count_window: number;
  failure_threshold: number;
  failure_window_sec: number;
  open_duration_sec: number;
  seconds_until_half_open?: number | null;
  opened_at?: number | null;
  half_open_since?: number | null;
  last_failure_at?: number | null;
  last_success_at?: number | null;
  last_state_change_at?: number | null;
  last_error?: string;
  last_recovery_duration_sec?: number | null;
  total_failures: number;
  total_opens: number;
  total_recoveries: number;
  manual_override?: string | null;
  recent_events?: Array<{ ts: number; event: string; detail?: string }>;
}

export interface CircuitBreakerSnapshot {
  providers: Record<string, CircuitBreakerRow>;
  config?: {
    failure_threshold: number;
    failure_window_sec: number;
    open_duration_sec: number;
  };
  updated_at?: number;
}

export interface ProviderStatus {
  name: string;
  status: string;
  latency_ms: number;
  model: string;
  models?: {
    heavy: string;
    light: string;
  };
  available_models?: string[];
  enabled?: boolean;
  type?: string;
  base_url?: string;
  capabilities?: {
    context_window: number;
    context_window_light?: number;
    max_tokens: number;
    supports_vision: boolean;
    supports_streaming: boolean;
  };
  health_check_endpoint?: string;
  priority?: number;
  is_default?: boolean;
  circuit?: CircuitBreakerRow;
  api_key_configured?: boolean;
  api_key_env?: string | null;
}

export interface RoutingRule {
  task_type: string;
  preferred_provider: string;
  model_role?: string;
  timeout_sec: number;
  fallback_provider?: string | null;
}

/** Admin LLM log cost estimate: blended $/1M tokens when model id has no specific rate */
export interface LlmPricingProviderRow {
  effective_usd_per_mtok: number;
  source: 'override' | 'builtin' | 'default_yaml' | 'default_builtin' | string;
  yaml_override_usd_per_mtok: number | null;
  builtin_usd_per_mtok: number | null;
}

export interface LlmLimitsPanelData {
  limits_saved: {
    max_requests_per_minute: number;
    daily_cost_cap_usd: number;
    monthly_cost_cap_usd: number;
    pre_call_reserve_usd: number;
    critical_escalation_enabled: boolean;
  };
  limits_effective: {
    max_requests_per_minute: number;
    daily_cost_cap_usd: number;
    monthly_cost_cap_usd: number;
    pre_call_reserve_usd: number;
    critical_escalation_enabled: boolean;
  };
  usage: {
    day: string;
    day_spend_usd: number;
    month: string;
    month_spend_usd: number;
    requests_last_minute: number;
  };
  env_overrides: {
    max_requests_per_minute?: boolean;
    daily_cost_cap_usd?: boolean;
    monthly_cost_cap_usd?: boolean;
    pre_call_reserve_usd?: boolean;
    critical_escalation_enabled?: boolean;
  };
}

export interface CreateProviderPayload {
  name: string;
  provider_type?: string;
  base_url?: string;
  api_key?: string | null;
  api_key_env?: string | null;
  enabled?: boolean;
  models?: { heavy?: string; light?: string };
  capabilities?: {
    context_window?: number;
    context_window_light?: number;
    max_tokens?: number;
    supports_vision?: boolean;
    supports_streaming?: boolean;
  };
  priority?: number;
  health_check_endpoint?: string;
  /** Edit-only hint from GET /providers — key is stored server-side, never returned. */
  api_key_configured?: boolean;
}

export interface AgentStatus {
  type: string;
  status: string;
  current_task: string | null;
  uptime: number;
  tasks_completed: number;
  timeout?: number;
  last_active?: number | null;
  log_metrics?: AgentLogMetricsSlice | null;
}

export type { AgentLogMetricsSlice } from './pipelineStages';

export interface PaymentRequest {
  product_id: string;
  chain?: string;
  token?: string;
  /** Partner / UTM referral captured as ?ref= (stored client-side) */
  referral_source?: string;
}

export interface PaymentStatus {
  payment_id: string;
  product_id: string;
  amount: number;
  currency: string;
  chain: string;
  wallet_address: string;
  status: string;
  created_at: number;
  expires_at: number;
  tx_hash?: string;
  confirmed_at?: number;
  confirmations?: number;
  verification?: {
    confirmations: number;
    from: string;
    block_number: number;
  };
  order_id?: string;
  license_key?: string;
}

export interface CustomerProfile {
  id: string;
  email: string;
  plan?: string;
  usage?: { period_ym: string; runs_count: number };
}

export interface FeedbackData {
  product_id: string;
  rating: number;
  comment: string;
  contact_email?: string;
  source?: string;
  page_url?: string;
  journey_step?: string;
  tags?: string[];
  locale?: string;
  session_id?: string;
}

export interface FeedbackResult {
  feedback_id: string;
  status: string;
  classification: string;
  usefulness_score: number;
  routed_to: string;
  message: string;
}

export interface TelemetryEventData {
  product_id: string;
  event_type: string;
  data?: Record<string, unknown>;
  session_id?: string;
  page_url?: string;
  locale?: string;
}

export interface AdminFeedbackSummary {
  window_hours: number;
  count: number;
  by_classification: Record<string, number>;
  top_products: Array<{ product_id: string; count: number; avg_rating: number; bugs: number }>;
  updated_at: number;
}

export interface TelemetryReplaySession {
  session_id: string;
  event_count: number;
  first_ts: number | null;
  last_ts: number | null;
}

export interface ReleaseCockpitPayload {
  product_id: string;
  go_no_go: 'go' | 'no-go';
  checks: Record<string, boolean>;
  issues: string[];
  details: Record<string, any>;
  evaluated_at: number;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in?: number;
  /** JWT role claim: viewer | operator | admin | super_admin */
  role?: string;
  requires_2fa?: boolean;
}

export interface AdminPanelUser {
  id: string;
  username: string;
  role: string;
  enabled: boolean;
  created_at?: number;
}

export interface AdminActionLogEntry {
  id: string;
  ts: number;
  actor_username: string;
  actor_user_id?: string | null;
  actor_type?: string;
  action: string;
  resource: string;
  details?: Record<string, unknown>;
  ip_address?: string;
}

export interface AdminActionLogResponse {
  username?: string;
  user_id?: string;
  entries: AdminActionLogEntry[];
  total_matched: number;
  limit: number;
}

export interface AdminRoleMeta {
  id: string;
  label: string;
  description: string;
}

export interface AdminMeResponse {
  username: string;
  user_id?: string | null;
  is_admin: boolean;
  role: string;
  totp_enabled: boolean;
  totp_pending: boolean;
  webauthn_enabled?: boolean;
  mfa_method?: string | null;
  /** True when unset/blank or still set to the legacy public demo password SandboxDemo!2026 (unsafe on reachable hosts). */
  sandbox_demo_password_uses_default?: boolean;
  /** AIFACTORY_DEMO_READONLY=1 — shared demo host (passwordless admin login). */
  public_demo?: boolean;
  public_demo_readonly?: boolean;
  blocks_factory_backup?: boolean;
  blocks_factory_restore?: boolean;
  blocks_admin_password_change?: boolean;
  blocks_admin_user_management?: boolean;
  blocks_platform_settings_save?: boolean;
}

export interface FactoryRestorePreview {
  restore_token: string;
  restore_mode: string;
  backup: {
    backup_manifest: Record<string, unknown>;
    archive_files: number;
    archive_bytes_uncompressed: number;
  };
  current: {
    products_total: number;
    products_by_state: Record<string, number>;
    has_config_overlay?: boolean;
    has_secrets_dir?: boolean;
    data_total_bytes?: number;
    top_level_dirs?: string[];
  };
  warnings: string[];
}

export interface FactoryBackupOnDiskEntry {
  filename: string;
  relative_path: string;
  size_bytes: number;
  modified_at_utc: string;
}

export interface FactoryBackupSchedule {
  enabled: boolean;
  time: string;
  timezone: string;
  include_sandboxes: boolean;
  retention: number;
  last_date?: string | null;
  last_run_utc?: string | null;
  last_file?: string | null;
  last_error?: string | null;
  on_disk_backups: FactoryBackupOnDiskEntry[];
  public_demo?: boolean;
}

export interface ChatMessage {
  id: string;
  username: string;
  text: string;
  timestamp: string;
  admin_username: string;
  /** owner | director | agent | system — Owner is the human platform owner */
  role?: string;
  agent_type?: string;
  kind?: string;
}

export interface ChatCorporateSettings {
  chat_username: string;
  director_standup_enabled: boolean;
  director_standup_time: string;
  director_standup_timezone: string;
}

/** Present when ``GET /admin/llm/logs`` is called with ``since`` and/or ``until`` (Unix seconds). */
export interface LLMLogsSummary {
  estimated_cost_usd: number;
  calls_with_cost_estimate: number;
  prompt_tokens: number;
  completion_tokens: number;
  tokens_used_sum: number;
  calls_with_prompt_completion_tokens: number;
  matching_in_range: number;
  by_provider: { name: string; value: number }[];
  by_role: { name: string; cost: number }[];
  by_agent: { name: string; cost: number }[];
}
