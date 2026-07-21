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
  Search,
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

export function CorporateChatTab({ locale }: { locale: AdminLocale }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const [chatUsername, setChatUsername] = useState('Owner');
  const [showSettings, setShowSettings] = useState(false);
  const [settingsUsername, setSettingsUsername] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [standupRunning, setStandupRunning] = useState(false);
  const [messageSearch, setMessageSearch] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  function roleLabel(msg: ChatMessage): string | null {
    const r = msg.role;
    if (r === 'owner') return 'Owner';
    if (r === 'director') return 'Director';
    if (r === 'agent') return msg.agent_type ? `${msg.agent_type}` : 'Agent';
    if (r === 'system') return 'System';
    return null;
  }

  // Load messages and settings on mount
  useEffect(() => {
    loadData();
  }, []);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, messageSearch]);

  async function loadData() {
    try {
      const [msgRes, settingsRes] = await Promise.all([
        api.getChatMessages(),
        api.getChatSettings(),
      ]);
      setMessages(msgRes.messages);
      setChatUsername(settingsRes.chat_username);
      setSettingsUsername(settingsRes.chat_username);
    } catch (err) {
      console.error('Failed to load chat data', err);
      toast.error('Failed to load chat');
    } finally {
      setLoading(false);
    }
  }

  async function handleSend() {
    const text = newMessage.trim();
    if (!text) return;
    setSending(true);
    try {
      const res = await api.sendChatMessage(text);
      setMessages(prev => [...prev, res.message]);
      setNewMessage('');
    } catch (err) {
      toast.error('Failed to send message');
    } finally {
      setSending(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteChatMessage(id);
      setMessages(prev => prev.filter(m => m.id !== id));
    } catch (err) {
      toast.error('Failed to delete message');
    }
  }

  async function handleSaveSettings() {
    const name = settingsUsername.trim();
    if (!name) {
      toast.error('Username cannot be empty');
      return;
    }
    try {
      const res = await api.updateChatSettings({ chat_username: name });
      setChatUsername(res.chat_username);
      setShowSettings(false);
      toast.success('Owner display name updated');
    } catch (err) {
      toast.error('Failed to update settings');
    }
  }

  async function handleRunStandup() {
    setStandupRunning(true);
    try {
      await api.runDirectorStandup();
      toast.success('Standup posted to chat');
      const msgRes = await api.getChatMessages();
      setMessages(msgRes.messages);
    } catch (err: any) {
      toast.error(err?.message || 'Standup failed');
    } finally {
      setStandupRunning(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const filteredMessages = useMemo(() => {
    const q = messageSearch.trim().toLowerCase();
    if (!q) return messages;
    return messages.filter((msg) => {
      const text = String(msg.text || '').toLowerCase();
      const user = String(msg.username || '').toLowerCase();
      const role = String(msg.role || '').toLowerCase();
      const agent = String(msg.agent_type || '').toLowerCase();
      const id = String(msg.id || '').toLowerCase();
      return (
        text.includes(q) ||
        user.includes(q) ||
        role.includes(q) ||
        agent.includes(q) ||
        id.includes(q)
      );
    });
  }, [messages, messageSearch]);

  if (loading) {
    return (
      <GlassCard hover={false} className="p-6">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400" />
        </div>
      </GlassCard>
    );
  }

  return (
    <GlassCard
      hover={false}
      className="flex min-h-0 flex-col overflow-hidden p-4 max-md:h-[calc(100dvh-8rem)] md:h-[calc(100vh-10rem)] md:p-6"
    >
      {/* Header — tighter on small screens so the thread stays visible */}
      <div className="mb-2 flex shrink-0 flex-col gap-3 border-b border-white/10 pb-2 max-md:gap-2 md:mb-4 md:gap-4 md:pb-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <MessageCircle className="h-6 w-6 shrink-0 text-cyan-400" />
          <h2 className="text-xl font-bold text-white">{t(locale, 'corpChat.title')}</h2>
          <span className="text-sm text-gray-400">
            You are <span className="text-cyan-300 font-medium">Owner</span>:{' '}
            <span className="text-white">{chatUsername}</span>
          </span>
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
          <div className="relative min-w-[12rem] flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" aria-hidden />
            <Input
              value={messageSearch}
              onChange={(e) => setMessageSearch(e.target.value)}
              placeholder="Search chat…"
              className="w-full pl-9"
              aria-label="Search messages in corporate chat"
            />
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleRunStandup}
            disabled={standupRunning}
            title="Post a standup now (same flow as scheduled)"
            className="flex-1 sm:flex-initial"
          >
            {standupRunning ? 'Running…' : 'Run standup now'}
          </Button>
          <button
            onClick={() => { setShowSettings(!showSettings); setSettingsUsername(chatUsername); }}
            className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
            title="Chat Settings"
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Mobile: long intro collapsed by default — otherwise it eats the whole viewport */}
      <details className="mb-2 shrink-0 rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-3 py-2 text-sm text-gray-300 md:hidden">
        <summary className="cursor-pointer list-none text-left marker:content-none [&::-webkit-details-marker]:hidden">
          <span className="font-medium text-cyan-300">About this tab</span>
          <span className="text-gray-400"> — Corporate Chat vs Brainstorming (tap to expand)</span>
        </summary>
        <div className="mt-3 border-t border-white/10 pt-3 text-[13px] leading-relaxed">
          <strong className="text-cyan-300">Corporate Chat</strong> is the ongoing company channel: Owner, scheduled Director
          standups, and agent-style updates.{' '}
          <strong className="text-purple-300">Brainstorming &amp; Discussions</strong> are separate session-based workshops
          with rounds and outcomes. Full comparison:{' '}
          <code className="rounded bg-black/30 px-1 text-xs">docs/corporate-chat-vs-discussions.md</code>.
        </div>
      </details>

      {/* Desktop: keep full explainer visible */}
      <div className="mb-4 hidden shrink-0 rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-3 text-sm text-gray-300 md:block">
        <strong className="text-cyan-300">Corporate Chat</strong> is the ongoing company channel: Owner, scheduled Director standups,
        and agent-style updates.{' '}
        <strong className="text-purple-300">Brainstorming &amp; Discussions</strong> are separate session-based workshops with rounds and outcomes.
        Full comparison: <code className="text-xs bg-black/30 px-1 rounded">docs/corporate-chat-vs-discussions.md</code>.
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="mb-4 shrink-0 rounded-lg border border-white/10 bg-white/5 p-4">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Owner display name (shown on your messages)
          </label>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              value={settingsUsername}
              onChange={(e) => setSettingsUsername(e.target.value)}
              placeholder="Enter username"
              className="min-w-0 flex-1"
            />
            <div className="flex gap-2 shrink-0">
              <Button onClick={handleSaveSettings} variant="primary">
                Save
              </Button>
              <Button onClick={() => setShowSettings(false)} variant="ghost">
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Messages area — flex-1 + min-h-0 so header/settings can grow without overflowing the card border */}
      <div className="custom-scrollbar min-h-0 flex-1 space-y-3 overflow-y-auto pr-1 md:pr-2">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500">
            <div className="text-center">
              <MessageCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>No messages yet. Start the conversation!</p>
            </div>
          </div>
        ) : filteredMessages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500">
            <div className="text-center px-4">
              <MessageCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>No messages match your search.</p>
              <button
                type="button"
                className="mt-2 text-sm text-indigo-300 hover:text-indigo-200 underline underline-offset-2"
                onClick={() => setMessageSearch('')}
              >
                Clear search
              </button>
            </div>
          </div>
        ) : (
          filteredMessages.map((msg) => (
            <div
              key={msg.id}
              className="group flex items-start gap-3 p-3 rounded-lg bg-white/5 hover:bg-white/[0.07] transition-colors"
            >
              {/* Avatar */}
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
                {msg.username.charAt(0).toUpperCase()}
              </div>
              {/* Message content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="font-semibold text-white text-sm">{msg.username}</span>
                  {roleLabel(msg) && (
                    <Badge variant="info" className="text-[10px] px-1.5 py-0">
                      {roleLabel(msg)}
                    </Badge>
                  )}
                  <span className="text-xs text-gray-500">
                    {new Date(msg.timestamp).toLocaleString()}
                  </span>
                </div>
                <p className="text-gray-200 mt-1 text-sm whitespace-pre-wrap break-words">{msg.text}</p>
              </div>
              {/* Delete button */}
              <button
                onClick={() => handleDelete(msg.id)}
                className="touch-manipulation flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg p-1.5 text-gray-500 opacity-100 transition-all hover:bg-red-500/20 hover:text-red-400 max-md:active:bg-red-500/25 md:min-h-0 md:min-w-0 md:opacity-0 md:group-hover:opacity-100"
                title="Delete message"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="mt-4 shrink-0 border-t border-white/10 pt-3">
        <div className="flex gap-2">
          <textarea
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Message as Owner (${chatUsername})...`}
            className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/30 resize-none text-sm"
            rows={2}
          />
          <Button
            onClick={handleSend}
            variant="primary"
            loading={sending}
            disabled={!newMessage.trim()}
            className="self-end"
          >
            <Send className="w-4 h-4 mr-1.5" />
            Send
          </Button>
        </div>
      </div>
    </GlassCard>
  );
}
