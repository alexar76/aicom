# Casos de uso

Attested Memory sirve cuando **olvidar sale caro** y **confiar a ciegas sale
peor**. Estos escenarios muestran cuándo una nota, un chat o un almacén
vectorial no bastan — y cuándo identidad, truth state, provenance y un
settlement exacto convierten el contexto en algo sobre lo que puedes actuar.

Los nombres de rutas, cabeceras y términos de pago se mantienen exactos en
todos los idiomas. Solo se localiza el texto explicativo.

## Segundo cerebro del fundador que sobrevive al context rot

**Quién.** Un fundador, investigador u operador que salta cada día entre
herramientas, agentes y dispositivos.

**Problema.** Las decisiones viven en chats, volcados de Notion y prompts a
medias. Seis semanas después nadie puede decir *por qué* se eligió un camino,
qué fuentes se confiaron o qué agente inventó un resumen cómodo.

**Cómo funciona.**

1. Escribe un Memory Unit con la decisión, la justificación, etiquetas y
   `source_refs`.
2. Firma como actor (`X-Actor-ID` / public key / signature). La clave privada
   permanece en tu cliente.
3. Más tarde, busca en `/memory/api/search` e inspecciona truth + provenance
   antes de reutilizar la memoria en un plan nuevo o en una ejecución de
   agente.

**Por qué importa la attestation.** No recuperas «un párrafo similar».
Recuperas una afirmación portable con un actor y un linaje.

**Empezar.** [Personal Memory](/memory) · [Guía de usuario](USER_GUIDE.md) ·
trial en [/billing](/billing).

## War-room de incidente que conserva el rastro de decisiones

**Quién.** Ingenieros on-call, SRE, responders de seguridad.

**Problema.** El canal del outage avanza más rápido que la wiki. El postmortem
se escribe de memoria, la autoría de cada llamada es difusa, y la semana
siguiente un agente repite una mitigación rechazada porque nadie firmó nada
en un namespace compartido.

**Cómo funciona.**

1. Abre un workspace de Team Memory OS y crea un team namespace.
2. Los miembros escriben notas del incidente, opciones rechazadas y acciones
   finales con firmas de actor.
3. El SaaS gateway comprueba la membresía; el Hub solo acepta registros
   `team:<id>` coincidentes. Las consultas no pueden cruzar a otro equipo.

**Por qué importa la attestation.** Los handoffs se vuelven auditables. El
offboarding revoca la clave; las team assertions de corta vida caducan sin
una cacería forense por los chats.

**Empezar.** [Team Memory OS](/teams) · [Guía de usuario § Team](USER_GUIDE.md).

## Conocimiento experto que se vende sin filtrar el corpus

**Quién.** Expertos de dominio, shops de research, boutiques de advisory.

**Problema.** Publicar el corpus completo gratis destruye el negocio.
Publicar solo un teaser destruye la confianza. El comprador necesita ver
provenance antes de pagar; el vendedor necesita acceso acotado en el tiempo,
no copias perpetuas por defecto.

**Cómo funciona.**

1. Publica un Memory Unit con campos de resumen públicos y visibilidad de
   pago para el cuerpo.
2. El comprador busca en el catálogo, inspecciona truth/provenance y abre un
   invoice exacto en Base USDC.
3. KOVA verifica la transferencia; el Gateway emite un entitlement acotado.
   El acceso caduca con el plan.

**Por qué importa la attestation.** El discovery es honesto. El settlement es
exacto. El entitlement es scope criptográfico del producto, no un enlace PDF
«por honor».

**Empezar.** [Expert Memory Market](/market) · [Pagos](/billing).

## Handoff multi-agente con continuidad criptográfica

**Quién.** Operadores de agentes, equipos de orquestación, workflows autónomos.

**Problema.** El agente A deja un resumen de chat para el agente B. El resumen
no está firmado, parcialmente alucinado y sin fuentes. El fallo parece «el
siguiente modelo era tonto» cuando el bug real fue la pérdida silenciosa de
provenance.

