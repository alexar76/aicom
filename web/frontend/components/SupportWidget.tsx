'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { MessageCircle, X, Send, Loader2, AlertCircle, Mic, MicOff } from 'lucide-react';
import api from '@/lib/api';
import { getSupportMessageBlockReason } from '@/lib/promptSafety';
import {
  enqueueOutboundMessage,
  isSupportAuthError,
  loadOutboundQueue,
  parseQueuedContext,
  removeOutboundById,
  shouldRetrySupportSend,
  type QueuedSupportMessage,
  withRetries,
} from '@/lib/supportDelivery';
import {
  detectSupportWidgetLocale,
  getQuickPrompts,
  getSupportWidgetText,
  speechRecognitionLang,
  type QuickPromptSection,
  type SupportWidgetLocale,
} from '@/lib/supportWidgetI18n';

const STORAGE_KEY = 'aif_support_v1';
const MAX_LEN = 4000;

type StoredSession = {
  sessionId: string;
  accessToken: string;
  productId: string | null;
  createdAt: number;
};

type UIContext = {
  current_page?: string;
  active_tab?: string;
  selected_product_id?: string;
  preferred_locale?: string;
};

function parseProductIdFromPath(pathname: string): string | null {
  const m = pathname.match(/\/product\/(prod-[a-zA-Z0-9-]+)/);
  return m ? m[1] : null;
}

function sectionFromPath(pathname: string): QuickPromptSection {
  if (!pathname || pathname === '/') return 'home';
  if (pathname.startsWith('/product/')) return 'product';
  if (pathname.startsWith('/explore')) return 'explore';
  if (pathname.startsWith('/docs')) return 'docs';
  if (pathname.startsWith('/checkout')) return 'checkout';
  if (pathname.startsWith('/account')) return 'account';
  if (pathname.startsWith('/iq')) return 'iq';
  return 'other';
}

function loadStored(): StoredSession | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const j = JSON.parse(raw) as StoredSession;
    if (!j?.sessionId || !j?.accessToken) return null;
    if (Date.now() - (j.createdAt || 0) > 86400_000) {
      sessionStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return j;
  } catch {
    return null;
  }
}

function saveStored(s: StoredSession) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(s));
}

