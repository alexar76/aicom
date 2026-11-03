# Déploiement en production d'un AIMarket Hub indépendant

[English](production-deployment.md) · [Русский](production-deployment.ru.md) · [Español](production-deployment.es.md) · [Français](production-deployment.fr.md) · [中文](production-deployment.zh.md)

> La terminologie suit le [glossaire de localisation](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md) canonique. Les noms de produits, identifiants de protocole, URL, commandes CLI et variables d'environnement ne sont jamais traduits.

Ce guide permet à un opérateur indépendant de déployer un hub public et de réussir l'admission dans la fédération sans contourner manuellement la confiance. Il couvre un serveur Ubuntu, nginx, TLS, Alien Monitor facultatif, une capability payante signée et l'enrôlement facultatif de l'agent de nœud SKOPOS.

## 1. Architecture cible et limite de confiance

```text
Internet
  └─ nginx :80/:443
       ├─ /hub/      → AIMarket Hub sur 127.0.0.1:9083
       ├─ /monitor/  → Alien Monitor sur 127.0.0.1:9100 (facultatif)
       └─ provider   → backend capability sur 127.0.0.1:<port>, non public
```

Utilisez un compte Unix non privilégié par service. Seuls nginx et SSH écoutent publiquement. Les bases SQLite et clés Ed25519 restent hors du checkout Git. L'origin public du hub constitue la limite de sécurité : discovery, manifeste signé et `invoke` publié doivent employer ce même origin.

Un hôte dédié tel que `hub.example.com` est le plus simple. Un sous-chemin tel que `https://example.com/hub` fonctionne aussi, mais exige toutes les règles proxy du §7. Une règle manquante peut laisser l'API saine tout en cassant les assets UI, WebSocket ou URL de fédération.

## 2. Prérequis

- Ubuntu 24.04 LTS ou autre Linux systemd pris en charge.
- Adresse IPv4/IPv6 publique et enregistrements DNS `A`/`AAAA` pointant déjà vers l'hôte.
- Domaine valide sous votre contrôle ; ne demandez pas TLS avant la propagation DNS mondiale.
- Accès SSH par clé Ed25519. Gardez la première session ouverte jusqu'au succès d'une seconde session uniquement par clé.
- Au moins 2 CPU, 2 Go de RAM et 10 Go libres pour Hub + Monitor.
- HTTPS sortant pour Git, ACME, crawl de fédération et enrôlement SKOPOS.

```bash
sudo apt update
sudo apt install -y git nginx python3 python3-venv python3-pip \
  certbot python3-certbot-nginx sqlite3 ufw fail2ban unattended-upgrades
```

## 3. Épingler les révisions du code

Ne déployez jamais directement une branche mobile. Notez et examinez un commit SHA, puis utilisez exactement cette révision :

```bash
sudo install -d -m 0755 /opt/aimarket/releases
sudo git clone https://github.com/alexar76/aimarket-hub.git \
  /opt/aimarket/releases/aimarket-hub-<sha>
sudo git -C /opt/aimarket/releases/aimarket-hub-<sha> checkout --detach <sha>
git -C /opt/aimarket/releases/aimarket-hub-<sha> rev-parse HEAD
python3 -m venv /opt/aimarket/venvs/hub
/opt/aimarket/venvs/hub/bin/pip install --upgrade pip
/opt/aimarket/venvs/hub/bin/pip install "/opt/aimarket/releases/aimarket-hub-<sha>[pqc]"
```

L'extra `[pqc]` installe le signataire et le vérificateur ML-DSA-65. Sans lui, le hub échoue en mode fermé sur toute signature hybride et ne peut pas se fédérer avec les hubs qui signent en hybride — ce que font tous les hubs AIMarket.

Répétez pour `alexar76/alien-monitor` et `alexar76/skopos` si nécessaire. Conservez les SHA dans le dossier de déploiement. Pour un patch de hardening, archivez le patch et la source intacte hors du checkout ; `git status --short` ne doit montrer que les changements intentionnels. Exécutez la suite de tests sur cette révision exacte en CI ou sur un hôte de build.

