'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  LayoutGrid,
  Loader2,
  Copy,
  ExternalLink,
  GitCompare,
  MonitorSmartphone,
  Radio,
  Bell,
  Layers,
  Save,
  Plus,
  Link2,
  BookOpen,
  X,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { ActionableFailurePanel } from '@/components/ui/ActionableFailurePanel';
import api from '@/lib/api';
import { resolveActionableFailure } from '@/lib/actionableErrors';
import { fetchPipelineCatalogPageSingleMode } from '@/lib/pipelineCatalogFetch';
import toast from 'react-hot-toast';
import { useWorkshopCanvas } from '@/hooks/admin/useWorkshopCanvas';

type Row = Record<string, unknown> & { id?: string; state?: string; idea?: string };

function groupByState(rows: Row[]): Map<string, Row[]> {
  const m = new Map<string, Row[]>();
  for (const r of rows) {
    const st = String(r.state || 'UNKNOWN').toUpperCase();
    if (!m.has(st)) m.set(st, []);
    m.get(st)!.push(r);
  }
  return new Map([...m.entries()].sort((a, b) => b[1].length - a[1].length));
}

function urlBase64ToUint8Array(base64String: string) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) outputArray[i] = rawData.charCodeAt(i);
  return outputArray;
}

export function WorkshopTab() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [boardFailure, setBoardFailure] = useState<ReturnType<typeof resolveActionableFailure> | null>(null);
  const [diffFailure, setDiffFailure] = useState<ReturnType<typeof resolveActionableFailure> | null>(null);
  const [patternFailure, setPatternFailure] = useState<ReturnType<typeof resolveActionableFailure> | null>(null);
  const [pushFailure, setPushFailure] = useState<ReturnType<typeof resolveActionableFailure> | null>(null);
  const [pushTestFailure, setPushTestFailure] = useState<ReturnType<typeof resolveActionableFailure> | null>(null);
  const [workshopIntroDismissed, setWorkshopIntroDismissed] = useState(true);
  const [aId, setAId] = useState('');
  const [bId, setBId] = useState('');
  const [leftJson, setLeftJson] = useState('');
  const [rightJson, setRightJson] = useState('');
  const [diffBusy, setDiffBusy] = useState(false);
  const [materialKind, setMaterialKind] = useState<'spec' | 'architecture'>('spec');

  const {
    canvasPid,
    setCanvasPid,
    nodes,
    edges,
    canvasLoadBusy,
    canvasSaveBusy,
    canvasFailure,
    canvasSaveFailure,
    edgeFrom,
    setEdgeFrom,
    edgeTo,
    setEdgeTo,
    loadCanvas,
    saveCanvas,
    addStageNode,
    forkSelectedBranch,
    addEdge,
    mergeEdge,
    onNodePointerDown,
    onNodePointerMove,
    onNodePointerUp,
  } = useWorkshopCanvas();

  const [labPid, setLabPid] = useState('');
  const [labSandboxId, setLabSandboxId] = useState('');
  const [labRefreshMs, setLabRefreshMs] = useState(8000);
  const [labTick, setLabTick] = useState(0);

  const [patterns, setPatterns] = useState<any[]>([]);
  const [patternsBusy, setPatternsBusy] = useState(false);
  const [patName, setPatName] = useState('');
  const [patTags, setPatTags] = useState('');
  const [patDoc, setPatDoc] = useState('{\n  "example": true\n}');

  const [pushBusy, setPushBusy] = useState(false);

  useEffect(() => {
    try {
      setWorkshopIntroDismissed(localStorage.getItem('aicom_workshop_intro_dismissed_v1') === '1');
    } catch {
      setWorkshopIntroDismissed(false);
    }
  }, []);

  const dismissWorkshopIntro = () => {
    try {
      localStorage.setItem('aicom_workshop_intro_dismissed_v1', '1');
    } catch {
      /* ignore */
    }
    setWorkshopIntroDismissed(true);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setBoardFailure(null);
    try {
      const res = await fetchPipelineCatalogPageSingleMode(48, 0, 'shipped_first', true);
      setRows((res.products || []) as Row[]);
    } catch (e: unknown) {
      setBoardFailure(resolveActionableFailure(e, { operation: 'workshop_catalog' }));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const columns = useMemo(() => groupByState(rows), [rows]);

  const options = useMemo(
    () =>
      rows.map((r) => ({
        id: String(r.id || ''),
        label: `${String(r.idea || r.id || '').slice(0, 48)}${String(r.idea || '').length > 48 ? '…' : ''} · ${r.state}`,
      })),
    [rows],
  );

  const runMaterialDiff = async () => {
    if (!aId || !bId || aId === bId) {
      toast.error('Pick two different product IDs');
      return;
    }
    setDiffBusy(true);
    setLeftJson('');
    setRightJson('');
    setDiffFailure(null);
    try {
      if (materialKind === 'spec') {
        const [ra, rb] = await Promise.all([api.getProductSpec(aId), api.getProductSpec(bId)]);
        setLeftJson(JSON.stringify(ra.spec ?? {}, null, 2));
        setRightJson(JSON.stringify(rb.spec ?? {}, null, 2));
      } else {
        const [ra, rb] = await Promise.all([
          api.getProductArchitecture(aId),
          api.getProductArchitecture(bId),
        ]);
        setLeftJson(JSON.stringify(ra.architecture ?? {}, null, 2));
        setRightJson(JSON.stringify(rb.architecture ?? {}, null, 2));
      }
      setDiffFailure(null);
    } catch (e: unknown) {
      setDiffFailure(resolveActionableFailure(e, { operation: 'workshop_material_diff' }));
    } finally {
      setDiffBusy(false);
    }
  };

  const copy = (text: string) => {
    void navigator.clipboard.writeText(text).then(
      () => toast.success('Copied'),
      () => toast.error('Copy failed'),
    );
  };

  const refreshPatterns = async () => {
    setPatternsBusy(true);
    setPatternFailure(null);
    try {
      const r = await api.listIterationPatterns();
      setPatterns(r.patterns || []);
      setPatternFailure(null);
    } catch (e: unknown) {
      setPatternFailure(resolveActionableFailure(e, { operation: 'workshop_patterns_list' }));
    } finally {
      setPatternsBusy(false);
    }
  };

  useEffect(() => {
    void refreshPatterns();
  }, []);

  const savePattern = async () => {
    let doc: Record<string, unknown>;
    try {
      doc = JSON.parse(patDoc || '{}') as Record<string, unknown>;
    } catch {
      setPatternFailure({
        title: 'Invalid JSON',
        detail: 'Fix the pattern document before saving.',
        actions: [],
      });
      return;
    }
    setPatternFailure(null);
    try {
      await api.upsertIterationPattern({
        name: patName.trim() || 'Untitled pattern',
        tags: patTags
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        document: doc,
      });
      setPatName('');
      toast.success('Pattern saved');
      void refreshPatterns();
    } catch (e: unknown) {
      setPatternFailure(resolveActionableFailure(e, { operation: 'workshop_patterns_save' }));
    }
  };

  const deletePattern = async (id: string) => {
    setPatternFailure(null);
    try {
      await api.deleteIterationPattern(id);
      void refreshPatterns();
      toast.success('Deleted');
    } catch (e: unknown) {
      setPatternFailure(resolveActionableFailure(e, { operation: 'workshop_patterns_delete' }));
    }
  };

  useEffect(() => {
    if (!labSandboxId.trim() || labRefreshMs <= 0) return;
    const t = window.setInterval(() => setLabTick((x) => x + 1), labRefreshMs);
    return () => window.clearInterval(t);
  }, [labSandboxId, labRefreshMs, labTick]);

  const labPreviewSrc = useMemo(() => {
    if (typeof window === 'undefined' || !labSandboxId.trim()) return '';
    const base = `${window.location.origin}/api/sandbox/view/${encodeURIComponent(labSandboxId.trim())}`;
    return `${base}?t=${labTick}&pid=${encodeURIComponent(labPid.trim())}`;
  }, [labSandboxId, labPid, labTick]);

  const subscribePush = async () => {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      toast.error('Push not supported in this browser');
      return;
    }
    setPushBusy(true);
    setPushFailure(null);
    setPushTestFailure(null);
    try {
      const reg = await navigator.serviceWorker.ready;
      const { publicKey } = await api.getWebPushVapidPublic();
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
      const j = sub.toJSON();
      if (!j.endpoint || !j.keys?.p256dh || !j.keys?.auth) {
        throw new Error('Incomplete subscription');
      }
      await api.subscribeWebPush({
        endpoint: j.endpoint,
        keys: { p256dh: j.keys.p256dh, auth: j.keys.auth },
        userAgent: navigator.userAgent,
      });
      toast.success('Subscribed to Web Push on this browser');
    } catch (e: unknown) {
      setPushFailure(resolveActionableFailure(e, { operation: 'workshop_webpush_subscribe' }));
    } finally {
      setPushBusy(false);
    }
  };

  const sendTestPush = async () => {
    setPushBusy(true);
    setPushFailure(null);
    setPushTestFailure(null);
    try {
      const r = await api.sendWebPushTest({
        title: 'AI Factory test',
        body: 'If you see this, Web Push delivery works.',
        url: '/admin',
      });
      toast.success(`Sent: ${r.sent ?? 0}, failed: ${r.failed ?? 0}${r.error ? ` (${r.error})` : ''}`);
    } catch (e: unknown) {
      setPushTestFailure(resolveActionableFailure(e, { operation: 'workshop_webpush_test' }));
    } finally {
      setPushBusy(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="flex items-center gap-2 text-xl font-semibold text-white">
          <LayoutGrid className="h-6 w-6 text-indigo-400" aria-hidden />
          Product Workshop
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-gray-400">
          Board of recent products, specification and architecture JSON diffs, a lightweight iteration canvas (branches
          + merge edges), synchronized iframe previews for a multi-device lab, cloud pattern library, and admin Web
          Push.
        </p>
      </div>

      {!workshopIntroDismissed ? (
        <GlassCard className="border border-indigo-500/25 bg-indigo-950/25 p-4">
          <div className="flex gap-3">
            <BookOpen className="mt-0.5 h-5 w-5 shrink-0 text-indigo-300" aria-hidden />
            <div className="min-w-0 flex-1 space-y-2 text-xs leading-relaxed text-indigo-100/90">
              <p className="text-sm font-medium text-white">How to use this tab</p>
              <ol className="list-decimal space-y-1 pl-4">
                <li>Pick product IDs from the board (or paste from Pipeline), then load spec or architecture JSON.</li>
                <li>Iteration canvas persists per product — load after pressing &quot;Use ID&quot; on a card.</li>
                <li>When something fails, use the red action card: retry plus deep links (Providers, Settings, Pipeline).</li>
              </ol>
            </div>
            <button
              type="button"
              className="shrink-0 rounded-lg p-1 text-indigo-200 hover:bg-white/10"
              aria-label="Dismiss workshop tips"
              onClick={dismissWorkshopIntro}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </GlassCard>
      ) : null}

      <GlassCard>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-medium text-gray-300">Board</h3>
          <Button type="button" variant="secondary" size="sm" onClick={() => void load()} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Refresh
          </Button>
        </div>
        {loading && rows.length === 0 ? (
          <div className="flex items-center gap-2 py-8 text-gray-400">
            <Loader2 className="h-5 w-5 animate-spin text-indigo-400" />
            Loading recent products…
          </div>
        ) : (
          <div className="space-y-3">
            {boardFailure ? (
              <ActionableFailurePanel failure={boardFailure} onRetry={() => void load()} retryLabel="Reload board" />
            ) : null}
            {rows.length === 0 && !loading ? (
              <div className="rounded-lg border border-dashed border-white/15 bg-white/[0.02] px-4 py-6 text-center text-sm text-gray-500">
                <p className="text-gray-300">No products in this catalog slice yet.</p>
                <p className="mt-2 text-xs">
                  Create one under{' '}
                  <a className="text-indigo-300 hover:underline" href="/admin?tab=new-product">
                    New product
                  </a>
                  , or open{' '}
                  <a className="text-indigo-300 hover:underline" href="/admin?tab=pipeline">
                    Pipeline
                  </a>{' '}
                  if the list should already contain items (check filters / worker).
                </p>
              </div>
            ) : null}
            {rows.length > 0 ? (
          <div className="flex gap-3 overflow-x-auto pb-2">
            {[...columns.entries()].map(([state, cards]) => (
              <div
                key={state}
                className="flex w-[min(100%,280px)] shrink-0 flex-col gap-2 rounded-xl border border-white/10 bg-white/[0.02] p-2"
              >
                <div className="flex items-center justify-between gap-2 border-b border-white/10 px-1 pb-2">
                  <span className="truncate text-xs font-semibold uppercase tracking-wide text-gray-400">{state}</span>
                  <span className="shrink-0 rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-gray-300">
                    {cards.length}
                  </span>
                </div>
                <div className="flex max-h-[min(55vh,520px)] flex-col gap-2 overflow-y-auto pr-1">
                  {cards.map((p) => {
                    const id = String(p.id || '');
                    const title = String(p.idea || id).slice(0, 80);
                    const origin = typeof window !== 'undefined' ? window.location.origin : '';
                    const storefront = `${origin}/product/${encodeURIComponent(id)}`;
                    return (
                      <div key={id} className="rounded-lg border border-white/10 bg-black/30 p-2 text-xs">
                        <p className="font-medium text-gray-100">{title || id}</p>
                        <p className="mt-1 truncate font-mono text-[10px] text-gray-500">{id}</p>
                        <div className="mt-2 flex flex-wrap gap-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-[10px]"
                            onClick={() => copy(storefront)}
                          >
                            <Copy className="mr-1 h-3 w-3" />
                            Store URL
                          </Button>
                          <a
                            href={storefront}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex h-7 items-center rounded-md border border-white/15 px-2 text-[10px] text-indigo-200 hover:bg-white/5"
                          >
                            <ExternalLink className="mr-1 h-3 w-3" />
                            Open
                          </a>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-[10px]"
                            onClick={() => {
                              setCanvasPid(id);
                              setLabPid(id);
                            }}
                          >
                            Use ID
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
            ) : null}
          </div>
        )}
      </GlassCard>

      <GlassCard>
        <h3 className="mb-1 flex items-center gap-2 text-sm font-medium text-gray-300">
          <GitCompare className="h-4 w-4 text-fuchsia-400" />
          Side-by-side material diff
        </h3>
        <p className="mb-4 text-xs text-gray-500">
          Choose <span className="text-gray-300">specification.json</span> or on-disk{' '}
          <span className="text-gray-300">architecture.json</span> for both products.
        </p>
        <div className="mb-3 flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant={materialKind === 'spec' ? 'secondary' : 'ghost'}
            onClick={() => setMaterialKind('spec')}
          >
            Specification
          </Button>
          <Button
            type="button"
            size="sm"
            variant={materialKind === 'architecture' ? 'secondary' : 'ghost'}
            onClick={() => setMaterialKind('architecture')}
          >
            Architecture
          </Button>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-[11px] text-gray-500">Product A</label>
            <select
              value={aId}
              onChange={(e) => setAId(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-gray-200"
            >
              <option value="">Select…</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-gray-500">Product B</label>
            <select
              value={bId}
              onChange={(e) => setBId(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-gray-200"
            >
              <option value="">Select…</option>
              {options.map((o) => (
                <option key={`b-${o.id}`} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-3">
          <Button type="button" variant="secondary" size="sm" onClick={() => void runMaterialDiff()} disabled={diffBusy}>
            {diffBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Load JSON
          </Button>
        </div>
        {diffFailure ? (
          <div className="mt-3">
            <ActionableFailurePanel
              failure={diffFailure}
              onRetry={() => void runMaterialDiff()}
              retryLabel="Retry JSON load"
            />
          </div>
        ) : null}
        {leftJson || rightJson ? (
          <div className="mt-4 grid max-h-[480px] gap-3 overflow-hidden md:grid-cols-2">
            <div className="flex min-h-0 flex-col gap-1">
              <span className="text-[10px] uppercase text-gray-500">
                A · {aId} · {materialKind}
              </span>
              <pre className="min-h-0 flex-1 overflow-auto rounded-lg border border-white/10 bg-black/50 p-3 font-mono text-[11px] leading-relaxed text-gray-300">
                {leftJson || '—'}
              </pre>
            </div>
            <div className="flex min-h-0 flex-col gap-1">
              <span className="text-[10px] uppercase text-gray-500">
                B · {bId} · {materialKind}
              </span>
              <pre className="min-h-0 flex-1 overflow-auto rounded-lg border border-white/10 bg-black/50 p-3 font-mono text-[11px] leading-relaxed text-gray-300">
                {rightJson || '—'}
              </pre>
            </div>
          </div>
        ) : null}
      </GlassCard>

      <GlassCard>
        <h3 className="mb-1 flex items-center gap-2 text-sm font-medium text-gray-300">
          <Layers className="h-4 w-4 text-sky-400" />
          Iteration canvas (branches / merge)
        </h3>
        <p className="mb-3 text-xs text-gray-500">
          Persisted per product. Drag nodes, fork a node onto a new branch id, and record merge edges. Full Miro-style
          CRDT sync is not included — this board is for workshop notes tied to pipeline IDs.
        </p>
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <div className="min-w-[200px] flex-1">
            <label className="mb-1 block text-[11px] text-gray-500">Product ID</label>
            <Input value={canvasPid} onChange={(e) => setCanvasPid(e.target.value)} placeholder="prod-…" />
          </div>
          <Button type="button" variant="secondary" size="sm" onClick={() => void loadCanvas()} disabled={canvasLoadBusy}>
            {canvasLoadBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Load
          </Button>
          <Button type="button" size="sm" onClick={() => void saveCanvas()} disabled={canvasSaveBusy || !canvasPid.trim()}>
            {canvasSaveBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={addStageNode} icon={<Plus className="h-4 w-4" />}>
            Add stage
          </Button>
        </div>
        {canvasFailure ? (
          <div className="mb-3">
            <ActionableFailurePanel
              failure={canvasFailure}
              onRetry={() => void loadCanvas()}
              retryLabel="Retry load canvas"
            />
          </div>
        ) : null}
        {canvasSaveFailure ? (
          <div className="mb-3">
            <ActionableFailurePanel
              failure={canvasSaveFailure}
              onRetry={() => void saveCanvas()}
              retryLabel="Retry save canvas"
            />
          </div>
        ) : null}
        <div className="relative mb-4 h-[min(380px,50vh)] w-full overflow-hidden rounded-xl border border-white/10 bg-gradient-to-b from-slate-900/80 to-black/60">
          <svg
            className="h-full w-full touch-none"
            viewBox="0 0 900 420"
            onPointerMove={onNodePointerMove}
            onPointerUp={onNodePointerUp}
            onPointerLeave={onNodePointerUp}
          >
            {edges.map((e) => {
              const a = nodes.find((n) => n.id === e.source);
              const b = nodes.find((n) => n.id === e.target);
              if (!a || !b) return null;
              const stroke = e.kind === 'merge' ? '#f472b6' : '#64748b';
              return (
                <line
                  key={e.id}
                  x1={a.x + 50}
                  y1={a.y + 22}
                  x2={b.x + 50}
                  y2={b.y + 22}
                  stroke={stroke}
                  strokeWidth={2}
                  strokeDasharray={e.kind === 'merge' ? '6 4' : undefined}
                />
              );
            })}
            {nodes.map((n) => (
              <g key={n.id}>
                <rect
                  x={n.x}
                  y={n.y}
                  width={140}
                  height={44}
                  rx={8}
                  fill="rgba(15,23,42,0.92)"
                  stroke="#6366f1"
                  strokeWidth={1.5}
                  onPointerDown={(ev) => onNodePointerDown(ev, n.id)}
                  className="cursor-grab"
                />
                <rect x={n.x} y={n.y} width={5} height={44} rx={1} fill={n.branchId === 'main' ? '#22c55e' : '#a855f7'} />
                <text x={n.x + 14} y={n.y + 18} fill="#e2e8f0" fontSize="11" fontFamily="system-ui">
                  {n.label.slice(0, 18)}
                </text>
                <text x={n.x + 14} y={n.y + 34} fill="#64748b" fontSize="9" fontFamily="ui-monospace">
                  {n.branchId || 'main'}
                </text>
              </g>
            ))}
          </svg>
        </div>
        <div className="mb-2 flex flex-wrap gap-2 border-t border-white/10 pt-3 text-xs text-gray-500">
          <span className="self-center">Fork / merge helpers:</span>
          <select
            value={edgeFrom}
            onChange={(e) => setEdgeFrom(e.target.value)}
            className="rounded border border-white/10 bg-black/40 px-2 py-1 text-gray-200"
          >
            <option value="">From node…</option>
            {nodes.map((n) => (
              <option key={`ef-${n.id}`} value={n.id}>
                {n.label}
              </option>
            ))}
          </select>
          <select
            value={edgeTo}
            onChange={(e) => setEdgeTo(e.target.value)}
            className="rounded border border-white/10 bg-black/40 px-2 py-1 text-gray-200"
          >
            <option value="">To node…</option>
            {nodes.map((n) => (
              <option key={`et-${n.id}`} value={n.id}>
                {n.label}
              </option>
            ))}
          </select>
          <Button type="button" variant="secondary" size="sm" onClick={addEdge} icon={<Link2 className="h-3.5 w-3.5" />}>
            Link
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={mergeEdge}>
            Merge edge
          </Button>
          {edgeFrom ? (
            <Button type="button" variant="ghost" size="sm" onClick={() => forkSelectedBranch(edgeFrom)}>
              Fork “from”
            </Button>
          ) : null}
        </div>
      </GlassCard>

      <GlassCard>
        <h3 className="mb-1 flex items-center gap-2 text-sm font-medium text-gray-300">
          <MonitorSmartphone className="h-4 w-4 text-emerald-400" />
          Multi-device lab · live-ish preview
        </h3>
        <p className="mb-3 text-xs text-gray-500">
          Three iframes load the same sandbox viewer URL and refresh on an interval (simulates multiple clients). True
          WebRTC or screen streaming needs a dedicated signaling service — not bundled here.
        </p>
        <div className="mb-3 grid gap-2 md:grid-cols-3">
          <div>
            <label className="mb-1 block text-[11px] text-gray-500">Product ID (annotation only)</label>
            <Input value={labPid} onChange={(e) => setLabPid(e.target.value)} placeholder="prod-…" />
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-gray-500">Sandbox ID</label>
            <Input value={labSandboxId} onChange={(e) => setLabSandboxId(e.target.value)} placeholder="sandbox-…" />
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-gray-500">Refresh interval (ms)</label>
            <Input
              type="number"
              min={2000}
              step={500}
              value={labRefreshMs}
              onChange={(e) => setLabRefreshMs(Number(e.target.value) || 8000)}
            />
          </div>
        </div>
        {labPreviewSrc ? (
          <div className="grid gap-2 md:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="space-y-1">
                <p className="text-[10px] uppercase text-gray-500">Device {i + 1}</p>
                <iframe title={`lab-${i}`} src={labPreviewSrc} className="h-56 w-full rounded-lg border border-white/10 bg-black" />
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-600">Enter a sandbox id from Pipeline / sandbox start to render previews.</p>
        )}
      </GlassCard>

      <GlassCard>
        <h3 className="mb-1 flex items-center gap-2 text-sm font-medium text-gray-300">
          <Radio className="h-4 w-4 text-amber-400" />
          Cloud pattern library
        </h3>
        <p className="mb-3 text-xs text-gray-500">
          JSON documents stored on the server (same factory data directory as templates). Use for reusable workshop
          shapes, checklists, or iteration recipes beyond reference templates.
        </p>
        <div className="mb-3 grid gap-2 md:grid-cols-2">
          <Input value={patName} onChange={(e) => setPatName(e.target.value)} placeholder="Pattern name" />
          <Input value={patTags} onChange={(e) => setPatTags(e.target.value)} placeholder="tags, comma-separated" />
        </div>
        <textarea
          className="input-glass mb-3 min-h-[120px] font-mono text-xs"
          value={patDoc}
          onChange={(e) => setPatDoc(e.target.value)}
        />
        <div className="mb-4 flex flex-wrap gap-2">
          <Button type="button" size="sm" onClick={() => void savePattern()}>
            Save pattern
          </Button>
          <Button type="button" variant="secondary" size="sm" onClick={() => void refreshPatterns()} disabled={patternsBusy}>
            {patternsBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Reload list
          </Button>
        </div>
        {patternFailure ? (
          <div className="mb-3">
            <ActionableFailurePanel
              failure={patternFailure}
              onRetry={() => void refreshPatterns()}
              retryLabel="Reload patterns"
            />
          </div>
        ) : null}
        <ul className="max-h-48 space-y-1 overflow-y-auto text-sm">
          {patterns.map((p) => (
            <li
              key={String(p.id)}
              className="flex items-center justify-between gap-2 rounded border border-white/5 bg-black/25 px-2 py-1"
            >
              <span className="truncate text-gray-200">{String(p.name)}</span>
              <Button type="button" variant="ghost" size="sm" className="text-red-300" onClick={() => void deletePattern(String(p.id))}>
                Delete
              </Button>
            </li>
          ))}
        </ul>
      </GlassCard>

      <GlassCard>
        <h3 className="mb-1 flex items-center gap-2 text-sm font-medium text-gray-300">
          <Bell className="h-4 w-4 text-rose-400" />
          Web Push (this browser)
        </h3>
        <p className="mb-3 text-xs text-gray-500">
          Uses the existing <code className="text-gray-400">/sw.js</code> worker (push handler). After subscribing, use
          “Send test” — payloads also fire after successful Telegram pipeline notifications when subscriptions exist.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" size="sm" disabled={pushBusy} onClick={() => void subscribePush()}>
            Subscribe
          </Button>
          <Button type="button" size="sm" disabled={pushBusy} onClick={() => void sendTestPush()}>
            Send test push
          </Button>
        </div>
        {pushFailure ? (
          <div className="mt-3">
            <ActionableFailurePanel
              failure={pushFailure}
              onRetry={() => void subscribePush()}
              retryLabel="Retry subscribe"
            />
          </div>
        ) : null}
        {pushTestFailure ? (
          <div className="mt-3">
            <ActionableFailurePanel
              failure={pushTestFailure}
              onRetry={() => void sendTestPush()}
              retryLabel="Retry test push"
            />
          </div>
        ) : null}
      </GlassCard>
    </div>
  );
}
