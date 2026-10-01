# Kullanım senaryoları

Attested Memory, **unutmanın pahalı** olduğu ve **kör güvenin daha kötü** olduğu durumlar içindir. Bu senaryolar; not, sohbet günlüğü veya vector store’un yetmediği — ve identity, truth state, provenance ile kesin settlement’ın bağlamı üzerine hareket edilebilir bir şeye dönüştürdüğü — anları gösterir.

Rota adları, header’lar ve ödeme terimleri tüm dillerde birebir kalır. Yalnızca açıklayıcı metin yerelleştirilir.

## Context rot’a dayanan kurucu ikinci beyin

**Kim.** Her gün araçlar, ajanlar ve cihazlar arasında geçen bir kurucu, araştırmacı veya operatör.

**Sorun.** Kararlar sohbetlerde, Notion dökümlerinde ve yarım prompt’larda yaşar. Altı hafta sonra kimse *neden* bir seçim yapıldığını, hangi kaynaklara güvenildiğini veya hangi ajanın rahat bir özet uydurduğunu söyleyemez.

**Nasıl çalışır.**

1. Karar, gerekçe, etiketler ve `source_refs` ile bir Memory Unit yazın.
2. Actor olarak imzalayın (`X-Actor-ID` / public key / signature). Özel anahtar istemcinizde kalır.
3. Sonra `/memory/api/search` ile arayın; belleği yeni bir planda veya ajan çalıştırmasında yeniden kullanmadan önce truth + provenance’ı inceleyin.

**Attestation neden önemli.** “Benzer bir paragraf” çekmiyorsunuz. Actor’ü ve soy ağacı olan taşınabilir bir iddia çekiyorsunuz.

**Başlangıç.** [Personal Memory](/memory) · [Kullanıcı rehberi](USER_GUIDE.md) · [/billing](/billing) üzerinde trial.

## Karar izini koruyan olay war-room’u

**Kim.** On-call mühendisler, SRE’ler, güvenlik responders.

**Sorun.** Kesinti kanalı wiki’den hızlıdır. Postmortem hafızadan yazılır, her çağrının sahipliği bulanıktır ve ertesi hafta bir ajan, reddedilmiş bir mitigasyonu tekrarlar — çünkü paylaşılan bir namespace’e hiçbir şey imzalanmamıştır.

**Nasıl çalışır.**

1. Bir Team Memory OS workspace açın ve bir team namespace oluşturun.
2. Üyeler olay notlarını, reddedilen seçenekleri ve nihai eylemleri actor imzalarıyla yazar.
3. SaaS gateway membership’i kontrol eder; Hub yalnızca eşleşen `team:<id>` kayıtlarını kabul eder. Sorgular başka bir ekibe sızmaz.

**Attestation neden önemli.** Handoff’lar denetlenebilir olur. Offboarding anahtarı iptal eder; kısa ömürlü team assertions, sohbetlerde adli arama olmadan süresi dolar.

**Başlangıç.** [Team Memory OS](/teams) · [Kullanıcı rehberi § Team](USER_GUIDE.md).

## Corpus sızdırmadan satılan uzman bilgisi

**Kim.** Alan uzmanları, research shop’lar, advisory butikleri.

**Sorun.** Tüm corpus’u ücretsiz yayımlamak işi öldürür. Yalnızca teaser yayımlamak güveni öldürür. Alıcılar ödemeden önce provenance görmeli; satıcılar varsayılan olarak kalıcı kopya değil, süre sınırlı erişim ister.

**Nasıl çalışır.**

1. Genel summary alanları ve gövde için ücretli visibility ile bir Memory Unit yayımlayın.
2. Alıcılar kataloğu arar, truth/provenance’ı inceler, ardından kesin bir Base USDC invoice açar.
3. KOVA transferi doğrular; Gateway scoped bir entitlement verir. Erişim planla birlikte sona erer.

**Attestation neden önemli.** Discovery dürüsttür. Settlement kesindir. Entitlement, “şeref sözü PDF linki” değil; ürünün kriptografik scope’udur.

**Başlangıç.** [Expert Memory Market](/market) · [Ödemeler](/billing).

## Kriptografik süreklilikli çok ajanlı handoff

**Kim.** Ajan operatörleri, orkestrasyon ekipleri, otonom workflow’lar.

**Sorun.** Ajan A, Ajan B’ye bir sohbet özeti bırakır. Özet imzasızdır, kısmen hayal ürünüdür ve kaynaklardan arındırılmıştır. Arızalar “sonraki model aptaldı” gibi görünür; gerçek bug ise provenance’ın sessizce kaybolmasıdır.