## 4. Utilisateurs, répertoires et permissions

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin aimarket-hub
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin aimarket-provider
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin alien-monitor
sudo install -d -o aimarket-hub -g aimarket-hub -m 0750 /var/lib/aimarket/hub
sudo install -d -o aimarket-provider -g aimarket-provider -m 0750 /var/lib/aimarket/provider
sudo install -d -o root -g root -m 0700 /etc/aimarket
sudo install -d -o root -g root -m 0700 /var/backups/aimarket
```

- Clés de signature du hub (`hub_signing_key` et, avec la signature post-quantique, `hub_signing_key_mldsa` à côté) : `0600`, propriétaire `aimarket-hub`.
- Clé du fournisseur : `0600`, propriétaire `aimarket-provider`.
- Fichiers d'environnement : `0600`, propriétaire root.
- Répertoires SQLite : écriture réservée au service propriétaire.
- Sauvegardes avec clés : `0600` dans un répertoire `0700`.

Ne placez jamais clé privée, admin token, enrollment ticket ou mot de passe de base dans Git, argv, historique shell ou journal public.

## 5. Configuration du hub

Créez `/etc/aimarket/hub.env` :

```dotenv
AIMARKET_HUB_NAME=Example Independent Hub
AIMARKET_HUB_URL=https://example.com/hub
AIMARKET_BIND_HOST=127.0.0.1
AIMARKET_DB_PATH=/var/lib/aimarket/hub/hub.db
AIMARKET_SIGNING_KEY_PATH=/var/lib/aimarket/hub/hub_signing_key
# Signature hybride (Ed25519 + ML-DSA-65) ; nécessite l'extra [pqc] (section 3). La clé ML-DSA est écrite
# à côté de la clé classique sous <AIMARKET_SIGNING_KEY_PATH>_mldsa ; les pairs l'épinglent dès qu'ils la voient.
AIMARKET_PQC=1
AIFACTORY_PROD=1
# Ne faites confiance aux adresses forwarded que depuis nginx local ; jamais *.
AIMARKET_TRUSTED_PROXIES=127.0.0.1,::1
# La même adresse décide SELF pour les serveurs listés dans ecosystem.json (à côté
# de la base) : voir docs/traffic-classes.fr.md.
# Les routes payantes qu'un autre service sert sur la même origine (un sidecar x402 sous /x402/)
# rejoignent /openapi.json, où les indexeurs x402 (x402scan, AgentCash) les cherchent. Même origine
# que AIMARKET_HUB_URL uniquement ; les routes du hub ne sont jamais remplacées. Rafraîchi toutes les 10 minutes.
# AIMARKET_OPENAPI_MERGE_URLS=https://hub.example.com/x402/openapi.json
# Un opérateur indépendant ne doit pas dépendre de l'oracle d'un autre opérateur.
AIMARKET_ORACLE_FAMILY_URL=off
AIMARKET_AUTO_CRAWL=1
AIMARKET_CRAWL_INTERVAL_S=3600
AIMARKET_CRAWL_REFRESH_MAX=64
AIMARKET_SEED_LIST=https://modelmarket.dev/.well-known/ai-market.json
AIMARKET_SEED_PUBKEYS=https://modelmarket.dev/.well-known/ai-market.json=<seed-ed25519-public-key>
AIMARKET_FEDERATION_ASSAY=1
AIMARKET_FEDERATION_ASSAY_SANDBOX=1
AIMARKET_FEDERATION_AUTO_ADMIT=1
AIMARKET_CREDITS_ENABLED=1
AIMARKET_CREDITS_OPEN_SIGNUP=1
AIMARKET_CREDITS_FREE_GRANT_USD=0

