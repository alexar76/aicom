# Guia de implementação do Expert Memory Market

Este guia cobre os caminhos reais de production para compradores, publishers e
integradores de agentes. Descoberta pública, entrega paga, contabilidade do
publisher e prova são contratos separados de propósito.

## Escolha o acesso antes de integrar

- Use o trial de 1 dia para validar UX e API sem transação da wallet.
- Use Expert Pass para sete dias de exploração com uma chave `ask_` restrita.
- Use pagamento por leitura quando cada Memory Unit entregue deve remunerar seu publisher.
- Não misture o pass com receita do publisher: o pass financia a vitrine; o capture do Meter financia a divisão.

## Inspecione antes de comprar

Chame `GET /market/v1/listings?q=<tema>` sem chave. Cada item mostra resumo,
`rank_score`, `rank_reasons`, Truth, Provenance, preço e publisher.
`GET /market/v1/listings/<memory_id>` nunca devolve o corpo pago.

Recuse listings sem evidência pública suficiente. Score alto não é ordem para
confiar: examine os motivos. Claim rejeitado fica abaixo de não verificado e
popularidade não é sinal de ranking.

## Comece no trial gratuito

Abra `/` com `trial=expert-market` ou use o assistente. O navegador cria a
identity do actor e mantém a private signing key local. O Gateway emite um trial
de 1 dia por actor/produto. Guarde `ask_` em secret vault, nunca em URL, log ou
analytics do cliente.

O trial valida o produto, mas não cria transação, publisher split ou entitlement permanente.

## Compre pass ou leitura entregue

Para Expert Pass, abra `/billing?plan=expert.pass.7d`, crie a invoice exata,
envie canonical USDC na Base e aguarde a finality da KOVA. O Gateway emite uma
chave por sete dias; a recuperação do checkout dura 48 horas.

Para per-read, crie e financie uma conta no Attested Meter, mantenha `amk_` no
servidor e chame `POST /market/v1/read` com `x-meter-key` e
`{"memory_id":"<id>"}`. Meter reserva o preço e só faz capture após a entrega;
falha ou recusa libera a reserva.

## Publique memória especialista e defina preço

- Crie uma Memory Unit com título preciso, resumo público útil, tags e `source_refs`.
- Adicione evidência Truth e Provenance antes de cobrar quando possível.
- Registre-se em `POST https://meter.attestedmemory.net/v1/publishers` com identity assinada e endereço Base.
- Mantenha a chave privada e precifique apenas `expert.read:<memory_id>` próprio em `/v1/publishers/me/prices`.
- Verifique o listing por `GET /market/v1/listings` antes de enviar compradores.

A divisão padrão é 70% publisher / 30% plataforma; Publisher Pro muda para
85% / 15%. Acima do mínimo, o operador emite `attested.payout/v1` assinado e
registra o hash.

## Integre um agente autônomo

- Separe descoberta e compra; autorize gasto após avaliar metadata.
- Defina preço máximo, publishers aceitos, Truth states e política de fontes.
- Guarde `ask_` e `amk_` em secrets de servidor e remova-os de traces.
- Trate `401` como credencial inválida, `402` como acesso/saldo, `403` como scope e `429` como backoff.
- Salve listing ID, rank reasons, charge ID e provenance receipt junto do resultado.
- Use idempotency nas invoices e não repita transferência com valor inventado.

## Implante em uma equipe

- Defina uma categoria inicial e a decisão que ela melhora.
- Publique 10–20 listings de alta qualidade antes de convidar compradores.
- Combine resumo público mínimo e fontes obrigatórias.
- Teste read correto, memory ausente, saldo insuficiente, falha upstream e revogação.
- Meça discovery-to-read, recusas, capture/release, accrual e backlog de payouts.

## Respeite limites de confiança e dinheiro

Memory Market classifica e entrega memory autorizada. Attested Meter controla
reserva, capture, contabilidade e payouts. Attested Prove torna recibos e
provenance verificáveis sem compartilhar chave. KOVA verifica settlement exato
por service-to-service autenticado e continua disponível por federação.

Nenhum componente pede seed phrase ou private key. USDC da assinatura vai
direto ao destinatário e payouts são executados à parte. Veja
[KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md) e [MARKET_USE_CASES.md](MARKET_USE_CASES.md).
