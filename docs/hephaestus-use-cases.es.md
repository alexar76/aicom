# HEPHAESTUS — casos de uso

> **English:** [hephaestus-use-cases.md](./hephaestus-use-cases.md) · **Русский:** [hephaestus-use-cases.ru.md](./hephaestus-use-cases.ru.md) · **Français:** [hephaestus-use-cases.fr.md](./hephaestus-use-cases.fr.md) · **中文:** [hephaestus-use-cases.zh.md](./hephaestus-use-cases.zh.md)
>
> Cómo manejar la página: [hephaestus-user-guide.es.md](./hephaestus-user-guide.es.md) · Cómo funciona por dentro: [hephaestus-studio.es.md](./hephaestus-studio.es.md) · **Instalación y capturas:** [hephaestus/README.md](https://github.com/alexar76/hephaestus/blob/main/README.md)

---

Cada cadena de abajo está construida con capacidades que están en venta **hoy** — 76 filas
entre GAIA, la familia de oráculos y ATLAS — con los precios que publica la lista en vivo. El
JSON es lo que da `Copy request`, así que cada una se ejecuta sin cambios desde una terminal
o desde un agente.

---

## 1. Una lectura de sensor que puedes defender

**Para quién:** cualquiera cuya decisión se apoye en un número del dispositivo de otro.
**Coste:** $0.0030 · **2 saltos** · cubierto por el tramo gratuito.

Una lectura por sí sola es una afirmación. Esta cadena compra la lectura y después compra una
segunda opinión sobre ella — de un verificador estadístico que comprueba límites, ritmo de
cambio y concordancia con dispositivos hermanos — y guarda un registro firmado de ambos pasos.

```json
{"nodes": [
  {"id": "read", "product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1",
   "input": {}, "depends_on": [], "source_hub": "https://iot.modelmarket.dev"},
  {"id": "check", "product_id": "gaia.gateway", "capability_id": "gaia.verify@v1",
   "input": {"reading": "${read.reading}", "attestation": "${read.attestation}"},
   "depends_on": ["read"], "source_hub": "https://iot.modelmarket.dev"}
]}
```

Lo que vuelve es un veredicto, no una impresión:

```json
{"verified": false, "score": 0.6667, "summary": "failed: sibling:pressure_hpa",
 "checks": [{"name": "known_device", "ok": true}, {"name": "device_attestation", "ok": true}]}
```

**Por qué vale dinero:** el verificador discrepó del sensor y dijo qué comprobación falló. Esa
es la diferencia entre «teníamos una lectura» y «teníamos una lectura y sabíamos cuánto
fiarnos». Es la cadena con la que abre el estudio.

---

## 2. Un sorteo en el que no hay que confiar en nadie

**Para quién:** quien organiza una lotería, una asignación, una muestra de auditoría aleatoria.
**Coste:** ~$0.0060 · **2 saltos**.

`platon.random@v1` devuelve bytes aleatorios con prueba de reproducibilidad y firma Ed25519;
`chronos.eval@v1` es una función de retardo verificable — prueba de que pasó tiempo secuencial
real. Encadenarlas da un sorteo que no se puede volver a tirar a posteriori ni pudo calcularse
antes de tiempo.

```json
{"nodes": [
  {"id": "seed", "product_id": "prod-platon", "capability_id": "platon.random@v1",
   "input": {"num_bytes": 32}, "depends_on": [],
   "source_hub": "https://oracles.modelmarket.dev/family"},
  {"id": "delay", "product_id": "prod-chronos", "capability_id": "chronos.eval@v1",
   "input": {"seed": "${seed.random_hex}", "difficulty": 200},
   "depends_on": ["seed"], "source_hub": "https://oracles.modelmarket.dev/family"}
]}
```

**Por qué vale dinero:** publicas la traza y los participantes comprueban el sorteo ellos
mismos. No estás pidiendo que te crean.

---

## 3. Ensayar el coste antes de comprometerse con un diseño

**Para quién:** quien tiene que responder «¿cuánto costará este pipeline a un millón de
llamadas?».
**Coste:** $0 — nunca pulsas Run.

Monta el grafo que estás considerando. La cabecera da el precio por ejecución según la lista
firmada, desglosado por salto, más un suelo de latencia. Multiplica por tu volumen. Cambia un
salto por un proveedor más barato y observa cómo se mueve la cifra.

Dos cosas que el presupuesto se niega a hacer, y por eso sirve:

* una capacidad sin precio se **nombra**, nunca se cuenta como gratis;
* el dinero se suma en micro-dólares enteros, porque un catálogo de lecturas de $0.001 no
  sobrevive intacto a la suma en punto flotante.

**Por qué merece la pena:** la respuesta es defendible. Sale de precios que un par firmó, no
de una hoja de cálculo que alguien escribió.

---

## 4. Evidencia para una disputa

**Para quién:** cualquiera que pague a varios proveedores en un mismo flujo.
**Coste:** la ejecución que ya hiciste.

Cuando una cadena falla, el bill of materials firmado nombra el salto culpable y **exonera
explícitamente** a los que hicieron su trabajo:

```json
{"policy": "hop-level",
 "at_fault": {"id": "check", "capability_id": "gaia.verify@v1", "status_code": 500},
 "not_at_fault": ["read"], "not_executed": []}
```

Cada salto registra además quién pagó por él — `trial`, `channel` o `local` — así que una
ejecución gratuita nunca se confunde con una compra.

**Por qué vale dinero:** sin culpa por salto, una cadena fallida es una factura y una
discusión. Con ella, el proveedor de aguas arriba cobra, el que falló queda identificado, y
hay un documento firmado que señalar. La escalera de penalizaciones del ecosistema lee
exactamente esto.

---

## 5. Averiguar si una capacidad merece la compra

**Para quién:** un integrador que elige entre ofertas.
**Coste:** gratis, dentro del saldo.

El catálogo publica, por fila: precio, latencia declarada, si declara siquiera su entrada y
salida, y cuánta evidencia respalda su fiabilidad. Hoy son **27 filas con tasa de éxito medida
y 49 sin ninguna** — y para el segundo grupo la página dice «no calls yet» en vez de mostrar
un valor de relleno como si fuera una puntuación.

Añade la fila, rellena sus campos, ejecútala una vez con el tramo gratuito, lee el resultado
real. Y decide.

**Por qué merece la pena:** evalúas con tu propia entrada, no con una demo que eligió el
vendedor, y en un minuto descubres si el esquema coincide con la realidad.

---

## 6. Entregar un grafo a tu propio agente

**Para quién:** quien construye un agente que debería comprar trabajo en lugar de simularlo.
**Coste:** lo que cueste el grafo, en tu canal.

Monta y comprueba el grafo a mano, pulsa **Copy request** y pega el JSON en tu agente. Envía el
mismo cuerpo al ejecutor y recibe el mismo registro firmado. El estudio es donde una persona
razona sobre la forma; el agente la ejecuta mil veces.

```bash
curl -s -X POST https://magic-ai-factory.com/ai-market/pipelines \
  -H 'content-type: application/json' --data @graph.json
```

**Por qué merece la pena:** lo que probaste es byte a byte lo que se ejecuta.

---

## Para qué NO sirve

* **Un motor de flujos genérico.** No hay bucles, ramas, reintentos ni nodos HTTP, y añadirlos
  cambiaría la única ventaja que hay aquí: que cada nodo es una fila de mercado con precio y
  verificable.
* **Una herramienta de transformación de datos.** Los valores se hilan entre saltos con
  `${hop.field}`, no se reforman. La transformación es una capacidad que alguien vende.
* **Un lugar para secretos.** Los campos viajan al proveedor. No escribas en un campo nada que
  no le entregarías directamente.
* **Prueba de que una respuesta es cierta.** Un registro firmado prueba lo que hizo el
  ejecutor. Si el resultado es correcto es cosa de un salto de verificación: ver el primer caso.
