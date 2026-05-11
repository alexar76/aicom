'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  Plus,
  Send,
  Play,
  Pause,
  RotateCcw,
  CheckCircle2,
  Sparkles,
  Lightbulb,
  Target,
  MessageCircle,
  BrainCircuit,
  ChevronRight,
  ChevronLeft,
  Trash2,
  Loader2,
  AlertCircle,
  Zap,
  Star,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import toast from 'react-hot-toast';
import api from '@/lib/api';

// ── Types ──────────────────────────────────────────────────────────────────

interface AvailableAgent {
  agent_type: string;
  display_name: string;
  description: string;
  icon: string;
  color: string;
  is_available: boolean;
}

interface DiscussionSession {
  session_id: string;
  topic: string;
  session_type: string;
  status: string;
  created_by: string;
  created_at: number;
  updated_at: number;
  completed_at: number | null;
  participants: string[];
  context: Record<string, any>;
  config: Record<string, any>;
  rounds: any[];
  results: Record<string, any> | null;
  message_count: number;
  round_count: number;
}

interface SessionSummary {
  session_id: string;
  topic: string;
  session_type: string;
  status: string;
  participants: string[];
  message_count: number;
  idea_count: number;
  created_at: number;
  completed_at: number | null;
  summary_preview: string | null;
}

interface DiscussionMessage {
  message_id: string;
  session_id: string;
  round_number: number;
  agent_type: string;
  sender_name: string;
  content: string;
  timestamp: number;
  metadata: Record<string, any>;
  attachments: any[];
}

interface Idea {
  idea_id: string;
  session_id: string;
  title: string;
  description: string;
  author_agent: string;
  supporters: string[];
  opposers: string[];
  score: {
    overall: number;
    feasibility: number;
    innovation: number;
    market_potential: number;
    effort_estimate: string | null;
  } | null;
  tags: string[];
  created_at: number;
  converted_to_product: boolean;
  product_id: string | null;
}

interface DiscussionStats {
  total_sessions: number;
  active_sessions: number;
  completed_sessions: number;
  total_messages: number;
  total_ideas: number;
  sessions_by_type: Record<string, number>;
}

// ── Agent Config ───────────────────────────────────────────────────────────

const AGENT_COLORS: Record<string, string> = {
  pm: '#6366f1',
  analyst: '#f59e0b',
  architect: '#8b5cf6',
  dev: '#06b6d4',
  qa: '#10b981',
  devops: '#3b82f6',
  security: '#ef4444',
  marketing: '#ec4899',
  sales: '#14b8a6',
  evolution_analyst: '#a855f7',
  methodologist: '#0ea5e9',
  human: '#94a3b8',
  system: '#64748b',
};

const AGENT_ICONS: Record<string, string> = {
  pm: '🎯',
  analyst: '📊',
  architect: '🏗️',
  dev: '💻',
  qa: '🔍',
  devops: '⚙️',
  security: '🛡️',
  marketing: '📣',
  sales: '🤝',
  evolution_analyst: '📈',
  methodologist: '🧭',
  human: '👤',
  system: '⚙️',
};

const SESSION_TYPE_CONFIG = [
  { value: 'brainstorming', label: 'Brainstorming', icon: '💡', color: '#8b5cf6' },
  { value: 'feature_discussion', label: 'Feature Discussion', icon: '🔧', color: '#06b6d4' },
  { value: 'strategy_session', label: 'Strategy Session', icon: '🎯', color: '#f59e0b' },
  { value: 'product_idea', label: 'Product Idea', icon: '🚀', color: '#10b981' },
];

const STATUS_COLORS: Record<string, string> = {
  pending: '#64748b',
  active: '#06b6d4',
  paused: '#f59e0b',
  completed: '#10b981',
  cancelled: '#ef4444',
};

// ── BrainstormingTab ───────────────────────────────────────────────────────

