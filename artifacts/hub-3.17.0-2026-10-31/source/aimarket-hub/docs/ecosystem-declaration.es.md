# Declarar tu ecosistema para que se muestre correctamente

> ## ⚠️ AVISO — LÉELO PRIMERO
>
> **Los monitores y los pares muestran EXACTAMENTE lo que declara tu hub. Nada más.**
>
> Ningún monitor va a adivinar la dirección pública de tus servicios, y ninguno debería:
> adivinar significaría escanear tu host buscando puertos abiertos y publicar lo que
> respondiera. Si declaras `http://memory-market:8810`, entonces todo el que mire cualquier
> mapa — el tuyo o el de otro operador — verá `http://memory-market:8810`: una dirección
> que resuelve exactamente en una máquina del mundo y es inútil para todas las demás.
>
> **Un hub que no declara direcciones públicas no está «mal configurado» de una forma que
> alguien pueda arreglar por ti. Es lo único que conoce la respuesta.**

## De dónde sale un nodo (no es descubrimiento)

Un monitor no encuentra tus proveedores. Lee `/.well-known/ai-market.json` y desempaqueta
`ecosystem.nodes` — nada más. Sin escaneo de puertos, sin sondear subdominios, sin adivinar:

```python
# alien-monitor/backend/hub_discovery.py
ecosystem = well_known.get("ecosystem")
declared_nodes = ecosystem.get("nodes") if isinstance(ecosystem, dict) else []
```

La cadena es: **una capacidad se publica en tu hub → tu hub construye `ecosystem.nodes` a
partir de ella → el hub lo sirve → un monitor lo dibuja.** El nodo existe porque está
registrado en el hub, y por nada más. Un subdominio no es cómo se encuentra; un subdominio
es solo lo que resulta ser su DIRECCIÓN, si publicas el servicio bajo uno.

## Qué se rompe, y por qué parece un fallo del mapa

Un proveedor se registra con la dirección que **tu hub** usa para llamarlo. En un
despliegue de una sola máquina, esa dirección es un nombre de contenedor:

```
http://memory-market:8810
http://truth-layer:8811
http://provenance-ledger:8812
```

Tu hub las publica en `/.well-known/ai-market.json` bajo `ecosystem.nodes`, y son las que
dibuja un monitor. El nodo aparece, está bien nombrado, informa de su número de
capacidades — y su dirección no la puede abrir nadie. Quien lo ve concluye,
razonablemente, que el mapa está roto. El mapa informa con fidelidad.

Medido en `hub.attestedmemory.net`, 2026-09-07: tres proveedores, tres nombres de
contenedor, tres tarjetas inservibles. En `independentai.network/hub` esos mismos tres
campos llevaban `https://kova.independentai.network`,
`https://aegis.independentai.network` y una URL de invocación pública — mismo código,
mismos monitores, resultado correcto. La diferencia era la configuración, y hasta ahora no
había variable donde ponerla: los nombres se podían fijar
(`AIMARKET_ECOSYSTEM_LABELS`) y las direcciones no.

## Las tres variables

Fija las tres. Responden a tres preguntas distintas.

| Variable | Pregunta que responde | Ejemplo |
|---|---|---|
| `AIMARKET_HUB_URL` | ¿Dónde es accesible **este hub**? | `https://hub.example.net` |
| `AIMARKET_ECOSYSTEM_LABELS` | ¿Cómo se **llaman** mis proveedores? | `memory-market:Memory Market,truth-layer:Truth Layer` |
| `AIMARKET_ECOSYSTEM_URLS` | ¿Dónde son **accesibles** mis proveedores? | `memory-market=https://memory.example.net,truth-layer=https://truth.example.net` |

Detalles que cuestan tiempo si se pasan por alto:

* `AIMARKET_ECOSYSTEM_LABELS` separa con `:` — el valor es un nombre.
* `AIMARKET_ECOSYSTEM_URLS` separa con **`=`** — el valor es una URL y ya contiene dos
  puntos.
* Las entradas se indexan por **`publisher_id`**, el id con el que se publicó la
  capacidad: no el nombre visible ni el id de producto. `GET /ai-market/v2/manifest` lo
  muestra.
* Todo lo que no sea `http://…` o `https://…` se ignora en lugar de publicarse. Una
  entrada mal formada deja la dirección derivada en su sitio; no vacía el nodo.
* Una dirección declarada **gana** frente a cualquiera derivable de la URL de invocación.
  Ése es el punto: tu hub marca a un proveedor por un camino y el mundo lo alcanza por otro.
* `AIMARKET_HUB_URL` debe ser tu dirección **pública**. Un hub que anuncia
  `http://localhost:9084` le está diciendo a cada par que llame a su propio loopback.

## Cómo desplegarlo

1. **Publica los servicios.** Una declaración es una promesa; hazla verdad primero. Un
   subdominio por proveedor es el patrón de este ecosistema (`kova.`, `aegis.`, `charon.`):

   * añade un registro DNS `A` por nombre, apuntando al host;
   * añade un bloque `server` de nginx por nombre, con proxy al puerto local;
   * emite los certificados (`certbot --nginx -d memory.example.net …`) — HTTP-01 necesita
     que el DNS resuelva **antes**, así que hazlo en este orden.

   Las rutas en un solo dominio (`https://example.net/memory`) también funcionan y no
   requieren DNS ni certificado nuevos, pero el servicio debe tolerar servirse bajo un
   prefijo — la mayoría sirven `/v1/…` en su raíz y no lo toleran.

2. **Fija las variables** donde tu despliegue guarde el entorno (`.env`, un bloque
   `environment:` de compose, un `EnvironmentFile` de systemd).

3. **Reinicia el hub.** Se leen al construir el documento well-known.

4. **Verifica** — no lo supongas:

   ```bash
   curl -s https://hub.example.net/.well-known/ai-market.json \
     | python3 -c 'import json,sys; d=json.load(sys.stdin); \
       print([(n["name"], n["url"]) for n in (d.get("ecosystem") or {}).get("nodes") or []])'
   ```

   Cada dirección de esa lista debe poder pegarse en un navegador **desde otra máquina**.
   Luego abre el nodo en un monitor: una dirección pública declarada se dibuja como enlace
   pulsable; una interna se dibuja como texto gris con la etiqueta **internal address** y
   nunca se ofrece como enlace.

## Lista de comprobación

- [ ] cada servicio proveedor responde en una dirección pública
- [ ] `AIMARKET_HUB_URL` es la dirección pública de ese hub, no loopback
- [ ] `AIMARKET_ECOSYSTEM_LABELS` nombra a cada proveedor
- [ ] `AIMARKET_ECOSYSTEM_URLS` direcciona a cada proveedor, con `=` como separador
- [ ] se usa `publisher_id` como clave, tomado del manifiesto
- [ ] documento well-known verificado desde **otra** máquina
- [ ] la tarjeta del nodo en un monitor muestra un enlace, no «internal address»

## Relacionado

* [federation-admission.es.md](./federation-admission.es.md) — cómo se admite un hub par.
* [federation-peer-keys.es.md](./federation-peer-keys.es.md) — cómo se fija su clave.
* [who-gets-a-sphere.es.md](./who-gets-a-sphere.es.md) — por qué un nodo tuyo puede no dibujarse en el mapa de otra persona, y las tres formas de cambiarlo.
