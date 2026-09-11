# Casos de uso

Attested Memory serve quando **esquecer custa caro** e **confiar às cegas
custa pior**. Estes cenários mostram quando uma nota, um log de chat ou um
vector store não bastam — e quando identidade, truth state, provenance e
settlement exato transformam contexto em algo sobre o qual você pode agir.

Nomes de rotas, headers e termos de pagamento permanecem exatos em todos os
idiomas. Só o texto explicativo é localizado.

## Segundo cérebro do fundador que sobrevive ao context rot

**Quem.** Um fundador, pesquisador ou operador que salta todos os dias entre
ferramentas, agentes e dispositivos.

**Problema.** Decisões vivem em chats, dumps do Notion e prompts pela metade.
Seis semanas depois ninguém consegue dizer *por que* uma escolha foi feita,
quais fontes foram confiadas ou qual agente inventou um resumo conveniente.

**Como funciona.**

1. Escreva um Memory Unit com a decisão, o racional, tags e `source_refs`.
2. Assine como actor (`X-Actor-ID` / public key / signature). A chave privada
   permanece no seu cliente.
3. Depois, busque em `/memory/api/search` e inspecione truth + provenance
   antes de reutilizar a memória em um novo plano ou execução de agente.

**Por que a attestation importa.** Você não está recuperando “um parágrafo
parecido”. Está recuperando uma afirmação portátil com um actor e uma linhagem.

**Começar.** [Personal Memory](/memory) · [Guia do usuário](USER_GUIDE.md) ·
trial em [/billing](/billing).

## War-room de incidente que preserva o rastro de decisões

**Quem.** Engenheiros on-call, SREs, responders de segurança.

**Problema.** O canal do outage anda mais rápido que a wiki. O postmortem é
escrito de memória, a autoria de cada chamada fica nebulosa, e na semana
seguinte um agente repete uma mitigação rejeitada porque nada foi assinado
em um namespace compartilhado.

**Como funciona.**

1. Abra um workspace do Team Memory OS e crie um team namespace.
2. Membros escrevem notas do incidente, opções rejeitadas e ações finais com
   assinaturas de actor.
3. O SaaS gateway verifica membership; o Hub aceita apenas registros
   `team:<id>` correspondentes. Consultas não vazam para outro time.

**Por que a attestation importa.** Handoffs tornam-se auditáveis. O
offboarding revoga a chave; team assertions de curta duração expiram sem uma
caça forense nos chats.

**Começar.** [Team Memory OS](/teams) · [Guia do usuário § Team](USER_GUIDE.md).

## Conhecimento especialista que vende sem vazar o corpus

**Quem.** Especialistas de domínio, research shops, boutiques de advisory.

**Problema.** Publicar o corpus inteiro de graça destrói o negócio. Publicar
só um teaser destrói a confiança. Compradores precisam ver provenance antes
de pagar — e vendedores precisam de acesso com prazo, não de cópias perpétuas
por padrão.

**Como funciona.**

1. Publique um Memory Unit com campos de summary públicos e visibility paga
   para o corpo.
2. Compradores buscam o catálogo, inspecionam truth/provenance e abrem um
   invoice exato em Base USDC.
3. KOVA verifica a transferência; o Gateway emite um entitlement com escopo.
   O acesso expira com o plano.

**Por que a attestation importa.** Discovery é honesto. Settlement é exato.
Entitlement é scope criptográfico do produto, não um link PDF “por palavra de
honra”.

**Começar.** [Expert Memory Market](/market) · [Pagamentos](/billing).

## Handoff multiagente com continuidade criptográfica

**Quem.** Operadores de agentes, times de orquestração, workflows autônomos.

**Problema.** O agente A despeja um resumo de chat para o agente B. O resumo
não é assinado, parcialmente alucinado e sem fontes. Falhas parecem “o
próximo modelo era burro” quando o bug real foi a perda silenciosa de
provenance.

