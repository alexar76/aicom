# Ücretsiz deneme ve yükseltme

Personal 7 gün, Team 14 gün ve Expert Market 1 gün ücretsiz deneme sunar. Doğrulanmış
bir actor her ürün için denemeyi yalnızca bir kez etkinleştirebilir.

Tarayıcı Ed25519 actor proof oluşturur. Gateway ödeme almadan bir `ask_...` deneme
anahtarı verir. Anahtar otomatik olarak sona erer ve ücretli anahtarla aynı
introspection, rotation ve revoke kurallarını kullanır.

Yükseltmede Gateway Base üzerinde kesin canonical USDC invoice oluşturur. KOVA
işlemi doğrular ve gerekli confirmations sonrasında ücretli anahtar otomatik verilir.