# Vendre du crédit contre USDC (docs/credits-topup.fr.md, section 5.1 ci-dessous). Éteint par défaut.
AIMARKET_TOPUP_ENABLED=1
# Un portefeuille qui reçoit les recharges ET RIEN D'AUTRE (son adresse seulement, jamais sa clé).
# Alors le hub le surveille et crédite chaque dépôt lui-même ; sans lui, les recharges vont à
# AIMARKET_X402_PAY_TO et quelqu'un doit présenter chacune.
AIMARKET_TOPUP_PAY_TO=<portefeuille de recharge dédié>
AIMARKET_TOPUP_MIN_CONFIRMATIONS=2
# Où les paiements sont lus (séparés par des virgules) ; sinon, nœuds publics de Base.
# AIMARKET_SETTLE_RPC_URL=https://mainnet.base.org,https://base-rpc.publicnode.com
# Le veilleur de dépôts — actif dès que AIMARKET_TOPUP_PAY_TO est défini ; valeurs par défaut.
# AIMARKET_DEPOSIT_WATCH=1
# AIMARKET_DEPOSIT_WATCH_INTERVAL_S=60
# AIMARKET_DEPOSIT_WATCH_CHUNK_BLOCKS=500
# AIMARKET_DEPOSIT_WATCH_LOOKBACK_BLOCKS=1800
AIMARKET_ADMIN_TOKEN=<secret>
AIMARKET_PUBLISHER_TOKENS=<publisher-id>:<secret>
AIMARKET_ECOSYSTEM_LABELS=publisher-id=Display Name
AIMARKET_CORS_ORIGINS=https://example.com
```

Règles importantes :

1. `AIMARKET_HUB_URL` est l'URL externe, avec `/hub` si un sous-chemin est utilisé ; jamais `localhost` en production.
2. Le hub crée sa clé Ed25519 au premier démarrage. Sauvegardez-la immédiatement. La remplacer change l'identité fédérée et ressemble à une prise de contrôle pour les pairs qui l'ont épinglée. Avec `AIMARKET_PQC=1`, il crée aussi la clé ML-DSA-65 `<chemin de la clé>_mldsa` : sauvegardez les deux et gardez-les sur un même volume.
3. La seed key est publique, mais l'épingler est une décision de confiance. Extrayez-la du well-known signé via TLS vérifié et consignez la comparaison.
4. Sans admin token, les routes opérateur doivent être fail-closed (refus par défaut).
5. Avec SQLite, arrêtez le hub ou utilisez l'API de sauvegarde SQLite. Préférez PostgreSQL pour plusieurs processus ou une forte écriture.
6. Donnez à chaque fournisseur son propre publisher token limité au sujet. Ne réutilisez jamais l'admin token du hub comme credential fournisseur. Pour plusieurs modules du même hub, définissez `AIMARKET_ECOSYSTEM_LABELS=publisher-id=Display Name,...` ; l'extension signée `ecosystem.nodes` exprime leur appartenance sans les faire passer pour des pairs fédérés indépendants.
7. À chaque cycle, le crawler doit rafraîchir un ensemble borné de pairs actifs déjà approuvés, même si le seed graph courant ne les référence plus. Dimensionnez `AIMARKET_CRAWL_REFRESH_MAX` pour ce roster ; sinon un pair valide de 30 capabilities peut rester indexé indéfiniment avec un ancien manifeste d'une seule capability.

### 5.1 Vendre du crédit contre USDC : un portefeuille à part

Avec `AIMARKET_TOPUP_ENABLED=1`, n'importe quel agent achète du crédit en USDC sur Base par
lui-même ([credits-topup.fr.md](credits-topup.fr.md)). Donnez à cette porte son propre portefeuille,
et personne n'aura à surveiller la chaîne ni à créditer quoi que ce soit à la main :

1. **Créez un portefeuille qui recevra les recharges et rien d'autre.** Le hub n'a besoin que de son
   adresse, jamais de sa clé : rien de ce que fait le hub ne dépense depuis lui. Gardez la clé là où
   l'opérateur garde les clés de trésorerie.
2. **Définissez les variables** ci-dessus (`AIMARKET_CREDITS_ENABLED=1`, `AIMARKET_TOPUP_ENABLED=1`,
   `AIMARKET_TOPUP_PAY_TO=<adresse>`). Sous systemd, dans le fichier env ou un drop-in
   (`Environment=AIMARKET_TOPUP_PAY_TO=0x…`) ; sous Docker Compose, le conteneur ne voit que ce que le
   fichier compose transmet : ajoutez `AIMARKET_TOPUP_PAY_TO: ${TOPUP_PAY_TO:-}` à
   l'`environment:` du hub et `TOPUP_PAY_TO=0x…` à `.env`.
3. **Sauvegardez la base et redémarrez le hub.** La migration `050_deposit_watch` ajoute
   `payer_wallets`, `deposit_watch_cursor` et `hub_deposits`.
4. **Vérifiez** : `pay_to` est le nouveau portefeuille et `deposit_watch.enabled` vaut `true` (éteint,
   `reason` dit ce qui manque). Liez une fois le portefeuille de chaque entreprise qui paiera par
   virement simple. Lisez ce qui est arrivé de personne de connu :

```bash
curl -s "$AIMARKET_HUB_URL/.well-known/ai-market.json" | jq '.payment_rails.credits.topup | {pay_to, deposit_watch}'
curl -s "$AIMARKET_HUB_URL/ai-market/v2/accounts/$ACCOUNT_ID/payer-wallets" -H "Authorization: Bearer $AIMARKET_ADMIN_TOKEN" \
     -H 'Content-Type: application/json' -d '{"address": "0x…"}'
