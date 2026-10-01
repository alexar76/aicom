# Capabilities KOVA no Attested

## O que é KOVA

KOVA é um serviço independente para Base e USDC; não roda dentro do Attested Hub.
Ele publica seis produtos no Hub para descoberta, preço e invoke pela federação.

## Como o agente chama

O agente chama o Hub em `POST /ai-market/v2/invoke`, não a URL privada da KOVA.
O Hub aplica acesso e settlement, registra o invoke e roteia a solicitação.

As capabilities são `kova.network.status@v1`, `kova.asset.balance@v1`,
`kova.usdc.invoice.create@v1`, `kova.usdc.invoice.status@v1`,
`kova.usdc.invoice.cancel@v1` e `kova.usdc.webhook.register@v1`.

## Por que checkout usa outra rota

A assinatura Attested chama a API de invoices da KOVA por conexão service-to-service
autenticada. Ela não compra uma capability paga para verificar o próprio pagamento.
Isso evita billing recursivo e mantém um entitlement por pedido.

## Quem paga a KOVA

Uma assinatura Attested envia o USDC do comprador diretamente para
`SAAS_PAYMENT_RECIPIENT`. Essa transferência não contém split nem percentual
automático para a KOVA. O Gateway usa uma `KOVA_API_KEY` dedicada; se ela vier de um
plano KOVA Pro ou Business pago, o operador compra ou renova o plano separadamente.
As chamadas federadas de capabilities formam um terceiro fluxo medido: o preço por
chamada e a routing fee do Hub são registrados como consumo e nunca descontados do
pagamento da assinatura Attested.

## O que fica visível

O Hub registra preço, status e receipt do invoke federado. O Operator ledger mostra
pedidos, chaves trial/paid e requests Attested. O Settlement desk KOVA mostra pedidos,
prefixos e uso da API. Nenhum deles lista chaves completas.

## Limite de segurança

A rota exige `X-AIMarket-Internal-Token`, confere identidade da rota/body e limita
escritas com rigor. `X-Provider-Signature` assina com Ed25519 `product_id`,
`capability_id`, hash do input e result, impedindo replay em outro input.

## Configuração segura

Use `KOVA_CAPABILITY_TOKEN` aleatório com 32+ caracteres, igual a
`AIMARKET_CAPABILITY_TOKEN` do Hub. Configure `KOVA_HUB_URL` e `KOVA_INVOKE_BASE` e
mantenha endpoints do provider na rede privada.
