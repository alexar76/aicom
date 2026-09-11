# Teste gratuito e upgrade

Personal oferece 7 dias grátis, Team 14 dias e Expert Market 1 dia. Cada actor
verificado pode ativar o teste uma vez por produto.

O navegador cria uma prova de actor Ed25519. O Gateway emite uma chave
`ask_...` sem pagamento. A chave expira automaticamente e segue as mesmas
regras de introspecção, rotação e revogação de uma chave paga.

Ao fazer upgrade, o Gateway cria uma invoice exata de USDC canônico na Base. A
KOVA verifica a transação e a nova chave paga é emitida automaticamente após as
confirmações necessárias.
