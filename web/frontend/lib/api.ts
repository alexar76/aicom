// ============================================================================
// AUTONOMOUS AI-FACTORY v2.1 — API Client Library
// ============================================================================

import { buildAgentsTabRows, type AgentLogMetricsSlice } from './pipelineStages';

const API_BASE = '/api';

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

function readCsrfCookie(): string | null {
  if (typeof document === 'undefined') return null;
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : null;
}

/** Admin UI routes that require a valid JWT (includes /sandbox/*). */
function isAdminSessionEndpoint(endpoint: string): boolean {
  return endpoint.startsWith('/admin') || endpoint.startsWith('/sandbox');
}

function clearAdminSessionAndRedirectToLogin(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem('admin_token');
  const onAdminUi =
    window.location.pathname.startsWith('/admin') &&
    !window.location.pathname.startsWith('/admin/login');
  if (onAdminUi) {
    window.location.href = '/admin/login';
  }
}

/** Thrown by {@link ApiClient.request} so UI can map status + message to recovery steps. */
export class ApiRequestError extends Error {
  readonly status: number;
  readonly endpoint: string;
  readonly detailPayload?: Record<string, unknown>;

  constructor(
    message: string,
    opts: { status: number; endpoint: string; detailPayload?: Record<string, unknown> },
  ) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = opts.status;
    this.endpoint = opts.endpoint;
    this.detailPayload = opts.detailPayload;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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
  };
  limits_effective: {
    max_requests_per_minute: number;
    daily_cost_cap_usd: number;
    monthly_cost_cap_usd: number;
    pre_call_reserve_usd: number;
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

export interface AdminRoleMeta {
  id: string;
  label: string;
  description: string;
}

export interface AdminMeResponse {
  username: string;
  is_admin: boolean;
  role: string;
  totp_enabled: boolean;
  totp_pending: boolean;
  webauthn_enabled?: boolean;
  mfa_method?: string | null;
  /** True when unset/blank or still set to the legacy public demo password SandboxDemo!2026 (unsafe on reachable hosts). */
  sandbox_demo_password_uses_default?: boolean;
  /** AIFACTORY_DEMO_READONLY=1 — shared demo host (e.g. admin/demo123). */
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

// ---------------------------------------------------------------------------
// API Client
// ---------------------------------------------------------------------------

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit & { clientTimeoutMs?: number; publicStorefront?: boolean } = {}
  ): Promise<T> {
    const { clientTimeoutMs, publicStorefront, ...fetchInit } = options;
    // Storefront sandbox must not send a stale admin_token from a prior Admin session.
    const adminToken =
      publicStorefront || typeof window === 'undefined'
        ? null
        : localStorage.getItem('admin_token');
    const customerToken =
      publicStorefront || typeof window === 'undefined'
        ? null
        : localStorage.getItem('customer_token');
    
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(fetchInit.headers as Record<string, string>),
    };

    const isAdminApi = endpoint.startsWith('/admin');
    if (adminToken) {
      headers['Authorization'] = `Bearer ${adminToken}`;
    } else if (customerToken && !isAdminApi) {
      headers['Authorization'] = `Bearer ${customerToken}`;
    }

    const method = (fetchInit.method || 'GET').toUpperCase();
    if (
      UNSAFE_METHODS.has(method) &&
      (endpoint.startsWith('/admin') ||
        endpoint.startsWith('/customer') ||
        endpoint.startsWith('/support'))
    ) {
      const csrf = readCsrfCookie();
      if (csrf) {
        headers['X-CSRF-Token'] = csrf;
      }
    }

    const signal =
      fetchInit.signal !== undefined
        ? fetchInit.signal
        : clientTimeoutMs && clientTimeoutMs > 0
          ? AbortSignal.timeout(clientTimeoutMs)
          : undefined;

    const doFetch = (hdrs: Record<string, string>) =>
      fetch(`${this.baseUrl}${endpoint}`, {
        ...fetchInit,
        headers: hdrs,
        credentials: 'include',
        ...(signal ? { signal } : {}),
      });

    let response: Response;
    try {
      response = await doFetch(headers);
      // Stale Bearer in localStorage can block a valid HttpOnly admin cookie.
      if (
        response.status === 401 &&
        adminToken &&
        isAdminSessionEndpoint(endpoint) &&
        typeof window !== 'undefined'
      ) {
        const { Authorization: _drop, ...cookieOnly } = headers;
        response = await doFetch(cookieOnly);
        if (response.ok) {
          localStorage.removeItem('admin_token');
        }
      }
    } catch (e: unknown) {
      const m = e instanceof Error ? e.message : String(e);
      throw new ApiRequestError(m || 'Network error: could not reach the API', {
        status: 0,
        endpoint,
      });
    }

    if (!response.ok) {
      if (response.status === 401 && typeof window !== 'undefined') {
        if (isAdminSessionEndpoint(endpoint)) {
          localStorage.removeItem('admin_token');
          clearAdminSessionAndRedirectToLogin();
        }
        if (customerToken && !adminToken) {
          localStorage.removeItem('customer_token');
          localStorage.removeItem('customer_email');
        }
      }
      const error = (await response.json().catch(() => ({}))) as { detail?: unknown };
      let detail = error.detail;
      let detailPayload: Record<string, unknown> | undefined;
      if (Array.isArray(detail)) {
        detail = detail
          .map((d: unknown) =>
            typeof d === 'object' && d !== null && 'msg' in d
              ? String((d as { msg?: string }).msg)
              : JSON.stringify(d),
          )
          .join('; ');
      } else if (detail !== null && detail !== undefined && typeof detail === 'object') {
        detailPayload = detail as Record<string, unknown>;
        detail =
          typeof detailPayload.message === 'string'
            ? detailPayload.message
            : JSON.stringify(detailPayload);
      }
      const msg =
        typeof detail === 'string' && detail.trim()
          ? detail.trim()
          : `HTTP ${response.status}${response.statusText ? ` ${response.statusText}` : ''}`.trim();
      throw new ApiRequestError(msg, { status: response.status, endpoint, detailPayload });
    }

    return response.json();
  }

  // ── Products ────────────────────────────────────────────────────────────

  async getProducts(category?: string): Promise<Product[]> {
    // Backend returns { products: [...], count: N }, unwrap to array
    const query = category ? `?category=${encodeURIComponent(category)}` : '';
    const result = await this.request<{ products: Product[] }>(`/products${query}`);
    return result.products || [];
  }

  async getProduct(id: string): Promise<Product> {
    return this.request(`/products/${id}`);
  }

  async getCategories(): Promise<{
    categories: { id: string; name: string; icon: string; description: string; product_count: number }[];
    totalCount: number;
  }> {
    const result = await this.request<{
      categories: any[];
      total_count?: number;
    }>('/products/categories');
    const categories = result.categories || [];
    const fromApi = result.total_count;
    const totalCount =
      typeof fromApi === 'number'
        ? fromApi
        : categories.reduce((s, c) => s + (c.product_count || 0), 0);
    return { categories, totalCount };
  }

  // ── Payment ─────────────────────────────────────────────────────────────

  async createPayment(data: PaymentRequest): Promise<PaymentStatus> {
    return this.request('/payment/create', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // ── Customer Commerce ────────────────────────────────────────────────────

  async registerCustomer(email: string, password: string): Promise<{ customer: CustomerProfile; access_token: string; token_type: string }> {
    return this.request('/customer/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  }

  async loginCustomer(email: string, password: string): Promise<{ customer: CustomerProfile; access_token: string; token_type: string }> {
    return this.request('/customer/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  }

  async getCustomerMe(): Promise<CustomerProfile> {
    return this.request('/customer/me');
  }

  async createCustomerPipelineRun(idea: string): Promise<{ product_id: string; state: string; plan: string }> {
    return this.request('/customer/pipeline/run', {
      method: 'POST',
      body: JSON.stringify({ idea }),
    });
  }

  async getCustomerOrders(): Promise<{ orders: any[]; count: number }> {
    return this.request('/customer/orders');
  }

  async getMyReferralDashboard(): Promise<{
    referral_code: string;
    conversions: number;
    attributed_revenue: number;
    share_link: string;
  }> {
    return this.request('/customer/referrals/me');
  }

  async createStripeCheckoutSession(targetPlan: 'maker' | 'studio' | 'enterprise'): Promise<{
    session_id: string;
    checkout_url: string;
    amount_total: number;
    currency: string;
    target_plan: string;
  }> {
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    return this.request('/customer/billing/stripe/checkout', {
      method: 'POST',
      body: JSON.stringify({
        target_plan: targetPlan,
        success_url: `${origin}/account?billing=success`,
        cancel_url: `${origin}/account?billing=cancel`,
      }),
    });
  }

  async getPaymentStatus(paymentId: string): Promise<PaymentStatus> {
    return this.request(`/payment/status/${paymentId}`);
  }

  async confirmPayment(
    paymentId: string,
    txHash: string,
    opts?: { testConfirmations?: number },
  ): Promise<PaymentStatus> {
    const q =
      opts?.testConfirmations !== undefined
        ? `?test_confirmations=${encodeURIComponent(String(opts.testConfirmations))}`
        : '';
    return this.request(`/payment/confirm/${paymentId}${q}`, {
      method: 'POST',
      body: JSON.stringify({ tx_hash: txHash }),
    });
  }

  async getSupportedChains(): Promise<any[]> {
    return this.request('/payment/chains');
  }

  // ── Feedback ────────────────────────────────────────────────────────────

  async submitFeedback(data: FeedbackData): Promise<FeedbackResult> {
    return this.request('/feedback/submit', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getProductFeedback(productId: string): Promise<any> {
    return this.request(`/feedback/product/${productId}`);
  }

  async recordTelemetryEvent(body: TelemetryEventData): Promise<{ ok: boolean }> {
    return this.request('/telemetry/event', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async getAdminFeedbackSummary(windowHours: number = 168): Promise<AdminFeedbackSummary> {
    return this.request(`/admin/feedback/summary?window_hours=${windowHours}`);
  }

  async getTelemetryReplaySessions(productId: string): Promise<{ product_id: string; count: number; sessions: TelemetryReplaySession[] }> {
    return this.request(`/admin/telemetry/replay/${encodeURIComponent(productId)}`);
  }

  async getTelemetryReplayTimeline(
    productId: string,
    sessionId: string
  ): Promise<{ product_id: string; session_id: string; count: number; events: Array<{ timestamp: number; event_type: string; data: Record<string, unknown> }> }> {
    return this.request(`/admin/telemetry/replay/${encodeURIComponent(productId)}/${encodeURIComponent(sessionId)}`);
  }

  async getReleaseCockpit(productId: string): Promise<ReleaseCockpitPayload> {
    return this.request(`/admin/release/cockpit/${encodeURIComponent(productId)}`);
  }

  async executeReleaseProtocol(productId: string): Promise<{ product_id: string; executed: boolean; missing: string[] }> {
    return this.request(`/admin/release/protocol/${encodeURIComponent(productId)}/execute`, {
      method: 'POST',
    });
  }

  // ── Admin Auth ──────────────────────────────────────────────────────────

  async login(
    username: string,
    password: string,
    totpCode?: string,
    webauthnCredential?: Record<string, unknown>
  ): Promise<LoginResponse> {
    const body: Record<string, unknown> = {
      username: (username || 'admin').trim(),
      password,
    };
    if (totpCode) body.totp_code = totpCode;
    if (webauthnCredential) body.webauthn_credential = webauthnCredential;
    return this.request('/admin/auth/login', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async oidcStatus(): Promise<{ enabled: boolean; issuer: string | null }> {
    return this.request('/admin/auth/oidc/status');
  }

  async webauthnLoginOptions(username: string): Promise<{ publicKey: Record<string, unknown> }> {
    return this.request('/admin/auth/webauthn/login/options', {
      method: 'POST',
      body: JSON.stringify({ username: (username || 'admin').trim() }),
    });
  }

  async webauthnRegisterOptions(): Promise<{ publicKey: Record<string, unknown> }> {
    return this.request('/admin/auth/webauthn/register/options', { method: 'POST' });
  }

  async webauthnRegisterVerify(
    credential: Record<string, unknown>,
    label = 'Passkey'
  ): Promise<{ message: string; credential_id?: string }> {
    return this.request('/admin/auth/webauthn/register/verify', {
      method: 'POST',
      body: JSON.stringify({ credential, label }),
    });
  }

  async disableWebAuthn(password: string): Promise<{ message: string }> {
    return this.request('/admin/auth/webauthn/disable', {
      method: 'POST',
      body: JSON.stringify({ password }),
    });
  }

  async listAdminUsers(): Promise<{ users: AdminPanelUser[] }> {
    return this.request('/admin/users');
  }

  async getAdminRolesMeta(): Promise<{ roles: AdminRoleMeta[] }> {
    return this.request('/admin/users/roles/meta');
  }

  async createAdminUser(payload: {
    username: string;
    password: string;
    role: string;
  }): Promise<AdminPanelUser & { password_hash?: never }> {
    return this.request('/admin/users', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async patchAdminUser(
    userId: string,
    patch: { role?: string; enabled?: boolean }
  ): Promise<Record<string, unknown>> {
    return this.request(`/admin/users/${encodeURIComponent(userId)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
  }

  async deleteAdminUser(userId: string): Promise<{ ok: boolean }> {
    return this.request(`/admin/users/${encodeURIComponent(userId)}`, {
      method: 'DELETE',
    });
  }

  async resetAdminUserPassword(userId: string, newPassword: string): Promise<{ ok: boolean; username?: string }> {
    return this.request(`/admin/users/${encodeURIComponent(userId)}/password`, {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword }),
    });
  }

  async logout(): Promise<void> {
    return this.request('/admin/auth/logout', { method: 'POST' });
  }

  async getMe(): Promise<AdminMeResponse> {
    return this.request('/admin/auth/me');
  }

  async setup2FA(password: string): Promise<{ secret: string; uri: string; message: string }> {
    return this.request('/admin/auth/setup-2fa', {
      method: 'POST',
      body: JSON.stringify({ password }),
    });
  }

  async verify2FA(code: string): Promise<{ message: string }> {
    return this.request('/admin/auth/verify-2fa', {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
  }

  async cancel2FASetup(): Promise<{ message: string }> {
    return this.request('/admin/auth/cancel-2fa-setup', { method: 'POST' });
  }

  async disable2FA(password: string): Promise<{ message: string }> {
    return this.request('/admin/auth/disable-2fa', {
      method: 'POST',
      body: JSON.stringify({ password }),
    });
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<any> {
    return this.request(`/admin/auth/change-password?old_password=${encodeURIComponent(currentPassword)}&new_password=${encodeURIComponent(newPassword)}`, {
      method: 'POST',
    });
  }

  // ── Admin Dashboard ─────────────────────────────────────────────────────

  async getDashboard(quick?: boolean): Promise<DashboardData> {
    const suffix = quick === true ? '?quick=1' : '';
    const clientTimeoutMs = quick === true ? 20_000 : 120_000;
    return this.request(`/admin/dashboard${suffix}`, { clientTimeoutMs });
  }

  async getDemoReplayAdmin(): Promise<DemoReplayAdminConfig> {
    return this.request('/admin/demo-replay');
  }

  async patchDemoReplay(patch: Record<string, unknown>): Promise<DemoReplayAdminConfig> {
    return this.request('/admin/demo-replay', {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
  }

  async uploadDemoReplayVideo(file: File): Promise<DemoReplayAdminConfig> {
    const adminToken = typeof window !== 'undefined' ? localStorage.getItem('admin_token') : null;
    const headers: Record<string, string> = {};
    if (adminToken) headers.Authorization = `Bearer ${adminToken}`;
    const fd = new FormData();
    fd.append('file', file);
    const response = await fetch(`${this.baseUrl}/admin/demo-replay/upload`, {
      method: 'POST',
      headers,
      body: fd,
      credentials: 'include',
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(
        typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail) || `HTTP ${response.status}`
      );
    }
    return response.json();
  }

  // ── Wow demo features ───────────────────────────────────────────────────

  async getReplayTimeline(productId: string): Promise<any> {
    return this.request(`/admin/wow/pipeline/products/${encodeURIComponent(productId)}/replay-timeline`);
  }

  async forkReplayFrom(
    productId: string,
    body: { frame_index: number; operator_notes?: string; model_override?: string },
  ): Promise<any> {
    return this.request(`/admin/wow/pipeline/products/${encodeURIComponent(productId)}/replay-fork`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async enqueueProductShowcase(productId: string, baseUrl?: string): Promise<any> {
    return this.request('/admin/wow/showcase/enqueue', {
      method: 'POST',
      body: JSON.stringify({ product_id: productId, base_url: baseUrl }),
    });
  }

  async getShowcaseGallery(): Promise<{ entries: any[]; count: number }> {
    return this.request('/admin/wow/showcase/gallery');
  }

  async getProductShowcaseStatus(productId: string): Promise<{
    product_id: string;
    status: string;
    queued_at?: number;
    completed_at?: number;
    error?: string;
    base_url?: string;
  }> {
    return this.request(`/admin/wow/showcase/status/${encodeURIComponent(productId)}`);
  }

  async analyzePromptFailures(): Promise<{ proposals: any[]; count: number }> {
    return this.request('/admin/wow/prompts/analyze', { method: 'POST' });
  }

  async getPromptProposals(): Promise<{ proposals: any[]; count: number }> {
    return this.request('/admin/wow/prompts/proposals');
  }

  async applyPromptProposal(proposalId: string): Promise<any> {
    return this.request('/admin/wow/prompts/apply', {
      method: 'POST',
      body: JSON.stringify({ proposal_id: proposalId }),
    });
  }

  async getProviders(): Promise<ProviderStatus[]> {
    const result = await this.request<{ providers: Record<string, any> }>('/admin/providers');
    const providers = result.providers || {};
    return Object.entries(providers).map(([name, config]) => ({
      name,
      status: config.status || (config.enabled ? 'online' : 'disabled'),
      latency_ms: config.latency_ms || 0,
      model: config.models?.heavy || config.models?.light || 'unknown',
      models: config.models || {},
      available_models: config.available_models || [],
      enabled: config.enabled ?? true,
      is_default: config.is_default ?? false,
      type: config.type,
      base_url: config.base_url,
      priority: config.priority,
      circuit: config.circuit,
      api_key_configured: config.api_key_configured ?? false,
      api_key_env: config.api_key_env ?? null,
      capabilities: config.capabilities,
      health_check_endpoint: config.health_check_endpoint,
    }));
  }

  async getProviderCircuits(): Promise<CircuitBreakerSnapshot> {
    return this.request<CircuitBreakerSnapshot>('/admin/providers/circuits');
  }

  async circuitForceOpen(providerName: string): Promise<{ status: string; circuit: CircuitBreakerRow }> {
    return this.request(`/admin/providers/${encodeURIComponent(providerName)}/circuit/open`, {
      method: 'POST',
    });
  }

  async circuitForceClose(providerName: string): Promise<{ status: string; circuit: CircuitBreakerRow }> {
    return this.request(`/admin/providers/${encodeURIComponent(providerName)}/circuit/close`, {
      method: 'POST',
    });
  }

  async circuitReset(providerName: string): Promise<{ status: string; circuit: CircuitBreakerRow }> {
    return this.request(`/admin/providers/${encodeURIComponent(providerName)}/circuit/reset`, {
      method: 'POST',
    });
  }

  async updateProviderModels(providerName: string, models: { heavy?: string; light?: string }): Promise<any> {
    return this.request(`/admin/providers/${providerName}`, {
      method: 'PATCH',
      body: JSON.stringify(models),
    });
  }

  // ── Provider CRUD ────────────────────────────────────────────────────────

  async createProvider(data: CreateProviderPayload): Promise<any> {
    return this.request('/admin/providers', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateProvider(providerName: string, data: Partial<CreateProviderPayload>): Promise<any> {
    return this.request(`/admin/providers/${providerName}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteProvider(providerName: string): Promise<any> {
    return this.request(`/admin/providers/${providerName}`, {
      method: 'DELETE',
    });
  }

  async setDefaultProvider(providerName: string): Promise<any> {
    return this.request(`/admin/providers/${providerName}/set-default`, {
      method: 'POST',
    });
  }

  async testProvider(providerName: string, modelRole: 'heavy' | 'light' = 'heavy', prompt?: string): Promise<{
    success: boolean;
    latency_ms: number;
    model: string;
    response?: string;
    error?: string;
    status_code?: number;
  }> {
    return this.request(`/admin/providers/${providerName}/test`, {
      method: 'POST',
      body: JSON.stringify({ model_role: modelRole, prompt }),
    });
  }

  async toggleProvider(providerName: string, enabled?: boolean): Promise<any> {
    return this.request(`/admin/providers/${providerName}/toggle`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    });
  }

  // ── Routing Rules ────────────────────────────────────────────────────────

  async getRoutingRules(): Promise<RoutingRule[]> {
    const result = await this.request<{ routing_rules: RoutingRule[] }>('/admin/providers/routing-rules');
    return result.routing_rules || [];
  }

  async updateRoutingRules(rules: RoutingRule[]): Promise<any> {
    return this.request('/admin/providers/routing-rules', {
      method: 'PUT',
      body: JSON.stringify({ routing_rules: rules }),
    });
  }

  /** Per-provider cost estimate overrides (writes ``data/config/llm_pricing.yaml``). */
  async getLlmPricing(): Promise<{ providers: Record<string, LlmPricingProviderRow> }> {
    return this.request('/admin/llm-pricing');
  }

  async putLlmPricingProvider(providerName: string, usdPerMtok: number): Promise<{ ok: boolean }> {
    return this.request(`/admin/llm-pricing/providers/${encodeURIComponent(providerName)}`, {
      method: 'PUT',
      body: JSON.stringify({ usd_per_mtok: usdPerMtok }),
    });
  }

  async deleteLlmPricingProviderOverride(providerName: string): Promise<{ ok: boolean; cleared?: boolean }> {
    return this.request(`/admin/llm-pricing/providers/${encodeURIComponent(providerName)}`, {
      method: 'DELETE',
    });
  }

  async getLlmLimits(): Promise<LlmLimitsPanelData> {
    return this.request('/admin/llm-limits');
  }

  async updateLlmLimits(payload: LlmLimitsPanelData['limits_saved']): Promise<LlmLimitsPanelData> {
    return this.request('/admin/llm-limits', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  }

  async getAgents(): Promise<AgentStatus[]> {
    // Backend returns { agents: {...} } (object), convert to array
    const result = await this.request<{ agents: Record<string, any> }>('/admin/agents');
    const agents = result.agents || {};
    const rows = Object.entries(agents).map(([type, info]) => {
      const lm = info?.log_metrics as Record<string, unknown> | undefined;
      const log_metrics =
        lm && typeof lm === 'object'
          ? {
              total_entries: Number(lm.total_entries) || 0,
              recent_entries: Number(lm.recent_entries) || 0,
              recent_errors: Number(lm.recent_errors) || 0,
              last_active: Number(lm.last_active) || 0,
              status: String(lm.status || 'idle'),
            }
          : null;
      return {
        type,
        status: info.status || 'idle',
        current_task: info.current_task ?? null,
        uptime: info.uptime || 0,
        tasks_completed: info.tasks_completed || 0,
        timeout: typeof info.timeout === 'number' ? info.timeout : undefined,
        last_active: info.last_active != null ? Number(info.last_active) : null,
        log_metrics,
      };
    });
    return buildAgentsTabRows(rows) as AgentStatus[];
  }

  async getSecurityLogs(
    limit: number = 500,
    since?: number,
    until?: number
  ): Promise<{ logs: any[]; count: number; total: number }> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (since != null) params.set('since', String(since));
    if (until != null) params.set('until', String(until));
    return this.request(`/admin/security/logs?${params}`);
  }

  async getAgentHandoffs(
    limit: number = 200,
    since?: number,
    until?: number,
    productId?: string
  ): Promise<{ handoffs: any[]; count: number; total: number }> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (since != null) params.set('since', String(since));
    if (until != null) params.set('until', String(until));
    if (productId) params.set('product_id', productId);
    return this.request(`/admin/agent/handoffs?${params}`);
  }

  async getDirectorReports(): Promise<DirectorReport[]> {
    // Backend returns { reports: [...] }, unwrap to array
    const result = await this.request<{ reports: any[] }>('/admin/director/reports');
    return result.reports || [];
  }

  async getPipelineProducts(
    limit: number = 60,
    offset: number = 0,
    sort: 'newest' | 'shipped_first' = 'newest',
    /** Fast path: skip heavy per-row disk hydration (Pipeline Monitor). */
    light: boolean = false,
    /** Per-request abort timeout (ms). Pipeline catalog uses 300s — see pipelineCatalogFetch.ts. */
    clientTimeoutMs: number = 300_000,
  ): Promise<{
    products: any[];
    count: number;
    total: number;
    offset: number;
    limit: number;
    catalog_summary?: {
      total_products: number;
      shipped_products: number;
      failed_products: number;
      storefront_listable_products: number | null;
      light?: boolean;
      sort: string;
      sort_note?: string;
    };
  }> {
    const q = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
      sort,
    });
    if (light) {
      q.set('light', '1');
    }
    // Large catalog hydration can exceed default proxy/browser patience; allow long waits.
    return this.request(`/admin/pipeline/products?${q.toString()}`, { clientTimeoutMs });
  }

  /** Manual storefront follow-up label (files under state/product_followup/). */
  async updatePipelineProductFollowup(
    productId: string,
    body: {
      followup?: 'planned' | 'not_pursuing' | null;
      planned_notes?: string;
      not_pursuing_reason?: string;
      improvement_on_hold?: boolean;
    }
  ): Promise<{
    product_id: string;
    storefront_followup: Record<string, unknown>;
    storefront_visible?: boolean;
    storefront_gate_reasons?: string[];
  }> {
    return this.request(`/admin/pipeline/products/${encodeURIComponent(productId)}/followup`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  async updatePipelineStorefrontAdmin(
    productId: string,
    body: {
      quality_score?: number;
      admin_force_list?: boolean;
      admin_force_list_note?: string;
      clear_force_list?: boolean;
      admin_hide_from_storefront?: boolean;
      clear_hide_from_storefront?: boolean;
    }
  ): Promise<{
    product_id: string;
    storefront_followup: Record<string, unknown>;
    storefront_visible?: boolean;
    storefront_gate_reasons?: string[];
  }> {
    return this.request(`/admin/pipeline/products/${encodeURIComponent(productId)}/storefront-admin`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  /** Persist storefront listing copy (marketing_content.json → marketing). */
  async patchPipelineMarketplaceCopy(
    productId: string,
    body: {
      product_name?: string;
      tagline?: string;
      short_description?: string;
      selling_description?: string;
      long_description?: string;
    }
  ): Promise<{
    product_id: string;
    storefront_marketing_copy: Record<string, unknown>;
    storefront_visible?: boolean;
    storefront_gate_reasons?: string[];
  }> {
    return this.request(`/admin/pipeline/products/${encodeURIComponent(productId)}/marketplace-copy`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  /** Manual storefront / checkout USDT (sales_config.json → sales_data.pricing.admin_storefront_usdt). */
  async patchPipelineStorefrontPricing(
    productId: string,
    body: { admin_storefront_usdt?: number; clear_admin_storefront_usdt?: boolean }
  ): Promise<{
    product_id: string;
    storefront_pricing: { admin_storefront_usdt?: number | null; storefront_checkout_usdt: number };
    storefront_visible?: boolean;
    storefront_gate_reasons?: string[];
  }> {
    return this.request(`/admin/pipeline/products/${encodeURIComponent(productId)}/storefront-pricing`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  async postPipelineHumanRework(
    productId: string,
    notes: string
  ): Promise<{ product_id: string; ok: boolean; task_id?: string; repair_round?: number }> {
    return this.request(`/admin/pipeline/products/${encodeURIComponent(productId)}/human-rework`, {
      method: 'POST',
      body: JSON.stringify({ notes }),
    });
  }

  async postPipelineReopenFailed(
    productId: string,
    notes: string,
    opts?: { agent_type?: string; target_state?: string }
  ): Promise<{
    product_id: string;
    ok: boolean;
    task_id?: string;
    product_state?: string;
    agent_type?: string;
    target_state?: string;
    cancelled_tasks?: number;
    failed_reopen_count?: number;
  }> {
    return this.request(
      `/admin/pipeline/products/${encodeURIComponent(productId)}/reopen-failed`,
      {
        method: 'POST',
        body: JSON.stringify({
          notes,
          agent_type: opts?.agent_type,
          target_state: opts?.target_state,
        }),
      },
    );
  }

  async postPipelineHumanReviewApprove(
    productId: string,
    body?: { note?: string }
  ): Promise<{
    product_id: string;
    ok: boolean;
    task_id?: string;
    state?: string;
    message?: string;
    already_approved?: boolean;
    storefront_force_list?: boolean;
    storefront_followup?: Record<string, unknown>;
  }> {
    return this.request(`/admin/pipeline/products/${encodeURIComponent(productId)}/human-review/approve`, {
      method: 'POST',
      body: JSON.stringify(body ?? {}),
    });
  }

  async postPipelineHumanReviewReject(
    productId: string,
    notes: string
  ): Promise<{ product_id: string; ok: boolean; task_id?: string; repair_round?: number; state?: string }> {
    return this.request(`/admin/pipeline/products/${encodeURIComponent(productId)}/human-review/reject`, {
      method: 'POST',
      body: JSON.stringify({ notes }),
    });
  }

  async getDirectorReport(filename: string): Promise<{ filename: string; content: string }> {
    return this.request(`/admin/director/report/${filename}`);
  }

  // ── Config ──────────────────────────────────────────────────────────────

  async getTheme(): Promise<{ theme: any; active_theme: string }> {
    // Backend returns { theme: {...}, active_theme: "cyberpunk" }
    const result = await this.request<{ theme: any; active_theme: string }>('/config/theme');
    return result;
  }

  async setTheme(theme: string): Promise<any> {
    return this.request('/admin/config/theme', {
      method: 'POST',
      body: JSON.stringify({ theme }),
    });
  }

  // ── Product Specs ───────────────────────────────────────────────────────

  async getProductSpec(productId: string): Promise<{ product_id: string; spec: any }> {
    return this.request(`/admin/products/${productId}/spec`);
  }

  async getProductArchitecture(productId: string): Promise<{ product_id: string; architecture: any }> {
    return this.request(`/admin/products/${encodeURIComponent(productId)}/architecture`);
  }

  // ── Iteration hub (templates, canvas, patterns, prefill, Web Push) ─────

  async listIterationUserTemplates(): Promise<{ templates: any[] }> {
    return this.request('/admin/iteration-hub/user-templates');
  }

  async upsertIterationUserTemplate(body: {
    id?: string;
    name: string;
    delivery_profile: string;
    production_mode: boolean;
    instructions: string;
  }): Promise<{ template: any }> {
    return this.request('/admin/iteration-hub/user-templates', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async deleteIterationUserTemplate(templateId: string): Promise<{ ok: boolean }> {
    return this.request(`/admin/iteration-hub/user-templates/${encodeURIComponent(templateId)}`, {
      method: 'DELETE',
    });
  }

  async listIterationPatterns(): Promise<{ patterns: any[] }> {
    return this.request('/admin/iteration-hub/patterns');
  }

  async upsertIterationPattern(body: {
    id?: string;
    name: string;
    tags: string[];
    document: Record<string, unknown>;
  }): Promise<{ pattern: any }> {
    return this.request('/admin/iteration-hub/patterns', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async deleteIterationPattern(patternId: string): Promise<{ ok: boolean }> {
    return this.request(`/admin/iteration-hub/patterns/${encodeURIComponent(patternId)}`, {
      method: 'DELETE',
    });
  }

  async getIterationCanvas(productId: string): Promise<{ version: number; nodes: any[]; edges: any[] }> {
    return this.request(`/admin/iteration-hub/products/${encodeURIComponent(productId)}/iteration-canvas`);
  }

  async putIterationCanvas(
    productId: string,
    body: { version: number; nodes: any[]; edges: any[] },
  ): Promise<{ version: number; nodes: any[]; edges: any[] }> {
    return this.request(`/admin/iteration-hub/products/${encodeURIComponent(productId)}/iteration-canvas`, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  }

  async prefillProductFromIdea(body: { idea: string; consent: boolean }): Promise<{
    delivery_profile: string;
    production_mode: boolean;
    instructions: string;
    source: string;
    rationale?: string;
  }> {
    return this.request('/admin/iteration-hub/prefill-from-idea', {
      method: 'POST',
      body: JSON.stringify(body),
      clientTimeoutMs: 45000,
    });
  }

  async getWebPushVapidPublic(): Promise<{ publicKey: string }> {
    return this.request('/admin/iteration-hub/web-push/vapid-public');
  }

  async subscribeWebPush(body: {
    endpoint: string;
    keys: { p256dh: string; auth: string };
    userAgent?: string;
  }): Promise<{ ok: boolean; subscription: any }> {
    return this.request('/admin/iteration-hub/web-push/subscribe', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async sendWebPushTest(body?: { title?: string; body?: string; url?: string }): Promise<{
    ok: boolean;
    sent?: number;
    failed?: number;
    removed?: number;
    error?: string;
  }> {
    return this.request('/admin/iteration-hub/web-push/test', {
      method: 'POST',
      body: JSON.stringify(body || {}),
    });
  }

  /** Inputs visible to the Developer agent (spec, arch, admin, analyst brief) + material quality summary. */
  async getDeveloperHandoff(productId: string): Promise<{
    product_id: string;
    idea: string;
    category: string;
    tags: string[];
    admin_instructions: string;
    delivery_profile: string | null;
    delivery_mode: string;
    analyst_brief_for_developer: string;
    specification: Record<string, unknown> | null;
    architecture: Record<string, unknown> | null;
    material_summary: {
      quality_band: 'ok' | 'thin' | 'weak';
      warnings: string[];
      stats: Record<string, number>;
    };
  }> {
    return this.request(`/admin/products/${productId}/developer-handoff`);
  }

  // ── Security Reports ───────────────────────────────────────────────────

  async getSecurityReport(productId: string): Promise<{ product_id: string; report: any }> {
    return this.request(`/admin/products/${productId}/security-report`);
  }

  async getFactoryBackupSchedule(): Promise<FactoryBackupSchedule> {
    return this.request('/admin/factory-backup/schedule');
  }

  async updateFactoryBackupSchedule(
    patch: Partial<
      Pick<
        FactoryBackupSchedule,
        'enabled' | 'time' | 'timezone' | 'include_sandboxes' | 'retention'
      >
    >
  ): Promise<FactoryBackupSchedule> {
    return this.request('/admin/factory-backup/schedule', {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
  }

  /** Upload backup ZIP → preview warnings (admin+, not on public demo). */
  async previewFactoryRestore(file: File): Promise<FactoryRestorePreview> {
    const token = typeof window !== 'undefined' ? localStorage.getItem('admin_token') : null;
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${this.baseUrl}/admin/factory-backup/preview`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: 'include',
      body: form,
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const body = (await res.json()) as { detail?: unknown };
        if (typeof body.detail === 'string') msg = body.detail;
      } catch {
        /* ignore */
      }
      if (res.status === 401 && typeof window !== 'undefined' && token) {
        clearAdminSessionAndRedirectToLogin();
      }
      throw new Error(msg);
    }
    return res.json() as Promise<FactoryRestorePreview>;
  }

  /** Execute full snapshot restore from preview token (admin+, not on public demo). */
  async executeFactoryRestore(
    restoreToken: string,
    confirms: {
      confirm_replace_all: boolean;
      confirm_trusted_backup: boolean;
      confirm_saved_current_backup: boolean;
    },
  ): Promise<{
    ok: boolean;
    message: string;
    restart_recommended?: boolean;
    pre_restore_backup_file?: string | null;
  }> {
    const token = typeof window !== 'undefined' ? localStorage.getItem('admin_token') : null;
    const form = new FormData();
    form.append('restore_token', restoreToken);
    form.append('confirm_replace_all', confirms.confirm_replace_all ? 'true' : 'false');
    form.append('confirm_trusted_backup', confirms.confirm_trusted_backup ? 'true' : 'false');
    form.append(
      'confirm_saved_current_backup',
      confirms.confirm_saved_current_backup ? 'true' : 'false',
    );
    const res = await fetch(`${this.baseUrl}/admin/factory-backup/restore`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: 'include',
      body: form,
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const body = (await res.json()) as { detail?: unknown };
        if (typeof body.detail === 'string') msg = body.detail;
      } catch {
        /* ignore */
      }
      if (res.status === 401 && typeof window !== 'undefined' && token) {
        clearAdminSessionAndRedirectToLogin();
      }
      throw new Error(msg);
    }
    return res.json();
  }

  /** Full factory data volume ZIP (admin+). Settings → Factory backup. */
  async downloadFactoryBackupZip(includeSandboxes = false): Promise<void> {
    const { parseContentDispositionFilename, saveBlobAsDownload } = await import(
      './browserDownload'
    );
    const token = typeof window !== 'undefined' ? localStorage.getItem('admin_token') : null;
    const qs = includeSandboxes ? '?include_sandboxes=true' : '';
    const suggestedName = 'aicom-factory-backup.zip';

    type SaveHandle = { createWritable: () => Promise<{ write: (b: Blob) => Promise<void>; close: () => Promise<void> }> };
    let saveHandle: SaveHandle | null = null;
    if (typeof window !== 'undefined' && 'showSaveFilePicker' in window) {
      try {
        const w = window as unknown as {
          showSaveFilePicker: (opts: {
            suggestedName: string;
            types: { description: string; accept: Record<string, string[]> }[];
          }) => Promise<SaveHandle>;
        };
        saveHandle = await w.showSaveFilePicker({
          suggestedName,
          types: [{ description: 'ZIP archive', accept: { 'application/zip': ['.zip'] } }],
        });
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return;
      }
    }

    const res = await fetch(`${this.baseUrl}/admin/factory-backup.zip${qs}`, {
      method: 'GET',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: 'include',
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const body = (await res.json()) as { detail?: unknown };
        const d = body?.detail;
        if (typeof d === 'string' && d.trim()) msg = d.trim();
        else if (d != null && typeof d !== 'string') msg = JSON.stringify(d);
      } catch {
        /* ignore */
      }
      if (res.status === 401 && typeof window !== 'undefined' && token) {
        clearAdminSessionAndRedirectToLogin();
      }
      throw new Error(msg);
    }
    const blob = await res.blob();
    const filename = parseContentDispositionFilename(
      res.headers.get('Content-Disposition'),
      suggestedName
    );
    if (saveHandle) {
      if (!blob.size) {
        throw new Error(
          'Download is empty (0 bytes). The server may have timed out while building the archive.'
        );
      }
      const writable = await saveHandle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    }
    await saveBlobAsDownload(blob, filename, { offerSavePicker: false });
  }

  /** Factory owner: ZIP of on-disk artifacts for one product (Admin → Files tree + EXPORT_MANIFEST.json). Operator+. */
  async downloadAdminProductOwnerZip(productId: string): Promise<void> {
    const { parseContentDispositionFilename, saveBlobAsDownload } = await import(
      './browserDownload'
    );
    const token = typeof window !== 'undefined' ? localStorage.getItem('admin_token') : null;
    const suggestedName = `aicom-product-${productId.replace(/[^\w.-]+/g, '_')}.zip`;

    type SaveHandle = { createWritable: () => Promise<{ write: (b: Blob) => Promise<void>; close: () => Promise<void> }> };
    let saveHandle: SaveHandle | null = null;
    if (typeof window !== 'undefined' && 'showSaveFilePicker' in window) {
      try {
        const w = window as unknown as {
          showSaveFilePicker: (opts: {
            suggestedName: string;
            types: { description: string; accept: Record<string, string[]> }[];
          }) => Promise<SaveHandle>;
        };
        saveHandle = await w.showSaveFilePicker({
          suggestedName,
          types: [{ description: 'ZIP archive', accept: { 'application/zip': ['.zip'] } }],
        });
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return;
      }
    }

    const res = await fetch(
      `${this.baseUrl}/admin/products/${encodeURIComponent(productId)}/owner-export.zip`,
      {
        method: 'GET',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: 'include',
      },
    );
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const body = (await res.json()) as { detail?: unknown };
        const d = body?.detail;
        if (typeof d === 'string' && d.trim()) msg = d.trim();
        else if (d != null && typeof d !== 'string') msg = JSON.stringify(d);
      } catch {
        /* ignore */
      }
      if (res.status === 401 && typeof window !== 'undefined' && token) {
        clearAdminSessionAndRedirectToLogin();
      }
      throw new Error(msg);
    }
    const blob = await res.blob();
    const filename = parseContentDispositionFilename(
      res.headers.get('Content-Disposition'),
      suggestedName
    );
    if (saveHandle) {
      if (!blob.size) {
        throw new Error('Download is empty (0 bytes).');
      }
      const writable = await saveHandle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    }
    await saveBlobAsDownload(blob, filename, { offerSavePicker: false });
  }

  /** Public security report — no auth required, for product detail page */
  async getPublicSecurityReport(productId: string): Promise<{ product_id: string; report: any }> {
    return this.request(`/products/${productId}/security-report`);
  }

  // ── LLM Call Logs ───────────────────────────────────────────────────────

  async getLLMLogs(
    limit: number = 200,
    provider?: string,
    since?: number,
    until?: number,
    offset: number = 0,
    clientTimeoutMs: number = 120_000,
  ): Promise<{
    logs: any[];
    count: number;
    total: number;
    summary?: LLMLogsSummary | null;
    offset?: number;
    limit?: number;
  }> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (provider) params.set('provider', provider);
    if (since != null && Number.isFinite(since)) params.set('since', String(since));
    if (until != null && Number.isFinite(until)) params.set('until', String(until));
    return this.request(`/admin/llm/logs?${params}`, { clientTimeoutMs });
  }

  // ── Sandbox & Git ───────────────────────────────────────────────────────

  async startSandbox(
    productId: string,
    opts?: { fromStorefront?: boolean },
  ): Promise<{
    sandbox_id: string;
    status: string;
    url: string;
    expires_at: number;
    preview_tier?: 'full' | 'degraded';
    startup_phase?: string;
    startup_warning?: string | null;
    degraded_badge?: boolean;
    degraded_reasons?: string[];
    preview_api?: { enabled: boolean; proxy_prefix: string | null; status: string | null };
    compose_preview?: { enabled: boolean; proxy_prefix: string | null; status: string | null };
  }> {
    if (opts?.fromStorefront) {
      return this.request(`/sandbox/storefront/start/${productId}`, {
        method: 'POST',
        publicStorefront: true,
      });
    }
    return this.request(`/sandbox/start/${productId}`, { method: 'POST' });
  }

  async sandboxReady(
    sandboxId: string,
  ): Promise<{
    ready: boolean;
    progress: number;
    stage: string;
    preview_path?: string;
    preview_tier?: string;
    startup_phase?: string;
    startup_warning?: string | null;
    degraded_badge?: boolean;
    degraded_reasons?: string[];
  }> {
    return this.request(`/sandbox/ready/${sandboxId}`, { publicStorefront: true });
  }

  async stopSandbox(sandboxId: string): Promise<{ status: string }> {
    return this.request(`/sandbox/stop/${sandboxId}`, { method: 'POST' });
  }

  async sandboxStatus(sandboxId: string): Promise<any> {
    return this.request(`/sandbox/status/${sandboxId}`);
  }

  async listActiveSandboxes(): Promise<{ active_sandboxes: number; sandboxes: any[] }> {
    return this.request('/sandbox/active');
  }

  async gitInit(productId: string, remoteUrl?: string): Promise<any> {
    const params = remoteUrl ? `?remote_url=${encodeURIComponent(remoteUrl)}` : '';
    return this.request(`/sandbox/git/init/${productId}${params}`, { method: 'POST' });
  }

  async gitPush(productId: string, remote: string = 'origin', branch: string = 'main'): Promise<any> {
    return this.request(`/sandbox/git/push/${productId}?remote=${remote}&branch=${branch}`, { method: 'POST' });
  }

  async gitStatus(productId: string): Promise<any> {
    return this.request(`/sandbox/git/status/${productId}`);
  }

  async listSandboxableProducts(): Promise<{ products: any[]; count: number }> {
    return this.request('/sandbox/products');
  }

  // ── Agent Logs ──────────────────────────────────────────────────────────

  async getAgentLogs(
    agent?: string,
    limit: number = 200,
    since?: number,
    until?: number
  ): Promise<{ logs: any[]; count: number; total: number }> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (agent) params.set('agent', agent);
    if (since != null) params.set('since', String(since));
    if (until != null) params.set('until', String(until));
    return this.request(`/admin/agent/logs?${params}`);
  }

  async getDirectorAnalysis(): Promise<{ reports: any[]; report_count: number }> {
    return this.request('/admin/director/analysis');
  }

  async getDiscoveryIdeas(limit: number = 20): Promise<{
    generated_at: number | null;
    signals_total: number;
    signals_collected_now: number;
    signal_pruning?: { before: number; after: number; removed: number };
    anomaly?: Record<string, unknown> | null;
    ranked_ideas: any[];
    count: number;
  }> {
    return this.request(`/admin/discovery/ideas?limit=${limit}`);
  }

  async runDiscovery(createProduct: boolean = false, topK: number = 8): Promise<any> {
    return this.request('/admin/discovery/run', {
      method: 'POST',
      body: JSON.stringify({ create_product: createProduct, top_k: topK }),
    });
  }

  async getBenchmarkScorecard(): Promise<BenchmarkScorecardPayload> {
    return this.request('/admin/benchmark/scorecard');
  }

  async triggerBenchmarkLeague(): Promise<{ message: string; status: string }> {
    return this.request('/admin/benchmark/trigger', { method: 'POST' });
  }

  async renameCatalogProductsNow(): Promise<{
    status: string;
    renamed_count: number;
    products: Array<{
      product_id: string;
      name: string;
      is_template: boolean;
      spec_updated: boolean;
      marketing_updated: boolean;
    }>;
  }> {
    return this.request('/admin/products/rename-now', { method: 'POST' });
  }

  async remediateCatalogComplianceNow(): Promise<{
    status: string;
    processed: number;
    rerouted: number;
    state_persisted: boolean;
    products: Array<Record<string, unknown>>;
  }> {
    return this.request('/admin/compliance/remediate-now', { method: 'POST' });
  }

  async createAdminProduct(payload: {
    idea: string;
    admin_instructions?: string;
    production_mode?: boolean;
    delivery_profile?: string;
    category?: string;
    interface_locale?: string;
    content_locale?: string;
  }): Promise<{ product_id: string; state: string; message: string }> {
    return this.request('/admin/products/create', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async createProductsBatch(payload: {
    ideas: string[];
    mode?: 'continue_on_error' | 'fail_fast';
    max_immediate_start?: number;
    active_limit?: number;
    admin_instructions?: string;
    delivery_profile?: string;
    production_mode?: boolean;
    interface_locale?: string;
    content_locale?: string;
  }): Promise<any> {
    return this.request('/admin/products/create-batch', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getBatchStatus(batchId: string): Promise<any> {
    return this.request(`/admin/products/batch/${encodeURIComponent(batchId)}`);
  }

  async retryBatchFailed(batchId: string): Promise<any> {
    return this.request(`/admin/products/batch/${encodeURIComponent(batchId)}/retry-failed`, {
      method: 'POST',
    });
  }

  // ── Settings ─────────────────────────────────────────────────────────────

  async getAdminSettings(): Promise<{
    factory_on_hold?: boolean;
    auto_pipeline: boolean;
    auto_pipeline_interval_minutes: number;
    local_high_throughput_enabled: boolean;
    git_remote_url: string;
    git_default_branch: string;
    docker_registry: string;
    docker_username: string;
    docker_password: string;
    telegram_notify_enabled: boolean;
    telegram_chat_id: string;
    telegram_notify_pipeline_stages: boolean;
    telegram_notify_new_products: boolean;
    telegram_bot_token_configured: boolean;
    auto_publish_enabled: boolean;
    auto_publish_provider: string;
    auto_publish_netlify_site_id: string;
    auto_publish_cf_project_name: string;
    public_site_url: string;
    site_badge_enabled: boolean;
    site_badge_link_url: string;
    published_site_head_html: string;
    railway_deploy_enabled: boolean;
    railway_project_id: string;
    railway_environment: string;
    railway_environment_id: string;
    railway_service_id: string;
    railway_token_configured: boolean;
    reference_templates_enabled: boolean;
    reference_templates_dir: string;
    reference_template_mode: string;
    reference_template_id: string;
    reference_prompt_max_chars: number;
    reference_templates_catalog?: Array<{
      id: string;
      title: string;
      path: string;
      files?: string[];
    }>;
    throughput_effective?: {
      local_high_throughput_enabled: boolean;
      effective_max_running_tasks: number;
      effective_task_executor_concurrency: number;
      effective_batch_pipeline_max_start_per_cycle: number;
      effective_batch_pipeline_active_limit: number;
      effective_llm_max_parallel_requests: number;
      effective_llm_min_interval_sec: number;
      effective_llm_max_requests_per_minute?: number;
      effective_llm_daily_cost_cap_usd?: number;
      effective_llm_monthly_cost_cap_usd?: number;
      effective_llm_pre_call_reserve_usd?: number;
    } | null;
    quality?: Record<string, boolean | number>;
    pipeline_db_backend?: 'sqlite' | 'postgres' | 'json';
    pipeline_database_url?: string;
    pipeline_database_url_masked?: string;
    pipeline_db_status?: Record<string, unknown>;
    disk_monitor_live?: Record<string, unknown> | null;
  }> {
    return this.request('/admin/settings');
  }

  async testPipelineDatabaseConnection(database_url?: string): Promise<{ ok: boolean; detail: string }> {
    return this.request('/admin/pipeline-database/test-connection', {
      method: 'POST',
      body: JSON.stringify({ database_url: database_url || '' }),
    });
  }

  async migratePipelineSqliteToPostgres(body: {
    database_url?: string;
    clear_target?: boolean;
  }): Promise<{
    ok: boolean;
    products_migrated: number;
    tasks_migrated: number;
    destination: string;
  }> {
    return this.request('/admin/pipeline-database/migrate-sqlite-to-postgres', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async updateAdminSettings(settings: Record<string, any>): Promise<{ message: string; updated: string[] }> {
    return this.request('/admin/settings', {
      method: 'POST',
      body: JSON.stringify(settings),
    });
  }

  async upsertReferenceTemplate(payload: {
    template_id: string;
    title?: string;
    files: Array<{ path: string; content: string }>;
  }): Promise<{
    ok: boolean;
    template_id: string;
    manifest_template_count: number;
    catalog: Array<{ id: string; title: string; path: string; files?: string[] }>;
  }> {
    return this.request('/admin/reference-templates', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async deleteReferenceTemplate(templateId: string): Promise<{
    ok: boolean;
    catalog: Array<{ id: string; title: string; path: string; files?: string[] }>;
  }> {
    return this.request(`/admin/reference-templates/${encodeURIComponent(templateId)}`, {
      method: 'DELETE',
    });
  }

  async testTelegramNotification(): Promise<{ ok: boolean; detail: string }> {
    return this.request('/admin/settings/test-telegram', { method: 'POST' });
  }

  // ── Corporate Chat ────────────────────────────────────────────────────────

  async getChatMessages(): Promise<{ messages: ChatMessage[] }> {
    return this.request('/admin/chat/messages');
  }

  async sendChatMessage(text: string): Promise<{ message: ChatMessage }> {
    return this.request('/admin/chat/messages', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  }

  async deleteChatMessage(messageId: string): Promise<{ success: boolean }> {
    return this.request(`/admin/chat/messages/${messageId}`, {
      method: 'DELETE',
    });
  }

  async getChatSettings(): Promise<ChatCorporateSettings> {
    return this.request('/admin/chat/settings');
  }

  async updateChatSettings(data: Partial<ChatCorporateSettings>): Promise<ChatCorporateSettings> {
    return this.request('/admin/chat/settings', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /** Manual Director standup in Corporate Chat (does not affect daily schedule counter). */
  async runDirectorStandup(): Promise<{ success?: boolean; closure?: string }> {
    return this.request('/admin/chat/standup/run', { method: 'POST' });
  }

  async triggerDirectorAnalysis(): Promise<{ message: string; status: string }> {
    return this.request('/admin/director/trigger', { method: 'POST' });
  }

  // ── Director Decisions ──────────────────────────────────────────────────

  async getDirectorDecisions(): Promise<{ pending: any[]; applied: any[]; all: any[]; pending_count: number; total_count: number }> {
    return this.request('/admin/director/decisions');
  }

  async approveDecision(decisionId: string): Promise<{ status: string; decision: any }> {
    return this.request(`/admin/director/decisions/${decisionId}/approve`, { method: 'POST' });
  }

  async rejectDecision(decisionId: string): Promise<{ status: string; decision: any }> {
    return this.request(`/admin/director/decisions/${decisionId}/reject`, { method: 'POST' });
  }

  // ── Escalations ─────────────────────────────────────────────────────────

  async getEscalations(limit: number = 50): Promise<{ escalations: any[]; count: number; total: number }> {
    return this.request(`/admin/escalations?limit=${limit}`);
  }

  // ── Metrics History ─────────────────────────────────────────────────────

  async getMetricsHistory(limit: number = 100): Promise<{ metrics: any[]; count: number; total: number }> {
    return this.request(`/admin/metrics/history?limit=${limit}`);
  }

  // ── Discussion Sessions ─────────────────────────────────────────────────

  async getDiscussionSessions(params?: string): Promise<{ sessions: any[]; total_count: number }> {
    return this.request(`/admin/discussions/sessions${params ? `?${params}` : ''}`);
  }

  async getDiscussionSession(sessionId: string): Promise<{ session: any }> {
    return this.request(`/admin/discussions/sessions/${sessionId}`);
  }

  async createDiscussionSession(data: {
    topic: string;
    session_type: string;
    participants: string[];
    product_id?: string;
    additional_instructions?: string;
  }): Promise<{ session: any }> {
    return this.request('/admin/discussions/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateDiscussionSession(sessionId: string, data: any): Promise<{ session: any }> {
    return this.request(`/admin/discussions/sessions/${sessionId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteDiscussionSession(sessionId: string): Promise<{ success: boolean }> {
    return this.request(`/admin/discussions/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  }

  async startDiscussionSession(sessionId: string): Promise<{ session: any }> {
    return this.request(`/admin/discussions/sessions/${sessionId}/start`, {
      method: 'POST',
    });
  }

  async runDiscussionRound(sessionId: string): Promise<{ session: any }> {
    return this.request(`/admin/discussions/sessions/${sessionId}/run-round`, {
      method: 'POST',
    });
  }

  async pauseDiscussionSession(sessionId: string): Promise<{ session: any }> {
    return this.request(`/admin/discussions/sessions/${sessionId}/pause`, {
      method: 'POST',
    });
  }

  async resumeDiscussionSession(sessionId: string): Promise<{ session: any }> {
    return this.request(`/admin/discussions/sessions/${sessionId}/resume`, {
      method: 'POST',
    });
  }

  async concludeDiscussionSession(sessionId: string): Promise<{ session: any }> {
    return this.request(`/admin/discussions/sessions/${sessionId}/conclude`, {
      method: 'POST',
    });
  }

  async getDiscussionMessages(sessionId: string, limit: number = 200): Promise<{ messages: any[]; total_count: number }> {
    return this.request(`/admin/discussions/sessions/${sessionId}/messages?limit=${limit}`);
  }

  async sendDiscussionMessage(sessionId: string, text: string): Promise<{ message: any }> {
    return this.request(`/admin/discussions/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  }

  async deleteDiscussionMessage(sessionId: string, messageId: string): Promise<{ success: boolean }> {
    return this.request(`/admin/discussions/sessions/${sessionId}/messages/${messageId}`, {
      method: 'DELETE',
    });
  }

  async getDiscussionIdeas(sessionId: string): Promise<{ idea: any }[]> {
    return this.request(`/admin/discussions/sessions/${sessionId}/ideas`);
  }

  async extractDiscussionIdeas(sessionId: string): Promise<{ idea: any }[]> {
    return this.request(`/admin/discussions/sessions/${sessionId}/extract-ideas`, {
      method: 'POST',
    });
  }

  async promoteIdeaToProduct(sessionId: string, ideaId: string): Promise<{ success: boolean; product_id: string }> {
    return this.request(`/admin/discussions/sessions/${sessionId}/ideas/${ideaId}/promote`, {
      method: 'POST',
    });
  }

  async getDiscussionStats(): Promise<{
    total_sessions: number;
    active_sessions: number;
    completed_sessions: number;
    total_messages: number;
    total_ideas: number;
    sessions_by_type: Record<string, number>;
  }> {
    return this.request('/admin/discussions/stats');
  }

  async getAvailableAgents(): Promise<{
    agent_type: string;
    display_name: string;
    description: string;
    icon: string;
    color: string;
    is_available: boolean;
  }[]> {
    return this.request('/admin/discussions/agents');
  }

  // ── Public support (storefront) ─────────────────────────────────────────

  async getSupportStatus(): Promise<{
    enabled: boolean;
    require_token: boolean;
    bot_name: string;
    bot_slug: string;
  }> {
    return this.request('/support/status');
  }

  async createSupportSession(
    productId?: string,
    uiContext?: {
      current_page?: string;
      active_tab?: string;
      selected_product_id?: string;
      preferred_locale?: string;
    }
  ): Promise<{
    session_id: string;
    access_token: string;
    product_id: string | null;
    bot_name: string;
  }> {
    return this.request('/support/sessions', {
      method: 'POST',
      body: JSON.stringify({
        product_id: productId || null,
        ui_context: uiContext || undefined,
      }),
    });
  }

  async getSupportSession(
    sessionId: string,
    accessToken: string
  ): Promise<{
    session_id: string;
    product_id: string | null;
    messages: Array<{ role: string; content: string; ts?: number; meta?: Record<string, unknown> }>;
    bot_name: string;
  }> {
    return this.request(`/support/sessions/${encodeURIComponent(sessionId)}`, {
      headers: { 'X-AIF-Support-Token': accessToken },
    });
  }

  async sendSupportMessage(
    sessionId: string,
    accessToken: string,
    message: string,
    uiContext?: {
      current_page?: string;
      active_tab?: string;
      selected_product_id?: string;
      preferred_locale?: string;
    }
  ): Promise<{
    reply: string;
    classification: string;
    confidence: number;
    file_pipeline_bug: boolean;
    escalate_to_director: boolean;
    bot_name: string;
  }> {
    return this.request(`/support/sessions/${encodeURIComponent(sessionId)}/message`, {
      method: 'POST',
      headers: { 'X-AIF-Support-Token': accessToken },
      body: JSON.stringify({
        message,
        ui_context: uiContext || undefined,
      }),
    });
  }

  // ── Admin: support escalations (Director queue) ─────────────────────────

  async getSupportEscalations(
    status?: string,
    limit: number = 100
  ): Promise<{ items: any[]; open_count: number }> {
    const q = new URLSearchParams();
    if (status) q.set('status', status);
    q.set('limit', String(limit));
    return this.request(`/admin/support-queue?${q.toString()}`);
  }

  async resolveSupportEscalation(
    escalationId: string,
    notes: string = ''
  ): Promise<{ ok: boolean; id: string }> {
    return this.request(`/admin/support-queue/${encodeURIComponent(escalationId)}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ notes }),
    });
  }

  // ── Admin: outreach (channels + announcements) ──────────────────────────

  async getOutreachChannels(): Promise<{ version: number; channels: any[] }> {
    return this.request('/admin/outreach/channels');
  }

  async putOutreachChannels(body: { version: number; channels: any[] }): Promise<{ ok: boolean }> {
    return this.request('/admin/outreach/channels', {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  }

  async getOutreachAnnouncements(): Promise<{ items: any[] }> {
    return this.request('/admin/outreach/announcements');
  }

  async createOutreachAnnouncement(data: {
    title: string;
    body_markdown: string;
    body_plain?: string | null;
    audience?: string;
    author_role?: string;
    channel_ids?: string[];
  }): Promise<{ announcement: any }> {
    return this.request('/admin/outreach/announcements', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async sendOutreachAnnouncement(id: string): Promise<{ ok: boolean; announcement: any }> {
    return this.request(`/admin/outreach/announcements/${encodeURIComponent(id)}/send`, {
      method: 'POST',
    });
  }

  async suggestOutreachCopy(
    topic: string,
    tone: string = 'professional, concise',
    audience: string = 'customers and visitors'
  ): Promise<{ title: string; body_plain: string }> {
    return this.request('/admin/outreach/announcements/suggest', {
      method: 'POST',
      body: JSON.stringify({ topic, tone, audience }),
    });
  }

  // ── Health ──────────────────────────────────────────────────────────────

  async healthCheck(): Promise<{ status: string; version: string }> {
    return this.request('/health');
  }

  async getPublicBenchmark(): Promise<{
    scorecard: Record<string, any>;
    alerts_count: number;
    investor_metrics_source?:
      | 'benchmark_scorecard'
      | 'pipeline_storefront_proxy'
      | 'pipeline_storefront_proxy_supplement';
    investor_metrics: {
      rolling_24h_pass_rate: number | null;
      rolling_7d_pass_rate: number | null;
      latest_pass_rate: number | null;
      trend_vs_7d: number;
      confidence_interval_95: { low: number; high: number; n: number };
      production_readiness_index: number;
    };
  }> {
    return this.request('/benchmark');
  }
}

export const api = new ApiClient();
export default api;
