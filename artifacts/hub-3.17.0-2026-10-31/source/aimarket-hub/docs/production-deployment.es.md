# Despliegue en producción de un AIMarket Hub independiente

[English](production-deployment.md) · [Русский](production-deployment.ru.md) · [Español](production-deployment.es.md) · [Français](production-deployment.fr.md) · [中文](production-deployment.zh.md)

> La terminología sigue el [glosario de localización](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md) canónico. Los nombres de productos, identificadores del protocolo, URL, comandos CLI y variables de entorno no se traducen.

Este manual permite a un operador independiente desplegar un hub público y superar la admisión de la federación sin eludir manualmente la confianza. Cubre un único servidor Ubuntu, nginx, TLS, Alien Monitor opcional, una capability de pago firmada y la incorporación opcional del agente de nodo SKOPOS.

## 1. Arquitectura objetivo y límite de confianza

```text
Internet
  └─ nginx :80/:443
       ├─ /hub/      → AIMarket Hub en 127.0.0.1:9083
       ├─ /monitor/  → Alien Monitor en 127.0.0.1:9100 (opcional)
       └─ provider   → backend de capability en 127.0.0.1:<port>, no público
```

Use una cuenta Unix sin privilegios por servicio. Solo nginx y SSH deben escuchar públicamente. Guarde las bases SQLite y las claves Ed25519 fuera del checkout de Git. El origin público del hub es el límite de seguridad: discovery, el manifiesto firmado y el `invoke` anunciado deben usar ese mismo origin.

Un nombre dedicado como `hub.example.com` es lo más sencillo. Un subpath como `https://example.com/hub` también funciona, pero requiere todas las reglas proxy de §7. Omitir una suele dejar la API sana y romper assets de UI, WebSocket o las URL de federación.

## 2. Requisitos previos

- Ubuntu 24.04 LTS u otro Linux con systemd compatible.
- IPv4/IPv6 pública y registros DNS `A`/`AAAA` apuntando al servidor.
- Dominio vigente bajo su control; no solicite TLS hasta que DNS resuelva globalmente.
- Acceso SSH con clave Ed25519. Mantenga abierta la primera sesión hasta comprobar una segunda sesión solo con clave.
- Al menos 2 CPU, 2 GB de RAM y 10 GB libres para Hub + Monitor.
- HTTPS saliente para Git, ACME, rastreo de la federación e incorporación de SKOPOS.

```bash
sudo apt update
sudo apt install -y git nginx python3 python3-venv python3-pip \
  certbot python3-certbot-nginx sqlite3 ufw fail2ban unattended-upgrades
```

## 3. Fijar las revisiones del código

No despliegue una rama móvil. Registre y revise un commit SHA y haga checkout exactamente de esa revisión:

```bash
sudo install -d -m 0755 /opt/aimarket/releases
sudo git clone https://github.com/alexar76/aimarket-hub.git \
  /opt/aimarket/releases/aimarket-hub-<sha>
sudo git -C /opt/aimarket/releases/aimarket-hub-<sha> checkout --detach <sha>
git -C /opt/aimarket/releases/aimarket-hub-<sha> rev-parse HEAD

python3 -m venv /opt/aimarket/venvs/hub
/opt/aimarket/venvs/hub/bin/pip install --upgrade pip
/opt/aimarket/venvs/hub/bin/pip install "/opt/aimarket/releases/aimarket-hub-<sha>[pqc]"
```

El extra `[pqc]` instala el firmante y el verificador ML-DSA-65. Sin él, el hub falla cerrado ante cualquier firma híbrida y no puede federarse con hubs que firman de forma híbrida, y todos los hubs de AIMarket lo hacen.

Repita para `alexar76/alien-monitor` y `alexar76/skopos` si los usa. Conserve los SHA en el registro de despliegue. Si aplica un parche de hardening, guarde el parche y el código original fuera del checkout; `git status --short` solo debe explicar cambios intencionados. Ejecute la suite de pruebas sobre esa revisión exacta en CI o en un host de compilación.

