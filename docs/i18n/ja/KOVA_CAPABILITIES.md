# Attested の KOVA capabilities

## KOVA とは

KOVA は独立した Base / USDC サービスで、Attested Hub 内にはありません。6つの
product を Hub に公開し、agent は federation から discovery、price、invoke できます。

## Agent からの呼び出し

Agent は KOVA の private provider URL ではなく Hub の
`POST /ai-market/v2/invoke` を呼びます。Hub が access と settlement policy を適用し、
invoke を記録して KOVA に routing します。

Capabilities は `kova.network.status@v1`、`kova.asset.balance@v1`、
`kova.usdc.invoice.create@v1`、`kova.usdc.invoice.status@v1`、
`kova.usdc.invoice.cancel@v1`、`kova.usdc.webhook.register@v1` です。

## Checkout が別経路である理由

Attested subscription は認証済み service-to-service 接続で KOVA invoice API を呼びます。
自身の購入を検証するために paid capability を買いません。recursive billing を防ぎ、
1 order が 1 entitlement だけを発行します。

## KOVA の費用を誰が負担するか

Attested subscription の購入 USDC は `SAAS_PAYMENT_RECIPIENT` に直接送られます。
この transfer に KOVA 向けの自動 split や percentage はありません。Gateway は専用の
`KOVA_API_KEY` を使います。その key が有料 KOVA Pro / Business plan 由来なら、operator
が別途購入・更新します。Federated capability call は独立して計測される第3の経路で、
per-call price と Hub routing fee は capability consumption として記録され、Attested の
subscription payment から差し引かれることはありません。

## 表示される利用情報

Hub は federated invoke の price、status、receipt を記録します。保護された Operator
ledger は Attested の order、trial/paid key、request 数を表示します。KOVA Settlement
desk は KOVA の order、key prefix、API usage を表示し、完全な key は表示しません。

## Security boundary

Provider route は private `X-AIMarket-Internal-Token` を要求し、route/body identity を
照合し、write を厳しく rate limit します。`X-Provider-Signature` は Ed25519 で
`product_id`、`capability_id`、input hash、result を結び、別 input への replay を防ぎます。

## 安全な設定

32文字以上のランダムな `KOVA_CAPABILITY_TOKEN` を Hub の
`AIMARKET_CAPABILITY_TOKEN` と同じ値にします。`KOVA_HUB_URL` と
`KOVA_INVOKE_BASE` を設定し、provider endpoint は private network 内に置きます。
