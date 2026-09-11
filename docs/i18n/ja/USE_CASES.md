# ユースケース

Attested Memory は、**忘れるコストが高く**、**盲目的な信頼はさらに高い**場面向けです。ノート、チャットログ、vector store では足りないとき——identity、truth state、provenance、正確な settlement が、文脈を「行動できるもの」に変えるとき——を示します。

ルート名、ヘッダー、支払い用語はどの言語でもそのままです。ローカライズするのは説明文だけです。

## context rot に耐える創業者のセカンドブレイン

**誰向け。** 毎日ツール・エージェント・デバイスを渡り歩く創業者、研究者、オペレーター。

**課題。** 意思決定はチャット、Notion のダンプ、途中のプロンプトに散らばる。六週間後、*なぜ*その選択をしたか、どの情報源を信じたか、どのエージェントが都合の良い要約を作ったかを誰も言えない。

**仕組み。**

1. 決定・根拠・タグ・`source_refs` を含む Memory Unit を書く。
2. actor として署名する（`X-Actor-ID` / public key / signature）。秘密鍵はクライアントに残す。
3. あとで `/memory/api/search` を検索し、新しい計画やエージェント実行に再利用する前に truth + provenance を確認する。

**attestation が重要な理由。** 取り出すのは「似た段落」ではない。actor と lineage を持つ、持ち運び可能な主張である。

**始める。** [Personal Memory](/memory) · [ユーザーガイド](USER_GUIDE.md) · [/billing](/billing) の trial。

## 意思決定の痕跡が残るインシデント war-room

**誰向け。** オンコールエンジニア、SRE、セキュリティ responders。

**課題。** 障害チャネルは wiki より速い。ポストモーテムは記憶で書かれ、各判断の所有者は曖昧で、翌週エージェントが却下済みの緩和策を繰り返す——共有 namespace に何も署名されていなかったから。

**仕組み。**

1. Team Memory OS の workspace を開き、team namespace を作る。
2. メンバーがインシデントメモ、却下案、最終アクションを actor 署名付きで書く。
3. SaaS gateway が membership を確認し、Hub は一致する `team:<id>` レコードだけを受け入れる。クエリは別チームに漏れない。

**attestation が重要な理由。** handoff が監査可能になる。offboarding で鍵を失効させ、短命の team assertions はチャットの鑑識捜査なしに期限切れになる。

**始める。** [Team Memory OS](/teams) · [ユーザーガイド § Team](USER_GUIDE.md)。

## コーパスを漏らさずに売れる専門家知識

**誰向け。** ドメイン専門家、research shops、advisory boutiques。

**課題。** コーパス全体を無料公開すると事業が死ぬ。ティーザーだけだと信頼が死ぬ。買い手は支払い前に provenance を見る必要があり、売り手は無期限コピーではなく期限付きアクセスが必要。

**仕組み。**

1. 公開 summary フィールドと、本文は有料 visibility の Memory Unit を公開する。
2. 買い手がカタログを検索し、truth/provenance を確認してから正確な Base USDC invoice を開く。
3. KOVA が送金を検証し、Gateway が scoped entitlement を発行する。アクセスはプランと共に期限切れになる。

**attestation が重要な理由。** discovery は正直で、settlement は正確。entitlement は「名誉に基づく PDF リンク」ではなく、製品の暗号学的 scope である。

**始める。** [Expert Memory Market](/market) · [支払い](/billing)。

## 暗号学的連続性を持つマルチエージェント handoff

**誰向け。** エージェント運用者、オーケストレーションチーム、自律ワークフロー。

**課題。** エージェント A がエージェント B にチャット要約を渡す。署名なし、一部幻覚、出典なし。失敗は「次のモデルが馬鹿だった」に見えるが、本当のバグは provenance の静かな消失である。

**仕組み。**

1. エージェント A が制約・使用ツール・出典・未解決リスクを含む署名済み handoff Memory Unit を書く。
2. エージェント B が同じ actor/team ポリシーで取得し、続行前に provenance を検証する。
3. truth state は unit と一緒に移動する——矛盾は自信満々の文章に丸められず、見えるまま残る。

**attestation が重要な理由。** 連続性はレコードの性質であり、タブを開いたままにしていた誰かの性質ではない。

**始める。** [Developers](/developers) · [ユーザーガイド § Actor identity](USER_GUIDE.md)。

## 出典に縛られた claims による due diligence と調査

**誰向け。** アナリスト、counsel、investment / vendor-review チーム。

**課題。** diligence メモは「デッキ」「通話」「Slack の何か」を引用する。claim が疑われたとき、保管連鎖は感覚でしかない。

**仕組み。**

1. 重要な claim ごとに明示的な `source_refs` 付き Memory Unit として記録する。
2. 証拠が届くたびに truth state を付与・更新する（confirmed、disputed、insufficient）。
3. あとで再構成した伝承ではなく、provenance receipts からファイルを組み立てる。

**attestation が重要な理由。** レビュアーは「誰のメモが新しいか」ではなく、claim とその証拠について議論する。

**始める。** Personal または Team 製品 · [用語集](GLOSSARY.md)。

## ブラウザが消えても動く自動有料アクセス

**誰向け。** wallet アプリから払う買い手、invoice を settle するスクリプト、checkout タブを見張れないオペレーター。

**課題。** 古典的 checkout はタブを閉じると死ぬ。「tx hash を貼れ」の手動フローはサポートチケットと曖昧な部分払いを生む。

**仕組み。**

1. 一意の `Idempotency-Key`、プラン、payer で `POST /v1/billing/orders`。
2. Base 上で canonical USDC の正確な金額を invoice 受取先へ送る。
3. KOVA が token、payer、recipient、amount、confirmation depth を照合する。
4. Gateway が製品キーを自動有効化する。checkout token 付きで `GET /v1/billing/orders/{id}` を poll すれば、confirmed 後にキーが返る——元のブラウザセッションがなくても。

**attestation が重要な理由。** 資金移動と entitlement 発行は wallet のスクリーンショットではなく、正確な invoice 同一性で結ばれる。

**始める。** [Billing](/billing) · [ユーザーガイド § Buy access](USER_GUIDE.md)。

## 組織の記憶を孤児にしない安全な offboarding

**誰向け。** チームリード、security、IT。

**課題。** 退職するオペレーターは、本物の runbook が入ったチャットエクスポートと個人メモをまだ持っている。Slack の失効は、管理されたシステムに一度も住んでいなかった組織記憶を失効させない。

**仕組み。**

1. 運用知識を Team Memory OS の明示的な namespace に置く。
2. 退職時に直ちに SaaS キーを rotate / revoke する。
3. team assertions は数分で期限切れになり、Hub ポリシーは保護された read/write に引き続き actor proofs を要求する。

**attestation が重要な理由。** アクセス終了は「誰かが Drive フォルダを消したはず」ではなく、control plane のイベントである。

**始める。** [Team Memory OS](/teams)。

## 向かない用途

- 身元も出典規律もない汎用チャットアーカイブ。
- wallet の private keys、seed phrases、生の credentials の保管場所。
- visibility ポリシーを飛ばした無制限の「世界と共有」ダンプ。
- 端数や概算の crypto 支払い——正確な USDC 金額こそが invoice である。

著作権・出典・支払い最終性の静かな喪失を許せるなら、ノートで足りる。許せないなら、上の該当プロダクト面から始め、Hub 契約を正確に保て。