## 4. Usuarios, directorios y permisos

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin aimarket-hub
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin aimarket-provider
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin alien-monitor
sudo install -d -o aimarket-hub -g aimarket-hub -m 0750 /var/lib/aimarket/hub
sudo install -d -o aimarket-provider -g aimarket-provider -m 0750 /var/lib/aimarket/provider
sudo install -d -o root -g root -m 0700 /etc/aimarket
sudo install -d -o root -g root -m 0700 /var/backups/aimarket
```

- Claves de firma del hub (`hub_signing_key` y, con firma poscuántica, `hub_signing_key_mldsa` a su lado): `0600`, propiedad de `aimarket-hub`.
- Clave del proveedor: `0600`, propiedad de `aimarket-provider`.
- Archivos de entorno: `0600`, propiedad de root.
- Directorios SQLite: solo puede escribir el servicio propietario.
- Backups con claves: `0600` dentro de un directorio `0700`.

Nunca guarde una clave privada, admin token, enrollment ticket o contraseña de base de datos en Git, argumentos de proceso, historial del shell o logs públicos.

## 5. Configuración del hub

Cree `/etc/aimarket/hub.env`:

```dotenv
AIMARKET_HUB_NAME=Example Independent Hub
AIMARKET_HUB_URL=https://example.com/hub
AIMARKET_BIND_HOST=127.0.0.1
AIMARKET_DB_PATH=/var/lib/aimarket/hub/hub.db
AIMARKET_SIGNING_KEY_PATH=/var/lib/aimarket/hub/hub_signing_key
# Firma híbrida (Ed25519 + ML-DSA-65); requiere el extra [pqc] (sección 3). La clave ML-DSA se escribe
# junto a la clásica como <AIMARKET_SIGNING_KEY_PATH>_mldsa; los peers la fijan la primera vez que la ven.
AIMARKET_PQC=1
AIFACTORY_PROD=1
# Confíe en direcciones forwarded solo desde nginx local; nunca use *.
AIMARKET_TRUSTED_PROXIES=127.0.0.1,::1
# La misma dirección decide SELF para los servidores de ecosystem.json (junto a la
# base de datos): véase docs/traffic-classes.es.md.
# Las rutas de pago que otro servicio sirve en este mismo origen (un sidecar x402 bajo /x402/)
# se añaden a /openapi.json, donde las buscan los indexadores x402 (x402scan, AgentCash). Solo el
# mismo origen que AIMARKET_HUB_URL; nunca sustituyen rutas del hub. Se refresca cada 10 minutos.
# AIMARKET_OPENAPI_MERGE_URLS=https://hub.example.com/x402/openapi.json
# Un operador independiente no debe depender del oracle de otro operador.
AIMARKET_ORACLE_FAMILY_URL=off
AIMARKET_AUTO_CRAWL=1
AIMARKET_CRAWL_INTERVAL_S=3600
AIMARKET_CRAWL_REFRESH_MAX=64
AIMARKET_SEED_LIST=https://modelmarket.dev/.well-known/ai-market.json
AIMARKET_SEED_PUBKEYS=https://modelmarket.dev/.well-known/ai-market.json=<seed-ed25519-public-key>
AIMARKET_FEDERATION_ASSAY=1
AIMARKET_FEDERATION_ASSAY_SANDBOX=1
AIMARKET_FEDERATION_AUTO_ADMIT=1
AIMARKET_CREDITS_ENABLED=1
AIMARKET_CREDITS_OPEN_SIGNUP=1
AIMARKET_CREDITS_FREE_GRANT_USD=0

