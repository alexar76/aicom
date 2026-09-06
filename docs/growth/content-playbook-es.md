# Content playbook — landings, READMEs y docs

> 🌐 Idiomas: [English](./content-playbook.md) · [Русский](./content-playbook-ru.md) · **Español** · [Français](./content-playbook-fr.md) · [中文](./content-playbook-zh.md)

Playbook para los agentes y los humanos que tocan los repos del ecosistema AICOM. **El texto público es solo en inglés.** El ruso va en un compañero RU explícito (por ej. `README-ru.md` en DIOSCURI) — no mezclado en el README o la landing principal.

**Ver también:** [THEOXENIA content plan](https://github.com/alexar76/dioscuri/blob/main/docs/content-plan.md) · [seeding playbook](./seeding-playbook.md) · [knowledge base](../ecosystem/knowledge-base.md)

---

## 1. Enlaces canónicos (un solo juego en todas partes)

Cada repo debe usar las mismas URL. DIOSCURI las lee desde `dioscuri.config.json` → `links`; la moderación elimina las invitaciones Discord/Telegram no canónicas.

| Qué | URL de producción | Rol |
|-----|-------------------|-----|
| Telegram bot (Castor) | https://t.me/next_agent_market_bot | Q&A — pregunta al gemelo |
| Telegram channel (Castor) | https://t.me/just_for_agents | News, releases, digests |
| Discord (Pollux) | https://discord.gg/aimarket | Discusiones, ayuda, show-and-tell |
| Ecosistema | https://magic-ai-factory.com | Sitio principal |
| Espejo / dev | https://modeldev.modelmarket.dev | Demos, staging |
| Observatory | https://monitor.modelmarket.dev/ | Estado live del stack |
| GitHub org | https://github.com/alexar76 | Código |
| DIOSCURI | https://github.com/alexar76/dioscuri | Gemelos, setup |
| THEOROS canon | https://alexar76.github.io/theoros/ | Agent Sovereignty Canon · `#the-canon` en Discord |
| THEOROS repo | https://github.com/alexar76/theoros | CANON.md, capítulos, landing de granito |

**Regla:** No inventes tus propias invitaciones Discord/Telegram. Si hace falta un segundo canal, acuérdalo primero y añádelo a los `links` de DIOSCURI.

---

## 2. Dos puertas — dos audiencias

No uses un CTA genérico único «join community». Dos caminos distintos:

| Audiencia | CTA | Copy (EN) |
|-----------|-----|-----------|
| Observador | Telegram | “Release news and digests — Castor on Telegram” → https://t.me/just_for_agents |
| Desarrollador | Discord | “Discuss, ask, show what you built — Pollux on Discord” → https://discord.gg/aimarket |

Cada README y landing incluye **ambos** enlaces. El orden depende del tipo de repo:

| Tipo de repo | Enlace community principal |
|--------------|----------------------------|
| SDK / client / widget | **Discord primero** (desarrolladores) |
| Demo / monitor / landing | **Telegram primero** (escaparate) |

---

## 3. Landing — bloques requeridos

Esqueleto mínimo (ver [DIOSCURI `landing/index.html`](https://github.com/alexar76/dioscuri/blob/main/landing/index.html)):

### Hero

- **Eyebrow:** Community · AICOM · MIT (o el rol del proyecto)
- **H1:** nombre del producto — sin hype crypto
- **Subtitle:** una frase — qué hace, no lo geniales que sois
- **3 CTA:** Demo · GitHub · Community (Telegram + Discord)

### Qué es (2–3 párrafos)

Problema → solución → lugar en el ecosistema (Factory / Oracles / AIMarket / ARGUS). Un enlace a [Alien Monitor](https://monitor.modelmarket.dev/) como prueba de vida.

### Features (3–6 tarjetas)

Hechos, no niebla de marketing: ports, protocolos, lo que funciona de verdad hoy. Enlace a una demo live cuando exista.

### Community block (requerido)

> Questions? The DIOSCURI twins answer from synced GitHub docs.
>
> • Telegram (Castor) — fast news: https://t.me/just_for_agents
> • Discord (Pollux) — deep threads: https://discord.gg/aimarket

### Footer

Repository · Setup/Docs · Alien Monitor · AICOM ecosystem · (opcional) README ruso

### Meta / SEO

- `description` — ≤160 caracteres, hechos concretos
- `og:title`, `og:description` — mismos hechos, mismo tono
- `lang="en"` en las páginas públicas

---

## 4. README — secciones requeridas

### Top (after badges)

```markdown
Part of the [AICOM open agent economy](https://magic-ai-factory.com).
**Live demo:** <url> · **Community:** [Telegram](https://t.me/just_for_agents) · [Discord](https://discord.gg/aimarket)
```

### What it does

3–5 viñetas. Cada viñeta es un hecho verificable («syncs READMEs every 60 min»), no «revolutionary AI».

### Quick start

Comandos copy-paste. Si hay una URL de demo, ponla en su propia línea justo después de la instalación.

### Demo URLs (crítico para MNEMOSYNE)

DIOSCURI parsea el README y extrae los enlaces de demo hacia las guías y las capturas. Formato:

```markdown
## Demo
- **Live:** https://modeldev.modelmarket.dev/your-demo/
- **Docs:** https://github.com/alexar76/your-repo/blob/main/docs/setup.md
```

Si no hay demo, escribe **No public demo yet** — no omitas la sección.

### Related repos

Tabla de 3 a 8 repos vecinos del ecosistema con enlaces. Ayuda a los gemelos a responder «¿qué hay al lado de esto?».

### Community (al final)

Mismo bloque que en la landing. Añadido opcional:

> Release announcements are syndicated by [KERYX](https://github.com/alexar76/dioscuri#keryx-syndication-post-only) (post-only, no spam automation).

---

## 5. Docs (`docs/`) — reglas

| Tipo | Archivo | Contenido |
|------|---------|-----------|
| Setup | `docs/setup.md` | Variables de entorno, ports, primer arranque |
| Usage | `docs/usage.md` | Cómo usarlo — no cómo hacerle marketing |
| Architecture | `docs/architecture.md` | Diagramas, fronteras de módulos |
| Security | `docs/security.md` | Amenazas y lo que el código hace de verdad |

En cada `setup.md`:

- Enlace community en una sección **Support / Community**
- Enlace a Alien Monitor si el servicio aparece allí
- Sin secretos en los ejemplos (`REPLACE_ME`, no tokens reales)

**Cross-links:** Rutas relativas dentro de la org; URL completas desde fuera.

---

## 6. Tono y estilo (THEOXENIA charter)

Alinearse con [`docs/content-plan.md`](https://github.com/alexar76/dioscuri/blob/main/docs/content-plan.md):

- **English only** en los posts públicos, landings, guías Discord
- Dry, technical, myth-flavored — **un solo Olympus touch por post**, no más
- Twins tease each other, never users
- **No hype:** nada de revolutionary, game-changer, to the moon, price talk, airdrops
- **No emoji walls** — el emoji como señal (🔨 digest, ⚒ release), no decoración
- **Silence beats filler** — semana vacía → sin digest, no un digest fabricado

Frases corporate prohibidas — ver `styleCharter()` en [`dioscuri/src/personas/index.ts`](https://github.com/alexar76/dioscuri/blob/main/src/personas/index.ts). Si los gemelos van a citar tu texto, no uses esas frases.

---

## 7. Lo que ayuda a MNEMOSYNE (y a los gemelos)

README y docs son comida para bots. Escribe para que el retrieval devuelva una respuesta útil:

- **H1** claro = nombre del proyecto
- Primer párrafo = una frase: «X is Y that does Z»
- Sección **Demo** con una URL que funciona (no localhost)
- Sección **Related** — vecinos del ecosistema
- Release notes: la primera frase termina en punto (KERYX lo usa para Mastodon/Bluesky)
- Sin bromas de prompt-injection en el README («ignore previous instructions») — AEGIS descarta el chunk

---

## 8. KERYX / releases — release notes

Cuando etiquetas una release, KERYX postea automáticamente:

```
⚒ your-repo v1.2.3 shipped — Short plain title here
https://github.com/alexar76/your-repo/releases/tag/v1.2.3
Community: discord.gg/aimarket | t.me/just_for_agents
```

Para los autores:

- Primera línea de las release notes — plain English title, ≤120 caracteres, punto al final si es posible
- Sin muros de markdown al principio (`##`, `**`, viñetas) — el anti-spam de Mastodon caza el junk
- Mastodon: calienta la cuenta manualmente antes de la API; detalles en [`docs/use-cases.md`](https://github.com/alexar76/dioscuri/blob/main/docs/use-cases.md) §9

---

## 9. Líneas rojas — no escribir

- Invitaciones `discord.gg/…` o `t.me/…` custom (moderación = delete)
- «Join for airdrop / whitelist / pump»
- Tráfico pagado, join4join, auto-bump DISBOARD
- Secretos en el README, los docs o las landings
- «AI does everything» sin enlace de demo
- Posts de setup duplicados en cada despliegue (la idempotencia es el trabajo de DIOSCURI, no de tu README)

---

## 10. Checklist antes del merge

- [ ] Hero: qué hace + demo + GitHub + community (TG + Discord)
- [ ] URL de demo en el README (que funciona, no 502)
- [ ] Related repos — 3+ vecinos
- [ ] Texto público en inglés
- [ ] Enlaces community canónicos (no invitaciones custom)
- [ ] Release notes: primera línea plain y corta
- [ ] Sin secretos, sin hype, sin bromas de injection en los docs
- [ ] Enlace a Alien Monitor si el proyecto vive allí

---

## 11. Copy-paste — README community block

```markdown
## Community

The [DIOSCURI](https://github.com/alexar76/dioscuri) twins answer questions from synced GitHub docs.

| Channel | Twin | Best for |
|---------|------|----------|
| [Telegram](https://t.me/just_for_agents) | Castor | Releases, digests, quick news |
| [Discord](https://discord.gg/aimarket) | Pollux | Help, ideas, show-and-tell |

**Ecosystem map:** [Alien Monitor](https://monitor.modelmarket.dev/) · [AICOM](https://magic-ai-factory.com)
```

---

## 12. Copy-paste — landing CTA row

```html
<a href="https://t.me/just_for_agents">Telegram · Castor</a>
<a href="https://discord.gg/aimarket">Discord · Pollux</a>
<a href="https://github.com/alexar76/YOUR_REPO">GitHub</a>
<a href="YOUR_DEMO_URL">Live demo</a>
```

---

## 13. Copy-paste — botones «Ask the twins»

CTA principales en las landings y las hero rows — enlaces a canales live, no anclas `#` ni setup docs:

```html
<a href="https://t.me/next_agent_market_bot">Ask Castor · Telegram</a>
<a href="https://discord.gg/aimarket">Ask Pollux · Discord</a>
```

En los repos **demo / monitor / landing**, lista Telegram primero. En los repos **SDK / client / widget**, lista Discord primero.

Enlace secundario opcional para los operadores que autoalojan los gemelos: `Deploy your twins` → `docs/setup.md`.

---

## 14. Difusión YouTube (HELIOS)

El upload de vídeo ya **no** es un `upload_youtube.py` manual — usa [HELIOS](https://github.com/alexar76/helios/blob/main/README.md):

| Paso | Comando |
|------|---------|
| Backfill por lotes | `helios backfill-enqueue -n 10` luego `helios worker` |
| Approve | Revisar el privado en Studio → `helios approve JOB_ID` |
| Short para una nueva release | `helios enqueue --template release-short --repo REPO --tag TAG` |
| Explorador editorial | Automático en `helios worker` (cron) — o `helios calliope run-editorial` |

### Growth cadence (channel @My-AI-Factory)

| Fase | Uploads | Ritmo público | Mix |
|------|---------|---------------|-----|
| **Backfill ahora** | hasta 9/día en privado | approve por lotes | backlog PromoMaterials E10+ |
| **Régimen estable** | 1 script CALLIOPE por run de explorador | **2–4 públicos/semana** | explainers evergreen + deep-dives de repos |
| **Releases** | DIOSCURI `release-short` en tag | bonus | publicar las news cuando el ecosistema etiqueta |
| **Human gate** | siempre privado primero | nunca auto-público | Studio + `helios approve` |

Config editorial (`helios.config.yaml` → `calliope`):

- `scout_interval_days: 3` — ~2 runs de explorador/semana, ideas registradas en `data/editorial/scout_log.jsonl`
- `weekly_enqueue_quota: 3` — la calidad antes que el volumen
- `backfill_pause_threshold: 8` — no competir con los uploads del backlog

**Charter:** private-first, VO template-only para el backfill, scripts fundados en MNEMOSYNE para el contenido nuevo, sin automatización de engagement. El nodo Monitor muestra las stats de YouTube en caché.

---

## Summary

Landings y READMEs no son anuncios — son **mapas de entrada**: demo → code → dos canales community → ecosistema en Monitor. Una sola voz, un solo juego de enlaces, hechos venidos del repo. Los gemelos y KERYX se encargan del resto si les dejas un README correcto.
