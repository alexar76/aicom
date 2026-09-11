# Guía de usuario

## Pago y clave

En `/billing` elige Personal, Team o Market. La factura indica importe, receptor,
token, chain y caducidad. Envía el importe exacto en Base, espera las
confirmaciones y pega el tx hash. La clave de pago `ask_...` se puede recuperar
con el secreto de checkout durante 48 horas; después solo queda su hash. Gateway
reconcilia el pago automáticamente aunque se cierre el navegador.

Puedes consultar `GET /v1/keys/me`, rotar con `POST /v1/keys/rotate` y revocar con
`POST /v1/keys/revoke`.

## Identidad y memoria

Envía la clave pagada activa como `X-SaaS-Key`; es distinta de la prueba del actor.

Las solicitudes protegidas requieren `X-Actor-ID`, `X-Actor-Public-Key` y
`X-Actor-Signature`. La clave privada permanece en tu cliente. Escribe en
`/memory/api/memories` y busca en `/memory/api/search`.

## Equipos

Crea un equipo en `/teams/api/teams`, añade miembros en
`/teams/api/teams/{team_id}/members` e incluye `team_id` en cada operación.
Gateway valida la membresía y Hub valida la assertion y la firma del actor.

`401` indica credenciales inválidas; `403`, scope incorrecto; `402`, pago
necesario; `429`, límite de peticiones. Nunca envíes claves privadas.

## Trial

Solicita el trial en `/v1/trials`: Personal dura 7 días, Team 14 días y Expert
Market 1 día. Gateway entrega una clave `ask_...` vinculada al actor sin pago; el
mismo actor firmado puede recuperarla mientras esté activa. El acceso caduca automáticamente; para continuar,
completa el pago exacto de USDC en Base. Consulta [TRIAL.md](TRIAL.md).

## Capabilities de KOVA y checkout

Los agentes descubren KOVA mediante la federación del Hub; el checkout de Attested
usa una ruta service-to-service autenticada y separada. Consulta ambos caminos y
sus límites de seguridad en [KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md).
