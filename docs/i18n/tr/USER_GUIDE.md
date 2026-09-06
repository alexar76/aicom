# Kullanıcı rehberi

## Ödeme ve anahtar

`/billing` üzerinde Personal, Team veya Market seçin. Invoice tutarı, alıcıyı,
token'ı, chain'i ve son tarihi gösterir. Base üzerinde tam tutarı gönderin,
onayları bekleyin ve tx hash'i girin. `ask_...` anahtarı yalnızca bir kez gösterilir.
Yönetim için `GET /v1/keys/me`, `POST /v1/keys/rotate` ve `POST /v1/keys/revoke` kullanılır.

## Identity ve memory

Aktif ücretli anahtarı `X-SaaS-Key` olarak gönderin; bu actor proof'tan ayrıdır.

Korumalı isteklerde `X-Actor-ID`, `X-Actor-Public-Key` ve `X-Actor-Signature` gerekir.
Private key istemcide kalır. Yazma `/memory/api/memories`, arama `/memory/api/search` üzerindedir.

## Ekipler

`/teams/api/teams` ile ekip oluşturun, `/teams/api/teams/{team_id}/members` ile üye yönetin
ve her işlemde `team_id` gönderin. Gateway membership'i, Hub kısa assertion'ı ve actor signature'ı doğrular.

`401` kimlik bilgisi hatası, `403` scope hatası, `402` ödeme gereksinimi, `429` rate limit demektir.
Private key'i API'ye göndermeyin.

## 7. Trial

Trial'ı `/v1/trials` üzerinden başlatın: Personal 7 gün, Team 14 gün ve Expert
Market 1 gün sürer. Gateway ödeme almadan tek kullanımlık `ask_...` anahtarı verir
ve bunu doğrulanmış actor'a bağlar. Süre dolunca erişim otomatik kapanır; devam etmek
için Base üzerinde kesin USDC ödemesini tamamlayın. Ayrıntılar: [TRIAL.md](TRIAL.md).
