# 사용 사례

Attested Memory는 **잊는 비용이 비싸고** **맹목적 신뢰는 더 비싼** 상황을 위한 제품입니다. 메모, 채팅 로그, vector store로는 부족한 때——그리고 identity, truth state, provenance, 정확한 settlement가 맥락을 실행 가능한 것으로 바꾸는 때——를 보여 줍니다.

라우트 이름, 헤더, 결제 용어는 모든 언어에서 그대로입니다. 설명문만 로컬라이즈합니다.

## context rot를 견디는 창업자의 세컨드 브레인

**대상.** 매일 도구·에이전트·기기 사이를 오가는 창업자, 연구자, 운영자.

**문제.** 결정은 채팅, Notion 덤프, 미완성 프롬프트에 흩어져 있습니다. 여섯 주 뒤면 *왜* 그 선택을 했는지, 어떤 소스를 믿었는지, 어떤 에이전트가 편한 요약을 만들어 냈는지 아무도 말할 수 없습니다.

**작동 방식.**

1. 결정, 근거, 태그, `source_refs`가 담긴 Memory Unit을 작성합니다.
2. actor로 서명합니다(`X-Actor-ID` / public key / signature). 개인 키는 클라이언트에 둡니다.
3. 나중에 `/memory/api/search`로 검색하고, 새 계획이나 에이전트 실행에 재사용하기 전에 truth + provenance를 확인합니다.

**attestation이 중요한 이유.** 꺼내는 것은 “비슷한 문단”이 아닙니다. actor와 lineage가 있는 이식 가능한 주장입니다.

**시작.** [Personal Memory](/memory) · [사용자 가이드](USER_GUIDE.md) · [/billing](/billing)의 trial.

## 결정 흔적이 남는 인시던트 war-room

**대상.** 온콜 엔지니어, SRE, 보안 responders.

**문제.** 장애 채널이 wiki보다 빠릅니다. 포스트모템은 기억으로 쓰이고, 각 판단의 소유권은 흐릿하며, 다음 주 에이전트는 거부된 완화를 반복합니다——공유 namespace에 서명된 것이 없었기 때문입니다.

**작동 방식.**

1. Team Memory OS workspace를 열고 team namespace를 만듭니다.
2. 멤버가 인시던트 메모, 거부된 옵션, 최종 조치를 actor 서명과 함께 작성합니다.
3. SaaS gateway가 membership을 확인하고, Hub는 일치하는 `team:<id>` 레코드만 받습니다. 쿼리가 다른 팀으로 새지 않습니다.

**attestation이 중요한 이유.** handoff가 감사 가능해집니다. offboarding으로 키를 폐기하고, 수명이 짧은 team assertions는 채팅 포렌식 없이 만료됩니다.

**시작.** [Team Memory OS](/teams) · [사용자 가이드 § Team](USER_GUIDE.md).

## 코퍼스를 유출하지 않고 팔리는 전문가 지식

**대상.** 도메인 전문가, research shops, advisory boutiques.

**문제.** 전체 코퍼스를 무료로 공개하면 사업이 죽습니다. 티저만 올리면 신뢰가 죽습니다. 구매자는 결제 전에 provenance를 봐야 하고, 판매자는 기본값으로 영구 복제가 아니라 기한 있는 접근이 필요합니다.

**작동 방식.**

1. 공개 summary 필드와 본문에 대한 유료 visibility로 Memory Unit을 게시합니다.
2. 구매자가 카탈로그를 검색하고 truth/provenance를 확인한 뒤 정확한 Base USDC invoice를 엽니다.
3. KOVA가 송금을 검증하고, Gateway가 scoped entitlement를 발급합니다. 접근은 플랜과 함께 만료됩니다.

**attestation이 중요한 이유.** discovery는 정직하고, settlement는 정확합니다. entitlement는 “명예에 기댄 PDF 링크”가 아니라 제품의 암호학적 scope입니다.

**시작.** [Expert Memory Market](/market) · [결제](/billing).

## 암호학적 연속성을 갖춘 멀티 에이전트 handoff

**대상.** 에이전트 운영자, 오케스트레이션 팀, 자율 워크플로.

**문제.** 에이전트 A가 에이전트 B에게 채팅 요약을 넘깁니다. 서명 없고, 일부 환각이며, 출처가 없습니다. 실패는 “다음 모델이 멍청했다”처럼 보이지만, 진짜 버그는 provenance의 조용한 상실입니다.

