# Attested의 KOVA capabilities

## KOVA란

KOVA는 Attested Hub 내부가 아닌 독립적인 Base/USDC 서비스입니다. 6개 product를
Hub에 publish하며 agent는 federation에서 discovery, price 확인, invoke를 수행합니다.

## Agent 호출 방식

Agent는 KOVA의 private provider URL 대신 Hub의 `POST /ai-market/v2/invoke`를
호출합니다. Hub가 access와 settlement policy를 적용하고 invoke를 기록한 뒤 KOVA로
routing합니다.

Capabilities는 `kova.network.status@v1`, `kova.asset.balance@v1`,
`kova.usdc.invoice.create@v1`, `kova.usdc.invoice.status@v1`,
`kova.usdc.invoice.cancel@v1`, `kova.usdc.webhook.register@v1`입니다.

## Checkout이 다른 경로인 이유

Attested subscription은 인증된 service-to-service 연결로 KOVA invoice API를 호출합니다.
자기 결제를 검증하기 위해 paid capability를 다시 구매하지 않습니다. 따라서 recursive
billing이 없고 order 하나가 entitlement 하나만 발급합니다.

## KOVA 비용을 누가 지불하나

Attested subscription의 구매자 USDC는 `SAAS_PAYMENT_RECIPIENT`로 직접 전송됩니다.
이 transfer에는 KOVA를 위한 자동 split이나 percentage가 없습니다. Gateway는 전용
`KOVA_API_KEY`를 사용하며, 이 key가 유료 KOVA Pro 또는 Business plan에서 발급된
것이라면 operator가 별도로 구매하고 갱신합니다. Federated capability call은 별도로
측정되는 세 번째 경로입니다. Per-call price와 Hub routing fee는 capability consumption으로
기록되며 Attested subscription payment에서 차감되지 않습니다.

## 표시되는 항목

Hub는 federated invoke의 price, status, receipt를 기록합니다. 보호된 Operator ledger는
Attested order, trial/paid key, request 수를 표시합니다. KOVA Settlement desk는 KOVA의
order, key prefix, API usage를 보여 주며 전체 key는 표시하지 않습니다.

## 보안 경계

Provider route는 private `X-AIMarket-Internal-Token`을 요구하고 route/body identity를
검사하며 write를 더 엄격하게 제한합니다. `X-Provider-Signature`는 Ed25519로
`product_id`, `capability_id`, input hash, result를 결합해 다른 input으로의 replay를 막습니다.

## 안전한 설정

32자 이상의 무작위 `KOVA_CAPABILITY_TOKEN`을 Hub의 `AIMARKET_CAPABILITY_TOKEN`과
같게 설정합니다. `KOVA_HUB_URL`, `KOVA_INVOKE_BASE`를 지정하고 provider endpoint는
private service network에 둡니다.
