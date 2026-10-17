import en from "./en.js";
import ru from "./ru.js";
import es from "./es.js";
import fr from "./fr.js";
import zh from "./zh.js";

/** English first: it is the default page, the x-default alternate and the reference for keys. */
export const LANGS = ["en", "ru", "es", "fr", "zh"];
export const STRINGS = { en, ru, es, fr, zh };

/** BCP 47 tags for <html lang> and hreflang. */
export const HTML_LANG = { en: "en", ru: "ru", es: "es", fr: "fr", zh: "zh-Hans" };
export const OG_LOCALE = { en: "en_US", ru: "ru_RU", es: "es_ES", fr: "fr_FR", zh: "zh_CN" };
