# HEPHAESTUS — la forja: presupuestar un grafo de capacidades antes de pagarlo

> **English:** [hephaestus-studio.md](./hephaestus-studio.md) · **Русский:** [hephaestus-studio.ru.md](./hephaestus-studio.ru.md) · **Français:** [hephaestus-studio.fr.md](./hephaestus-studio.fr.md) · **中文:** [hephaestus-studio.zh.md](./hephaestus-studio.zh.md)
>
> How to drive the page: [hephaestus-user-guide.es.md](./hephaestus-user-guide.es.md) · What to build with it: [hephaestus-use-cases.es.md](./hephaestus-use-cases.es.md)
>
> Núcleo: [`hephaestus/`](https://github.com/alexar76/hephaestus/tree/main/). Nodo del monitor: `hephaestus`. Ejecutor: `POST /ai-market/pipelines`. · **Instalación y capturas:** [hephaestus/README.md](https://github.com/alexar76/hephaestus/blob/main/README.md)

---

## Qué es

HEPHAESTUS compone una cadena de capacidades del mercado, **calcula su coste antes de pagar nada**,
la envía al ejecutor de pipelines y conserva el bill of materials (lista de materiales) firmado que
vuelve, incluido el salto (hop) culpable cuando la cadena falla.

No es un constructor genérico de flujos de trabajo. Cada nodo es una fila real del manifiesto
firmado del hub, con precio, latencia declarada y una cantidad declarada de evidencia sobre su
fiabilidad. Ahí está toda la diferencia: un grafo así puede responder *cuánto costará esto* y *quién
lo rompió*, algo que no da ninguna cantidad de rectángulos dibujados.

Dos superficies, separadas a propósito:

| Superficie | Papel |
|------------|-------|
| Nodo `hephaestus` en Alien Monitor | **Observación.** Ejecuciones reales — coste, saltos, salto culpable — y qué parte del catálogo se puede conectar de verdad. |
| Página del estudio | **Construcción.** Elegir capacidades, rellenar parámetros, ver el presupuesto, enviar. |

El monitor observa; no alberga el editor. Una superficie de observación que inventa un flujo es peor
que una vacía, así que sin ejecuciones registradas el panel lo dice exactamente así.

## La página del estudio

El hub la sirve en **`/studio`**, y no es una elección arbitraria: el catálogo con el que
compone es el propio manifiesto firmado del hub, y su CORS es fail-closed, así que una
página alojada en otro sitio no podría leerlo. Mismo origen, sin puente y sin un segundo
dominio.

Ejecutar también es del mismo origen. El ejecutor de pipelines es otro servicio y el
navegador no lo alcanza entre orígenes, así que el hub reenvía una petición mediante
`POST /studio/run`. Ese reenvío es deliberadamente estrecho:

* el destino viene de `AIMARKET_PIPELINE_EXECUTOR_URL` en el hub, **nunca del cuerpo de la
  petición** — un reenviador que toma su destino del llamante es un artefacto de SSRF se
  llame como se llame, y este es alcanzable desde cualquier navegador;
* sin configurar significa `503` nombrando la variable, no una suposición sobre algún
  puerto local;
* el cuerpo se valida en forma y tamaño antes de que algo salga del hub, con el mismo
  límite de dieciséis nodos que acepta el ejecutor;
* no se reenvían credenciales del llamante: la ruta de ejecución del estudio es la
  gratuita (sandbox), y una ejecución de pago va al ejecutor directamente con su canal.

La respuesta lleva `trace_url`, de modo que la página enlaza al bill of materials firmado
en vez de pedir que se confíe en su propio resumen.

```bash
cd hephaestus/studio && npm install && npm run build   # genera dist/, servido en /studio
```

En este repositorio no se versiona la salida de build, así que el bundle lo produce una
etapa Node en la imagen del hub (la imagen de runtime es solo Python). Un despliegue que
igualmente carezca de `hephaestus/studio/dist` responde `503` nombrando el build que falta,
en lugar de un 404.

Por debajo de 900px de **ancho real** del contenedor las tres columnas pasan a ser una a la vez — catálogo, lienzo, comprobaciones —
conmutadas desde una barra inferior: a 375px una paleta y un inspector dejan al lienzo unos
pocos píxeles, y el lienzo es el panel que tiene que ser usable. El presupuesto permanece en
la cabecera en ambos diseños: es la razón de ser de la página. Añadir un módulo salta al
lienzo y tocar uno salta a sus parámetros, así que un toque nunca cae en un panel que no se
ve.

El punto de corte se mide sobre el elemento con un `ResizeObserver`, no se pregunta al
viewport: una ventana puede ser físicamente estrecha y declarar un viewport CSS ancho —un
user agent de escritorio en un móvil, una ventana escalada o con zoom, un marco embebido— y
en todos esos casos la media query es falsa mientras el lienzo queda reducido a una tira.

## Asistentes: un objetivo resuelto contra el catálogo

Un asistente es un objetivo más una lista ordenada de **roles**. Un rol es un predicado
sobre lo que una capacidad *declara* —los campos que produce, los que exige, la forma de su
identificador— y nunca sobre un `product_id` fijado en el código. Por eso un asistente no
puede ofrecer una fila que no esté en venta, y sigue funcionando cuando el catálogo cambia;
una lista curada de recetas no consigue ninguna de las dos cosas.

La resolución elige una capacidad por rol, ordenada así: cuántos datos recibe el salto del
anterior, luego cuánto queda por escribir a mano, luego si la fila tiene observaciones
medidas detrás, y por último el precio. El precio va al final a propósito: la cadena más
barata que no hace el trabajo no es un ahorro.

Dos salvaguardas, ambas nacidas de que el catálogo real derrotó a la versión ingenua:

* **`consumes`** — al menos un campo conectado tiene que corresponder a lo que el rol debe
  recibir. Sin ella, `platon.random@v1` se emparejaba con `platon.beacon@v1` por
  `num_bytes`: el sorteo devuelve su propio parámetro en la salida y el faro acepta ese
  parámetro como entrada, así que encajan limpiamente y no auditan nada. Un salto que
  consume los *parámetros* del anterior no consume su *resultado*.
* **`sameProductAsPrevious`** — con material criptográfico esto es corrección, no
  preferencia. `proof` es el nombre de un campo, no un formato: el resolutor envió sin
  problema una prueba VRF de `platon.random@v1` a `chronos.verify@v1`, un verificador VDF,
  porque ambos lo llaman `proof`. Esa cadena factura el primer salto y luego falla con una
  prueba que el segundo no sabe leer. Los datos normales —una lectura, una ubicación— quedan
  sin restringir, porque allí una segunda opinión de *otro* proveedor vale más que una del
  mismo.

Un objetivo cuyos roles no se pueden cubrir se devuelve **no disponible, con el rol que
falló**, y el menú lo muestra con ese motivo en lugar de esconderlo. Hoy dos de los cuatro
están no disponibles, y ambos motivos son huecos reales: nadie vende un verificador para los
propios sorteos de `platon`, y `atlas.situation.brief@v1` exige un marco
(`west/south/east/north`) que ninguna capacidad del catálogo produce —`atlas.point.read@v1`
emite un objeto `point`. Un asistente que descartara en silencio el paso que falta entregaría
una cadena que hace algo distinto de lo que promete su título, y se pagaría antes de
descubrirlo.

## El presupuesto

Dos reglas mantienen honesta la cifra, fijadas por las pruebas de [`hephaestus/tests/estimate.test.ts`](https://github.com/alexar76/hephaestus/blob/main/tests/estimate.test.ts):

1. **Una capacidad sin precio se nombra, nunca se trata como gratuita.** Queda fuera del total y se
   lista aparte: un total que absorbe lo desconocido en silencio no es un presupuesto.
2. **El dinero se suma en micro-dólares enteros.** Los precios reales del catálogo son lecturas de
   sensor de $0.001 y llamadas de oráculo de $0.004; sumar eso en punto flotante deriva justo en los
   dígitos de los que está hecho el total.

Donde el hub enruta hacia un par se usa el precio enrutado: cotizar el precio del proveedor
infravaloraría cada salto federado por la comisión de enrutamiento.

La latencia se informa como el camino más largo por latencia declarada, es decir un **suelo**: hoy el
ejecutor recorre los saltos en secuencia, así que una ejecución real no puede ser más rápida. Las
capacidades que no declaran latencia cuentan como cero y se listan por nombre, de modo que la cifra
nunca se infla con una conjetura.

## Fiabilidad en la que se puede confiar — la regla `reputation_basis`

El manifiesto del hub publica un `success_rate_30d` para cada fila. Para una fila que nadie ha
invocado nunca, ese número es un valor neutro deliberado: el rastreador ignora las tasas de éxito
declaradas por el par, porque un par capaz de declararse un 99 % dominaría el enrutamiento en el
primer indexado.

La consecuencia fue que las 76 filas del catálogo en vivo publicaban `0.5`, y nada en el documento
distinguía un uno-de-dos medido de un marcador de posición no observado. Ahora el manifiesto lleva la
evidencia junto al número:

| Campo | Significado |
|-------|-------------|
| `observations_30d` | Invocaciones que el hub publicador observó en los últimos 30 días. |
| `reputation_basis` | `measured` — la tasa es éxitos/intentos en esa ventana. `unobserved` — nada se ejecutó; la tasa es un marcador de posición. |
| `by_hub[*].trust_basis` | Gemelo por par: `measured`, `unobserved` o `self` para el propio hub publicador. |

**La regla para todo consumidor, incluida nuestra propia interfaz: guiarse por `reputation_basis`,
nunca por el número.** Cuando la base no es `measured`, mostrar «sin llamadas todavía», no una
puntuación. El núcleo descarta el valor en lugar de propagarlo
([`hephaestus/src/catalog.ts`](https://github.com/alexar76/hephaestus/blob/main/src/catalog.ts)), y un hub anterior a estos campos se lee
como `unknown`, que no es lo mismo que malo.

Una vez invocada una capacidad, el manifiesto sirve la tasa **medida**: el comentario del rastreador
siempre dijo que el hub la calcula por sí mismo; nadie lo hacía, así que `0.5` quedó congelado en
cada manifiesto firmado.

## Componibilidad — por qué algunas filas no se pueden conectar

Una capacidad es componible solo si declara campos de entrada (un objeto `properties`, aunque esté
vacío — «no toma nada» es una respuesta) **y** un esquema de salida no vacío. Las filas que fallan en
cualquiera de las dos cosas son descubribles y tienen precio, pero no pueden conectarse a un vecino,
y el estudio lo dice en lugar de dibujar un puerto que no lleva a ninguna parte.

Se cerraron tres huecos del lado de las fuentes para volver componible el catálogo:

* **Platon, 9 capacidades.** El agregador oracle-family federaba Platon solo por identificador,
  descripción y precio, así que cada fila heredaba el valor por defecto «sin campos» de oracle-core,
  mientras que Platon documenta `num_bytes`, `client_seed`, `prompt`, `round`, `question` y el resto.
  Ahora el agregador transmite las declaraciones propias de Platon en lugar de repetirlas: todo lo
  repetido a mano es la deriva que una vez puso `platon.verify@v1` en venta.
* **ATLAS, 6 SKU.** `output_schema` faltaba por completo: seis artefactos de decisión de pago cuya
  forma de resultado un comprador solo podía conocer pagando uno. Ahora los esquemas reflejan lo que
  construyen los manejadores, y la suite valida la salida real contra ellos en ambos sentidos: el
  esquema no puede prometer de más ni quedarse atrás del manejador.
* **Capacidades que realmente no toman entrada** (`platon.state@v1`, `platon.commit@v1`,
  `gaia.fleet.status@v1`) declaran un `properties` explícitamente vacío. Eso es correcto, no roto:
  «no toma nada» y «no lo dice» son estados distintos y el estudio los muestra distinto.

## Qué puede expresar el ejecutor y qué no

El estudio rechaza un grafo que el ejecutor no podría correr, con una razón, en vez de exportar un
JSON que falla luego o —peor— que funciona alimentando un salto desde el ascendiente equivocado.

* **Como máximo 16 capacidades por pipeline** (`PipelineRequest.nodes`). Divide el trabajo mayor en
  etapas.
* **Un solo padre portador de datos por salto.** `input_from` nombra un único nodo, así que solo una
  conexión entrante puede marcarse como fuente de datos; las demás expresan orden.
* **Los saltos corren en secuencia.** La estimación de latencia es un suelo, no un pronóstico.

### `input_from` nombra un nodo

`input_from` está declarado como identificador de nodo y estaba implementado como booleano:
cualquier valor verdadero inyectaba el resultado del salto que terminó último. En una cadena recta
coinciden. En un DAG no: un salto con dos padres recibía el resultado de aquel que el orden
topológico terminó de segundo, de modo que un grafo con convergencia podía dibujarse, presupuestarse,
pagarse y alimentarse del ascendiente equivocado, con una firma válida sobre el bill of materials.

Ahora nombra al padre que quiere decir, y los resultados se guardan por nodo, así que también se
puede nombrar un ascendiente lejano. Un valor que no coincide con ningún nodo conocido conserva el
comportamiento anterior de «último resultado», por lo que quienes ya llamaban no se ven afectados.

## Ejecutar: quién ejecuta y quién paga

Un salto que esta fábrica no aloja se enruta al invoke federado del hub, porque el estudio
compone desde el catálogo del hub —setenta y seis filas, todas de pares— mientras el
ejecutor aloja nueve propias. Antes de ese enrutamiento, todo grafo que un visitante pudiera
construir respondía `404 capability not found`.

Lo que había que decidir era el dinero, no el código:

* **Nunca se adjunta credencial alguna del ejecutor.** Un botón Run sin autenticar que gaste
  el saldo del operador es un grifo abierto, y cada recibo que produjera nombraría al
  comprador equivocado.
* **La identidad de prueba del visitante viaja de extremo a extremo** —navegador → hub →
  ejecutor → hub— como `X-AIMarket-Sandbox-Visitor`. El hub mide un saldo renovable por
  visitante, así que reenviar el id del visitante y no el del servicio es la diferencia entre
  que cada persona tenga su saldo y que todos compartan uno agotado.
* **Un salto que necesita dinero falla como ese salto.** `402` si requiere pago, `429` si el
  saldo está gastado — con el motivo visible, nunca un cargo silencioso. El presupuesto sigue
  diciendo lo que habría costado.
* **El bill of materials registra `payer` por salto** —`local`, `trial`, `channel` o
  `unpaid`— así que una ejecución gratuita nunca es evidencia firmada de una compra.

Más allá del tramo gratuito, un salto se liquida contra un canal de pago que controla quien
llama, y el registro nombra ese canal.

## Leer una ejecución de vuelta

El ejecutor firma un bill of materials por ejecución y lo persiste. Hasta que existieron estas rutas
nada podía leerlo: la atribución de culpa por salto —la evidencia sobre la que se apoya una disputa y
cualquier penalización (slashing) resultante— solo la veía quien hizo el POST original.

| Ruta | Devuelve |
|------|----------|
| `GET /ai-market/pipelines?limit=N` | Ejecuciones recientes como **proyección redactada**: coste, saltos, estado por salto, culpa. |
| `GET /ai-market/pipelines/{trace_id}` | El bill of materials **firmado**, literal. |

La separación es deliberada. Una firma cubre el objeto tal como fue escrito, así que filtrar la
respuesta por identificador devolvería algo no verificable. Enumerar es el problema inverso: un flujo
público de ejecuciones publicaría qué canal de pago financió qué, y los nonces de recibo por salto,
que son claves de búsqueda de recibos públicos con importes. Por eso el listado quita `channel_id` y
`receipt_nonce`, y cada fila indica la ruta a su propio original firmado.

### Culpa

El fallo de un pipeline es culpa del salto que falló, nunca de todo el grafo. El bill of materials
nombra el salto culpable y exonera explícitamente a los saltos previos que hicieron su trabajo, para
que una disputa apunte solo al proveedor responsable:

```json
{
  "policy": "hop-level",
  "at_fault": {"id": "v", "capability_id": "metis.verify@v1", "status_code": 500},
  "not_at_fault": ["s"],
  "not_executed": ["d"]
}
```

## Enviar un grafo

Un plano se convierte en el cuerpo del ejecutor. Solo viajan los nodos de capacidad: disparadores y
salidas son la forma en que una persona lee un lienzo, no saltos que se facturan a nadie:

```json
{
  "nodes": [
    {"id": "s", "product_id": "prod-mcp", "capability_id": "web.search@v1",
     "input": {"query": "a claim"}, "depends_on": []},
    {"id": "v", "product_id": "prod-metis", "capability_id": "metis.verify@v1",
     "input": {"claim": "a claim"}, "depends_on": ["s"], "input_from": "s"}
  ]
}
```

```bash
curl -s -X POST https://magic-ai-factory.com/ai-market/pipelines \
  -H 'content-type: application/json' --data @blueprint.json
```

La respuesta lleva `trace_id`, el `bill_of_materials` firmado y `final_result`.

## Dónde está cada cosa

| Ruta | Qué es |
|------|--------|
| [`hephaestus/src/catalog.ts`](https://github.com/alexar76/hephaestus/blob/main/src/catalog.ts) | Manifiesto → catálogo de capacidades; la regla de reputación |
| [`hephaestus/src/estimate.ts`](https://github.com/alexar76/hephaestus/blob/main/src/estimate.ts) | Presupuesto de coste y latencia |
| [`hephaestus/src/blueprint.ts`](https://github.com/alexar76/hephaestus/blob/main/src/blueprint.ts) | Validación; plano → `PipelineRequest` |
| [`hephaestus/src/wizards.ts`](https://github.com/alexar76/hephaestus/blob/main/src/wizards.ts) | Objetivos → roles → una cadena sobre el catálogo de hoy |
| `alien-monitor/backend/hephaestus_status.py` | Consulta ejecuciones y preparación del catálogo para el nodo |
| `alien-monitor/frontend/src/components/HephaestusRuns.tsx` | El panel de observación |
| `web/backend/services/ai_market_protocol/pipelines.py` | Ejecutor, almacén de trazas, proyección |

El núcleo es sin dependencias y sin DOM a propósito: tiene que servir a la página del estudio y a
cualquier otra superficie que necesite presupuestar o convertir un plano, así que no puede arrastrar
las opiniones de un framework de UI.

```bash
cd hephaestus && npm install && npm run check    # tipos + 57 pruebas
```

## Límites que conviene decir con claridad

* Un presupuesto no es una oferta firme. Los precios vienen de un manifiesto firmado en el momento
  de la lectura y un proveedor puede cambiarlos antes de la ejecución.
* `reputation_basis: measured` significa que alguien invocó la capacidad a través de *este* hub, en
  30 días. Es evidencia, no garantía.
* Un bill of materials firmado prueba lo que registró este ejecutor. No prueba que el resultado fuera
  correcto: para eso existe la capa de verificación.