# Vender crédito por USDC (docs/credits-topup.es.md, sección 5.1 abajo). Apagado por defecto.
AIMARKET_TOPUP_ENABLED=1
# Una cartera que recibe recargas Y NADA MÁS (solo su dirección, nunca su clave). Entonces el
# hub la vigila y abona cada depósito él mismo; sin ella, las recargas van a AIMARKET_X402_PAY_TO
# y alguien tiene que presentar cada una.
AIMARKET_TOPUP_PAY_TO=<cartera de recargas dedicada>
AIMARKET_TOPUP_MIN_CONFIRMATIONS=2
# Dónde se leen los pagos (separados por comas); sin valor, nodos públicos de Base.
# AIMARKET_SETTLE_RPC_URL=https://mainnet.base.org,https://base-rpc.publicnode.com
# El vigilante de depósitos — activo siempre que AIMARKET_TOPUP_PAY_TO esté definido; valores por defecto.
# AIMARKET_DEPOSIT_WATCH=1
# AIMARKET_DEPOSIT_WATCH_INTERVAL_S=60
# AIMARKET_DEPOSIT_WATCH_CHUNK_BLOCKS=500
# AIMARKET_DEPOSIT_WATCH_LOOKBACK_BLOCKS=1800
AIMARKET_ADMIN_TOKEN=<secret>
AIMARKET_PUBLISHER_TOKENS=<publisher-id>:<secret>
AIMARKET_ECOSYSTEM_LABELS=publisher-id=Display Name
AIMARKET_CORS_ORIGINS=https://example.com
```

Reglas importantes:

1. `AIMARKET_HUB_URL` es la URL externa e incluye `/hub` si usa un subpath; nunca use `localhost` en producción.
2. El hub crea su clave Ed25519 al arrancar por primera vez. Haga backup inmediatamente. Sustituirla cambia la identidad federada y parece una toma de control a los peers que la fijaron. Con `AIMARKET_PQC=1` también crea la clave ML-DSA-65 `<ruta de la clave>_mldsa`: haga backup de ambas y manténgalas en un mismo volumen.
3. La seed key es pública, pero fijarla es una decisión de confianza. Obtenga y compare la clave del well-known firmado sobre TLS verificado.
4. Sin admin token, las rutas de operador deben ser fail-closed (denegar por defecto).
5. Con SQLite, detenga el hub o use la API de backup de SQLite. Para múltiples procesos o muchas escrituras, prefiera PostgreSQL.
6. Asigne a cada proveedor su propio publisher token limitado por sujeto. Nunca reutilice el admin token del hub como credencial de proveedor. Con varios módulos del mismo hub, configure `AIMARKET_ECOSYSTEM_LABELS=publisher-id=Display Name,...`; la extensión firmada `ecosystem.nodes` muestra la pertenencia sin fingir que son peers federados independientes.
7. En cada ciclo, el crawler debe refrescar un conjunto acotado de peers activos ya confiables, aunque el seed graph actual ya no los enlace. Dimensione `AIMARKET_CRAWL_REFRESH_MAX` para ese roster; de lo contrario, un peer válido con 30 capabilities puede quedar indefinidamente indexado con un manifiesto antiguo de una sola capability.

### 5.1 Vender crédito por USDC: una cartera propia

Con `AIMARKET_TOPUP_ENABLED=1` cualquier agente compra crédito con USDC en Base por sí mismo
([credits-topup.es.md](credits-topup.es.md)). Da a esta puerta su propia cartera y nadie tendrá que
vigilar la cadena ni abonar nada a mano:

1. **Crea una cartera que reciba recargas y nada más.** El hub solo necesita su dirección, nunca su
   clave: nada de lo que hace el hub gasta de ella. Guarda la clave donde el operador guarda las
   claves de tesorería.
2. **Define las variables** de arriba (`AIMARKET_CREDITS_ENABLED=1`, `AIMARKET_TOPUP_ENABLED=1`,
   `AIMARKET_TOPUP_PAY_TO=<dirección>`). Con systemd van en el archivo env o en un drop-in
   (`Environment=AIMARKET_TOPUP_PAY_TO=0x…`); con Docker Compose el contenedor solo ve lo que el
   archivo compose reenvía, así que añade `AIMARKET_TOPUP_PAY_TO: ${TOPUP_PAY_TO:-}` al
   `environment:` del hub y `TOPUP_PAY_TO=0x…` a `.env`.
3. **Haz copia de la base de datos y reinicia el hub.** La migración `050_deposit_watch` añade
   `payer_wallets`, `deposit_watch_cursor` y `hub_deposits`.
4. **Compruébalo**: `pay_to` es la nueva cartera y `deposit_watch.enabled` es `true` (apagado,
   `reason` dice qué falta). Vincula una vez la cartera de cada empresa que pagará por
   transferencia simple. Lee lo que llegó de nadie conocido:

```bash
curl -s "$AIMARKET_HUB_URL/.well-known/ai-market.json" | jq '.payment_rails.credits.topup | {pay_to, deposit_watch}'
curl -s "$AIMARKET_HUB_URL/ai-market/v2/accounts/$ACCOUNT_ID/payer-wallets" -H "Authorization: Bearer $AIMARKET_ADMIN_TOKEN" \
     -H 'Content-Type: application/json' -d '{"address": "0x…"}'
