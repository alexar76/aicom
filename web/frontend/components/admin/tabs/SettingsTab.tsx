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
  TrainFront,
  Palette,
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
} from '@/lib/api';
import { INITIAL_AGENTS_TAB_ROWS, PIPELINE_STAGE_ORDER } from '@/lib/pipelineStages';
import { formatRelativeTime, getStateColor, getStateLabel, getAgentIcon, applyTheme } from '@/lib/utils';
import { AdminLocale, detectAdminLocale, saveAdminLocale, t, tVars } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

import { DemoReplayMonitorSection } from './DemoReplayMonitorSection';
import {
  DEFAULT_QUALITY_SETTINGS,
  QualitySettingsCollapsible,
  type QualitySettingsState,
} from './QualitySettingsCollapsible';

type AdminThroughputSnapshot = NonNullable<
  Awaited<ReturnType<typeof api.getAdminSettings>>['throughput_effective']
>;

/** Deterministic JSON for autosave dedupe (key order must not cause false mismatches). */
function stableStringify(value: unknown): string {
  if (value === undefined) {
    return 'null';
  }
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value) ?? 'null';
  }
  if (Array.isArray(value)) {
    return `[${value.map((v) => stableStringify(v)).join(',')}]`;
  }
  const rec = value as Record<string, unknown>;
  return `{${Object.keys(rec)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${stableStringify(rec[k])}`)
    .join(',')}}`;
}

export function SettingsTab() {
  const [currentTheme, setCurrentTheme] = useState<string>('cyberpunk');
  const [themeSaving, setThemeSaving] = useState<string | null>(null);

  // Settings state
  const [settings, setSettings] = useState({
    auto_pipeline: false,
    auto_pipeline_interval_minutes: 60,
    local_high_throughput_enabled: false,
    git_remote_url: '',
    git_default_branch: 'main',
    docker_registry: '',
    docker_username: '',
    docker_password: '',
    telegram_notify_enabled: false,
    telegram_chat_id: '',
    telegram_notify_pipeline_stages: true,
    telegram_notify_new_products: true,
    auto_publish_enabled: false,
    auto_publish_provider: 'none',
    auto_publish_netlify_site_id: '',
    auto_publish_cf_project_name: '',
    site_badge_enabled: false,
    site_badge_link_url: '',
    published_site_head_html: '',
    railway_deploy_enabled: false,
    railway_project_id: '',
    railway_environment: '',
    railway_environment_id: '',
    railway_service_id: '',
    reference_templates_enabled: false,
    reference_templates_dir: '',
    reference_template_mode: 'random',
    reference_template_id: '',
    reference_prompt_max_chars: 14000,
  });
  const [throughputEffective, setThroughputEffective] = useState<AdminThroughputSnapshot | null>(null);
  const [throughputSnapshotBusy, setThroughputSnapshotBusy] = useState(false);
  const [telegramBotTokenConfigured, setTelegramBotTokenConfigured] = useState(false);
  const [railwayTokenConfigured, setRailwayTokenConfigured] = useState(false);
  const [telegramBotTokenInput, setTelegramBotTokenInput] = useState('');
  const [telegramTestBusy, setTelegramTestBusy] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [directorTriggering, setDirectorTriggering] = useState(false);
  const [directorMessage, setDirectorMessage] = useState<string | null>(null);
  const [corpChatSettings, setCorpChatSettings] = useState({
    director_standup_enabled: false,
    director_standup_time: '09:00',
    director_standup_timezone: 'UTC',
  });
  const [corpChatSaving, setCorpChatSaving] = useState(false);

  const [referenceTemplatesCatalog, setReferenceTemplatesCatalog] = useState<
    Array<{ id: string; title: string; path: string; files?: string[] }>
  >([]);
  const [refUploadId, setRefUploadId] = useState('');
  const [refUploadTitle, setRefUploadTitle] = useState('');
  const [refUploadHtml, setRefUploadHtml] = useState('');
  const [refUploadCss, setRefUploadCss] = useState('');
  const [refUploadJs, setRefUploadJs] = useState('');
  const [refUploadBusy, setRefUploadBusy] = useState(false);

  const [twofaEnabled, setTwofaEnabled] = useState(false);
  const [twofaPending, setTwofaPending] = useState(false);
  const [twofaModalOpen, setTwofaModalOpen] = useState(false);
  const [twofaStep, setTwofaStep] = useState<1 | 2>(1);
  const [twofaPassword, setTwofaPassword] = useState('');
  const [twofaUri, setTwofaUri] = useState('');
  const [twofaSecret, setTwofaSecret] = useState('');
  const [twofaVerify, setTwofaVerify] = useState('');
  const [twofaBusy, setTwofaBusy] = useState(false);
  const [disable2faModalOpen, setDisable2faModalOpen] = useState(false);
  const [disable2faPassword, setDisable2faPassword] = useState('');
  const [disable2faBusy, setDisable2faBusy] = useState(false);

  const [autoGenModalOpen, setAutoGenModalOpen] = useState(false);
  const [autoGenIntervalDraft, setAutoGenIntervalDraft] = useState(60);
  const [autoGenSaving, setAutoGenSaving] = useState(false);

  const [qualityOpen, setQualityOpen] = useState(false);
  const [qualitySettings, setQualitySettings] = useState<QualitySettingsState>(() => ({
    ...DEFAULT_QUALITY_SETTINGS,
  }));

  const ADMIN_AUTOSAVE_MS = 700;
  const CORP_AUTOSAVE_MS = 650;
  const adminBaselineReadyRef = useRef(false);
  const adminAutosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastAdminPersistSigRef = useRef<string>('');
  const corpChatHydratedRef = useRef(false);
  const corpAutosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastCorpPersistSigRef = useRef<string>('');

  const clampAutoPipelineMinutes = (n: number) => Math.min(10080, Math.max(15, Math.round(n)));

  const ingestAdminSettingsResponse = (data: Awaited<ReturnType<typeof api.getAdminSettings>>) => {
    const {
      throughput_effective: te,
      telegram_bot_token_configured: tokOk,
      railway_token_configured: rwTok,
      reference_templates_catalog: refCatalog,
      quality: qualityPayload,
      ...rest
    } = data;
    if (te && typeof te === 'object') {
      setThroughputEffective(te as AdminThroughputSnapshot);
    } else {
      setThroughputEffective(null);
    }
    setReferenceTemplatesCatalog(Array.isArray(refCatalog) ? refCatalog : []);
    const head =
      typeof rest.published_site_head_html === 'string'
        ? rest.published_site_head_html
        : rest.published_site_head_html == null
          ? ''
          : String(rest.published_site_head_html);
    setSettings((prev) => ({ ...prev, ...rest, published_site_head_html: head }));
    setTelegramBotTokenConfigured(Boolean(tokOk));
    setRailwayTokenConfigured(Boolean(rwTok));
    if (qualityPayload && typeof qualityPayload === 'object') {
      setQualitySettings((prev) => ({ ...prev, ...DEFAULT_QUALITY_SETTINGS, ...qualityPayload }));
    }
  };

  /** Matches `buildAdminPayload` / `adminPayloadSignature` after a GET so autosave does not loop. */
  const adminSigFromGetResponse = (data: Awaited<ReturnType<typeof api.getAdminSettings>>) => {
    const {
      throughput_effective: _te,
      telegram_bot_token_configured: _tb,
      railway_token_configured: _rw,
      reference_templates_catalog: _rc,
      quality,
      ...rest
    } = data;
    const q =
      quality && typeof quality === 'object'
        ? { ...DEFAULT_QUALITY_SETTINGS, ...quality }
        : { ...DEFAULT_QUALITY_SETTINGS };
    const head =
      typeof rest.published_site_head_html === 'string'
        ? rest.published_site_head_html
        : rest.published_site_head_html == null
          ? ''
          : String(rest.published_site_head_html);
    return stableStringify({ ...rest, published_site_head_html: head, quality: q });
  };

  const refreshThroughputSnapshotOnly = async () => {
    setThroughputSnapshotBusy(true);
    try {
      const data = await api.getAdminSettings();
      const te = data.throughput_effective;
      if (te && typeof te === 'object') {
        setThroughputEffective(te as AdminThroughputSnapshot);
      } else {
        setThroughputEffective(null);
      }
    } catch {
      /* ignore */
    } finally {
      setThroughputSnapshotBusy(false);
    }
  };

  const refreshTwofaStatus = async () => {
    try {
      const me = await api.getMe();
      setTwofaEnabled(Boolean(me.totp_enabled));
      setTwofaPending(Boolean(me.totp_pending));
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    void refreshTwofaStatus();
    api.getTheme().then((data) => {
      if (data?.active_theme) setCurrentTheme(data.active_theme);
      if (data?.theme) applyTheme(data.theme);
    }).catch(() => {});
    api.getAdminSettings().then((data) => {
      ingestAdminSettingsResponse(data);
      setSettingsLoading(false);
    }).catch(() => {
      setSettingsLoading(false);
    });
    api.getChatSettings().then((s) => {
      const next = {
        director_standup_enabled: s.director_standup_enabled,
        director_standup_time: s.director_standup_time,
        director_standup_timezone: s.director_standup_timezone,
      };
      lastCorpPersistSigRef.current = stableStringify(next);
      corpChatHydratedRef.current = true;
      setCorpChatSettings(next);
    }).catch(() => {});
  }, []);

  const handleThemeChange = async (themeName: string) => {
    setThemeSaving(themeName);
    try {
      const result = await api.setTheme(themeName);
      setCurrentTheme(themeName);
      // Apply the new theme's CSS variables
      if (result?.theme) {
        applyTheme(result.theme);
      } else {
        // Re-fetch full theme data if response doesn't include it
        const data = await api.getTheme();
        if (data?.theme) applyTheme(data.theme);
      }
    } catch (e) {
      console.error('Failed to set theme:', e);
    } finally {
      setThemeSaving(null);
    }
  };

  const handleSettingChange = (key: string, value: any) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleAutoPipelineToggleClick = async () => {
    if (settings.auto_pipeline) {
      setAutoGenSaving(true);
      try {
        await api.updateAdminSettings({ auto_pipeline: false, auto_pipeline_interval_minutes: settings.auto_pipeline_interval_minutes });
        const fresh = await api.getAdminSettings();
        ingestAdminSettingsResponse(fresh);
        lastAdminPersistSigRef.current = adminSigFromGetResponse(fresh);
        toast.success('Auto-generation turned off');
      } catch (e: unknown) {
        toast.error(e instanceof Error ? e.message : 'Failed to save');
      } finally {
        setAutoGenSaving(false);
      }
      return;
    }
    setAutoGenIntervalDraft(clampAutoPipelineMinutes(settings.auto_pipeline_interval_minutes || 60));
    setAutoGenModalOpen(true);
  };

  const handleAutoGenConfirm = async () => {
    const minutes = clampAutoPipelineMinutes(autoGenIntervalDraft);
    setAutoGenSaving(true);
    try {
      await api.updateAdminSettings({
        auto_pipeline: true,
        auto_pipeline_interval_minutes: minutes,
      });
      const fresh = await api.getAdminSettings();
      ingestAdminSettingsResponse(fresh);
      lastAdminPersistSigRef.current = adminSigFromGetResponse(fresh);
      setAutoGenModalOpen(false);
      toast.success(`Auto-generation on: at most once every ${minutes} minutes.`);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Failed to save');
    } finally {
      setAutoGenSaving(false);
    }
  };

  const buildAdminPayload = (): Record<string, unknown> => {
    const payload: Record<string, unknown> = { ...settings };
    delete payload.telegram_bot_token_configured;
    delete payload.railway_token_configured;
    delete payload.reference_templates_catalog;
    delete payload.throughput_effective;
    payload.published_site_head_html =
      typeof settings.published_site_head_html === 'string'
        ? settings.published_site_head_html
        : settings.published_site_head_html == null
          ? ''
          : String(settings.published_site_head_html);
    const tok = telegramBotTokenInput.trim();
    if (tok.length >= 35) {
      payload.telegram_bot_token = tok;
    }
    payload.quality = qualitySettings;
    return payload;
  };

  const adminPayloadSignature = () => stableStringify(buildAdminPayload());

  const persistAdminSettings = async (): Promise<boolean> => {
    const sig = adminPayloadSignature();
    if (sig === lastAdminPersistSigRef.current) {
      return true;
    }
    const payload = buildAdminPayload();
    setSettingsSaving(true);
    setSettingsMessage(null);
    try {
      const result = await api.updateAdminSettings(payload as Record<string, unknown>);
      setTelegramBotTokenInput('');
      const fresh = await api.getAdminSettings();
      ingestAdminSettingsResponse(fresh);
      lastAdminPersistSigRef.current = adminSigFromGetResponse(fresh);
      setSettingsMessage(`✅ ${result.message}`);
      window.setTimeout(() => setSettingsMessage(null), 3200);
      return true;
    } catch (e: any) {
      setSettingsMessage(`❌ Failed to save: ${e.message || 'Unknown error'}`);
      toast.error(e?.message || 'Failed to save settings');
      return false;
    } finally {
      setSettingsSaving(false);
    }
  };

  useEffect(() => {
    if (settingsLoading) {
      adminBaselineReadyRef.current = false;
      return;
    }
    if (!adminBaselineReadyRef.current) {
      adminBaselineReadyRef.current = true;
      lastAdminPersistSigRef.current = adminPayloadSignature();
      return;
    }
    const nextSig = adminPayloadSignature();
    if (nextSig === lastAdminPersistSigRef.current) {
      return;
    }
    if (adminAutosaveTimerRef.current) {
      clearTimeout(adminAutosaveTimerRef.current);
    }
    adminAutosaveTimerRef.current = setTimeout(() => {
      adminAutosaveTimerRef.current = null;
      void persistAdminSettings();
    }, ADMIN_AUTOSAVE_MS);
    return () => {
      if (adminAutosaveTimerRef.current) {
        clearTimeout(adminAutosaveTimerRef.current);
        adminAutosaveTimerRef.current = null;
      }
    };
  }, [settings, qualitySettings, telegramBotTokenInput, settingsLoading]); // persistAdminSettings reads latest state when timer fires

  // Autosave Corporate Chat standup schedule (debounced)
  useEffect(() => {
    if (!corpChatHydratedRef.current || settingsLoading) {
      return;
    }
    const sig = stableStringify(corpChatSettings);
    if (sig === lastCorpPersistSigRef.current) {
      return;
    }
    if (corpAutosaveTimerRef.current) {
      clearTimeout(corpAutosaveTimerRef.current);
    }
    corpAutosaveTimerRef.current = setTimeout(async () => {
      corpAutosaveTimerRef.current = null;
      setCorpChatSaving(true);
      setSettingsMessage(null);
      try {
        await api.updateChatSettings(corpChatSettings);
        lastCorpPersistSigRef.current = sig;
        setSettingsMessage('✅ Corporate Chat / standup schedule saved');
        window.setTimeout(() => setSettingsMessage(null), 2800);
      } catch (e: any) {
        setSettingsMessage(`❌ Failed to save standup: ${e.message || 'Unknown error'}`);
        toast.error(e?.message || 'Failed to save standup schedule');
      } finally {
        setCorpChatSaving(false);
      }
    }, CORP_AUTOSAVE_MS);
    return () => {
      if (corpAutosaveTimerRef.current) {
        clearTimeout(corpAutosaveTimerRef.current);
        corpAutosaveTimerRef.current = null;
      }
    };
  }, [corpChatSettings, settingsLoading]);

  const handleRevokeTelegramToken = async () => {
    if (!window.confirm('Remove the stored Telegram bot token? Alerts will stop until you save a new token.')) return;
    try {
      // Do not spread `settings` here: that would POST every general.* field and can wipe e.g.
      // `published_site_head_html` if local React state is stale or empty while the server had a value.
      await api.updateAdminSettings({ telegram_bot_token_revoke: true } as Record<string, unknown>);
      setTelegramBotTokenInput('');
      const fresh = await api.getAdminSettings();
      ingestAdminSettingsResponse(fresh);
      lastAdminPersistSigRef.current = adminSigFromGetResponse(fresh);
      toast.success('Telegram bot token removed');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Failed to revoke token');
    }
  };

  const handleTestTelegram = async () => {
    setTelegramTestBusy(true);
    try {
      await api.testTelegramNotification();
      toast.success('Test message sent — check your Telegram chat');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Telegram test failed');
    } finally {
      setTelegramTestBusy(false);
    }
  };

  const refreshReferenceCatalog = async () => {
    try {
      const data = await api.getAdminSettings();
      const { reference_templates_catalog: cat } = data;
      setReferenceTemplatesCatalog(Array.isArray(cat) ? cat : []);
    } catch {
      /* ignore */
    }
  };

  const handleReferenceTemplateUpload = async () => {
    const slug = refUploadId.trim().toLowerCase().replace(/\s+/g, '-');
    if (!slug) {
      toast.error('Enter a folder id (slug), e.g. my-brand-shell');
      return;
    }
    const html = refUploadHtml.trim();
    if (!html) {
      toast.error('index.html content is required');
      return;
    }
    const files: Array<{ path: string; content: string }> = [{ path: 'index.html', content: refUploadHtml }];
    if (refUploadCss.trim()) files.push({ path: 'style.css', content: refUploadCss });
    if (refUploadJs.trim()) files.push({ path: 'app.js', content: refUploadJs });
    setRefUploadBusy(true);
    try {
      await api.upsertReferenceTemplate({
        template_id: slug,
        title: refUploadTitle.trim() || undefined,
        files,
      });
      toast.success(`Template “${slug}” saved`);
      setRefUploadId('');
      setRefUploadTitle('');
      setRefUploadHtml('');
      setRefUploadCss('');
      setRefUploadJs('');
      await refreshReferenceCatalog();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setRefUploadBusy(false);
    }
  };

  const handleReferenceTemplateDelete = async (templatePath: string) => {
    if (
      !window.confirm(
        `Remove reference template folder “${templatePath}” from disk? This cannot be undone.`,
      )
    ) {
      return;
    }
    setRefUploadBusy(true);
    try {
      await api.deleteReferenceTemplate(templatePath);
      toast.success('Template removed');
      await refreshReferenceCatalog();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setRefUploadBusy(false);
    }
  };

  const handleTriggerDirector = async () => {
    setDirectorTriggering(true);
    setDirectorMessage(null);
    try {
      const result = await api.triggerDirectorAnalysis();
      setDirectorMessage(`✅ ${result.message}`);
    } catch (e: any) {
      setDirectorMessage(`❌ Failed to trigger: ${e.message || 'Unknown error'}`);
    } finally {
      setDirectorTriggering(false);
    }
  };

  return (
    <div className="w-full min-w-0 max-w-2xl space-y-6">
      <h2 className="text-xl font-semibold text-white mb-4">Settings</h2>

      {/* ── Director AI: autonomous development vs ideas-only ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <Zap className="w-5 h-5 text-yellow-400" />
          AI Director & pipeline mode
        </h3>
        <p className="text-sm text-gray-400 mb-4">
          The AI Director oversees products and analysis. Use autonomous development to create new products on a schedule,
          or turn it off and submit ideas manually (CLI / admin).
        </p>

        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Loading settings...
          </div>
        ) : (
          <div className="space-y-4">
            {/* Autonomous development (general.auto_pipeline) */}
            <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-white">Autonomous development</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  On: scheduled market research + idea generation enqueue products into the same pipeline. Off: new products only
                  when you submit a brief (Admin / CLI).
                </div>
              </div>
              <button
                type="button"
                onClick={() => void handleAutoPipelineToggleClick()}
                disabled={autoGenSaving || settingsLoading}
                className={`relative w-12 h-6 rounded-full transition-colors shrink-0 ${
                  settings.auto_pipeline ? 'bg-indigo-500' : 'bg-white/20'
                } ${autoGenSaving ? 'opacity-60 cursor-wait' : ''}`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                    settings.auto_pipeline ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>

            {settings.auto_pipeline && (
              <p className="text-xs text-gray-500 px-1">
                Cadence: at most one auto-enqueued product per{' '}
                <span className="text-gray-300">{settings.auto_pipeline_interval_minutes}</span> minutes (Director checks every ~30s).
              </p>
            )}

            {/* Auto-pipeline interval — edit here or via the enable dialog */}
            <div className="flex flex-col gap-2 p-3 rounded-xl bg-white/5">
              <label className="text-sm text-gray-300">Minimum interval between auto-generated products (minutes)</label>
              <div className="flex flex-wrap gap-2">
                {[15, 30, 60, 360, 720, 1440].map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => handleSettingChange('auto_pipeline_interval_minutes', m)}
                    className={`text-xs px-2 py-1 rounded-lg border transition-colors ${
                      settings.auto_pipeline_interval_minutes === m
                        ? 'border-indigo-400 bg-indigo-500/20 text-white'
                        : 'border-white/10 bg-white/5 text-gray-300 hover:bg-white/10'
                    }`}
                  >
                    {m >= 1440 ? '24h' : m >= 60 ? `${m / 60}h` : `${m}m`}
                  </button>
                ))}
              </div>
              <input
                type="number"
                min={15}
                max={10080}
                value={settings.auto_pipeline_interval_minutes}
                onChange={(e) =>
                  handleSettingChange('auto_pipeline_interval_minutes', clampAutoPipelineMinutes(parseInt(e.target.value, 10) || 60))
                }
                className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500/50"
              />
              <p className="text-xs text-gray-500">Range 15 minutes … 7 days (10080 min). Changes save automatically after a short pause.</p>
            </div>

            <div className="border-t border-white/5 pt-4">
              <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-white">Local high-throughput mode</div>
                  <div className="text-xs text-gray-400 mt-0.5">
                    For a powerful local machine (many cores / RAM, local Ollama): raises how many pipeline tasks can run at
                    once, batch intake per cycle, and parallel agent execution. Turn off on small VMs or shared cloud — you can
                    overload GPUs or hit API rate limits. Non-empty <code className="text-[10px] text-gray-500">AIFACTORY_*</code>{' '}
                    env vars still override each knob. Task limits pick up from saved config automatically; the LLM router reads
                    its limits at worker start — restart the pipeline worker after toggling this if you rely on changed LLM
                    parallelism.
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    handleSettingChange('local_high_throughput_enabled', !settings.local_high_throughput_enabled)
                  }
                  className={`relative h-6 w-12 shrink-0 rounded-full transition-colors ${
                    settings.local_high_throughput_enabled ? 'bg-emerald-600' : 'bg-white/20'
                  }`}
                >
                  <span
                    className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform ${
                      settings.local_high_throughput_enabled ? 'translate-x-6' : 'translate-x-0'
                    }`}
                  />
                </button>
              </label>

              <div className="mt-3 rounded-lg border border-white/10 bg-black/25 px-3 py-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-medium text-gray-300">Effective throughput (this host)</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={throughputSnapshotBusy || settingsLoading}
                    onClick={() => void refreshThroughputSnapshotOnly()}
                    className="inline-flex h-8 items-center gap-1.5 px-2 text-xs text-gray-300 hover:text-white"
                  >
                    {throughputSnapshotBusy ? (
                      <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5 shrink-0" aria-hidden />
                    )}
                    Refresh
                  </Button>
                </div>
                <p className="mb-2 text-[11px] leading-snug text-gray-500">
                  Same rules as the pipeline worker: non-empty <code className="text-[10px] text-gray-600">AIFACTORY_*</code> env
                  overrides each value. LLM router still uses its semaphore from worker start — this table shows what would apply
                  to a new process now.
                </p>
                {throughputEffective ? (
                  <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
                    <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                      <dt className="text-gray-500">Turbo preset in config</dt>
                      <dd className="font-mono text-gray-200">
                        {throughputEffective.local_high_throughput_enabled ? 'on' : 'off'}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                      <dt className="text-gray-500">Max running tasks</dt>
                      <dd className="font-mono text-gray-200">{throughputEffective.effective_max_running_tasks}</dd>
                    </div>
                    <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                      <dt className="text-gray-500">Task executor concurrency</dt>
                      <dd className="font-mono text-gray-200">{throughputEffective.effective_task_executor_concurrency}</dd>
                    </div>
                    <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                      <dt className="text-gray-500">Batch starts / cycle</dt>
                      <dd className="font-mono text-gray-200">
                        {throughputEffective.effective_batch_pipeline_max_start_per_cycle}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                      <dt className="text-gray-500">Batch active ceiling</dt>
                      <dd className="font-mono text-gray-200">{throughputEffective.effective_batch_pipeline_active_limit}</dd>
                    </div>
                    <div className="flex justify-between gap-3 border-b border-white/5 pb-1 sm:block sm:border-0 sm:pb-0">
                      <dt className="text-gray-500">LLM max parallel</dt>
                      <dd className="font-mono text-gray-200">{throughputEffective.effective_llm_max_parallel_requests}</dd>
                    </div>
                    <div className="flex justify-between gap-3 sm:col-span-2">
                      <dt className="text-gray-500">LLM min interval (sec)</dt>
                      <dd className="font-mono text-gray-200">
                        {Number(throughputEffective.effective_llm_min_interval_sec).toFixed(3)}
                      </dd>
                    </div>
                  </dl>
                ) : !settingsLoading ? (
                  <p className="text-xs text-gray-500">Snapshot not available.</p>
                ) : null}
              </div>
            </div>

            <Modal
              isOpen={autoGenModalOpen}
              onClose={() => !autoGenSaving && setAutoGenModalOpen(false)}
              title="How often should auto-generation run?"
              size="md"
            >
              <p className="text-sm text-gray-300 mb-4">
                The autonomous pipeline enqueues at most one new product per interval. Director re-reads settings about every 30 seconds.
              </p>
              <div className="flex flex-wrap gap-2 mb-4">
                {[
                  { label: '15 min', m: 15 },
                  { label: '30 min', m: 30 },
                  { label: '1 h', m: 60 },
                  { label: '6 h', m: 360 },
                  { label: '12 h', m: 720 },
                  { label: '24 h', m: 1440 },
                ].map(({ label, m }) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setAutoGenIntervalDraft(m)}
                    className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                      autoGenIntervalDraft === m
                        ? 'border-indigo-400 bg-indigo-500/25 text-white'
                        : 'border-white/10 bg-white/5 text-gray-300 hover:bg-white/10'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <label className="block text-xs text-gray-400 mb-1">Custom interval (minutes)</label>
              <input
                type="number"
                min={15}
                max={10080}
                value={autoGenIntervalDraft}
                onChange={(e) => setAutoGenIntervalDraft(clampAutoPipelineMinutes(parseInt(e.target.value, 10) || 60))}
                className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white mb-4 focus:outline-none focus:border-indigo-500/50"
              />
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <Button size="sm" variant="ghost" onClick={() => !autoGenSaving && setAutoGenModalOpen(false)} className="w-full sm:w-auto">
                  Cancel
                </Button>
                <Button size="sm" onClick={() => void handleAutoGenConfirm()} disabled={autoGenSaving} className="w-full sm:w-auto">
                  {autoGenSaving ? 'Saving…' : 'Enable'}
                </Button>
              </div>
            </Modal>

            {/* Trigger Director button */}
            <div className="border-t border-white/5 pt-4">
              <p className="text-xs text-gray-500 mb-2">
                Manually trigger Director AI to run an analysis cycle and generate a report now.
              </p>
              <Button
                size="sm"
                onClick={handleTriggerDirector}
                disabled={directorTriggering}
              >
                {directorTriggering ? (
                  <span className="flex items-center gap-2">
                    <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Triggering...
                  </span>
                ) : (
                  'Trigger Director Analysis Now'
                )}
              </Button>
              {directorMessage && (
                <p className="text-xs mt-2 text-gray-400">{directorMessage}</p>
              )}
            </div>
          </div>
        )}
      </GlassCard>

      <QualitySettingsCollapsible
        open={qualityOpen}
        onToggle={() => setQualityOpen((v) => !v)}
        quality={qualitySettings}
        onChange={(key, value) => setQualitySettings((prev) => ({ ...prev, [key]: value }))}
        disabled={settingsLoading || settingsSaving}
      />

      {/* ── Director standup (Corporate Chat) ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <Clock className="w-5 h-5 text-cyan-400" />
          Director standup — Corporate Chat
        </h3>
        <p className="text-sm text-gray-400 mb-4">
          AI Director runs a standup in <strong className="text-gray-300">Corporate Chat</strong> at the scheduled local time:
          plan, agent-style reports, clarifying questions. You participate as <strong className="text-gray-300">Owner</strong>{' '}
          (display name is configured in Corporate Chat tab). This differs from Brainstorming sessions — see{' '}
          <code className="text-xs bg-black/30 px-1 rounded">docs/corporate-chat-vs-discussions.md</code>.
        </p>
        <div className="space-y-4 max-w-md">
          <label className="flex cursor-pointer items-start gap-3 sm:items-center">
            <input
              type="checkbox"
              checked={corpChatSettings.director_standup_enabled}
              onChange={(e) =>
                setCorpChatSettings((prev) => ({ ...prev, director_standup_enabled: e.target.checked }))
              }
              className="rounded border-white/20"
            />
            <span className="text-sm text-gray-300">Enable daily standup</span>
          </label>
          <Input
            label="Local time (HH:MM)"
            placeholder="09:30"
            value={corpChatSettings.director_standup_time}
            onChange={(e) =>
              setCorpChatSettings((prev) => ({ ...prev, director_standup_time: e.target.value }))
            }
          />
          <Input
            label="IANA timezone"
            placeholder="UTC"
            value={corpChatSettings.director_standup_timezone}
            onChange={(e) =>
              setCorpChatSettings((prev) => ({ ...prev, director_standup_timezone: e.target.value }))
            }
          />
          <p className="text-[11px] text-gray-500">
            {corpChatSaving ? 'Saving standup schedule…' : 'Standup schedule saves automatically a moment after you change it.'}
          </p>
        </div>
      </GlassCard>

      {/* ── Git Remote Settings ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <GitBranch className="w-5 h-5 text-orange-400" />
          Git Remote Configuration
        </h3>
        <p className="text-sm text-gray-400 mb-4">
          Configure the remote Git repository where product code will be pushed.
          Used by the Pipeline → Git workflow.
        </p>

        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Loading settings...
          </div>
        ) : (
          <div className="space-y-4">
            <Input
              label="Remote URL"
              placeholder="https://github.com/your-org/repo.git"
              value={settings.git_remote_url}
              onChange={(e) => handleSettingChange('git_remote_url', e.target.value)}
            />
            <Input
              label="Default Branch"
              placeholder="main"
              value={settings.git_default_branch}
              onChange={(e) => handleSettingChange('git_default_branch', e.target.value)}
            />
          </div>
        )}
      </GlassCard>

      {/* ── Docker Registry Credentials ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <Container className="w-5 h-5 text-blue-400" />
          Docker Registry Credentials
        </h3>
        <p className="text-sm text-gray-400 mb-4">
          Docker registry credentials for pushing built images (e.g., Docker Hub, GitHub Container Registry).
        </p>

        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Loading settings...
          </div>
        ) : (
          <div className="space-y-4">
            <Input
              label="Registry URL"
              placeholder="docker.io (default)"
              value={settings.docker_registry}
              onChange={(e) => handleSettingChange('docker_registry', e.target.value)}
            />
            <Input
              label="Username"
              placeholder="Docker registry username"
              value={settings.docker_username}
              onChange={(e) => handleSettingChange('docker_username', e.target.value)}
            />
            <Input
              label="Password / Token"
              type="password"
              placeholder="Docker registry password or access token"
              value={settings.docker_password}
              onChange={(e) => handleSettingChange('docker_password', e.target.value)}
            />
          </div>
        )}
      </GlassCard>

      {/* ── Auto-publish (Vercel / Netlify / Cloudflare Pages) ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <Globe className="w-5 h-5 text-emerald-400" />
          Auto-publish after DevOps
        </h3>
        <p className="text-sm text-gray-400 mb-4">
          Deploy <code className="text-xs text-indigo-300">data/code/&lt;product_id&gt;/</code> to a static host when the
          DevOps stage succeeds. Install the matching CLI on the factory host and set tokens via environment variables (
          <code className="text-xs text-gray-500">VERCEL_TOKEN</code>,{' '}
          <code className="text-xs text-gray-500">NETLIFY_AUTH_TOKEN</code>,{' '}
          <code className="text-xs text-gray-500">CLOUDFLARE_API_TOKEN</code>
          ). See <code className="text-xs text-gray-500">docs/auto-publish.md</code>.
        </p>
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Loading settings...
          </div>
        ) : (
          <div className="space-y-4">
            <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-white">Enable auto-publish</div>
                <div className="text-xs text-gray-400 mt-0.5">Runs after DevOps completes (non-blocking).</div>
              </div>
              <button
                type="button"
                onClick={() => handleSettingChange('auto_publish_enabled', !settings.auto_publish_enabled)}
                className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                  settings.auto_publish_enabled ? 'bg-emerald-600' : 'bg-white/20'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                    settings.auto_publish_enabled ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Provider</label>
              <select
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white"
                value={settings.auto_publish_provider}
                onChange={(e) => handleSettingChange('auto_publish_provider', e.target.value)}
              >
                <option value="none">none</option>
                <option value="vercel">vercel</option>
                <option value="netlify">netlify</option>
                <option value="cloudflare_pages">cloudflare_pages</option>
              </select>
            </div>
            <Input
              label="Netlify site ID (optional)"
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              value={settings.auto_publish_netlify_site_id}
              onChange={(e) => handleSettingChange('auto_publish_netlify_site_id', e.target.value)}
            />
            <Input
              label="Cloudflare Pages project name (optional)"
              placeholder="aifactory-my-product"
              value={settings.auto_publish_cf_project_name}
              onChange={(e) => handleSettingChange('auto_publish_cf_project_name', e.target.value)}
            />
          </div>
        )}
      </GlassCard>

      {/* ── Railway / full_software cloud hook ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <TrainFront className="w-5 h-5 text-violet-400" />
          Railway (full_software)
        </h3>
        <p className="text-sm text-gray-400 mb-4">
          After DevOps, when the product specification is <code className="text-xs text-gray-500">full_software</code>,
          the factory records deploy metadata under{' '}
          <code className="text-xs text-gray-500">data/state/&lt;product_id&gt;/railway_deploy.json</code> so you can
          trigger a separate CI step (GitHub Action calling Railway’s API, or Git-connected deploy). Set{' '}
          <code className="text-xs text-gray-500">RAILWAY_TOKEN</code> on the factory host — never in YAML. See{' '}
          <code className="text-xs text-gray-500">docs/deploy-full-software-cloud.md</code>.
        </p>
        {!railwayTokenConfigured && (
          <p className="text-xs text-amber-300/90 mb-4 rounded-lg bg-amber-500/10 border border-amber-500/25 px-3 py-2">
            <code className="text-[11px] text-amber-200">RAILWAY_TOKEN</code> is not set in the environment — enable the
            toggle below after adding the token to <code className="text-[11px] text-amber-200">.env</code> / container
            secrets.
          </p>
        )}
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Loading settings...
          </div>
        ) : (
          <div className="space-y-4">
            <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-white">Record Railway deploy intent after DevOps</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  Only for <code className="text-[11px]">full_software</code> specs; requires{' '}
                  <code className="text-[11px]">RAILWAY_TOKEN</code>.
                </div>
              </div>
              <button
                type="button"
                onClick={() => handleSettingChange('railway_deploy_enabled', !settings.railway_deploy_enabled)}
                className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                  settings.railway_deploy_enabled ? 'bg-violet-600' : 'bg-white/20'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                    settings.railway_deploy_enabled ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>
            <Input
              label="Railway project ID"
              placeholder="UUID from Railway dashboard"
              value={settings.railway_project_id}
              onChange={(e) => handleSettingChange('railway_project_id', e.target.value)}
            />
            <Input
              label="Environment name (optional)"
              placeholder="production"
              value={settings.railway_environment}
              onChange={(e) => handleSettingChange('railway_environment', e.target.value)}
            />
            <Input
              label="Environment ID (optional, UUID for Railway API)"
              placeholder="From Railway dashboard / GraphQL — for redeploy scripts"
              value={settings.railway_environment_id}
              onChange={(e) => handleSettingChange('railway_environment_id', e.target.value)}
            />
            <Input
              label="Service ID (optional)"
              placeholder="For dashboards / future API wiring"
              value={settings.railway_service_id}
              onChange={(e) => handleSettingChange('railway_service_id', e.target.value)}
            />
          </div>
        )}
      </GlassCard>

      {/* ── Neural UI reference pool (Developer prompt) ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <Palette className="w-5 h-5 text-fuchsia-400" />
          Neural UI reference pool
        </h3>
        <p className="text-sm text-gray-400 mb-4">
          Optionally inject a generated vanilla HTML/CSS/JS shell into the Developer (and Hardening) prompt so new products
          mirror motion, tokens, and layout polish. Build the pool offline:{' '}
          <code className="text-xs text-gray-500">python scripts/generate_reference_templates.py --data-root ./data</code>
          — outputs under <code className="text-xs text-gray-500">data/reference_templates/</code> plus{' '}
          <code className="text-xs text-gray-500">manifest.json</code>. Style presets live in{' '}
          <code className="text-xs text-gray-500">reference_templates/style_presets.json</code>. Environment variables{' '}
          <code className="text-xs text-gray-500">AIFACTORY_REFERENCE_*</code> override these saved values on the worker.
        </p>
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Loading settings...
          </div>
        ) : (
          <div className="space-y-4">
            <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-white">Inject reference shell into Developer prompt</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  Web deliverables only. Requires a generated pool (manifest + template folders on disk).
                </div>
              </div>
              <button
                type="button"
                onClick={() =>
                  handleSettingChange('reference_templates_enabled', !settings.reference_templates_enabled)
                }
                className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                  settings.reference_templates_enabled ? 'bg-fuchsia-600' : 'bg-white/20'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                    settings.reference_templates_enabled ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>
            <Input
              label="Templates directory (optional)"
              placeholder="Empty → &lt;data_root&gt;/reference_templates"
              value={settings.reference_templates_dir}
              onChange={(e) => handleSettingChange('reference_templates_dir', e.target.value)}
            />
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-400">Selection mode</label>
              <select
                value={settings.reference_template_mode}
                onChange={(e) => handleSettingChange('reference_template_mode', e.target.value)}
                className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-fuchsia-500/50"
              >
                <option value="random">random (stable per product id)</option>
                <option value="round_robin">round_robin</option>
                <option value="fixed">fixed</option>
                <option value="match_spec">match_spec (keyword overlap with spec)</option>
              </select>
            </div>
            <p className="text-xs text-gray-500 rounded-lg bg-white/5 px-3 py-2 border border-white/5">
              Templates detected on disk:{' '}
              <strong className="text-gray-300">{referenceTemplatesCatalog.length}</strong>
              {referenceTemplatesCatalog.length === 0 && settings.reference_templates_enabled ? (
                <span className="text-amber-300/90">
                  {' '}
                  — generate the pool (see command above), upload below, or check the templates directory path.
                </span>
              ) : null}
            </p>

            {referenceTemplatesCatalog.length > 0 && (
              <div className="space-y-2 max-h-52 overflow-y-auto rounded-xl border border-white/10 p-3 bg-black/25">
                <div className="text-xs font-medium text-gray-400">Installed templates</div>
                {referenceTemplatesCatalog.map((t) => (
                  <div
                    key={t.path}
                    className="flex flex-col gap-2 border-b border-white/5 py-3 last:border-0 sm:flex-row sm:items-center sm:justify-between sm:gap-2 sm:py-2"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-white truncate">{t.title}</div>
                      <div className="text-[11px] text-gray-500 font-mono truncate">{t.path}</div>
                    </div>
                    <button
                      type="button"
                      disabled={refUploadBusy}
                      onClick={() => void handleReferenceTemplateDelete(t.path)}
                      className="self-end text-xs text-red-400 hover:text-red-300 disabled:opacity-40 px-2 py-1 rounded-lg hover:bg-red-500/10 sm:self-center"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="rounded-xl border border-fuchsia-500/25 bg-fuchsia-950/15 p-4 space-y-3">
              <div className="text-sm font-medium text-white">Add custom template</div>
              <p className="text-xs text-gray-400">
                Saves under your reference templates directory as a new folder with{' '}
                <code className="text-[11px] text-gray-500">index.html</code> (required) and optional{' '}
                <code className="text-[11px] text-gray-500">style.css</code> /{' '}
                <code className="text-[11px] text-gray-500">app.js</code>. Slug: lowercase letters, digits, hyphen,
                underscore.
              </p>
              <Input
                label="Folder id (slug)"
                placeholder="my-brand-shell"
                value={refUploadId}
                onChange={(e) => setRefUploadId(e.target.value)}
              />
              <Input
                label="Display title (optional)"
                placeholder="My brand shell"
                value={refUploadTitle}
                onChange={(e) => setRefUploadTitle(e.target.value)}
              />
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-gray-400">index.html *</label>
                <textarea
                  value={refUploadHtml}
                  onChange={(e) => setRefUploadHtml(e.target.value)}
                  rows={8}
                  placeholder="<!DOCTYPE html>..."
                  className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-fuchsia-500/50"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-gray-400">style.css (optional)</label>
                <textarea
                  value={refUploadCss}
                  onChange={(e) => setRefUploadCss(e.target.value)}
                  rows={5}
                  className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-fuchsia-500/50"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-gray-400">app.js (optional)</label>
                <textarea
                  value={refUploadJs}
                  onChange={(e) => setRefUploadJs(e.target.value)}
                  rows={5}
                  className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-fuchsia-500/50"
                />
              </div>
              <Button
                type="button"
                size="sm"
                disabled={refUploadBusy}
                onClick={() => void handleReferenceTemplateUpload()}
              >
                {refUploadBusy ? 'Saving…' : 'Save template'}
              </Button>
            </div>

            {settings.reference_template_mode === 'random' && (
              <p className="text-xs text-gray-500">
                Same product always gets the same reference (hash of product id over the pool).
              </p>
            )}
            {settings.reference_template_mode === 'round_robin' && (
              <p className="text-xs text-gray-500">
                Each new Developer run advances to the next template in order (state file on disk).
              </p>
            )}
            {settings.reference_template_mode === 'match_spec' && (
              <p className="text-xs text-gray-500">
                Chooses the preset whose keywords best overlap with the specification and admin brief; falls back to
                random if there is no overlap.
              </p>
            )}
            {settings.reference_template_mode === 'fixed' && (
              <div className="space-y-3">
                {referenceTemplatesCatalog.length > 0 ? (
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-gray-400">Template</label>
                    <select
                      value={
                        referenceTemplatesCatalog.some((t) => t.path === settings.reference_template_id)
                          ? settings.reference_template_id
                          : ''
                      }
                      onChange={(e) => handleSettingChange('reference_template_id', e.target.value)}
                      className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-fuchsia-500/50"
                    >
                      <option value="">— Select template —</option>
                      {referenceTemplatesCatalog.map((t) => (
                        <option key={t.path} value={t.path}>
                          {t.title} ({t.path})
                        </option>
                      ))}
                    </select>
                    {!referenceTemplatesCatalog.some((t) => t.path === settings.reference_template_id) &&
                      settings.reference_template_id.trim() !== '' && (
                      <p className="text-xs text-amber-300/90">
                        Current id “{settings.reference_template_id}” is not in the catalog — pick above or fix the path.
                      </p>
                    )}
                  </div>
                ) : (
                  <Input
                    label="Fixed template id (folder name)"
                    placeholder="e.g. aurora-glass"
                    value={settings.reference_template_id}
                    onChange={(e) => handleSettingChange('reference_template_id', e.target.value)}
                  />
                )}
              </div>
            )}
            <div className="flex flex-col gap-2 rounded-xl bg-white/5 p-3 sm:flex-row sm:items-center sm:gap-3">
              <label className="shrink-0 text-sm text-gray-300 sm:whitespace-nowrap">Max prompt chars:</label>
              <input
                type="number"
                min={2000}
                max={64000}
                step={500}
                value={settings.reference_prompt_max_chars}
                onChange={(e) =>
                  handleSettingChange('reference_prompt_max_chars', parseInt(e.target.value, 10) || 14000)
                }
                className="flex-1 bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-fuchsia-500/50"
              />
            </div>
          </div>
        )}
      </GlassCard>

      {/* ── Generated-site badge (GitHub / viral loop) ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-amber-400" />
          “Built with AI-Factory” badge
        </h3>
        <p className="text-sm text-gray-400 mb-4">
          After each developer build, inject a small fixed-corner link on every generated <code className="text-xs text-gray-500">*.html</code> file.
          Point it at your public repo (e.g. GitHub) so visitors can star or fork the factory.
        </p>
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Loading settings...
          </div>
        ) : (
          <div className="space-y-4">
            <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-white">Enable badge on generated sites</div>
                <div className="text-xs text-gray-400 mt-0.5">Runs when Developer completes (needs HTTPS URL below).</div>
              </div>
              <button
                type="button"
                onClick={() => handleSettingChange('site_badge_enabled', !settings.site_badge_enabled)}
                className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                  settings.site_badge_enabled ? 'bg-amber-600' : 'bg-white/20'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                    settings.site_badge_enabled ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>
            <Input
              label="Badge link URL (HTTPS)"
              placeholder="https://github.com/your-org/aicom"
              value={settings.site_badge_link_url}
              onChange={(e) => handleSettingChange('site_badge_link_url', e.target.value)}
            />
          </div>
        )}
      </GlassCard>

      {/* ── Generated-site head snippet (analytics / SEO) ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-emerald-400" />
          Head snippet on generated sites
        </h3>
        <p className="text-sm text-gray-400 mb-4">
          Raw HTML inserted before <code className="text-xs text-gray-500">&lt;/head&gt;</code> on every{' '}
          <code className="text-xs text-gray-500">*.html</code> when Developer finishes (Google Analytics gtag, Yandex
          Metrica, <code className="text-xs text-gray-500">meta</code> verification tags, etc.). Leave empty to disable.
          Trusted admin content only. If the snippet includes a GA4 measurement id (<code className="text-xs text-gray-500">G-…</code>
          ), the same id is loaded on this Next.js storefront (Explore, product pages) after save — no separate env needed.
        </p>
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Loading settings...
          </div>
        ) : (
          <div className="space-y-2">
            <label className="text-xs font-medium text-gray-400" htmlFor="published_site_head_html">
              HTML / scripts for <span className="text-gray-300">&lt;head&gt;</span>
            </label>
            <textarea
              id="published_site_head_html"
              rows={10}
              spellCheck={false}
              placeholder={`<!-- Example: GA4 -->\n<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXX"></script>\n<script>\n  window.dataLayer = window.dataLayer || [];\n  function gtag(){dataLayer.push(arguments);}\n  gtag('js', new Date());\n  gtag('config', 'G-XXXX');\n</script>`}
              value={settings.published_site_head_html ?? ''}
              onChange={(e) => handleSettingChange('published_site_head_html', e.target.value)}
              onBlur={() => {
                if (adminAutosaveTimerRef.current) {
                  clearTimeout(adminAutosaveTimerRef.current);
                  adminAutosaveTimerRef.current = null;
                }
                void persistAdminSettings();
              }}
              className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 font-mono text-xs text-white placeholder:text-gray-600 focus:border-emerald-500/40 focus:outline-none"
            />
            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
              <p className="text-xs text-gray-500 min-w-0">
                Max 100,000 characters (server truncates beyond that). Already-built pages are not rewritten; run Developer
                again or edit HTML on disk to apply changes retroactively. This field{' '}
                <span className="text-gray-400">autosaves</span> a few seconds after edits — blur the field to save immediately.
              </p>
              <p
                className={`shrink-0 text-xs tabular-nums sm:text-right ${
                  (settings.published_site_head_html ?? '').length > 100_000 ? 'text-amber-400' : 'text-gray-400'
                }`}
                aria-live="polite"
              >
                {(settings.published_site_head_html ?? '').length.toLocaleString()} / 100,000
              </p>
            </div>
          </div>
        )}
      </GlassCard>

      {/* ── Telegram pipeline alerts ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
          <Send className="w-5 h-5 text-sky-400" />
          Telegram alerts
        </h3>
        <p className="text-sm text-gray-400 mb-4">
          Optional notifications when products are created and when each pipeline stage completes (same events as Corporate
          Chat). Create a bot with{' '}
          <a href="https://t.me/BotFather" className="text-sky-400 hover:underline" target="_blank" rel="noreferrer">
            BotFather
          </a>
          , copy the API token, then{' '}
          <strong className="text-gray-300">send any message to your bot</strong> and resolve{' '}
          <strong className="text-gray-300">chat id</strong> via{' '}
          <code className="text-cyan-400/90 text-xs">https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</code> (look for{' '}
          <code className="text-cyan-400/90 text-xs">chat.id</code>
          ).
        </p>
        {settingsLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Loading…
          </div>
        ) : (
          <div className="space-y-4">
            <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-white">Enable Telegram alerts</div>
                <div className="text-xs text-gray-400 mt-0.5">Master switch — requires bot token and chat id.</div>
              </div>
              <button
                type="button"
                onClick={() => handleSettingChange('telegram_notify_enabled', !settings.telegram_notify_enabled)}
                className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                  settings.telegram_notify_enabled ? 'bg-sky-600' : 'bg-white/20'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                    settings.telegram_notify_enabled ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>

            <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1 text-sm text-gray-300">Notify pipeline stages</div>
              <button
                type="button"
                onClick={() =>
                  handleSettingChange('telegram_notify_pipeline_stages', !settings.telegram_notify_pipeline_stages)
                }
                className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                  settings.telegram_notify_pipeline_stages ? 'bg-sky-600' : 'bg-white/20'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                    settings.telegram_notify_pipeline_stages ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>

            <label className="flex cursor-pointer flex-col gap-3 rounded-xl bg-white/5 p-3 transition-colors hover:bg-white/10 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1 text-sm text-gray-300">Notify new products</div>
              <button
                type="button"
                onClick={() =>
                  handleSettingChange('telegram_notify_new_products', !settings.telegram_notify_new_products)
                }
                className={`relative w-12 h-6 shrink-0 rounded-full transition-colors ${
                  settings.telegram_notify_new_products ? 'bg-sky-600' : 'bg-white/20'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                    settings.telegram_notify_new_products ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </label>

            <Input
              label="Telegram chat ID"
              placeholder='e.g. "123456789" or "-1001234567890" for groups'
              value={settings.telegram_chat_id}
              onChange={(e) => handleSettingChange('telegram_chat_id', e.target.value)}
            />

            <div>
              <label className="text-xs text-gray-500 block mb-1">Bot API token</label>
              <Input
                label=""
                type="password"
                placeholder={
                  telegramBotTokenConfigured ? 'Leave blank to keep current token — enter only when rotating' : 'Paste token from BotFather'
                }
                value={telegramBotTokenInput}
                onChange={(e) => setTelegramBotTokenInput(e.target.value)}
              />
              <p className="text-[11px] text-gray-500 mt-1">
                Saved in <code className="text-gray-400">config.yaml</code> on the server (like other Settings secrets).
                Bot token is sent only when it looks complete (≥35 chars), then saves automatically after you stop typing.
                {telegramBotTokenConfigured ? (
                  <span className="text-emerald-400/90"> Token stored.</span>
                ) : (
                  <span className="text-amber-400/90"> Not configured.</span>
                )}
              </p>
            </div>

            <div className="flex flex-wrap gap-2 pt-1">
              <Button type="button" variant="secondary" size="sm" disabled={telegramTestBusy} onClick={() => void handleTestTelegram()}>
                {telegramTestBusy ? 'Sending…' : 'Send test message'}
              </Button>
              {telegramBotTokenConfigured && (
                <Button type="button" variant="ghost" size="sm" onClick={() => void handleRevokeTelegramToken()}>
                  Remove bot token
                </Button>
              )}
            </div>
          </div>
        )}
      </GlassCard>

      {/* ── Autosave status (main settings persist on edit, ~0.7s debounce) ── */}
      {!settingsLoading && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
          <div className="flex items-center gap-2 text-sm">
            {settingsSaving ? (
              <span className="flex items-center gap-2 text-gray-300">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Saving settings…
              </span>
            ) : (
              <span className="text-emerald-400/90">Settings save automatically while you edit.</span>
            )}
          </div>
          {settingsMessage && (
            <span className="text-sm text-gray-400 break-words">{settingsMessage}</span>
          )}
        </div>
      )}

      {/* ── Change Password ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4">Change Password</h3>
        <div className="space-y-4">
          <Input label="Current Password" type="password" />
          <Input label="New Password" type="password" />
          <Input label="Confirm New Password" type="password" />
          <Button>Update Password</Button>
        </div>
      </GlassCard>

      {/* ── Two-Factor Authentication ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4">Two-Factor Authentication</h3>
        <p className="text-sm text-gray-400 mb-4">
          TOTP-based 2FA (Google Authenticator, 1Password, etc.). After enabling, login requires a 6-digit code.
        </p>
        {twofaPending && !twofaEnabled && (
          <div className="mb-4 p-3 rounded-xl bg-amber-500/10 border border-amber-500/25 text-sm text-amber-100">
            A secret is pending verification — open <strong>Complete 2FA setup</strong> or cancel to start over.
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          {!twofaEnabled ? (
            <>
              <Button
                variant="secondary"
                onClick={() => {
                  setTwofaModalOpen(true);
                  setTwofaStep(twofaPending ? 2 : 1);
                  setTwofaPassword('');
                  setTwofaVerify('');
                  if (!twofaPending) {
                    setTwofaUri('');
                    setTwofaSecret('');
                  }
                }}
              >
                {twofaPending ? 'Complete 2FA setup' : 'Setup 2FA'}
              </Button>
              {twofaPending && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    void (async () => {
                      try {
                        await api.cancel2FASetup();
                        toast.success('Pending 2FA setup cleared');
                        await refreshTwofaStatus();
                      } catch (e: unknown) {
                        toast.error(e instanceof Error ? e.message : 'Failed to cancel');
                      }
                    })();
                  }}
                >
                  Cancel pending setup
                </Button>
              )}
            </>
          ) : (
            <>
              <Badge variant="success">2FA enabled</Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDisable2faModalOpen(true);
                  setDisable2faPassword('');
                }}
              >
                Disable 2FA
              </Button>
            </>
          )}
        </div>
      </GlassCard>

      <Modal
        isOpen={twofaModalOpen}
        onClose={() => setTwofaModalOpen(false)}
        title={twofaStep === 1 ? 'Setup 2FA — confirm password' : 'Setup 2FA — scan & verify'}
        size={twofaStep === 2 ? 'lg' : 'md'}
      >
        <div className="space-y-4" onClick={(e) => e.stopPropagation()}>
          {twofaStep === 1 ? (
            <>
              <Input
                label="Current admin password"
                type="password"
                value={twofaPassword}
                onChange={(e) => setTwofaPassword(e.target.value)}
                placeholder="Required to generate a secret"
              />
              <Button
                variant="primary"
                disabled={twofaBusy || twofaPassword.length < 1}
                onClick={() => {
                  void (async () => {
                    setTwofaBusy(true);
                    try {
                      const res = await api.setup2FA(twofaPassword);
                      setTwofaUri(res.uri);
                      setTwofaSecret(res.secret);
                      setTwofaStep(2);
                      await refreshTwofaStatus();
                      toast.success('Secret created — scan the QR code');
                    } catch (e: unknown) {
                      toast.error(e instanceof Error ? e.message : 'Setup failed');
                    } finally {
                      setTwofaBusy(false);
                    }
                  })();
                }}
              >
                {twofaBusy ? 'Working…' : 'Continue'}
              </Button>
            </>
          ) : (
            <>
              {twofaUri ? (
                <div className="flex flex-col items-center gap-3">
                  <div className="p-3 rounded-xl bg-white">
                    <QRCodeSVG value={twofaUri} size={200} level="M" />
                  </div>
                  <p className="text-xs text-gray-500 text-center">
                    Or enter manually: <span className="font-mono text-gray-300">{twofaSecret}</span>
                  </p>
                </div>
              ) : (
                <p className="text-sm text-gray-400">
                  Enter the 6-digit code from your authenticator app. Need the QR again? Cancel pending setup from Settings
                  and start over.
                </p>
              )}
              <Input
                label="Verification code"
                value={twofaVerify}
                onChange={(e) => setTwofaVerify(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000"
                maxLength={6}
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  disabled={twofaBusy || twofaVerify.length !== 6}
                  onClick={() => {
                    void (async () => {
                      setTwofaBusy(true);
                      try {
                        await api.verify2FA(twofaVerify.trim());
                        toast.success('2FA is now enabled');
                        setTwofaModalOpen(false);
                        setTwofaVerify('');
                        await refreshTwofaStatus();
                      } catch (e: unknown) {
                        toast.error(e instanceof Error ? e.message : 'Invalid code');
                      } finally {
                        setTwofaBusy(false);
                      }
                    })();
                  }}
                >
                  {twofaBusy ? 'Verifying…' : 'Verify & enable'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={twofaBusy}
                  onClick={() => {
                    void (async () => {
                      try {
                        await api.cancel2FASetup();
                        toast('2FA setup cancelled');
                        setTwofaModalOpen(false);
                        await refreshTwofaStatus();
                      } catch (e: unknown) {
                        toast.error(e instanceof Error ? e.message : 'Cancel failed');
                      }
                    })();
                  }}
                >
                  Cancel setup
                </Button>
              </div>
            </>
          )}
        </div>
      </Modal>

      <Modal
        isOpen={disable2faModalOpen}
        onClose={() => setDisable2faModalOpen(false)}
        title="Disable 2FA"
        size="md"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-400">
            Confirm your password to remove TOTP protection from this admin account.
          </p>
          <Input
            label="Current password"
            type="password"
            value={disable2faPassword}
            onChange={(e) => setDisable2faPassword(e.target.value)}
          />
          <Button
            variant="secondary"
            disabled={disable2faBusy || disable2faPassword.length < 1}
            onClick={() => {
              void (async () => {
                setDisable2faBusy(true);
                try {
                  await api.disable2FA(disable2faPassword);
                  toast.success('2FA disabled');
                  setDisable2faModalOpen(false);
                  setDisable2faPassword('');
                  await refreshTwofaStatus();
                } catch (e: unknown) {
                  toast.error(e instanceof Error ? e.message : 'Failed');
                } finally {
                  setDisable2faBusy(false);
                }
              })();
            }}
          >
            {disable2faBusy ? 'Working…' : 'Disable 2FA'}
          </Button>
        </div>
      </Modal>

      {/* ── Demo replay (same as Live Monitor — enable without editing JSON on disk) ── */}
      <DemoReplayMonitorSection variant="settings" />

      {/* ── Theme ── */}
      <GlassCard>
        <h3 className="text-lg font-medium text-white mb-4">Theme</h3>
        <div className="flex flex-wrap gap-3">
          {['cyberpunk', 'minimal', 'glass', 'neon', 'corporate'].map((theme) => (
            <button
              key={theme}
              onClick={() => handleThemeChange(theme)}
              disabled={themeSaving === theme}
              className={`px-4 py-2 rounded-xl glass transition-all capitalize text-sm ${
                currentTheme === theme
                  ? 'border-indigo-500/60 bg-indigo-500/15 text-white shadow-lg shadow-indigo-500/10'
                  : 'hover:border-indigo-500/30 text-gray-300'
              }`}
            >
              {themeSaving === theme ? (
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  {theme}
                </span>
              ) : (
                theme
              )}
            </button>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}
