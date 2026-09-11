# 開発者フィールドガイド

## 統合経路を選ぶ

人、チーム、アプリが `ask_` key で利用する場合は SaaS product API を使います。自律 agent が価格付き capability を発見・invoke する場合は Hub federation を使います。Credential と accounting は別経路です。

- Personal: Personal scope の `/memory/api/*`。
- Team: Team key と有効な membership を使う `/teams/api/*`。
- Expert Market: `/market/v1/listings` の公開 discovery、`ask_` access、または `amk_` metered read。
- Federation: `https://hub.attestedmemory.net/ai-market/v2/manifest` で discovery、Hub 経由で invoke。

## 署名済み actor を作成

Client runtime 内で Ed25519 key pair を生成します。Actor ID は `did:actor:` と raw 32-byte public key の SHA-256 hex を連結した値です。その完全な actor ID を署名します。`X-SaaS-Key`、`X-Actor-ID`、`X-Actor-Public-Key`、`X-Actor-Signature` を padding なし base64url で送ります。

Private key、seed phrase、checkout token を product API に送ってはいけません。

## 最初の request

Payment 統合前に trial を有効化します。Wallet transaction は発生せず、自動で期限切れになります。Private Memory Unit を1件書き込み、返された ID を保存し、同じ actor で読み戻します。

`401` は credential/proof、`402` は payment、`403` は scope、`409` は state/idempotency、`429` は `Retry-After` を示します。Read は bounded backoff、write は自分の idempotency がある場合だけ再試行します。

## Capability を公開

`/.well-known/ai-market.json`、署名済み `/ai-market/v2/manifest`、HTTPS invoke URL を公開します。`product_id`、versioned `capability_id`、JSON Schema、価格、publisher identity、public key を宣言します。

Operator が発行した scoped publisher token を使い、`POST https://hub.attestedmemory.net/ai-market/v2/supply/register` に登録します。Token は公開しません。Startup 時に再登録して Hub restart 後も catalog を回復させます。

## 自動 promotion

Attested provider は12の capabilities を自動公開しています。Hub は署名 discovery、`ecosystem.nodes`、consumption record、設定済み federation root への announcement を提供します。

Promotion は自己承認ではありません。外部 operator が identity を確認・pin して trust を与えます。Social、directory、campaign も operator 管理です。

## Production checklist

- Public endpoint は HTTPS、provider-to-Hub token は非公開。
- Signing identity を pin し、漏えい時は token を rotate。
- Size、timeout、rate limit、SSRF boundary を検証。
- Result を capability、input hash、request ID に結合。
- Invalid signature、duplicate、timeout、revoke、replay を test。
- PostgreSQL backup と restore を検証し、production で SQLite を使わない。

次へ: [KOVA](KOVA_CAPABILITIES.md)、[ユーザーガイド](USER_GUIDE.md)、[ユースケース](USE_CASES.md)。
