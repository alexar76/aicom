# Attested Memory documentation

Attested Memory is a PostgreSQL-backed SaaS family for durable, verifiable
knowledge. The public edge exposes Personal Memory, Team Memory OS and Expert
Memory Market through one origin. Memory Market is the system of record for
Memory Units; Truth Layer and Provenance Ledger attach verification and lineage.

## Choose a language

- [English](i18n/en/README.md)
- [Русский](i18n/ru/README.md)
- [Español](i18n/es/README.md)
- [Português (Brasil)](i18n/pt-BR/README.md)
- [Deutsch](i18n/de/README.md)
- [Français](i18n/fr/README.md)
- [日本語](i18n/ja/README.md)
- [한국어](i18n/ko/README.md)
- [简体中文](i18n/zh-CN/README.md)
- [Türkçe](i18n/tr/README.md)

Every locale contains the same overview, user guide, trial guide, use cases and
glossary. Screenshots are kept beside the locale so translated UI terminology
can be reviewed visually.

For the terminology audit, completeness matrix and external standards used for
definitions, see [`TERM_AUDIT.md`](TERM_AUDIT.md) and the shared
[`GLOSSARY.md`](i18n/GLOSSARY.md). Each locale also contains a short localized
glossary.

## Canonical product map

| Route | Product | Purpose |
|---|---|---|
| `/memory` | Personal Attested Memory | private personal and agent context |
| `/teams` | Team Memory OS | permissioned shared company knowledge |
| `/market` | Expert Memory Market | discover and unlock paid expert memory |
| `/billing` | SaaS Gateway | exact USDC invoice and key issuance |
| `/developers` | Developer Portal | API, actor identity and operations |

## Production essentials

- PostgreSQL is mandatory in production for Hub and SaaS Gateway.
- USDC settlement is non-custodial: KOVA verifies an exact Base invoice.
- Raw SaaS keys are displayed once; only hashes and prefixes are persisted.
- Team access uses PostgreSQL membership plus five-minute HMAC assertions.
- Actor signatures are verified by Memory Market on every protected request.

See the repository deployment runbooks in
[`attested-saas-gateway/docs/`](../attested-saas-gateway/docs/) and
[`SAAS_PROJECTS.md`](../SAAS_PROJECTS.md).

The same index is published at `/docs` by the SaaS edge.
