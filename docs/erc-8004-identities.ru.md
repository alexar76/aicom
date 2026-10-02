# Идентичности ERC-8004: AIMarket Hub, HISTOR и WARDEN

[English](erc-8004-identities.md) · **Русский** · [Español](erc-8004-identities.es.md) · [Français](erc-8004-identities.fr.md) · [中文](erc-8004-identities.zh.md)

С 2026-10-01 три наших сервиса зарегистрированы как агенты в IdentityRegistry
[ERC-8004](https://eips.ethereum.org/EIPS/eip-8004) в основной сети Base. Любой агент, кошелёк
или обозреватель блоков, читающий реестр, найдёт каждый из них, его владельца и файл регистрации,
в котором сказано, что это за сервис и как к нему обратиться.

## Три агента

| Агент | agentId | Что это | Файл регистрации | Обозреватель |
|---|---|---|---|---|
| AIMarket Hub | `96682` | Федеративный рынок capability агентов с оплатой за каждый вызов через MCP, A2A и x402 | [aimarket-hub.json](https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json) | [8004scan](https://8004scan.io/agents/base/96682) |
| HISTOR | `96683` | Журнал прозрачности для MCP-серверов: что объявлял каждый сервер и когда это изменилось | [histor.json](https://modelmarket.dev/.well-known/erc-8004/histor.json) | [8004scan](https://8004scan.io/agents/base/96683) |
| WARDEN | `96684` | Файрвол для MCP: сканирует определения инструментов до того, как хост покажет их модели | [warden.json](https://modelmarket.dev/.well-known/erc-8004/warden.json) | [8004scan](https://8004scan.io/agents/base/96684) |

## Ончейн-запись

- **Реестр:** IdentityRegistry
  [`0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`](https://basescan.org/address/0x8004A169FB4a3325136EB29fA0ceB6D2e539a432)
  в основной сети Base (chain id 8453), `AgentIdentity` версии 2.0.0 — каноническое развёртывание
  ERC-8004, а не наша собственная копия.
- **Владелец всех трёх:** кошелёк оператора
  [`0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`](https://basescan.org/address/0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a).
- **Вызов:** по одному `register(string agentURI)` на агента; agentURI — это URL файла регистрации.

| Агент | Транзакция | Блок |
|---|---|---|
| AIMarket Hub (`96682`) | [`0x207807…284bae`](https://basescan.org/tx/0x207807bbd9dc346e775f8db3cb2aa6b59190fe27e8b4b15d75eb9f5175284bae) | 52046664 |
| HISTOR (`96683`) | [`0xcec3de…f68fd6`](https://basescan.org/tx/0xcec3deb9a343b7257d4d83cbcb80cc3831647d0a907552a7ee14f7dcf7f68fd6) | 52046664 |
| WARDEN (`96684`) | [`0xa784ca…937fda`](https://basescan.org/tx/0xa784cacbea144ed5d9f9ac98e36ae3175f06907c3f8f7f308d5f5c7b37937fda) | 52046664 |

- **Стоимость:** 0.0000031 ETH газа за все три.
- **Проверено после включения в блок:** для каждого agentId `ownerOf` возвращает кошелёк оператора,
  а `tokenURI` — URL файла регистрации.
- **Не сделано:** в ReputationRegistry ничего не записано — это наш выбор, а у ValidationRegistry
  нет канонического развёртывания, в которое можно было бы писать. Обоснование:
  [соответствие ERC-8004](erc-8004-alignment.md).

## Файлы регистрации

Каждый agentURI указывает на JSON-документ `registration-v1` по EIP-8004, который отдаётся из
`https://modelmarket.dev/.well-known/erc-8004/`: имя, описание, изображение, эндпоинты сервиса
(веб-страница, MCP, A2A, A2MCP, x402, DID или npm-пакет — в зависимости от агента) и запись
`registrations`, где указаны agentId и реестр в виде `eip155:8453:0x8004A169…a432`.

`https://modelmarket.dev/.well-known/agent-registration.json` перечисляет все три agentId. Это
подтверждение со стороны домена modelmarket.dev, который отдаёт файлы регистрации и эндпоинты хаба
и A2MCP: этот домен подтверждает, что регистрации — его собственные. Веб-домены HISTOR и WARDEN
подтверждают и свои: `https://histor.modelmarket.dev/.well-known/agent-registration.json`
перечисляет `96683`, а `https://warden.modelmarket.dev/.well-known/agent-registration.json` — `96684`.

Файл можно менять без новой транзакции, потому что ончейн agentURI указывает на URL, а не на
содержимое: отредактируйте `build.py`, сгенерируйте файлы заново, загрузите.

## Хаб объявляет свою идентичность

Хаб на корневом домене указывает свой agentId в собственном подписанном discovery-документе,
[`/.well-known/ai-market.json`](https://modelmarket.dev/.well-known/ai-market.json), в блоке
`erc8004`:

```json
{
  "agent_id": "96682",
  "chain": "eip155:8453",
  "identity_registry": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
  "reputation_registry": "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63",
  "agent_uri": "https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json",
  "verified_by_this_hub": false
}
```

`verified_by_this_hub: false` стоит намеренно. Это заявление хаба о самом себе: читатель сверяет
его с реестром, а не верит хабу на слово. Любой оператор хаба может сделать то же самое через
`AIMARKET_ERC8004_AGENT_ID`, `AIMARKET_ERC8004_CHAIN`, `AIMARKET_ERC8004_NETWORK` и
`AIMARKET_ERC8004_AGENT_URI`, зарегистрировавшись со своего кошелька.

## Проверьте сами

Всё сказанное выше можно проверить, не доверяя нам:

```bash
REG=0x8004A169FB4a3325136EB29fA0ceB6D2e539a432
RPC=https://mainnet.base.org
cast call $REG "ownerOf(uint256)(address)" 96682 --rpc-url $RPC    # 0x1218ff36…Ad0a
cast call $REG "tokenURI(uint256)(string)" 96682 --rpc-url $RPC    # …/erc-8004/aimarket-hub.json
curl -s https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json
curl -s https://modelmarket.dev/.well-known/agent-registration.json
curl -s https://modelmarket.dev/.well-known/ai-market.json | jq .erc8004
```

Для HISTOR или WARDEN подставьте `96683` или `96684` в строки `cast` и `histor.json` или
`warden.json` в первый `curl`; блок `erc8004` есть только в документе хаба.

## Источники

- [`deploy/erc-8004/`](../deploy/erc-8004/): `build.py` генерирует файлы регистрации,
  `register.py` регистрирует их (без `--send` — только пробный прогон; отказывается работать, если
  кошелёк не покрывает стоимость в худшем случае с учётом комиссии Base за данные L1, пропускает
  агентов, уже записанных в `ids.json`, и подписывает внутри процесса, так что ключ никогда не
  попадает в командную строку), `ids.json`, `registrations.log`.
- Запись в [ончейн-журнале](onchain-journal.md) от 2026-10-01.
- [Соответствие ERC-8004](erc-8004-alignment.md): как идентичности, квитанции и репутация этого
  протокола ложатся на ERC-8004 и что он намеренно оставляет за рамками.
