# UNI — guide d'exploitation

> 🌐 [English](uni-realm-runbook.md) · [Русский](uni-realm-runbook.ru.md) · [Español](uni-realm-runbook.es.md) · **Français** · [中文](uni-realm-runbook.zh.md)

Aide-mémoire pour lancer, déplacer et vérifier la bulle UNI. Le pourquoi est dans
[uni-realm.md](uni-realm.md) ; cette page dit quoi faire et dans quel ordre.

## Deux chaînes, jamais une seule

| Chaîne | Qui la fait tourner | Adresse vue par les conteneurs | Ce qu'elle porte |
|---|---|---|---|
| **Chaîne de la bulle** | conteneur `anvil-uni`, volume `anvil_uni_state` | `http://172.17.0.1:8546` | l'argent du hub : jeton `0x5fbd…0aa3`, escrow `0xe7f1…0512`, le portefeuille du hub (Anvil #1) et l'acheteur (Anvil #2) |
| **Chaîne de démonstration** | le conteneur Alien Monitor UNI (`alien-monitor`), avec son propre Anvil | `http://172.17.0.1:8545` (via `uni-rpc-bridge`) | le monde de la carte : loterie, NFT, ACEX (PulseAMM, registre, prêts) |

Le hub UNI **règle sur la chaîne de la bulle** (`AIMARKET_RPC_BASE=…:8546`) et lit la loterie et le
NFT sur la chaîne de démonstration (`ALIEN_EVM_RPC=…:8545`). La chaîne de démonstration est jetable :
le moniteur l'efface au-delà de 64 Mo et redéploie ses contrats à de nouvelles adresses. L'argent
n'y vit jamais.

## Déplacer UNI vers un autre serveur — liste d'étapes

1. Copier le volume `anvil_uni_state` (arrêter d'abord `anvil-uni`, pour que l'état sur disque soit complet).
2. Démarrer `anvil-uni` sur le nouveau serveur — le `docker run` de
   [uni-realm.md](uni-realm.md#standing-it-up), publié sur `172.17.0.1:8546` uniquement.
3. Pare-feu : les conteneurs doivent joindre `172.17.0.1:8546`, internet non.
   `ufw allow proto tcp from 172.17.0.0/16 to 172.17.0.1 port 8546`
4. Vérifier que l'économie est bien sur la chaîne de la bulle : du code au jeton et à l'escrow, des
   soldes chez Anvil #1 et #2. Vide → l'état n'a pas été copié ; lancer `scripts/deploy_uni_realm.py`
   contre **8546** (jamais 8545) et reprendre les adresses qu'il affiche.
5. Démarrer le hub depuis le monorepo : `bash deploy/uni-hub.sh <image> <jeton> <escrow>`.
   Jamais depuis une copie sur le serveur, jamais en fusionnant `hub.env.snippet` dans le hub.
6. Déplacer aussi ce que vend le hub — cela tourne sur le serveur lui-même, pas dans un conteneur : les
   six satellites (copier `/var/lib/uni-satellites`, puis `bash deploy/uni-satellites.sh`) et le
   fournisseur de `uni.answer@v1` (copier `/var/lib/uni_provider_key`, puis `bash deploy/uni-provider.sh`).
   Le hub épingle les deux clés : une nouvelle clé, c'est un pair refusé ou des signatures refusées.
   Ensuite, un crawl (`POST /ai-market/v2/federation/crawl`, admin) et arrêter les anciennes copies sur
   le serveur précédent.
7. Pointer l'acheteur du moniteur sur la chaîne de la bulle :
   `ALIEN_UNIVERSE_BUYER_RPC=http://172.17.0.1:8546`, `ALIEN_UNIVERSE_BUYER_TOKEN=<jeton>`.
8. Lancer `python3 deploy/uni-hub-verify.py` **sur le serveur lui-même**. Chaque ligne doit être `ok`.
9. En une quinzaine de minutes, le journal du moniteur affiche `hub declares its settlement wallet`
   et un canal s'ouvre ; le bandeau rouge « REALM ECONOMY STALLED » ne doit pas revenir.

## `deploy/uni-hub-verify.py`

À lancer après chaque démarrage ou recréation du hub. Au-delà des règles de publication, il vérifie
le côté argent auprès des chaînes elles-mêmes :

- le hub règle sur sa propre chaîne, pas sur la chaîne de démonstration du moniteur ;
- un seul jeton pour les dépôts et x402, et il existe sur la chaîne de règlement ;
- une seule adresse d'escrow partout, et elle existe sur la chaîne de règlement ;
- payé sur un seul portefeuille partout (destinataire = payTo x402 = hub de l'escrow) ;
- la loterie caritative existe sur la chaîne de démonstration.

`--no-chain` saute les vérifications de chaîne (hors du serveur), `--no-live` les publiques.

## Quand la chaîne de démonstration change

Après une réinitialisation du moniteur, les adresses de la loterie, du NFT et d'ACEX changent. Les
nouvelles sont dans `data/alien-monitor/universe/hub.env.snippet`. N'en prendre **que** ceci :

- hub : `AIMARKET_CHARITY_LOTTERY_ADDRESS`, `LOTTERY_ADDRESS`, `HUB_LOTTERY_ADDRESS`, `AIMARKET_NFT_CONTRACT` ;
- ARGUS-UNI : les lignes `ARGUS_UNI_*` de `argus/.env`, puis `docker compose up -d argus-uni`.

Ne jamais reporter dans le hub son `AIMARKET_PAYMENT_RECIPIENT`, son `AIFACTORY_PAYMENT_VERIFY_STUB`
ni ses lignes RPC : elles décrivent la chaîne de démonstration et Anvil #0, et cassent le règlement.
Le hub ignore `AIMARKET_ADDR_UNI_*` (son réseau s'appelle `base`).

L'Anvil du moniteur écrit son état toutes les 30 s (`ALIEN_ANVIL_STATE_INTERVAL_S`) : un redémarrage
ne perd plus les contrats déployés depuis la dernière sortie propre.

## Symptômes

| Sur la carte / dans le journal | Cause | Correction |
|---|---|---|
| `settlement chain http://172.17.0.1:8546 is unreachable` | `anvil-uni` arrêté, ou règle de pare-feu absente | étapes 2–3 |
| `channel/open … moved no USDC to the configured recipient` | l'acheteur a payé un autre portefeuille, ou le destinataire du hub n'est pas Anvil #1 | vérificateur ; l'acheteur abandonne lui-même ce dépôt |
| `transaction not found or not yet mined` à chaque tour | acheteur et hub sur des chaînes différentes | étape 7, vérificateur |
| vérificateur : « settlement token exists … FAIL » | le hub pointe vers une chaîne sans son jeton | étape 4 |
| vérificateur : « charity lottery exists … FAIL » | la chaîne de démonstration a été réinitialisée | « Quand la chaîne de démonstration change » |
| `listing_not_sellable` dans le journal de l'acheteur | normal : cette offre n'a pas d'adresse de paiement ; les canaux sont payés au portefeuille que déclare le hub | — |
| `Invoke error for uni.answer@v1: timed out` | le fournisseur ne tourne pas sur ce serveur ; la connexion reste bloquée au-delà du délai de l'acheteur | étape 6 (`deploy/uni-provider.sh`) |
| `no match for …` à chaque tour ; le catalogue compte quelques outils au lieu d'environ 93 | les satellites ne tournent pas sur ce serveur (nginx répond 502 sur `/sat/*`) | étape 6 (`deploy/uni-satellites.sh`), puis un crawl |
