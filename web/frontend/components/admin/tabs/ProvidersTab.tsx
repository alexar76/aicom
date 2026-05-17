'use client';

import React, { useEffect, useState, useRef, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  LayoutDashboard,
  Cpu,
  Bot,
  Shield,
  FileText,
  BarChart3,
  Settings,
  LogOut,
  Plus,
  Send,
  Activity,
  Users,
  DollarSign,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Sparkles,
  MessageCircle,
  Menu,
  X,
  Trash2,
  Edit3,
  RefreshCw,
  Globe,
  ToggleLeft,
  ToggleRight,
  Save,
  List,
  ScrollText,
  ChevronRight,
  Terminal,
  Radio,
  Pause,
  Play,
  Gauge,
  Circle,
  Star,
  ExternalLink,
  Zap,
  GitBranch,
  Container,
  Layers,
  FlaskConical,
  BrainCircuit,
  ClipboardList,
  Inbox,
  Megaphone,
  Store,
  Loader2,
  Upload,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Modal } from '@/components/ui/Modal';
import {
  FilterControlsPanel,
  FilterNumberInput,
  FilterResetSummary,
  FilterSelect,
} from '@/components/admin/FilterControls';
import BrainstormingTab from '@/components/BrainstormingTab';
import SupportQueueTab from '@/components/SupportQueueTab';
import OutreachTab from '@/components/OutreachTab';
import { QRCodeSVG } from 'qrcode.react';
import api, {
  DashboardData,
  ProviderStatus,
  AgentStatus,
  CreateProviderPayload,
  RoutingRule,
  ChatMessage,
  DemoReplayAdminConfig,
  LlmPricingProviderRow,
} from '@/lib/api';
import { INITIAL_AGENTS_TAB_ROWS, PIPELINE_STAGE_ORDER } from '@/lib/pipelineStages';
import { formatRelativeTime, getStateColor, getStateLabel, getAgentIcon, applyTheme } from '@/lib/utils';
import { AdminLocale, detectAdminLocale, saveAdminLocale, t, tVars } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

import { ProviderFormModal } from './ProviderFormModal';
import { RoutingRulesEditor } from './RoutingRulesEditor';
import { LlmLimitsPanel } from './LlmLimitsPanel';
import { CircuitBreakerPanel } from '../providers/CircuitBreakerPanel';