curl -s "$AIMARKET_HUB_URL/ai-market/v2/admin/deposits" -H "Authorization: Bearer $AIMARKET_ADMIN_TOKEN"
```

5. **Alertez dessus** : ajoutez le hub à `AICOM_ALERT_DEPOSIT_HUBS` de l'alerteur de l'écosystème
   (seuls les hubs dans son `AICOM_ALERT_SCOPE` sont vérifiés)
   (`deposit_watch_on:<hub>` — le hub devrait surveiller et ne le fait pas ;
   `deposits_unattributed:<hub>` — de l'argent est arrivé d'un portefeuille que personne n'a lié).

Le premier balayage commence `AIMARKET_DEPOSIT_WATCH_LOOKBACK_BLOCKS` (1800, environ une heure sur
Base) blocs derrière la tête, un intervalle après le démarrage du hub : un virement fait peu avant
l'activation est donc retrouvé ; un plus ancien est crédité à la main avec son `tx_hash`. Un nouveau
portefeuille reçoit un nouveau curseur, et l'ancien n'est plus lu.

Ne pointez jamais `AIMARKET_TOPUP_PAY_TO` vers un portefeuille qui reçoit d'autre argent : chaque
virement entrant serait lu comme une recharge. Le hub refuse ses propres portefeuilles x402 et
destinataire des paiements (`AIMARKET_X402_PAY_TO`, `AIMARKET_PAYMENT_RECIPIENT` ; `reason` dans le
well-known) ; il ne peut pas savoir ce qu'un autre portefeuille reçoit, ni si un autre hub utilise le même.

## 6. Service systemd

Créez `/etc/systemd/system/aimarket-hub.service` :

```ini
[Unit]
Description=Independent AIMarket Hub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=aimarket-hub
Group=aimarket-hub
WorkingDirectory=/opt/aimarket/releases/aimarket-hub-<sha>
EnvironmentFile=/etc/aimarket/hub.env
ExecStart=/opt/aimarket/venvs/hub/bin/python -m aimarket_hub serve
Restart=on-failure
RestartSec=5s
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictNamespaces=yes
LockPersonality=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=/var/lib/aimarket/hub
UMask=0027
MemoryMax=1G
TasksMax=256

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aimarket-hub
sudo systemctl status aimarket-hub --no-pager
```

Liez l'application à loopback si la version prend en charge bind-host. Si elle écoute sur `0.0.0.0:9083`, UFW doit toujours bloquer ce port et nginx doit rester le seul chemin public.

## 7. nginx, sous-chemins et TLS

Configuration essentielle à adapter pour les certificats et rate limits :

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name example.com;
    location ^~ /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 301 https://$host$request_uri; }
}
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name example.com;
    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_tickets off;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    client_max_body_size 1m;

    location = /hub { return 301 /hub/; }
    location ^~ /hub/ {
        proxy_pass http://127.0.0.1:9083/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }
    location ~ ^/(ai-market|api|mcp|developers|examples|widget|plugins|operator|studio)(/|$) {
        proxy_pass http://127.0.0.1:9083;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
    location = /hub-ui-i18n.json { proxy_pass http://127.0.0.1:9083/hub-ui-i18n.json; }
    location = /cap-descriptions-i18n.json { proxy_pass http://127.0.0.1:9083/cap-descriptions-i18n.json; }
}
```

