# Comprobar una cesta con n8n y un hub propio

[English](n8n-workshop.md) · [Русский](n8n-workshop.ru.md) · [Español](n8n-workshop.es.md) · [Français](n8n-workshop.fr.md) · [中文](n8n-workshop.zh.md)

Taller práctico en línea de 60 minutos para integradores de n8n y propietarios de pequeñas
API. Crearemos un servicio de solo lectura: **«¿Puede este proveedor preparar mi cesta y
cuál es el subtotal de los productos?»** El operador conserva el control del workflow y del
catálogo. El ejercicio local no requiere compras, cartera, LLM de pago ni clientes externos.

## Por qué este caso

Un asistente de tienda, de ventas o de compras consulta las mismas reglas del proveedor.
n8n ejecuta las reglas; Hub publica el servicio y verifica las respuestas firmadas.
n8n ya ofrece [MCP nativo](https://n8n.io/mcp/), que puede bastar para conectar un agente propio.
Aquí añadimos un catálogo operado de forma independiente, firmas del proveedor y una posible
integración posterior con la federación.

El inventario es **sintético**: demuestra la integración, no existencias reales, demanda
comercial ni una instalación de producción. Hub es gratuito; el operador paga su alojamiento
y n8n tiene su propia licencia. La federación es un canal potencial de distribución.

## Ejemplo y resultados

[Workflow importable](../examples/n8n-order-check/workflow.json) ·
[Código y detalles](../examples/n8n-order-check/README.md) ·
[Validación](../examples/n8n-order-check/VALIDATION.md)

```json
{"items":[{"sku":"BEANS-250","quantity":2},{"sku":"MUG-BLUE","quantity":1}]}
```

Resultado: `status: ready`, `can_fulfill: true`, `subtotal_minor: 3430`, `currency: USD`.
Son 34,30 USD solo en productos. Impuestos, envío y total final son `null`: no calculados.
La respuesta incluye `demo: true`, `reservation_created: false`, `order_created: false`.

| Solicitud | Resultado esperado |
|---|---|
| Dos BEANS-250 y una MUG-BLUE | Disponible; subtotal 3430 |
| Cuatro MUG-BLUE | Stock insuficiente; hay tres |
| SKU desconocido | Producto desconocido; subtotal no disponible |
| Dos líneas de dos MUG-BLUE | Se agregan a cuatro; stock insuficiente |
| Cesta vacía o cantidad negativa/fraccionaria | Entrada rechazada |
| Credencial incorrecta / n8n no disponible | Rechazo / error; sin cotización inventada |

`evaluated_at` indica cuándo se ejecutó la consulta, no la actualidad del inventario.
La firma autentica la declaración y la vincula a la solicitud; no demuestra que exista el stock.

## Preparación previa

Instancia local separada, Python 3.11+, Node.js 24.14.0 y puertos libres 15678/13456/19083.
Desde la raíz de un clon de este repositorio:

```bash
python3 -m venv examples/n8n-order-check/.venv
examples/n8n-order-check/.venv/bin/python -m pip install -e './aimarket-hub[pqc]'
cd examples/n8n-order-check
source .venv/bin/activate
npm install --prefix .runtime/npm n8n@2.43.7 --no-audit --no-fund
export PATH="$PWD/.runtime/npm/node_modules/.bin:$PATH"
python run.py init
python run.py n8n-import
```

La instalación se hace antes del taller. `.runtime/` contiene claves y secretos generados y
está excluido de Git; no lo comparta. El workflow usa una credencial Header Auth, sin tokens
incrustados. Detenga la instancia de n8n del taller antes de repetir la importación.

En tres terminales, entre en el directorio del ejemplo y active `.venv`. Ejecute respectivamente
`python run.py n8n`, `python run.py adapter` y `python run.py hub`. Repita el export de PATH
en la terminal de n8n. Editor: `http://127.0.0.1:15678`; cree una cuenta local de propietario
si se solicita. La importación publica el workflow; se utiliza `/webhook/`. Ctrl+C detiene
los servidores y conserva los datos locales.

## Sesión de 60 minutos

| Minutos | Actividad |
|---|---|
| 0–5 | Operador, consumidor, resultado de solo lectura y datos sintéticos |
| 5–15 | Webhook → Code → Respond to Webhook; llamada autenticada |
| 15–25 | Esquema de entrada, SKU duplicados, stock y precios |
| 25–40 | Adaptador y Hub; invocación, resultado y firmas |
| 40–50 | Faltantes, SKU desconocido, cantidad y credencial incorrectas |
| 50–60 | Sustituir la muestra por una fuente autorizada; preguntas |

Antes de probar, espere a que n8n indique que el editor está disponible y la indexación de workflows ha terminado.

```bash
curl --fail-with-body http://127.0.0.1:19083/ai-market/v2/invoke \
  -H 'Content-Type: application/json' --data-binary @request.json
python run.py check
node test_quote.cjs
```

Cliente MCP local: `http://127.0.0.1:19083/mcp`. Instrucción:
«Busca la herramienta de comprobación de cesta del taller. Consulta dos BEANS-250 y una
MUG-BLUE. Indica el subtotal, los faltantes y que son datos sintéticos. No hagas un pedido».
Un cliente exclusivamente en la nube no llega al loopback del portátil. Las pruebas HTTP/MCP
no validan por sí solas todos los clientes de agentes.

## Primer operador real

Solicite una respuesta de catálogo anonimizada y una fuente autorizada por el propietario.
Sustituya los datos de muestra por lectura de moneda, precios en unidades menores, stock
disponible y fecha de observación; establezca un límite de antigüedad. Actualice conjuntamente
el contrato de respuesta del adaptador y las pruebas. Reservas y pedidos son operaciones
separadas. Los precios privados requieren autorización del consumidor y aislamiento entre clientes.

Para uso público: claves y base de datos persistentes, HTTPS y límites de solicitudes;
n8n y adaptador privados y autenticados. No reutilice la configuración HTTP del laboratorio.
Siga la [guía del operador](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.es.md), ejecute
`aimarket doctor` y decida si anunciarse. El éxito local no equivale a admisión en la federación.

El objetivo es que el propietario independiente controle la instalación y las claves, repita
una llamada útil y sepa detenerla. Registre por separado el ejercicio local, los datos reales,
la admisión y el uso tras siete días. No se exige ninguna venta externa.
