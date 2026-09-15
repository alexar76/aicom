# Expert Memory Market 導入ガイド

Buyer、publisher、agent integrator の production 経路を説明します。Public
discovery、paid delivery、publisher accounting、proof は意図的に分離された
contract です。

## 統合前に access 経路を選ぶ

- 1日 trial で wallet transaction なしに UX と API の適合を確認します。
- Expert Pass は scoped `ask_` key で7日間 storefront を探索できます。
- Memory Unit ごとに publisher へ帰属・支払いする場合は per-read を使います。
- Pass と publisher revenue を混同しないでください。Pass は storefront、Meter capture は publisher split を支えます。

## 購入前に listing を確認する

Key なしで `GET /market/v1/listings?q=<topic>` を呼び出します。Public summary、
`rank_score`、`rank_reasons`、Truth、Provenance、price、publisher が表示されます。
`GET /market/v1/listings/<memory_id>` は有料本文を返しません。

自分の policy に対して公開 evidence が足りない listing は拒否します。高い
score は信頼命令ではありません。Rejected claim は unverified より低く、
popularity は ranking signal ではありません。

## 無料 trial から始める

`/` を `trial=expert-market` 付きで開くか、setup wizard を使います。Browser
が Actor Identity を作成し private signing key をローカルに保持します。
Gateway は actor/product ごとに1回の1日 trial を発行します。`ask_` key は
secret vault に保存し、URL、log、client analytics に入れないでください。

Trial は product fit を確認しますが、payment、split、永久 entitlement は作りません。

## Pass または配信された read を購入する

Expert Pass は `/billing?plan=expert.pass.7d` で正確な invoice を作り、Base 上の
canonical USDC を送信して KOVA finality を待ちます。Gateway が7日間の key
を発行し、checkout recovery は48時間利用できます。

Per-read は Attested Meter account を作成・fund し、`amk_` を server-side に
保持して `POST /market/v1/read` を `x-meter-key` と
`{"memory_id":"<id>"}` で呼びます。Meter は価格を reserve し、content 配信後
だけ capture します。失敗・拒否時は reserve を解放します。

## Expert memory を publish して価格を設定する

- 正確な title、役立つ public summary、tags、`source_refs` を持つ Memory Unit を作成します。
- 課金前に可能な Truth / Provenance evidence を追加します。
- 署名済み identity と Base payout address で `POST https://meter.attestedmemory.net/v1/publishers` に登録します。
- Publisher key は秘密にし、自分の `expert.read:<memory_id>` だけを `/v1/publishers/me/prices` で価格設定します。
- Buyer を案内する前に public listing を確認します。

Standard split は publisher 70% / platform 30%、Publisher Pro は 85% / 15% です。
最低額を超えると operator が署名済み `attested.payout/v1` を発行し hash を記録します。

## Autonomous agent を統合する

- Discovery と purchase を分離し、metadata 評価後に spend を許可します。
- Maximum price、allowed publisher、Truth state、source policy を設定します。
- `ask_` と `amk_` は server secrets に保存し traces から削除します。
- `401` は credential、`402` は access/balance、`403` は scope、`429` は backoff です。
- Listing ID、rank reasons、charge ID、provenance receipt を結果と一緒に保存します。
- Invoice は idempotent に作成し、異なる金額で transfer を再試行しません。

## Team に rollout する

- 最初の knowledge category と改善したい decision を定義します。
- Buyer 招待前に10〜20件の高品質 listing を用意します。
- Public summary と必須 source の最低基準を合意します。
- 成功、unknown memory、insufficient balance、upstream failure、revocation をテストします。
- Discovery-to-read、refusal、capture/release、accrual、payout backlog を監視します。

## Trust と money の境界を理解する

Memory Market は ranking と entitled memory 配信、Attested Meter は reserve、
capture、accounting、payout、Attested Prove は key なしの receipt verification を
担当します。KOVA は authenticated service-to-service で subscription settlement
を検証し、federation でも独立して利用できます。

Seed phrase や wallet private key は要求しません。USDC は recipient に直接移動し、
payout は別に実行されます。[KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md) と
[MARKET_USE_CASES.md](MARKET_USE_CASES.md) も参照してください。
