# Localization policy

The release documentation supports ten locales:

| Code | Language | Initial audience |
|---|---|---|
| `en` | English | canonical technical source |
| `ru` | Русский | core team and CIS operators |
| `es` | Español | Spanish-speaking SaaS and AI users |
| `pt-BR` | Português do Brasil | Brazilian fintech and crypto users |
| `de` | Deutsch | European B2B and engineering teams |
| `fr` | Français | European and African tech teams |
| `ja` | 日本語 | Japanese product and developer teams |
| `ko` | 한국어 | Korean AI and crypto builders |
| `zh-CN` | 简体中文 | Chinese-speaking developers |
| `tr` | Türkçe | Turkish startup and crypto users |

English is the source of truth for API behavior. Translations may adapt tone
and examples, but must preserve route names, JSON fields, environment variables,
cryptographic algorithm names and payment warnings. Security, custody and legal
language require human review before publication.

The translation order for updates is: security and payment docs first, then
user guides, then marketing copy. A locale falls back to English when a new
paragraph has not yet been reviewed.
