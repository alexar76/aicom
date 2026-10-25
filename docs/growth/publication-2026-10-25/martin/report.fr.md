# Cinq portefeuilles ont payé un vendeur x402. Que peut-on dire de la demande ?

Déclaration : je maintiens HISTOR et AIMarket dans l’écosystème alexar76. Cette analyse, son implémentation et cet article ont été préparés avec une aide substantielle de l’IA générative. Du code déterministe a produit les décomptes et les vérifications de transferts ; aucun modèle n’a déduit l’identité des portefeuilles. Un paiement de recherche était le nôtre et il est identifié ci-dessous.

Après notre étude de livraison des services x402, [Martin Pisacreta a signalé](https://dev.to/alexar76/we-tried-to-buy-one-call-from-100-x402-sellers-most-delivered-almost-nobody-is-buying-2498#comment-3ioef) que le seul payeur récurrent de textokit semblait envoyer l’inputExample publié pour `normativa-ar`. Il a demandé si HISTOR pouvait signaler les portefeuilles dont l’activité ressemblait à un balayage. Nous avons implémenté un audit local et vérifié les cinq payeurs externes. Le résultat utile est un tableau de preuves où les inconnues sont explicites.

## Les montants des paiements sont confirmés

Le [registre public du vendeur](https://tienda.textokit.store/receipts.json), récupéré le **25 octobre 2026 à 05:16:44 UTC**, contenait **80 ventes réglées** : 56 identifiées par l’éditeur comme provenant de ses propres portefeuilles et **24 ventes externes provenant de cinq portefeuilles**, pour **0,055000 USDC**. Les indicateurs de propriété sont des affirmations de la source, et non des identités authentifiées indépendamment.

Les **24 entrées externes** correspondaient à des reçus de transactions Base réussies contenant un USDC Transfer officiel du payeur indiqué vers le vendeur, pour le montant exact annoncé. Cela vérifie le règlement. Cela ne vérifie ni la livraison du service ni la raison du paiement. Le registre évolue ; ces chiffres décrivent un instantané.

Pour le contexte, nous avons examiné les transferts USDC sortants de ces cinq adresses du **11 octobre 2026 à 05:23:11 UTC au 25 octobre 2026 à 05:23:11 UTC** : blocs **52453422–53058222**. Les **605 plages consécutives de journaux** ont toutes été lues avec succès, renvoyant **23 254 événements bruts**. Deux événements de valeur nulle ont été exclus des mesures comportementales. La collecte s’est achevée à 05:27:36 UTC. Le bloc supérieur retenu se trouvait douze blocs derrière la tête initiale du nœud et son hash est resté stable.

## Ce que montrent les cinq portefeuilles

Les adresses ci-dessous renvoient à leurs pages publiques dans l’explorateur. « Destinataires » désigne des adresses USDC distinctes, pas nécessairement des commerçants ou des services x402. Les décomptes de transferts sortants excluent les deux événements de valeur nulle.

| Portefeuille | Ventes textokit | USDC | Transferts sortants / destinataires | Destinataires payés une seule fois | Transferts ≤0,01 USDC | Étiquette |
|---|---:|---:|---:|---:|---:|---|
| [0x097e…475a](https://basescan.org/address/0x097e3f339d0b023605e12a6b81e2d6cb7571475a) | 1 | 0,001000 | 5 / 4 | 3 (75,0%) | 1 (20,0%) | `known-probe` |
| [0x7722…5e4a](https://basescan.org/address/0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a) | 1 | 0,001000 | 1 262 / 1 010 | 909 (90,0%) | 1 051 (83,3%) | `unknown` |
| [0xa1d1…1978](https://basescan.org/address/0xa1d1c0cf717402ff3651aa4873ccf96410b01978) | 1 | 0,001000 | 1 896 / 1 632 | 1 416 (86,8%) | 1 449 (76,4%) | `unknown` |
| [0xc9c7…1670](https://basescan.org/address/0xc9c7b38c0942914fc8ea12063bc92dcd3b581670) | 1 | 0,001000 | 1 979 / 730 | 442 (60,5%) | 1 518 (76,7%) | `unknown` |
| [0xec2a…d034](https://basescan.org/address/0xec2abd3eda89bed90124736e317e847d5fb6d034) | 20 | 0,051000 | 18 110 / 648 | 217 (33,5%) | 16 320 (90,1%) | `probe-like` |

**0x097e…475a était notre sonde de recherche.** Son unique achat `x402-ping` de 0,001 USDC, le 20 octobre, correspond à la transaction enregistrée dans notre étude. L’étiquette s’applique à cet achat, pas à toutes les actions futures de l’adresse.

**0xec2a…d034 a effectué vingt achats auprès de dix-sept services**, dont quatre achats `normativa-ar`, entre le 20 et le 24 octobre. Martin indique qu’il envoie l’inputExample publié. Nous avons associé sa déclaration à ces quatre lignes du registre par service et par heure. Les contenus des requêtes ne sont pas publics ; les correspondances exactes des entrées par transaction n’ont donc pas été vérifiées indépendamment. Cela étaye une indication `probe-like` attribuée à une source, sans établir l’identité d’un moniteur. Sans cette annotation, l’étiquette automatique stricte est `unknown`.

**Les trois autres portefeuilles présentent une large distribution de petits paiements, avec une intention inconnue.** Les deux premiers ont atteint 1 010 et 1 632 destinataires. Notre ancienne description « plus d’un millier » reste valable, mais « presque tous » doit être remplacé par les proportions exactes du tableau. Le troisième a atteint 730 destinataires et a payé plus souvent les mêmes. Leurs achats individuels de 0,001 USDC chez textokit ne prouvent ni un usage organique ni une surveillance.

## La fonction existe ; les étiquettes restent prudentes

La commande locale, **pas encore publiée**, `histor payer-audit` accepte des reçus publics, des données facultatives de la chaîne pour une période bornée et des annotations de sources rattachées aux transactions. Elle exporte du JSON et du Markdown avec les hashes des entrées, la période d’observation, les mesures par payeur, les règles, les références de règlement et les limites de couverture. Elle ne nécessite ni clés de portefeuille ni base de données de production. Son collecteur autorise cinq méthodes RPC de lecture et n’envoie jamais de transactions ni de requêtes payantes aux services.

L’heuristique initiale de distribution large exige au moins **50 transferts**, **50 destinataires**, **90 % de destinataires payés une seule fois** et **90 % de transferts d’au plus 0,01 USDC**. Ces seuils non calibrés ont été fixés avant l’examen des mesures collectées et n’ont pas été assouplis pour imposer une étiquette. Les signaux descriptifs restent visibles quand la règle combinée échoue.

Le résultat est une sonde connue, un cas probe-like annoté selon une source et trois cas inconnus. **Unknown ne signifie pas acheteur confirmé. Probe-like ne signifie ni fraude ni usage sans valeur.** Une surveillance payante peut elle-même être un usage réel. Les **0,055000 USDC restent intégralement dans les totaux des paiements**, quelles que soient les étiquettes.

Ces observations ne déterminent ni le nombre de clients organiques de textokit, ni sa rentabilité, ni la livraison des services, ni la propriété des portefeuilles. Les vérifications RPC font confiance au nœud Base choisi ; ce ne sont pas des preuves de chaîne vérifiées localement. L’amélioration pratique est plus limitée : règlement, comportement et affirmations attribuées ont désormais des champs distincts, afin qu’un nombre de reçus ne devienne pas silencieusement un nombre de clients.

## Références publiques des règlements

Les 24 transactions publiques suivantes correspondent aux entrées externes vérifiées du registre, regroupées par payeur. Les montants sont en USDC. Le [registre actuel](https://tienda.textokit.store/receipts.json) et les liens de l’explorateur sont des sources primaires ; les mesures comportementales sur quatorze jours ci-dessus concernent la période d’observation fixe.

### 0x097e3f339d0b023605e12a6b81e2d6cb7571475a

- [0x62c01526…](https://basescan.org/tx/0x62c01526c5beb13cad96634ec80e837e576df496905f1bac8019c6ffa3e358c3) — 0.001000 USDC

### 0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a

- [0x8d2ccd6a…](https://basescan.org/tx/0x8d2ccd6a3e04a769ecc680f298999dd082a0a2eba936f00a96c0e4ec5902b934) — 0.001000 USDC

### 0xa1d1c0cf717402ff3651aa4873ccf96410b01978

- [0x58ddb2e7…](https://basescan.org/tx/0x58ddb2e77e574ddda75fd74df6f3dbf94e2795e22c36f8a01a506c544ff4ada3) — 0.001000 USDC

### 0xc9c7b38c0942914fc8ea12063bc92dcd3b581670

- [0x3ca4f279…](https://basescan.org/tx/0x3ca4f2791f4f851a574f4abd7cb949e1b05fb00dadeb77b83fb3d0e36a608fb2) — 0.001000 USDC

### 0xec2abd3eda89bed90124736e317e847d5fb6d034

- [0x8c0acafc…](https://basescan.org/tx/0x8c0acafc219977d53b7431c734b1d29b7ef6db90cab5091c7aabe4a0f69a2c0a) — 0.005000 USDC
- [0xef5f2a2c…](https://basescan.org/tx/0xef5f2a2c81b7f6021c73a966eceb453055481a333256a2475a8ac8f011183ffd) — 0.002000 USDC
- [0xcc3231d1…](https://basescan.org/tx/0xcc3231d1e3d39a27838c4e3fbb87db85fb61da5048c49690e5511e844fc83b7e) — 0.005000 USDC
- [0xa7662362…](https://basescan.org/tx/0xa7662362f207a4d0059b32c1204f1171fa7ec7fae9b8567b9ef7cc6cd1f37885) — 0.005000 USDC
- [0xd197a66a…](https://basescan.org/tx/0xd197a66ab0eb069c0acfddfd280dcefe123ec576878d1a924f5407e8f87afda9) — 0.003000 USDC
- [0x68a7bb46…](https://basescan.org/tx/0x68a7bb46a2839d40c1001e1bf1dab036abb849939203e7a4131183581158d8ce) — 0.002000 USDC
- [0x4f712436…](https://basescan.org/tx/0x4f712436cfe5bb039f55d2a536a484b2847e5e29cb86edc97ec6c33552bd9c13) — 0.002000 USDC
- [0x9fe21127…](https://basescan.org/tx/0x9fe21127d045e4398ca6b9d6889241a15c861f7f08d812d7ef66e1846e8cfe04) — 0.002000 USDC
- [0x23207988…](https://basescan.org/tx/0x23207988c28a9bd13e4d2fcd3dffd4e1ae47594077802890ca57fafeb4215bb0) — 0.001000 USDC
- [0x0e65e22c…](https://basescan.org/tx/0x0e65e22cea86dadeeb4bb1736f94bd8f28538011e8024c98eb4d4fc7d25d4121) — 0.001000 USDC
- [0x56eafab5…](https://basescan.org/tx/0x56eafab52aa8a3889b97ba4a013ea3f508cafa934c0acb7958bbd3ec43d78bb6) — 0.001000 USDC
- [0x55049b03…](https://basescan.org/tx/0x55049b036d022dc9970490abbdf079d70bf15f8afdf35f65782472b8f115ef89) — 0.001000 USDC
- [0x6322b987…](https://basescan.org/tx/0x6322b987ed57b94367753a7cfdb4bb1b31bf9efaf183d2ccf0036a057c75959f) — 0.005000 USDC
- [0x415ec0e3…](https://basescan.org/tx/0x415ec0e389ce17a9936de89a28b7ba0fc1717b2f50e756196e074851d712bd9b) — 0.001000 USDC
- [0x4feb47e1…](https://basescan.org/tx/0x4feb47e132ac06e7b5081756cdfb8b6b5436fae1ab62701d04139982b74f0186) — 0.001000 USDC
- [0x9bb91375…](https://basescan.org/tx/0x9bb91375a64c6da4a5fc78e8df817fe86b51487a36c3c98a73a78513edd4d637) — 0.001000 USDC
- [0x3bc01e29…](https://basescan.org/tx/0x3bc01e29b53d187320b18bd1794526c85b8addc456fc0e8e7756fd17fd971ea6) — 0.001000 USDC
- [0x068b1930…](https://basescan.org/tx/0x068b1930266c6235ee31cbfa87690b8ef14c519bba4f1dafd0b36872b836fe95) — 0.002000 USDC
- [0x4700749e…](https://basescan.org/tx/0x4700749eb35c98129e0abc6adb2f9ee66d76dc7bc8ba2e509341f858146d35d6) — 0.005000 USDC
- [0xf93149b9…](https://basescan.org/tx/0xf93149b946d87295924977c2d46f76f163b4d93354bc3fa7aa1f5c04e392736d) — 0.005000 USDC

