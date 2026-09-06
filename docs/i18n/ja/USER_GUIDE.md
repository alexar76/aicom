# ユーザーガイド

## 支払いとキー

`/billing` で Personal、Team、Market を選びます。invoice には金額、受取先、
token、chain、期限が表示されます。Base で正確な金額を送信し、必要な確認後に
tx hash を入力します。`ask_...` キーは一度だけ表示されます。キー管理には
`GET /v1/keys/me`、`POST /v1/keys/rotate`、`POST /v1/keys/revoke` を使います。

## identity と memory

有料キーは `X-SaaS-Key` として送信します。これは actor proof とは別です。

保護されたリクエストには `X-Actor-ID`、`X-Actor-Public-Key`、
`X-Actor-Signature` が必要です。秘密鍵はクライアント内に保持します。
書き込みは `/memory/api/memories`、検索は `/memory/api/search` です。

## チーム

`/teams/api/teams` でチームを作成し、`/teams/api/teams/{team_id}/members` で
メンバーを管理します。すべての操作に `team_id` を付けます。Gateway が membership、
Hub が短期 assertion と actor signature を検証します。

`401` は認証エラー、`403` は scope エラー、`402` は支払いが必要、`429` は rate limit です。
秘密鍵を API に送信しないでください。

## 7. Trial

`/v1/trials` から trial を開始できます。Personal は7日間、Team は14日間、
Expert Market は1日間です。支払いなしで一度だけ使える `ask_...` キーが発行され、
検証済み actor に紐づきます。期間終了後は自動失効し、継続には Base の正確な USDC
決済が必要です。詳しくは [TRIAL.md](TRIAL.md) を参照してください。
