#!/usr/bin/env python3
"""Write docs/value.md and inject plain-language value sections into README + user-guide."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (english, russian) — accessible language, no jargon
VALUES: dict[str, tuple[str, str, str]] = {
    # slug/path -> (title, en, ru)
    # --- Desktop apps ---
    "desktop-integrations/interview-prep-coach": (
        "Interview Prep Coach",
        "You get interview questions that are actually fresh — from this week, for your target company — "
        "instead of stale forum posts. Pay a few cents per question bank instead of a $500 course. "
        "Your practice answers stay on your computer; you only share anonymized patterns if you choose to sell them.",
        "Вы получаете актуальные вопросы с собеседований — за эту неделю, под вашу компанию — "
        "а не устаревшие посты с форумов. Платите копейки за банк вопросов вместо курса за $500. "
        "Ответы при практике остаются на вашем компьютере; в маркетплейс уходят только обезличенные паттерны, если вы сами решите их продать.",
    ),
    "desktop-integrations/personal-finance-coach": (
        "Personal Finance Coach",
        "Your bank data stays on your machine — not in someone else's cloud — while you still use smart "
        "categorization and tax rules bought from the marketplace. You keep privacy and get AI help with money.",
        "Данные банка остаются на вашем компьютере — не в чужом облаке — а умные категории и налоговые "
        "правила вы покупаете на маркетплейсе. Приватность сохраняется, помощь с деньгами — тоже.",
    ),
    "desktop-integrations/capability-composer": (
        "Capability Composer",
        "You visually connect AI building blocks into a pipeline — like Lego for AI services — without writing "
        "integration code. Test it, run it with one wallet, and sell your pipeline as a template to others.",
        "Вы собираете AI-блоки в цепочку на холсте — как конструктор — без написания интеграционного кода. "
        "Проверяете, запускаете с одним кошельком и можете продать свой пайплайн как шаблон.",
    ),
    "desktop-integrations/cold-outreach-coach": (
        "Cold Outreach Coach",
        "Your cold emails get better deliverability and reply rates. The app checks structure and rules locally; "
        "you buy fresh SPF/DKIM and tone rules from the market without sending your letter text to strangers.",
        "Холодные письма чаще попадают во входящие и получают ответы. Приложение проверяет структуру локально; "
        "правила доставки и тона покупаете на маркетплейсе, не отдавая текст письма посторонним.",
    ),
    "desktop-integrations/creator-algorithm-coach": (
        "Creator Algorithm Coach",
        "Creators see what TikTok, YouTube, and Instagram algorithms reward in their niche this week — "
        "not generic advice from a blog. Buy signal packs; optionally share anonymous metrics to earn credits.",
        "Авторы видят, что алгоритмы TikTok, YouTube и Instagram поощряют в их нише на этой неделе — "
        "не общие советы из блога. Покупаете пакеты сигналов; при желании делитесь анонимной статистикой за кредиты.",
    ),
    "desktop-integrations/discovery-prospector": (
        "Discovery Prospector",
        "Builders learn what people search for on the AI marketplace but nobody sells yet — so you build what "
        "has real demand instead of guessing. It's a radar for profitable gaps before competitors fill them.",
        "Разработчики видят, что люди ищут на AI-маркетплейсе, но никто не продаёт — можно строить то, "
        "на что есть спрос, а не гадать. Это радар прибыльных ниш до того, как их займут конкуренты.",
    ),
    "desktop-integrations/freelance-contract-reviewer": (
        "Freelance Contract Reviewer",
        "Freelancers read client contracts on their own computer before signing. For a few dollars you invoke "
        "jurisdiction-specific clause libraries instead of paying a lawyer hundreds for a simple MSA review.",
        "Фрилансеры читают договор клиента на своём компьютере до подписи. За несколько долларов вызываете "
        "библиотеки пунктов под вашу юрисдикцию вместо сотен долларов юристу за простой договор.",
    ),
    "desktop-integrations/reputation-dashboard": (
        "Reputation Dashboard",
        "Buyers see which AI capabilities are trustworthy — like reviews for apps, but tied to real purchases "
        "and receipts. Sellers earn trust with stake; curators flag abuse. Less scam, more informed spending.",
        "Покупатели видят, каким AI-сервисам можно доверять — как отзывы к приложениям, но привязанные к реальным "
        "покупкам и чекам. Продавцы копят репутацию; модераторы отсекают злоупотребления. Меньше обмана — больше осознанных трат.",
    ),
    # --- Hub plugins ---
    "plugins/aimarket-safety": (
        "aimarket-safety",
        "Stops dangerous or manipulative prompts before they reach any AI provider. If a call is blocked, "
        "you get a signed receipt and your money back — the marketplace stays safe for everyone.",
        "Останавливает опасные или манипулятивные промпты до того, как они дойдут до AI. При блокировке — "
        "подписанный чек и возврат денег. Маркетплейс остаётся безопасным для всех.",
    ),
    "plugins/aimarket-reputation": (
        "aimarket-reputation",
        "Shows who you can trust on the marketplace. Providers put money at stake; cheaters lose it. "
        "Buyers compare scores before paying — reputation becomes real, not fake stars.",
        "Показывает, кому на маркетплейсе можно доверять. Продавцы ставят залог; мошенники его теряют. "
        "Покупатели сравнивают баллы до оплаты — репутация настоящая, не накрученные звёзды.",
    ),
    "plugins/aimarket-channels": (
        "aimarket-channels",
        "Pay once into a prepaid tab, make dozens of tiny AI calls, settle once on-chain. "
        "No credit-card fee on every micro-cent — fast sessions for agents and apps.",
        "Пополняете «вкладку» один раз, делаете десятки мелких вызовов AI, закрываете один раз on-chain. "
        "Без комиссии карты на каждую копейку — быстрые сессии для агентов и приложений.",
    ),
    "plugins/aimarket-tee": (
        "aimarket-tee",
        "Runs sensitive AI inside secure hardware so even the server owner cannot read your input. "
        "You get a hardware attestation — proof the right code ran in a protected enclave.",
        "Чувствительный AI работает в защищённом железе — даже владелец сервера не видит ваш ввод. "
        "Получаете аппаратное подтверждение: нужный код выполнен в изолированной среде.",
    ),
    "plugins/aimarket-auction": (
        "aimarket-auction",
        "Scarce AI capacity goes to whoever values it most right now — like airline yield management. "
        "Providers earn more at peak; buyers save money off-peak.",
        "Редкая мощность AI достаётся тому, кому она сейчас важнее — как динамические цены у авиакомпаний. "
        "Продавцы зарабатывают в пик; покупатели экономят в спокойное время.",
    ),
    "plugins/aimarket-personas": (
        "aimarket-personas",
        "Gives each capability a clear, buyer-friendly AI persona — so non-technical users understand "
        "what they're buying without reading API docs.",
        "У каждой возможности появляется понятный «персонаж» AI — нетехническим пользователям ясно, "
        "что они покупают, без чтения API-документации.",
    ),
    "plugins/aimarket-streaming": (
        "aimarket-streaming",
        "Streams long AI answers token by token and charges fairly for what you actually read — "
        "stop early, pay less. Better for chat UIs and long reports.",
        "Длинные ответы AI идут по токенам, платите за то, что реально получили — остановили раньше, "
        "заплатили меньше. Удобно для чата и длинных отчётов.",
    ),
    "plugins/aimarket-nft": (
        "aimarket-nft",
        "Pre-paid AI credits as transferable tokens — gift them, resell unused balance, "
        "or run loyalty programs without building billing from scratch.",
        "Предоплаченные кредиты AI как передаваемые токены — подарить, перепродать остаток "
        "или сделать программу лояльности без биллинга с нуля.",
    ),
    "plugins/aimarket-mcp-packager": (
        "aimarket-mcp-packager",
        "Turns any marketplace capability into an MCP tool for Claude Desktop / Cursor in one step — "
        "authors reach agent users without hand-writing MCP servers.",
        "Превращает возможность маркетплейса в MCP-инструмент для Claude Desktop / Cursor за один шаг — "
        "авторы доходят до пользователей агентов без ручного MCP-сервера.",
    ),
    "plugins/aimarket-orchestrator": (
        "aimarket-orchestrator",
        "Describe a goal in plain language; the hub plans which AI capabilities to call in what order "
        "and estimates cost before spending — autopilot for multi-step tasks.",
        "Описываете цель простыми словами; хаб планирует, какие AI вызывать и в каком порядке, "
        "и оценивает стоимость до траты — автопилот для многошаговых задач.",
    ),
    "plugins/aimarket-data-cap": (
        "aimarket-data-cap",
        "Monetize private documents: others pay per search query, you never hand over raw files. "
        "Law firms, labs, and enterprises turn knowledge into revenue safely.",
        "Монетизируете закрытые документы: другие платят за поиск, сырые файлы вы не отдаёте. "
        "Юрфирмы, лаборатории и компании превращают знания в доход безопасно.",
    ),
    "plugins/aimarket-promo": (
        "aimarket-promo",
        "Time-limited signed discounts fill idle AI capacity — like happy hour for GPU slots. "
        "Providers move spare compute; buyers catch real deals.",
        "Подписанные скидки на время заполняют простаивающую мощность AI — «happy hour» для GPU. "
        "Продавцы загружают простой; покупатели ловят настоящие акции.",
    ),
    "plugins/aimarket-dataset": (
        "aimarket-dataset",
        "Weekly anonymized snapshot of what the marketplace searches and buys — open data for researchers "
        "and builders who want to know demand trends without spying on users.",
        "Еженедельный обезличенный снимок того, что ищут и покупают на маркетплейсе — открытые данные "
        "для исследователей и разработчиков без слежки за пользователями.",
    ),
    "plugins/aimarket-zk": (
        "aimarket-zk",
        "Prove an AI ran correctly on secret input without revealing the input — for M&A, legal, "
        "and regulated workflows where showing the document is not an option.",
        "Доказываете, что AI корректно обработал секретный ввод, не раскрывая его — для M&A, права "
        "и регулируемых процессов, где показать документ нельзя.",
    ),
    "aimarket-hub/plugins/aimarket-provenance": (
        "aimarket-provenance",
        "Every AI answer gets a cryptographic receipt — who, when, what model — verifiable later for "
        "compliance, disputes, and user trust. Like a fiscal receipt for AI output.",
        "Каждый ответ AI получает криптографический чек — кто, когда, какая модель — можно проверить "
        "позже для compliance, споров и доверия. Как фискальный чек для результата AI.",
    ),
    # --- Infra / shared ---
    "aimarket-hub": (
        "AIMarket Hub",
        "One place to find, pay for, and call AI capabilities from many providers — search, wallet, "
        "invoke, settle. The «app store + payment network» for AI functions.",
        "Одно место, чтобы найти, оплатить и вызвать AI-возможности от разных поставщиков — поиск, кошелёк, "
        "вызов, расчёт. «App Store + платёжная сеть» для AI-функций.",
    ),
    "aimarket-protocol": (
        "AIMarket Protocol",
        "Open rules for how AI marketplaces discover, price, pay, and verify calls — so hubs and apps "
        "interoperate like websites use HTTP. Build once, sell anywhere.",
        "Открытые правила: как AI-маркетплейсы ищут, ценообразуют, платят и проверяют вызовы — "
        "чтобы хабы и приложения работали вместе, как сайты на HTTP. Собрал раз — продаёшь везде.",
    ),
    "aimarket-widget": (
        "AIMarket Widget",
        "Drop a search-and-buy box for AI capabilities onto any website — visitors discover and invoke "
        "marketplace skills without leaving your product.",
        "Вставляете на любой сайт блок «найти и купить» AI-возможности — посетители находят и вызывают "
        "навыки маркетплейса, не уходя с вашего продукта.",
    ),
    "aimarket-sdks/dart": (
        "aimarket_agent (Dart SDK)",
        "Flutter and Dart apps connect to the AI marketplace in a few lines — discover, open channel, "
        "invoke, verify. Shared plumbing for all desktop SKUs.",
        "Flutter/Dart-приложения подключаются к AI-маркетплейсу в несколько строк — discover, канал, "
        "invoke, verify. Общая «проводка» для всех desktop-приложений.",
    ),
    "desktop-integrations/packages/aicom_desktop_core": (
        "aicom_desktop_core",
        "Shared themes, wallet bar, languages, and backup for every AICOM desktop app — consistent UX "
        "and one place to fix economics/settings for all eight products.",
        "Общие темы, панель кошелька, языки и бэкап для каждого desktop-приложения AICOM — единый UX "
        "и одно место, где чинить economics/настройки для всех восьми продуктов.",
    ),
    "desktop-integrations/packages/aicom_platform_init": (
        "aicom_platform_init",
        "Bootstraps local SQLite on desktop so finance and audit apps store data on-device reliably — "
        "small helper, big privacy win.",
        "Поднимает локальный SQLite на desktop, чтобы финансовые и audit-приложения надёжно хранили данные "
        "на устройстве — маленький пакет, большой выигрыш в приватности.",
    ),
}


def value_md(title: str, en: str, ru: str) -> str:
    return f"""# {title} — Value in plain words

