# 사용자 가이드

## 결제와 키

`/billing`에서 Personal, Team 또는 Market을 선택합니다. invoice에는 금액,
수취인, token, chain, 만료 시간이 표시됩니다. Base에서 정확한 금액을 보내고
확인 후 tx hash를 입력합니다. `ask_...` 키는 한 번만 표시됩니다. 키 관리는
`GET /v1/keys/me`, `POST /v1/keys/rotate`, `POST /v1/keys/revoke`를 사용합니다.

## identity와 memory

활성 유료 키는 `X-SaaS-Key`로 보내며 actor proof와는 별개입니다.

보호된 요청에는 `X-Actor-ID`, `X-Actor-Public-Key`, `X-Actor-Signature`가
필요합니다. private key는 클라이언트에 남습니다. 작성은 `/memory/api/memories`,
검색은 `/memory/api/search`를 사용합니다.

## 팀

`/teams/api/teams`에서 팀을 만들고 `/teams/api/teams/{team_id}/members`에서
멤버를 관리합니다. 모든 요청에 `team_id`를 포함합니다. Gateway는 membership을,
Hub는 짧은 assertion과 actor signature를 확인합니다.

`401`은 인증 오류, `403`은 scope 오류, `402`는 결제 필요, `429`는 rate limit입니다.
private key를 API로 보내지 마세요.

## 7. Trial

`/v1/trials`에서 trial을 시작합니다. Personal은 7일, Team은 14일, Expert
Market은 1일입니다. 결제 없이 한 번만 사용할 수 있는 `ask_...` 키를 발급하고
검증된 actor에 연결합니다. 기간이 끝나면 자동 만료되며, 계속 사용하려면 Base에서
정확한 USDC 결제를 완료하세요. 자세한 내용은 [TRIAL.md](TRIAL.md)입니다.