Pour Alien Monitor, compilez le frontend avec `VITE_BASE_PATH=/monitor/`, proxifiez `/monitor/` vers son port HTTP loopback et configurez `/monitor/ws` avec les en-têtes WebSocket `Upgrade`/`Connection` et un timeout long. Une build conçue pour `/` peut répondre HTTP 200 tout en perdant JavaScript et CSS sous le sous-chemin.

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d example.com
sudo certbot renew --dry-run
systemctl is-enabled certbot.timer
```

N'activez HSTS qu'après validation HTTPS de tous les sous-domaines couverts.

Si la racine du domaine héberge un portail séparé, exécutez-le comme un autre service non privilégié sur loopback et ne le proxifiez qu'en dernier fallback nginx. Placez les préfixes API du portail, par exemple `/api/v1/`, avant la règle large de compatibilité root-relative du hub ; sinon le portail peut s'afficher tandis que son API part silencieusement vers le hub. Gardez `/hub/`, `/monitor/` et les chemins fournisseur explicites, et ne redirigez pas `/` vers `/hub/` lorsque le portail est l'entrée prévue.

## 8. Publier une capability réelle sans contourner le paiement

Pour la première capability de contrôle locale, arrêtez le hub et exécutez le quickstart idempotent sous son compte. Il crée un static pack exécutable sans modèle ni fournisseur externe ; remplacez-le par votre backend avant de le proposer comme produit :

```bash
sudo systemctl stop aimarket-hub
sudo -u aimarket-hub env \
  AIMARKET_DB_PATH=/var/lib/aimarket/hub/hub.db \
  AIMARKET_HUB_URL=https://example.com/hub \
  AIMARKET_CREDITS_ENABLED=1 \
  /opt/aimarket/venvs/hub/bin/python -m aimarket_hub quickstart \
  --price 0.01 --grant 0
sudo systemctl start aimarket-hub
```

La buyer key produite est secrète et affichée une seule fois. Avec un grant nul, elle n'a aucun solde ; rangez-la dans un password manager ou révoquez-la. Pour un vrai fournisseur, suivez [Exploiter ce hub vous-même](operator-quickstart.md), n'enregistrez qu'un backend sous votre contrôle et conservez sa clé de signature.

Une capability de production comporte un backend interne du fournisseur, qui travaille et signe le résultat, et un gateway public du hub, qui contrôle sécurité, paiement, routage et reçus.

Le manifeste signé doit publier le gateway du hub, par exemple `https://example.com/hub/ai-market/v2/invoke`, jamais une URL brute `/provider/invoke`. Limitez le fournisseur à loopback, à une connexion mutuellement authentifiée ou à l'adresse propre de l'hôte. Une version qui expose cette URL doit être mise à jour ou recevoir un backport examiné.

Pour une capability payante, une requête non autorisée — même avec `X-AIMarket-Sandbox-Visitor` — doit répondre `402`, nommer un canal de paiement utilisable et annoncer exactement le prix du catalogue signé. Autrement, une capability réellement gratuite peut effectuer le travail et fournir un reçu signé. Un endpoint de démonstration sans preuve ne suffit pas.

Vérifications minimales :

- `/hub/.well-known/ai-market.json` valide le schéma fourni ;
- `manifest_url` est public et same-origin ;
- les signatures well-known/manifeste se vérifient avec la clé Ed25519 publiée ;
- `generated_at` est récent ;
- le canonical à cinq champs couvre nombre de capability, timestamp, protocol version, `tools_hash` et `by_hub_hash` ;
- tout champ numérique est un nombre et non `null` ;
- `invoke_url` est same-origin et passe par le gateway du hub ;
- le prix `402` égale `price_per_call_usd` ;
- une réponse réussie du fournisseur porte une signature vérifiable.

