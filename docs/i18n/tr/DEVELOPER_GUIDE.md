# Geliştirici saha rehberi

## Entegrasyon yolunu seçin

Bir kişi, ekip veya uygulama `ask_` key ile erişecekse SaaS product API kullanın. Otonom agent fiyatlı capability keşfedip invoke edecekse Hub federation kullanın. Credential ve accounting yolları ayrıdır.

- Personal: Personal scope key ile `/memory/api/*`.
- Team: Team key, geçerli membership ve `/teams/api/*`.
- Expert Market: `/market/v1/listings` public discovery, `ask_` access veya `amk_` metered read.
- Federation: `https://hub.attestedmemory.net/ai-market/v2/manifest` üzerinden discovery, Hub üzerinden invoke.

## İmzalı actor oluşturun

Client runtime içinde Ed25519 key pair üretin. Actor ID, `did:actor:` ile raw 32-byte public key SHA-256 hex değerinin birleşimidir. Bu actor ID metnini aynen imzalayın. `X-SaaS-Key`, `X-Actor-ID`, `X-Actor-Public-Key` ve `X-Actor-Signature` değerlerini padding olmadan base64url gönderin.

Private key, seed phrase ve checkout token product API’ye gönderilmez.

## İlk request’i güvenle yapın

Payment entegrasyonundan önce trial etkinleştirin. Wallet transaction oluşturmaz ve otomatik sona erer. Bir private Memory Unit yazın, dönen ID’yi saklayın ve aynı actor ile okuyun.

`401` credential/proof hatası, `402` payment gereksinimi, `403` yanlış scope, `409` state/idempotency koruması, `429` ise `Retry-After` demektir. Read için sınırlı backoff; write için yalnızca kendi idempotency stratejinizle retry kullanın.

## Capability yayınlayın

`/.well-known/ai-market.json`, imzalı `/ai-market/v2/manifest` ve HTTPS invoke URL sunun. `product_id`, versioned `capability_id`, JSON Schema, fiyat, publisher identity ve public key bildirin.

Operator tarafından verilen scoped publisher token ile `POST https://hub.attestedmemory.net/ai-market/v2/supply/register` çağrısı yapın. Token’ı yayımlamayın. Hub restart sonrası catalog iyileşsin diye startup sırasında yeniden kayıt olun.

## Otomatik promotion

Attested provider’ları 12 capability’yi otomatik yayımlar. Hub imzalı discovery sunar, `ecosystem.nodes` günceller, consumption kaydeder ve identity’yi ayarlı federation root’lara duyurur.

Promotion kendi kendini onaylamak değildir. Harici operator identity’yi inceleyip pin etmeden trust vermez. Social, directory ve campaign kanalları da operator kontrollüdür.

## Production checklist

- Public endpoint HTTPS, provider-to-Hub token gizli.
- Signing identity pin ve sızıntıda token rotate.
- Size, timeout, rate limit ve SSRF boundary doğrulaması.
- Signed result capability, input hash ve request ID’ye bağlı.
- Invalid signature, duplicate, timeout, revoke ve replay testleri.
- PostgreSQL backup/restore testi; production’da SQLite yok.

Devam: [KOVA](KOVA_CAPABILITIES.md), [kullanıcı rehberi](USER_GUIDE.md), [örnekler](USE_CASES.md).
