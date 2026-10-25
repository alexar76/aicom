# Cinco monederos pagaron a un vendedor x402. ¿Qué podemos decir de la demanda?

Declaración: mantengo HISTOR y AIMarket en el ecosistema alexar76. El análisis, su implementación y este artículo se prepararon con ayuda sustancial de IA generativa. Código determinista produjo los recuentos y las comprobaciones de transferencias; ningún modelo dedujo las identidades de los monederos. Un pago de investigación fue nuestro y se identifica abajo.

Tras nuestro estudio de entrega de servicios x402, [Martin Pisacreta informó](https://dev.to/alexar76/we-tried-to-buy-one-call-from-100-x402-sellers-most-delivered-almost-nobody-is-buying-2498#comment-3ioef) de que el único pagador recurrente de textokit parecía enviar el inputExample publicado de `normativa-ar`. Preguntó si HISTOR podía marcar monederos cuya actividad pareciera un barrido. Implementamos una auditoría local y comprobamos los cinco pagadores externos. El resultado útil es una tabla de pruebas con incógnitas explícitas.

## Los importes de los pagos se confirman

El [registro público del vendedor](https://tienda.textokit.store/receipts.json), obtenido el **25 de octubre de 2026 a las 05:16:44 UTC**, contenía **80 ventas liquidadas**: 56 marcadas por el editor como pagos de sus propios monederos y **24 ventas externas de cinco monederos**, por un total de **0,055000 USDC**. Las marcas de propiedad son afirmaciones de la fuente, no identidades verificadas de forma independiente.

Las **24 entradas externas** coincidieron con recibos de transacciones exitosas de Base que contenían un USDC Transfer oficial del pagador indicado al vendedor por el importe exacto declarado. Esto verifica la liquidación. No verifica la entrega del servicio ni el motivo del pago. El registro cambia; estas cifras corresponden a una instantánea.

Como contexto, examinamos las transferencias salientes de USDC de estas cinco direcciones entre el **11 de octubre de 2026 a las 05:23:11 UTC y el 25 de octubre de 2026 a las 05:23:11 UTC**: bloques **52453422–53058222**. Los **605 intervalos consecutivos de registros** se completaron correctamente y devolvieron **23.254 eventos brutos**. Se excluyeron dos eventos de valor cero de las métricas de comportamiento. La recopilación terminó a las 05:27:36 UTC. El bloque superior elegido estaba doce bloques por detrás de la cabecera inicial del nodo y su hash se mantuvo estable.

## Qué muestran los cinco monederos

Las direcciones enlazan a sus páginas públicas del explorador. «Destinatarios» significa direcciones distintas que recibieron USDC, no necesariamente comerciantes ni servicios x402. Los recuentos de transferencias salientes excluyen los dos eventos de valor cero.

| Monedero | Ventas textokit | USDC | Transferencias salientes / destinatarios | Destinatarios con un solo pago | Transferencias ≤0,01 USDC | Etiqueta |
|---|---:|---:|---:|---:|---:|---|
| [0x097e…475a](https://basescan.org/address/0x097e3f339d0b023605e12a6b81e2d6cb7571475a) | 1 | 0,001000 | 5 / 4 | 3 (75,0%) | 1 (20,0%) | `known-probe` |
| [0x7722…5e4a](https://basescan.org/address/0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a) | 1 | 0,001000 | 1.262 / 1.010 | 909 (90,0%) | 1.051 (83,3%) | `unknown` |
| [0xa1d1…1978](https://basescan.org/address/0xa1d1c0cf717402ff3651aa4873ccf96410b01978) | 1 | 0,001000 | 1.896 / 1.632 | 1.416 (86,8%) | 1.449 (76,4%) | `unknown` |
| [0xc9c7…1670](https://basescan.org/address/0xc9c7b38c0942914fc8ea12063bc92dcd3b581670) | 1 | 0,001000 | 1.979 / 730 | 442 (60,5%) | 1.518 (76,7%) | `unknown` |
| [0xec2a…d034](https://basescan.org/address/0xec2abd3eda89bed90124736e317e847d5fb6d034) | 20 | 0,051000 | 18.110 / 648 | 217 (33,5%) | 16.320 (90,1%) | `probe-like` |

**0x097e…475a fue nuestra prueba de investigación.** Su única compra de `x402-ping`, por 0,001 USDC el 20 de octubre, coincide con la transacción registrada en nuestro estudio. La etiqueta se aplica a esa compra, no a toda acción futura de la dirección.

**0xec2a…d034 realizó veinte compras en diecisiete servicios**, incluidas cuatro compras de `normativa-ar`, entre el 20 y el 24 de octubre. Martin informa de que envía el inputExample publicado. Asociamos su declaración con esas cuatro filas del registro por servicio y hora. El contenido de las solicitudes no es público, por lo que no verificamos de forma independiente las coincidencias exactas de entrada por transacción. Esto respalda un indicio `probe-like` atribuido a la fuente; no establece la identidad de un monitor. Sin esa anotación, la etiqueta automática estricta es `unknown`.

**Los otros tres monederos muestran una amplia distribución de pagos pequeños, con intención desconocida.** Los dos primeros alcanzaron 1.010 y 1.632 destinatarios. Nuestra descripción anterior de «más de mil» se sostiene, pero «casi todos» debe sustituirse por las fracciones exactas de la tabla. El tercero alcanzó 730 destinatarios y repitió destinatarios con más frecuencia. Sus compras individuales de 0,001 USDC en textokit no demuestran ni un flujo de trabajo orgánico ni monitorización.

## La función existe; las etiquetas siguen siendo prudentes

El comando local, **todavía no publicado**, `histor payer-audit` acepta recibos públicos, datos opcionales de la cadena para un período acotado y anotaciones de fuentes vinculadas a transacciones. Exporta JSON y Markdown con hashes de entrada, período de observación, métricas por pagador, política, referencias de liquidación y límites de cobertura. No necesita claves de monederos ni una base de datos de producción. Su recolector permite cinco métodos RPC de lectura y nunca envía transacciones ni solicitudes de pago a servicios.

La heurística inicial de distribución amplia exige al menos **50 transferencias**, **50 destinatarios**, **90% de destinatarios con un solo pago** y **90% de transferencias de como máximo 0,01 USDC**. Estos umbrales sin calibrar se fijaron antes de examinar las métricas recopiladas y no se redujeron para forzar una etiqueta. Las señales descriptivas siguen visibles cuando no se cumple la regla conjunta.

El resultado es una prueba conocida, un caso probe-like anotado según la fuente y tres casos desconocidos. **Unknown no significa comprador confirmado. Probe-like no significa fraude ni uso sin valor.** La monitorización de pago puede ser, por sí misma, un uso real. Los **0,055000 USDC permanecen en los totales de pagos**, independientemente de las etiquetas.

Estas observaciones no determinan el número de clientes orgánicos de textokit, su rentabilidad, la entrega de servicios ni la propiedad de los monederos. Las comprobaciones RPC confían en el nodo Base seleccionado; no son pruebas de la cadena verificadas localmente. La mejora práctica es más acotada: liquidación, comportamiento y afirmaciones atribuidas tienen campos separados, para que un recuento de recibos no se convierta silenciosamente en un recuento de clientes.

## Referencias públicas de liquidación

Las siguientes 24 transacciones públicas corresponden a las entradas externas verificadas del registro y están agrupadas por pagador. Los importes se expresan en USDC. El [registro actual](https://tienda.textokit.store/receipts.json) y los enlaces del explorador son fuentes primarias; las métricas de comportamiento de catorce días anteriores corresponden al período fijo de observación.

### 0x097e3f339d0b023605e12a6b81e2d6cb7571475a

- [0x62c01526…](https://basescan.org/tx/0x62c01526c5beb13cad96634ec80e837e576df496905f1bac8019c6ffa3e358c3) — 0.001000 USDC

### 0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a

- [0x8d2ccd6a…](https://basescan.org/tx/0x8d2ccd6a3e04a769ecc680f298999dd082a0a2eba936f00a96c0e4ec5902b934) — 0.001000 USDC

### 0xa1d1c0cf717402ff3651aa4873ccf96410b01978

- [0x58ddb2e7…](https://basescan.org/tx/0x58ddb2e77e574ddda75fd74df6f3dbf94e2795e22c36f8a01a506c544ff4ada3) — 0.001000 USDC

### 0xc9c7b38c0942914fc8ea12063bc92dcd3b581670

- [0x3ca4f279…](https://basescan.org/tx/0x3ca4f2791f4f851a574f4abd7cb949e1b05fb00dadeb77b83fb3d0e36a608fb2) — 0.001000 USDC

### 0xec2abd3eda89bed90124736e317e847d5fb6d034

- [0x8c0acafc…](https://basescan.org/tx/0x8c0acafc219977d53b7431c734b1d29b7ef6db90cab5091c7aabe4a0f69a2c0a) — 0.005000 USDC
- [0xef5f2a2c…](https://basescan.org/tx/0xef5f2a2c81b7f6021c73a966eceb453055481a333256a2475a8ac8f011183ffd) — 0.002000 USDC
- [0xcc3231d1…](https://basescan.org/tx/0xcc3231d1e3d39a27838c4e3fbb87db85fb61da5048c49690e5511e844fc83b7e) — 0.005000 USDC
- [0xa7662362…](https://basescan.org/tx/0xa7662362f207a4d0059b32c1204f1171fa7ec7fae9b8567b9ef7cc6cd1f37885) — 0.005000 USDC
- [0xd197a66a…](https://basescan.org/tx/0xd197a66ab0eb069c0acfddfd280dcefe123ec576878d1a924f5407e8f87afda9) — 0.003000 USDC
- [0x68a7bb46…](https://basescan.org/tx/0x68a7bb46a2839d40c1001e1bf1dab036abb849939203e7a4131183581158d8ce) — 0.002000 USDC
- [0x4f712436…](https://basescan.org/tx/0x4f712436cfe5bb039f55d2a536a484b2847e5e29cb86edc97ec6c33552bd9c13) — 0.002000 USDC
- [0x9fe21127…](https://basescan.org/tx/0x9fe21127d045e4398ca6b9d6889241a15c861f7f08d812d7ef66e1846e8cfe04) — 0.002000 USDC
- [0x23207988…](https://basescan.org/tx/0x23207988c28a9bd13e4d2fcd3dffd4e1ae47594077802890ca57fafeb4215bb0) — 0.001000 USDC
- [0x0e65e22c…](https://basescan.org/tx/0x0e65e22cea86dadeeb4bb1736f94bd8f28538011e8024c98eb4d4fc7d25d4121) — 0.001000 USDC
- [0x56eafab5…](https://basescan.org/tx/0x56eafab52aa8a3889b97ba4a013ea3f508cafa934c0acb7958bbd3ec43d78bb6) — 0.001000 USDC
- [0x55049b03…](https://basescan.org/tx/0x55049b036d022dc9970490abbdf079d70bf15f8afdf35f65782472b8f115ef89) — 0.001000 USDC
- [0x6322b987…](https://basescan.org/tx/0x6322b987ed57b94367753a7cfdb4bb1b31bf9efaf183d2ccf0036a057c75959f) — 0.005000 USDC
- [0x415ec0e3…](https://basescan.org/tx/0x415ec0e389ce17a9936de89a28b7ba0fc1717b2f50e756196e074851d712bd9b) — 0.001000 USDC
- [0x4feb47e1…](https://basescan.org/tx/0x4feb47e132ac06e7b5081756cdfb8b6b5436fae1ab62701d04139982b74f0186) — 0.001000 USDC
- [0x9bb91375…](https://basescan.org/tx/0x9bb91375a64c6da4a5fc78e8df817fe86b51487a36c3c98a73a78513edd4d637) — 0.001000 USDC
- [0x3bc01e29…](https://basescan.org/tx/0x3bc01e29b53d187320b18bd1794526c85b8addc456fc0e8e7756fd17fd971ea6) — 0.001000 USDC
- [0x068b1930…](https://basescan.org/tx/0x068b1930266c6235ee31cbfa87690b8ef14c519bba4f1dafd0b36872b836fe95) — 0.002000 USDC
- [0x4700749e…](https://basescan.org/tx/0x4700749eb35c98129e0abc6adb2f9ee66d76dc7bc8ba2e509341f858146d35d6) — 0.005000 USDC
- [0xf93149b9…](https://basescan.org/tx/0xf93149b946d87295924977c2d46f76f163b4d93354bc3fa7aa1f5c04e392736d) — 0.005000 USDC