curl -s "$AIMARKET_HUB_URL/ai-market/v2/admin/deposits" -H "Authorization: Bearer $AIMARKET_ADMIN_TOKEN"
```

5. **Configura el aviso**: añade el hub a `AICOM_ALERT_DEPOSIT_HUBS` del alertador del ecosistema
   (solo se comprueban los hubs dentro de su `AICOM_ALERT_SCOPE`)
   (`deposit_watch_on:<hub>`: el hub debería vigilar y no lo hace; `deposits_unattributed:<hub>`:
   llegó dinero de una cartera que nadie vinculó).

El primer escaneo empieza `AIMARKET_DEPOSIT_WATCH_LOOKBACK_BLOCKS` (1800, cerca de una hora en Base)
bloques por detrás de la cabeza, un intervalo después de arrancar el hub, así que una transferencia
hecha poco antes de activarlo se encuentra igual; una más antigua se abona a mano con su `tx_hash`.
Una cartera nueva recibe un cursor nuevo y la antigua deja de leerse.

Nunca apuntes `AIMARKET_TOPUP_PAY_TO` a una cartera que reciba otro dinero: cada transferencia
entrante se leería como recarga. El hub rechaza sus propias carteras x402 y receptora de pagos
(`AIMARKET_X402_PAY_TO`, `AIMARKET_PAYMENT_RECIPIENT`; `reason` en el well-known); no puede saber qué
más recibe otra cartera ni si otro hub usa la misma.

## 6. Servicio systemd

Cree `/etc/systemd/system/aimarket-hub.service`:

```ini
[Unit]
Description=Independent AIMarket Hub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=aimarket-hub
Group=aimarket-hub
WorkingDirectory=/opt/aimarket/releases/aimarket-hub-<sha>
EnvironmentFile=/etc/aimarket/hub.env
ExecStart=/opt/aimarket/venvs/hub/bin/python -m aimarket_hub serve
Restart=on-failure
RestartSec=5s
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictNamespaces=yes
LockPersonality=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=/var/lib/aimarket/hub
UMask=0027
MemoryMax=1G
TasksMax=256

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aimarket-hub
sudo systemctl status aimarket-hub --no-pager
```

Vincule la aplicación a loopback cuando la versión permita elegir bind-host. Si escucha en `0.0.0.0:9083`, UFW debe seguir bloqueando ese puerto y nginx debe ser la única entrada pública.

## 7. nginx, subpaths y TLS

Configuración esencial; adapte certificados y rate limits:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name example.com;
    location ^~ /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 301 https://$host$request_uri; }
}
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name example.com;
    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_tickets off;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    client_max_body_size 1m;

    location = /hub { return 301 /hub/; }
    location ^~ /hub/ {
        proxy_pass http://127.0.0.1:9083/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }
    location ~ ^/(ai-market|api|mcp|developers|examples|widget|plugins|operator|studio)(/|$) {
        proxy_pass http://127.0.0.1:9083;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
    location = /hub-ui-i18n.json { proxy_pass http://127.0.0.1:9083/hub-ui-i18n.json; }
    location = /cap-descriptions-i18n.json { proxy_pass http://127.0.0.1:9083/cap-descriptions-i18n.json; }
}
```