## 9. Admission dans la fédération

Après les contrôles locaux, annoncez via le protocole public :

```bash
curl -fsS -X POST https://modelmarket.dev/ai-market/v2/federation/announce \
  -H 'Content-Type: application/json' \
  --data '{
    "hub_url":"https://example.com/hub",
    "hub_name":"Example Independent Hub",
    "well_known_url":"https://example.com/hub/.well-known/ai-market.json"
  }'
curl -fsS 'https://modelmarket.dev/ai-market/v2/federation/assay?url=https%3A%2F%2Fexample.com%2Fhub'
```

```text
announce ou crawl entrant → pending/quarantine → sandbox assay → pass → trusted/indexed
```

Ne contournez pas la confiance avec operator panel, admin endpoint ou peer table modifiée. Un pair pending peut attendre le cycle suivant du récepteur ; une heure est normale. Pour `review` ou `fail`, corrigez la preuve vivante et attendez la relance documentée. Conservez le dossier qui précise le contrôle échoué.

Après admission, vérifiez roster, recherche fédérée et Alien Monitor par nom et `capability_id`, pas seulement par HTTP 200.

## 10. Sécurité de l'hôte

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw limit 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Activez les jails Fail2ban `sshd`, `nginx-http-auth`, `nginx-botsearch` et les mises à jour de sécurité automatiques. Examinez bans et journaux : l'installation seule n'est pas de la supervision.

Ordre impératif pour SSH :

1. Installez la clé publique de l'opérateur.
2. Ouvrez une seconde session avec `BatchMode=yes` et cette clé.
3. Inspectez `sshd -T` ; un drop-in cloud-init peut en remplacer un autre.
4. Réglez `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin prohibit-password`, ou désactivez root et utilisez sudo.
5. Rechargez SSH, gardez la première session et testez une troisième connexion par clé uniquement.

Ne fermez jamais l'unique session fonctionnelle avant ce test indépendant.

## 11. Sauvegarde et restauration

Sauvegardez la base SQLite et les bases channel/provenance, les clés privées du hub et du fournisseur (la clé Ed25519 et, avec `AIMARKET_PQC=1`, sa compagne ML-DSA `<chemin de la clé>_mldsa`), les env files/drop-ins root, nginx, les SHA épinglés et les patchs intentionnels.

Utilisez `sqlite3 /path/hub.db '.backup /staging/hub.db'` ou arrêtez le service avant copie. Produisez une archive réservée à root, gardez plusieurs générations et sortez une copie chiffrée de l'hôte. Une sauvegarde non restaurée n'est pas vérifiée.

Pour restaurer : arrêtez hub/fournisseur ; restaurez bases et clés avec propriétaires/modes d'origine ; restaurez la configuration puis lancez `systemctl daemon-reload` et `nginx -t` ; démarrez et confirmez qu'aucune clé publique n'a changé (`signature.public_key` et `signature.pq_public_key` dans `/.well-known/ai-market.json`) ; refaites schéma, signatures, `402`, recherche et fédération.

## 12. Alien Monitor et SKOPOS

Exécutez Alien Monitor comme service LIVE séparé et non privilégié. Ciblez le hub local, proxifiez HTTP API et WebSocket séparément, puis vérifiez après reboot que le tick progresse. Des métriques financières vides peuvent simplement signifier aucun trafic ; un tick figé ou un health endpoint défaillant est une panne.

Traitez chaque Hub indépendant comme un système stellaire distinct. Dédupliquez par identité stable et URL normalisée, imposez une distance minimale entre les centres des hubs et groupez `ecosystem.nodes` autour de leur Hub propriétaire. Réservez d'abord le child budget du Hub aux `ecosystem.nodes` signés, puis tracez les liens vers les pairs fédérés ; un grand roster ne doit pas masquer les fournisseurs propres. L'assistant IA doit résoudre les noms dans le live snapshot courant — y compris les requêtes localisées ou translittérées — avant de revenir à l'aide statique, afin que les nouveaux modules restent visibles sans clé LLM externe.

