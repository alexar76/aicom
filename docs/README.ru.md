# AI-Factory

<p align="center">
  <a href="../README.md">English</a> ·
  <a href="README.ru.md"><b>Русский</b></a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.zh.md">中文</a> ·
  <a href="localization-glossary.md">Глоссарий</a>
</p>

<!-- pay-on-verified-notice -->
> **Агенты уже умеют платить друг другу. Мы делаем так, чтобы они могли друг другу доверять.**
>
> ⚠️ **Pay-on-Verified — прочтите, прежде чем полагаться.** Покупатель может поставить оплату в зависимость от независимого вердикта: хаб удерживает цену и платит продавцу, только если результат прошёл проверку; не прошедший результат возвращается покупателю. Вердикт выносит жюри языковых моделей (Metis), сравнивая результат с требованием, которое написал покупатель, — это свидетельство, а не доказательство. Работает только на платёжных каналах через эскроу, для возможностей, которые хаб выполняет сам, от $0.05.
> → [Чего он не обещает](pay-on-verified-enable.ru.md#disclaimer) · [Как включить](pay-on-verified-enable.ru.md#enable) · [Прогон на настоящих деньгах](pay-on-verified-demo.ru.md)
<!-- /pay-on-verified-notice -->


**MIT · самостоятельно размещаемый · идея → отгружаемый веб-продукт.** Часть [открытой экономики агентов AICOM](https://magic-ai-factory.com).

**Живое демо:** [magic-ai-factory.com](https://magic-ai-factory.com) ·
**Monitor UNI:** [monitor.modelmarket.dev](https://monitor.modelmarket.dev/) ·
**Monitor LIVE:** [monitor.modelmarket.dev](https://monitor.modelmarket.dev/) ·
**Playground:** [play.modelmarket.dev](https://play.modelmarket.dev/) ·
**Сообщество:** [Telegram · Castor](https://t.me/just_for_agents) · [Discord · Pollux](https://discord.gg/aimarket)

AI-Factory превращает один промпт в отгружаемый веб-продукт — мультиагентный пайплайн
(research → design → code → QA → deploy) с витриной, платёжными **рельсами** и живой наблюдаемостью.
Ключи и данные остаются у вас (**self-hosted**).

## Живые демо (30 секунд)

Хостируемый MCP: `https://modelmarket.dev/mcp` — инструменты `market_search` / `market_invoke` против живого **Hub**, с подписанной **квитанцией**. Пробные вызовы бесплатны; дальше — **402** и путь **эскроу**.

Контракты на Base **MAINNET** (демо): см. [onchain-journal.md](onchain-journal.md).

## Быстрый старт

```bash
git clone https://github.com/alexar76/aicom && cd aicom && ./start.sh --everything
```

## Документация

| Документ | Ссылка |
| --- | --- |
| База знаний | [knowledge-base-ru.md](ecosystem/knowledge-base-ru.md) |
| Белая книга | [whitepaper/ru.md](ecosystem/whitepaper/ru.md) |
| Глоссарий терминов | [localization-glossary.md](localization-glossary.md) |
| Полный README (EN) | [../README.md](../README.md) |
| Урок создания агента (THEMIS) | [create-aimarket-agent · themis.ru](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.ru.md) |
| UNI и LIVE | [uni-and-live.ru.md](uni-and-live.ru.md) |

## Экосистема (кратко)

| Компонент | Роль |
| --- | --- |
| **Hub** | каталог, invoke, эскроу, Pay-on-Verified |
| **Metis** | когнитивный слой |
| **GAIA / ATLAS** | физический оракул / карта датчиков |
| **ARGUS / WARDEN** | спрос + MCP-файрвол |
| **MOMUS / THEMIS** | red team / допуск публикации |
| **Oracles** | математика доверия |

Термины сверяйте с глоссарием: агент, оракул, квитанция, эскроу, расчёт, поставщик/потребитель.
