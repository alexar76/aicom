# HEPHAESTUS — guía de usuario

> **English:** [hephaestus-user-guide.md](./hephaestus-user-guide.md) · **Русский:** [hephaestus-user-guide.ru.md](./hephaestus-user-guide.ru.md) · **Français:** [hephaestus-user-guide.fr.md](./hephaestus-user-guide.fr.md) · **中文:** [hephaestus-user-guide.zh.md](./hephaestus-user-guide.zh.md)
>
> La página: **[modelmarket.dev/studio](https://modelmarket.dev/studio)** · Cómo funciona por dentro: [hephaestus-studio.es.md](./hephaestus-studio.es.md) · Para qué sirve: [hephaestus-use-cases.es.md](./hephaestus-use-cases.es.md) · **Instalación y capturas:** [hephaestus/README.md](https://github.com/alexar76/hephaestus/blob/main/README.md)

---

## Qué se puede hacer aquí, en un párrafo

Elegir capacidades del mercado, conectarlas, ver cuánto cuesta la cadena **antes** de
ejecutarla, ejecutarla y conservar un registro firmado de lo que pasó — incluido qué paso
es el culpable si alguno falla. Sin cuenta. Las primeras ejecuciones son gratis.

## Abrirla

Entra en **[modelmarket.dev/studio](https://modelmarket.dev/studio)**. No abre con un lienzo
vacío sino con un ejemplo que funciona: dos capacidades ya conectadas, presupuestadas y
listas para ejecutar. La cabecera muestra exactamente la razón de ser de la página:

```
$0.0030 · 2 hops · ≥101 ms          5 free runs left · every hop has an observed success rate
```

* **$0.0030** — lo que cuesta ejecutar este grafo. Sumado de la lista de precios en vivo.
* **2 hops** — los pasos de pago. `Start` y `Result` no son pasos: marcan dónde empieza y
  termina el grafo.
* **≥101 ms** — el suelo, no un pronóstico: hoy los pasos se ejecutan uno tras otro, así que
  una ejecución real no puede ser más rápida.
* **5 free runs left** — tu saldo, contado contra un id aleatorio guardado en este
  navegador. No es una cuenta, y no dice nada sobre ti.

![La página al cargar: catálogo a la izquierda, un grafo de dos saltos, la estimación en la cabecera](https://github.com/alexar76/hephaestus/blob/main/docs/screenshots/opens-on-a-real-chain.png)

*Así se ve la página al cargar: una cadena que ya funciona y ya está tasada.*

## Empezar por un objetivo, no por un identificador de capacidad

Setenta y seis filas con nombres como `gaia.verify@v1` son un catálogo, no una respuesta. Si
lo que se quiere es *una medición que se pueda defender en una discusión*, primero hay que
saber que la lectura y el veredicto sobre ella son dos compras distintas y que una alimenta
a la otra.

El botón **Wizards** de la cabecera enuncia el objetivo en su lugar. Cada entrada muestra la
cadena que construiría con el catálogo de hoy, ya tasada, antes de cargarla:

![El menú de asistentes abierto: dos objetivos con su cadena y su precio, dos con el motivo por el que no se pueden construir](https://github.com/alexar76/hephaestus/blob/main/docs/screenshots/wizards-are-goals.png)

*Objetivos y lo que costaría cada uno; y los dos que el catálogo no satisface hoy.*

Al pulsar uno, su cadena aparece en el lienzo, conectada y rellenada, igual que si se
hubiera montado a mano. Después no queda nada oculto: es un grafo normal que se puede
editar, volver a tasar o descartar.

Los objetivos que el mercado **no** puede satisfacer permanecen en la lista con el motivo
—por ejemplo *«nada de lo que está en venta aquí cubre el paso de un informe que acepte una
ubicación»*. No es un error suyo: es un hueco en lo que se vende ahora, y conviene saberlo
antes de planificar una compra alrededor.

Dos cosas que un asistente nunca hará. No acortará una cadena para que el objetivo parezca
alcanzable: si un paso no tiene candidato, el objetivo entero queda no disponible. Y no
conectará dos saltos solo porque comparten el nombre de un campo: un salto tiene que
consumir el *resultado* del anterior y, cuando hay material criptográfico, del mismo
proveedor. Ambas reglas existen porque el catálogo contiene de verdad pares que parecen
conectables y no lo son.

## Los tres paneles

| Panel | Para qué es |
|-------|-------------|
| **Catálogo** (izquierda) | Todas las capacidades en venta: identificador, precio y cuánta evidencia respalda su fiabilidad. Filtra por id o descripción. Haz clic para añadir. |
| **Lienzo** (centro) | El grafo. Arrastra para mover; desde el punto bajo un módulo al punto sobre otro para conectar. Un clic en la conexión alterna si lleva datos. |
| **Parámetros / Comprobaciones / Última ejecución** (derecha) | Los campos del módulo seleccionado, todo lo que va mal en el grafo y lo que devolvió la última ejecución. |

En un móvil los tres pasan a mostrarse uno a la vez, conmutados desde la barra inferior.

<p>
  <img src="../hephaestus/docs/screenshots/mobile-canvas.png" alt="La página a 390px: el grafo" width="220">
  <img src="../hephaestus/docs/screenshots/mobile-catalogue.png" alt="La pestaña de catálogo a 390px" width="220">
</p>

*La misma página a 390px: «Catálogo» y «Lienzo» se cambian desde la barra inferior.*

## Leer una fila del catálogo

```
gaia.weather.read@v1
$0.0010   127 calls (30d), 99.2% ok
```

El precio es lo que se te cobrará, incluida cualquier comisión de enrutamiento. La segunda
línea es **evidencia, no una calificación**: aparece solo si alguien invocó de verdad esa
capacidad a través de este hub en los últimos treinta días. Cuando nadie lo ha hecho, dice
**«no calls yet»** — y ese es el estado honesto de 49 de las 76 filas de hoy. No es una mala
puntuación: es ninguna puntuación.

Una fila puede aparecer atenuada con un motivo como *«declares no output schema — nothing
downstream can use it»*. Esas no se pueden conectar a nada, y la página lo dice en lugar de
dejarte dibujar un puerto que no lleva a ninguna parte.

## Rellenar parámetros

Selecciona un módulo. Sus campos son exactamente los que publicó el proveedor, nada
inventado. Los obligatorios llevan `*`. Algunas capacidades no toman entrada alguna y lo
dicen.

**Un campo puede leer de un paso anterior en vez de un literal.** Escribe:

```
${read.reading}
```

y en ejecución el valor viene del paso llamado `read`. `${read}` entrega el resultado
completo de ese paso; `${read.reading.values.temperature_c}` entra dentro de él; `seen at
${read.ts}` lo coloca dentro de una frase. Esto es lo que convierte una cadena en un
pipeline en lugar de una lista de llamadas separadas, y es lo que demuestra el ejemplo
inicial.

Una referencia se comprueba antes de poder ejecutar: debe nombrar un paso del lienzo, no a
sí misma, y uno que con certeza se ejecute antes. Si no puede, **Comprobaciones** dice cuál
y por qué.

![El verificador seleccionado; sus campos reading y attestation contienen ${read.reading} y ${read.attestation}](https://github.com/alexar76/hephaestus/blob/main/docs/screenshots/references-in-the-fields.png)

*Un campo que lee de un salto anterior. El panel de comprobaciones dice qué campo va a dónde.*

## Comprobaciones

Todo lo que impediría ejecutar el grafo, en una lista y en palabras normales:

* `"gaia.verify@v1" needs "reading" (object)` — un campo obligatorio está vacío.
* `"Start" is not connected to anything` — un módulo inalcanzable.
* `Pipelines take at most 16 capabilities` — el límite del ejecutor; divide el trabajo.
* `"check" is fed by 2 connections at once` — un paso recibe datos de un solo paso anterior;
  marca una única conexión como fuente de datos.

Las advertencias son amarillas y no bloquean: una capacidad sin precio publicado, o que no
declara qué devuelve, sigue siendo usable — simplemente sabes menos de ella.

## Ejecutar

**Run** envía el grafo. Lo que vuelve es un registro real, no un resumen:

```
tr_c87f3be013e4
$0.0030 · 2 hops · 771 ms
✓ gaia.weather.read@v1 · $0.0010
✓ gaia.verify@v1 · $0.0020
signed bill of materials →
```

Sigue el enlace para el original firmado: el mismo documento en el que se apoyaría una
disputa. Si un paso falla, el registro nombra al paso culpable y exonera explícitamente a
los que hicieron su trabajo:

```
at fault: gaia.verify@v1 (HTTP 500) · cleared: read
```

**Copy request** copia el JSON exacto al portapapeles, para ejecutar el mismo grafo desde
una terminal, un job de CI o tu propio agente. La página es una comodidad, no una puerta.

![Una ejecución terminada: identificador de traza, los dos saltos con su precio y el veredicto](https://github.com/alexar76/hephaestus/blob/main/docs/screenshots/signed-bill-of-materials.png)

*Tras ejecutar: el identificador de traza, cada salto con lo que costó y el veredicto del verificador.*

## Cuánto cuesta y quién paga

* **Ejecuciones gratis.** Cada visitante recibe un saldo pequeño y renovable, contado contra
  el id aleatorio de este navegador. Si borras el almacenamiento, eres un visitante nuevo con
  saldo nuevo: es una prueba, no una frontera de seguridad.
* **Qué excluye el tramo gratuito.** Las capacidades que componen su respuesta con un modelo
  de pago gastan presupuesto real en cada llamada, así que no son gratis. Esos pasos vuelven
  pidiendo pago.
* **A nadie se le cobra en silencio.** Sin saldo y sin un canal propio, un paso de pago falla
  con un motivo. El presupuesto sigue diciéndote lo que habría costado.
* **Pagar de verdad.** Más allá del tramo gratuito, un paso necesita un canal de pago que
  controles tú. Las ejecuciones se liquidan contra él, y el registro nombra el canal en vez
  del servicio que reenvió tu petición.

## Límites que conviene saber antes de construir

* **16 capacidades** por ejecución.
* **Una fuente de datos por paso** — puede que varios pasos deban terminar antes, pero solo
  uno entrega su resultado.
* **Los pasos van uno tras otro.** La cifra de latencia es un suelo.
* **Un presupuesto no es una oferta firme.** Los precios vienen de una lista firmada en el
  momento de leerla, y un proveedor puede cambiarlos antes de que ejecutes.
* **Un registro firmado prueba lo que hizo el ejecutor, no que la respuesta sea correcta.**
  Que el resultado sea *cierto* es tarea de las capacidades de verificación — y puedes poner
  una en el grafo, que es justo lo que hace el ejemplo inicial.

## Si algo parece raro

| Lo que ves | Qué significa |
|------------|---------------|
| `no calls yet` en todas las filas | Nadie invocó esas capacidades por este hub en treinta días. Honesto, no roto. |
| Un paso falla con `402` | Necesita pago y no hay canal adjunto. |
| Un paso falla con `429` | Tu saldo gratuito está agotado por ahora; se renueva. |
| `unresolved reference: …` | El paso anterior se ejecutó pero no devolvió el campo que referenciaste. Su esquema de salida dice qué sí devuelve. |
| `executor_not_configured` | Este despliegue no tiene ejecutor de pipelines. Lo arregla un operador, no tú. |
| El catálogo está vacío | La página no pudo leer el manifiesto del hub. Como la sirve el propio hub, suele significar que el hub no está alcanzable. |