export default function BrainstormingTab() {
  const [view, setView] = useState<'list' | 'detail'>('list');
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedSession, setSelectedSession] = useState<DiscussionSession | null>(null);
  const [messages, setMessages] = useState<DiscussionMessage[]>([]);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [stats, setStats] = useState<DiscussionStats | null>(null);
  const [availableAgents, setAvailableAgents] = useState<AvailableAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');

  // Create session modal
  const [showCreate, setShowCreate] = useState(false);
  const [newTopic, setNewTopic] = useState('');
  const [newType, setNewType] = useState('brainstorming');
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);

  // Human message input
  const [humanInput, setHumanInput] = useState('');

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load data
  const loadSessions = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set('status', statusFilter);
      if (typeFilter) params.set('session_type', typeFilter);
      params.set('limit', '50');

      const res = await api.getDiscussionSessions(params.toString());
      setSessions(res.sessions || []);
    } catch (err: any) {
      console.error('Failed to load sessions:', err);
    }
  }, [statusFilter, typeFilter]);

  const loadStats = useCallback(async () => {
    try {
      const res = await api.getDiscussionStats();
      setStats(res);
    } catch (err: any) {
      console.error('Failed to load stats:', err);
    }
  }, []);

  const loadAgents = useCallback(async () => {
    try {
      const res = await api.getAvailableAgents();
      setAvailableAgents(res || []);
    } catch (err: any) {
      console.error('Failed to load agents:', err);
    }
  }, []);

  const loadSessionDetail = useCallback(async (sessionId: string) => {
    const [sessionRes, msgRes, ideasRes] = await Promise.all([
      api.getDiscussionSession(sessionId),
      api.getDiscussionMessages(sessionId, 200),
      api.getDiscussionIdeas(sessionId),
    ]);
    if (!sessionRes?.session) {
      toast.error('Invalid session response from server');
      throw new Error('Missing session in response');
    }
    setSelectedSession(sessionRes.session);
    setMessages((msgRes.messages || []).reverse());
    setIdeas(ideasRes.map((i: any) => i.idea) || []);
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([loadSessions(), loadStats(), loadAgents()]).finally(() => setLoading(false));
  }, [loadSessions, loadStats, loadAgents]);

  // ── Auto-refresh active sessions ────────────────────────────────────────

  useEffect(() => {
    if (view !== 'detail' || !selectedSession) return;
    if (selectedSession.status !== 'active') return;

    const interval = setInterval(() => {
      loadSessionDetail(selectedSession.session_id).catch(() => {
        /* Polling must not surface unhandled rejections (e.g. transient network / 503). */
      });
    }, 5000);

    return () => clearInterval(interval);
  }, [view, selectedSession?.session_id, selectedSession?.status, loadSessionDetail]);

  // ── Actions ─────────────────────────────────────────────────────────────

  const handleCreateSession = async () => {
    if (!newTopic.trim() || selectedAgents.length === 0) {
      toast.error('Topic and at least one agent are required');
      return;
    }

    setActionLoading('create');
    try {
      const res = await api.createDiscussionSession({
        topic: newTopic.trim(),
        session_type: newType,
        participants: selectedAgents,
      });

      toast.success('Session created');
      setShowCreate(false);
      setNewTopic('');
      setNewType('brainstorming');
      setSelectedAgents([]);
      await loadSessions();
      await loadStats();
    } catch (err: any) {
      toast.error(err.message || 'Failed to create session');
    } finally {
      setActionLoading(null);
    }
  };

  const handleStartSession = async (sessionId: string) => {
    setActionLoading(`start-${sessionId}`);
    try {
      const res = await api.startDiscussionSession(sessionId);
      setSelectedSession(res.session);
      await loadSessionDetail(sessionId);
      await loadSessions();
      toast.success('Session started');
    } catch (err: any) {
      toast.error(err.message || 'Failed to start session');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRunRound = async (sessionId: string) => {
    setActionLoading(`round-${sessionId}`);
    try {
      const res = await api.runDiscussionRound(sessionId);
      setSelectedSession(res.session);
      await loadSessionDetail(sessionId);
      await loadSessions();
      toast.success('Round completed');
    } catch (err: any) {
      toast.error(err.message || 'Failed to run round');
    } finally {
      setActionLoading(null);
    }
  };

  const handlePauseSession = async (sessionId: string) => {
    setActionLoading(`pause-${sessionId}`);
    try {
      const res = await api.pauseDiscussionSession(sessionId);
      setSelectedSession(res.session);
      await loadSessions();
      toast.success('Session paused');
    } catch (err: any) {
      toast.error(err.message || 'Failed to pause session');
    } finally {
      setActionLoading(null);
    }
  };

  const handleResumeSession = async (sessionId: string) => {
    setActionLoading(`resume-${sessionId}`);
    try {
      const res = await api.resumeDiscussionSession(sessionId);
      setSelectedSession(res.session);
      await loadSessionDetail(sessionId);
      await loadSessions();
      toast.success('Session resumed');
    } catch (err: any) {
      toast.error(err.message || 'Failed to resume session');
    } finally {
      setActionLoading(null);
    }
  };

  const handleConcludeSession = async (sessionId: string) => {
    setActionLoading(`conclude-${sessionId}`);
    try {
      const res = await api.concludeDiscussionSession(sessionId);
      setSelectedSession(res.session);
      await loadSessionDetail(sessionId);
      await loadSessions();
      await loadStats();
      toast.success('Session concluded');
    } catch (err: any) {
      toast.error(err.message || 'Failed to conclude session');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (!confirm('Delete this session and all its data? This is irreversible.')) return;

    setActionLoading(`delete-${sessionId}`);
    try {
      await api.deleteDiscussionSession(sessionId);
      if (selectedSession?.session_id === sessionId) {
        setView('list');
        setSelectedSession(null);
      }
      await loadSessions();
      await loadStats();
      toast.success('Session deleted');
    } catch (err: any) {
      toast.error(err.message || 'Failed to delete session');
    } finally {
      setActionLoading(null);
    }
  };

  const handleSendMessage = async () => {
    if (!humanInput.trim() || !selectedSession) return;

    setActionLoading('send');
    try {
      await api.sendDiscussionMessage(selectedSession.session_id, humanInput.trim());
      setHumanInput('');
      await loadSessionDetail(selectedSession.session_id);
    } catch (err: any) {
      toast.error(err.message || 'Failed to send message');
    } finally {
      setActionLoading(null);
    }
  };

  const handleExtractIdeas = async (sessionId: string) => {
    setActionLoading(`extract-${sessionId}`);
    try {
      const res = await api.extractDiscussionIdeas(sessionId);
      setIdeas(res.map((i: any) => i.idea) || []);
      toast.success('Ideas extracted');
    } catch (err: any) {
      toast.error(err.message || 'Failed to extract ideas');
    } finally {
      setActionLoading(null);
    }
  };

  const handlePromoteIdea = async (sessionId: string, ideaId: string) => {
    setActionLoading(`promote-${ideaId}`);
    try {
      await api.promoteIdeaToProduct(sessionId, ideaId);
      toast.success('Idea promoted to product!');
      await loadSessionDetail(sessionId);
    } catch (err: any) {
      toast.error(err.message || 'Failed to promote idea');
    } finally {
      setActionLoading(null);
    }
  };

  // ── Formatting helpers ──────────────────────────────────────────────────

  const formatTime = (ts: number) => {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  };

  const formatDate = (ts: number) => {
    const d = new Date(ts * 1000);
    return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  };

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      pending: 'bg-gray-500/20 text-gray-300',
      active: 'bg-cyan-500/20 text-cyan-300',
      paused: 'bg-yellow-500/20 text-yellow-300',
      completed: 'bg-green-500/20 text-green-300',
      cancelled: 'bg-red-500/20 text-red-300',
    };
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || 'bg-gray-500/20 text-gray-300'}`}>
        {status}
      </span>
    );
  };

  // ── Render: List View ───────────────────────────────────────────────────

  if (view === 'list') {
    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-white flex items-center gap-2">
              <BrainCircuit className="w-6 h-6 text-purple-400" />
              Brainstorming & Discussions
            </h2>
            <p className="text-sm text-gray-400 mt-1">
              Multi-agent discussion sessions for ideas, features, and strategy
            </p>
          </div>
          <Button onClick={() => setShowCreate(true)} variant="primary">
            <Plus className="w-4 h-4 mr-1.5" />
            New Session
          </Button>
        </div>

        <div className="rounded-xl border border-purple-500/25 bg-purple-500/5 px-4 py-3 text-sm text-gray-300">
          <span className="font-semibold text-purple-300">Brainstorming &amp; Discussions</span> — themed sessions with rounds,
          agent selection, and outputs (ideas, decisions). This is{' '}
          <span className="text-amber-200/90">not</span> the corporate chat: daily standup, Owner, and Director live under{' '}
          <span className="text-cyan-300">Admin → Corporate Chat</span>. Details:{' '}
          <code className="text-xs bg-black/30 px-1 rounded">docs/corporate-chat-vs-discussions.md</code>.
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { label: 'Total', value: stats.total_sessions, color: 'text-purple-400', icon: BrainCircuit },
              { label: 'Active', value: stats.active_sessions, color: 'text-cyan-400', icon: Play },
              { label: 'Completed', value: stats.completed_sessions, color: 'text-green-400', icon: CheckCircle2 },
              { label: 'Messages', value: stats.total_messages, color: 'text-blue-400', icon: MessageCircle },
              { label: 'Ideas', value: stats.total_ideas, color: 'text-yellow-400', icon: Lightbulb },
            ].map((stat) => (
              <GlassCard key={stat.label} className="p-3 flex items-center gap-3">
                <stat.icon className={`w-5 h-5 ${stat.color}`} />
                <div>
                  <div className="text-lg font-semibold text-white">{stat.value}</div>
                  <div className="text-xs text-gray-500">{stat.label}</div>
                </div>
              </GlassCard>
            ))}
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-cyan-500/50"
          >
            <option value="">All Status</option>
            <option value="pending">Pending</option>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-cyan-500/50"
          >
            <option value="">All Types</option>
            {SESSION_TYPE_CONFIG.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>

        {/* Session List */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
          </div>
        ) : sessions.length === 0 ? (
          <GlassCard className="p-12 text-center">
            <BrainCircuit className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400 mb-4">No discussion sessions yet</p>
            <Button onClick={() => setShowCreate(true)} variant="primary">
              <Plus className="w-4 h-4 mr-1.5" />
              Create First Session
            </Button>
          </GlassCard>
        ) : (
          <div className="space-y-3">
            {sessions.map((s) => (
              <motion.div
                key={s.session_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <GlassCard
                  className="p-4 cursor-pointer hover:bg-white/5 transition-colors"
                  onClick={async () => {
                    try {
                      await loadSessionDetail(s.session_id);
                      setView('detail');
                    } catch {
                      toast.error('Failed to load session details');
                    }
                  }}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-lg">
                          {SESSION_TYPE_CONFIG.find((t) => t.value === s.session_type)?.icon || '💬'}
                        </span>
                        <h3 className="font-medium text-white truncate">{s.topic}</h3>
                        {getStatusBadge(s.status)}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-gray-500 mt-2">
                        <span>{formatDate(s.created_at)}</span>
                        <span>•</span>
                        <span>{s.message_count} messages</span>
                        {s.idea_count > 0 && (
                          <>
                            <span>•</span>
                            <span>{s.idea_count} ideas</span>
                          </>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {s.participants.map((p) => (
                          <span
                            key={p}
                            className="text-xs px-1.5 py-0.5 rounded"
                            style={{ backgroundColor: `${AGENT_COLORS[p] || '#64748b'}20`, color: AGENT_COLORS[p] || '#64748b' }}
                          >
                            {AGENT_ICONS[p] || '🤖'} {p}
                          </span>
                        ))}
                      </div>
                    </div>
                    <ChevronRight className="w-5 h-5 text-gray-600 shrink-0 mt-1" />
                  </div>
                </GlassCard>
              </motion.div>
            ))}
          </div>
        )}

        {/* Create Session Modal */}
        <Modal isOpen={showCreate} onClose={() => setShowCreate(false)} title="New Discussion Session" size="lg">
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Topic</label>
              <Input
                value={newTopic}
                onChange={(e) => setNewTopic(e.target.value)}
                placeholder="What do you want to discuss?"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Session Type</label>
              <div className="grid grid-cols-2 gap-2">
                {SESSION_TYPE_CONFIG.map((t) => (
                  <button
                    key={t.value}
                    onClick={() => setNewType(t.value)}
                    className={`p-3 rounded-xl text-left transition-all ${
                      newType === t.value
                        ? 'bg-white/10 border border-cyan-500/50'
                        : 'bg-white/5 border border-white/10 hover:bg-white/10'
                    }`}
                  >
                    <span className="text-lg">{t.icon}</span>
                    <div className="text-sm text-white mt-1">{t.label}</div>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-2">
                Participants ({selectedAgents.length} selected)
              </label>
              <div className="grid grid-cols-2 gap-2 max-h-60 overflow-y-auto">
                {availableAgents.map((agent) => (
                  <button
                    key={agent.agent_type}
                    onClick={() => {
                      setSelectedAgents((prev) =>
                        prev.includes(agent.agent_type)
                          ? prev.filter((a) => a !== agent.agent_type)
                          : [...prev, agent.agent_type]
                      );
                    }}
                    className={`p-2 rounded-xl text-left transition-all ${
                      selectedAgents.includes(agent.agent_type)
                        ? 'bg-white/10 border border-cyan-500/50'
                        : 'bg-white/5 border border-white/10 hover:bg-white/10'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span>{AGENT_ICONS[agent.agent_type] || '🤖'}</span>
                      <div>
                        <div className="text-sm text-white">{agent.display_name}</div>
                        <div className="text-xs text-gray-500 truncate">{agent.description}</div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <Button variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button
                variant="primary"
                onClick={handleCreateSession}
                loading={actionLoading === 'create'}
                disabled={!newTopic.trim() || selectedAgents.length === 0}
              >
                Create Session
              </Button>
            </div>
          </div>
        </Modal>
      </div>
    );
  }

  // ── Render: Detail View ─────────────────────────────────────────────────

  if (!selectedSession) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
      </div>
    );
  }

  const canStart = selectedSession.status === 'pending';
  const canRunRound = selectedSession.status === 'active';
  const canPause = selectedSession.status === 'active';
  const canResume = selectedSession.status === 'paused';
  const canConclude = selectedSession.status === 'active';
  const isOver = ['completed', 'cancelled'].includes(selectedSession.status);

  return (
    <div className="space-y-4">
      {/* Back button & header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => { setView('list'); setSelectedSession(null); }}
            className="p-1.5 rounded-lg hover:bg-white/10 transition-colors"
          >
            <ChevronLeft className="w-5 h-5 text-gray-400" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-white">{selectedSession.topic}</h2>
              {getStatusBadge(selectedSession.status)}
            </div>
            <p className="text-xs text-gray-500">
              {selectedSession.session_type} • Round {selectedSession.round_count}/{selectedSession.config.max_rounds}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {canStart && (
            <Button
              size="sm"
              variant="primary"
              onClick={() => handleStartSession(selectedSession.session_id)}
              loading={actionLoading === `start-${selectedSession.session_id}`}
            >
              <Play className="w-4 h-4 mr-1" />
              Start
            </Button>
          )}
          {canRunRound && (
            <Button
              size="sm"
              variant="primary"
              onClick={() => handleRunRound(selectedSession.session_id)}
              loading={actionLoading === `round-${selectedSession.session_id}`}
            >
              <RotateCcw className="w-4 h-4 mr-1" />
              Run Round
            </Button>
          )}
          {canPause && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => handlePauseSession(selectedSession.session_id)}
              loading={actionLoading === `pause-${selectedSession.session_id}`}
            >
              <Pause className="w-4 h-4 mr-1" />
              Pause
            </Button>
          )}
          {canResume && (
            <Button
              size="sm"
              variant="primary"
              onClick={() => handleResumeSession(selectedSession.session_id)}
              loading={actionLoading === `resume-${selectedSession.session_id}`}
            >
              <Play className="w-4 h-4 mr-1" />
              Resume
            </Button>
          )}
          {canConclude && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => handleConcludeSession(selectedSession.session_id)}
              loading={actionLoading === `conclude-${selectedSession.session_id}`}
            >
              <CheckCircle2 className="w-4 h-4 mr-1" />
              Conclude
            </Button>
          )}
          <button
            onClick={() => handleDeleteSession(selectedSession.session_id)}
            disabled={actionLoading === `delete-${selectedSession.session_id}`}
            className="p-2 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-colors disabled:opacity-50"
            title="Delete session"
          >
            {actionLoading === `delete-${selectedSession.session_id}` ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Main chat area */}
        <div className="lg:col-span-2">
          <GlassCard className="p-4 flex flex-col h-[calc(100vh-16rem)]">
            {/* Participants bar */}
            <div className="flex flex-wrap gap-1.5 mb-3 pb-3 border-b border-white/10">
              {selectedSession.participants.map((p) => (
                <span
                  key={p}
                  className="text-xs px-2 py-0.5 rounded-full"
                  style={{ backgroundColor: `${AGENT_COLORS[p] || '#64748b'}20`, color: AGENT_COLORS[p] || '#64748b' }}
                >
                  {AGENT_ICONS[p] || '🤖'} {p}
                </span>
              ))}
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto space-y-3 mb-3">
              {messages.length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-gray-500 text-sm">
                    {canStart ? 'Start the session to begin discussion' : 'No messages yet'}
                  </p>
                </div>
              ) : (
                messages.map((msg) => (
                  <div
                    key={msg.message_id}
                    className={`flex gap-2 ${msg.agent_type === 'human' ? 'justify-end' : ''}`}
                  >
                    {msg.agent_type !== 'human' && (
                      <div
                        className="w-8 h-8 rounded-full flex items-center justify-center text-sm shrink-0"
                        style={{ backgroundColor: `${AGENT_COLORS[msg.agent_type] || '#64748b'}20` }}
                      >
                        <span>{AGENT_ICONS[msg.agent_type] || '🤖'}</span>
                      </div>
                    )}
                    <div
                      className={`max-w-[80%] ${
                        msg.agent_type === 'human'
                          ? 'bg-cyan-500/20 border border-cyan-500/30'
                          : 'bg-white/5 border border-white/10'
                      } rounded-xl px-3 py-2`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className="text-xs font-medium"
                          style={{ color: AGENT_COLORS[msg.agent_type] || '#94a3b8' }}
                        >
                          {msg.sender_name}
                        </span>
                        <span className="text-xs text-gray-600">{formatTime(msg.timestamp)}</span>
                      </div>
                      <p className="text-sm text-gray-300 whitespace-pre-wrap">{msg.content}</p>
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Human input */}
            {!isOver && (
              <div className="flex gap-2 pt-3 border-t border-white/10">
                <Input
                  value={humanInput}
                  onChange={(e) => setHumanInput(e.target.value)}
                  placeholder="Type your message..."
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendMessage(); } }}
                />
                <Button
                  variant="primary"
                  onClick={handleSendMessage}
                  loading={actionLoading === 'send'}
                  disabled={!humanInput.trim()}
                >
                  <Send className="w-4 h-4" />
                </Button>
              </div>
            )}
          </GlassCard>
        </div>

        {/* Side panel: Ideas & Info */}
        <div className="space-y-4">
          {/* Session Info */}
          <GlassCard className="p-3">
            <h3 className="text-sm font-medium text-white mb-2 flex items-center gap-1.5">
              <Target className="w-4 h-4 text-cyan-400" />
              Session Info
            </h3>
            <div className="space-y-1.5 text-xs text-gray-400">
              <div className="flex justify-between">
                <span>Type</span>
                <span className="text-white">{selectedSession.session_type}</span>
              </div>
              <div className="flex justify-between">
                <span>Round</span>
                <span className="text-white">{selectedSession.round_count}/{selectedSession.config.max_rounds}</span>
              </div>
              <div className="flex justify-between">
                <span>Messages</span>
                <span className="text-white">{messages.length}</span>
              </div>
              <div className="flex justify-between">
                <span>Created</span>
                <span className="text-white">{formatDate(selectedSession.created_at)}</span>
              </div>
              {selectedSession.results?.aggregated_rating && (
                <div className="flex justify-between">
                  <span>Rating</span>
                  <span className="text-yellow-400">
                    {(selectedSession.results.aggregated_rating * 100).toFixed(0)}%
                  </span>
                </div>
              )}
            </div>
          </GlassCard>

          {/* Ideas */}
          <GlassCard className="p-3">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-white flex items-center gap-1.5">
                <Lightbulb className="w-4 h-4 text-yellow-400" />
                Ideas ({ideas.length})
              </h3>
              {isOver && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => handleExtractIdeas(selectedSession.session_id)}
                  loading={actionLoading === `extract-${selectedSession.session_id}`}
                >
                  <Sparkles className="w-3 h-3 mr-1" />
                  Extract
                </Button>
              )}
            </div>
            {ideas.length === 0 ? (
              <p className="text-xs text-gray-500">
                {isOver ? 'Click Extract to generate ideas' : 'Ideas will appear after conclusion'}
              </p>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {ideas.map((idea) => (
                  <div key={idea.idea_id} className="bg-white/5 rounded-lg p-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-xs text-white font-medium truncate">{idea.title}</p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          by {AGENT_ICONS[idea.author_agent] || '🤖'} {idea.author_agent}
                        </p>
                        {idea.score && (
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-xs text-yellow-400">
                              <Star className="w-3 h-3 inline mr-0.5" />
                              {idea.score.overall.toFixed(2)}
                            </span>
                            {idea.score.effort_estimate && (
                              <span className="text-xs text-gray-500">
                                Effort: {idea.score.effort_estimate}
                              </span>
                            )}
                          </div>
                        )}
                        {idea.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {idea.tags.map((tag) => (
                              <span key={tag} className="text-xs px-1 py-0.5 rounded bg-white/5 text-gray-400">
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      {!idea.converted_to_product && isOver && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handlePromoteIdea(selectedSession.session_id, idea.idea_id)}
                          loading={actionLoading === `promote-${idea.idea_id}`}
                          title="Promote to product"
                        >
                          <Zap className="w-3 h-3 text-yellow-400" />
                        </Button>
                      )}
                      {idea.converted_to_product && (
                        <Badge variant="success">Product</Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </GlassCard>

          {/* Summary (if concluded) */}
          {selectedSession.results?.summary && (
            <GlassCard className="p-3">
              <h3 className="text-sm font-medium text-white mb-2 flex items-center gap-1.5">
                <MessageCircle className="w-4 h-4 text-green-400" />
                Summary
              </h3>
              <p className="text-xs text-gray-400 whitespace-pre-wrap leading-relaxed">
                {selectedSession.results.summary}
              </p>
            </GlassCard>
          )}

          {/* Consensus / Divergence */}
          {selectedSession.results?.consensus_topics && selectedSession.results.consensus_topics.length > 0 && (
            <GlassCard className="p-3">
              <h3 className="text-sm font-medium text-white mb-2 flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-green-400" />
                Consensus
              </h3>
              <div className="space-y-1">
                {selectedSession.results.consensus_topics.slice(0, 5).map((topic: string, i: number) => (
                  <div key={i} className="flex items-start gap-2 text-xs text-gray-400">
                    <span className="text-green-400 mt-0.5">✓</span>
                    <span>{topic}</span>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {selectedSession.results?.divergence_points && selectedSession.results.divergence_points.length > 0 && (
            <GlassCard className="p-3">
              <h3 className="text-sm font-medium text-white mb-2 flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4 text-yellow-400" />
                Divergence
              </h3>
              <div className="space-y-1">
                {selectedSession.results.divergence_points.slice(0, 3).map((point: string, i: number) => (
                  <div key={i} className="flex items-start gap-2 text-xs text-gray-400">
                    <span className="text-yellow-400 mt-0.5">⚠</span>
                    <span>{point}</span>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}
        </div>
      </div>
    </div>
  );
}