export function ProvidersTab({ locale }: { locale: AdminLocale }) {
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [llmPricing, setLlmPricing] = useState<Record<string, LlmPricingProviderRow> | null>(null);
  const [pricingDraft, setPricingDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [savingPricing, setSavingPricing] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingProvider, setEditingProvider] = useState<CreateProviderPayload | null>(null);
  const [showRoutingRules, setShowRoutingRules] = useState(false);
  const [settingDefault, setSettingDefault] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; latency_ms: number; model: string; response?: string; error?: string; testing?: boolean }>>({});

  useEffect(() => {
    loadProviders();
  }, []);

  useEffect(() => {
    if (!llmPricing) return;
    const next: Record<string, string> = {};
    for (const [name, row] of Object.entries(llmPricing)) {
      next[name] =
        row.yaml_override_usd_per_mtok != null
          ? String(row.yaml_override_usd_per_mtok)
          : String(row.effective_usd_per_mtok);
    }
    setPricingDraft(next);
  }, [llmPricing]);

  const loadProviders = async () => {
    try {
      const [data, pricingRes] = await Promise.all([
        api.getProviders(),
        api.getLlmPricing().catch(() => null),
      ]);
      setProviders(Array.isArray(data) ? data : []);
      if (pricingRes?.providers) {
        setLlmPricing(pricingRes.providers);
      } else {
        setLlmPricing(null);
      }
    } catch (e) {
      console.error('Failed to load providers:', e);
    }
  };

  const pricingSourceLabel = (source: string) => {
    switch (source) {
      case 'override':
        return 'YAML override';
      case 'builtin':
        return 'Built-in';
      case 'default_yaml':
        return 'Global default (YAML)';
      case 'default_builtin':
        return 'Global default';
      default:
        return source;
    }
  };

  const handleSavePricing = async (providerName: string) => {
    const raw = pricingDraft[providerName];
    const v = parseFloat(String(raw).replace(',', '.'));
    if (Number.isNaN(v) || v < 0) {
      toast.error('Enter a valid non-negative number ($/1M tokens)');
      return;
    }
    setSavingPricing(providerName);
    try {
      await api.putLlmPricingProvider(providerName, v);
      toast.success(`Saved cost estimate for ${providerName}`);
      await loadProviders();
    } catch (e: any) {
      toast.error(e?.message || 'Failed to save pricing');
    } finally {
      setSavingPricing(null);
    }
  };

  const handleClearPricingOverride = async (providerName: string) => {
    setSavingPricing(providerName);
    try {
      await api.deleteLlmPricingProviderOverride(providerName);
      toast.success(`Cleared override for ${providerName}`);
      await loadProviders();
    } catch (e: any) {
      toast.error(e?.message || 'Failed to clear override');
    } finally {
      setSavingPricing(null);
    }
  };

  const handleTest = async (name: string, modelRole: 'heavy' | 'light' = 'heavy') => {
    setTestResults((prev) => ({ ...prev, [name]: { ...prev[name], testing: true } }));
    try {
      const result = await api.testProvider(name, modelRole);
      setTestResults((prev) => ({
        ...prev,
        [name]: { ...result, testing: false },
      }));
    } catch (e: any) {
      setTestResults((prev) => ({
        ...prev,
        [name]: { success: false, latency_ms: 0, model: '', error: e?.message || 'Request failed', testing: false },
      }));
    }
  };

  const handleModelChange = async (providerName: string, role: 'heavy' | 'light', model: string) => {
    setSaving(`${providerName}-${role}`);
    try {
      await api.updateProviderModels(providerName, { [role]: model });
      await loadProviders();
    } catch (e) {
      console.error('Failed to update model:', e);
    } finally {
      setSaving(null);
    }
  };

  const handleSetDefault = async (name: string) => {
    setSettingDefault(name);
    try {
      await api.setDefaultProvider(name);
      await loadProviders();
    } catch (e) {
      console.error('Failed to set default provider:', e);
    } finally {
      setSettingDefault(null);
    }
  };

  const handleToggle = async (name: string, currentEnabled: boolean) => {
    try {
      await api.toggleProvider(name, !currentEnabled);
      await loadProviders();
    } catch (e) {
      console.error('Failed to toggle provider:', e);
    }
  };

  const handleDelete = async (name: string) => {
    if (!window.confirm(`Delete provider "${name}"? This cannot be undone.`)) return;
    try {
      await api.deleteProvider(name);
      await loadProviders();
    } catch (e) {
      console.error('Failed to delete provider:', e);
    }
  };

  const handleEdit = (p: ProviderStatus) => {
    setEditingProvider({
      name: p.name,
      provider_type: p.type || 'openai_compatible',
      base_url: p.base_url || '',
      api_key_env: null,
      enabled: p.enabled ?? true,
      models: { heavy: p.models?.heavy || '', light: p.models?.light || '' },
      capabilities: p.capabilities || undefined,
      priority: p.priority || 10,
      health_check_endpoint: '/v1/models',
    });
    setShowAddModal(true);
  };

  return (
    <motion.div className="space-y-6">
      <CircuitBreakerPanel locale={locale} />
      <LlmLimitsPanel />

      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-xl font-semibold text-white">{t(locale, 'providers.title')}</h2>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:justify-end">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowRoutingRules(!showRoutingRules)}
            className="w-full sm:w-auto"
          >
            <List className="w-4 h-4 mr-1" />
            Routing Rules
          </Button>
          <Button size="sm" onClick={() => { setEditingProvider(null); setShowAddModal(true); }} className="w-full sm:w-auto">
            <Plus className="w-4 h-4 mr-1" />
            Add Provider
          </Button>
        </div>
      </div>

      {/* Provider Cards */}
      <div className="grid md:grid-cols-2 gap-4">
        {providers.map((provider, i) => (
          <motion.div
            key={provider.name}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
          >
            <GlassCard>
              {/* Header with actions */}
              <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex min-w-0 flex-wrap items-center gap-3">
                  <Cpu className="h-5 w-5 shrink-0 text-indigo-400" />
                  <h3 className="text-white font-medium">{provider.name}</h3>
                  {provider.circuit && (
                    <span
                      className={`h-2.5 w-2.5 rounded-full shrink-0 ${
                        provider.circuit.state === 'open'
                          ? 'bg-rose-500'
                          : provider.circuit.state === 'half_open'
                            ? 'bg-amber-400 animate-pulse'
                            : 'bg-emerald-500'
                      }`}
                      title={`Circuit: ${provider.circuit.state}`}
                    />
                  )}
                  {provider.is_default && (
                    <span className="text-xs text-amber-400 font-medium bg-amber-500/10 px-2 py-0.5 rounded-full border border-amber-500/20">
                      ⭐ Default
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center justify-end gap-1 sm:gap-2">
                  <button
                    onClick={() => handleTest(provider.name, 'heavy')}
                    disabled={testResults[provider.name]?.testing}
                    className="p-1.5 rounded-lg hover:bg-indigo-500/20 transition-colors text-gray-400 hover:text-indigo-400"
                    title="Test heavy model"
                  >
                    {testResults[provider.name]?.testing ? (
                      <span className="text-xs animate-pulse">...</span>
                    ) : (
                      <FlaskConical className="w-4 h-4" />
                    )}
                  </button>
                  <button
                    onClick={() => handleEdit(provider)}
                    className="p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-400 hover:text-white"
                    title="Edit provider"
                  >
                    <Edit3 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleToggle(provider.name, provider.enabled ?? true)}
                    className="p-1.5 rounded-lg hover:bg-white/10 transition-colors"
                    title={provider.enabled ? 'Disable' : 'Enable'}
                  >
                    {provider.enabled ? (
                      <ToggleRight className="w-4 h-4 text-green-400" />
                    ) : (
                      <ToggleLeft className="w-4 h-4 text-gray-500" />
                    )}
                  </button>
                  <button
                    onClick={() => handleDelete(provider.name)}
                    className="p-1.5 rounded-lg hover:bg-red-500/20 transition-colors text-gray-400 hover:text-red-400"
                    title="Delete provider"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                  {!provider.is_default && (
                    <button
                      onClick={() => handleSetDefault(provider.name)}
                      disabled={settingDefault === provider.name}
                      className="p-1.5 rounded-lg hover:bg-amber-500/20 transition-colors text-gray-400 hover:text-amber-400"
                      title="Set as default provider"
                    >
                      {settingDefault === provider.name ? (
                        <span className="text-xs animate-pulse">...</span>
                      ) : (
                        <Star className="w-4 h-4" />
                      )}
                    </button>
                  )}
                  <Badge
                    variant={
                      provider.status === 'online'
                        ? 'success'
                        : provider.status === 'degraded'
                        ? 'warning'
                        : 'error'
                    }
                  >
                    {provider.enabled === false ? 'disabled' : provider.status}
                  </Badge>
                </div>
              </div>

              {/* Test result display */}
              {testResults[provider.name] && !testResults[provider.name]?.testing && (
                <div className={`mt-3 p-3 rounded-lg text-xs ${
                  testResults[provider.name]?.success
                    ? 'bg-green-500/10 border border-green-500/20'
                    : 'bg-red-500/10 border border-red-500/20'
                }`}>
                  {testResults[provider.name]?.success ? (
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-3 h-3 text-green-400" />
                        <span className="text-green-400 font-medium">OK</span>
                        <span className="text-gray-500">—</span>
                        <span className="text-gray-400">{testResults[provider.name]?.model}</span>
                        <span className="text-gray-500">·</span>
                        <span className="text-gray-400">{testResults[provider.name]?.latency_ms}ms</span>
                      </div>
                      <div className="text-gray-400 ml-5">
                        "{testResults[provider.name]?.response}"
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-3 h-3 text-red-400" />
                      <span className="text-red-400 font-medium">Failed</span>
                      <span className="text-gray-500">—</span>
                      <span className="text-gray-400">{testResults[provider.name]?.error || 'Unknown error'}</span>
                    </div>
                  )}
                </div>
              )}

              {/* Provider details */}
              <div className="space-y-2 text-sm">
                {provider.base_url && (
                  <div className="flex items-center gap-2 text-gray-500">
                    <Globe className="w-3 h-3" />
                    <span className="truncate">{provider.base_url}</span>
                  </div>
                )}

                <div className="flex items-center gap-2 text-gray-500">
                  <span className="text-xs">Latency:</span>
                  <span className="text-gray-400">
                    {provider.latency_ms > 0 ? `${provider.latency_ms}ms` : 'N/A'}
                  </span>
                </div>

                {llmPricing?.[provider.name] && (
                  <div className="rounded-lg border border-white/10 bg-white/[0.03] p-2 space-y-2">
                    <div className="flex items-center gap-2 text-gray-400 text-xs">
                      <DollarSign className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      <span>
                        Log cost estimate (blended $/1M tok){' '}
                        <span className="text-gray-500">
                          · {pricingSourceLabel(llmPricing[provider.name].source)}
                        </span>
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        type="text"
                        inputMode="decimal"
                        className="w-24 bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-indigo-500"
                        value={pricingDraft[provider.name] ?? ''}
                        onChange={(e) =>
                          setPricingDraft((prev) => ({ ...prev, [provider.name]: e.target.value }))
                        }
                        disabled={savingPricing === provider.name}
                        title="Stored in data/config/llm_pricing.yaml (provider fallback when model id is unknown)"
                      />
                      <Button
                        variant="secondary"
                        size="sm"
                        className="!py-1 !px-2 !text-xs"
                        disabled={savingPricing === provider.name}
                        onClick={() => handleSavePricing(provider.name)}
                      >
                        {savingPricing === provider.name ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <>
                            <Save className="w-3 h-3 mr-1" />
                            Save
                          </>
                        )}
                      </Button>
                      {llmPricing[provider.name].yaml_override_usd_per_mtok != null && (
                        <button
                          type="button"
                          className="text-xs text-amber-400/90 hover:text-amber-300 underline-offset-2 hover:underline disabled:opacity-50"
                          disabled={savingPricing === provider.name}
                          onClick={() => handleClearPricingOverride(provider.name)}
                        >
                          Clear override
                        </button>
                      )}
                    </div>
                    {llmPricing[provider.name].builtin_usd_per_mtok != null && (
                      <p className="text-[10px] text-gray-500 leading-snug">
                        Built-in default for this provider id:{' '}
                        {llmPricing[provider.name].builtin_usd_per_mtok}. Model-specific rates in YAML
                        still override this for known model ids.
                      </p>
                    )}
                  </div>
                )}

                {/* Heavy model selector */}
                {provider.available_models && provider.available_models.length > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-500 text-xs w-14 shrink-0">Heavy:</span>
                    <select
                      className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-indigo-500"
                      value={provider.models?.heavy || provider.model || ''}
                      onChange={(e) => handleModelChange(provider.name, 'heavy', e.target.value)}
                      disabled={saving?.startsWith(provider.name)}
                    >
                      {provider.available_models.map((m) => (
                        <option key={m} value={m} className="bg-gray-900">{m}</option>
                      ))}
                    </select>
                    {saving === `${provider.name}-heavy` && (
                      <span className="text-xs text-indigo-400 animate-pulse">...</span>
                    )}
                  </div>
                )}

                {/* Light model selector */}
                {provider.available_models && provider.available_models.length > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-500 text-xs w-14 shrink-0">Light:</span>
                    <select
                      className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-indigo-500"
                      value={provider.models?.light || provider.model || ''}
                      onChange={(e) => handleModelChange(provider.name, 'light', e.target.value)}
                      disabled={saving?.startsWith(provider.name)}
                    >
                      {provider.available_models.map((m) => (
                        <option key={m} value={m} className="bg-gray-900">{m}</option>
                      ))}
                    </select>
                    {saving === `${provider.name}-light` && (
                      <span className="text-xs text-indigo-400 animate-pulse">...</span>
                    )}
                  </div>
                )}

                {/* Fallback */}
                {(!provider.available_models || provider.available_models.length === 0) && (
                  <div className="text-gray-500 text-xs">
                    Heavy: {provider.models?.heavy || '-'} | Light: {provider.models?.light || '-'}
                  </div>
                )}
              </div>
            </GlassCard>
          </motion.div>
        ))}
      </div>

      {/* Routing Rules Section */}
      {showRoutingRules && (
        <GlassCard className="p-4">
          <RoutingRulesEditor providers={providers} />
        </GlassCard>
      )}

      {/* Add/Edit Provider Modal */}
      <ProviderFormModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        initial={editingProvider}
        onSaved={loadProviders}
      />
    </motion.div>
  );
}
