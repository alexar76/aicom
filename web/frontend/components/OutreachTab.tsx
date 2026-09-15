'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Megaphone, Loader2, Send, Sparkles, Save } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import api from '@/lib/api';
import type { AdminLocale } from '@/lib/adminI18n';
import toast from 'react-hot-toast';

type Channel = {
  id: string;
  type: string;
  name: string;
  enabled: boolean;
  help?: string;
  url_env?: string;
  token_env?: string;
  chat_id_env?: string;
  env_profile?: string;
};

type Announcement = {
  id: string;
  title: string;
  body_markdown?: string;
  body_plain?: string | null;
  audience: string;
  author_role: string;
  status: string;
  created_at: number;
  sent_at?: number;
  send_log?: Array<{ channel_id?: string; ok: boolean; detail?: string }>;
};

const TXT = {
  title: { en: 'Outreach & Announcements', ru: 'Аутрич и анонсы', es: 'Difusión y anuncios', fr: 'Communication et annonces', zh: '外联与公告' },
  subtitle: {
    en: 'Credentials stay in server environment variables only (see .env.example). Manage channels and launches for Marketing, Sales, and Director here.',
    ru: 'Креды только в переменных окружения на сервере (см. .env.example). Здесь — включение каналов и запуск рассылок для маркетинга, продаж и директора.',
    es: 'Las credenciales solo viven en variables de entorno del servidor (ver .env.example). Aquí se gestionan canales y envíos para Marketing, Ventas y Director.',
    fr: 'Les identifiants restent uniquement dans les variables d’environnement du serveur (voir .env.example). Gérez ici les canaux et les envois pour le Marketing, les Ventes et le Directeur.',
    zh: '凭据仅保存在服务器环境变量中（见 .env.example）。在此管理市场、销售和总监的渠道与发送。',
  },
  channels: { en: 'Channels', ru: 'Каналы', es: 'Canales', fr: 'Canaux', zh: '渠道' },
  save: { en: 'Save', ru: 'Сохранить', es: 'Guardar', fr: 'Enregistrer', zh: '保存' },
  newAnnouncement: { en: 'New announcement', ru: 'Новый анонс', es: 'Nuevo anuncio', fr: 'Nouvelle annonce', zh: '新公告' },
  authorRole: { en: 'Author role', ru: 'Роль автора', es: 'Rol del autor', fr: 'Rôle de l’auteur', zh: '作者角色' },
  audience: { en: 'Audience (tag)', ru: 'Аудитория (метка)', es: 'Audiencia (etiqueta)', fr: 'Audience (étiquette)', zh: '受众（标签）' },
  titleLabel: { en: 'Title / subject', ru: 'Заголовок / тема', es: 'Título / asunto', fr: 'Titre / objet', zh: '标题 / 主题' },
  bodyLabel: { en: 'Body (plain)', ru: 'Текст (plain)', es: 'Texto (plano)', fr: 'Corps (texte brut)', zh: '正文（纯文本）' },
  draftWithLlm: { en: 'Draft with LLM', ru: 'Черновик с LLM', es: 'Borrador con LLM', fr: 'Rédiger avec le LLM', zh: '用 LLM 起草' },
  saveDraft: { en: 'Save draft', ru: 'Сохранить черновик', es: 'Guardar borrador', fr: 'Enregistrer le brouillon', zh: '保存草稿' },
  history: { en: 'History', ru: 'История', es: 'Historial', fr: 'Historique', zh: '历史' },
  send: { en: 'Send', ru: 'Отправить', es: 'Enviar', fr: 'Envoyer', zh: '发送' },
  marketing: { en: 'Marketing', ru: 'Маркетинг', es: 'Marketing', fr: 'Marketing', zh: '市场' },
  sales: { en: 'Sales', ru: 'Продажи', es: 'Ventas', fr: 'Ventes', zh: '销售' },
  director: { en: 'Director', ru: 'Директор', es: 'Director', fr: 'Directeur', zh: '总监' },
  topicPlaceholder: { en: 'Email or post subject', ru: 'Тема письма или поста', es: 'Asunto de correo o publicación', fr: 'Objet de l’e-mail ou du post', zh: '邮件或帖子主题' },
  bodyPlaceholder: { en: 'Message text…', ru: 'Текст сообщения…', es: 'Texto del mensaje…', fr: 'Texte du message…', zh: '消息内容…' },
  loadFailed: { en: 'Load failed', ru: 'Load failed', es: 'Load failed', fr: 'Échec du chargement', zh: '加载失败' },
  saveFailed: { en: 'Save failed', ru: 'Save failed', es: 'Save failed', fr: 'Échec de l’enregistrement', zh: '保存失败' },
  createFailed: { en: 'Create failed', ru: 'Create failed', es: 'Create failed', fr: 'Échec de la création', zh: '创建失败' },
  sendFailed: { en: 'Send failed', ru: 'Send failed', es: 'Send failed', fr: 'Échec de l’envoi', zh: '发送失败' },
  channelsSaved: { en: 'Channels saved', ru: 'Каналы сохранены', es: 'Canales guardados', fr: 'Canaux enregistrés', zh: '渠道已保存' },
  enterTitle: {
    en: 'Enter topic or draft in title first',
    ru: 'Введите тему / черновик в заголовок',
    es: 'Primero escribe el tema o borrador en el título',
    fr: 'Saisissez d’abord un sujet ou un brouillon dans le titre',
    zh: '请先在标题中输入主题或草稿',
  },
  draftGenerated: { en: 'Draft generated', ru: 'Черновик сгенерирован', es: 'Borrador generado', fr: 'Brouillon généré', zh: '草稿已生成' },
  llmUnavailable: { en: 'LLM unavailable', ru: 'LLM недоступен', es: 'LLM no disponible', fr: 'LLM indisponible', zh: 'LLM 不可用' },
  titleAndBodyRequired: { en: 'Title and body are required', ru: 'Заголовок и текст обязательны', es: 'Título y texto son obligatorios', fr: 'Le titre et le corps sont obligatoires', zh: '标题和正文为必填项' },
  draftCreated: { en: 'Draft created', ru: 'Черновик создан', es: 'Borrador creado', fr: 'Brouillon créé', zh: '草稿已创建' },
  sent: { en: 'Sent', ru: 'Отправлено', es: 'Enviado', fr: 'Envoyé', zh: '已发送' },
  sendFailedSeeLog: { en: 'Send failed — check channel log', ru: 'Отправка не удалась — см. лог каналов', es: 'No se pudo enviar — revisa el log del canal', fr: 'Échec de l’envoi — consultez le journal du canal', zh: '发送失败——请查看渠道日志' },
  ok: { en: 'ok', ru: 'ok', es: 'ok', fr: 'ok', zh: 'ok' },
  fail: { en: 'fail', ru: 'fail', es: 'fail', fr: 'échec', zh: '失败' },
};

