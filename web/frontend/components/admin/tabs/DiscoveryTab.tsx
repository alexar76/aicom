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

export function DiscoveryTab({ locale }: { locale: AdminLocale }) {
  const [queue, setQueue] = useState<any[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [minScore, setMinScore] = useState('');

  const refresh = async (createProduct: boolean) => {
    setLoading(true);
    try {
      const run = await api.runDiscovery(createProduct, 12);
      const x = await api.getDiscoveryIdeas(20);
      setQueue(x.ranked_ideas || []);
      setMeta(x);
      if (createProduct && run?.created_product_id) {
        toast.success(tVars(locale, 'discovery.toastQueuedWithId', { id: run.created_product_id }));
      } else if (createProduct) {
        toast.success(t(locale, 'discovery.queueTop'));
      } else {
        toast.success(t(locale, 'discovery.toastRefreshed'));
      }
    } catch (e: any) {
      toast.error(e?.message || 'Discovery refresh failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    api.getDiscoveryIdeas(20).then((x) => {
      setQueue(x.ranked_ideas || []);
      setMeta(x);
    }).catch(() => {});
  }, []);

  const queueCategories = useMemo(
    () =>
      Array.from(
        new Set(
          queue
            .map((idea: any) => String(idea?.category || ''))
            .filter(Boolean)
        )
      ).sort(),
    [queue]
  );

  const filteredQueue = useMemo(() => {
    const q = query.trim().toLowerCase();
    const min = minScore.trim() === '' ? null : Number(minScore);
    return queue.filter((idea: any) => {
      const category = String(idea?.category || '');
      if (categoryFilter !== 'all' && category !== categoryFilter) return false;
      const scoreNum = Number(idea?.balanced_score ?? idea?.score_total ?? 0);
      if (min != null && Number.isFinite(min) && scoreNum < min) return false;
      if (!q) return true;
      const text = String(idea?.idea || '').toLowerCase();
      return text.includes(q) || category.toLowerCase().includes(q);
    });
  }, [queue, query, categoryFilter, minScore]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="text-xl font-semibold text-white">{t(locale, 'discovery.pageTitle')}</h2>
        <Badge variant="info" className="text-xs">
          {queue.length} {t(locale, 'discovery.ideasLabel')}
        </Badge>
        <Badge variant="info" className="text-xs">
          {t(locale, 'discovery.signalsLabel')} {meta?.signals_total ?? 0}
        </Badge>
        <Button variant="secondary" size="sm" onClick={() => refresh(false)} disabled={loading} className="ml-auto">
          {loading ? t(locale, 'discovery.refreshing') : t(locale, 'discovery.refresh')}
        </Button>
        <Button variant="secondary" size="sm" onClick={() => refresh(true)} disabled={loading}>
          {loading ? t(locale, 'discovery.queueing') : t(locale, 'discovery.queueTop')}
        </Button>
      </div>
      <GlassCard>
        <FilterControlsPanel
          onReset={() => {
            setQuery('');
            setCategoryFilter('all');
            setMinScore('');
          }}
          summary={`${filteredQueue.length} / ${queue.length}`}
          gridClassName="grid grid-cols-1 md:grid-cols-4 gap-2 mb-3"
        >
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search idea text/category..."
          />
          <FilterSelect
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="all">All categories</option>
            {queueCategories.map((cat) => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </FilterSelect>
          <FilterNumberInput
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            placeholder="Min score (e.g. 8)"
          />
        </FilterControlsPanel>
        {filteredQueue.length === 0 ? (
          <p className="text-sm text-gray-400">{t(locale, 'discovery.empty')}</p>
        ) : (
          <div className="space-y-2">
            {filteredQueue.map((idea: any, idx: number) => (
              <div key={`${idea.idea}-${idx}`} className="p-3 rounded-lg bg-white/5 border border-white/10">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-xs text-gray-400">#{idx + 1} · {idea.category}</span>
                  <span className="text-xs text-cyan-300">
                    {Number(idea.balanced_score ?? idea.score_total ?? 0).toFixed(2)}
                  </span>
                </div>
                <p className="text-sm text-white">{idea.idea}</p>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
