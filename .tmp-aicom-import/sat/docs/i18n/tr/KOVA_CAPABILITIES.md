# Attested içinde KOVA capabilities

## KOVA nedir

KOVA, Attested Hub içinde çalışmayan bağımsız bir Base ve USDC servisidir. Altı product'ı
Hub'a yayınlar; agent'lar federation ile keşfeder, fiyatını görür ve invoke eder.

## Agent nasıl çağırır

Agent KOVA'nın private provider URL'sini değil Hub üzerindeki
`POST /ai-market/v2/invoke` yolunu çağırır. Hub access ve settlement kurallarını uygular,
invoke'u kaydeder ve KOVA'ya yönlendirir.

Capabilities: `kova.network.status@v1`, `kova.asset.balance@v1`,
`kova.usdc.invoice.create@v1`, `kova.usdc.invoice.status@v1`,
`kova.usdc.invoice.cancel@v1`, `kova.usdc.webhook.register@v1`.

## Checkout neden ayrı yol kullanır

Attested subscription, KOVA invoice API'yi kimliği doğrulanmış service-to-service bağlantıyla
çağırır. Kendi ödemesini doğrulamak için paid capability satın almaz. Böylece recursive
billing oluşmaz ve bir order bir entitlement üretir.

## KOVA'yı kim öder

Attested subscription satın alındığında alıcının USDC'si doğrudan
`SAAS_PAYMENT_RECIPIENT` adresine gider. Bu transfer KOVA için otomatik split veya
yüzde içermez. Gateway özel bir `KOVA_API_KEY` kullanır; key ücretli KOVA Pro ya da
Business planından geliyorsa operator bunu ayrıca satın alır veya yeniler. Federated
capability call üçüncü ve ayrı ölçülen akıştır: per-call price ile Hub routing fee,
capability consumption olarak kaydedilir ve Attested subscription payment'ından
kesilmez.

## Neler görünür

Hub federated invoke için price, status ve receipt kaydeder. Korunan Operator ledger Attested
order, trial/paid key ve request sayılarını gösterir. KOVA Settlement desk kendi order, key
prefix ve API usage verisini gösterir. Tam key hiçbir panelde listelenmez.

## Güvenlik sınırı

Provider route private `X-AIMarket-Internal-Token` ister, route/body identity eşleşmesini
kontrol eder ve write çağrılarını daha sıkı sınırlar. `X-Provider-Signature`, Ed25519 ile
`product_id`, `capability_id`, input hash ve result'ı bağlayıp başka input'a replay'i önler.

## Güvenli kurulum

Hub `AIMARKET_CAPABILITY_TOKEN` ile aynı, rastgele 32+ karakter
`KOVA_CAPABILITY_TOKEN` kullanın. `KOVA_HUB_URL` ve `KOVA_INVOKE_BASE` ayarlayın;
provider endpoint'leri private service network içinde tutun.
