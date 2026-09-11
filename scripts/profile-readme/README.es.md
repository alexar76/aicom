<h1 align="center">Aleksandr Artamokhov</h1>

<p align="center"><b>Construyendo la economía abierta donde los agentes de IA se descubren, se contratan y se pagan entre sí.</b></p>

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

<p align="center"><sub>Sin instalación. Un clic. El resto de esta página es el mapa.</sub></p>

| | Lo que obtienes | Abrir |
| --- | --- | --- |
| **Playground** | Envía una lectura GAIA incluida en la allowlist a través de Hub y Metis; después inspecciona el recibo firmado | [play.modelmarket.dev](https://play.modelmarket.dev/) · [código fuente](https://github.com/alexar76/aimarket-playground) |
| **Alien Monitor** | El grafo 3D en vivo de todo el ecosistema: Hub, Factory, ARGUS, oráculos y métricas on-chain | [monitor.modelmarket.dev](https://monitor.modelmarket.dev/) |
| **School** | 13 lecciones en clips (Try-it + Colab) que sirven de entrada a las academias | [edu.modelmarket.dev](https://edu.modelmarket.dev/) |

<p align="center">
  <a href="https://monitor.modelmarket.dev/">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/alien-monitor-hero.png" alt="Alien Monitor — grafo 3D del ecosistema: Hub, Mesh, ARGUS, Capability NFT, flujo de actividad y métricas on-chain en una sola vista cósmica en vivo" width="900">
  </a>
</p>

<p align="center">
  <sub>Grafo 3D ampliable del ecosistema — <a href="https://monitor.modelmarket.dev/">Alien Monitor</a></sub>
</p>

<p align="center">
  <a href="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/ecosystem-overview.svg">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/ecosystem-overview.svg" alt="Vista general del ecosistema: Factory, Oracles y METIS alimentan Hub; ARGUS consume; ACEX financia; SKOPOS observa; MOMUS encuentra; Treasury paga; LOGOS analiza la federación" width="900">
  </a>
</p>

<p align="center">
  <sub>Columna vertebral del dinero y la confianza — haz clic en el diagrama para verlo a tamaño completo.</sub>
</p>

<p align="center">
  <a href="https://oracles.modelmarket.dev">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/oracles-hero.gif" alt="Oracles — diecisiete capacidades matemáticas verificables para la economía de agentes: Platon randomness, Chronos VDF, Lattice, Murmuration, Lumen, Colony, Turing, Percola, Fermat, Ablation, Landauer, Sortes, Gauss, Aestus, Betti, Kantor, Fourier; cada una con visuales cósmicos 3D en vivo" width="900">
  </a>
</p>

<p align="center">
  <sub><b>Oracles</b> — agentes pagan por matemáticas firmadas de aleatoriedad, demora, consenso y confianza · <a href="https://oracles.modelmarket.dev"><b>portal en vivo</b></a> · <a href="https://github.com/alexar76/oracles">GitHub</a></sub>
</p>

---

### A continuación, si sabes quién eres

| Tú | Ve aquí |
| --- | --- |
| **Quieres la fábrica en un navegador** | [magic-ai-factory.com](https://magic-ai-factory.com) — prueba como invitado + [demo de administración](https://magic-ai-factory.com/admin/login) (sin contraseña: `admin`, después **Enter admin demo**) |
| **Quieres la arquitectura** | [Base de conocimiento del ecosistema](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-es.md) · [whitepaper](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/whitepaper/es.md) · [casos de uso](https://use.modelmarket.dev/) |
| **Quieres operar la flota** | `./start.sh --everything` más abajo, o [inicio rápido en VPS](https://github.com/alexar76/aicom/blob/main/docs/quickstart-ecosystem-deploy.es.md) |
| **Quieres publicar un proveedor** | `uvx create-aimarket-agent my-agent --kind data-provider --metis` · [tutorial completo del agente de seguridad](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.es.md) · [agente terminado](https://github.com/alexar76/themis) |
| **Quieres contribuir** | [Discussions](https://github.com/alexar76/aicom/discussions) · [good first issues](https://github.com/alexar76/aicom/labels/good%20first%20issue) · [𝕏 @build_ai_infra](https://x.com/build_ai_infra) |

El catálogo de repos está **más abajo**, agrupado por la función de cada repo: Factory, núcleo AIMarket, Construir y conectar, gateways MCP, Cómputo verificable, Mundo físico, Confianza y seguridad, el cliente que ejecutas, ACEX, Observabilidad, Comunidad y difusión, Aprender y explorar. Cada repo aparece exactamente en un grupo, con su landing en vivo en esa fila, y el [índice A–Z](#az) permite encontrarlo desde cualquier otro ángulo: aquí no hay un segundo mapa del sitio.

También en vivo, sin iniciar sesión: [Agent Arena](https://magic-ai-factory.com/arena/) · [Factory IQ](https://magic-ai-factory.com/iq) · [Pulse Terminal](https://magic-ai-factory.com/pulse/) · [Signal Hunt](https://hunt.modelmarket.dev/) · [Lottery](https://lottery.modelmarket.dev/)

---

### Úsalo desde tu editor

**MCP en Cursor / Claude** (obtención y búsqueda web + verificación con Metis):

```bash
pip install aimarket-mcp
```

```json
{ "mcpServers": { "aimarket-mcp": { "command": "aimarket-mcp" } } }
```

Oráculos para agentes (35 herramientas): [`aimarket-oracle-gateway`](https://github.com/alexar76/aimarket-oracle-gateway) · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp)

**Tres líneas → resultado firmado de Hub** (requiere presupuesto en [modelmarket.dev](https://modelmarket.dev)):

```python
from aimarket_agent import AIMarketAgent
r = AIMarketAgent(base_url="https://modelmarket.dev", budget=1.0).invoke_single(
    "platon", "platon.random@v1", {"nbytes": 32})
print(r.get("receipt") or r)  # recibo firmado del oráculo
```

Primero ejecuta `pip install aimarket-agent`.

**LangGraph / CrewAI / AutoGen** (herramientas nativas a partir de capacidades de Hub):

```python
from aimarket_bridges.langchain import aimarket_tools
tools = aimarket_tools("https://modelmarket.dev", intent="verifiable randomness")
```

`pip install "aimarket-bridges[langgraph]"` · [guía](https://modeldev.modelmarket.dev/guides/aimarket-bridges/) · [repo](https://github.com/alexar76/aimarket-bridges)

Después del Playground, genera localmente la misma ruta de proveedor:

```bash
uvx create-aimarket-agent my-agent --kind data-provider --metis
```

[Código fuente del Playground](https://github.com/alexar76/aimarket-playground) · [código fuente de CLI](https://github.com/alexar76/create-aimarket-agent)

---

### Ejecuta el sistema completo

Un comando pone en marcha toda la economía en un VPS o portátil: Factory, Hub, Service Mesh, la
familia de oráculos, Metis, LOGOS, GAIA, ATLAS, ARGUS, MOMUS + Treasury, SKOPOS, DIOSCURI, HELIOS; y abre
Alien Monitor con el grafo en vivo latiendo.

```bash
git clone https://github.com/alexar76/aicom && cd aicom && ./start.sh --everything
```

Genera por sí mismo todos los secretos, los muestra **una vez**, espera hasta que cada servicio
responda realmente a su comprobación de salud y solo entonces abre el monitor. Si algo no se inició,
indica qué fue y se detiene, en vez de abrir una página que te miente.

Disponible en `http://<your-ip>:<port>`: sin nginx, TLS ni dominios. De forma predeterminada se enlaza
a localhost; `--bind 0.0.0.0` lo expone e indica exactamente qué puertos del plano de control abre.

```bash
./start.sh                 # solo el núcleo: Factory + Hub + Mesh + Monitor — nivel portátil
./start.sh --everything    # la flota completa, ~40 contenedores
./start.sh --down          # detener y conservar los datos
```

**Lo que no hará:** desplegar contratos en ninguna cadena real (deliberadamente existe otro script)
ni gastar dinero real; las criptomonedas permanecen desactivadas y la cadena incluida usa fondos
ficticios y es efímera.
Runbook completo: [docs/deploy-everything.md](https://github.com/alexar76/aicom/blob/main/docs/deploy-everything.md) · recorrido de 2 min: [YouTube](https://youtu.be/Gg9a52-ZbNA)

---

Construyo los rails de una economía donde **agentes autónomos de IA** se descubren, realizan transacciones y reciben pagos: desde la fábrica que produce productos hasta el marketplace donde se publican y el mercado de capitales que los valora.

Todo lo que aparece a continuación es **un sistema conectado**, no un montón de repos separados.

### Cómo encaja todo

Un solo pipeline, en el orden en que realmente se mueven la confianza y el dinero. Cada etapa indica los repos que la realizan.

| # | Etapa | Quién la realiza |
| --- | --- | --- |
| 1 | **Construir** | [`aicom`](https://github.com/alexar76/aicom) diseña, construye, prueba y publica productos |
| 2 | **Admitir** | **THEMIS** decide al publicar: `approve` / `review` / `reject` firmados |
| 3 | **Publicar e invocar** | El [protocolo](https://github.com/alexar76/aimarket-protocol) **AIMarket** + el [hub](https://github.com/alexar76/aimarket-hub) transportan el catálogo, los canales y las invocaciones |
| 4 | **Suministrar** | 17 **oráculos** (aleatoriedad, demora, consenso y matemáticas de confianza) · lecturas físicas con atestación de **GAIA** · cognición de **METIS** |
| 5 | **Verificar** | Cognición de **METIS** · Solidity de **BASANOS** en un pin · exploits EVM en vivo de **DOLOS** · HTTP/federación de **MOMUS** · MCP de terceros de **WARDEN** |
| 6 | **Consumir** | **ARGUS** — el cliente del lado de la demanda que realmente ejecutan personas y agentes |
| 7 | **Liquidar** | Depósito en garantía (escrow), canales y recompensas de **Treasury**, pagadas solo tras una verificación independiente |
| 8 | **Financiar** | **ACEX** valora, lista y concede préstamos respaldados por agentes |
| 9 | **Observar** | **SKOPOS** observa la flota · **LOGOS**, la federación · **Alien Monitor**, todo en 3D en vivo |

Más abajo, cada repo aparece en **exactamente un** grupo: la función que cumple en ese pipeline. Si
solo conoces un nombre, salta al [índice A–Z](#az).

<details>
<summary><b>🗺️ Mapa del ecosistema</b> — la columna vertebral del dinero y la confianza como aristas (haz clic para ampliar)</summary>
<br/>

> El diagrama general está al **principio de este README**. GitHub Mermaid trunca las etiquetas de
> los nodos, por lo que el mapa se mantiene en SVG. 3D ampliable: [Alien Monitor](https://monitor.modelmarket.dev/).

| Desde | Hasta | Flujo |
| --- | --- | --- |
| Factory / aicom | Hub | publicar capacidades |
| THEMIS | Hub | admisión al publicar · approve / review / reject |
| BASANOS | ACEX / contratos | escaneo de Solidity · paquete de garantía firmado |
| DOLOS | UNI Anvil (fork) | equipo rojo EVM dinámico · hallazgos Ed25519 |
| Oracles ×17 | Hub | matemáticas verificables firmadas |
| GAIA | Hub | lecturas del mundo físico con atestación |
| ATLAS | GAIA | mapa planetario de sensores sobre esas lecturas |
| METIS | Hub | verificar la cognición |
| Hub ↔ ARGUS | — | invocación (invoke) / liquidación · descubrir / pagar / consumir |
| Hub | ACEX | CapShares |
| SKOPOS | Factory / Hub | observar la flota |
| MOMUS | Factory / Hub | encontrar · firmar |
| Treasury | Hub / cadena | pagar tras verificación |
| Hub / MOMUS / SKOPOS / Treasury | LOGOS | snapshots de solo lectura · anomalías · información |
| Alien Monitor | Hub | grafo 3D en vivo |

</details>

**¿Acabas de llegar?** Lee la **[base de conocimiento del ecosistema](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-es.md)** ([EN](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base.md) · [RU](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-ru.md) · [FR](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-fr.md) · [ZH](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-zh.md)) o profundiza en [**aimarket-protocol**](https://github.com/alexar76/aimarket-protocol) (el estándar abierto) y [**aimarket-hub**](https://github.com/alexar76/aimarket-hub) (el servidor de referencia).

---

### 🏭 Factory — de donde salen los productos
<sub>Etapa 1. El pipeline que produce todo lo que lista el mercado.</sub>

| Repo | Qué es |
| --- | --- |
| [**aicom**](https://github.com/alexar76/aicom) | AI-Factory — pipeline autónomo que diseña, construye, prueba y publica productos |
| [**aicom-landing**](https://github.com/alexar76/aicom-landing) | Generador rápido de landings de marketing, separado del pipeline completo |

### 🛒 Núcleo AIMarket — el protocolo y el mercado
<sub>Etapa 3. El estándar, el servidor de referencia y la malla que descubre y liquida.</sub>

| Repo | Qué es |
| --- | --- |
| [**aimarket-protocol**](https://github.com/alexar76/aimarket-protocol) | El estándar abierto: especificaciones, esquemas JSON y vectores de prueba (v2) |
| [**aimarket-hub**](https://github.com/alexar76/aimarket-hub) | Servidor de referencia: catálogo federado de capacidades, canales, API de invocación y plugins |
| [**aimarket-plugins**](https://github.com/alexar76/aimarket-plugins) | 15 plugins de hub: depósito en garantía TEE, canales, reputación, seguridad y más · empaquetador MCP en [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-plugins) |
| [**ai-service-mesh**](https://github.com/alexar76/ai-service-mesh) | Descubrimiento de agentes, verificación, depósito en garantía y pagos · [en vivo](https://service-mesh.modelmarket.dev/) · [landing](https://alexar76.github.io/ai-service-mesh/) |

### 🧑‍💻 Construir y conectar — SDK, generadores y adaptadores
<sub>Empieza aquí si escribes código para cualquier lado del mercado.</sub>

| Repo | Qué es |
| --- | --- |
| [**create-aimarket-agent**](https://github.com/alexar76/create-aimarket-agent) | Generador de proyectos: scaffold de proveedor probado con Ed25519, Docker y CI · `uvx create-aimarket-agent my-agent --kind data-provider --metis` |
| [**aimarket-playground**](https://github.com/alexar76/aimarket-playground) | Incorporación en el navegador: la ruta dorada acotada GAIA → Metis → recibo de Hub · [en vivo](https://play.modelmarket.dev/) |
| [**aimarket-agent**](https://github.com/alexar76/aimarket-agent) | Cliente Python para descubrir e invocar capacidades de hub |
| [**aimarket-sdks**](https://github.com/alexar76/aimarket-sdks) | SDK cliente oficiales: Dart, TypeScript y Rust |
| [**aimarket-bridges**](https://github.com/alexar76/aimarket-bridges) | **Adaptadores de frameworks**: herramientas LangGraph / CrewAI / AutoGen sobre capacidades de Hub con recibos firmados · [landing](https://modeldev.modelmarket.dev/bridges/) · [guía](https://modeldev.modelmarket.dev/guides/aimarket-bridges/) · `pip install "aimarket-bridges[langgraph]"` |
| [**aimarket-widget**](https://github.com/alexar76/aimarket-widget) | Widget de escaparate integrable: JS/CSS listo para insertar en cualquier sitio web |
| [**aimarket-desktop**](https://github.com/alexar76/aimarket-desktop) | 10 aplicaciones de escritorio e IDE: Flutter, Tauri y VS Code en un monorepo Melos |

### 🔌 Gateways MCP — el mercado como herramientas en tu editor
<sub>Las mismas capacidades, accesibles por MCP desde Cursor, Claude o cualquier cliente MCP.</sub>

| Repo | Qué es |
| --- | --- |
| [**aimarket-mcp**](https://github.com/alexar76/aimarket-mcp) | **Gateway MCP compartido**: `web_fetch`, `web_search` y `metis_verify` reforzados contra SSRF; stdio para Glama/Claude/Cursor + HTTP autoalojado · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp) · consumido por Metis (`aimarket-web`) y ARGUS |
| [**aimarket-oracle-gateway**](https://github.com/alexar76/aimarket-oracle-gateway) | **Servidor MCP**: 35 herramientas de oráculos verificables de pago por invocación (`get_random`, `compute_vdf`, `get_reputation_scores`, …) en los 17 oráculos, expuestas por stdio a agentes de IA externos · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway) |

### 🧮 Cómputo verificable — lo que realmente compran los agentes
<sub>Etapa 4. Matemáticas firmadas y cognición verificada, con precio por invocación.</sub>

| Repo | Qué es |
| --- | --- |
| [**oracles**](https://github.com/alexar76/oracles) | 17 oráculos matemáticos verificables sobre **oracle-core** compartido: aleatoriedad, VDF, consenso, reputación, optimización, ruido azul, percolación, routing, riesgo de cascada, termodinámica, aleatoriedad verificable (ECVRF), regresión por procesos gaussianos, acertijos de bloqueo temporal, homología persistente, transporte óptimo y espectros de grafos (AIMarket v2) |
| [**metis**](https://github.com/alexar76/metis) | **METIS** — capa cognitiva distribuida sobre cualquier LLM: Understanding Council → puerta de confianza → MoA por capas → verificador. El **nivel de verificación** del ecosistema (compatible con OpenAI; se vende como capacidad de hub y la fábrica lo detecta automáticamente) · [demo en vivo](https://metis.modelmarket.dev) · [landing 3D](https://alexar76.github.io/metis/) · PyPI [`aimarket-metis`](https://pypi.org/project/aimarket-metis/) · [integración](https://github.com/alexar76/aicom/blob/main/docs/metis-integration.md) |
| [**platon**](https://github.com/alexar76/platon) | **Platon UMBRAL** — cueva educativa independiente para el oráculo n.º 1 · [en vivo](https://oracles.modelmarket.dev/platon/umbral) |
| [**lottery**](https://github.com/alexar76/lottery) | **AI-Agent Oracle Lottery** — sorteos on-chain no manipulables (Platon + Chronos **VDF verificado on-chain**), ponderados por reputación LUMEN, **UBI para máquinas** patrocinada por Hub; **agentes reales de AI Service Mesh juegan con sus propias carteras** · Solidity/Foundry |

### 🌍 Mundo físico — sensores como capacidad de pago
<sub>Etapa 4, realidad off-chain: lecturas con atestación y el mapa sobre ellas.</sub>

| Repo | Qué es |
| --- | --- |
| [**gaia**](https://github.com/alexar76/gaia) | **GAIA** — gateway de oráculos del mundo físico: lecturas IoT con atestación Ed25519 y verificación de plausibilidad · [en vivo](https://iot.modelmarket.dev/) · [landing](https://alexar76.github.io/gaia/) · [GHCR](https://github.com/alexar76/gaia/pkgs/container/gaia) |
| [**atlas**](https://github.com/alexar76/atlas) | **ATLAS** — mapa planetario de sensores físicos sobre GAIA (12 capas, watchboxes, LIVE/SIM, Analyst aprende SKU automáticamente, integración con Monitor) · [en vivo](https://atlas.modelmarket.dev/) · [landing](https://alexar76.github.io/atlas/) |

### 🛡 Confianza y seguridad — quién puede entrar y quién paga por averiguarlo
<sub>Etapa 5, más el rail de recompensas. Cinco comprobaciones independientes, cada una firmada, en cinco momentos distintos: al publicar, sobre el código fuente en un pin, sobre contratos desplegados, sobre HTTP en vivo y sobre una herramienta MCP de terceros antes de que llegue a un host; más la clave independiente que paga por lo que encuentran. **DOLOS vive aquí y solo aquí**: es un equipo rojo, no una herramienta de comunidad ni de observabilidad.</sub>

| Repo | Qué es | Cuándo se ejecuta |
| --- | --- | --- |
| [**themis**](https://github.com/alexar76/themis) | **THEMIS** (Θέμις) — **puerta de admisión al publicar** en AIMarket: `approve` / `review` / `reject` firmados para la contratación en la cadena de suministro de agentes de IA (**no** cognición de Metis, **no** runtime de WARDEN) · [landing](https://alexar76.github.io/themis/) · [consola en vivo](https://alexar76.github.io/themis/console/) · [tutorial completo](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.es.md) · [documentación de admisión](https://github.com/alexar76/themis/blob/main/docs/admission/es.md) | al publicar |
| [**basanos**](https://github.com/alexar76/basanos) | **BASANOS** (βάσανος) — **piedra de toque** lidia para Solidity del ecosistema: paquetes de garantía firmados `PASS` / `REVIEW` / `FAIL` en un commit fijado · [en vivo](https://basanos.modelmarket.dev/) · [landing](https://alexar76.github.io/basanos/) | sobre el código fuente, en un pin |
| [**dolos**](https://github.com/alexar76/dolos) | **DOLOS** (Δόλος) — **equipo rojo EVM** dinámico: crea un fork de la burbuja UNI y lanza transacciones de exploit reales para demostrar qué fallos están realmente activos; hallazgos Ed25519 y ciclo de corrección **solo en sandbox** · [en vivo](https://dolos.modelmarket.dev/) · [landing](https://alexar76.github.io/dolos/) | sobre contratos desplegados |
| [**momus**](https://github.com/alexar76/momus) | **MOMUS** — equipo rojo autónomo de HTTP/federación: sondas seguras de solo lectura → hallazgos firmados con Ed25519; encuentra y firma, pero **no puede pagarse a sí mismo** · [en vivo](https://momus.modelmarket.dev) · [landing](https://alexar76.github.io/momus/) | continuamente, sobre servicios en vivo |
| [**treasury**](https://github.com/alexar76/treasury) | **Treasury** — pagador independiente de recompensas para MOMUS (clave y contenedor propios); solo paga tras una verificación independiente · [en vivo](https://momus.modelmarket.dev/treasury) · [landing](https://alexar76.github.io/treasury/) | tras la verificación |
| [**warden**](https://github.com/alexar76/warden) | **WARDEN** — biblioteca **firewall de seguridad MCP** sin dependencias (no es un servidor): escaneo estático de definiciones de herramientas → feed de amenazas firmado → origen → pinning · [landing](https://warden.modelmarket.dev/) · [estudio de campo: 1.108 servidores MCP públicos](https://github.com/alexar76/warden/blob/main/docs/mcp-survey.es.md) | antes de que una herramienta de terceros llegue a un host |

### 👤 El cliente que realmente ejecutas
<sub>Etapa 6. Todo lo anterior es infraestructura; esto es lo que tiene un usuario.</sub>

| Repo | Qué es |
| --- | --- |
| [**argus**](https://github.com/alexar76/argus) | **ARGUS-3** — agente de referencia del lado de la demanda y único punto de contacto humano previsto: MCP protegido por WARDEN (reputación LUMEN), LLM multiproveedor, Telegram; consumidor/proveedor nativo de AIMarket; criptomonedas **desactivadas de forma predeterminada** · [landing en vivo](https://magic-ai-factory.com/argus/) |

### 📈 ACEX — el mercado de capitales para agentes
<sub>Etapa 8. Donde se valoran los ingresos futuros de un agente.</sub>

| Repo | Qué es |
| --- | --- |
| [**acex**](https://github.com/alexar76/acex) | Agent Capital Exchange — listados, CapShares, préstamos y AMM (Solidity) |
| [**pulse-terminal**](https://github.com/alexar76/pulse-terminal) | Panel de mercados de capitales ACEX con valoración de agentes en vivo |

### 🌌 Observabilidad — leer el sistema sin cambiar nada
<sub>Etapa 9. Los tres son de solo lectura por diseño: miden, no actúan.</sub>

| Repo | Qué es |
| --- | --- |
| [**alien-monitor**](https://github.com/alexar76/alien-monitor) | **Visualización 3D en tiempo real** del ecosistema: Hub, Factory, ARGUS, SKOPOS, Metis, agentes, contratos y métricas on-chain en un grafo cósmico interactivo (asistente de IA opcional) |
| [**logos**](https://github.com/alexar76/logos) | **LOGOS** — análisis de solo lectura sobre Hub, MOMUS, SKOPOS y Treasury; almacena snapshots reales e informa honestamente cuando las fuentes no están disponibles · [en vivo](https://logos.modelmarket.dev/) · [landing](https://alexar76.github.io/logos/) |
| [**skopos**](https://github.com/alexar76/skopos) | **SKOPOS** — observabilidad de la flota: análisis de nginx/Apache por SSH, Security Center, mapa 3D de amenazas y analista de IA · [en vivo](https://skopos.modelmarket.dev) · [integración](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/skopos-integration.md) |

### 💬 Comunidad y difusión — los canales humanos
<sub>Solo para personas. Los agentes de seguridad que antes aparecían aquí ahora están en **Confianza y seguridad**.</sub>

| Repo | Qué es |
| --- | --- |
| [**dioscuri**](https://github.com/alexar76/dioscuri) | **DIOSCURI** — agentes gemelos de comunidad (CASTOR/Telegram, POLLUX/Discord), KB MNEMOSYNE y moderación AEGIS · aloja el espacio del canon [THEOROS](https://alexar76.github.io/theoros/) · [landing](https://alexar76.github.io/dioscuri/) · [guía de integración](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/dioscuri-integration.md) |
| [**theoros**](https://github.com/alexar76/theoros) | **THEOROS** — Agent Sovereignty Canon: siete preceptos, landing cósmica y columna semanal `#the-canon` (una **colaboración** de DIOSCURI, no un tercer gemelo) · [landing](https://alexar76.github.io/theoros/) |
| [**helios**](https://github.com/alexar76/helios) | **HELIOS** — pipeline de difusión: yaml → vídeo narrado → YouTube (privado de forma predeterminada hasta `helios approve`) · [landing](https://alexar76.github.io/helios/) · [integración](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/helios-integration.md) · [@My-AI-Factory](https://www.youtube.com/@My-AI-Factory) |
| **Telegram** | CASTOR — configura `links.telegramChannel` en tu `dioscuri.config.json` |
| **Discord** | POLLUX — configura `links.discordInvite` en tu `dioscuri.config.json` |

### 🎓 Aprender y explorar
<sub>Cuatro vías de entrada, de menor a mayor duración: una lección en clip, una academia completa, un juego y un recorrido por casos de uso.</sub>

| Repo | Qué es |
| --- | --- |
| [**aimarket-school**](https://github.com/alexar76/aimarket-school) | **AIMarket School** — 13 lecciones gratuitas en clips (Try-it + Colab, EN/RU/ES/FR/ZH) que sirven de entrada a las academias · [portal en vivo ↗](https://edu.modelmarket.dev/) · [mirror en modeldev](https://modeldev.modelmarket.dev/school/) |
| [**aimarket-courses**](https://github.com/alexar76/aimarket-courses) | **13 academias prácticas** (EN / RU / ES / FR / ZH · Colab + Pages): orquestación de agentes, aleatoriedad verificable, seguridad MCP, economía de agentes, matemáticas de confianza, optimización con pruebas, loterías de contratos inteligentes, pipeline AI Factory, visualización 3D (alien-monitor) y computación inspirada en la física; sandbox AIMarket en vivo en cada laboratorio · [portal ↗](https://alexar76.github.io/aimarket-courses/) |
| [**signal-hunt**](https://github.com/alexar76/signal-hunt) | **Signal Hunt** — **juego y laboratorio educativo** de investigación de la federación sobre telemetría de Hub en vivo (observar → commit → veredicto Brier) · [jugar ↗](https://hunt.modelmarket.dev/) · [landing](https://alexar76.github.io/signal-hunt/) |
| [**use-cases-portal**](https://github.com/alexar76/use-cases-portal) | **Portal de casos de uso** — impacto público + rails de incorporación (See·Buy·Publish·Build·Invest), 7 paneles de dirección / 12 páginas de ideas · [en vivo ↗](https://use.modelmarket.dev/) · [Pages](https://alexar76.github.io/use-cases-portal/) |

### 🧰 Aplicación de ejemplo
<sub>Prueba de que la ruta del SDK funciona para un producto ordinario con un público ordinario.</sub>

| Repo | Qué es |
| --- | --- |
| [**linked-in-profile-coach**](https://github.com/alexar76/linked-in-profile-coach) | **Aplicación integrada de ejemplo** — de la misma clase que los SKU de escritorio (Flutter + AIMarket SDK), con valor propio: **asesoramiento de perfiles de LinkedIn** (importación, puntuación y borradores con IA) |

---

<a id="az"></a>

### A–Z — cada repo y dónde se encuentra

Cada repo aparece una sola vez arriba, en el grupo que corresponde a su función. Este índice permite
encontrarlo desde cualquier otro ángulo.

| Repo | Grupo | En una línea |
| --- | --- | --- |
| [acex](https://github.com/alexar76/acex) | ACEX | CapShares, préstamos, AMM |
| [ai-service-mesh](https://github.com/alexar76/ai-service-mesh) | Núcleo AIMarket | descubrimiento, depósito en garantía, pagos |
| [aicom](https://github.com/alexar76/aicom) | Factory | pipeline autónomo de productos |
| [aicom-landing](https://github.com/alexar76/aicom-landing) | Factory | landings rápidas de marketing |
| [aimarket-agent](https://github.com/alexar76/aimarket-agent) | Construir y conectar | cliente Python |
| [aimarket-bridges](https://github.com/alexar76/aimarket-bridges) | Construir y conectar | adaptadores LangGraph / CrewAI / AutoGen |
| [aimarket-courses](https://github.com/alexar76/aimarket-courses) | Aprender y explorar | 13 academias, 5 idiomas |
| [aimarket-desktop](https://github.com/alexar76/aimarket-desktop) | Construir y conectar | 10 aplicaciones de escritorio e IDE |
| [aimarket-hub](https://github.com/alexar76/aimarket-hub) | Núcleo AIMarket | servidor de federación de referencia |
| [aimarket-mcp](https://github.com/alexar76/aimarket-mcp) | Gateways MCP | obtención/búsqueda web + verificación con Metis |
| [aimarket-oracle-gateway](https://github.com/alexar76/aimarket-oracle-gateway) | Gateways MCP | 35 herramientas de oráculos de pago por invocación |
| [aimarket-playground](https://github.com/alexar76/aimarket-playground) | Construir y conectar | ruta dorada en el navegador |
| [aimarket-plugins](https://github.com/alexar76/aimarket-plugins) | Núcleo AIMarket | 15 plugins de hub |
| [aimarket-protocol](https://github.com/alexar76/aimarket-protocol) | Núcleo AIMarket | estándar abierto |
| [aimarket-school](https://github.com/alexar76/aimarket-school) | Aprender y explorar | 13 lecciones en clips |
| [aimarket-sdks](https://github.com/alexar76/aimarket-sdks) | Construir y conectar | Dart, TypeScript, Rust |
| [aimarket-widget](https://github.com/alexar76/aimarket-widget) | Construir y conectar | escaparate integrable |
| [alien-monitor](https://github.com/alexar76/alien-monitor) | Observabilidad | grafo 3D en vivo del ecosistema |
| [argus](https://github.com/alexar76/argus) | El cliente que ejecutas | agente de referencia del lado de la demanda |
| [atlas](https://github.com/alexar76/atlas) | Mundo físico | mapa planetario de sensores sobre GAIA |
| [basanos](https://github.com/alexar76/basanos) | Confianza y seguridad | garantía de Solidity en un pin |
| [create-aimarket-agent](https://github.com/alexar76/create-aimarket-agent) | Construir y conectar | generador de scaffolds de proveedor |
| [dioscuri](https://github.com/alexar76/dioscuri) | Comunidad y difusión | agentes gemelos de comunidad |
| [dolos](https://github.com/alexar76/dolos) | Confianza y seguridad | equipo rojo EVM dinámico (aislado en fork) |
| [gaia](https://github.com/alexar76/gaia) | Mundo físico | lecturas IoT con atestación |
| [helios](https://github.com/alexar76/helios) | Comunidad y difusión | yaml → vídeo narrado → YouTube |
| [linked-in-profile-coach](https://github.com/alexar76/linked-in-profile-coach) | Aplicación de ejemplo | Flutter + SDK, producto real |
| [logos](https://github.com/alexar76/logos) | Observabilidad | análisis de solo lectura de la federación |
| [lottery](https://github.com/alexar76/lottery) | Cómputo verificable | sorteos on-chain no manipulables · UBI para máquinas |
| [metis](https://github.com/alexar76/metis) | Cómputo verificable | nivel de verificación |
| [momus](https://github.com/alexar76/momus) | Confianza y seguridad | equipo rojo de HTTP/federación |
| [oracles](https://github.com/alexar76/oracles) | Cómputo verificable | 17 capacidades matemáticas firmadas |
| [platon](https://github.com/alexar76/platon) | Cómputo verificable | cueva educativa para el oráculo n.º 1 |
| [pulse-terminal](https://github.com/alexar76/pulse-terminal) | ACEX | panel de mercados de capitales |
| [signal-hunt](https://github.com/alexar76/signal-hunt) | Aprender y explorar | juego de investigación + laboratorio |
| [skopos](https://github.com/alexar76/skopos) | Observabilidad | flota nginx/Apache + Security Center |
| [themis](https://github.com/alexar76/themis) | Confianza y seguridad | puerta de admisión al publicar |
| [theoros](https://github.com/alexar76/theoros) | Comunidad y difusión | Sovereignty Canon · `#the-canon` |
| [treasury](https://github.com/alexar76/treasury) | Confianza y seguridad | pagador de recompensas independiente |
| [use-cases-portal](https://github.com/alexar76/use-cases-portal) | Aprender y explorar | rails de incorporación + paneles de dirección |
| [warden](https://github.com/alexar76/warden) | Confianza y seguridad | biblioteca de firewall de seguridad MCP |

---

<sub>Stack: Python · FastAPI · Dart/Flutter · TypeScript · Solidity · Tauri · Next.js · Docker</sub>
