/**
 * Storefront Lumen support widget — UI strings and quick prompts (en / ru / es / fr / zh).
 * Locale follows `marketing_locale` in localStorage (same as home page language switcher).
 */

import { detectMarketingLocale, type MarketingLocale } from '@/lib/marketing';

export type SupportWidgetLocale = MarketingLocale;

export type QuickPromptSection =
  | 'home'
  | 'product'
  | 'explore'
  | 'docs'
  | 'checkout'
  | 'account'
  | 'iq'
  | 'other';

type WidgetText = {
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
};

const UI: Record<SupportWidgetLocale, WidgetText> = {
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
    micDeviceBusy: 'Could not use the microphone (no device or it’s busy in another app).',
    sendError: 'Send error',
    openAria: (name) => `Open chat: ${name}`,
    subtitle: 'AI-Factory marketplace support',
    checkingConnection: 'Checking connection…',
    serverAwayFriendly:
      'Our assistant briefly stepped away — we’re retrying in the background. Your messages stay in line here and send automatically when the connection is back.',
    queueBadge: (n) =>
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
    queueBadge: (n) =>
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
  es: {
    botDefault: 'Soporte',
    connectError: 'Error de conexión',
    voiceUnavailable:
      'El dictado por voz no está disponible en este navegador. Use el teclado o pruebe Chrome, Edge o Samsung Internet actualizado.',
    micStartError: 'No se pudo iniciar el reconocimiento de voz',
    micRecognitionDenied:
      'El reconocimiento de voz necesita acceso al micrófono. Toque el candado o la configuración del sitio, permita el micrófono, recargue la página e intente de nuevo.',
    micNeedsHttps:
      'El micrófono solo funciona en una página segura (https:// o localhost). Abra el sitio con HTTPS e intente de nuevo.',
    micNoMediaDevices:
      'Este navegador no expone el micrófono como requiere el chat. Pruebe Chrome, Edge o Samsung Internet, recargue e intente de nuevo.',
    micPermBlocked:
      'El micrófono ya está bloqueado para este sitio. Abra la configuración del sitio, permita el micrófono, recargue y vuelva a dictar.',
    micDeniedShort:
      'Se denegó el acceso al micrófono. En la configuración del sitio permita el micrófono e intente de nuevo.',
    micDeviceBusy:
      'No se pudo usar el micrófono (sin dispositivo o ocupado en otra app).',
    sendError: 'Error al enviar',
    openAria: (name) => `Abrir chat: ${name}`,
    subtitle: 'Soporte del marketplace AI-Factory',
    checkingConnection: 'Comprobando conexión…',
    serverAwayFriendly:
      'El asistente no está disponible por un momento; reintentamos en segundo plano. Los mensajes quedan en cola y se enviarán solos al volver la conexión.',
    queueBadge: (n) =>
      n === 1
        ? '1 mensaje en cola — se enviará al conectar…'
        : `${n} mensajes en cola — se enviarán al conectar…`,
    queueWillRetry: 'Sigue sin conexión — seguiremos intentando. Deje la pestaña abierta o vuelva más tarde.',
    closeAria: 'Cerrar',
    emptyHint:
      'Escriba un mensaje o use el botón junto al campo de entrada. En la página de un producto el bot entiende mejor el contexto.',
    messagePlaceholder: 'Mensaje…',
    stopDictation: 'Parar',
    dictation: 'Dictado',
    unavailable: 'No disponible',
    secureSession: 'Chat con sesión',
    devMode: 'Modo desarrollo',
    send: 'Enviar',
  },
  fr: {
    botDefault: 'Support',
    connectError: 'Erreur de connexion',
    voiceUnavailable:
      'La saisie vocale n’est pas disponible dans ce navigateur. Utilisez le clavier, ou essayez Chrome, Edge ou Samsung Internet sur un appareil à jour.',
    micStartError: 'Impossible de démarrer la reconnaissance vocale',
    micRecognitionDenied:
      'La reconnaissance vocale nécessite l’accès au microphone. Touchez le cadenas ou l’icône « paramètres du site » dans la barre d’adresse, autorisez le microphone, rechargez la page, puis réessayez.',
    micNeedsHttps:
      'Le microphone ne fonctionne que sur une page sécurisée (https:// ou localhost). Ouvrez ce site en HTTPS et réessayez.',
    micNoMediaDevices:
      'Ce navigateur n’expose pas l’accès au microphone comme ce chat en a besoin. Essayez Chrome, Edge ou Samsung Internet, rechargez la page, puis réessayez.',
    micPermBlocked:
      'Le microphone est déjà bloqué pour ce site, le navigateur peut donc ne plus afficher de demande. Ouvrez les paramètres du site pour cette page, autorisez le microphone, rechargez, puis lancez la dictée.',
    micDeniedShort:
      'L’accès au microphone a été refusé. Ouvrez les paramètres du site pour cette page, autorisez le microphone, puis réessayez.',
    micDeviceBusy: 'Impossible d’utiliser le microphone (aucun appareil ou occupé par une autre application).',
    sendError: 'Erreur d’envoi',
    openAria: (name) => `Ouvrir le chat : ${name}`,
    subtitle: 'Support de la place de marché AI-Factory',
    checkingConnection: 'Vérification de la connexion…',
    serverAwayFriendly:
      'Notre assistant s’est brièvement absenté — nous réessayons en arrière-plan. Vos messages restent en file ici et s’envoient automatiquement au retour de la connexion.',
    queueBadge: (n) =>
      n === 1
        ? '1 message en file — envoi dès que vous êtes en ligne…'
        : `${n} messages en file — envoi dès que vous êtes en ligne…`,
    queueWillRetry: 'Toujours hors ligne — nous continuons d’essayer. Laissez cet onglet ouvert ou revenez plus tard.',
    closeAria: 'Fermer',
    emptyHint:
      'Écrivez un message ou utilisez le bouton en bas à droite du champ de saisie. Depuis une page produit, le bot comprend mieux le contexte.',
    messagePlaceholder: 'Message…',
    stopDictation: 'Arrêter',
    dictation: 'Dictée',
    unavailable: 'Indisponible',
    secureSession: 'Chat connecté',
    devMode: 'Mode développement',
    send: 'Envoyer',
  },
  zh: {
    botDefault: '支持',
    connectError: '连接错误',
    voiceUnavailable:
      '此浏览器不支持语音输入。请使用键盘，或在最新版设备上尝试 Chrome、Edge 或三星浏览器。',
    micStartError: '无法启动语音识别',
    micRecognitionDenied:
      '语音识别需要麦克风权限。请点击地址栏中的锁形或「网站设置」图标，允许使用麦克风，重新加载页面后再试。',
    micNeedsHttps:
      '麦克风仅在安全页面（https:// 或 localhost）上可用。请以 HTTPS 打开本站后再试。',
    micNoMediaDevices:
      '此浏览器未按聊天所需的方式提供麦克风访问。请尝试 Chrome、Edge 或三星浏览器，重新加载页面后再试。',
    micPermBlocked:
      '本站的麦克风已被阻止，浏览器可能不再弹出提示。请打开本页的网站设置，允许使用麦克风，重新加载后再开始语音输入。',
    micDeniedShort:
      '麦克风访问被拒绝。请在本页的网站设置中允许使用麦克风后再试。',
    micDeviceBusy: '无法使用麦克风（没有设备或已被其他应用占用）。',
    sendError: '发送错误',
    openAria: (name) => `打开聊天：${name}`,
    subtitle: 'AI-Factory 交易市场支持',
    checkingConnection: '正在检查连接…',
    serverAwayFriendly:
      '我们的助手暂时离开了——正在后台重试。您的消息会在此排队，并在连接恢复后自动发送。',
    queueBadge: (n) =>
      n === 1 ? '1 条消息排队中——联网后发送…' : `${n} 条消息排队中——联网后发送…`,
    queueWillRetry: '仍处于离线状态——我们会继续尝试。请保持此标签页打开，或稍后再回来。',
    closeAria: '关闭',
    emptyHint:
      '输入消息，或使用输入框右下角的按钮。在产品页面上，机器人能更好地理解上下文。',
    messagePlaceholder: '消息…',
    stopDictation: '停止',
    dictation: '语音输入',
    unavailable: '不可用',
    secureSession: '已登录聊天',
    devMode: '开发模式',
    send: '发送',
  },
};

