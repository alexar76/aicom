# Имена discovery — два написания одного документа

> **English:** [discovery-names.md](./discovery-names.md) · **Español:** [discovery-names.es.md](./discovery-names.es.md) · **Français:** [discovery-names.fr.md](./discovery-names.fr.md) · **中文:** [discovery-names.zh.md](./discovery-names.zh.md)
>
> Код: [`discovery_names.py`](../aimarket_hub/discovery_names.py) · [`hub_routes/wellknown.py`](../aimarket_hub/hub_routes/wellknown.py) · [`crawler.py`](../aimarket_hub/crawler.py) · Драфты: [`aimarket-protocol/ietf/`](https://github.com/alexar76/aimarket-protocol/tree/main/ietf)

С 30.10.2026 хаб отдаёт discovery-документ под двумя именами, шлёт заголовок краулера под
двумя именами и принимает любое из них. Ничего не переименовано и ничего не отключено: все
пиры сети по-прежнему читают старые имена, а новые — предложение на рассмотрении.

## Зачем

Два Internet-Draft в `aimarket-protocol/ietf/` описывают discovery и федерацию этого хаба для
рабочей группы IETF DAWN. Документ, предлагаемый как стандарт, не может нести бренд одного
продукта в well-known URI, а префикс `X-` у заголовков устарел (RFC 6648). Поэтому драфты
используют `/.well-known/agent-marketplace` и `Agent-Marketplace-Crawler`, и хаб, который
заявляет их реализацию, обязан отдавать эти имена — не ломая ни одного существующего пира.

## Что делает хаб

| | Старое (контракт на проводе) | Драфт (предложение) |
|---|---|---|
| Discovery-документ | `GET`/`HEAD /.well-known/ai-market.json` | `GET`/`HEAD /.well-known/agent-marketplace` |
| Адрес каталога | `manifest_url` | `catalogue_url` (тот же URL) |
| Профиль подписи | подразумевается | `signature_profile: "ed25519-pipe-2"` |
| Допущенные пиры | `peers`: объекты с `url`, `name`, `trust_score`, … | `peers`: URI discovery-документов |
| Краулер называет себя | `X-AIMarket-Crawler: <url хаба>` | `Agent-Marketplace-Crawler: <url хаба>` |

- **Отдача.** Документ драфта собирается из старого, поэтому ключ, каталог и счётчики не могут
  разойтись. В нём также есть `manifest_url` и `legacy_discovery_url` для читателя, который
  знает только старые имена. `peers` перечисляет discovery-URI, которые этот хаб реально читает
  у допущенных пиров: старый путь у пира, который отдаёт только его, путь драфта — когда пир его
  объявил. Пир в состоянии pending не попадает ни в один из документов.
- **Отправка.** Краулер шлёт оба заголовка с одним значением при каждом запросе.
- **Приём.** Оба маршрута читают оба заголовка. Если пришли оба, побеждает старое значение —
  именно по нему пиры всегда и опознавались. Остальное без изменений: запись вне пути запроса,
  синтаксическая проверка, SSRF-проверка до любого запроса, допуск как *pending* при открытой
  федерации и никакого доверия по одному заголовку.
- **Чтение.** Пир, публикующий форму драфта (`catalogue_url`, `peers` как URI), приводится к
  старой форме до валидации, обхода и assay, поэтому индексируется как любой другой. Пир,
  указанный URI с путём драфта, вызывается по этому пути, а не по старому, которого он может
  не отдавать.

Подписанный каталог байт-в-байт одинаков под обоими именами: каноническая строка сохраняет имя
пары `tools_hash`, так что подпись, верная для одного читателя, верна и для другого.

## Проверка хаба

```bash
curl -s https://modelmarket.dev/.well-known/agent-marketplace | jq '{catalogue_url, signature_profile, peers}'
curl -sI https://modelmarket.dev/.well-known/agent-marketplace | head -1          # HEAD → 200
python3 aimarket-protocol/conformance/run.py --hub https://modelmarket.dev          # проверки драфта включены
```

Конформанс-раннер записывает проверки драфта, когда путь отвечает, и **пропускает** их у хаба,
который отдаёт только старое имя. Драфты — предложение; старый путь — контракт.
