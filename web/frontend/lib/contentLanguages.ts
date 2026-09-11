/** Supported landing / UI copy languages for the factory pipeline. */
export type ContentLocaleCode =
  | 'auto'
  | 'en'
  | 'ru'
  | 'es'
  | 'de'
  | 'fr'
  | 'pt'
  | 'it'
  | 'pl'
  | 'uk'
  | 'tr'
  | 'zh'
  | 'ja'
  | 'ko'
  | 'ar'
  | 'hi'
  | 'id'
  | 'vi';

export type ContentLocaleChoice = ContentLocaleCode;

type LocaleLabel = Record<'en' | 'ru' | 'es', string> & Partial<Record<'fr' | 'zh', string>>;

export const CONTENT_LOCALE_OPTIONS: {
  code: ContentLocaleCode;
  label: LocaleLabel;
  reach?: string;
}[] = [
  { code: 'auto', label: { en: 'Auto (brief + UI language)', ru: 'Авто (бриф + язык интерфейса)', es: 'Auto (brief + idioma UI)', fr: 'Auto (brief + langue UI)', zh: '自动（简报 + 界面语言）' } },
  { code: 'en', label: { en: 'English', ru: 'Английский', es: 'Inglés', fr: 'Anglais', zh: '英语' }, reach: 'global' },
  { code: 'ru', label: { en: 'Russian', ru: 'Русский', es: 'Ruso', fr: 'Russe', zh: '俄语' }, reach: 'RU/CIS' },
  { code: 'es', label: { en: 'Spanish', ru: 'Испанский', es: 'Español', fr: 'Espagnol', zh: '西班牙语' }, reach: 'ES/LATAM' },
  { code: 'de', label: { en: 'German', ru: 'Немецкий', es: 'Alemán', fr: 'Allemand', zh: '德语' }, reach: 'DACH/EU' },
  { code: 'fr', label: { en: 'French', ru: 'Французский', es: 'Francés', fr: 'Français', zh: '法语' }, reach: 'FR/EU/Africa' },
  { code: 'pt', label: { en: 'Portuguese', ru: 'Португальский', es: 'Portugués', fr: 'Portugais', zh: '葡萄牙语' }, reach: 'BR/PT' },
  { code: 'it', label: { en: 'Italian', ru: 'Итальянский', es: 'Italiano', fr: 'Italien', zh: '意大利语' }, reach: 'IT/EU' },
  { code: 'pl', label: { en: 'Polish', ru: 'Польский', es: 'Polaco', fr: 'Polonais', zh: '波兰语' }, reach: 'PL/EU' },
  { code: 'uk', label: { en: 'Ukrainian', ru: 'Украинский', es: 'Ucraniano', fr: 'Ukrainien', zh: '乌克兰语' }, reach: 'UA' },
  { code: 'tr', label: { en: 'Turkish', ru: 'Турецкий', es: 'Turco', fr: 'Turc', zh: '土耳其语' }, reach: 'TR' },
  { code: 'zh', label: { en: 'Chinese (Simplified)', ru: 'Китайский (упрощ.)', es: 'Chino (simpl.)', fr: 'Chinois (simplifié)', zh: '中文（简体）' }, reach: 'CN' },
  { code: 'ja', label: { en: 'Japanese', ru: 'Японский', es: 'Japonés', fr: 'Japonais', zh: '日语' }, reach: 'JP' },
  { code: 'ko', label: { en: 'Korean', ru: 'Корейский', es: 'Coreano', fr: 'Coréen', zh: '韩语' }, reach: 'KR' },
  { code: 'ar', label: { en: 'Arabic', ru: 'Арабский', es: 'Árabe', fr: 'Arabe', zh: '阿拉伯语' }, reach: 'MENA' },
  { code: 'hi', label: { en: 'Hindi', ru: 'Хинди', es: 'Hindi', fr: 'Hindi', zh: '印地语' }, reach: 'IN' },
  { code: 'id', label: { en: 'Indonesian', ru: 'Индонезийский', es: 'Indonesio', fr: 'Indonésien', zh: '印尼语' }, reach: 'ID' },
  { code: 'vi', label: { en: 'Vietnamese', ru: 'Вьетнамский', es: 'Vietnamita', fr: 'Vietnamien', zh: '越南语' }, reach: 'VN' },
];

export function contentLocaleLabel(code: ContentLocaleCode, ui: 'en' | 'ru' | 'es' | 'fr' | 'zh'): string {
  const row = CONTENT_LOCALE_OPTIONS.find((o) => o.code === code);
  return row?.label[ui] ?? row?.label.en ?? code;
}

/** Map admin UI locale to default interface locale for new products. */
export function adminLocaleToInterface(locale: 'en' | 'ru' | 'es' | 'fr' | 'zh'): Exclude<ContentLocaleCode, 'auto'> {
  return locale;
}
