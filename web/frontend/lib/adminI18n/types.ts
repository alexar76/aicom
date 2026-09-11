export type AdminLocale = 'en' | 'ru' | 'es' | 'fr' | 'zh';

// en/ru/es are the baseline (always present); fr/zh are optional so dict modules
// can be filled incrementally — t() falls back to `en` for any missing locale.
export type I18nRow = Record<'en' | 'ru' | 'es', string> & Partial<Record<'fr' | 'zh', string>>;

export type I18nDict = Record<string, I18nRow>;
