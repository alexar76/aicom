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

export function HumanReviewGatePanel({
  product,
  onPatch,
}: {
  product: Record<string, unknown>;
  onPatch: (productId: string, patch: Record<string, unknown>) => void;
}) {
  const st = String(product.state || '').toUpperCase();
  const [approveNote, setApproveNote] = useState('');
  const [rejectNotes, setRejectNotes] = useState('');
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null);

  if (st !== 'HUMAN_REVIEW_PENDING') return null;

  const submitApprove = async () => {
    setBusy('approve');
    try {
      await api.postPipelineHumanReviewApprove(String(product.id), { note: approveNote.trim() });
      onPatch(String(product.id), { state: 'SALES_ACTIVE' });
      toast.success('Approved — sales stage queued');
      setApproveNote('');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Approve failed');
    } finally {
      setBusy(null);
    }
  };

  const submitReject = async () => {
    if (rejectNotes.trim().length < 8) {
      toast.error('Rejection notes must be at least 8 characters');
      return;
    }
    setBusy('reject');
    try {
      await api.postPipelineHumanReviewReject(String(product.id), rejectNotes.trim());
      onPatch(String(product.id), { state: 'BUG_FOUND' });
      toast.success('Rejected — developer rework queued');
      setRejectNotes('');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Reject failed');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mb-4 rounded-xl border border-amber-500/35 bg-amber-500/10 p-3 space-y-3">
      <p className="text-xs uppercase tracking-wide text-amber-200/90">Post-DevOps human gate</p>
      <p className="text-[11px] text-gray-400 leading-relaxed">
        Full-software pipeline stops here until you approve going to sales or send back to development with notes.
        Approval also records human-review feedback for release gates and may trigger{' '}
        <span className="font-mono text-amber-100/90">AIFACTORY_PREVIEW_DEPLOY_WEBHOOK_URL</span> if set.
      </p>
      <div className="grid sm:grid-cols-2 gap-3">
        <div className="space-y-2">
          <label className="text-[10px] text-gray-500 block">Approve note (optional)</label>
          <textarea
            value={approveNote}
            onChange={(e) => setApproveNote(e.target.value)}
            rows={2}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white placeholder:text-gray-600"
            placeholder="Ship checklist, staging URL, …"
          />
          <Button
            type="button"
            variant="primary"
            size="sm"
            disabled={busy !== null}
            onClick={() => void submitApprove()}
          >
            {busy === 'approve' ? 'Approving…' : 'Approve → sales'}
          </Button>
        </div>
        <div className="space-y-2">
          <label className="text-[10px] text-gray-500 block">Reject — instructions for developer (min 8 chars)</label>
          <textarea
            value={rejectNotes}
            onChange={(e) => setRejectNotes(e.target.value)}
            rows={3}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white placeholder:text-gray-600"
            placeholder="What must change before sales…"
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={busy !== null}
            onClick={() => void submitReject()}
          >
            {busy === 'reject' ? 'Rejecting…' : 'Reject → DEV_FIXING'}
          </Button>
        </div>
      </div>
    </div>
  );
}
