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
} from '@/lib/api';
import { INITIAL_AGENTS_TAB_ROWS, PIPELINE_STAGE_ORDER } from '@/lib/pipelineStages';
import { formatRelativeTime, getStateColor, getStateLabel, getAgentIcon, applyTheme } from '@/lib/utils';
import { AdminLocale, detectAdminLocale, saveAdminLocale, t, tVars } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

export function DemoReplayMonitorSection({
  demoReplay,
  variant = 'monitor',
}: {
  demoReplay?: DashboardData['demo_replay'];
  /** monitor = Live Monitor tab copy; settings = Admin → Settings duplicate */
  variant?: 'monitor' | 'settings';
}) {
  const [adminCfg, setAdminCfg] = useState<DemoReplayAdminConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const [videoBlobUrl, setVideoBlobUrl] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .getDemoReplayAdmin()
      .then(setAdminCfg)
      .catch(() => setAdminCfg(null));
  }, []);

  useEffect(() => {
    if (adminCfg) {
      setTitle(adminCfg.title || '');
      setVideoUrl(adminCfg.video_url || '');
    }
  }, [adminCfg]);

  const savePatch = async (patch: Record<string, unknown>) => {
    setLoading(true);
    try {
      const r = await api.patchDemoReplay(patch);
      setAdminCfg(r);
      setErr(null);
      toast.success('Demo replay saved');
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Save failed');
      toast.error('Demo replay save failed');
    } finally {
      setLoading(false);
    }
  };

  const onPickFile = async (f: File | undefined) => {
    if (!f) return;
    setLoading(true);
    try {
      const r = await api.uploadDemoReplayVideo(f);
      setAdminCfg(r);
      setErr(null);
      toast.success('Video uploaded');
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Upload failed');
      toast.error('Upload failed');
    } finally {
      setLoading(false);
    }
  };

  /** Uploaded files: load via admin media (Bearer/cookie) — public URL 404s when volume missing the file. */
  useEffect(() => {
    let revoked: string | null = null;
    const fn = adminCfg?.media_filename;
    if (adminCfg?.source !== 'upload' || !fn || typeof window === 'undefined') {
      setVideoBlobUrl(null);
      return () => {
        if (revoked) URL.revokeObjectURL(revoked);
      };
    }
    const token = localStorage.getItem('admin_token');
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    let cancelled = false;
    void (async () => {
      try {
        const r = await fetch(`/api/admin/demo-replay/media/${encodeURIComponent(fn)}`, {
          credentials: 'include',
          headers,
        });
        if (!r.ok) {
          const pub = await fetch(`/api/public/pipeline-demo-replay`);
          if (!pub.ok) throw new Error(`HTTP ${r.status}`);
          const blob = await pub.blob();
          if (cancelled) return;
          revoked = URL.createObjectURL(blob);
          setVideoBlobUrl(revoked);
          setErr(null);
          return;
        }
        const blob = await r.blob();
        if (cancelled) return;
        revoked = URL.createObjectURL(blob);
        setVideoBlobUrl(revoked);
        setErr(null);
      } catch {
        if (!cancelled) setVideoBlobUrl(null);
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [adminCfg?.source, adminCfg?.media_filename, adminCfg?.updated_at]);

  /** Prefer PATCH response (adminCfg) so video reappears immediately after re-enabling — no dashboard refresh. */
  const playSrc = useMemo(() => {
    if (videoBlobUrl) return videoBlobUrl;
    const raw =
      adminCfg?.enabled && adminCfg.play_url
        ? adminCfg.play_url
        : demoReplay?.enabled && demoReplay.play_url
          ? demoReplay.play_url
          : null;
    if (!raw) return null;
    return raw.startsWith('http://') || raw.startsWith('https://')
      ? raw
      : typeof window !== 'undefined'
        ? `${window.location.origin}${raw}`
        : raw;
  }, [
    videoBlobUrl,
    adminCfg?.enabled,
    adminCfg?.play_url,
    demoReplay?.enabled,
    demoReplay?.play_url,
  ]);

  return (
    <GlassCard
      hover={false}
      className="!backdrop-blur-none bg-slate-950/95 [backdrop-filter:none] [-webkit-backdrop-filter:none] border border-white/10 shadow-xl"
    >
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-4">
        <div>
          <h3 className="text-lg font-semibold text-white">Demo replay</h3>
          <p className="text-sm text-gray-500 mt-1 max-w-xl">
            Screen recording of landing/pipeline flow (Playwright or manual). Shown here for operators; metrics stream also carries{' '}
            <code className="text-xs text-indigo-300">demo_replay</code> for other clients.
          </p>
          {variant === 'settings' && (
            <p className="text-xs text-gray-600 mt-2 max-w-xl">
              Turn <strong className="text-gray-400">Show on Live Monitor</strong> back on here if you disabled it — no need to edit{' '}
              <code className="text-[11px] text-indigo-300/90">pipeline_demo_replay.json</code>. Same controls exist under{' '}
              <strong className="text-gray-400">Live Monitor</strong>.
            </p>
          )}
        </div>
        <label className="flex w-full flex-col gap-1 self-stretch sm:w-auto sm:shrink-0 sm:items-end cursor-pointer select-none">
          <span className="flex items-center justify-end gap-2 text-sm text-gray-300 sm:justify-end">
            <input
              type="checkbox"
              className="rounded border-white/20 bg-white/5"
              checked={!!adminCfg?.enabled}
              disabled={loading || !adminCfg}
              onChange={(e) => savePatch({ enabled: e.target.checked })}
            />
            Show on Live Monitor
          </span>
          {!adminCfg?.enabled && adminCfg && (
            <span className="text-[10px] text-amber-500/90 max-w-[14rem] text-right leading-snug">
              Off only hides video from the monitor & dashboard payload — URL/upload stay saved. Check the box to publish again.
            </span>
          )}
        </label>
      </div>

      {playSrc || (adminCfg?.source === 'upload' && adminCfg.media_filename) ? (
        /* Video + backdrop-filter on same ancestor → Chromium often composites a blurry / stuck first frame. */
        <div className="relative mb-4 isolate overflow-hidden rounded-lg border border-white/10 bg-black">
          {playSrc ? (
          <video
            key={playSrc}
            controls
            playsInline
            className="relative z-10 block w-full max-h-[min(52vh,520px)] object-contain bg-black [transform:translateZ(0)]"
            src={playSrc}
            preload="auto"
            onError={(e) => {
            const el = e.currentTarget;
            const code = el.error?.code;
            const hint =
              code === 2
                ? 'Network error loading media.'
                : code === 3
                  ? 'Decode error — try re-encoding (H.264/AAC for .mp4, VP9 for .webm).'
                  : code === 4
                    ? 'Source not supported for this browser.'
                    : 'Playback failed.';
            setErr(
              `${hint} If this is an uploaded file, use “Upload video” again or check the network tab for 404/403 on the media URL.`,
            );
          }}
          />
          ) : (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin" />
              Loading video…
            </div>
          )}
        </div>
      ) : (
        <div className="mb-4 rounded-lg border border-dashed border-white/15 bg-white/[0.02] px-4 py-8 text-center text-sm text-gray-500">
          Enable above and set a URL or upload a file (.webm / .mp4 / .mov).
        </div>
      )}

      {err && <p className="text-sm text-red-400 mb-3">{err}</p>}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <label className="text-xs text-gray-500">Title</label>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Landing generation walkthrough"
            disabled={loading}
          />
        </div>
        <div className="space-y-2">
          <label className="text-xs text-gray-500">External URL or path</label>
          <Input
            value={videoUrl}
            onChange={(e) => setVideoUrl(e.target.value)}
            placeholder="https://… or /your-hosted/demo.webm"
            disabled={loading}
          />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 mt-4">
        <Button
          variant="secondary"
          size="sm"
          disabled={loading}
          onClick={() =>
            savePatch({
              title,
              video_url: videoUrl.trim() === '' ? '' : videoUrl.trim(),
            })
          }
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          <span className="ml-1">Save URL</span>
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept=".webm,.mp4,.mov,video/webm,video/mp4"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            void onPickFile(f);
            e.target.value = '';
          }}
        />
        <Button variant="secondary" size="sm" disabled={loading} onClick={() => fileRef.current?.click()}>
          <Upload className="w-4 h-4" />
          <span className="ml-1">Upload video</span>
        </Button>
        {adminCfg?.source === 'upload' && adminCfg.media_filename ? (
          <span className="text-xs text-gray-500">
            File: <span className="font-mono text-gray-400">{adminCfg.media_filename}</span>
          </span>
        ) : null}
      </div>
    </GlassCard>
  );
}
