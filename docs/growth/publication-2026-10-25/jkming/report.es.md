# Estudio de umbrales de WARDEN: conservar 8/10 y corregir el índice de credenciales

**Divulgación:** mantengo WARDEN en el ecosistema alexar76. El experimento, el análisis y este informe se prepararon con ayuda sustancial de IA generativa. Es una evaluación de nuestro propio código realizada por su mantenedor con casos construidos, no una auditoría independiente ni una medición del tráfico de producción.

Fecha: 2026-10-25. **Estado: el cambio final del código es local y aún no se ha publicado como versión.**

## Pregunta y decisión

[jkming preguntó](https://dev.to/alexar76/we-attacked-our-own-mcp-firewall-with-its-source-code-open-14-of-17-attacks-got-through-now-2-of-2m7l#comment-3ion2) si WARDEN debería reconocer fragmentos de secretos más cortos dentro de otras palabras. Comparamos ventanas no hexadecimales de 6, 7 y 8 caracteres; la ventana hexadecimal se mantuvo en 10 en todos los casos.

Conservamos 8/10 y corregimos un defecto de indexación más específico. Mejoró el reconocimiento sin cambiar las decisiones de la muestra de solicitudes ordinarias. **No** permite detectar de forma fiable un fragmento de 6 caracteres incrustado en otra palabra.

## Resultados del guard completo

`ask` pausa la ejecución hasta que el operador la apruebe; `deny` la rechaza; `pass` permite atravesar este guard. Tras leer una credencial y texto externo, el guard evaluado exige aprobación para las llamadas salientes/MCP compatibles, salvo que exista una regla exacta para una solicitud pública revisada de forma independiente. No se enviaron solicitudes reales.

| Variante | Solicitudes de ataque | `pass` | `ask` | `deny` |
| --- | ---: | ---: | ---: | ---: |
| Original, 6 | 14,400 | 0 | 7,145 | 7,255 |
| Original, 7 | 14,400 | 0 | 10,464 | 3,936 |
| Original, 8 | 14,400 | 0 | 11,555 | 2,845 |
| Final, 8 | 14,400 | 0 | 10,838 | 3,562 |

La corrección trasladó 717 solicitudes de `ask` a `deny`: 342 casos de tipo Stripe y 375 de tipo GitHub. **No fueron 717 transmisiones automáticas adicionales evitadas**: la aprobación ya las detenía. Se conservaron todos los rechazos anteriores.

Sin la barrera general de credenciales, el detector final de fugas/fragmentos por sí solo no encontró coincidencias en 8,709 solicitudes de ataque. Reconocer huellas no sustituye esa barrera.

## Solicitudes ordinarias y controles de coincidencias

Hubo 7,680 solicitudes ordinarias distintas, cada una probada en ambos perfiles. En el perfil estricto predeterminado, todas las variantes pidieron aprobación para las 7,680. Con reglas exactas y revisadas para solicitudes públicas, las 7,680 pasaron sin preguntas adicionales ni rechazos. Son las mismas entradas en dos perfiles, no muestras independientes. El perfil predeterminado sigue exigiendo un trabajo considerable de revisión.

El escaneo directo con 480 credenciales de calibración abarcó 3,575 archivos públicos únicos, 39,259 extractos y 22,056,276 letras y dígitos normalizados. La ventana 6 produjo 79 coincidencias exactas de subcadenas en 31 extractos; las ventanas 7, 8 y la final 8 no produjeron ninguna. Son coincidencias de subcadenas, no colisiones de hashes truncados ni una tasa de falsos positivos por llamada.

Reprodujimos los 31 pares coincidentes de credencial/extracto mediante el hook real con reglas exactas para solicitudes públicas. La ventana 6 rechazó erróneamente los 31; las demás variantes permitieron 29 y pidieron aprobación para 2. Estos controles se seleccionaron deliberadamente por coincidir; sus proporciones no estiman tasas de la población.

Otro contraejemplo conocido reprodujo un rechazo erróneo con 7: texto ordinario de JSON/comprobación de estado contenía `mit3okt` tras normalizarlo, coincidiendo con una credencial sintética de tipo PEM. Las ventanas 6 y 7 lo rechazaron; la original y la final 8 lo permitieron. Por tanto, cero coincidencias en el corpus nuevo no demuestra que sea seguro implantar 7.

## Corrección del índice

El índice anterior omitía todas las letras iniciales hasta el primer dígito. Por ello, una clave con prefijo de proveedor y dígitos cerca del final podía carecer de ventanas válidas de 8 caracteres. El cambio final empieza antes tras los prefijos de proveedor reconocidos, conservando la condición de combinar letras y dígitos y las exclusiones existentes para DER y valores genéricos.

Descartamos una variante más amplia: tras leer `AcmeIntegrationToken2026`, rechazaba erróneamente el texto público revisado `Public build Token2026`. La versión final conserva la decisión original en ese control.

Se conservaron todas las huellas anteriores de las 960 credenciales: 0 perdidas, 70,466 → 71,612 entradas, con ampliación para 279 credenciales. Las sesiones existentes necesitan releer la credencial para obtener las ventanas nuevas. En 960 casos embedded-6, la versión final 8 siguió produciendo 960 solicitudes de aprobación y 0 rechazos.

## Método y limitaciones

Usamos 960 credenciales sintéticas de ocho formatos y dos semillas deterministas, con 15 ataques por credencial. Las particiones del corpus no se solapaban entre semillas. Las posiciones de ataque ejercitaban deliberadamente el defecto del índice; las proporciones observadas dependen de los casos construidos.

Todas las mediciones empíricas del corpus y del guard se ejecutaron en contenedores Docker Linux restringidos y sin red, **sin gVisor**. Por separado, pasaron 1,156 pruebas de código locales en macOS. El gate existente incluyó 26 ataques con herramientas, con 0 completamente entregados, más 2 escenarios de solo respuesta. Estas comprobaciones respaldan la corrección específica y los umbrales conservados; no establecen seguridad universal ni una tasa de falsos positivos en producción.
