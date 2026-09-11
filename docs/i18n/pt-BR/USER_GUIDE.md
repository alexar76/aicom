# Guia do usuário

## Pagamento e chave

Em `/billing`, escolha Personal, Team ou Market. A invoice informa valor, recebedor,
token, chain e validade. Envie o valor exato na Base, aguarde as confirmações e
cole o tx hash. A chave paga `ask_...` pode ser recuperada com o segredo de
checkout por 48 horas; depois disso, apenas o hash permanece. O Gateway reconcilia
o pagamento automaticamente mesmo com o navegador fechado.

Consulte `GET /v1/keys/me`, faça rotação com `POST /v1/keys/rotate` e revogue com
`POST /v1/keys/revoke`.

## Identidade e memória

Envie a chave paga ativa como `X-SaaS-Key`; ela é separada da prova do actor.

Requisições protegidas exigem `X-Actor-ID`, `X-Actor-Public-Key` e
`X-Actor-Signature`. A chave privada fica no seu cliente. Escreva em
`/memory/api/memories` e pesquise em `/memory/api/search`.

## Equipes

Crie a equipe em `/teams/api/teams`, adicione membros em
`/teams/api/teams/{team_id}/members` e envie `team_id` em toda operação.
O Gateway valida membership e o Hub valida a assertion curta e a assinatura.

`401` é credencial inválida; `403`, scope incorreto; `402`, pagamento necessário;
`429`, limite de requisições. Nunca envie chaves privadas.

## Trial

Solicite o trial em `/v1/trials`: Personal dura 7 dias, Team 14 dias e Expert
Market 1 dia. O Gateway entrega uma chave `ask_...` vinculada ao actor sem pagamento;
o mesmo actor assinado pode recuperá-la enquanto estiver ativa. O acesso expira automaticamente; para continuar,
faça o pagamento exato de USDC na Base. Veja [TRIAL.md](TRIAL.md).

## Capabilities KOVA e checkout

Agentes descobrem KOVA pela federação do Hub; o checkout Attested usa uma rota
service-to-service autenticada e separada. Os dois fluxos e seus limites estão em
[KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md).
