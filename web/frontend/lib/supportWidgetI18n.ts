/**
 * Storefront Lumen support widget — UI strings and quick prompts (en / ru / es).
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
  return 'en-US';
}
