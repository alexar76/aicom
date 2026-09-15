# Revisión de madurez del ecosistema — crítica externa y plan de acción

**Fecha:** 2026-07-12  
**Objetivo:** Validación honesta de un scorecard de terceros y **acciones concretas dentro del repo** que podemos ejecutar ahora vs. bloqueos del operador/proveedor.

**Véase también:** [known-issues.md](known-issues.md) · [pet-project-trust.md](pet-project-trust.md) · [oracles crypto-maturity](https://github.com/alexar76/oracles/blob/main/docs/crypto-maturity.en.md)

---

## ¿Es justa la crítica?

| Componente | Puntuación externa | Veredicto | En una línea |
|------------|--------------------|-----------|--------------|
| **1. AI-Factory** | 7.8/10 | **Mayormente justa** | Un pipeline multiagente real + gates en ~2 meses es impresionante; KI-3/KI-2/KI-4 y los MVP entregados coinciden con la crítica. |
| **2. Metis** | 8.0/10 | **Justa** | Diseño sólido (gate de confianza, ruta de verificación); el clúster distribuido y la cobertura adversarial son incipientes. |
| **3. Oracles ×17** | 6.5–6.7/10 | **Justa** | Amplitud > profundidad; crypto sin endurecer ([KI-6](known-issues.md#ki-6--oracle-family-cryptographic-maturity-not-production-hardened)). |
| **4. ARGUS-3** | 7.5/10 | **Justa** | WARDEN es real y está probado contra el envenenamiento evidente; los ataques sofisticados (codificación, exfiltración en tiempo de ejecución, evasión del lado del modelo) no están cubiertos. |
| **5. Hub + Protocol** | 7.2/10 | **Justa** | La spec v2 + el hub de referencia son sólidos; la federación/el micropago a escala no están probados; adopción externa ≈ 0. |
| **6. Alien Monitor** | 8.0/10 | **Justa** | Observabilidad pulida; modelo de autenticación corregido; no es una capa de confianza financiera. |
| **7. Soporte (HELIOS, DIOSCURI, escritorio, widget)** | 6.8–7.3/10 | **Justa** | Satélites útiles; secundarios frente a Factory/Hub/ARGUS; DIOSCURI = devrel + demo de seguridad de referencia. |

**Global:** La revisión es **direccionalmente correcta**. Las puntuaciones son subjetivas, pero los *riesgos nombrados* coinciden con lo que ya seguimos en los docs KI-* y de pet-project trust. Nada de esto es FUD — es la misma postura pre-mainnet que declaramos públicamente.

---

## Matriz de acciones

| ID | Componente | Acción | Responsable | Estado |
|----|------------|--------|-------------|--------|
| **A-1** | Factory | Documentar los perfiles de pipeline **minimal vs full**; recomendar minimal para landings MVP | in-repo | [`factory-pipeline-profiles.md`](factory-pipeline-profiles.md) |
| **A-2** | Factory | Etiquetar las salidas de ejemplo como **nivel MVP**; enlazar el replay del build | in-repo | [`sample-output/README.md`](sample-output/README.md) |
| **A-3** | Factory | Seguir explícitamente las brechas de producción | in-repo | **KI-7** en known-issues |
| **A-4** | Metis | Documentar las brechas distribuido + adversarial | in-repo | [`metis/docs/en/MATURITY.md`](https://github.com/alexar76/metis/blob/main/docs/en/MATURITY.md) |
| **A-5** | Metis | Sembrar tests de regresión del gate adversarial | in-repo | `metis/tests/test_adversarial_gates.py` |
| **A-6** | Metis | Seguir el soak del clúster + el benchmark red-team | in-repo | **KI-8** |
| **A-7** | Oracles | Honestidad crypto (Chronos, PQC híbrido, nivel prototipo) | in-repo | **KI-6** + docs crypto-maturity ✅ |
| **A-8** | ARGUS | Limitaciones de WARDEN + brecha ante ataques sofisticados | in-repo | [`argus/docs/security-warden.md`](https://github.com/alexar76/argus/blob/main/docs/security-warden.md) §Limitations |
| **A-9** | ARGUS | Test de fixture adversarial (inyección ofuscada) | in-repo | `argus/test/adversarial-warden.test.ts` |
| **A-10** | ARGUS | Seguir la ruta red-team / bug bounty | in-repo | **KI-9** |
| **A-11** | Hub | Honestidad de federación/adopción + plan para los casos límite | in-repo | [`aimarket-hub/docs/MATURITY.md`](https://github.com/alexar76/aimarket-hub/blob/main/docs/MATURITY.md) + **KI-10** |
| **A-12** | Monitor | Sin cambios — mantener la etiqueta de nivel «observabilidad, no confianza» | — | tabla pet-project-trust |
| **A-13** | Soporte | Nivel **secundario / devrel** en pet-project-trust | in-repo | pet-project-trust.md |
| **A-14** | All | Enlazar desde ROADMAP + README | in-repo | ROADMAP.md |

**Solo operador (no se puede cerrar únicamente con documentación):** auditoría KI-2, test de carga KI-3, multisig KI-4, auditoría crypto KI-6, adopción en producción en hubs de terceros.

---

## Detalle por componente

### 1. AI-Factory (7.8)

**Crítica validada:** El pipeline es el subsistema más grande; los agentes condicionales/el director/los gates añaden superficie operativa; el self-host Docker es una fortaleza; la checklist de producción (carga, multisig, auditoría) está explícitamente abierta; las demos públicas se inclinan hacia escaparates landing/MVP ([`docs/sample-output/`](sample-output/)).

**No discrepamos con el «sobreingeniería» para un proyecto personal** — la pila de fragmentos por defecto encadena PM → arquitecto → dev → QA → seguridad → despliegue → marketing. Es adecuado para builds de escaparate, pesado para una simple landing page.

**Acciones:** A-1, A-2, A-3, `./scripts/quickstart.sh` para una demo de un solo comando.

### 2. Metis (8.0)

**Crítica validada:** El modo distribuido existe ([`metis/docs/en/DISTRIBUTED.md`](https://github.com/alexar76/metis/blob/main/docs/en/DISTRIBUTED.md)) pero los clústeres multirregión necesitan pruebas de soak; el gate de confianza es fail-closed ante señales *estructuradas* pero confía en el `confidence` asignado por el council — alucinaciones sutiles con un self-score alto pueden pasar; la medición económica es orientativa mientras Factory no imponga los débitos.

**Acciones:** A-4, A-5, A-6; los benchmarks ya señalan «señal de confianza, no techo de precisión» ([`metis/docs/benchmarks/`](https://github.com/alexar76/metis/tree/main/docs/benchmarks/)).

### 3. Oracles (6.5–6.7)

**Crítica validada:** Ya tratado en [crypto-maturity.en.md](https://github.com/alexar76/oracles/blob/main/docs/crypto-maturity.en.md). La aleatoriedad de Platon + la reputación de Lumen necesitan la misma clase de revisión externa que el VDF de Chronos.

### 4. ARGUS (7.5)

**Crítica validada:** WARDEN detecta el envenenamiento de manual ([`argus/test/warden.test.ts`](https://github.com/alexar76/argus/blob/main/test/warden.test.ts)); `allowUnknownServers: true` en los tests refleja valores por defecto realmente permisivos; la reputación se degrada a neutral cuando LUMEN es inalcanzable (autonomía por encima de fail-closed).

**Acciones:** A-8, A-9, A-10.

### 5. Hub + Protocol (7.2)

**Crítica validada:** El protocolo v2 es la base correcta; el crawler de federación + los canales funcionan en el despliegue de referencia; no hay una malla de hubs de terceros significativa ni volumen de invocaciones en producción → los casos límite (sincronización del slashing, carrera en los canales, manifest obsoleto) siguen siendo mayormente teóricos.

**Acciones:** A-11, KI-10.

### 6. Alien Monitor (8.0)

**Crítica validada:** UX sólida y topología LIVE; crítica limitada. No sustituye a la seguridad económica.

### 7. Herramientas de soporte (6.8–7.3)

**Crítica validada:** HELIOS, el widget y las integraciones de escritorio son reales pero **secundarios**. DIOSCURI (Castor/Pollux) es **devrel + endurecimiento de referencia** sobre chat público — valioso, pero no una infraestructura de agentes de producción.

**Acciones:** A-13 — etiquetas de nivel, sin sobreventa en la landing del ecosistema.

---

## Mensaje (uso público)

> *Economía de agentes de IA autoalojada — nivel investigación/prototipo. Demos sólidas y cableado del protocolo; se requiere auditoría externa, pruebas de carga y revisión crypto antes de un TVL a escala mainnet.*

---

> 🌐 Idiomas: [English](ecosystem-maturity-review.en.md) · [Русский](ecosystem-maturity-review.ru.md) · [Français](ecosystem-maturity-review.fr.md) · **Español** · [中文](ecosystem-maturity-review.zh.md)
</content>
</invoke>
