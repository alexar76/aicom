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
import { ProductImprovementHoldToggle } from '@/components/admin/pipeline/ProductImprovementHoldToggle';
import { ProductPipelineHoldToggle } from '@/components/admin/pipeline/ProductPipelineHoldToggle';

export function StorefrontFollowupPanel({
  product,
  onPatch,
}: {
  product: Record<string, unknown>;
  onPatch: (productId: string, patch: Record<string, unknown>) => void;
}) {
  const locale = detectAdminLocale();
  const st = String(product.state || '').toUpperCase();
  const showPanel = st === 'COMPLETED' || st === 'DEPLOYED_PRODUCTION';

  const sf = (product.storefront_followup || {}) as Record<string, unknown>;
  const visible = Boolean(product.storefront_visible);
  const reasons: string[] = Array.isArray(product.storefront_gate_reasons)
    ? (product.storefront_gate_reasons as string[])
    : [];

  const [followupSel, setFollowupSel] = useState<string>(
    sf.followup === 'planned' || sf.followup === 'not_pursuing' ? String(sf.followup) : '',
  );
  const [plannedNotes, setPlannedNotes] = useState<string>(String(sf.planned_notes || ''));
  const [notPursuingReason, setNotPursuingReason] = useState<string>(
    String(sf.not_pursuing_reason || ''),
  );
  const [qualitySel, setQualitySel] = useState<string>(
    sf.quality_score != null && sf.quality_score !== '' ? String(sf.quality_score) : '',
  );
  const [forceList, setForceList] = useState<boolean>(Boolean(sf.admin_force_list));
  const [forceNote, setForceNote] = useState<string>(String(sf.admin_force_list_note || ''));
  const [hideFromStorefront, setHideFromStorefront] = useState<boolean>(Boolean(sf.admin_hide_from_storefront));
  const mc0 = (product.storefront_marketing_copy || {}) as Record<string, unknown>;
  const [mktProductName, setMktProductName] = useState<string>(String(mc0.product_name || ''));
  const [mktTagline, setMktTagline] = useState<string>(String(mc0.tagline || ''));
  const [mktShort, setMktShort] = useState<string>(String(mc0.short_description || ''));
  const [mktSelling, setMktSelling] = useState<string>(String(mc0.selling_description || ''));
  const [mktLong, setMktLong] = useState<string>(String(mc0.long_description || ''));
  const [reworkNotes, setReworkNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [savingAdmin, setSavingAdmin] = useState(false);
  const [savingMarketing, setSavingMarketing] = useState(false);
  const [savingPrice, setSavingPrice] = useState(false);
  const [priceDraft, setPriceDraft] = useState('');
  const [reworkLoading, setReworkLoading] = useState(false);

  useEffect(() => {
    const f = (product.storefront_followup || {}) as Record<string, unknown>;
    setFollowupSel(
      f.followup === 'planned' || f.followup === 'not_pursuing' ? String(f.followup) : '',
    );
    setPlannedNotes(String(f.planned_notes || ''));
    setNotPursuingReason(String(f.not_pursuing_reason || ''));
    setQualitySel(f.quality_score != null && f.quality_score !== '' ? String(f.quality_score) : '');
    setForceList(Boolean(f.admin_force_list));
    setForceNote(String(f.admin_force_list_note || ''));
    setHideFromStorefront(Boolean(f.admin_hide_from_storefront));
  }, [product.id, product.storefront_followup]);

  useEffect(() => {
    const m = (product.storefront_marketing_copy || {}) as Record<string, unknown>;
    setMktProductName(String(m.product_name || ''));
    setMktTagline(String(m.tagline || ''));
    setMktShort(String(m.short_description || ''));
    setMktSelling(String(m.selling_description || ''));
    setMktLong(String(m.long_description || ''));
  }, [product.id, product.storefront_marketing_copy]);

  useEffect(() => {
    const adm =
      typeof product.storefront_admin_price_usdt === 'number' && !Number.isNaN(product.storefront_admin_price_usdt)
        ? product.storefront_admin_price_usdt
        : null;
    const eff =
      typeof product.storefront_effective_price_usdt === 'number' &&
      !Number.isNaN(product.storefront_effective_price_usdt)
        ? product.storefront_effective_price_usdt
        : null;
    setPriceDraft(adm != null ? String(adm) : eff != null ? String(eff) : '');
  }, [product.id, product.storefront_admin_price_usdt, product.storefront_effective_price_usdt]);

  const saveFollowup = async () => {
    setSaving(true);
    try {
      const body = {
        followup: (followupSel === '' ? null : followupSel) as 'planned' | 'not_pursuing' | null,
        planned_notes: followupSel === 'planned' ? plannedNotes : undefined,
        not_pursuing_reason: followupSel === 'not_pursuing' ? notPursuingReason : undefined,
      };
      const res = await api.updatePipelineProductFollowup(String(product.id), body);
      onPatch(String(product.id), {
        storefront_followup: res.storefront_followup as Record<string, unknown>,
        ...(typeof res.storefront_visible === 'boolean' ? { storefront_visible: res.storefront_visible } : {}),
        ...(Array.isArray(res.storefront_gate_reasons)
          ? { storefront_gate_reasons: res.storefront_gate_reasons }
          : {}),
      });
      toast.success('Storefront follow-up saved');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const saveQuality = async () => {
    if (!qualitySel) {
      toast.error('Choose a score from 1 to 5');
      return;
    }
    setSavingAdmin(true);
    try {
      const res = await api.updatePipelineStorefrontAdmin(String(product.id), {
        quality_score: Number(qualitySel),
      });
      onPatch(String(product.id), {
        storefront_followup: res.storefront_followup as Record<string, unknown>,
        ...(typeof res.storefront_visible === 'boolean' ? { storefront_visible: res.storefront_visible } : {}),
        ...(Array.isArray(res.storefront_gate_reasons)
          ? { storefront_gate_reasons: res.storefront_gate_reasons }
          : {}),
      });
      toast.success('Quality score saved');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSavingAdmin(false);
    }
  };

  const saveHideGuard = async () => {
    setSavingAdmin(true);
    try {
      const res = await api.updatePipelineStorefrontAdmin(String(product.id), {
        admin_hide_from_storefront: hideFromStorefront,
      });
      const fu = res.storefront_followup as Record<string, unknown>;
      if (!hideFromStorefront) {
        setForceList(Boolean(fu.admin_force_list));
      } else {
        setForceList(false);
        setForceNote('');
      }
      onPatch(String(product.id), {
        storefront_followup: fu,
        ...(typeof res.storefront_visible === 'boolean' ? { storefront_visible: res.storefront_visible } : {}),
        ...(Array.isArray(res.storefront_gate_reasons)
          ? { storefront_gate_reasons: res.storefront_gate_reasons }
          : {}),
      });
      toast.success(hideFromStorefront ? 'Product hidden from public storefront' : 'Admin hide cleared');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSavingAdmin(false);
    }
  };

  const clearHideGuard = async () => {
    setSavingAdmin(true);
    try {
      const res = await api.updatePipelineStorefrontAdmin(String(product.id), {
        clear_hide_from_storefront: true,
      });
      setHideFromStorefront(false);
      const fu = res.storefront_followup as Record<string, unknown>;
      setForceList(Boolean(fu.admin_force_list));
      onPatch(String(product.id), {
        storefront_followup: fu,
        ...(typeof res.storefront_visible === 'boolean' ? { storefront_visible: res.storefront_visible } : {}),
        ...(Array.isArray(res.storefront_gate_reasons)
          ? { storefront_gate_reasons: res.storefront_gate_reasons }
          : {}),
      });
      toast.success('Admin hide flag removed');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSavingAdmin(false);
    }
  };

  const saveMarketingCopy = async () => {
    setSavingMarketing(true);
    try {
      const res = await api.patchPipelineMarketplaceCopy(String(product.id), {
        product_name: mktProductName.trim(),
        tagline: mktTagline.trim(),
        short_description: mktShort.trim(),
        selling_description: mktSelling.trim(),
        long_description: mktLong.trim(),
      });
      onPatch(String(product.id), {
        storefront_marketing_copy: res.storefront_marketing_copy as Record<string, unknown>,
        ...(typeof res.storefront_visible === 'boolean' ? { storefront_visible: res.storefront_visible } : {}),
        ...(Array.isArray(res.storefront_gate_reasons)
          ? { storefront_gate_reasons: res.storefront_gate_reasons }
          : {}),
      });
      toast.success('Marketplace copy saved');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSavingMarketing(false);
    }
  };

  const saveStorefrontPrice = async () => {
    const raw = priceDraft.replace(',', '.').trim();
    const v = parseFloat(raw);
    if (!Number.isFinite(v) || v <= 0) {
      toast.error('Enter a positive USDT amount');
      return;
    }
    setSavingPrice(true);
    try {
      const res = await api.patchPipelineStorefrontPricing(String(product.id), {
        admin_storefront_usdt: v,
      });
      const sp = res.storefront_pricing as {
        admin_storefront_usdt?: number | null;
        storefront_checkout_usdt: number;
      };
      onPatch(String(product.id), {
        storefront_effective_price_usdt: sp.storefront_checkout_usdt,
        storefront_admin_price_usdt: sp.admin_storefront_usdt ?? null,
        storefront_price_tier: 'admin',
        ...(typeof res.storefront_visible === 'boolean' ? { storefront_visible: res.storefront_visible } : {}),
        ...(Array.isArray(res.storefront_gate_reasons)
          ? { storefront_gate_reasons: res.storefront_gate_reasons }
          : {}),
      });
      toast.success('Storefront / checkout price saved');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSavingPrice(false);
    }
  };

  const clearStorefrontPriceOverride = async () => {
    setSavingPrice(true);
    try {
      const res = await api.patchPipelineStorefrontPricing(String(product.id), {
        clear_admin_storefront_usdt: true,
      });
      const sp = res.storefront_pricing as {
        admin_storefront_usdt?: number | null;
        storefront_checkout_usdt: number;
      };
      onPatch(String(product.id), {
        storefront_effective_price_usdt: sp.storefront_checkout_usdt,
        storefront_admin_price_usdt: sp.admin_storefront_usdt ?? null,
        ...(typeof res.storefront_visible === 'boolean' ? { storefront_visible: res.storefront_visible } : {}),
        ...(Array.isArray(res.storefront_gate_reasons)
          ? { storefront_gate_reasons: res.storefront_gate_reasons }
          : {}),
      });
      setPriceDraft(String(sp.storefront_checkout_usdt));
      toast.success('Manual price cleared — automatic pricing applies again');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Clear failed');
    } finally {
      setSavingPrice(false);
    }
  };

  const saveForceList = async () => {
    if (forceList && forceNote.trim().length < 5) {
      toast.error('Add a justification (min 5 characters) when forcing storefront listing');
      return;
    }
    setSavingAdmin(true);
    try {
      const res = await api.updatePipelineStorefrontAdmin(String(product.id), {
        admin_force_list: forceList,
        admin_force_list_note: forceList ? forceNote.trim() : undefined,
      });
      const fu = res.storefront_followup as Record<string, unknown>;
      onPatch(String(product.id), {
        storefront_followup: fu,
        ...(typeof res.storefront_visible === 'boolean' ? { storefront_visible: res.storefront_visible } : {}),
        ...(Array.isArray(res.storefront_gate_reasons)
          ? { storefront_gate_reasons: res.storefront_gate_reasons }
          : {}),
      });
      toast.success(forceList ? 'Forced listing enabled' : 'Listing follows automatic gates only');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSavingAdmin(false);
    }
  };

  const clearForce = async () => {
    setSavingAdmin(true);
    try {
      const res = await api.updatePipelineStorefrontAdmin(String(product.id), { clear_force_list: true });
      setForceList(false);
      setForceNote('');
      onPatch(String(product.id), {
        storefront_followup: res.storefront_followup as Record<string, unknown>,
        ...(typeof res.storefront_visible === 'boolean' ? { storefront_visible: res.storefront_visible } : {}),
        ...(Array.isArray(res.storefront_gate_reasons)
          ? { storefront_gate_reasons: res.storefront_gate_reasons }
          : {}),
      });
      toast.success('Admin listing override removed');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSavingAdmin(false);
    }
  };

  const submitRework = async () => {
    if (reworkNotes.trim().length < 8) {
      toast.error('Instructions must be at least 8 characters');
      return;
    }
    if (!window.confirm('Send this product to developer rework (BUG_FOUND → DEV_FIXING)?')) return;
    setReworkLoading(true);
    try {
      await api.postPipelineHumanRework(String(product.id), reworkNotes.trim());
      onPatch(String(product.id), { state: 'BUG_FOUND' });
      toast.success('Rework queued — developer task pending');
      setReworkNotes('');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setReworkLoading(false);
    }
  };

  if (!showPanel) return null;

  return (
    <div className="mb-4 rounded-xl border border-white/10 bg-white/[0.02] p-3 space-y-3">
      <ProductImprovementHoldToggle
        locale={locale}
        productId={String(product.id)}
        storefrontFollowup={sf}
        onPatch={onPatch}
      />
      <ProductPipelineHoldToggle
        locale={locale}
        productId={String(product.id)}
        storefrontFollowup={sf}
        pipelineFocusActive={Boolean(product.pipeline_focus_active)}
        onPatch={onPatch}
      />
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-gray-500">Storefront</span>
        {visible ? (
          <Badge variant="success">Listed on storefront</Badge>
        ) : (
          <Badge variant="warning">Not on storefront</Badge>
        )}
        {sf.followup === 'planned' && <Badge variant="info">Rework planned</Badge>}
        {sf.followup === 'not_pursuing' && <Badge variant="error">Not pursuing listing</Badge>}
        {sf.quality_score != null && sf.quality_score !== '' && (
          <Badge variant="default">Score {String(sf.quality_score)}/5</Badge>
        )}
        {Boolean(sf.admin_force_list) && <Badge variant="info">Admin force-list</Badge>}
        {Boolean(sf.admin_hide_from_storefront) && <Badge variant="error">Hidden (admin)</Badge>}
      </div>
      {Boolean(sf.admin_force_list) && (
        <p className="text-xs text-cyan-200/90 bg-cyan-500/10 border border-cyan-500/20 rounded-lg px-2 py-2">
          Admin override: product is shown on the public storefront even when automatic quality gates fail (generated code is still required).
        </p>
      )}
      {!visible && reasons.includes('hidden_from_public_storefront') && (
        <p className="text-xs text-rose-200/90 bg-rose-500/10 border border-rose-500/25 rounded-lg px-2 py-2">
          Not shown publicly: “Not pursuing” follow-up and/or admin “Hide from public storefront” is on — shoppers get no
          listing row and the product detail URL responds as missing (404).
        </p>
      )}
      {!visible && reasons.length > 0 && (
        <div className="text-xs text-amber-200/90 bg-amber-500/10 border border-amber-500/20 rounded-lg px-2 py-2">
          <span className="text-amber-300/80 font-medium">Gate signals (why not listed): </span>
          <ul className="list-disc list-inside mt-1 text-gray-300">
            {reasons.map((r) => (
              <li key={r} className="font-mono text-[11px]">
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid sm:grid-cols-2 gap-2 items-end">
        <div>
          <label className="text-[10px] text-gray-500 block mb-1">Manual follow-up</label>
          <select
            value={followupSel}
            onChange={(e) => setFollowupSel(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white"
          >
            <option value="">Not set</option>
            <option value="planned">Plan to rework toward storefront</option>
            <option value="not_pursuing">Not pursuing storefront listing</option>
          </select>
        </div>
        <Button type="button" variant="primary" size="sm" disabled={saving} onClick={() => void saveFollowup()}>
          {saving ? 'Saving…' : 'Save label'}
        </Button>
      </div>
      {followupSel === 'planned' && (
        <div>
          <label className="text-[10px] text-gray-500 block mb-1">Notes (optional)</label>
          <textarea
            value={plannedNotes}
            onChange={(e) => setPlannedNotes(e.target.value)}
            rows={2}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white placeholder:text-gray-600"
            placeholder="What to fix first, owner, rough ETA…"
          />
        </div>
      )}
      {followupSel === 'not_pursuing' && (
        <div>
          <label className="text-[10px] text-gray-500 block mb-1">Why not listing (required to save)</label>
          <textarea
            value={notPursuingReason}
            onChange={(e) => setNotPursuingReason(e.target.value)}
            rows={3}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white placeholder:text-gray-600"
            placeholder="Business decision, ROI, experiment ended, gates not worth it…"
          />
        </div>
      )}

      <div className="border-t border-white/10 pt-3 space-y-2">
        <p className="text-xs uppercase tracking-wide text-gray-500">Public storefront guard</p>
        <p className="text-[11px] text-gray-500">
          Removes the product from the public marketplace (listing + detail), regardless of quality gates. Clears
          forced listing until you clear this flag.
        </p>
        <label className="flex items-start gap-2 text-sm text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            className="mt-1 rounded border-white/20"
            checked={hideFromStorefront}
            onChange={(e) => setHideFromStorefront(e.target.checked)}
          />
          <span>Hide from public storefront (admin)</span>
        </label>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={savingAdmin}
            onClick={() => void saveHideGuard()}
          >
            Apply visibility guard
          </Button>
          {Boolean(sf.admin_hide_from_storefront) && (
            <Button type="button" variant="ghost" size="sm" disabled={savingAdmin} onClick={() => void clearHideGuard()}>
              Clear admin hide
            </Button>
          )}
        </div>
      </div>

      <div className="border-t border-white/10 pt-3 space-y-2">
        <p className="text-xs uppercase tracking-wide text-gray-500">Human evaluation</p>
        <div className="flex flex-wrap gap-2 items-end">
          <div>
            <label className="text-[10px] text-gray-500 block mb-1">Quality score (1–5)</label>
            <select
              value={qualitySel}
              onChange={(e) => setQualitySel(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white min-w-[5rem]"
            >
              <option value="">—</option>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={String(n)}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={savingAdmin || !qualitySel}
            onClick={() => void saveQuality()}
          >
            Save score
          </Button>
        </div>
      </div>

      <div className="border-t border-white/10 pt-3 space-y-2">
        <p className="text-xs uppercase tracking-wide text-gray-500">Force public storefront</p>
        {(Boolean(sf.admin_hide_from_storefront) || hideFromStorefront) && (
          <p className="text-[11px] text-amber-200/85">
            Clear “Hide from public storefront” above before forcing listing (or the backend will reject).
          </p>
        )}
        <label className="flex items-start gap-2 text-sm text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            className="mt-1 rounded border-white/20"
            checked={forceList}
            disabled={Boolean(sf.admin_hide_from_storefront || hideFromStorefront)}
            onChange={(e) => setForceList(e.target.checked)}
          />
          <span>List on storefront even if automatic quality gates fail (does not replace missing code).</span>
        </label>
        {forceList && (
          <div>
            <label className="text-[10px] text-gray-500 block mb-1">Justification (required)</label>
            <textarea
              value={forceNote}
              onChange={(e) => setForceNote(e.target.value)}
              rows={2}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white placeholder:text-gray-600"
              placeholder="Why publish despite gates…"
            />
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={savingAdmin || Boolean(sf.admin_hide_from_storefront || hideFromStorefront)}
            onClick={() => void saveForceList()}
          >
            Apply listing decision
          </Button>
          {Boolean(sf.admin_force_list) && (
            <Button type="button" variant="ghost" size="sm" disabled={savingAdmin} onClick={() => void clearForce()}>
              Remove override
            </Button>
          )}
        </div>
      </div>

      <div className="border-t border-white/10 pt-3 space-y-3">
        <p className="text-xs uppercase tracking-wide text-gray-500">Marketplace copy</p>
        <p className="text-[11px] text-gray-500">
          Stored in marketing artifacts — used for storefront cards and product detail (name, tagline, descriptions).
          Filled by the Marketing agent when the pipeline reaches the marketing stage; edit here to override listing text.
        </p>
        <div>
          <label className="text-[10px] text-gray-500 block mb-1">Product name (marketing)</label>
          <input
            type="text"
            value={mktProductName}
            onChange={(e) => setMktProductName(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white placeholder:text-gray-600"
            placeholder="Listing title"
          />
        </div>
        <div>
          <label className="text-[10px] text-gray-500 block mb-1">Tagline</label>
          <input
            type="text"
            value={mktTagline}
            onChange={(e) => setMktTagline(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white placeholder:text-gray-600"
          />
        </div>
        <div>
          <label className="text-[10px] text-gray-500 block mb-1">Short description</label>
          <textarea
            value={mktShort}
            onChange={(e) => setMktShort(e.target.value)}
            rows={2}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white placeholder:text-gray-600"
          />
        </div>
        <div>
          <label className="text-[10px] text-gray-500 block mb-1">Selling description</label>
          <textarea
            value={mktSelling}
            onChange={(e) => setMktSelling(e.target.value)}
            rows={3}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white placeholder:text-gray-600"
          />
        </div>
        <div>
          <label className="text-[10px] text-gray-500 block mb-1">Long description</label>
          <textarea
            value={mktLong}
            onChange={(e) => setMktLong(e.target.value)}
            rows={4}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white placeholder:text-gray-600"
          />
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={savingMarketing}
          onClick={() => void saveMarketingCopy()}
        >
          {savingMarketing ? 'Saving…' : 'Save marketplace copy'}
        </Button>
      </div>

      <div className="border-t border-white/10 pt-3 space-y-2">
        <p className="text-xs uppercase tracking-wide text-gray-500">Storefront &amp; checkout price (USDT)</p>
        <p className="text-[11px] text-gray-500">
          Overrides automatic sales/marketing pricing for public cards and crypto checkout. Stored in{' '}
          <code className="text-[10px] text-cyan-300/90">sales_config.json</code> →{' '}
          <code className="text-[10px] text-cyan-300/90">admin_storefront_usdt</code>. When unset, the Sales /
          Marketing agents&apos; tier or the default (~4.99 USDT) applies.
        </p>
        {typeof product.storefront_effective_price_usdt === 'number' && (
          <p className="text-[11px] text-gray-400">
            Current effective:{' '}
            <span className="text-white font-medium">{product.storefront_effective_price_usdt}</span> USDT
            {typeof product.storefront_price_tier === 'string' && product.storefront_price_tier ? (
              <span className="text-gray-500"> · tier: {product.storefront_price_tier}</span>
            ) : null}
            {product.storefront_admin_price_usdt != null ? (
              <span className="text-amber-200/90"> · admin override active</span>
            ) : null}
          </p>
        )}
        <div className="flex flex-wrap gap-2 items-end">
          <div className="min-w-[8rem] flex-1">
            <label className="text-[10px] text-gray-500 block mb-1">USDT amount</label>
            <Input
              type="text"
              inputMode="decimal"
              value={priceDraft}
              onChange={(e) => setPriceDraft(e.target.value)}
              placeholder="e.g. 9.99"
              className="bg-white/5 border-white/10"
            />
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={savingPrice}
            onClick={() => void saveStorefrontPrice()}
          >
            {savingPrice ? 'Saving…' : 'Save price'}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={savingPrice || product.storefront_admin_price_usdt == null}
            onClick={() => void clearStorefrontPriceOverride()}
          >
            Clear override
          </Button>
        </div>
      </div>

      <div className="border-t border-white/10 pt-3 space-y-2">
        <p className="text-xs uppercase tracking-wide text-gray-500">Send to rework (pipeline)</p>
        <p className="text-[11px] text-gray-500">
          Queues BUG_FOUND → developer DEV_FIXING (same repair path as support). Requires completed product with spare repair budget.
        </p>
        <textarea
          value={reworkNotes}
          onChange={(e) => setReworkNotes(e.target.value)}
          rows={3}
          className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-white placeholder:text-gray-600"
          placeholder="Instructions for the developer agent (min 8 characters)…"
        />
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={reworkLoading}
          onClick={() => void submitRework()}
        >
          {reworkLoading ? 'Queueing…' : 'Queue developer rework'}
        </Button>
      </div>
    </div>
  );
}