SKOPOS utilise un agent de nœud push-only restreint. L'enrôlement exige un ticket officiel à usage unique :

1. Émettez le ticket dans le control plane SKOPOS pour l'entrée serveur exacte.
2. Exécutez l'installer généré comme root sur le nœud.
3. Saisissez le ticket par stdin masqué, jamais par argv, URL, historique ou chat.
4. Confirmez sa consommation, les permissions strictes du credential file et le bon fonctionnement des timers.

Le nœud ne peut pas émettre son propre ticket : seul le control plane SKOPOS peut le créer. S'il n'existe pas, laissez l'installer préparé à l'arrêt et marquez l'enrôlement comme pending ; ne devinez jamais le ticket et n'en copiez pas depuis un autre nœud.

Ne créez pas de credential manuellement dans la base SKOPOS et n'accordez ni groupe Docker ni sudo illimité à l'agent.

## 13. Liste de recette finale

```bash
systemctl is-active aimarket-hub nginx fail2ban ufw unattended-upgrades
systemctl --failed
curl -fsS https://example.com/hub/.well-known/ai-market.json
curl -fsS https://example.com/hub/ai-market/v2/manifest
curl -sS -o /tmp/invoke.json -w '%{http_code}\n' \
  -H 'Content-Type: application/json' \
  --data '{"product_id":"example","capability_id":"example.echo@v1","input":{}}' \
  https://example.com/hub/ai-market/v2/invoke
ufw status verbose
sshd -T | egrep '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication) '
```

Redémarrez l'hôte et recommencez depuis un réseau externe. Tous les services doivent revenir ; seuls SSH/HTTP/HTTPS sont publics ; le dry-run TLS réussit ; signatures et clé persistent ; le fournisseur ne peut être contourné ; le hub reste visible dans la fédération ; Alien Monitor se reconnecte avec un tick LIVE croissant ; une sauvegarde récente et sa procédure de restauration existent.

## 14. Mise à niveau et rollback

1. Créez un release et virtualenv nouveaux et immuables ; aucun `git pull` dans le release actif.
2. Lisez les migrations, notamment les chemins SQLite channel/provenance.
3. Sauvegardez bases et clés.
4. Lancez tests et federation assay local.
5. Modifiez seulement la cible `WorkingDirectory`/`ExecStart`, redémarrez et refaites la recette.
6. Revenez au code précédent si nécessaire, mais jamais à travers une migration de base incompatible sans la sauvegarde correspondante.

L'identité de signature (la clé Ed25519 et, avec la signature post-quantique, sa compagne `_mldsa`) et le ledger de paiement sont un état persistant, pas des artefacts de release. Leur perte ou remplacement silencieux n'est pas un redéploiement ordinaire.

## 15. Déplacer le hub vers un autre hôte

Le conteneur et son volume de données sont la partie facile. Ce qui casse un déménagement, c'est
ce qui tourne **à côté** du hub sur l'hôte : rien de cela n'est dans l'image, un `/health` au vert
n'en dit rien, et l'ancien hôte continue de faire tourner sa copie pour un hub qui n'y est plus.
Le 2026-10-01, le hub de modelmarket.dev a changé d'hôte, et le tunnel vers le signataire de
l'escrow ainsi que le balayage de règlement sont restés en arrière : pendant deux jours aucun
débit de l'escrow n'a atteint la chaîne et rien n'a alerté, car l'ancien balayage continuait de
publier « ok, rien à soumettre ».

**À déplacer avec le conteneur**