**Cómo funciona.**

1. El agente A escribe un Memory Unit de handoff firmado: restricciones,
   herramientas usadas, fuentes, riesgos abiertos.
2. El agente B lo recupera con la misma política actor/team y verifica
   provenance antes de continuar.
3. El truth state viaja con la unit — las contradicciones quedan visibles en
   lugar de alisarse en prosa segura.

**Por qué importa la attestation.** La continuidad es propiedad del registro,
no de quien dejó la pestaña abierta.

**Empezar.** [Developers](/developers) ·
[Guía de usuario § Actor identity](USER_GUIDE.md).

## Due diligence e investigación con claims anclados a fuentes

**Quién.** Analistas, counsel, equipos de investment y vendor-review.

**Problema.** Las notas de diligence citan «el deck», «la call» y «algo de
Slack». Cuando se cuestiona un claim, la cadena de custodia es una sensación.

**Cómo funciona.**

1. Captura cada claim material como Memory Unit con `source_refs` explícitos.
2. Adjunta o actualiza el truth state conforme llega evidencia (confirmed,
   disputed, insufficient).
3. Reconstruye el expediente después a partir de provenance receipts, no de
   folklore reconstruido.

**Por qué importa la attestation.** Los revisores discuten el claim y su
evidencia, no de quiénes notas eran «más recientes».

**Empezar.** Producto Personal o Team · [Glosario](GLOSSARY.md).

## Acceso de pago automatizado cuando el navegador ya no está

**Quién.** Compradores que pagan desde una wallet app, scripts que liquidan
invoices y operadores que no pueden cuidar una pestaña de checkout.

**Problema.** El checkout clásico muere al cerrar la pestaña. Los flujos
manuales de «pega el tx hash» generan tickets de soporte y pagos parciales
ambiguos.

**Cómo funciona.**

1. `POST /v1/billing/orders` con un `Idempotency-Key` único, plan y payer.
2. Envía el importe exacto de USDC canónico en Base al destinatario del
   invoice.
3. KOVA empareja token, payer, recipient, amount y profundidad de
   confirmación.
4. El Gateway activa la clave de producto automáticamente. Un poll a
   `GET /v1/billing/orders/{id}` con el checkout token devuelve la clave
   cuando está confirmed — aunque la sesión original del navegador haya
   desaparecido.

**Por qué importa la attestation.** El movimiento de dinero y la emisión del
entitlement quedan ligados por la identidad exacta del invoice, no por una
captura de pantalla de la wallet.

**Empezar.** [Billing](/billing) · [Guía de usuario § Buy access](USER_GUIDE.md).

## Offboarding seguro sin dejar huérfana a la institución

**Quién.** Team leads, security, IT.

**Problema.** Un operador que se va aún tiene exportaciones de chat y notas
personales con los runbooks reales. Revocar Slack no revoca la memoria
institucional que nunca vivió en un sistema controlado.

**Cómo funciona.**

1. Mantén el conocimiento operativo en Team Memory OS bajo un namespace
   explícito.
2. Rota o revoca la clave SaaS de inmediato al marcharse.
3. Las team assertions caducan en minutos; la política del Hub sigue exigiendo
   actor proofs para lecturas y escrituras protegidas.

**Por qué importa la attestation.** El acceso termina como evento del
control plane, no como la esperanza de que alguien borró una carpeta de Drive.

**Empezar.** [Team Memory OS](/teams).

## Para qué no sirve

- Un archivo general de chats sin disciplina de identidad ni de fuentes.
- Un sitio para guardar private keys de wallets, seed phrases o credenciales
  en bruto.
- Volcados «compartir con el mundo» sin política de visibility.
- Pagos crypto redondeados o aproximados — el importe exacto de USDC es el
  invoice.

Si tu workflow tolera la pérdida silenciosa de autoría, fuentes y finalidad
de pago, basta un cuaderno. Si no, empieza por la superficie de producto que
corresponda arriba y mantén exactos los contratos del Hub.
