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

export function CorporateChatTab() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const [chatUsername, setChatUsername] = useState('Owner');
  const [showSettings, setShowSettings] = useState(false);
  const [settingsUsername, setSettingsUsername] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [standupRunning, setStandupRunning] = useState(false);
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
  }, [messages]);

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

  if (loading) {
    return (
      <GlassCard className="p-6">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400" />
        </div>
      </GlassCard>
    );
  }

  return (
    <GlassCard className="p-6 flex flex-col h-[calc(100vh-12rem)]">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-white/10">
        <div className="flex items-center gap-3 flex-wrap">
          <MessageCircle className="w-6 h-6 text-cyan-400" />
          <h2 className="text-xl font-bold text-white">Corporate Chat</h2>
          <span className="text-sm text-gray-400">
            You are <span className="text-cyan-300 font-medium">Owner</span>:{' '}
            <span className="text-white">{chatUsername}</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleRunStandup}
            disabled={standupRunning}
            title="Post a standup now (same flow as scheduled)"
          >
            {standupRunning ? 'Running…' : 'Run standup now'}
          </Button>
          <button
            onClick={() => { setShowSettings(!showSettings); setSettingsUsername(chatUsername); }}
            className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-colors"
            title="Chat Settings"
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="mb-4 rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-3 text-sm text-gray-300">
        <strong className="text-cyan-300">Corporate Chat</strong> is the ongoing company channel: Owner, scheduled Director standups,
        and agent-style updates.{' '}
        <strong className="text-purple-300">Brainstorming &amp; Discussions</strong> are separate session-based workshops with rounds and outcomes.
        Full comparison: <code className="text-xs bg-black/30 px-1 rounded">docs/corporate-chat-vs-discussions.md</code>.
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="mb-4 p-4 rounded-lg bg-white/5 border border-white/10">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Owner display name (shown on your messages)
          </label>
          <div className="flex gap-2">
            <Input
              value={settingsUsername}
              onChange={(e) => setSettingsUsername(e.target.value)}
              placeholder="Enter username"
              className="flex-1"
            />
            <Button onClick={handleSaveSettings} variant="primary">
              Save
            </Button>
            <Button onClick={() => setShowSettings(false)} variant="ghost">
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto space-y-3 pr-2 custom-scrollbar">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500">
            <div className="text-center">
              <MessageCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>No messages yet. Start the conversation!</p>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
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
                className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-red-500/20 text-gray-500 hover:text-red-400 transition-all"
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
      <div className="mt-4 pt-3 border-t border-white/10">
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
