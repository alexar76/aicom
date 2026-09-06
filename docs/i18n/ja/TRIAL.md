# 無料トライアルとアップグレード

Personal は7日間、Team は14日間、Expert Market は1日間の無料トライアルを
提供します。検証済み actor は、各プロダクトで1回だけ利用できます。

ブラウザが Ed25519 actor proof を作成し、Gateway が支払いなしで `ask_...`
キーを発行します。キーは自動的に期限切れになり、有料キーと同じ
introspection、rotation、revoke のルールを使います。

アップグレードすると Gateway が Base 上の canonical USDC の正確な invoice
を作成します。KOVA が取引を確認し、必要な confirmations 後に有料キーが
自動発行されます。
