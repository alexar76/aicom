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

export function NewProductTab() {
  const [idea, setIdea] = useState('');
  const [instructions, setInstructions] = useState('');
  /** Omit → infer from idea (legacy); prefer explicit full_software default for real builds */
  const [deliveryChoice, setDeliveryChoice] = useState<'full_software' | 'marketing_landing' | 'infer'>(
    'full_software'
  );
  const [mode, setMode] = useState<'prototype' | 'production'>('prototype');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get('idea');
    if (fromUrl) {
      setIdea(decodeURIComponent(fromUrl.replace(/\+/g, ' ')));
      return;
    }
    try {
      const stored = sessionStorage.getItem('aicom_prefill_idea');
      if (stored) {
        setIdea(stored);
        sessionStorage.removeItem('aicom_prefill_idea');
      }
    } catch {
      /* ignore */
    }
  }, []);

  const handleSubmit = async () => {
    if (!idea.trim()) return;

    setSubmitting(true);
    setResult(null);
    setError(null);

    try {
      // Call the API to create a new product with admin instructions
      const payload: Record<string, unknown> = {
        idea: idea.trim(),
        admin_instructions: instructions.trim() || undefined,
        production_mode: mode === 'production',
      };
      if (deliveryChoice !== 'infer') {
        payload.delivery_profile = deliveryChoice;
      }

      const response = await fetch('/api/admin/products/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to create product');
      }

      const data = await response.json();
      setResult(`Product created successfully! ID: ${data.product_id}`);
      setIdea('');
      setInstructions('');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <GlassCard>
          <div className="flex items-center gap-3 mb-6">
            <Sparkles className="w-6 h-6 text-indigo-400" />
            <div>
              <h2 className="text-xl font-semibold text-white">Create New Product</h2>
              <p className="text-sm text-gray-400">
                Same full pipeline as autonomous builds — your idea text becomes the stakeholder brief for every downstream agent.
              </p>
            </div>
          </div>

          <div className="space-y-6">
            {/* Product Idea */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Product Idea <span className="text-red-400">*</span>
              </label>
              <textarea
                className="input-glass min-h-[120px] resize-y"
                placeholder="Describe the product you want to build..."
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
              />
            </div>

            {/* Admin Instructions */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Admin Instructions (Optional)
              </label>
              <textarea
                className="input-glass min-h-[160px] resize-y"
                placeholder={`Provide specific instructions for the AI agents:

Example:
- Use Python/FastAPI for the backend
- Include JWT authentication
- Add PostgreSQL as the database
- Focus on performance optimization
- Include comprehensive API documentation
- Add rate limiting middleware`}
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
              />
              <p className="text-xs text-gray-500 mt-1">
                These instructions will be passed to all agents in the pipeline.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">What to ship</label>
              <select
                value={deliveryChoice}
                onChange={(e) =>
                  setDeliveryChoice(e.target.value as 'full_software' | 'marketing_landing' | 'infer')
                }
                className="input-glass"
              >
                <option value="full_software">Full product (app/service, backend + UI scope)</option>
                <option value="marketing_landing">Marketing landing page only (single-page brochure)</option>
                <option value="infer">Auto-detect from idea text (legacy)</option>
              </select>
              <p className="text-xs text-gray-500 mt-1">
                Default is full product. Pick landing only for explicit brochure SKUs; auto-detect uses heuristics on
                your wording.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Delivery mode</label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as 'prototype' | 'production')}
                className="input-glass"
              >
                <option value="prototype">prototype (faster, lighter checks)</option>
                <option value="production">production (deeper checks, extra critic pass)</option>
              </select>
              <p className="text-xs text-gray-500 mt-1">
                Production mode enforces stricter PM/architecture quality gates and a release critic loop before completion.
              </p>
            </div>

            {/* Submit */}
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
              <Button
                onClick={handleSubmit}
                loading={submitting}
                disabled={!idea.trim()}
                icon={<Send className="w-4 h-4" />}
                className="w-full sm:w-auto"
              >
                Start Building
              </Button>
              {!idea.trim() && (
                <span className="text-xs text-gray-500">Enter a product idea to continue</span>
              )}
            </div>

            {/* Result */}
            {result && (
              <div className="glass p-4 rounded-xl border border-emerald-500/30">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 mt-0.5" />
                  <div>
                    <p className="text-sm text-emerald-300">{result}</p>
                    <p className="text-xs text-gray-500 mt-1">
                      The pipeline has started. Monitor progress in the Pipeline tab.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="glass p-4 rounded-xl border border-red-500/30">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5" />
                  <div>
                    <p className="text-sm text-red-300">Failed to create product</p>
                    <p className="text-xs text-gray-500 mt-1">{error}</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </GlassCard>
      </motion.div>
    </div>
  );
}
