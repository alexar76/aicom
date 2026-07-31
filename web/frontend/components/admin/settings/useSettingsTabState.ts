'use client';

import { useEffect, useRef, useState } from 'react';
import api from '@/lib/api';
import { applyTheme } from '@/lib/utils';
import type { AdminLocale } from '@/lib/adminI18n';
import { t, tVars } from '@/lib/adminI18n';
import toast from 'react-hot-toast';
import { useAdminSessionStore } from '@/lib/adminSessionStore';
import {
  DEFAULT_QUALITY_SETTINGS,
  LEGACY_QUALITY_PRESETS,
  OPTIMIZED_QUALITY_PRESETS,
  type QualitySettingsState,
} from '../tabs/QualitySettingsCollapsible';

export type AdminThroughputSnapshot = NonNullable<
  Awaited<ReturnType<typeof api.getAdminSettings>>['throughput_effective']
>;

/** Deterministic JSON for autosave dedupe (key order must not cause false mismatches). */
export function stableStringify(value: unknown): string {
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

const ADMIN_AUTOSAVE_MS = 700;
const CORP_AUTOSAVE_MS = 650;

export function useSettingsTabState(locale: AdminLocale) {
  const publicDemo = useAdminSessionStore((s) =>
    Boolean(s.me?.public_demo || (s.me as { public_demo_readonly?: boolean } | null)?.public_demo_readonly),
  );
  const [currentTheme, setCurrentTheme] = useState<string>('cyberpunk');
  const [themeSaving, setThemeSaving] = useState<string | null>(null);

  const [settings, setSettings] = useState({
    factory_on_hold: false,
    autonomy_mode: 'supervised' as 'supervised' | 'full',
    auto_pipeline: false,
    auto_pipeline_interval_minutes: 60,
    local_high_throughput_enabled: false,
    pipeline_cost_optimized: true,
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
    public_site_url: 'https://magic-ai-factory.com',
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
    pipeline_db_backend: 'sqlite' as 'sqlite' | 'postgres' | 'json',
    pipeline_database_url: '',
    telegram_notify_host_disk: true,
    disk_warn_used_pct: 90,
    disk_crit_used_pct: 96,
    disk_warn_free_gb: 4,
    disk_crit_free_gb: 1,
    disk_alert_cooldown_hours: 8,
    disk_monitor_interval_minutes: 15,
  });
  const [diskMonitorLive, setDiskMonitorLive] = useState<Record<string, unknown> | null>(null);
  const [pipelineDbStatus, setPipelineDbStatus] = useState<Record<string, unknown> | null>(null);
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
  const [webauthnEnabled, setWebauthnEnabled] = useState(false);
  const [mfaMethod, setMfaMethod] = useState<string | null>(null);
  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const [disablePasskeyModalOpen, setDisablePasskeyModalOpen] = useState(false);
  const [disablePasskeyPassword, setDisablePasskeyPassword] = useState('');

  const [autoGenModalOpen, setAutoGenModalOpen] = useState(false);
  const [autoGenIntervalDraft, setAutoGenIntervalDraft] = useState(60);
  const [autoGenSaving, setAutoGenSaving] = useState(false);
  const [autonomyModeSaving, setAutonomyModeSaving] = useState(false);
  const autoGenAbortRef = useRef<AbortController | null>(null);

  const [qualityOpen, setQualityOpen] = useState(false);
  const [qualitySettings, setQualitySettings] = useState<QualitySettingsState>(() => ({
    ...DEFAULT_QUALITY_SETTINGS,
  }));

  const adminBaselineReadyRef = useRef(false);
  const adminAutosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastAdminPersistSigRef = useRef<string>('');
  const corpChatHydratedRef = useRef(false);
  const corpAutosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastCorpPersistSigRef = useRef<string>('');

  const clampAutoPipelineMinutes = (n: number) => Math.min(10080, Math.max(15, Math.round(n)));

  const clearAdminAutosaveTimer = () => {
    if (adminAutosaveTimerRef.current) {
      clearTimeout(adminAutosaveTimerRef.current);
      adminAutosaveTimerRef.current = null;
    }
  };

  const ingestAdminSettingsResponse = (data: Awaited<ReturnType<typeof api.getAdminSettings>>) => {
    const {
      throughput_effective: te,
      telegram_bot_token_configured: tokOk,
      railway_token_configured: rwTok,
      reference_templates_catalog: refCatalog,
      quality: qualityPayload,
      pipeline_db_status: pipeStatus,
      pipeline_database_url_masked: _urlMasked,
      disk_monitor_live: diskLive,
      ...rest
    } = data;
    setDiskMonitorLive(diskLive && typeof diskLive === 'object' ? (diskLive as Record<string, unknown>) : null);
    setPipelineDbStatus(pipeStatus && typeof pipeStatus === 'object' ? pipeStatus : null);
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
    const backend =
      rest.pipeline_db_backend === 'postgres' || rest.pipeline_db_backend === 'json'
        ? rest.pipeline_db_backend
        : 'sqlite';
    setSettings((prev) => ({
      ...prev,
      ...rest,
      pipeline_db_backend: backend,
      published_site_head_html: head,
    }));
    setTelegramBotTokenConfigured(Boolean(tokOk));
    setRailwayTokenConfigured(Boolean(rwTok));
    if (qualityPayload && typeof qualityPayload === 'object') {
      setQualitySettings((prev) => ({ ...prev, ...DEFAULT_QUALITY_SETTINGS, ...qualityPayload }));
    }
  };

  const adminSigFromGetResponse = (data: Awaited<ReturnType<typeof api.getAdminSettings>>) => {
    const {
      throughput_effective: _te,
      telegram_bot_token_configured: _tb,
      railway_token_configured: _rw,
      reference_templates_catalog: _rc,
      disk_monitor_live: _diskLive,
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
      setWebauthnEnabled(Boolean(me.webauthn_enabled));
      setMfaMethod(me.mfa_method ?? null);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    void refreshTwofaStatus();
    api
      .getTheme()
      .then((data) => {
        if (data?.active_theme) setCurrentTheme(data.active_theme);
        if (data?.theme) applyTheme(data.theme);
      })
      .catch(() => {});
    api
      .getAdminSettings()
      .then((data) => {
        ingestAdminSettingsResponse(data);
        setSettingsLoading(false);
      })
      .catch(() => {
        setSettingsLoading(false);
      });
    api
      .getChatSettings()
      .then((s) => {
        const next = {
          director_standup_enabled: s.director_standup_enabled,
          director_standup_time: s.director_standup_time,
          director_standup_timezone: s.director_standup_timezone,
        };
        lastCorpPersistSigRef.current = stableStringify(next);
        corpChatHydratedRef.current = true;
        setCorpChatSettings(next);
      })
      .catch(() => {});
  }, []);

  const handleThemeChange = async (themeName: string) => {
    setThemeSaving(themeName);
    try {
      const result = await api.setTheme(themeName);
      setCurrentTheme(themeName);
      if (result?.theme) {
        applyTheme(result.theme);
      } else {
        const data = await api.getTheme();
        if (data?.theme) applyTheme(data.theme);
      }
    } catch (e) {
      console.error('Failed to set theme:', e);
    } finally {
      setThemeSaving(null);
    }
  };

  const persistSettingsPatch = async (
    patch: Record<string, unknown>,
    toastKey?: string,
  ): Promise<boolean> => {
    clearAdminAutosaveTimer();
    setSettingsSaving(true);
    setSettingsMessage(null);
    try {
      const result = await api.updateAdminSettings(patch, { clientTimeoutMs: 20_000 });
      const fresh = await api.getAdminSettings();
      ingestAdminSettingsResponse(fresh);
      lastAdminPersistSigRef.current = adminSigFromGetResponse(fresh);
      setSettingsMessage(`✅ ${result.message}`);
      window.setTimeout(() => setSettingsMessage(null), 3200);
      if (toastKey) toast.success(t(locale, toastKey));
      return true;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t(locale, 'settings.error.unknown');
      setSettingsMessage(tVars(locale, 'settings.error.saveWithMessage', { message: msg }));
      toast.error((e as Error)?.message || t(locale, 'settings.toast.saveSettingsFailed'));
      return false;
    } finally {
      setSettingsSaving(false);
    }
  };

  const handleSettingChange = (key: string, value: unknown) => {
    if (key === 'factory_on_hold') {
      const next = Boolean(value);
      setSettings((prev) => ({ ...prev, factory_on_hold: next }));
      void (async () => {
        const ok = await persistSettingsPatch(
          { factory_on_hold: next },
          next ? 'settings.toast.factoryHoldOn' : 'settings.toast.factoryHoldOff',
        );
        if (ok) window.dispatchEvent(new CustomEvent('aicom-factory-hold', { detail: next }));
      })();
      return;
    }

    if (key === 'autonomy_mode') {
      if (!settings.auto_pipeline) {
        toast.error(t(locale, 'settings.autonomyMode.requiresAutoDev'));
        return;
      }
      const next = value === 'full' ? 'full' : 'supervised';
      const prevMode = settings.autonomy_mode;
      setSettings((prev) => ({ ...prev, autonomy_mode: next }));
      clearAdminAutosaveTimer();
      setAutonomyModeSaving(true);
      void (async () => {
        try {
          await api.updateAdminSettings({ autonomy_mode: next }, { clientTimeoutMs: 20_000 });
          const fresh = await api.getAdminSettings();
          ingestAdminSettingsResponse(fresh);
          lastAdminPersistSigRef.current = adminSigFromGetResponse(fresh);
          toast.success(
            t(locale, next === 'full' ? 'settings.toast.autonomyFull' : 'settings.toast.autonomySupervised'),
          );
        } catch (e: unknown) {
          setSettings((prev) => ({ ...prev, autonomy_mode: prevMode }));
          toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.saveFailed'));
        } finally {
          setAutonomyModeSaving(false);
        }
      })();
      return;
    }

    if (key === 'local_high_throughput_enabled') {
      const next = Boolean(value);
      setSettings((prev) => ({ ...prev, local_high_throughput_enabled: next }));
      void persistSettingsPatch(
        { local_high_throughput_enabled: next },
        next ? 'settings.toast.highThroughputOn' : 'settings.toast.highThroughputOff',
      );
      return;
    }

    if (key === 'pipeline_cost_optimized') {
      const next = Boolean(value);
      const preset = next ? OPTIMIZED_QUALITY_PRESETS : LEGACY_QUALITY_PRESETS;
      setSettings((prev) => ({ ...prev, pipeline_cost_optimized: next }));
      setQualitySettings((prev) => {
        const merged = { ...prev, ...preset };
        void persistSettingsPatch(
          { pipeline_cost_optimized: next, quality: merged },
          next ? 'settings.toast.pipelineCostOptimizedOn' : 'settings.toast.pipelineCostOptimizedOff',
        );
        return merged;
      });
      return;
    }

    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleAutoPipelineToggleClick = async () => {
    if (settings.auto_pipeline) {
      setAutoGenSaving(true);
      try {
        await api.updateAdminSettings({
          auto_pipeline: false,
          auto_pipeline_interval_minutes: settings.auto_pipeline_interval_minutes,
          autonomy_mode: 'supervised',
        });
        const fresh = await api.getAdminSettings();
        ingestAdminSettingsResponse(fresh);
        lastAdminPersistSigRef.current = adminSigFromGetResponse(fresh);
        toast.success(t(locale, 'settings.toast.autoGenOff'));
      } catch (e: unknown) {
        toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.saveFailed'));
      } finally {
        setAutoGenSaving(false);
      }
      return;
    }
    setAutoGenIntervalDraft(clampAutoPipelineMinutes(settings.auto_pipeline_interval_minutes || 60));
    clearAdminAutosaveTimer();
    setAutoGenModalOpen(true);
  };

  const closeAutoGenModal = () => {
    autoGenAbortRef.current?.abort();
    autoGenAbortRef.current = null;
    clearAdminAutosaveTimer();
    setAutoGenSaving(false);
    setAutoGenModalOpen(false);
  };

  const handleAutoGenConfirm = async () => {
    if (publicDemo) {
      return;
    }
    const minutes = clampAutoPipelineMinutes(autoGenIntervalDraft);
    clearAdminAutosaveTimer();
    autoGenAbortRef.current?.abort();
    const ac = new AbortController();
    autoGenAbortRef.current = ac;
    setAutoGenSaving(true);
    const reqOpts = { signal: ac.signal, clientTimeoutMs: 20_000 };
    try {
      await api.updateAdminSettings(
        {
          auto_pipeline: true,
          auto_pipeline_interval_minutes: minutes,
        },
        reqOpts,
      );
      if (ac.signal.aborted) {
        return;
      }
      const fresh = await api.getAdminSettings();
      if (ac.signal.aborted) {
        return;
      }
      ingestAdminSettingsResponse(fresh);
      lastAdminPersistSigRef.current = adminSigFromGetResponse(fresh);
      setSettings((prev) => ({
        ...prev,
        auto_pipeline: true,
        auto_pipeline_interval_minutes: minutes,
      }));
      autoGenAbortRef.current = null;
      setAutoGenSaving(false);
      setAutoGenModalOpen(false);
      toast.success(tVars(locale, 'settings.toast.autoGenOn', { minutes: String(minutes) }));
    } catch (e: unknown) {
      if (ac.signal.aborted) {
        return;
      }
      const msg = e instanceof Error ? e.message : t(locale, 'settings.toast.saveFailed');
      toast.error(msg);
    } finally {
      if (autoGenAbortRef.current === ac) {
        autoGenAbortRef.current = null;
        setAutoGenSaving(false);
      }
    }
  };

  const buildAdminPayload = (): Record<string, unknown> => {
    const payload: Record<string, unknown> = { ...settings };
    delete payload.telegram_bot_token_configured;
    delete payload.railway_token_configured;
    delete payload.reference_templates_catalog;
    delete payload.throughput_effective;
    delete payload.pipeline_db_status;
    delete payload.pipeline_database_url_masked;
    delete (payload as Record<string, unknown>).disk_monitor_live;
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
    if (publicDemo) {
      toast.error(t(locale, 'settings.demo.settingsSaveBlocked'), { id: 'demo-settings-blocked' });
      return false;
    }
    const sig = adminPayloadSignature();
    if (sig === lastAdminPersistSigRef.current) {
      return true;
    }
    const payload = buildAdminPayload();
    setSettingsSaving(true);
    setSettingsMessage(null);
    try {
      const result = await api.updateAdminSettings(payload as Record<string, unknown>, {
        clientTimeoutMs: 20_000,
      });
      setTelegramBotTokenInput('');
      const fresh = await api.getAdminSettings();
      ingestAdminSettingsResponse(fresh);
      lastAdminPersistSigRef.current = adminSigFromGetResponse(fresh);
      setSettingsMessage(`✅ ${result.message}`);
      window.setTimeout(() => setSettingsMessage(null), 3200);
      return true;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t(locale, 'settings.error.unknown');
      setSettingsMessage(tVars(locale, 'settings.error.saveWithMessage', { message: msg }));
      toast.error((e as Error)?.message || t(locale, 'settings.toast.saveSettingsFailed'));
      return false;
    } finally {
      setSettingsSaving(false);
    }
  };

  useEffect(() => {
    if (publicDemo || settingsLoading || autoGenModalOpen || autoGenSaving || autonomyModeSaving) {
      if (publicDemo || autoGenModalOpen || autoGenSaving || autonomyModeSaving) {
        adminBaselineReadyRef.current = false;
      }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- debounced autosave intentionally keys off the settings snapshot; depending on adminPayloadSignature/persistAdminSettings (recreated each render) would reset the debounce timer on every render
  }, [settings, qualitySettings, telegramBotTokenInput, settingsLoading, publicDemo, autoGenModalOpen, autoGenSaving, autonomyModeSaving]);

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
        setSettingsMessage(t(locale, 'settings.toast.standupSaved'));
        window.setTimeout(() => setSettingsMessage(null), 2800);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : t(locale, 'settings.error.unknown');
        setSettingsMessage(tVars(locale, 'settings.error.standupWithMessage', { message: msg }));
        toast.error((e as Error)?.message || t(locale, 'settings.toast.standupSaveFailed'));
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
  }, [corpChatSettings, settingsLoading, locale]);

  const handleRevokeTelegramToken = async () => {
    if (!window.confirm(t(locale, 'settings.confirm.revokeTelegram'))) return;
    try {
      await api.updateAdminSettings({ telegram_bot_token_revoke: true } as Record<string, unknown>);
      setTelegramBotTokenInput('');
      const fresh = await api.getAdminSettings();
      ingestAdminSettingsResponse(fresh);
      lastAdminPersistSigRef.current = adminSigFromGetResponse(fresh);
      toast.success(t(locale, 'settings.toast.telegramTokenRemoved'));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.telegramRevokeFailed'));
    }
  };

  const handleTestTelegram = async () => {
    setTelegramTestBusy(true);
    try {
      await api.testTelegramNotification();
      toast.success(t(locale, 'settings.toast.telegramTestSent'));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.telegramTestFailed'));
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
      toast.error(t(locale, 'settings.toast.refSlugRequired'));
      return;
    }
    const html = refUploadHtml.trim();
    if (!html) {
      toast.error(t(locale, 'settings.toast.refHtmlRequired'));
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
      toast.success(tVars(locale, 'settings.toast.refTemplateSaved', { slug }));
      setRefUploadId('');
      setRefUploadTitle('');
      setRefUploadHtml('');
      setRefUploadCss('');
      setRefUploadJs('');
      await refreshReferenceCatalog();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.uploadFailed'));
    } finally {
      setRefUploadBusy(false);
    }
  };

  const handleReferenceTemplateDelete = async (templatePath: string) => {
    if (!window.confirm(tVars(locale, 'settings.confirm.deleteTemplate', { path: templatePath }))) {
      return;
    }
    setRefUploadBusy(true);
    try {
      await api.deleteReferenceTemplate(templatePath);
      toast.success(t(locale, 'settings.toast.templateRemoved'));
      await refreshReferenceCatalog();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t(locale, 'settings.toast.deleteFailed'));
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
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t(locale, 'settings.error.unknown');
      setDirectorMessage(tVars(locale, 'settings.error.triggerDirector', { message: msg }));
    } finally {
      setDirectorTriggering(false);
    }
  };

  return {
    locale,
    publicDemo,
    currentTheme,
    themeSaving,
    settings,
    diskMonitorLive,
    pipelineDbStatus,
    throughputEffective,
    throughputSnapshotBusy,
    telegramBotTokenConfigured,
    railwayTokenConfigured,
    telegramBotTokenInput,
    telegramTestBusy,
    settingsLoading,
    settingsSaving,
    settingsMessage,
    directorTriggering,
    directorMessage,
    corpChatSettings,
    corpChatSaving,
    referenceTemplatesCatalog,
    refUploadId,
    refUploadTitle,
    refUploadHtml,
    refUploadCss,
    refUploadJs,
    refUploadBusy,
    twofaEnabled,
    twofaPending,
    twofaModalOpen,
    twofaStep,
    twofaPassword,
    twofaUri,
    twofaSecret,
    twofaVerify,
    twofaBusy,
    disable2faModalOpen,
    disable2faPassword,
    disable2faBusy,
    webauthnEnabled,
    mfaMethod,
    passkeyBusy,
    disablePasskeyModalOpen,
    disablePasskeyPassword,
    autoGenModalOpen,
    autoGenIntervalDraft,
    autoGenSaving,
    autonomyModeSaving,
    qualityOpen,
    qualitySettings,
    adminAutosaveTimerRef,
    clampAutoPipelineMinutes,
    setCorpChatSettings,
    setRefUploadId,
    setRefUploadTitle,
    setRefUploadHtml,
    setRefUploadCss,
    setRefUploadJs,
    setTelegramBotTokenInput,
    setAutoGenIntervalDraft,
    setAutoGenModalOpen,
    setQualityOpen,
    setQualitySettings,
    setTwofaModalOpen,
    setTwofaStep,
    setTwofaPassword,
    setTwofaUri,
    setTwofaSecret,
    setTwofaVerify,
    setTwofaBusy,
    setDisable2faModalOpen,
    setDisable2faPassword,
    setDisable2faBusy,
    setDisablePasskeyModalOpen,
    setDisablePasskeyPassword,
    setPasskeyBusy,
    handleThemeChange,
    handleSettingChange,
    handleAutoPipelineToggleClick,
    handleAutoGenConfirm,
    closeAutoGenModal,
    refreshThroughputSnapshotOnly,
    persistAdminSettings,
    refreshTwofaStatus,
    handleRevokeTelegramToken,
    handleTestTelegram,
    handleReferenceTemplateUpload,
    handleReferenceTemplateDelete,
    handleTriggerDirector,
  };
}

export type SettingsTabApi = ReturnType<typeof useSettingsTabState>;
