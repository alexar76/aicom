# Expert Memory Market uygulama rehberi

Bu rehber buyer, publisher ve agent integrator için gerçek production yollarını
açıklar. Public discovery, paid delivery, publisher accounting ve proof bilinçli
olarak ayrı contract’lardır.

## Entegrasyondan önce access yolunu seçin

- 1 günlük trial ile wallet transaction olmadan UX ve API uyumunu doğrulayın.
- Expert Pass, scoped `ask_` key ile yedi gün storefront keşfi sağlar.
- Her Memory Unit publisher’a atanıp ödenecekse per-read kullanın.
- Pass ile publisher revenue’yu karıştırmayın: pass storefront’u, Meter capture split’i finanse eder.

## Satın almadan listing’i inceleyin

Key olmadan `GET /market/v1/listings?q=<konu>` çağırın. Her sonuç summary,
`rank_score`, `rank_reasons`, Truth, Provenance, price ve publisher gösterir.
`GET /market/v1/listings/<memory_id>` ücretli gövdeyi asla döndürmez.

Policy’niz için public evidence yetersizse listing’i reddedin. Yüksek score güven
emri değildir. Rejected claim unverified altında kalır; popularity ranking signal değildir.

## Ücretsiz trial ile başlayın

`/` adresini `trial=expert-market` ile açın veya setup wizard kullanın. Browser
Actor Identity oluşturur ve private signing key’i yerelde tutar. Gateway her
actor/product için bir kez 1 günlük trial verir. `ask_` key’i secret vault’ta
tutun; URL, log veya client analytics’e koymayın.

Trial product fit’i doğrular; payment, split veya kalıcı entitlement oluşturmaz.

## Pass veya teslim edilen read satın alın

Expert Pass için `/billing?plan=expert.pass.7d` açın, exact invoice oluşturun,
Base üzerinde canonical USDC gönderin ve KOVA finality bekleyin. Gateway yedi
günlük key verir; checkout recovery 48 saattir.

Per-read için Attested Meter account oluşturup fonlayın, `amk_` key’i server-side
tutun ve `POST /market/v1/read` çağrısını `x-meter-key` ile
`{"memory_id":"<id>"}` gövdesiyle yapın. Meter fiyatı reserve eder, content
tesliminden sonra capture eder. Hata veya red reserve’ü serbest bırakır.

## Expert memory publish edin ve fiyatlandırın

- Net title, yararlı public summary, tags ve `source_refs` içeren Memory Unit oluşturun.
- Ücret açmadan mümkün Truth / Provenance evidence ekleyin.
- İmzalı identity ve Base payout address ile `POST https://meter.attestedmemory.net/v1/publishers` kaydı yapın.
- Publisher key’i gizli tutun; yalnız kendi `expert.read:<memory_id>` işleminizi `/v1/publishers/me/prices` ile fiyatlandırın.
- Buyer göndermeden public listing’i doğrulayın.

Standart split publisher %70 / platform %30; Publisher Pro %85 / %15’tir.
Minimum üzerinde operator imzalı `attested.payout/v1` çıkarır ve hash’i kaydeder.

## Autonomous agent entegre edin

- Discovery ile purchase’ı ayırın; metadata değerlendikten sonra spend izni verin.
- Maximum price, allowed publisher, Truth state ve source policy tanımlayın.
- `ask_`, `amk_` server secrets’ta kalsın ve traces’ten çıkarılsın.
- `401` credential, `402` access/balance, `403` scope, `429` backoff anlamına gelir.
- Listing ID, rank reasons, charge ID ve provenance receipt’i sonuçla saklayın.
- Invoice için idempotency kullanın; farklı amount ile transfer tekrarlamayın.

## Team rollout yapın

- İlk knowledge category ve iyileştireceği decision’ı tanımlayın.
- Buyer davetinden önce 10–20 yüksek kaliteli listing hazırlayın.
- Public summary ve zorunlu source standardını belirleyin.
- Başarı, unknown memory, insufficient balance, upstream failure ve revocation test edin.
- Discovery-to-read, refusal, capture/release, accrual ve payout backlog izleyin.

## Trust ve money sınırlarını bilin

Memory Market ranking ve entitled memory sunumunu; Attested Meter reserve,
capture, accounting ve payout’u; Attested Prove key olmadan receipt verification’ı
yönetir. KOVA authenticated service-to-service ile subscription settlement’ı
doğrular ve federation üzerinden bağımsız kullanılabilir.

Hiçbir bileşen seed phrase veya wallet private key istemez. USDC recipient’a
doğrudan gider; payout ayrı yürütülür. [KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md)
ve [MARKET_USE_CASES.md](MARKET_USE_CASES.md) belgelerine bakın.