Para Alien Monitor, compile el frontend con `VITE_BASE_PATH=/monitor/`, haga proxy de `/monitor/` a su puerto HTTP loopback y configure `/monitor/ws` con headers WebSocket `Upgrade`/`Connection` y timeout prolongado. Una build creada para `/` puede devolver HTTP 200 y aun así perder JavaScript y CSS bajo el subpath.

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d example.com
sudo certbot renew --dry-run
systemctl is-enabled certbot.timer
```

No active HSTS hasta que HTTPS funcione en todos los subdominios cubiertos.

Si la raíz del dominio aloja un portal separado, ejecútelo como otro servicio sin privilegios en loopback y úselo solo como fallback final de nginx. Coloque los prefijos API del portal, por ejemplo `/api/v1/`, antes de la regla amplia de compatibilidad root-relative del hub; de lo contrario, el portal puede renderizar mientras su API va silenciosamente al hub. Mantenga explícitos `/hub/`, `/monitor/` y los paths de proveedores, y no redirija `/` a `/hub/` cuando el portal sea la entrada prevista.

## 8. Publicar una capability real sin eludir el pago

Para la primera capability de prueba local, detenga el hub y ejecute el quickstart idempotente como usuario del hub. Crea un static pack ejecutable sin modelo ni proveedor externo; sustitúyalo por su backend antes de ofrecerlo como producto:

```bash
sudo systemctl stop aimarket-hub
sudo -u aimarket-hub env \
  AIMARKET_DB_PATH=/var/lib/aimarket/hub/hub.db \
  AIMARKET_HUB_URL=https://example.com/hub \
  AIMARKET_CREDITS_ENABLED=1 \
  /opt/aimarket/venvs/hub/bin/python -m aimarket_hub quickstart \
  --price 0.01 --grant 0
sudo systemctl start aimarket-hub
```

La buyer key generada es secreta y solo se muestra una vez. Con grant cero no tiene saldo; guárdela en un password manager o revóquela. Para un proveedor real, consulte [Ejecutar este hub por su cuenta](operator-quickstart.md), registre únicamente un backend bajo su control y conserve su clave de firma.

Una capability de producción tiene un backend interno del proveedor, que hace el trabajo y firma el resultado, y un gateway público del hub, que comprueba seguridad, pago, routing y recibos.

El manifiesto firmado debe anunciar el gateway del hub, por ejemplo `https://example.com/hub/ai-market/v2/invoke`, nunca una URL directa `/provider/invoke`. Limite el proveedor a loopback, autenticación mutua o la dirección propia del host. Una versión que exponga esa URL requiere una actualización o backport revisado.

Para una capability exclusivamente de pago, una petición no autorizada —incluida una con `X-AIMarket-Sandbox-Visitor`— debe devolver `402`, nombrar un canal de pago utilizable y cotizar exactamente el precio del catálogo firmado. Como alternativa, una capability realmente gratuita puede realizar el trabajo y devolver un recibo firmado. Un endpoint demostrativo sin evidencia no sirve.

Comprobaciones mínimas:

- `/hub/.well-known/ai-market.json` valida con el esquema distribuido;
- `manifest_url` es público y same-origin;
- las firmas de well-known y manifiesto se verifican con la clave Ed25519 anunciada;
- `generated_at` es reciente;
- el canonical de cinco campos cubre número de capability, timestamp, protocol version, `tools_hash` y `by_hub_hash`;
- los campos numéricos son números, no `null`;
- `invoke_url` es same-origin y entra al gateway del hub;
- el precio `402` coincide con `price_per_call_usd`;
- una respuesta correcta del proveedor contiene una firma verificable.

## 9. Admisión a la federación

Tras superar las pruebas locales, anuncie por el protocolo público:

```bash
curl -fsS -X POST https://modelmarket.dev/ai-market/v2/federation/announce \
  -H 'Content-Type: application/json' \
  --data '{
    "hub_url":"https://example.com/hub",
    "hub_name":"Example Independent Hub",
    "well_known_url":"https://example.com/hub/.well-known/ai-market.json"
  }'
curl -fsS 'https://modelmarket.dev/ai-market/v2/federation/assay?url=https%3A%2F%2Fexample.com%2Fhub'
```

```text
announce o crawl entrante → pending/quarantine → sandbox assay → pass → trusted/indexed
```

No eluda la confianza con operator panel, admin endpoint ni una peer table editada. Un peer pending puede esperar al siguiente ciclo del receptor; una hora es normal. Ante `review` o `fail`, corrija la evidencia viva y espere el reintento documentado. Conserve el dossier que identifica la prueba fallida.

Después de la admisión, verifique el roster, la búsqueda federada y Alien Monitor por nombre y `capability_id`, no solo por HTTP 200.

## 10. Seguridad del host

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw limit 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Active jails de Fail2ban para `sshd`, `nginx-http-auth` y `nginx-botsearch`, además de actualizaciones de seguridad desatendidas. Revise bans y logs: instalar no equivale a monitorizar.

Orden crítico para SSH:

1. Instale la clave pública del operador.
2. Abra otra sesión con `BatchMode=yes` y la clave prevista.
3. Inspeccione `sshd -T`; un drop-in de cloud-init puede anular otro archivo.
4. Configure `PasswordAuthentication no`, `KbdInteractiveAuthentication no` y `PermitRootLogin prohibit-password`, o desactive root y use sudo.
5. Recargue SSH, mantenga la primera sesión y pruebe un tercer acceso solo con clave.

Nunca cierre la única sesión funcional antes de esa prueba independiente.

## 11. Backups y restauración

Incluya la base SQLite y bases de channel/provenance, claves privadas del hub y proveedor (la Ed25519 y, con `AIMARKET_PQC=1`, su compañera ML-DSA `<ruta de la clave>_mldsa`), env files y drop-ins de root, configuración nginx, SHA fijados y parches intencionados.

Use `sqlite3 /path/hub.db '.backup /staging/hub.db'` o detenga el servicio antes de copiar. Genere un archivo solo para root, conserve generaciones y saque una copia cifrada del host. Un backup no está verificado hasta restaurarlo.

Para restaurar: detenga hub y proveedor; restaure bases y claves con propietario/modos originales; restaure la configuración y ejecute `systemctl daemon-reload` y `nginx -t`; arranque los servicios y compruebe que no cambió ninguna clave pública (`signature.public_key` y `signature.pq_public_key` en `/.well-known/ai-market.json`); repita esquema, firmas, `402`, búsqueda y federación.

## 12. Alien Monitor y SKOPOS

Ejecute Alien Monitor como servicio separado sin privilegios en modo LIVE. Apúntelo al hub local, haga proxy por separado de HTTP API y WebSocket, y compruebe tras reboot que el tick avanza. Métricas financieras vacías pueden indicar que no hubo tráfico; un tick congelado o health endpoint fallido es una incidencia.

