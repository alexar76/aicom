# Jurado de tres o de cinco — con mediciones

> 🌐 [English](jury-3-vs-5.md) · [Русский](jury-3-vs-5.ru.md) · **Español** · [Français](jury-3-vs-5.fr.md) · [中文](jury-3-vs-5.zh.md)

Las mismas 24 comprobaciones (12 tareas × una respuesta honesta y otra sutilmente errónea:
factorización, ordenación, una suma, millas → km, días entre fechas, campos JSON obligatorios,
contar vocales, invertir una cadena, primalidad, una traducción, una capital) pasaron una vez por el
jurado de cinco asientos de Metis el 2026-10-03. Los jurados menores se calculan con los mismos
votos de cada jurado y la regla del propio jurado (mayoría estricta de todo el jurado, abstención =
sin voto, puntuación = acuerdo × confianza mediana, umbral 0.7), así que solo cambia la composición.
Script: [`metis/bench/jury_3v5.py`](https://github.com/alexar76/metis/blob/main/bench/jury_3v5.py); votos en bruto:
[`metis/bench/results/2026-10-03-jury-3v5.json`](https://github.com/alexar76/metis/blob/main/bench/results/2026-10-03-jury-3v5.json).

| Composición | Decisiones correctas | Indeterminado | Decisiones erróneas | Espera, mediana / máx. (s) |
|---|---|---|---|---|
| 3 asientos, un linaje (DeepSeek, MiniMax, GLM) | 20/24 | 4 | 0 | 7.1 / 52.4 |
| 3 asientos, tres linajes (DeepSeek, Claude, Mistral) | 16/24 | 8 | 0 | 3.7 / 29.2 |
| 5 asientos (todos) | **21/24** | **3** | **0** | 7.1 / 52.4 |

| Jurado | Votos erróneos de 24 |
|---|---|
| Claude Sonnet 5.5 (Anthropic) | 0 |
| DeepSeek V4 Pro | 1 |
| GLM-5.3 (Zhipu) | 1 |
| MiniMax M3 | 2 |
| Mistral Medium 3.5 | 6 |

**Qué muestra**

- **Ninguna composición tomó una decisión errónea.** El desacuerdo deja el veredicto indeterminado
  (se reembolsa al comprador, no se culpa al vendedor); nunca lo invierte.
- **Cinco asientos deciden más a menudo** (21/24): un voto erróneo ya no bloquea el veredicto.
- **La diversidad solo ayuda si cada jurado es fuerte.** El trío de tres linajes fue el peor (16/24)
  porque Mistral Medium 3.5 votó mal 6 veces, sobre todo aceptando respuestas erróneas (una suma con
  un error de uno, un factor equivocado, un recuento de vocales erróneo, «97 no es primo»). En un
  jurado de cinco los demás lo superan; en uno de tres bloquea cada decisión con la que discrepa.
- El jurado más lento marca la espera: GLM-5.3 tardó hasta 52 s en una factorización difícil;
  Claude y Mistral nunca más de 9 s.

**Salvedades.** 24 comprobaciones, una ejecución, solo tareas comprobables; una tarea (campos JSON)
es discutible: su respuesta honesta inventa una dirección de correo y dos jurados objetaron. Tome
estas cifras como orientativas, no como un ranking.

**Siguiente paso.** Sustituir el asiento de Mistral Medium por un modelo más fuerte de otro linaje
(por ejemplo Mistral Large o Gemini) y repetir las mismas 24 comprobaciones: el script lo convierte
en una comparación de dos minutos.

## Sustitución del asiento débil (el mismo día)

| Candidato al quinto asiento | Votos erróneos | Abstenciones | 5 asientos: correctas | Resultado |
|---|---|---|---|---|
| Mistral Medium 3.5 | 6 / 24 | 0 | 21/24 | débil: aceptaba respuestas erróneas |
| Mistral Large 2512 | 1 / 2 respondidas | 22 (`rate_limit` en el proveedor) | 20/24 | no disponible: un jurado que no puede responder se abstiene |
| **Gemini 3.8 Flash** | **1 / 24** | **0** | **22/24** | **se queda** (el trío de tres linajes DeepSeek + Claude + Gemini también 22/24) |

Cada candidato pasó las mismas 24 comprobaciones con ids de auditoría nuevos; los votos en bruto están en `metis/bench/results/`. Dos lecciones: **mida a un jurado antes de confiar en él** (un modelo de nombre ilustre puede ser el voto más débil) y **la disponibilidad forma parte de la calidad**: un jurado limitado por cuota se abstiene en cada minuto de carga. Con este cambio el jurado perdió su linaje europeo: ahora abarca laboratorios chinos (DeepSeek, MiniMax, GLM) y estadounidenses (Anthropic, Google). Entre ejecuciones el mismo trío varió en una decisión (20 → 21/24): con 24 comprobaciones, una diferencia de uno es ruido.

## Nueva prueba: Mistral con razonamiento activado

El primer veredicto sobre Mistral Medium 3.5 era sospechoso: respondía en un segundo mientras los
demás pensaban 3–50 s, así que pudo perder por el *modo* y no por el modelo. Los jurados de Metis
ganaron `extra_body` (se fusiona en cada petición; no puede sustituir el modelo ni los mensajes) y
Mistral se volvió a ejecutar como sexto asiento con `reasoning: {effort: medium}` de OpenRouter y
luego `{effort: high}`.

| Mistral Medium 3.5 | Votos erróneos | Respuesta mediana | Tokens de salida |
|---|---|---|---|
| sin razonamiento | 6 / 24 | 1.1 s | — |
| `reasoning: medium` | 7 / 24 | 1.2 s | ~105 |
| `reasoning: high` | 6 / 24 | 1.1 s | ~100 |

El interruptor funciona —ante una pregunta corta directa el mismo modelo gastó 273–2143 tokens
razonando—, pero dentro del jurado, donde la respuesta debe ser un único veredicto JSON estricto,
apenas piensa incluso en `high` y sigue aceptando respuestas erróneas. Un jurado que no recalcula
es un jurado débil para cálculos, sea cual sea su fama en benchmarks. **Decisión: Gemini 3.8 Flash
conserva el quinto asiento; Mistral sale.**

**Corrección a las tablas anteriores.** La tarea «¿cuántos días hay del 2026-01-01 al 2026-03-14?»
era ambigua: contando ambos extremos salen 73, la respuesta «errónea», y cinco jurados la aceptaron.
Ahora se formula como «¿cuántos días después del 2026-01-01 cae el 2026-03-14?». Dejando fuera el
par original, ninguna composición tomó una decisión errónea en ninguna ejecución. Con el conjunto
corregido, la composición final —DeepSeek, MiniMax, GLM, Claude, Gemini— decide **23 de 24, ninguna
errónea**; el trío DeepSeek + Claude + Gemini decide 22 de 24 con la espera más corta (mediana 5.4 s).