**Nasıl çalışır.**

1. Ajan A imzalı bir handoff Memory Unit yazar: kısıtlar, kullanılan araçlar, kaynaklar, açık riskler.
2. Ajan B aynı actor/team politikasıyla alır ve devam etmeden önce provenance’ı doğrular.
3. Truth state unit ile birlikte taşınır — çelişkiler özgüvenli düz yazıya yumuşatılmak yerine görünür kalır.

**Attestation neden önemli.** Süreklilik, sekmeyi açık bırakanın değil; kaydın özelliğidir.

**Başlangıç.** [Developers](/developers) · [Kullanıcı rehberi § Actor identity](USER_GUIDE.md).

## Kaynaklara bağlı claim’lerle due diligence ve araştırma

**Kim.** Analistler, counsel, investment ve vendor-review ekipleri.

**Sorun.** Diligence notları “deck”, “call” ve “Slack’ten bir şey”e atıf yapar. Bir claim itiraz edildiğinde zincir, bir histir.

**Nasıl çalışır.**

1. Her maddi claim’i açık `source_refs` ile bir Memory Unit olarak kaydedin.
2. Kanıt geldikçe truth state ekleyin veya güncelleyin (confirmed, disputed, insufficient).
3. Dosyayı sonra yeniden uydurulmuş folklordan değil; provenance receipts’ten yeniden kurun.

**Attestation neden önemli.** İnceleyenler kimin notlarının “daha yeni” olduğu değil; claim ve evidence üzerine tartışır.

**Başlangıç.** Personal veya Team ürünü · [Sözlük](GLOSSARY.md).

## Tarayıcı yokken otomatik ücretli erişim

**Kim.** Wallet uygulamasından ödeyen alıcılar, invoice settle eden script’ler ve checkout sekmesini bekleyemeyen operatörler.

**Sorun.** Klasik checkout sekme kapanınca ölür. Elle “tx hash yapıştır” akışları destek biletleri ve belirsiz kısmi ödemeler üretir.

**Nasıl çalışır.**

1. Benzersiz `Idempotency-Key`, plan ve payer ile `POST /v1/billing/orders`.
2. Base üzerinde invoice alıcısına tam canonical USDC tutarını gönderin.
3. KOVA token, payer, recipient, amount ve confirmation depth’i eşleştirir.
4. Gateway ürün anahtarını otomatik etkinleştirir. Checkout token ile `GET /v1/billing/orders/{id}` poll’u, confirmed olduğunda anahtarı döner — orijinal tarayıcı oturumu gitmiş olsa bile.

**Attestation neden önemli.** Para hareketi ile entitlement çıkarımı, cüzdan ekran görüntüsüne değil; kesin invoice kimliğine bağlıdır.

**Başlangıç.** [Billing](/billing) · [Kullanıcı rehberi § Buy access](USER_GUIDE.md).

## Kurumu yetim bırakmayan güvenli offboarding

**Kim.** Team lead’ler, security, IT.

**Sorun.** Ayrılan operatörde hâlâ gerçek runbook’ları içeren sohbet dışa aktarımları ve kişisel notlar vardır. Slack’i iptal etmek, hiç kontrollü bir sistemde yaşamamış kurumsal belleği iptal etmez.

**Nasıl çalışır.**

1. Operasyon bilgisini Team Memory OS’ta açık bir namespace altında tutun.
2. Ayrılışta SaaS anahtarını hemen rotate/revoke edin.
3. Team assertions dakikalar içinde sona erer; Hub politikası korumalı read/write için hâlâ actor proofs ister.

**Attestation neden önemli.** Erişim, Drive klasörünün silindiği umuduyla değil; bir control plane olayı olarak biter.

**Başlangıç.** [Team Memory OS](/teams).

## Ne için değildir

- Kimlik veya kaynak disiplini olmayan genel bir sohbet arşivi.
- Wallet private key’leri, seed phrase’ler veya ham credentials saklama yeri.
- Visibility politikasını atlayan sınırsız “dünyayla paylaş” dökümleri.
- Yuvarlanmış veya yaklaşık crypto ödemeleri — kesin USDC tutarı invoice’un kendisidir.

İş akışınız yazarlık, kaynak ve ödeme kesinliğinin sessiz kaybına dayanabiliyorsa bir defter yeter. Dayanamıyorsa yukarıdaki eşleşen ürün yüzeyinden başlayın ve Hub sözleşmelerini kesin tutun.