Trate cada Hub independiente como un sistema estelar separado. Deduplicate por identidad estable y URL normalizada, imponga una distancia mínima entre centros de hubs y agrupe `ecosystem.nodes` alrededor de su Hub propietario. Reserve primero el child budget de cada Hub para los `ecosystem.nodes` firmados y dibuje después los enlaces a peers federados; un roster grande no debe ocultar los proveedores propios. El asistente de IA debe resolver los nombres desde el live snapshot actual —incluidas consultas localizadas o transliteradas— antes de usar ayuda estática, para que los módulos recién desplegados sigan visibles sin una clave LLM externa.

SKOPOS usa un agente de nodo push-only restringido. La incorporación requiere un ticket oficial de un solo uso:

1. Emita el ticket en el control plane de SKOPOS para la entrada exacta del servidor.
2. Ejecute el installer generado como root en el nodo.
3. Introduzca el ticket por stdin oculto; nunca en argv, URL, historial ni chat.
4. Confirme que se consumió, que el credential file solo es legible por root/agente y que los timers informan correctamente.

El nodo no puede emitir su propio ticket: solo el control plane de SKOPOS puede crearlo. Si no existe, deje detenido el installer preparado y marque la incorporación como pending; no adivine el ticket ni copie uno de otro nodo.

No cree credenciales manualmente en la base SKOPOS ni conceda al agente el grupo Docker o sudo irrestricto.

## 13. Lista final de aceptación

```bash
systemctl is-active aimarket-hub nginx fail2ban ufw unattended-upgrades
systemctl --failed
curl -fsS https://example.com/hub/.well-known/ai-market.json
curl -fsS https://example.com/hub/ai-market/v2/manifest
curl -sS -o /tmp/invoke.json -w '%{http_code}\n' \
  -H 'Content-Type: application/json' \
  --data '{"product_id":"example","capability_id":"example.echo@v1","input":{}}' \
  https://example.com/hub/ai-market/v2/invoke
ufw status verbose
sshd -T | egrep '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication) '
```

Reinicie el host y repita desde una red externa. Deben volver todos los servicios; solo SSH/HTTP/HTTPS estarán públicos; el dry-run de TLS funcionará; firmas y clave permanecerán; no se podrá eludir el proveedor; el hub seguirá visible en la federación; Alien Monitor reconectará con tick LIVE creciente; y existirá un backup reciente con restauración documentada.

## 14. Actualización y rollback

1. Cree un release y virtualenv nuevos e inmutables; no use `git pull` en el release activo.
2. Revise migraciones, en especial rutas SQLite channel/provenance.
3. Respalde bases y claves.
4. Ejecute pruebas y federation assay local.
5. Cambie únicamente el objetivo de `WorkingDirectory`/`ExecStart`, reinicie y repita la aceptación.
6. Puede revertir el código, pero no una base a través de una migración incompatible sin su backup correspondiente.

La identidad de firma (la clave Ed25519 y, con firma poscuántica, su compañera `_mldsa`) y el ledger de pagos son estado persistente, no artefactos del release. Perderlos o sustituirlos silenciosamente no es un despliegue rutinario.

## 15. Trasladar el hub a otro host

El contenedor y su volumen de datos son la parte fácil. Lo que rompe un traslado es lo que se
ejecuta **junto** al hub en el host: nada de eso está en la imagen, un `/health` en verde no dice
nada de ello, y el host antiguo sigue ejecutando su copia para un hub que ya no está allí. El
2026-10-01 el hub de modelmarket.dev cambió de host y el túnel al firmante del escrow y el barrido
de liquidación se quedaron atrás: durante dos días ningún cargo del escrow llegó a la cadena y
nada avisó, porque el barrido antiguo seguía publicando «ok, nada que enviar».

**Trasladar junto con el contenedor**