const tt = (locale: AdminLocale, key: keyof typeof TXT) => TXT[key][locale] || TXT[key].en;

export default function OutreachTab({ locale = 'en' }: { locale?: AdminLocale }) {
  const [channelsDoc, setChannelsDoc] = useState<{ version: number; channels: Channel[] } | null>(null);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [audience, setAudience] = useState('all');
  const [authorRole, setAuthorRole] = useState('marketing');
  const [suggesting, setSuggesting] = useState(false);
  const [sendingId, setSendingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ch, ann] = await Promise.all([api.getOutreachChannels(), api.getOutreachAnnouncements()]);
      setChannelsDoc(ch as { version: number; channels: Channel[] });
      setAnnouncements((ann.items || []) as Announcement[]);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : tt(locale, 'loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [locale]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleChannel = (id: string) => {
    setChannelsDoc((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        channels: prev.channels.map((c) => (c.id === id ? { ...c, enabled: !c.enabled } : c)),
      };
    });
  };

  const saveChannels = async () => {
    if (!channelsDoc) return;
    setSaving(true);
    try {
      await api.putOutreachChannels(channelsDoc);
      toast.success(tt(locale, 'channelsSaved'));
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : tt(locale, 'saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const suggest = async () => {
    if (!title.trim()) {
      toast.error(tt(locale, 'enterTitle'));
      return;
    }
    setSuggesting(true);
    try {
      const r = await api.suggestOutreachCopy(title, 'professional, concise', 'customers and storefront visitors');
      setTitle(r.title);
      setBody(r.body_plain);
      toast.success(tt(locale, 'draftGenerated'));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : tt(locale, 'llmUnavailable'));
    } finally {
      setSuggesting(false);
    }
  };

  const createDraft = async () => {
    if (!title.trim() || !body.trim()) {
      toast.error(tt(locale, 'titleAndBodyRequired'));
      return;
    }
    try {
      const r = await api.createOutreachAnnouncement({
        title: title.trim(),
        body_markdown: body.trim(),
        body_plain: body.trim(),
        audience,
        author_role: authorRole,
        channel_ids: [],
      });
      toast.success(tt(locale, 'draftCreated'));
      setTitle('');
      setBody('');
      setAnnouncements((prev) => [r.announcement as Announcement, ...prev]);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : tt(locale, 'createFailed'));
    }
  };

  const sendAnn = async (id: string) => {
    setSendingId(id);
    try {
      const r = await api.sendOutreachAnnouncement(id);
      if (r.ok) toast.success(tt(locale, 'sent'));
      else toast.error(tt(locale, 'sendFailedSeeLog'));
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : tt(locale, 'sendFailed'));
    } finally {
      setSendingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-white flex items-center gap-2">
          <Megaphone className="w-6 h-6 text-fuchsia-400" />
          {tt(locale, 'title')}
        </h2>
        <p className="text-sm text-gray-400 mt-1">
          {tt(locale, 'subtitle')}
        </p>
      </div>

      {loading || !channelsDoc ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 text-fuchsia-400 animate-spin" />
        </div>
      ) : (
        <>
          <GlassCard className="p-4 space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <h3 className="text-sm font-medium text-white">{tt(locale, 'channels')}</h3>
              <Button variant="primary" onClick={() => void saveChannels()} disabled={saving} className="w-full sm:w-auto">
                <Save className="w-4 h-4 mr-1" />
                {saving ? '…' : tt(locale, 'save')}
              </Button>
            </div>
            <div className="space-y-2">
              {channelsDoc.channels.map((c) => (
                <label
                  key={c.id}
                  className="flex items-start gap-3 rounded-lg border border-white/10 bg-black/20 p-3 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={c.enabled}
                    onChange={() => toggleChannel(c.id)}
                    className="mt-1"
                  />
                  <div>
                    <div className="text-sm text-white font-medium">{c.name}</div>
                    <div className="text-xs text-gray-500 font-mono">{c.type}</div>
                    {c.help && <p className="text-xs text-gray-400 mt-1">{c.help}</p>}
                  </div>
                </label>
              ))}
            </div>
          </GlassCard>

          <GlassCard className="p-4 space-y-3">
            <h3 className="text-sm font-medium text-white">{tt(locale, 'newAnnouncement')}</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-500">{tt(locale, 'authorRole')}</label>
                <select
                  value={authorRole}
                  onChange={(e) => setAuthorRole(e.target.value)}
                  className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white"
                >
                  <option value="marketing">{tt(locale, 'marketing')}</option>
                  <option value="sales">{tt(locale, 'sales')}</option>
                  <option value="director">{tt(locale, 'director')}</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-gray-500">{tt(locale, 'audience')}</label>
                <Input value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="all" />
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-500">{tt(locale, 'titleLabel')}</label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={tt(locale, 'topicPlaceholder')} />
            </div>
            <div>
              <label className="text-xs text-gray-500">{tt(locale, 'bodyLabel')}</label>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={6}
                className="w-full mt-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white"
                placeholder={tt(locale, 'bodyPlaceholder')}
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="ghost" onClick={() => void suggest()} disabled={suggesting}>
                <Sparkles className="w-4 h-4 mr-1" />
                {suggesting ? '…' : tt(locale, 'draftWithLlm')}
              </Button>
              <Button variant="primary" onClick={() => void createDraft()}>
                {tt(locale, 'saveDraft')}
              </Button>
            </div>
          </GlassCard>

          <div>
            <h3 className="text-sm font-medium text-white mb-2">{tt(locale, 'history')}</h3>
            <div className="space-y-2">
              {announcements.map((a) => (
                <GlassCard key={a.id} className="flex flex-col gap-3 p-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <div className="text-sm text-white font-medium">{a.title}</div>
                    <div className="text-xs text-gray-500">
                      {a.author_role} · {a.status} · {new Date((a.sent_at || a.created_at) * 1000).toLocaleString()}
                    </div>
                    {a.send_log && a.send_log.length > 0 && (
                      <ul className="text-[11px] text-gray-500 mt-1 list-disc pl-4">
                        {a.send_log.map((l, i) => (
                          <li key={i}>
                            {l.channel_id}: {l.ok ? tt(locale, 'ok') : tt(locale, 'fail')} — {l.detail}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  {a.status === 'draft' && (
                    <Button
                      variant="primary"
                      onClick={() => void sendAnn(a.id)}
                      disabled={sendingId === a.id}
                    >
                      <Send className="w-4 h-4 mr-1" />
                      {sendingId === a.id ? '…' : tt(locale, 'send')}
                    </Button>
                  )}
                </GlassCard>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
