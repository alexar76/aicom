# Languages

## Default: English

Wiki pages, [`docs/`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/README.md), and the repository README are **English-first** — operator and developer reference.

## Optional wiki / docs companions

| Language | Wiki | Full guides in repo |
|----------|------|---------------------|
| **Russian** | [[FAQ-RU]] | [`USER_GUIDE.ru.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.ru.md), [`FAQ.ru.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/FAQ.ru.md) |
| **Spanish** | [[FAQ-ES]] | [`USER_GUIDE.es.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.es.md), [`FAQ.es.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/FAQ.es.md) |

## Product UI (en / ru / es)

Separate from documentation locale:

| Surface | How |
|---------|-----|
| **Storefront** | `NEXT_PUBLIC_MARKETING_LOCALE=es` → [`marketing-es.ts`](http://5.129.212.122/Superowner/aicom/src/branch/main/web/frontend/lib/marketing-es.ts) |
| **Admin panel** | In-app language switcher (en, ru, es) |
| **Support (Lumen)** | Replies respect user `locale` including `es` |

You can run a **Spanish storefront** with **English wiki** — by design, not a bug.

Spanish companions match Russian depth (`USER_GUIDE.es.md`, `FAQ.es.md` in the main repo). Wiki [[FAQ-ES]] links there; technical `docs/*.md` remain English.