**작동 방식.**

1. 에이전트 A가 제약, 사용 도구, 출처, 미해결 위험이 담긴 서명된 handoff Memory Unit을 작성합니다.
2. 에이전트 B가 같은 actor/team 정책으로 가져와 계속하기 전에 provenance를 검증합니다.
3. truth state가 unit과 함께 이동합니다——모순은 자신만만한 문장으로 매끄럽게 다듬기지 않고 드러납니다.

**attestation이 중요한 이유.** 연속성은 탭을 열어 둔 사람의 속성이 아니라 레코드의 속성입니다.

**시작.** [Developers](/developers) · [사용자 가이드 § Actor identity](USER_GUIDE.md).

## 출처에 묶인 claims로 하는 due diligence와 조사

**대상.** 분석가, counsel, investment 및 vendor-review 팀.

**문제.** diligence 메모는 “덱”, “콜”, “Slack의 무언가”를 인용합니다. claim이 이의되면 보관 연쇄는 느낌뿐입니다.

**작동 방식.**

1. 중요한 claim마다 명시적 `source_refs`가 있는 Memory Unit으로 기록합니다.
2. 증거가 도착할 때마다 truth state를 붙이거나 갱신합니다(confirmed, disputed, insufficient).
3. 나중에 재구성된 전설이 아니라 provenance receipts로 파일을 재구성합니다.

**attestation이 중요한 이유.** 리뷰어는 “누구 메모가 더 최근인가”가 아니라 claim과 evidence를 논합니다.

**시작.** Personal 또는 Team 제품 · [용어집](GLOSSARY.md).

## 브라우저가 없어도 되는 자동 유료 접근

**대상.** wallet 앱에서 결제하는 구매자, invoice를 settle하는 스크립트, checkout 탭을 지킬 수 없는 운영자.

**문제.** 고전적인 checkout은 탭을 닫으면 죽습니다. “tx hash를 붙여 넣기” 수동 흐름은 지원 티켓과 애매한 부분 결제를 만듭니다.

**작동 방식.**

1. 고유 `Idempotency-Key`, 플랜, payer로 `POST /v1/billing/orders`.
2. Base에서 canonical USDC의 정확한 금액을 invoice 수취인에게 보냅니다.
3. KOVA가 token, payer, recipient, amount, confirmation depth를 대조합니다.
4. Gateway가 제품 키를 자동 활성화합니다. checkout token으로 `GET /v1/billing/orders/{id}`를 poll하면 confirmed 후 키가 반환됩니다——원래 브라우저 세션이 없어도.

**attestation이 중요한 이유.** 자금 이동과 entitlement 발급은 wallet 스크린샷이 아니라 정확한 invoice 동일성으로 묶입니다.

**시작.** [Billing](/billing) · [사용자 가이드 § Buy access](USER_GUIDE.md).

## 조직을 고아로 만들지 않는 안전한 offboarding

**대상.** 팀 리드, security, IT.

**문제.** 떠나는 운영자는 실제 runbook이 담긴 채팅 내보내기와 개인 메모를 여전히 갖고 있습니다. Slack을 폐기해도, 통제된 시스템에 한 번도 살지 않은 조직 기억은 폐기되지 않습니다.

**작동 방식.**

1. 운영 지식을 Team Memory OS의 명시적 namespace에 둡니다.
2. 퇴사 시 SaaS 키를 즉시 rotate/revoke합니다.
3. team assertions는 수분 내 만료되고, Hub 정책은 보호된 read/write에 계속 actor proofs를 요구합니다.

**attestation이 중요한 이유.** 접근 종료는 “누군가 Drive 폴더를 지웠겠지”가 아니라 control plane 이벤트입니다.

**시작.** [Team Memory OS](/teams).

## 적합하지 않은 용도

- 신원·출처 규율 없는 일반 채팅 아카이브.
- wallet private keys, seed phrases, 원시 credentials를 보관하는 곳.
- visibility 정책을 건너뛴 무제한 “세상과 공유” 덤프.
- 반올림·대략적인 crypto 결제——정확한 USDC 금액이 곧 invoice입니다.

저작권, 출처, 결제 최종성의 조용한 상실을 감당할 수 있다면 노트면 충분합니다. 감당할 수 없다면 위의 해당 제품 표면에서 시작하고 Hub 계약을 정확히 유지하세요.
