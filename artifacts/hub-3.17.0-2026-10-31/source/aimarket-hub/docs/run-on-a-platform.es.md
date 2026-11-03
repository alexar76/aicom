# Un hub en una plataforma

[English](run-on-a-platform.md) · [Русский](run-on-a-platform.ru.md) · [Español](run-on-a-platform.es.md) · [Français](run-on-a-platform.fr.md) · [中文](run-on-a-platform.zh.md)

Railway, Render y Fly dan a un hub un nombre `https` público sin dominio propio. El repositorio
incluye un archivo para cada una (`railway.json`, `render.yaml`, `fly.toml`), y todos construyen
`Dockerfile.standalone`. La imagen se configura sola en su primer arranque (`serve --init`: el
archivo de configuración, un token de administrador, la `hub.ping@v1` gratuita y una muestra de
pago), así que no hay nada que ejecutar antes del primer despliegue.

En cualquier plataforma rigen tres reglas:

1. **Un volumen persistente en `/app/data`.** Ahí viven las claves de firma, la base de datos y
   la configuración, y las claves son la identidad del hub: un despliegue sin ellas es un hub
   nuevo, y todo par que fijó la clave anterior lo rechaza. Una plataforma sin volúmenes en su
   plan gratuito no sirve para un hub.
2. **`AIMARKET_HUB_URL` definido antes del primer arranque**, con la dirección pública que da la
   plataforma. Va dentro de cada documento que el hub firma, y los otros hubs le conocen por ella.
3. **`AIMARKET_ADMIN_TOKEN` como secreto de la plataforma**, para que usted lo conozca: con él se
   aprueban pares y se recarga a compradores. Sin él, `--init` genera uno dentro del volumen.

## Railway

1. Proyecto nuevo → desplegar desde su fork de `alexar76/aimarket-hub`; `railway.json` elige
   `Dockerfile.standalone` y la comprobación de salud.
2. Servicio → Settings → Networking → Generate Domain, puerto de destino `9083`.
3. Añada un volumen montado en `/app/data`.
4. Variables: `AIMARKET_HUB_URL=https://<el dominio generado>`, `AIMARKET_HUB_NAME`,
   `AIMARKET_ADMIN_TOKEN`, `PORT=9083`. Despliegue.

## Render

New → Blueprint → su fork. `render.yaml` crea un servicio web con un disco de 1 GB en
`/app/data` y pide `AIMARKET_HUB_URL` (`https://<nombre del servicio>.onrender.com`) y
`AIMARKET_HUB_NAME`; genera `AIMARKET_ADMIN_TOKEN`. Un disco requiere un tipo de instancia de pago.

## Fly.io

```bash
fly launch --no-deploy --copy-config --name <your-app>
fly volumes create hub_data --size 1
fly secrets set AIMARKET_ADMIN_TOKEN=$(openssl rand -base64 32)
fly deploy
```

Antes, edite `app`, `AIMARKET_HUB_URL` (`https://<your-app>.fly.dev`) y `AIMARKET_HUB_NAME` en
`fly.toml`. La máquina no se detiene (`auto_stop_machines = "off"`): un hub tiene que responder a
rastreos y sondas de admisión a cualquier hora.

## Después

`doctor` se ejecuta desde cualquier sitio, también desde su portátil, contra la dirección pública:

```bash
uvx --from "aimarket-hub[pqc]" aimarket doctor --url https://<su hub>
```

Cuando `doctor` diga `pass`, llame a la puerta — vea [Su propio hub](operator-quickstart.es.md#5-la-llamada).
Para publicar su propia API, abra una shell en la plataforma (`railway ssh`, Render Shell,
`fly ssh console`) y ejecute allí `docker-entrypoint.sh add …`: escribe en la base de datos del
propio hub en el volumen, como el usuario del hub, así que los archivos siguen siendo escribibles
por el hub.

Estos archivos siguen el formato documentado de cada plataforma; la imagen en sí está probada
sobre un volumen propiedad de root, como los que montan estas plataformas.
