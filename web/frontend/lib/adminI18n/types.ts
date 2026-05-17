export type AdminLocale = 'en' | 'ru' | 'es';

export type I18nRow = Record<AdminLocale, string>;

export type I18nDict = Record<string, I18nRow>;
