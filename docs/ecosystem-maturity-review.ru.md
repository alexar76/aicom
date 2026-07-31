# Обзор зрелости экосистемы — внешняя критика и план действий

**Дата:** 2026-07-12  
**Цель:** Честно проверить сторонний scorecard и зафиксировать **конкретные действия** (in-repo сейчас vs блокеры оператора/вендора).

**См. также:** [known-issues.md](known-issues.md) · [pet-project-trust.md](pet-project-trust.md) · [oracles crypto-maturity](../oracles/docs/crypto-maturity.ru.md)

---

## Критика справедлива?

| Компонент | Оценка | Вердикт | Почему |
|-----------|--------|---------|--------|
| **1. AI-Factory** | 7.8/10 | **В целом да** | За ~2 месяца — большой объём; технический долг, KI-3/KI-2/KI-4 и MVP-лендинги — честно. |
| **2. Metis** | 8.0/10 | **Да** | Сильный дизайн; distributed и adversarial-покрытие сырые. |
| **3. Oracles ×17** | 6.5–6.7/10 | **Да** | Ширина > глубина; crypto не hardened ([KI-6](known-issues.md#ki-6--oracle-family-cryptographic-maturity-not-production-hardened)). |
| **4. ARGUS-3** | 7.5/10 | **Да** | WARDEN реален; против sophisticated attacks (obfuscation, runtime, model bypass) — нет. |
| **5. Hub + Protocol** | 7.2/10 | **Да** | v2 — хороший фундамент; federation/adoption ≈ 0, edge-кейсы не обкатаны. |
| **6. Alien Monitor** | 8.0/10 | **Да** | Одна из самых polished частей; не финансовый trust layer. |
| **7. Supporting** | 6.8–7.3/10 | **Да** | Вторичные инструменты; DIOSCURI — devrel + reference demo. |

**Итог:** критика **в целом верна**. Оценки субъективны, но **риски** совпадают с KI-* и pet-project trust — это не FUD, а наш же pre-mainnet posture.

---

## Матрица действий

| ID | Компонент | Действие | Ответственный | Статус |
|----|-----------|----------|---------------|--------|
| **A-1** | Factory | Профили pipeline: minimal vs full | in-repo | [`factory-pipeline-profiles.md`](factory-pipeline-profiles.md) |
| **A-2** | Factory | MVP-tier для sample output | in-repo | [`sample-output/README.md`](sample-output/README.md) |
| **A-3** | Factory | **KI-7** — production readiness | in-repo | known-issues |
| **A-4** | Metis | MATURITY.md | in-repo | [`metis/docs/en/MATURITY.md`](../metis/docs/en/MATURITY.md) |
| **A-5** | Metis | Adversarial gate tests | in-repo | `metis/tests/test_adversarial_gates.py` |
| **A-6** | Metis | **KI-8** — cluster soak / red-team | in-repo | known-issues |
| **A-7** | Oracles | Crypto honesty | in-repo | **KI-6** ✅ |
| **A-8** | ARGUS | §Limitations в security-warden | in-repo | argus docs |
| **A-9** | ARGUS | Adversarial WARDEN fixture | in-repo | `argus/test/adversarial-warden.test.ts` |
| **A-10** | ARGUS | **KI-9** | in-repo | known-issues |
| **A-11** | Hub | MATURITY.md + **KI-10** | in-repo | aimarket-hub docs |
| **A-12** | Monitor | Tier «observability» | — | pet-project-trust |
| **A-13** | Supporting | Tier secondary/devrel | in-repo | pet-project-trust |
| **A-14** | All | ROADMAP + README links | in-repo | ROADMAP.md |

**Только оператор (нельзя закрыть одними документами):** аудит KI-2, нагрузочный тест KI-3, multisig KI-4, крипто-аудит KI-6, продакшн-внедрение на сторонних хабах.

---

## По компонентам (кратко)

### 1. AI-Factory — критика верна

Самый тяжёлый компонент; conditional agents/gates дают operational surface; Docker self-host — плюс; load/multisig/audit открыты; shipped продукты — в основном MVP-лендинги. **«Over-engineered» для pet project** — согласны: полный pipeline избыточен для одной landing page → см. minimal profile (A-1).

### 2. Metis — критика верна

Distributed есть, но 2 месяца — мало для надёжного кластера. Confidence gate fail-closed по **структурным** сигналам, но доверяет `confidence` от council — subtle hallucination с высоким score может пройти. Metering носит рекомендательный характер, пока Factory принудительно не списывает средства.

### 3. Oracles — критика верна

Закрыто в [crypto-maturity](../oracles/docs/crypto-maturity.ru.md) + KI-6. Platon/Lumen — тот же класс «нужен внешний аудит».

### 4. ARGUS — критика верна

WARDEN ловит типовое отравление; сложные атаки, разрешительные настройки по умолчанию, деградация LUMEN к нейтральному — задокументированные пробелы (A-8–A-10).

### 5. Hub — критика верна

Protocol v2 ок; реальное adoption ≈ 0 → federation/micropay edge cases в основном на бумаге (KI-10).

### 6. Monitor — критика мягкая, согласны

### 7. Supporting — критика верна

Вторичный tier; DIOSCURI ≠ production agent platform.

---

## Публичная формулировка

> *Самостоятельно размещаемая экономика AI-агентов — уровень исследования/прототипа. Сильные демо и protocol wiring; для mainnet-scale TVL нужны внешний аудит, load testing и crypto review.*

> 🌐 Языки: [English](ecosystem-maturity-review.en.md) · **Русский** · [Français](ecosystem-maturity-review.fr.md) · [Español](ecosystem-maturity-review.es.md) · [中文](ecosystem-maturity-review.zh.md)
