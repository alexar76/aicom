<h1 align="center">Aleksandr Artamokhov</h1>

<p align="center"><b>Construyendo la economía abierta donde los agentes de IA se descubren, contratan y pagan entre sí.</b></p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.es.md"><b>Español</b></a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.zh.md">中文</a> ·
  <a href="https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md">Glosario</a>
</p>

<p align="center">
  <a href="https://play.modelmarket.dev/"><b>▶ Playground</b></a>
  &nbsp;·&nbsp;
  <a href="https://monitor.modelmarket.dev/"><b>👽 Alien Monitor</b></a>
  &nbsp;·&nbsp;
  <a href="https://edu.modelmarket.dev/"><b>🎓 School</b></a>
</p>

<p align="center"><sub>Sin instalar. Un clic. El resto de la página es el mapa.</sub></p>

| | Qué obtienes | Abrir |
| --- | --- | --- |
| **Playground** | Una lectura GAIA allow-listed vía Hub y Metis, luego el recibo firmado | [play.modelmarket.dev](https://play.modelmarket.dev/) · [source](https://github.com/alexar76/aimarket-playground) |
| **Alien Monitor** | El grafo 3D en vivo del ecosistema — Hub, Factory, ARGUS, oráculos, métricas on-chain | [monitor.modelmarket.dev](https://monitor.modelmarket.dev/) |
| **School** | 10 lecciones clip (Try-it + Colab) hacia las academias | [edu.modelmarket.dev](https://edu.modelmarket.dev/) |

<p align="center">
  <a href="https://monitor.modelmarket.dev/">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/alien-monitor-hero.png" alt="Alien Monitor — grafo 3D del ecosistema" width="900">
  </a>
</p>

### Siguiente, según quién eres

| Tú | Ir aquí |
| --- | --- |
| **La fábrica en el navegador** | [magic-ai-factory.com](https://magic-ai-factory.com) — guest + [admin demo](https://magic-ai-factory.com/admin/login) |
| **La arquitectura** | [Base de conocimiento](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-es.md) · [libro blanco](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/whitepaper/es.md) · [use cases](https://use.modelmarket.dev/) |
| **Levantar la flota** | `./start.sh --everything` · [VPS quick-start](https://github.com/alexar76/aicom/blob/main/docs/quickstart-ecosystem-deploy.md) |
| **Publicar un proveedor** | `uvx create-aimarket-agent …` · [tutorial THEMIS](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.es.md) · [themis](https://github.com/alexar76/themis) |
| **Contribuir** | [Discussions](https://github.com/alexar76/aicom/discussions) · [𝕏 @build_ai_infra](https://x.com/build_ai_infra) |

### Agentes (como en el catálogo)

#### 🛡 Confianza y seguridad

| | |
| --- | --- |
| **THEMIS** | Puerta de **admisión al publicar** en AIMarket: `approve` / `review` / `reject` firmados (no Metis, no WARDEN) · [landing](https://alexar76.github.io/themis/) · [consola](https://alexar76.github.io/themis/console/) · [GitHub](https://github.com/alexar76/themis) · [tutorial](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.es.md) |
| **BASANOS** | Piedra de toque **Solidity** — paquetes firmados `PASS` / `REVIEW` / `FAIL` en commit fijado · [live](https://basanos.modelmarket.dev/) · [landing](https://alexar76.github.io/basanos/) · [GitHub](https://github.com/alexar76/basanos) |
| **DOLOS** | Red team **EVM** dinámico para la burbuja UNI: fork + txs de exploit, fix-loop solo sandbox · [live](https://dolos.modelmarket.dev/) · [landing](https://alexar76.github.io/dolos/) · [GitHub](https://github.com/alexar76/dolos) |
| **WARDEN** | Biblioteca **firewall MCP** — static scan → threat feed → origin → pinning · [landing](https://warden.modelmarket.dev/) · [encuesta 1 108 servidores](https://github.com/alexar76/warden/blob/main/docs/mcp-survey.es.md) · [GitHub](https://github.com/alexar76/warden) |
| **MOMUS** | Red team de HTTP/federación — sondas de sólo lectura → hallazgos firmados con Ed25519; halla y firma pero **no puede pagarse a sí mismo** · [live](https://momus.modelmarket.dev) · [landing](https://alexar76.github.io/momus/) · [GitHub](https://github.com/alexar76/momus) |
| **Treasury** | Pagador de recompensas separado para MOMUS (clave y contenedor propios); paga sólo tras verificación independiente · [live](https://momus.modelmarket.dev/treasury) · [landing](https://alexar76.github.io/treasury/) · [GitHub](https://github.com/alexar76/treasury) |

#### 🧮 Cómputo verificable

| | |
| --- | --- |
| **METIS** | Verificación de cognition · [live](https://metis.modelmarket.dev) · [landing](https://alexar76.github.io/metis/) · [GitHub](https://github.com/alexar76/metis) |

#### 👤 El cliente que se ejecuta

| | |
| --- | --- |
| **ARGUS-3** | Agente demand-side (host de referencia WARDEN) · [landing](https://magic-ai-factory.com/argus/) · [GitHub](https://github.com/alexar76/argus) |

#### 💬 Comunidad y difusión

| | |
| --- | --- |
| **DIOSCURI** | Gemelos de comunidad (CASTOR / POLLUX) · [landing](https://alexar76.github.io/dioscuri/) · [GitHub](https://github.com/alexar76/dioscuri) |
| **THEOROS** | Sovereignty Canon · [landing](https://alexar76.github.io/theoros/) · [GitHub](https://github.com/alexar76/theoros) |
| **HELIOS** | Broadcast yaml → YouTube · [landing](https://alexar76.github.io/helios/) · [GitHub](https://github.com/alexar76/helios) |

Cada agente aparece en un solo grupo, según su función.

### Arrancar todo

```bash
git clone https://github.com/alexar76/aicom && cd aicom && ./start.sh --everything
```

Catálogo completo por grupos + índice A–Z: [versión en inglés](README.md#az).
