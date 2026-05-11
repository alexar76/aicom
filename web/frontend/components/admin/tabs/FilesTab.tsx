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

export function FilesTab() {
  const [products, setProducts] = useState<any[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<string | null>(null);
  const [files, setFiles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [expandedFile, setExpandedFile] = useState<string | null>(null);
  const [sandboxOpening, setSandboxOpening] = useState(false);
  const [productSearch, setProductSearch] = useState('');
  const [productStateFilter, setProductStateFilter] = useState('all');
  const [fileSearch, setFileSearch] = useState('');
  const [fileCategoryFilter, setFileCategoryFilter] = useState('all');

  useEffect(() => {
    api.getPipelineProducts(1000, 0).then((data) => {
      setProducts(data.products || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const loadFiles = async (productId: string) => {
    setSelectedProduct(productId);
    setFileLoading(true);
    setExpandedFile(null);
    try {
      const token = localStorage.getItem('admin_token');
      const res = await fetch(`/api/admin/products/${productId}/files`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setFiles(data.files || []);
    } catch (e) {
      setFiles([]);
    }
    setFileLoading(false);
  };

  const openSandboxPreview = async () => {
    if (!selectedProduct) return;
    setSandboxOpening(true);
    try {
      const result = await api.startSandbox(selectedProduct);
      const raw = result.url || `/api/sandbox/view/${result.sandbox_id}`;
      const abs = raw.startsWith('http') ? raw : new URL(raw, window.location.origin).href;
      const win = window.open(abs, '_blank', 'noopener,noreferrer');
      if (!win) {
        toast.error('Popup blocked — allow popups for this site or open the URL manually.');
      }
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Failed to start sandbox');
    } finally {
      setSandboxOpening(false);
    }
  };

  const categoryColors: Record<string, string> = {
    specs: 'from-blue-500 to-blue-600',
    architecture: 'from-purple-500 to-purple-600',
    code: 'from-green-500 to-green-600',
    bugs: 'from-red-500 to-red-600',
    security: 'from-cyan-500 to-cyan-600',
    marketing: 'from-amber-500 to-amber-600',
    telemetry: 'from-pink-500 to-pink-600',
  };

  const filteredProducts = useMemo(() => {
    const q = productSearch.trim().toLowerCase();
    return products.filter((p: any) => {
      const st = String(p?.state || '').toUpperCase();
      if (productStateFilter !== 'all' && st !== productStateFilter) return false;
      if (!q) return true;
      const idea = String(p?.idea || '').toLowerCase();
      const id = String(p?.id || '').toLowerCase();
      return idea.includes(q) || id.includes(q);
    });
  }, [products, productSearch, productStateFilter]);

  const availableProductStates = useMemo(() => {
    const s = new Set<string>();
    for (const p of products) {
      const st = String(p?.state || '').toUpperCase();
      if (st) s.add(st);
    }
    return Array.from(s).sort();
  }, [products]);

  const availableFileCategories = useMemo(() => {
    const s = new Set<string>();
    for (const f of files) {
      const c = String(f?.category || '');
      if (c) s.add(c);
    }
    return Array.from(s).sort();
  }, [files]);

  const filteredFiles = useMemo(() => {
    const q = fileSearch.trim().toLowerCase();
    return files.filter((file: any) => {
      if (fileCategoryFilter !== 'all' && String(file?.category || '') !== fileCategoryFilter) return false;
      if (!q) return true;
      const filename = String(file?.filename || '').toLowerCase();
      const path = String(file?.path || '').toLowerCase();
      const preview = String(file?.preview || '').toLowerCase();
      return filename.includes(q) || path.includes(q) || preview.includes(q);
    });
  }, [files, fileSearch, fileCategoryFilter]);

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white">Generated Files Browser</h2>
      <p className="text-sm text-gray-400">Browse all artifacts generated by the AI pipeline for each product.</p>

      {loading ? (
        <div className="text-gray-400">Loading products...</div>
      ) : products.length === 0 ? (
        <div className="text-gray-500">No products found. Create a product first.</div>
      ) : (
        <div className="grid md:grid-cols-3 gap-6">
          {/* Product list */}
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-gray-400 mb-2">Products</h3>
            <div className="space-y-2 mb-2">
              <Input
                value={productSearch}
                onChange={(e) => setProductSearch(e.target.value)}
                placeholder="Search products..."
              />
              <select
                value={productStateFilter}
                onChange={(e) => setProductStateFilter(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-2 text-sm text-gray-300 focus:outline-none focus:border-indigo-500/50"
              >
                <option value="all">All states</option>
                {availableProductStates.map((st) => (
                  <option key={st} value={st}>{st}</option>
                ))}
              </select>
              <p className="text-[11px] text-gray-500">
                Showing {filteredProducts.length} of {products.length}
              </p>
              <button
                type="button"
                onClick={() => {
                  setProductSearch('');
                  setProductStateFilter('all');
                }}
                className="text-[11px] text-indigo-300 hover:text-indigo-200 underline underline-offset-2"
              >
                Reset product filters
              </button>
            </div>
            {filteredProducts.map((p: any) => (
              <button
                key={p.id}
                onClick={() => loadFiles(p.id)}
                className={`w-full text-left p-3 rounded-xl text-sm transition-all ${
                  selectedProduct === p.id
                    ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                    : 'text-gray-400 hover:text-white hover:bg-white/5 border border-transparent'
                }`}
              >
                <div className="font-medium">{p.idea || p.id}</div>
                <div className="text-xs mt-1 opacity-60">{p.state} · {p.id?.slice(0, 12)}</div>
              </button>
            ))}
          </div>

          {/* File list */}
          <div className="md:col-span-2 space-y-2">
            {!selectedProduct ? (
              <div className="text-gray-500 text-center py-12">Select a product to browse its files</div>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-3 mb-3 p-3 rounded-xl bg-white/[0.03] border border-white/10">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={sandboxOpening}
                    onClick={() => void openSandboxPreview()}
                    className="flex items-center gap-2"
                  >
                    {sandboxOpening ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <ExternalLink className="w-4 h-4" />
                    )}
                    {sandboxOpening ? 'Starting…' : 'Open sandbox preview'}
                  </Button>
                  <p className="text-xs text-gray-500 max-w-xl">
                    Starts a sandbox for this product and opens the HTML demo (iframe) in a new tab — same viewer as the product page.
                  </p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-3">
                  <Input
                    value={fileSearch}
                    onChange={(e) => setFileSearch(e.target.value)}
                    placeholder="Search filename/path/content preview..."
                  />
                  <FilterSelect
                    value={fileCategoryFilter}
                    onChange={(e) => setFileCategoryFilter(e.target.value)}
                  >
                    <option value="all">All categories</option>
                    {availableFileCategories.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </FilterSelect>
                  <FilterResetSummary
                    onReset={() => {
                      setFileSearch('');
                      setFileCategoryFilter('all');
                    }}
                    resetLabel="Reset file filters"
                    summary={`Showing ${filteredFiles.length} of ${files.length}`}
                  />
                </div>
                {fileLoading ? (
                  <div className="text-gray-400">Loading files...</div>
                ) : files.length === 0 ? (
                  <div className="text-gray-500 text-center py-12">No files found for this product</div>
                ) : filteredFiles.length === 0 ? (
                  <div className="text-gray-500 text-center py-12">No files match current filters</div>
                ) : (
                  <>
                <h3 className="text-sm font-medium text-gray-400 mb-2">
                  {filteredFiles.length} file{filteredFiles.length !== 1 ? 's' : ''} for {selectedProduct?.slice(0, 12)}
                </h3>
                {filteredFiles.map((file: any) => (
                  <GlassCard key={file.path} className="overflow-hidden">
                    <button
                      onClick={() => setExpandedFile(expandedFile === file.path ? null : file.path)}
                      className="w-full text-left p-3 flex items-center justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <div className={`w-2 h-2 rounded-full bg-gradient-to-br ${categoryColors[file.category] || 'from-gray-500 to-gray-600'}`} />
                        <div>
                          <span className="text-white text-sm font-medium">{file.filename}</span>
                          <span className="text-gray-500 text-xs ml-2">({(file.size_bytes / 1024).toFixed(1)} KB)</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-500 bg-white/5 px-2 py-0.5 rounded">{file.category}</span>
                        <span className="text-gray-500 text-xs">{expandedFile === file.path ? '▲' : '▼'}</span>
                      </div>
                    </button>
                    {expandedFile === file.path && (
                      <div className="border-t border-white/5">
                        <pre className="p-4 text-xs text-gray-300 overflow-auto max-h-96 whitespace-pre-wrap font-mono">
                          {file.error ? (
                            <span className="text-red-400">Error: {file.error}</span>
                          ) : (
                            file.preview
                          )}
                        </pre>
                      </div>
                    )}
                  </GlassCard>
                ))}
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
