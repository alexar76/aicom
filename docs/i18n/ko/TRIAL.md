# 무료 트라이얼과 업그레이드

Personal은 7일, Team은 14일, Expert Market은 1일 무료 트라이얼을 제공합니다.
검증된 actor는 제품별로 한 번만 활성화할 수 있습니다.

브라우저가 Ed25519 actor proof를 만들고 Gateway가 결제 없이 `ask_...` 키를
발급합니다. 키는 자동 만료되며 유료 키와 동일한 introspection, rotation,
revoke 규칙을 적용합니다.

업그레이드하면 Gateway가 Base의 canonical USDC 정확한 invoice를 만들고,
KOVA가 거래를 확인한 뒤 필요한 confirmations 후 유료 키를 자동 발급합니다.
