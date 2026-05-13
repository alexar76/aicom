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

const STORAGE_KEY = 'aif_support_v1';
const MAX_LEN = 4000;
type WidgetLocale = 'en' | 'ru';

const UI_TEXT: Record<
  WidgetLocale,
  {
    botDefault: string;
    connectError: string;
    voiceUnavailable: string;
    micStartError: string;
    micRecognitionDenied: string;
    micNeedsHttps: string;
    micNoMediaDevices: string;
    micPermBlocked: string;
    micDeniedShort: string;
    micDeviceBusy: string;
    sendError: string;
    openAria: (name: string) => string;
    subtitle: string;
    closeAria: string;
    emptyHint: string;
    messagePlaceholder: string;
    stopDictation: string;
    dictation: string;
    unavailable: string;
    secureSession: string;
    devMode: string;
    send: string;
    checkingConnection: string;
    serverAwayFriendly: string;
    queueBadge: (n: number) => string;
    queueWillRetry: string;
  }
> = {
  en: {
    botDefault: 'Support',
    connectError: 'Connection error',
    voiceUnavailable:
      'Voice typing isn’t available in this browser. Use the keyboard, or try Chrome, Edge, or Samsung Internet on an up-to-date device.',
    micStartError: 'Could not start speech recognition',
    micRecognitionDenied:
      'Speech recognition needs microphone access. Tap the lock or “site settings” icon in the address bar, allow the microphone, reload the page, and try again.',
    micNeedsHttps:
      'Microphone only works on a secure page (https:// or localhost). Open this site with HTTPS and try again.',
    micNoMediaDevices:
      'This browser doesn’t expose microphone access the way this chat needs. Try Chrome, Edge, or Samsung Internet, reload the page, and try again.',
    micPermBlocked:
      'The microphone is already blocked for this site, so the browser may not show a prompt again. Open site settings for this page, allow the microphone, reload, then try dictation.',
    micDeniedShort:
      'Microphone access was denied. Open site settings for this page, allow the microphone, and try again.',
    micDeviceBusy:
      'Could not use the microphone (no device or it’s busy in another app).',
    sendError: 'Send error',
    openAria: (name) => `Open chat: ${name}`,
    subtitle: 'AI-Factory marketplace support',
    checkingConnection: 'Checking connection…',
    serverAwayFriendly:
      'Our assistant briefly stepped away — we’re retrying in the background. Your messages stay in line here and send automatically when the connection is back.',
    queueBadge: (n: number) =>
      n === 1 ? '1 message queued — sending when online…' : `${n} messages queued — sending when online…`,
    queueWillRetry: 'Still offline — we’ll keep trying. Leave this tab open or come back later.',
    closeAria: 'Close',
    emptyHint:
      'Write a message or use the button at the bottom-right of the input. From a product page the bot understands context better.',
    messagePlaceholder: 'Message…',
    stopDictation: 'Stop',
    dictation: 'Dictation',
    unavailable: 'Unavailable',
    secureSession: 'Signed-in chat',
    devMode: 'Development mode',
    send: 'Send',
  },
  ru: {
    botDefault: 'Поддержка',
    connectError: 'Ошибка соединения',
    voiceUnavailable:
      'Голосовой ввод в этом браузере недоступен. Наберите текст с клавиатуры или откройте страницу в Chrome, Edge или Samsung Internet с обновлениями системы.',
    micStartError: 'Не удалось запустить распознавание речи',
    micRecognitionDenied:
      'Для диктовки нужен доступ к микрофону. Нажмите на замок или настройки сайта в адресной строке, разрешите микрофон, обновите страницу и повторите.',
    micNeedsHttps:
      'Микрофон доступен только по защищённому соединению (https:// или localhost). Откройте сайт по HTTPS и попробуйте снова.',
    micNoMediaDevices:
      'В этом браузере нет нужного доступа к микрофону. Попробуйте Chrome, Edge или Samsung Internet, обновите страницу и повторите.',
    micPermBlocked:
      'Микрофон для этого сайта уже заблокирован, поэтому запрос может не появиться. Откройте настройки сайта, разрешите микрофон, обновите страницу и снова нажмите диктовку.',
    micDeniedShort:
      'Доступ к микрофону отклонён. В настройках сайта разрешите микрофон и попробуйте снова.',
    micDeviceBusy:
      'Не удалось использовать микрофон (нет устройства или оно занято в другом приложении).',
    sendError: 'Ошибка отправки',
    openAria: (name) => `Открыть чат: ${name}`,
    subtitle: 'Поддержка маркетплейса AI-Factory',
    checkingConnection: 'Проверяем соединение…',
    serverAwayFriendly:
      'Помощник временно недоступен — в фоне идут повторные попытки. Сообщения остаются в очереди и уйдут автоматически, когда связь восстановится.',
    queueBadge: (n: number) =>
      n === 1
        ? '1 сообщение в очереди — отправим при появлении сети…'
        : `${n} сообщ. в очереди — отправим при появлении сети…`,
    queueWillRetry: 'Сеть всё ещё недоступна — попробуем снова. Оставьте вкладку открытой или зайдите позже.',
    closeAria: 'Закрыть',
    emptyHint:
      'Напишите сообщение или воспользуйтесь кнопкой у поля ввода. На странице продукта бот лучше понимает контекст.',
    messagePlaceholder: 'Сообщение…',
    stopDictation: 'Стоп',
    dictation: 'Диктовка',
    unavailable: 'Недоступно',
    secureSession: 'Чат с авторизацией',
    devMode: 'Режим разработки',
    send: 'Отправить',
  },
};

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
};