| Quoi | Où cela vit | Sur le nouvel hôte |
|---|---|---|
| Données du hub (`hub.db`, registre des canaux, stockage des autorisations d'escrow, deposit claims) | le volume de données | copier depuis une sauvegarde récente prise hub arrêté (§11) |
| Identité de signature | volume de données / chemin de la clé : `hub_signing_key` et `hub_signing_key_mldsa` | les deux clés, jamais de nouvelles (§14) : les pairs qui ont épinglé la clé post-quantique en rejettent une nouvelle jusqu'à ce que chacun la ré-épingle |
| Tunnel vers le signataire de l'escrow | `escrow-signer-tunnel.service` (SSH `-L` vers l'hôte du signataire) | nouvelle clé SSH sur le nouvel hôte ; sur l'hôte du signataire, l'ajouter comme `restrict,port-forwarding,permitopen="127.0.0.1:9500",command="/bin/false"` ; épingler la clé d'hôte du signataire en comparant son empreinte au `known_hosts` de l'ancien hôte ; écouter sur `127.0.0.1:9500` **et** sur la passerelle du réseau Docker du conteneur du hub ; pare-feu : autoriser le sous-réseau de ce réseau vers la passerelle sur le 9500, rien d'autre |
| Balayage de règlement | `aicom-settlement-sweep.{service,timer}` + `/usr/local/lib/aicom-settlement/escrow_settlement_sweep.py` | installer, faire pointer `--publish` vers le répertoire d'où le nouvel hôte sert `verify.<domaine>`, l'exécuter une fois |
| Canari de paiement | `aicom-payment-canary.{service,timer}` (`scripts/payment_canary.py`) | installer, publier dans le même répertoire `verify.<domaine>` ; l'alerteur prévient quand `status.json` devient périmé |
| Auditeur (THEMIS) | rejoint l'espace réseau du hub | le recréer avec `--network container:<hub>` après le hub (sinon il est orphelin) |
| Clé du vérificateur de Pay-on-Verified | `/root/.metis-verify-key` (0600) → `AIMARKET_VERIFY_METIS_*` | copier de serveur à serveur, jamais via un terminal |
| Fournisseurs maison | unités systemd (`weather-witness`, `pov-demo`) | installer, puis revérifier leurs location nginx |
| location nginx, TLS, hooks de renouvellement | `/etc/nginx`, `/etc/letsencrypt` | revérifier chaque `location` qui fait proxy vers un port de l'hôte |

**Un seul script fait les trois premières lignes et les vérifie :** `scripts/hub_host_companions.sh --install` sur le nouvel hôte (définissez `AICOM_SIGNER_SSH_HOST` si le hub signe via le signataire externe), `--verify` pour vérifier (il échoue sauf si les unités tournent, si le conteneur du hub atteint le signataire et si les deux rapports sont frais), `--disable` sur l'ancien hôte. `scripts/deploy_hub_rebuild.sh` lance `--verify` à la fin de chaque déploiement et sort avec le code 3 s'il manque quelque chose.

**Puis éteignez l'ancien hôte** — chaque unité de la liste, explicitement
(`systemctl disable --now`). Un balayage laissé là-bas lit un stockage où plus personne n'écrit et
annonce un succès pour toujours.

**Prouvez le chemin de l'argent avant de déclarer le déménagement terminé**

```bash
# le conteneur du hub atteint le signataire par le tunnel (affiche l'adresse du signataire)
docker exec <hub> python -c "import httpx;print(httpx.get('http://<passerelle>:9500/health').text[:120])"
# le balayage a tourné ICI : checked_at date de quelques minutes, errors est vide
curl -s https://verify.<domaine>/settlement.json | jq '{checked_at, ok, errors}'
# plus rien n'écoute sur l'ancien hôte
ssh <ancien-hôte> 'systemctl is-active escrow-signer-tunnel aicom-settlement-sweep.timer'   # inactive, inactive
# Pay-on-Verified est toujours branché : enabled, votre vérificateur, escrow_hub déclaré
curl -s https://<domaine>/.well-known/ai-market.json | jq '.pay_on_verified.enabled, .contracts.entries'
```

La bulle UNI a sa propre liste (sa chaîne privée, pare-feu, réglages de l'acheteur) :
[docs/uni-realm-runbook.fr.md](https://github.com/alexar76/aicom/blob/main/docs/uni-realm-runbook.fr.md).
