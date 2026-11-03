# HISTOR y LEGION-tlog en un mismo servidor MCP

[English](README.en.md) · [Русский](README.md) · [Español](README.es.md) · [Français](README.fr.md) · [简体中文](README.zh.md)

¿Pueden dos registros de transparencia independientes corroborar las definiciones de herramientas anunciadas por un servidor MCP en momentos comparables? Elegimos LEGION-tlog porque publica la hora de observación y una huella SHA-256 por herramienta. Así podemos identificar un conjunto de herramientas coincidente y localizar las diferencias con observaciones posteriores del mismo servidor, `com.aiapplyd/aiapplyd`.

| Observación de HISTOR (UTC) | Comparación con LEGION |
|---|---|
| 19 de octubre de 2026, 21:37:07 | Las 23 huellas de `name`, `description` e `inputSchema` coinciden con la observación de LEGION a las 22:01:05. |
| 24 de octubre, 18:19:21 | Los 23 nombres pasan del prefijo `aiapplyd_` a `getmattered_` y conservan sus sufijos. La respuesta archivada de LEGION sigue mostrando el registro del 19 de octubre. |
| 31 de octubre, 12:45:49 | HISTOR registra 40 herramientas. Ningún nombre coincide con el registro archivado de LEGION. La instantánea del 2 de noviembre contiene ese conjunto de herramientas. La hora de la lectura posterior procede de los metadatos de la instantánea. |

## Verificación sin conexión

Ejecuta desde la raíz del repositorio con Node.js 22.

```sh
node artifacts/histor-legion-case-2026-11-03/replay.mjs
```

Compara la salida con [result.json](result.json). El script verifica las firmas Ed25519 y la prueba de inclusión de la hoja 29030 de LEGION bajo su encabezado de árbol firmado (STH) de 50 578 hojas. Después verifica el STH de HISTOR de 1 564 894 hojas, las firmas y las pruebas de inclusión de las etiquetas MTL/1 de las hojas 762851, 988911 y 1324412, y el resumen SHA-256 que vincula cada conjunto de herramientas a su etiqueta firmada. Por último, repite la comparación por herramienta.

La evidencia se limita a estas observaciones y a estos encabezados del árbol de Merkle. La seguridad del servidor, la causa de la ausencia del cambio posterior en la respuesta archivada de LEGION, la consistencia entre encabezados y el anclaje en Bitcoin quedan fuera del alcance de esta verificación.

[Procedencia de los datos](README.md) · [Documentación del registro de HISTOR](../../histor/docs/log.es.md) · [Especificación de LEGION](https://legion-api.com/tlog/docs/)
