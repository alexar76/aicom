# Pay-on-Verified pour un effet physique — un agent ne paie une prise qu'une fois que le compteur a prouvé qu'elle s'est allumée

> 🌐 [English](pay-on-verified-device-demo.md) · [Русский](pay-on-verified-device-demo.ru.md) · [Español](pay-on-verified-device-demo.es.md) · **Français** · [中文](pay-on-verified-device-demo.zh.md)

Base mainnet, 2026-10-16, hub modelmarket.dev (version `899ecbdb4`). Un agent acheteur a payé **0,05 $**
pour allumer une prise pendant 60 secondes. Le prix est resté en séquestre (escrow) jusqu'à ce que le
vérificateur de GAIA ait contrôlé la commande signée et les relevés du compteur avant et après. Personne n'a
fait appel dans l'heure : le hub a débité 0,05 $ sur la chaîne et l'acheteur a récupéré **0,95 $** de son
dépôt de 1,00 $. La première démonstration, un agent qui engage deux inconnus pour factoriser un nombre, est
[ici](pay-on-verified-demo.fr.md) ; le fonctionnement du pilotage d'appareils est décrit [dans la
documentation de GAIA](https://github.com/alexar76/gaia/blob/main/docs/i18n/ACTUATION.fr.md).

## Qui est qui — à lire d'abord

- **Le vendeur est à nous.** GAIA (`gaia.gateway`, éditeur `gaia`) est exploitée par l'opérateur de modelmarket.dev.
- **La prise est simulée.** `plug-sim-01` est un radiateur de 1500 W qui n'existe qu'en logiciel, et chaque
  réponse le dit (`"simulated": true`). Cela prouve le chemin de l'argent et de la vérification, pas le
  matériel. Le vrai matériel est une prise Tasmota avec puce de mesure d'énergie ([ACTUATION](https://github.com/alexar76/gaia/blob/main/docs/i18n/ACTUATION.fr.md)).
- **Le portefeuille de l'acheteur est distinct, mais c'est nous qui l'alimentons :**
  `0x097e3F339D0b023605e12A6B81E2d6Cb7571475a`, le même que dans la première démonstration. Pour ce passage,
  le propriétaire l'a rechargé de 0,50 USDC depuis le portefeuille de l'opérateur `0x1218…Ad0a`. Cela prouve
  le mécanisme, pas une demande de tiers.
- **Le juge est le propre vérificateur du vendeur.** Le hub envoie `gaia.actuate@v1` à `gaia.verify@v1`, le
  contrôle exact de GAIA, au lieu de son jury de LLM. GAIA est donc à la fois vendeur et juge. Ce n'est
  acceptable que parce que le contrôle est déterministe, sur des preuves signées que chacun peut rejouer, et
  parce que l'acheteur peut faire appel d'un succès devant la cour d'appel du hub, un autre vérificateur.
  Voir « Ce que cela ne montre pas ».

## Ce qu'il a fallu changer d'abord, et pourquoi

La capacité a été mise en vente le matin même. Cinq choses la séparaient d'un appel payé et vérifié.

| # | Problème | Ce que nous avons fait | Pourquoi |
|---|---|---|---|
| 1 | Le hub n'avait qu'un vérificateur pour tout : le jury de LLM de Metis. | Des routes de vérificateur par capacité, `AIMARKET_VERIFY_ROUTES` (hub `71be57610`). `gaia.actuate@v1` → `gaia.verify@v1` ; tout le reste reste chez Metis. | Un modèle de langage ne peut pas vérifier une signature Ed25519 ni la physique d'un compteur, et un jury peut s'abstenir et laisser impayé un effet honnête. Une route inutilisable **refuse** de vérifier ; elle ne se rabat jamais en silence sur Metis. |
| 2 | Le point de vérification de GAIA répondait 503 à tout le monde en production : le compose ne transmettait jamais `GAIA_VERIFY_TOKEN` au conteneur. | Jeton créé sur l'hôte de GAIA et transmis au conteneur (`c718f810e`) ; le hub l'envoie en Bearer depuis la variable que nomme la route. | Un verdict de succès fait avancer la marque anti-rejeu de GAIA : un point de vérification ouvert pourrait faire échouer tous les règlements en attente. Seul le hub peut l'appeler. |
| 3 | modelmarket.dev tournait sur une ancienne version rapiécée à la main, sans le code des routes. | Le hash de chaque fichier du conteneur en production a été comparé à git : aucun correctif n'existait seulement sur le serveur. Puis une mise en production complète depuis main avec `deploy_hub_rebuild.sh`, l'ancien conteneur conservé pour revenir en arrière. | Le code doit être dans ce qui tourne réellement, et une mise en production ne doit pas perdre en silence un correctif qui ne vit que sur le serveur. |
| 4 | `gaia.actuate@v1` n'apparaissait que comme capacité fédérée, et Pay-on-Verified ne retient l'argent que pour les capacités que le hub exécute lui-même. | Une inscription locale : éditeur `gaia` (éditeur propre à l'opérateur), clé de signature de GAIA épinglée, signatures de réponse obligatoires. | Sans elle, le bloc `verify` est ignoré et rien n'est retenu. |
| 5 | Le canari de paiement alertait : « travail payant servi gratuitement ». | C'était l'essai gratuit propre à Independent, sur un pair dont le hub n'est que l'intermédiaire. Le canari sait désormais pour qui le hub vend (`899ecbdb4`). | Une fausse alerte sur l'argent apprend à ignorer les vraies. |

Avant de dépenser quoi que ce soit, la route a été prouvée par un essai gratuit (sandbox) : la prise a
consommé 1491 W et le verdict était `passed`, signé `verifier: gaia.verify@v1` (trace
`gaia_c12c4efa209ea762`). Aucun argent n'a bougé.

## Le passage payant, étape par étape

| # | Étape | Ce qui s'est passé |
|---|---|---|
| 1 | La tâche et la limite | « Allume plug-sim-01 pendant 60 s. » Limite : un dépôt de 1,00 $ en séquestre, que le contrat ne laisse pas dépasser. |
| 2 | Trouver le vendeur | `GET /ai-market/v2/search` a renvoyé `gaia.actuate@v1`, `gaia.gateway`, 0,05 $, éditeur `gaia`. L'acheteur ne prend que l'inscription **locale**, car la fédérée n'est jamais vérifiée. |
| 3 | Le travail, avec preuves | GAIA a signé la commande (`act_0aec0a640ed36476`), relevé le compteur avant, allumé, puis relevé de nouveau. Attendu ≥ 1000 W en 20 s ; **observé 1506,2 W**. La prise s'est éteinte d'elle-même à 10:53:15 UTC. L'appel complet a duré 15,5 s. |
| 4 | Le verdict | `gaia.verify@v1` : **passed**, score 1,0 avec le seuil du hub à 0,7 (trace `gaia_e34da88c0a648c51`). Il est resté provisoire jusqu'à la fermeture de la fenêtre d'appel à 11:52:29 UTC ; personne n'a fait appel et il est devenu définitif. |
| 5 | L'argent | Le signataire du hub a débité **0,05 $** sur la chaîne à 12:03 UTC. L'acheteur a demandé la clôture, attendu la fenêtre de règlement d'une heure, puis réglé : **0,05 $ au hub, 0,95 $ de retour**. |

Coût pour l'acheteur : **0,05 $** et environ 0,000007 ETH de gaz. Solde 1,094148 → 1,044148 USDC.
Le journal du passage est [`pov-demo/runs/2026-10-16T105204Z.json`](../pov-demo/runs/2026-10-16T105204Z.json).

## Transactions (Base mainnet)

Contrats : séquestre AIMarketEscrowV2 [`0xa4cb6ef7…1B2Eb`](https://basescan.org/address/0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb),
débité par le signataire du hub [`0xBE0bBE44…C5f1`](https://basescan.org/address/0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1),
USDC [`0x833589fC…02913`](https://basescan.org/address/0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913).
Canal de séquestre `0x8c89c278…e8f3`.

| Étape | Qui | Bloc | Tx |
|---|---|---|---|
| `USDC.approve(escrow, 1.00)` | acheteur | 52679290 | [`0xf765fe99…b52d`](https://basescan.org/tx/0xf765fe99e6570fb7590abb4f9a492b8544d52f96185eb8990931215e3e01b52d) |
| `openChannel` 1,00 $ | acheteur | 52679291 | [`0x6ed3cdb4…19c8`](https://basescan.org/tx/0x6ed3cdb421b1a1619d8a695f857feb34dceac398f27cf9fabd678f9e7c1b19c8) |
| verdict **passed** par `gaia.verify@v1`, définitif après la fenêtre d'appel | — | — | — |
| `debitChannel` 0,05 $ | signataire du hub | 52681416 | [`0x6973d111…fe10`](https://basescan.org/tx/0x6973d11160f4f58951f42c8ee65ba3639d2b376b02e037e5747663ea7d28fe10) |
| `requestClose` | acheteur | 52681422 | [`0xbfb451bd…52cf`](https://basescan.org/tx/0xbfb451bd33db3af0db7f3258c6f0fab56ded47204e9c4f9a28540df575db52cf) |
| `settleChannel` : 0,05 $ au hub, **0,95 $ de retour** | acheteur | 52683232 | [`0x1e2b0aa7…9f25`](https://basescan.org/tx/0x1e2b0aa794924a373635dc651e20afd6a1baa2be5e5f3d80724fbff1fcef9f25) |

## Ce qui a mal tourné en chemin

1. **L'oracle de confiance était injoignable.** Le lien entre l'hôte du hub et celui des oracles était
   dégradé ce jour-là : LUMEN répondait en 4 à 35 secondes, ou pas du tout. Le hub interroge LUMEN sur un
   éditeur pour lequel il n'a pas de confiance enregistrée, donc les cinq premiers essais gratuits ont été
   refusés avec « trust oracle unavailable » et rien n'a été débité. Le sixième a obtenu une réponse, le hub a
   enregistré une confiance de 0,70 pour `gaia`, et le passage payant a utilisé cette valeur enregistrée. Le
   problème réseau lui-même reste ouvert.
2. **Trop court pour être sûr.** L'essai qui est passé demandait 5 secondes et GAIA l'a refusé : `plug-sim-01`
   accepte de 10 à 900 secondes, pour que rien ne reste allumé sans limite. Rien n'a été débité.
3. **Le premier envoi du débit a échoué**, et le passage suivant, 15 minutes plus tard, l'a fait aboutir.
   L'autorisation signée dure deux heures de plus que la fenêtre d'appel précisément pour qu'une nouvelle
   tentative fonctionne encore.
4. **La mise en production avait son propre piège.** Le contrôle de version du hub exige que le client
   pipeline publié corresponde à la version du hub. Le client servi était le 3.15.1 pour un hub en 3.15.28 :
   la mise en production se serait annulée d'elle-même. Le client a été reconstruit d'abord.

## Ce que cela ne montre pas

- Du vrai matériel : la prise est simulée. Une prise Tasmota signe ce que rapporte son compteur : la garde du
  rapport, pas la preuve que le matériel ne peut pas mentir.
- Un juge indépendant : GAIA vend et vérifie. Les preuves sont signées avec des clés que GAIA détient, donc
  aucun vérificateur, ni GAIA ni un LLM, ne détecterait des preuves forgées par le détenteur de la clé. La
  protection de l'acheteur est que chacun peut rejouer le contrôle (`POST /v1/verify`, ou `gaia.verify@v1`
  avec le lot), plus la cour d'appel.
- Une demande de tiers : le vendeur et l'argent de l'acheteur sont à nous.

## Le refaire soi-même

```bash
python3 pov-demo/buyer.py --key-file <json de votre portefeuille> --task actuate --duration 60 --yes
```

Il faut 1,00 $ USDC et environ 0,00005 ETH sur Base. Avec la fenêtre d'appel d'une heure et la fenêtre de
règlement d'une heure, le passage dure environ deux heures ; tout revient sauf 0,05 $.