const QUICK: Record<SupportWidgetLocale, Record<QuickPromptSection, string[]>> = {
  en: {
    product: [
      'What does this product do in one sentence?',
      'How do I quickly validate this product in sandbox?',
      'If something is broken here, what details should I report?',
    ],
    explore: [
      'How do I choose a product category?',
      'What does product status mean on cards?',
      'How can I compare two products quickly?',
    ],
    docs: [
      'Give me a quick start checklist for AI-Factory.',
      'Where are API endpoints for products and sandbox?',
      'How does the pipeline flow from idea to storefront?',
    ],
    checkout: [
      'How does payment and access delivery work here?',
      'What should I do if checkout fails?',
      'How can I verify my order status?',
    ],
    account: [
      'Where can I download purchased products?',
      'How do referrals work?',
      'What should I do if I cannot see my order?',
    ],
    home: [
      'What is AI-Factory in plain words?',
      'How do I go from idea to working product here?',
      'Where should I start as a new user?',
    ],
    iq: [
      'What does Factory IQ measure?',
      'How is the swarm scoring each build?',
      'Why is my Factory IQ number what it is?',
    ],
    other: [
      'Can you explain what this page is for?',
      'What should I do next from here?',
      'If something fails, what details should I share with support?',
    ],
  },
  ru: {
    product: [
      'Что делает этот продукт одним предложением?',
      'Как быстро проверить продукт в песочнице?',
      'Если что-то сломано — какие детали указать в обращении?',
    ],
    explore: [
      'Как выбрать категорию продукта?',
      'Что означает статус на карточке?',
      'Как быстро сравнить два продукта?',
    ],
    docs: [
      'Краткий чеклист старта с AI-Factory.',
      'Где API для продуктов и sandbox?',
      'Как пайплайн ведёт от идеи до витрины?',
    ],
    checkout: [
      'Как работает оплата и выдача доступа?',
      'Что делать, если checkout не проходит?',
      'Как проверить статус заказа?',
    ],
    account: [
      'Где скачать купленные продукты?',
      'Как работают рефералы?',
      'Что делать, если не вижу заказ?',
    ],
    home: [
      'Что такое AI-Factory простыми словами?',
      'Как от идеи перейти к рабочему продукту?',
      'С чего начать новому пользователю?',
    ],
    iq: [
      'Что измеряет Factory IQ?',
      'Как рой моделей оценивает каждую сборку?',
      'Почему моё число Factory IQ такое?',
    ],
    other: [
      'Для чего эта страница?',
      'Что делать дальше отсюда?',
      'Если что-то не работает — что написать в поддержку?',
    ],
  },
  es: {
    product: [
      '¿Qué hace este producto en una frase?',
      '¿Cómo validar rápido este producto en el sandbox?',
      'Si algo falla aquí, ¿qué detalles debo reportar?',
    ],
    explore: [
      '¿Cómo elijo una categoría de producto?',
      '¿Qué significa el estado en las tarjetas?',
      '¿Cómo comparar dos productos rápido?',
    ],
    docs: [
      'Checklist rápido para empezar con AI-Factory.',
      '¿Dónde están los endpoints de productos y sandbox?',
      '¿Cómo fluye el pipeline de la idea a la vitrina?',
    ],
    checkout: [
      '¿Cómo funcionan el pago y la entrega del acceso?',
      '¿Qué hago si falla el checkout?',
      '¿Cómo verifico el estado de mi pedido?',
    ],
    account: [
      '¿Dónde descargo productos comprados?',
      '¿Cómo funcionan los referidos?',
      '¿Qué hago si no veo mi pedido?',
    ],
    home: [
      '¿Qué es AI-Factory en palabras simples?',
      '¿Cómo paso de una idea a un producto funcionando?',
      '¿Por dónde empiezo si soy nuevo?',
    ],
    iq: [
      '¿Qué mide Factory IQ?',
      '¿Cómo puntúa el enjambre cada build?',
      '¿Por qué mi número Factory IQ es así?',
    ],
    other: [
      '¿Para qué sirve esta página?',
      '¿Qué debería hacer a continuación?',
      'Si algo falla, ¿qué detalles comparto con soporte?',
    ],
  },
  fr: {
    product: [
      'Que fait ce produit en une phrase ?',
      'Comment valider rapidement ce produit dans le bac à sable ?',
      'Si quelque chose ne fonctionne pas ici, quels détails dois-je signaler ?',
    ],
    explore: [
      'Comment choisir une catégorie de produit ?',
      'Que signifie le statut du produit sur les cartes ?',
      'Comment comparer rapidement deux produits ?',
    ],
    docs: [
      'Donne-moi une checklist de démarrage rapide pour AI-Factory.',
      'Où sont les endpoints API pour les produits et le bac à sable ?',
      'Comment le pipeline passe-t-il de l’idée à la vitrine ?',
    ],
    checkout: [
      'Comment fonctionnent le paiement et la livraison de l’accès ici ?',
      'Que faire si le paiement échoue ?',
      'Comment vérifier le statut de ma commande ?',
    ],
    account: [
      'Où puis-je télécharger les produits achetés ?',
      'Comment fonctionnent les parrainages ?',
      'Que faire si je ne vois pas ma commande ?',
    ],
    home: [
      'Qu’est-ce qu’AI-Factory en mots simples ?',
      'Comment passer d’une idée à un produit fonctionnel ici ?',
      'Par où commencer en tant que nouvel utilisateur ?',
    ],
    iq: [
      'Que mesure Factory IQ ?',
      'Comment l’essaim note-t-il chaque build ?',
      'Pourquoi mon score Factory IQ est-il celui-ci ?',
    ],
    other: [
      'Peux-tu expliquer à quoi sert cette page ?',
      'Que dois-je faire ensuite à partir d’ici ?',
      'Si quelque chose échoue, quels détails partager avec le support ?',
    ],
  },
  zh: {
    product: [
      '用一句话说明这个产品的作用？',
      '如何在沙箱中快速验证这个产品？',
      '如果这里出了问题，我该反馈哪些细节？',
    ],
    explore: [
      '如何选择产品类别？',
      '卡片上的产品状态是什么意思？',
      '如何快速比较两个产品？',
    ],
    docs: [
      '给我一份 AI-Factory 快速上手清单。',
      '产品和沙箱的 API 端点在哪里？',
      '流水线如何从想法走到店面？',
    ],
    checkout: [
      '这里的支付和访问交付是如何工作的？',
      '如果结账失败我该怎么办？',
      '如何查看我的订单状态？',
    ],
    account: [
      '在哪里下载已购买的产品？',
      '推荐奖励如何运作？',
      '如果看不到我的订单该怎么办？',
    ],
    home: [
      '用简单的话说，AI-Factory 是什么？',
      '在这里如何从想法做到可用的产品？',
      '作为新用户我该从哪里开始？',
    ],
    iq: [
      'Factory IQ 衡量什么？',
      '模型集群如何为每次构建打分？',
      '为什么我的 Factory IQ 数值是这个？',
    ],
    other: [
      '能解释一下这个页面的用途吗？',
      '从这里接下来我该做什么？',
      '如果出错了，我该向支持团队分享哪些细节？',
    ],
  },
};

export function detectSupportWidgetLocale(): SupportWidgetLocale {
  return detectMarketingLocale();
}

export function getSupportWidgetText(locale: SupportWidgetLocale): WidgetText {
  return UI[locale] ?? UI.en;
}

export function getQuickPrompts(section: QuickPromptSection, locale: SupportWidgetLocale): string[] {
  return QUICK[locale]?.[section] ?? QUICK.en[section];
}

export function speechRecognitionLang(locale: SupportWidgetLocale): string {
  if (locale === 'ru') return 'ru-RU';
  if (locale === 'es') return 'es-ES';
  if (locale === 'fr') return 'fr-FR';
  if (locale === 'zh') return 'zh-CN';
  return 'en-US';
}