type QuickPromptSection =
  | 'home'
  | 'product'
  | 'explore'
  | 'docs'
  | 'checkout'
  | 'account'
  | 'other';

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
  return 'other';
}

function quickPromptsFor(section: QuickPromptSection): string[] {
  if (section === 'product') {
    return [
      'What does this product do in one sentence?',
      'How do I quickly validate this product in sandbox?',
      'If something is broken here, what details should I report?',
    ];
  }
  if (section === 'explore') {
    return [
      'How do I choose a product category?',
      'What does product status mean on cards?',
      'How can I compare two products quickly?',
    ];
  }
  if (section === 'docs') {
    return [
      'Give me a quick start checklist for AI-Factory.',
      'Where are API endpoints for products and sandbox?',
      'How does the pipeline flow from idea to storefront?',
    ];
  }
  if (section === 'checkout') {
    return [
      'How does payment and access delivery work here?',
      'What should I do if checkout fails?',
      'How can I verify my order status?',
    ];
  }
  if (section === 'account') {
    return [
      'Where can I download purchased products?',
      'How do referrals work?',
      'What should I do if I cannot see my order?',
    ];
  }
  if (section === 'home') {
    return [
      'What is AI-Factory in plain words?',
      'How do I go from idea to working product here?',
      'Where should I start as a new user?',
    ];
  }
  return [
    'Can you explain what this page is for?',
    'What should I do next from here?',
    'If something fails, what details should I share with support?',
  ];
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

function pickRecognitionLang(): string {
  if (typeof navigator === 'undefined') return 'en-US';
  const n = (navigator.language || '').toLowerCase();
  if (n.startsWith('ru')) return 'ru-RU';
  if (n.startsWith('en')) return 'en-US';
  return navigator.language || 'en-US';
}

type MicGate = { proceed: true } | { proceed: false; userMessage: string };

function detectWidgetLocale(): WidgetLocale {
  if (typeof navigator === 'undefined') return 'en';
  const lang = (navigator.language || '').toLowerCase();
  if (lang.startsWith('ru')) return 'ru';
  return 'en';
}

/**
 * Ensures mic access: uses Permissions API when possible, then getUserMedia (browser prompt on «ask»).
 * If the user previously chose «Block», many browsers never show the prompt again — we explain how to reset.
 */
async function gateMicrophoneForDictation(locale: WidgetLocale): Promise<MicGate> {
  if (typeof window === 'undefined') return { proceed: true };
  const tr = UI_TEXT[locale];

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
  const productId = useMemo(() => parseProductIdFromPath(pathname || ''), [pathname]);
  const quickPromptSection = useMemo(() => sectionFromPath(pathname || ''), [pathname]);
  const quickPrompts = useMemo(() => quickPromptsFor(quickPromptSection), [quickPromptSection]);
  const uiContext = useMemo<UIContext>(
    () => ({
      current_page: pathname || '/',
      active_tab: quickPromptSection,
      selected_product_id: productId || undefined,
    }),
    [pathname, quickPromptSection, productId]
  );
  const locale = detectWidgetLocale();
  const tr = UI_TEXT[locale];

  /** live = API ok; disabled = server turned chat off; unknown = status fetch failed after retries (still show FAB). */
  const [gate, setGate] = useState<'pending' | 'live' | 'disabled' | 'unknown'>('pending');
  const [requireToken, setRequireToken] = useState(true);
  const [botName, setBotName] = useState(tr.botDefault);
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
          if (st.bot_name) {
            const hasCyrillic = /\p{Script=Cyrillic}/u.test(st.bot_name);
            setBotName(locale === 'en' && hasCyrillic ? tr.botDefault : st.bot_name);
          }
          return;
        } catch {
          if (attempt === delaysMs.length - 1 && !cancelled) setGate('unknown');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [publicWidgetOff, locale, tr.botDefault]);

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
    rec.lang = pickRecognitionLang();
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
  }, [voiceListening, session, sending, micBusy, stopVoiceInput]);

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
        aria-label={tr.openAria(botName)}
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
                {botName}
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
