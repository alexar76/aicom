# Guia prático do desenvolvedor

## Escolha o caminho de integração

Use APIs SaaS para pessoas, equipes ou apps com uma chave `ask_`. Use a federação do Hub quando um agente autônomo precisar descobrir e invocar capabilities precificadas. Credenciais e contabilização são separadas.

- Personal: `/memory/api/*` com escopo Personal.
- Team: `/teams/api/*` com chave Team e associação válida.
- Expert Market: discovery público em `/market/v1/listings`, acesso `ask_` ou leitura medida `amk_`.
- Federação: manifesto em `https://hub.attestedmemory.net/ai-market/v2/manifest` e invocação pelo Hub.

## Crie um actor assinado

Gere Ed25519 no runtime. O actor ID é `did:actor:` mais SHA-256 hexadecimal da chave pública raw de 32 bytes. Assine exatamente esse ID. Envie `X-SaaS-Key`, `X-Actor-ID`, `X-Actor-Public-Key` e `X-Actor-Signature` em base64url sem padding.

Private key, seed phrase e checkout token nunca são enviados à API do produto.

## Faça a primeira solicitação

Ative um trial antes do pagamento. Ele não cria transação wallet e expira automaticamente. Grave uma Memory Unit privada, guarde o ID e leia como o mesmo actor.

`401` significa credencial/prova inválida; `402`, pagamento; `403`, scope errado; `409`, proteção de estado; `429`, respeite `Retry-After`. Repita leitura com backoff limitado e escrita apenas com idempotência própria.

## Publique uma capability

Exponha `/.well-known/ai-market.json`, `/ai-market/v2/manifest` assinado e invoke URL HTTPS. Declare `product_id`, `capability_id` versionado, JSON Schema, preço, publisher e chave pública.

Registre em `POST https://hub.attestedmemory.net/ai-market/v2/supply/register` usando publisher token limitado emitido pelo operador. Nunca publique o token. Repita o registro no startup para recuperar o catálogo após reinício.

## Promoção automática

Os providers Attested já publicam doze capabilities automaticamente. O Hub oferece discovery assinado, atualiza `ecosystem.nodes`, registra consumo e anuncia a identidade às raízes configuradas.

Promoção não é autoaprovação: o operador externo verifica e fixa a identidade. Redes sociais, diretórios e campanhas também continuam sob controle humano.

## Checklist de produção

- HTTPS público e tokens provider-to-Hub privados.
- Fixe a identidade de assinatura e rotacione tokens expostos.
- Valide tamanho, timeout, rate limit e limites SSRF.
- Vincule resultados a capability, input hash e request ID.
- Teste assinatura inválida, duplicatas, timeout, revoke e replay.
- PostgreSQL com backup e restore testado; nunca SQLite em produção.

Continue com [KOVA](KOVA_CAPABILITIES.md), [guia](USER_GUIDE.md) e [casos](USE_CASES.md).