| Qué | Dónde vive | En el host nuevo |
|---|---|---|
| Datos del hub (`hub.db`, libro de canales, almacén de autorizaciones del escrow, deposit claims) | el volumen de datos | copiar de una copia de seguridad reciente hecha con el hub detenido (§11) |
| Identidad de firma | volumen de datos / ruta de la clave: `hub_signing_key` y `hub_signing_key_mldsa` | ambas claves, nunca nuevas (§14): los peers que fijaron la clave poscuántica rechazan una nueva hasta que cada uno la vuelva a fijar |
| Túnel al firmante del escrow | `escrow-signer-tunnel.service` (SSH `-L` al host del firmante) | nueva clave SSH en el host nuevo; en el host del firmante añadirla como `restrict,port-forwarding,permitopen="127.0.0.1:9500",command="/bin/false"`; fijar la clave de host del firmante comparando su huella con el `known_hosts` del host antiguo; escuchar en `127.0.0.1:9500` **y** en la pasarela de la red Docker del contenedor del hub; cortafuegos: permitir la subred de esa red hacia la pasarela en el 9500 y nada más |
| Barrido de liquidación | `aicom-settlement-sweep.{service,timer}` + `/usr/local/lib/aicom-settlement/escrow_settlement_sweep.py` | instalar, apuntar `--publish` al directorio desde el que el host nuevo sirve `verify.<dominio>`, ejecutarlo una vez |
| Canario de pagos | `aicom-payment-canary.{service,timer}` (`scripts/payment_canary.py`) | instalar, publicar en el mismo directorio de `verify.<dominio>`; el alertador avisa cuando `status.json` se queda viejo |
| Auditor (THEMIS) | se une al espacio de red del hub | recrearlo con `--network container:<hub>` después del hub (si no, queda huérfano) |
| Clave del verificador de Pay-on-Verified | `/root/.metis-verify-key` (0600) → `AIMARKET_VERIFY_METIS_*` | copiar de servidor a servidor, nunca a través de una terminal |
| Proveedores propios | unidades systemd (`weather-witness`, `pov-demo`) | instalar y volver a comprobar sus location de nginx |
| location de nginx, TLS, hooks de renovación | `/etc/nginx`, `/etc/letsencrypt` | volver a comprobar cada `location` que hace proxy a un puerto del host |

**Un solo script hace las tres primeras filas y las comprueba:** `scripts/hub_host_companions.sh --install` en el host nuevo (defina `AICOM_SIGNER_SSH_HOST` si el hub firma mediante el firmante externo), `--verify` para comprobar (falla salvo que las unidades se ejecuten, el contenedor del hub alcance al firmante y ambos informes estén frescos), `--disable` en el host antiguo. `scripts/deploy_hub_rebuild.sh` ejecuta `--verify` al final de cada despliegue y sale con código 3 si falta algo.

**Después apague el host antiguo** — cada unidad de la lista, de forma explícita
(`systemctl disable --now`). Un barrido que se queda allí lee un almacén en el que ya nadie
escribe e informa de éxito para siempre.

**Demuestre la ruta del dinero antes de dar el traslado por terminado**

```bash
# el contenedor del hub alcanza al firmante por el túnel (imprime la dirección del firmante)
docker exec <hub> python -c "import httpx;print(httpx.get('http://<pasarela>:9500/health').text[:120])"
# el barrido se ejecutó AQUÍ: checked_at es de hace minutos, errors está vacío
curl -s https://verify.<dominio>/settlement.json | jq '{checked_at, ok, errors}'
# en el host antiguo ya no escucha nada
ssh <host-antiguo> 'systemctl is-active escrow-signer-tunnel aicom-settlement-sweep.timer'   # inactive, inactive
# Pay-on-Verified sigue conectado: enabled, su verificador, escrow_hub declarado
curl -s https://<dominio>/.well-known/ai-market.json | jq '.pay_on_verified.enabled, .contracts.entries'
```

La burbuja UNI tiene su propia lista (su cadena privada, cortafuegos, ajustes del comprador):
[docs/uni-realm-runbook.es.md](https://github.com/alexar76/aicom/blob/main/docs/uni-realm-runbook.es.md).
