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

export const CONTENT_LOCALE_OPTIONS: {
  code: ContentLocaleCode;
  label: Record<'en' | 'ru' | 'es', string>;
  reach?: string;
}[] = [
  { code: 'auto', label: { en: 'Auto (brief + UI language)', ru: 'Авто (бриф + язык интерфейса)', es: 'Auto (brief + idioma UI)' } },
  { code: 'en', label: { en: 'English', ru: 'Английский', es: 'Inglés' }, reach: 'global' },
  { code: 'ru', label: { en: 'Russian', ru: 'Русский', es: 'Ruso' }, reach: 'RU/CIS' },
  { code: 'es', label: { en: 'Spanish', ru: 'Испанский', es: 'Español' }, reach: 'ES/LATAM' },
  { code: 'de', label: { en: 'German', ru: 'Немецкий', es: 'Alemán' }, reach: 'DACH/EU' },
  { code: 'fr', label: { en: 'French', ru: 'Французский', es: 'Francés' }, reach: 'FR/EU/Africa' },
  { code: 'pt', label: { en: 'Portuguese', ru: 'Португальский', es: 'Portugués' }, reach: 'BR/PT' },
  { code: 'it', label: { en: 'Italian', ru: 'Итальянский', es: 'Italiano' }, reach: 'IT/EU' },
  { code: 'pl', label: { en: 'Polish', ru: 'Польский', es: 'Polaco' }, reach: 'PL/EU' },
  { code: 'uk', label: { en: 'Ukrainian', ru: 'Украинский', es: 'Ucraniano' }, reach: 'UA' },
  { code: 'tr', label: { en: 'Turkish', ru: 'Турецкий', es: 'Turco' }, reach: 'TR' },
  { code: 'zh', label: { en: 'Chinese (Simplified)', ru: 'Китайский (упрощ.)', es: 'Chino (simpl.)' }, reach: 'CN' },
  { code: 'ja', label: { en: 'Japanese', ru: 'Японский', es: 'Japonés' }, reach: 'JP' },
  { code: 'ko', label: { en: 'Korean', ru: 'Корейский', es: 'Coreano' }, reach: 'KR' },
  { code: 'ar', label: { en: 'Arabic', ru: 'Арабский', es: 'Árabe' }, reach: 'MENA' },
  { code: 'hi', label: { en: 'Hindi', ru: 'Хинди', es: 'Hindi' }, reach: 'IN' },
  { code: 'id', label: { en: 'Indonesian', ru: 'Индонезийский', es: 'Indonesio' }, reach: 'ID' },
  { code: 'vi', label: { en: 'Vietnamese', ru: 'Вьетнамский', es: 'Vietnamita' }, reach: 'VN' },
];

export function contentLocaleLabel(code: ContentLocaleCode, ui: 'en' | 'ru' | 'es'): string {
  const row = CONTENT_LOCALE_OPTIONS.find((o) => o.code === code);
  return row?.label[ui] ?? row?.label.en ?? code;
}

/** Map admin UI locale to default interface locale for new products. */
export function adminLocaleToInterface(locale: 'en' | 'ru' | 'es'): Exclude<ContentLocaleCode, 'auto'> {
  return locale;
}