/** Web Speech API — Chromium-based browsers; availability varies on iOS / WebView. */
function getSpeechRecognitionCtor(): SpeechRecognitionConstructor | null {
  if (typeof window === 'undefined') return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

type MicGate = { proceed: true } | { proceed: false; userMessage: string };

/**
 * Ensures mic access: uses Permissions API when possible, then getUserMedia (browser prompt on «ask»).
 * If the user previously chose «Block», many browsers never show the prompt again — we explain how to reset.
 */
async function gateMicrophoneForDictation(locale: SupportWidgetLocale): Promise<MicGate> {
  if (typeof window === 'undefined') return { proceed: true };
  const tr = getSupportWidgetText(locale);

  if (!window.isSecureContext) {
    return {
      proceed: false,
      userMessage: tr.micNeedsHttps,
    };
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    return {
      proceed: false,
      userMessage: tr.micNoMediaDevices,
    };
  }

  try {
    const perm = await navigator.permissions?.query({ name: 'microphone' as PermissionName });
    if (perm?.state === 'denied') {
      return {
        proceed: false,
        userMessage: tr.micPermBlocked,
      };
    }
  } catch {
    /* Permissions API may be unavailable; continue with getUserMedia. */
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((t) => t.stop());
    return { proceed: true };
  } catch (e) {
    const denied =
      e instanceof DOMException &&
      (e.name === 'NotAllowedError' || e.name === 'PermissionDeniedError' || e.name === 'SecurityError');
    if (denied) {
      return {
        proceed: false,
        userMessage: tr.micDeniedShort,
      };
    }
    return {
      proceed: false,
      userMessage: tr.micDeviceBusy,
    };
  }
}

export function SupportWidget() {
  const pathname = usePathname();
  const [locale, setLocale] = useState<SupportWidgetLocale>(() => detectSupportWidgetLocale());
  const productId = useMemo(() => parseProductIdFromPath(pathname || ''), [pathname]);
  const quickPromptSection = useMemo(() => sectionFromPath(pathname || ''), [pathname]);
  const quickPrompts = useMemo(
    () => getQuickPrompts(quickPromptSection, locale),
    [quickPromptSection, locale]
  );
  const uiContext = useMemo<UIContext>(
    () => ({
      current_page: pathname || '/',
      active_tab: quickPromptSection,
      selected_product_id: productId || undefined,
      preferred_locale: locale,
    }),
    [pathname, quickPromptSection, productId, locale]
  );
  const tr = useMemo(() => getSupportWidgetText(locale), [locale]);

  useEffect(() => {
    const syncLocale = () => setLocale(detectSupportWidgetLocale());
    const onStorage = (e: StorageEvent) => {
      if (e.key === 'marketing_locale' || e.key === null) syncLocale();
    };
    window.addEventListener('marketing-locale-changed', syncLocale);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('marketing-locale-changed', syncLocale);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  /** live = API ok; disabled = server turned chat off; unknown = status fetch failed after retries (still show FAB). */
  const [gate, setGate] = useState<'pending' | 'live' | 'disabled' | 'unknown'>('pending');
  const [requireToken, setRequireToken] = useState(true);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<
    Array<{ role: string; content: string; ts?: number; meta?: Record<string, unknown> }>
  >([]);
  const [input, setInput] = useState('');
  const [session, setSession] = useState<StoredSession | null>(null);
  const [voiceListening, setVoiceListening] = useState(false);
  const [micBusy, setMicBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const sessionRef = useRef<StoredSession | null>(null);
  const flushRunningRef = useRef(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const voiceInputSnapshotRef = useRef('');
  const voiceFinalAccumRef = useRef('');
  const inputRef = useRef(input);
  inputRef.current = input;
  sessionRef.current = session;

  const [outboundQueue, setOutboundQueue] = useState<QueuedSupportMessage[]>(() => loadOutboundQueue());

  const publicWidgetOff =
    typeof process !== 'undefined' && process.env.NEXT_PUBLIC_SUPPORT_WIDGET === '0';

  useEffect(() => {
    if (publicWidgetOff) return;
    let cancelled = false;
    const delaysMs = [0, 400, 1200, 2500];
    (async () => {
      for (let attempt = 0; attempt < delaysMs.length; attempt++) {
        if (attempt > 0) await new Promise((r) => setTimeout(r, delaysMs[attempt]));
        if (cancelled) return;
        try {
          const st = await api.getSupportStatus();
          if (cancelled) return;
          setGate(st.enabled ? 'live' : 'disabled');
          setRequireToken(!!st.require_token);
          return;
        } catch {
          if (attempt === delaysMs.length - 1 && !cancelled) setGate('unknown');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [publicWidgetOff]);

  const bootstrapSession = useCallback(async () => {
    const stored = loadStored();
    if (stored && stored.productId === productId) {
      setSession(stored);
      return stored;
    }
    const created = await api.createSupportSession(productId ?? undefined, uiContext);
    const s: StoredSession = {
      sessionId: created.session_id,
      accessToken: created.access_token,
      productId: created.product_id ?? productId ?? null,
      createdAt: Date.now(),
    };
    saveStored(s);
    setSession(s);
    return s;
  }, [productId, uiContext]);

  const refreshMessages = useCallback(
    async (s: StoredSession) => {
      const data = await api.getSupportSession(s.sessionId, s.accessToken);
      setMessages((data.messages || []) as typeof messages);
    },
    []
  );

  const flushOutboundQueue = useCallback(async () => {
    if (flushRunningRef.current) return;
    const sess = sessionRef.current;
    if (!sess) return;
    flushRunningRef.current = true;
    setSending(true);
    try {
      for (;;) {
        const batch = loadOutboundQueue();
        if (batch.length === 0) break;
        const head = batch[0];
        try {
          await withRetries(
            () =>
              api.sendSupportMessage(
                sess.sessionId,
                sess.accessToken,
                head.text,
                parseQueuedContext(head)
              ),
            { attempts: 4, delaysMs: [0, 700, 1800, 4000] }
          );
          setOutboundQueue((prev) => removeOutboundById(prev, head.id));
          setError(null);
          await refreshMessages(sess);
        } catch (e) {
          if (isSupportAuthError(e)) {
            try {
              sessionStorage.removeItem(STORAGE_KEY);
            } catch {
              /* ignore */
            }
            setSession(null);
            setError(e instanceof Error ? e.message : tr.sendError);
            break;
          }
          if (!shouldRetrySupportSend(e)) {
            setError(e instanceof Error ? e.message : tr.sendError);
            setOutboundQueue((prev) => removeOutboundById(prev, head.id));
            continue;
          }
          setError(tr.queueWillRetry);
          break;
        }
      }
    } finally {
      flushRunningRef.current = false;
      setSending(false);
    }
  }, [refreshMessages, tr.queueWillRetry, tr.sendError]);

  useEffect(() => {
    if (!open || !session || publicWidgetOff) return;
    refreshMessages(session).catch(() => setError('Could not load conversation history'));
  }, [open, session, refreshMessages, publicWidgetOff]);

  /** Periodically retry queued messages after a blip. */
  useEffect(() => {
    if (!open || !session || publicWidgetOff) return;
    const tick = () => {
      if (loadOutboundQueue().length === 0) return;
      void flushOutboundQueue();
    };
    const id = window.setInterval(tick, 22_000);
    return () => window.clearInterval(id);
  }, [open, session, publicWidgetOff, flushOutboundQueue]);

  /** Drain queue when opening or session restored. */
  useEffect(() => {
    if (!open || !session || publicWidgetOff) return;
    if (loadOutboundQueue().length === 0) return;
    void flushOutboundQueue();
  }, [open, session, publicWidgetOff, flushOutboundQueue]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, open]);

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.abort();
      } catch {
        /* ignore */
      }
      recognitionRef.current = null;
    };
  }, []);

  const handleOpen = async () => {
    if (publicWidgetOff) return;
    if (gate === 'disabled') {
      setOpen(true);
      setError('Support chat is disabled on server (AIFACTORY_SUPPORT_CHAT_ENABLED).');
      return;
    }
    setError(null);
    setOpen(true);
    setLoading(true);
    try {
      let s = loadStored();
      if (!s || s.productId !== productId) {
        s = await bootstrapSession();
      } else {
        setSession(s);
      }
      await refreshMessages(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : tr.connectError);
      try {
        sessionStorage.removeItem(STORAGE_KEY);
      } catch {
        /* ignore */
      }
      setSession(null);
    } finally {
      setLoading(false);
    }
  };

  const stopVoiceInput = useCallback(() => {
    try {
      recognitionRef.current?.abort();
    } catch {
      /* ignore */
    }
    recognitionRef.current = null;
    setVoiceListening(false);
  }, []);

  const toggleVoiceInput = useCallback(async () => {
    if (voiceListening) {
      stopVoiceInput();
      return;
    }
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) {
      setError(tr.voiceUnavailable);
      return;
    }
    if (sending || micBusy) return;
    if (!session) return;

    setError(null);
    setMicBusy(true);
    const gate = await gateMicrophoneForDictation(locale);
    setMicBusy(false);
    if (!gate.proceed) {
      setError(gate.userMessage);
      return;
    }

    voiceInputSnapshotRef.current = inputRef.current;
    voiceFinalAccumRef.current = '';
    const rec = new Ctor();
    rec.lang = speechRecognitionLang(locale);
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;

    rec.onresult = (event: SpeechRecognitionEvent) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const piece = event.results[i][0]?.transcript ?? '';
        if (event.results[i].isFinal) voiceFinalAccumRef.current += piece;
        else interim += piece;
      }
      const base = voiceInputSnapshotRef.current.trimEnd();
      const spoken = (voiceFinalAccumRef.current + interim).trim();
      const sep = base && spoken ? ' ' : '';
      setInput((base + sep + spoken).slice(0, MAX_LEN));
    };

    rec.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error === 'aborted' || event.error === 'no-speech') return;
      if (event.error === 'not-allowed') {
        setError(tr.micRecognitionDenied);
      } else {
        setError(event.message || event.error);
      }
      setVoiceListening(false);
      recognitionRef.current = null;
    };

    rec.onend = () => {
      setVoiceListening(false);
      recognitionRef.current = null;
    };

    recognitionRef.current = rec;
    setVoiceListening(true);
    try {
      rec.start();
    } catch (e) {
      setVoiceListening(false);
      recognitionRef.current = null;
      setError(e instanceof Error ? e.message : tr.micStartError);
    }
  }, [voiceListening, session, sending, micBusy, stopVoiceInput, locale, tr]);

  const handleSend = async () => {
    stopVoiceInput();
    const text = input.trim();
    if (!text || !session) return;
    const block = getSupportMessageBlockReason(text);
    if (block) {
      setError(block);
      return;
    }
    setError(null);
    setInput('');
    setOutboundQueue((prev) => enqueueOutboundMessage(prev, text, uiContext));
    await flushOutboundQueue();
  };

  const applyQuickPrompt = (text: string) => {
    const block = getSupportMessageBlockReason(text);
    if (block) {
      setError(block);
      return;
    }
    setError(null);
    setInput((prev) => {
      const base = prev.trim();
      if (!base) return text.slice(0, MAX_LEN);
      return `${base}\n${text}`.slice(0, MAX_LEN);
    });
  };

  if (publicWidgetOff) return null;
  if ((pathname || '').startsWith('/admin')) return null;
  if (gate === 'disabled') return null;

  return (
    <>
      <button
        type="button"
        aria-label={tr.openAria(tr.botDefault)}
        aria-expanded={open}
        onClick={() => (open ? setOpen(false) : void handleOpen())}
        className="fixed bottom-8 right-5 z-[400] flex h-14 w-14 items-center justify-center rounded-full border border-cyan-500/40 bg-gradient-to-br from-slate-900/95 to-indigo-950/95 text-cyan-200 shadow-lg shadow-cyan-900/30 backdrop-blur-md transition hover:border-cyan-400/60 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/80 md:bottom-10 md:right-8"
      >
        {loading ? <Loader2 className="h-6 w-6 animate-spin" /> : <MessageCircle className="h-6 w-6" />}
      </button>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="support-widget-title"
          className="fixed bottom-24 right-5 z-[400] flex w-[min(100vw-2.5rem,22rem)] flex-col overflow-hidden rounded-2xl border border-white/10 bg-slate-950/95 shadow-2xl backdrop-blur-xl md:bottom-28 md:right-8"
        >
          <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <div>
              <h2 id="support-widget-title" className="text-sm font-semibold text-white">
                {tr.botDefault}
              </h2>
              <p className="text-[11px] text-slate-400">{tr.subtitle}</p>
              {gate === 'pending' && (
                <p className="text-[10px] text-slate-500 mt-1">{tr.checkingConnection}</p>
              )}
              {gate === 'unknown' && (
                <p className="text-[10px] text-amber-200/90 mt-1 leading-snug">{tr.serverAwayFriendly}</p>
              )}
              {outboundQueue.length > 0 && (
                <p className="text-[10px] text-cyan-200/80 mt-1">{tr.queueBadge(outboundQueue.length)}</p>
              )}
            </div>
            <button
              type="button"
              aria-label={tr.closeAria}
              onClick={() => setOpen(false)}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 hover:text-white"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {error && (
            <div className="flex items-start gap-2 border-b border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div ref={listRef} className="max-h-72 space-y-3 overflow-y-auto px-3 py-3">
            {messages.length === 0 && !loading && (
              <p className="text-xs text-slate-500">
                {tr.emptyHint}
              </p>
            )}
            {messages.map((m, i) => (
              <div
                key={`${m.ts}-${i}`}
                className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[92%] rounded-xl px-3 py-2 text-sm ${
                    m.role === 'user'
                      ? 'bg-cyan-600/25 text-cyan-50'
                      : 'bg-white/5 text-slate-100'
                  }`}
                >
                  <div className="whitespace-pre-wrap break-words">{m.content}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="border-t border-white/10 p-3">
            <div className="mb-2 flex flex-wrap gap-1.5">
              {quickPrompts.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => applyQuickPrompt(q)}
                  className="rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-[11px] text-slate-300 hover:bg-white/10 hover:text-white"
                  disabled={sending || !session}
                >
                  {q}
                </button>
              ))}
            </div>
            <div className="relative mb-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value.slice(0, MAX_LEN))}
                placeholder={tr.messagePlaceholder}
                rows={3}
                className="min-h-[5.5rem] w-full resize-none rounded-xl border border-white/10 bg-black/30 py-2 pl-3 pr-14 text-sm text-white placeholder:text-slate-500 focus:border-cyan-500/40 focus:outline-none"
                disabled={sending || !session}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    void handleSend();
                  }
                }}
              />
              <button
                type="button"
                onClick={() => void toggleVoiceInput()}
                disabled={sending || micBusy}
                aria-pressed={voiceListening}
                aria-label={voiceListening ? tr.stopDictation : tr.dictation}
                title={getSpeechRecognitionCtor() ? (voiceListening ? tr.stopDictation : tr.dictation) : tr.unavailable}
                className={`absolute bottom-3 right-3 flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-2 text-white shadow-lg transition focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/80 disabled:pointer-events-none disabled:opacity-40 ${
                  voiceListening
                    ? 'border-rose-300/60 bg-rose-600 hover:bg-rose-500 animate-pulse'
                    : 'border-cyan-400/50 bg-cyan-600 hover:bg-cyan-500 hover:scale-105 active:scale-95'
                }`}
              >
                {micBusy ? (
                  <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
                ) : voiceListening ? (
                  <MicOff className="h-5 w-5" aria-hidden />
                ) : (
                  <Mic className="h-5 w-5" aria-hidden />
                )}
              </button>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[10px] text-slate-500">
                {requireToken ? tr.secureSession : tr.devMode}
              </span>
              <button
                type="button"
                onClick={() => void handleSend()}
                disabled={sending || !session || !input.trim()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-cyan-500 disabled:opacity-40"
              >
                {sending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                {tr.send}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
