# Expert Memory Market 도입 가이드

Buyer, publisher, agent integrator를 위한 실제 production 경로입니다. Public
discovery, paid delivery, publisher accounting, proof는 의도적으로 분리된 contract입니다.

## 통합 전에 access 경로 선택

- 1일 trial로 wallet transaction 없이 UX와 API 적합성을 확인합니다.
- Expert Pass는 scoped `ask_` key로 7일간 storefront를 탐색합니다.
- 각 Memory Unit을 publisher에게 귀속하고 지급해야 하면 per-read를 사용합니다.
- Pass와 publisher revenue를 섞지 마세요. Pass는 storefront, Meter capture는 split을 지원합니다.

## 구매 전에 listing 확인

Key 없이 `GET /market/v1/listings?q=<topic>`을 호출합니다. Public summary,
`rank_score`, `rank_reasons`, Truth, Provenance, price, publisher가 보입니다.
`GET /market/v1/listings/<memory_id>`는 유료 본문을 반환하지 않습니다.

Policy에 필요한 public evidence가 부족하면 거절하세요. 높은 score는 신뢰 명령이
아닙니다. Rejected claim은 unverified보다 낮고 popularity는 ranking signal이 아닙니다.

## 무료 trial로 시작

`/`를 `trial=expert-market`과 함께 열거나 setup wizard를 사용합니다. Browser가
Actor Identity를 만들고 private signing key를 로컬에 유지합니다. Gateway는
actor/product당 1회의 1일 trial을 발급합니다. `ask_`는 secret vault에 보관하고
URL, log, client analytics에 넣지 마세요.

Trial은 product fit을 확인하지만 payment, split, 영구 entitlement를 만들지 않습니다.

## Pass 또는 제공된 read 구매

Expert Pass는 `/billing?plan=expert.pass.7d`에서 정확한 invoice를 만들고 Base의
canonical USDC를 보낸 뒤 KOVA finality를 기다립니다. Gateway는 7일 key를 발급하며
checkout recovery는 48시간입니다.

Per-read는 Attested Meter account를 만들고 fund한 뒤 `amk_`를 server-side에
보관하고 `POST /market/v1/read`를 `x-meter-key`, `{"memory_id":"<id>"}`와
호출합니다. Meter는 가격을 reserve하고 content 제공 후에만 capture합니다.
실패나 거절은 reserve를 해제합니다.

## Expert memory publish 및 가격 설정

- 정확한 title, 유용한 public summary, tags, `source_refs`가 있는 Memory Unit을 만듭니다.
- 과금 전에 가능한 Truth / Provenance evidence를 추가합니다.
- 서명 identity와 Base payout address로 `POST https://meter.attestedmemory.net/v1/publishers`에 등록합니다.
- Publisher key를 비밀로 유지하고 자신의 `expert.read:<memory_id>`만 `/v1/publishers/me/prices`에서 가격화합니다.
- Buyer를 보내기 전에 public listing을 확인합니다.

Standard split은 publisher 70% / platform 30%, Publisher Pro는 85% / 15%입니다.
최소액을 넘으면 operator가 서명된 `attested.payout/v1`을 발급하고 hash를 기록합니다.

## Autonomous agent 통합

- Discovery와 purchase를 분리하고 metadata 평가 후 spend를 허용합니다.
- Maximum price, allowed publisher, Truth state, source policy를 정의합니다.
- `ask_`, `amk_`는 server secrets에 저장하고 traces에서 제거합니다.
- `401`은 credential, `402`는 access/balance, `403`은 scope, `429`는 backoff입니다.
- Listing ID, rank reasons, charge ID, provenance receipt를 결과와 저장합니다.
- Invoice는 idempotent하게 만들고 다른 금액으로 transfer를 재시도하지 않습니다.

## Team rollout

- 첫 knowledge category와 개선할 decision을 정합니다.
- Buyer 초대 전 10–20개의 고품질 listing을 준비합니다.
- Public summary와 필수 source의 최소 기준을 합의합니다.
- 성공, unknown memory, insufficient balance, upstream failure, revocation을 테스트합니다.
- Discovery-to-read, refusal, capture/release, accrual, payout backlog를 모니터링합니다.

## Trust와 money 경계 이해

Memory Market은 ranking과 entitled memory 제공, Attested Meter는 reserve,
capture, accounting, payout, Attested Prove는 key 없는 receipt verification을
담당합니다. KOVA는 authenticated service-to-service로 subscription settlement를
검증하고 federation에서도 독립적으로 사용할 수 있습니다.

Seed phrase나 wallet private key를 요구하지 않습니다. USDC는 recipient로 직접
이동하고 payout은 별도로 실행됩니다. [KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md)와
[MARKET_USE_CASES.md](MARKET_USE_CASES.md)를 참고하세요.
