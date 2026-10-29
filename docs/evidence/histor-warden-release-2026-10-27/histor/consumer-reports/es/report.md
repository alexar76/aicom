# Investigación semanal — ejemplo sintético

Análisis de definiciones guardadas y comprobaciones de sus flujos de trabajo.

| Dependencia | Resultado | Flujos que comprobar |
|---|---|---|
| demo:research | Cambios observados | 2 |
| demo:migration | Cambiaron las condiciones de observación | 1 |
| demo:offline | Datos insuficientes | 1 |

## demo:research

**Cambios observados**

- Antes: 2026\-10\-26T09:00:00Z; versión del paquete 1\.0\.0; versión del servidor 1\.0\.0; protocolo 2025\-06\-18.
- Después: 2026\-10\-27T09:00:00Z; versión del paquete 1\.1\.0; versión del servidor 1\.1\.0; protocolo 2025\-06\-18.


### Leer documentos de archivo

Se requiere una nueva prueba.

- [ ] legacy\_fetch: Compruebe una alternativa o fije el paquete anterior; revise el flujo antes de ejecutarlo\.

### Preparar la revisión semanal de documentos

Se requiere una nueva prueba.

- [ ] export\_brief: Compruebe las confirmaciones, los permisos y los precios anunciados; las annotations son declaraciones del servidor\.
- [ ] search\_docs: Lea las instrucciones modificadas; repita una petición habitual y compruebe la selección de herramientas\.
- [ ] search\_docs: Compruebe las entradas guardadas, los campos obligatorios y los tipos; añada un caso límite\.
- [ ] search\_docs: Repita el procesamiento del resultado: compruebe los campos y tipos que lee el flujo\.

### Cambios en las herramientas seleccionadas

**export\_brief: Modificada**

- destructiveHint: false → true. Es una declaración del servidor.
- readOnlyHint: true → false. Es una declaración del servidor.

**legacy\_fetch: Eliminada**


**search\_docs: Modificada**

- Nuevos campos obligatorios: workspace
- Cambios de type: $/properties/limit, $/properties/workspace
- inputSchema: $\.&quot;properties&quot;\.&quot;limit&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;workspace&quot;\.&quot;type&quot;, $\.&quot;required&quot;\[1\]
- outputSchema: $\.&quot;properties&quot;\.&quot;items&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;results&quot;\.&quot;type&quot;
- Descripción eliminada: “using”
- Descripción añadida: “in”
- Descripción eliminada: “query\.”
- Descripción añadida: “selected workspace\. Include source links in the result\.”

Tamaño del JSON presentado al modelo en UTF-8: lista completa 534 → 627 bytes; herramientas seleccionadas 534 → 451 bytes.
No son tokens ni ahorro conseguido.

## demo:migration

**Cambiaron las condiciones de observación**

- Antes: 2026\-10\-26T09:00:00Z; versión del paquete no corresponde; versión del servidor 1; protocolo 2025\-06\-18.
- Después: 2026\-10\-27T09:00:00Z; versión del paquete no corresponde; versión del servidor 2; protocolo 2026\-07\-28.

- Condiciones distintas: protocol; las diferencias no se pueden atribuir solo a la actualización del paquete.

### Comprobar el estado del servicio tras la migración MCP

Se necesitan observaciones comparables.

- [ ] Compruebe protocol, launcher y las condiciones de acceso; repita ambas instantáneas en el mismo contexto\.

### Cambios en las herramientas seleccionadas

No se detectaron cambios en las definiciones seleccionadas.

Tamaño del JSON presentado al modelo en UTF-8: lista completa 94 → 94 bytes; herramientas seleccionadas 94 → 94 bytes.
No son tokens ni ahorro conseguido.

## demo:offline

**Datos insuficientes**

- Antes: 2026\-10\-26T09:00:00Z; versión del paquete no corresponde; versión del servidor 1; protocolo 2025\-06\-18.
- Después: 2026\-10\-27T09:00:00Z; versión del paquete no corresponde; versión del servidor desconocida; protocolo desconocido.
No hay una pareja de definiciones obtenidas correctamente. No se compararon los campos de herramientas.

- Limitación: No hay una observación completa y correcta posterior a la actualización\.

### Consultar el estado diario del servicio externo

Se necesitan observaciones comparables.

- [ ] Compruebe protocol, launcher y las condiciones de acceso; repita ambas instantáneas en el mismo contexto\.
- [ ] read\_status: Obtenga dos observaciones completas y correctas en entornos comparables\.

### Cambios en las herramientas seleccionadas

**read\_status: Datos insuficientes**


## Límites del análisis

- Solo se comparan las definiciones observadas, no el comportamiento del servidor en ejecución\.
- Un cambio no demuestra un fallo; unas definiciones sin cambios no establecen la seguridad\.
- Los flujos se relacionan mediante herramientas seleccionadas explícitamente, sin análisis semántico\.
- El tamaño del JSON compacto en UTF\-8 mide bytes, no tokens, dinero ni ahorro conseguido\.
- launch se representa solo con su hash; no se ejecutan sus condiciones ni se muestran secretos del entorno\.

[Datos completos, versiones y hashes SHA-256 de las entradas](report.json).