## English

{en}

## Русский (простыми словами)

{ru}

---

*Regenerate: `python3 scripts/bootstrap_product_value.py`*
"""


def inject_readme(readme: Path, title: str, en: str, ru: str) -> None:
    if not readme.is_file():
        return
    text = readme.read_text(encoding="utf-8")
    block = (
        "## Value in plain words\n\n"
        f"{en}\n\n"
        "Full text: [docs/value.md](docs/value.md)\n\n"
    )
    if "## Value in plain words" in text:
        text = re.sub(
            r"## Value in plain words\n.*?(?=\n## |\n---\n)",
            block.rstrip() + "\n\n",
            text,
            count=1,
            flags=re.DOTALL,
        )
    else:
        anchors = [
            "## Promo video",
            "## Screenshot gallery",
            "## Documentation",
            "## Why ",
            "## What It Does",
            "## What it does",
            "\n---\n",
        ]
        insert_at = None
        for anchor in anchors:
            idx = text.find(anchor)
            if idx > 0:
                insert_at = idx if insert_at is None else min(insert_at, idx)
        if insert_at is None:
            text = text.rstrip() + "\n\n" + block
        else:
            text = text[:insert_at].rstrip() + "\n\n" + block + text[insert_at:].lstrip("\n")
    readme.write_text(text, encoding="utf-8")


def inject_user_guide(guide: Path, en: str, ru: str) -> None:
    if not guide.is_file():
        return
    text = guide.read_text(encoding="utf-8")
    block = f"""## Why it matters (plain words)

{en}

"""
    if "## Why it matters (plain words)" in text:
        text = re.sub(
            r"## Why it matters \(plain words\)\n.*?(?=\n## )",
            block.rstrip() + "\n\n",
            text,
            count=1,
            flags=re.DOTALL,
        )
    elif "## What this product does" in text:
        text = text.replace(
            "## What this product does",
            block.rstrip() + "\n\n## What this product does",
            1,
        )
    elif "## What it does" in text:
        text = text.replace(
            "## What it does",
            block.rstrip() + "\n\n## What it does",
            1,
        )
    else:
        lines = text.split("\n", 2)
        if len(lines) >= 2:
            text = lines[0] + "\n\n" + block + (lines[2] if len(lines) > 2 else "")
    guide.write_text(text, encoding="utf-8")


def main() -> None:
    for rel, (title, en, ru) in VALUES.items():
        root = ROOT / rel
        if not root.is_dir():
            print(f"SKIP missing {rel}")
            continue
        docs = root / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "value.md").write_text(value_md(title, en, ru), encoding="utf-8")
        inject_readme(root / "README.md", title, en, ru)
        inject_user_guide(docs / "user-guide.md", en, ru)
        print(f"OK {rel}")


if __name__ == "__main__":
    main()
