# 개발자 필드 가이드

## 연동 경로 선택

사람, 팀, 앱이 `ask_` key로 접근할 때는 SaaS product API를 사용합니다. 자율 agent가 가격이 있는 capability를 발견하고 invoke해야 할 때는 Hub federation을 사용합니다. Credential과 accounting 경로는 분리됩니다.

- Personal: Personal scope key와 `/memory/api/*`.
- Team: Team key, 유효한 membership과 `/teams/api/*`.
- Expert Market: `/market/v1/listings` public discovery, `ask_` access 또는 `amk_` metered read.
- Federation: `https://hub.attestedmemory.net/ai-market/v2/manifest`에서 discovery하고 Hub를 통해 invoke.

## 서명된 actor 생성

Client runtime에서 Ed25519 key pair를 만듭니다. Actor ID는 `did:actor:` 뒤에 raw 32-byte public key의 SHA-256 hex를 붙인 값입니다. 정확한 actor ID 문자열을 서명합니다. `X-SaaS-Key`, `X-Actor-ID`, `X-Actor-Public-Key`, `X-Actor-Signature`를 padding 없는 base64url로 보냅니다.

Private key, seed phrase, checkout token은 product API로 보내지 않습니다.

## 첫 request 실행

Payment 연동 전에 trial을 활성화하세요. Wallet transaction 없이 시작하고 자동 만료됩니다. Private Memory Unit 하나를 기록하고 반환된 ID를 저장한 뒤 같은 actor로 읽습니다.

`401`은 credential/proof 오류, `402`는 payment 필요, `403`은 잘못된 scope, `409`는 state/idempotency 보호, `429`는 `Retry-After` 준수를 뜻합니다. Read는 bounded backoff로, write는 자체 idempotency가 있을 때만 재시도합니다.

## Capability 게시

`/.well-known/ai-market.json`, 서명된 `/ai-market/v2/manifest`, HTTPS invoke URL을 제공합니다. `product_id`, versioned `capability_id`, JSON Schema, 가격, publisher identity, public key를 선언합니다.

Operator가 발급한 scoped publisher token으로 `POST https://hub.attestedmemory.net/ai-market/v2/supply/register`에 등록합니다. Token을 공개하지 마세요. Startup에서 재등록해 Hub restart 후 catalog를 복구합니다.

## 자동 promotion

Attested provider는 이미 12개 capabilities를 자동 게시합니다. Hub는 서명 discovery, `ecosystem.nodes`, consumption 기록, 설정된 federation root announcement를 제공합니다.

Promotion은 자기 승인이 아닙니다. 외부 operator가 identity를 확인하고 pin해야 trust가 생깁니다. Social, directory, campaign도 operator 제어입니다.

## Production checklist

- Public endpoint는 HTTPS, provider-to-Hub token은 비공개.
- Signing identity를 pin하고 노출된 token을 rotate.
- Size, timeout, rate limit, SSRF boundary 검증.
- Signed result를 capability, input hash, request ID에 결합.
- Invalid signature, duplicate, timeout, revoke, replay test.
- PostgreSQL backup과 restore 검증, production SQLite 금지.

다음: [KOVA](KOVA_CAPABILITIES.md), [사용자 가이드](USER_GUIDE.md), [사용 사례](USE_CASES.md).
