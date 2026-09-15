# Cripto / economía on-chain — el interruptor maestro

AICOM funciona **sin ningún blockchain por defecto**. El cripto está
**DESACTIVADO salvo que lo actives explícitamente**. Con el interruptor apagado,
ningún componente carga una cartera (wallet), contacta una cadena/RPC, abre un canal de
pago, devuelve `402 Payment Required`, verifica una transacción on-chain ni
liquida UNI/lotería. Todo sigue funcionando — las capacidades se sirven en un
nivel gratuito, la firma de federación y la contabilidad interna siguen
operando — simplemente nunca toca dinero.

## Qué se ve en el Alien Monitor

El monitor muestra el estado **real**, nunca uno falso:

| Modo | Contexto de cadena | Nodos on-chain (chain · escrow · NFT · ACEX · lottery) |
|------|--------------------|----------------------------------------------------------|
| **TEST** | nunca | simulado por script |
| **UNI** | **siempre** (Anvil local privado — nunca Base) | en vivo contra la cadena local |
| **LIVE**, cripto **OFF** | ninguno | **en gris / desactivado** + insignia «Blockchain real desactivado en los ajustes» |
| **LIVE**, cripto **ON** | Base mainnet | en vivo en Base, iluminados |

Esto refleja el contrato del lado del agente
`shouldBuildChainContext(mode, cryptoEnabled)`
(`argus/src/ecosystem/networks.ts`): `uni → siempre`, `live → solo con cripto
activado`, `test → nunca`. Invariante de seguridad:
`shouldBuildChainContext("live", false) === false`.

## Cómo activar la economía on-chain real

1. **Interruptor maestro.** Configura `AIFACTORY_CRYPTO_ENABLED=1` en el `.env`
   del ecosistema. Valores verdaderos: `1`, `true`, `yes`, `on`. Cualquier otro
   (o sin definir) = OFF.
2. **Config por componente.** Cada componente necesita su propia config real:
   endpoints RPC, direcciones de destinatario/contrato y claves de cartera.
3. **Interbloqueos de producción.** En producción siguen aplicándose los
   gates fail-closed de `AIFACTORY_PROD` sobre el interruptor.
4. **Alien Monitor en concreto.** Despliégalo en modo LIVE para que se vincule a
   la cadena real:
   ```bash
   ALIEN_MODE=real AIFACTORY_CRYPTO_ENABLED=1 ./scripts/deploy_alien_monitor.sh --live
   ```
   En modo UNI el monitor siempre usa su Anvil local privado y nunca toca Base,
   independientemente de este interruptor.

## Cripto activado no es lo mismo que vender

El interruptor maestro habilita la maquinaria on-chain. **No** pone por sí mismo un
precio a una capacidad federada: eso es un segundo interruptor, independiente.

> [!WARNING]
> **`AIMARKET_SELLS_FOR` no está fijada por defecto, y fijarla convierte en pago,
> de golpe, 42 capacidades hoy gratuitas.** Sin fijar, el Hub no cobra nada por una
> invocación federada: no se exige canal, no se retiene importe, no se cobra
> comisión de enrutado. Con un prefijo de URL de un par listado en ella, toda
> capacidad de ese par pasa a tener precio y una invocación sin
> `X-Payment-Channel` recibe `402 payment_required`; los llamantes gratuitos
> existentes —incluido cualquier agente, puente o cliente MCP que ya las use—
> empiezan a fallar ese mismo minuto. No hay despliegue parcial ni periodo de
> gracia.

Vender en nombre de un par hay que **declararlo**, no deducirlo: un par que factura
por fuera también responde `200`, así que tratar «el par no nos cobró» como «podemos
cobrar» facturaría dos veces al comprador.

El lado del oráculo tiene su propio interruptor (`ORACLE_PAID_TIER_SECRET`), y debe
fijarse **primero**: de lo contrario el Hub exige pago por un trabajo que el oráculo
seguiría rechazando por encima de su techo gratuito. Secuencia completa y
justificación: [free-and-paid-tiers](free-and-paid-tiers.es.md).

## Seguridad

Activa el cripto solo si realmente vas a ejecutar una **economía on-chain real**
(fondos reales en Base). Dejarlo apagado es el valor por defecto seguro y
mantiene todo el ecosistema plenamente funcional en el nivel gratuito —véase
[free-and-paid-tiers](free-and-paid-tiers.es.md) para saber exactamente qué incluye
ese nivel y qué lo acota.
