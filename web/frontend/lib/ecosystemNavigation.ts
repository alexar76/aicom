import type { MarketingLocale } from '@/lib/marketing';

const labels = {
  en: ['You are in the working factory', 'About the factory', 'Explore the ecosystem'],
  ru: ['Вы в рабочей фабрике', 'О фабрике', 'Исследовать экосистему'],
  es: ['Estás en la fábrica', 'Conocer la fábrica', 'Explorar el ecosistema'],
  fr: ['Vous êtes dans la fabrique', 'Découvrir la fabrique', 'Explorer l’écosystème'],
  zh: ['你正在使用工厂', '了解工厂', '探索生态系统'],
} as const;

export function ecosystemNavigation(locale: MarketingLocale) {
  const path = locale === 'en' ? '/' : `/${locale}/`;
  const [current, factory, ecosystem] = labels[locale];
  return {
    current,
    links: [
      { label: factory, href: `https://modeldev.modelmarket.dev${path}` },
      { label: ecosystem, href: `https://ecosystem.modelmarket.dev${path}` },
    ],
  };
}