**Como funciona.**

1. O agente A escreve um Memory Unit de handoff assinado: restrições,
   ferramentas usadas, fontes, riscos abertos.
2. O agente B recupera com a mesma política actor/team e verifica provenance
   antes de continuar.
3. O truth state viaja com a unit — contradições ficam visíveis em vez de
   serem alisadas em prosa confiante.

**Por que a attestation importa.** Continuidade é propriedade do registro,
não de quem deixou a aba aberta.

**Começar.** [Developers](/developers) ·
[Guia do usuário § Actor identity](USER_GUIDE.md).

## Due diligence e pesquisa com claims amarrados a fontes

**Quem.** Analistas, counsel, times de investment e vendor-review.

**Problema.** Notas de diligence citam “o deck”, “a call” e “algo do Slack”.
Quando um claim é contestado, a cadeia de custódia é uma sensação.

**Como funciona.**

1. Capture cada claim material como Memory Unit com `source_refs` explícitos.
2. Anexe ou atualize o truth state conforme a evidência chega (confirmed,
   disputed, insufficient).
3. Reconstrua o dossiê depois a partir de provenance receipts, não de
   folclore reconstruído.

**Por que a attestation importa.** Revisores discutem o claim e sua
evidência, não de quem as notas eram “mais recentes”.

**Começar.** Produto Personal ou Team · [Glossário](GLOSSARY.md).

## Acesso pago automatizado quando o navegador já sumiu

**Quem.** Compradores que pagam de um app de wallet, scripts que liquidam
invoices e operadores que não podem babysitar uma aba de checkout.

**Problema.** O checkout clássico morre quando a aba fecha. Fluxos manuais de
“cole o tx hash” geram tickets de suporte e pagamentos parciais ambíguos.

**Como funciona.**

1. `POST /v1/billing/orders` com um `Idempotency-Key` único, plano e payer.
2. Envie o valor exato de USDC canônico na Base para o destinatário do
   invoice.
3. KOVA confere token, payer, recipient, amount e profundidade de
   confirmação.
4. O Gateway ativa a chave do produto automaticamente. Polling
   `GET /v1/billing/orders/{id}` com o checkout token devolve a chave quando
   confirmed — mesmo se a sessão original do navegador tiver sumido.

**Por que a attestation importa.** Movimentação de dinheiro e emissão de
entitlement ficam ligados pela identidade exata do invoice, não por um
screenshot da wallet.

**Começar.** [Billing](/billing) · [Guia do usuário § Buy access](USER_GUIDE.md).

## Offboarding seguro sem deixar a instituição órfã

**Quem.** Team leads, security, IT.

**Problema.** Um operador que sai ainda tem exports de chat e notas pessoais
com os runbooks reais. Revogar o Slack não revoga memória institucional que
nunca viveu em um sistema controlado.

**Como funciona.**

1. Mantenha o conhecimento operacional no Team Memory OS sob um namespace
   explícito.
2. Rotacione ou revogue a chave SaaS imediatamente na saída.
3. Team assertions expiram em minutos; a política do Hub ainda exige actor
   proofs para reads e writes protegidos.

**Por que a attestation importa.** O acesso termina como evento do control
plane, não como a esperança de que alguém apagou uma pasta no Drive.

**Começar.** [Team Memory OS](/teams).

## Para o que isto não serve

- Um arquivo geral de chats sem disciplina de identidade ou de fontes.
- Um lugar para guardar private keys de wallets, seed phrases ou credenciais
  brutas.
- Dumps “compartilhar com o mundo” sem política de visibility.
- Pagamentos crypto arredondados ou aproximados — o valor exato de USDC é o
  invoice.

Se o seu workflow tolera perda silenciosa de autoria, fontes e finalidade de
pagamento, um caderno basta. Se não tolera, comece pela superfície de produto
correspondente acima e mantenha os contratos do Hub exatos.
