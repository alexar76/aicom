# Lancez gratuitement votre propre hub de capteurs

[English](sensor-operator.md) · [Русский](sensor-operator.ru.md) · [Español](sensor-operator.es.md) · [Français](sensor-operator.fr.md) · [中文](sensor-operator.zh.md)

**Déployez et utilisez gratuitement Hub + GAIA sur votre propre infrastructure**, en gardant le contrôle de vos clés, données et services. Ce guide s’adresse aux propriétaires de stations, aux communautés locales de capteurs et aux petits intégrateurs IoT. Vous fournissez l’infrastructure ; vous ne nous payez ni licence ni abonnement pour cet usage auto-hébergé.

Après la procédure normale d’admission, la fédération AIMarket constitue un marché potentiel pour vos offres. La vente d’accès est facultative et vous fixez vos prix ; aucun acheteur ni revenu n’est garanti. L’exemple de service payant ci-dessous décrit cette possibilité. Vous n’avez pas besoin d’acheter des données ni de réaliser une vente pour commencer à utiliser votre propre hub.

Un premier service utile fournit une observation locale réelle là où l’acheteur ne dispose que d’une prévision ou de peu de mesures. Précisez le lieu, les grandeurs mesurées, la fréquence et les limites du capteur. Une copie d’une source publique doit apporter une utilité supplémentaire.

Il s’agit d’un guide reproductible, pas du compte rendu d’un déploiement matériel déjà réalisé ni d’une promesse de revenus. Après admission, la fédération rend le service découvrable ; l’acheteur décide toujours de l’utiliser.

## Ce que vous exploitez

Le parcours est **votre capteur → votre adaptateur → GAIA → votre Hub → acheteur**. GAIA reçoit les mesures et signe le résultat ; Hub publie le service, traite le mode de paiement configuré et renvoie un reçu. La signature établit la provenance et l’intégrité, pas une preuve indépendante de l’exactitude de la mesure.

Une activité commerciale autour d’une API n’est pas nécessaire. Il faut toutefois exporter les mesures au format JSON ci-dessous. L’endpoint d’ingestion n’est pas un connecteur automatique pour tout appareil Tasmota, ESPHome, Home Assistant, TTN ou SenML : la conversion propre au matériel appartient à l’adaptateur.

Le récepteur générique accepte actuellement `temperature_c`, `humidity_pct`, `pressure_hpa`, `pm2_5_ugm3`, ainsi que `latitude` et `longitude`, obligatoires. N’envoyez que les champs réellement mesurés. Son identifiant est `feeder-iot-01` ; la capacité vendue est `gaia.iot.read@v1`. Une instance offre actuellement un seul récepteur IoT générique. Plusieurs stations nécessitent une extension explicite ou des instances distinctes, pas des identifiants inventés.

## 1. Démarrez un fournisseur GAIA privé

Prérequis : Docker, `curl`, `jq`, un adaptateur exportant de vraies mesures et un Hub initialisé selon le [guide opérateur](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.fr.md). L’exemple exécute GAIA dans Docker et Hub directement sur **la même machine**. Construisez l’image depuis la racine d’AICOM, à une révision que vous avez vérifiée :

```bash
docker build -f gaia/Dockerfile -t local/gaia-sensor .
export GAIA_FEEDER_TOKEN="$(openssl rand -hex 32)"
docker run -d --name gaia-sensor \
  -p 127.0.0.1:9320:9320 \
  -v gaia-sensor-data:/data \
  -e GAIA_FEEDER_TOKEN \
  -e GAIA_ENABLE_LIVE=1 -e GAIA_FEEDER_ENABLED=1 \
  -e GAIA_SIM_CONTROL=0 -e AIFACTORY_PROD=1 \
  -e GAIA_PUBLIC_URL=http://127.0.0.1:9320 \
  -e GAIA_KEY_DIR=/data/devices \
  -e GAIA_SIGNING_KEY_PATH=/data/gaia_signing_key \
  local/gaia-sensor
```

Conservez le jeton généré dans votre configuration privée ; le client d’envoi doit utiliser la même valeur. Préservez le volume `/data`, avec les clés de la passerelle et des appareils. GAIA est liée à loopback : les acheteurs passent par Hub. Un capteur distant nécessite un accès HTTPS protégé ou un réseau privé vers l’ingestion, pas un port fournisseur directement exposé.

Le démarrage actuel exige `GAIA_ENABLE_LIVE=1` et `GAIA_FEEDER_ENABLED=1`. GAIA enregistre aussi des relais et simulateurs intégrés ; ce guide ne publie que votre service `gaia.iot.read@v1` sur Hub. Ne présentez pas les stations simulées comme votre matériel.

## 2. Envoyez une observation réelle

Votre adaptateur doit écrire `station-reading.json` sous cette forme. Avant l’envoi, remplacez chaque marqueur entre guillemets par un véritable **nombre JSON** : le modèle n’est pas une mesure. `observed_at` représente l’heure de l’observation en secondes Unix, pas la retransmission d’une ancienne mesure.

```json
{
  "device_id": "feeder-iot-01",
  "observed_at": "<observed_at>",
  "fields": {
    "latitude": "<latitude>",
    "longitude": "<longitude>",
    "temperature_c": "<temperature_c>"
  }
}
```

Envoyez les données, puis lisez le même appareil localement :

```bash
curl --fail-with-body -sS http://127.0.0.1:9320/feeder/v1/ingest \
  -H "Authorization: Bearer $GAIA_FEEDER_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @station-reading.json

curl --fail-with-body -sS http://127.0.0.1:9320/ai-market/v2/invoke \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"gaia.gateway","capability_id":"gaia.iot.read@v1","input":{"device_id":"feeder-iot-01"}}'
```

L’ingestion doit renvoyer `ok: true`, et l’invocation un résultat contenant le relevé et son attestation. Vérifiez l’appareil, les valeurs et la source. Examinez aussi le JSON : un relevé indisponible peut renvoyer `ok: false` avec HTTP 200. Cet appel local au fournisseur vérifie la connexion ; ce n’est pas une vente.

Envoyez les mises à jour plus souvent que la limite actuelle de fraîcheur de 600 secondes. Sans données ou avec des données périmées, le récepteur est indisponible. Il conserve actuellement seulement la dernière observation **en mémoire du processus** : après un redémarrage, envoyez une nouvelle mesure avant d’accepter des achats. La persistance des clés ne constitue pas un historique des mesures.

## 3. Publiez le relevé sur votre propre Hub

Dans le répertoire et l’environnement du Hub initialisé, définissez `SENSOR_PAY_TO` avec **l’adresse de votre portefeuille de réception**, jamais une clé privée. Le prix d’exemple est de $0.002 par appel ; choisissez le vôtre. Récupérez localement la clé publique de GAIA et fixez-la dans l’entrée du catalogue :

```bash
: "${SENSOR_PAY_TO:?Set SENSOR_PAY_TO to your receiving wallet address}"
GAIA_PROVIDER_KEY="$(curl -fsS http://127.0.0.1:9320/.well-known/ai-market.json | jq -er .signer_public_key)"
export AIMARKET_INVOKE_HOST_GATEWAY=127.0.0.1
aimarket add gaia.iot.read@v1 \
  --product gaia.gateway \
  --url http://127.0.0.1:9320/ai-market/v2/invoke \
  --provider-pubkey "$GAIA_PROVIDER_KEY" \
  --price 0.002 --pay-to "$SENSOR_PAY_TO" \
  --name "Local station readings" \
  --description "Current measurements from the operator's own station" \
  --input-schema '{"type":"object","properties":{"device_id":{"type":"string","enum":["feeder-iot-01"]}},"required":["device_id"],"additionalProperties":false}'
```

Démarrez ou redémarrez `aimarket serve` avec la même base de données et `AIMARKET_INVOKE_HOST_GATEWAY=127.0.0.1` dans l’environnement du service. Cela autorise explicitement Hub à appeler son fournisseur local. Pour un Hub conteneurisé ou distant, suivez le réseau du [guide de production](https://github.com/alexar76/aimarket-hub/blob/main/docs/production-deployment.md) ; le loopback d’un conteneur désigne ce conteneur.

GAIA signe déjà les réponses du fournisseur ; `--provider-pubkey` permet de les vérifier. La commande locale `aimarket add` publie votre propre service. Une publication sur le Hub d’un autre opérateur suit un parcours d’admission distinct.

## 4. Vérifiez l’exigence de paiement

Appelez Hub sans paiement et sans en-tête sandbox :

```bash
curl -sS -i http://127.0.0.1:9083/ai-market/v2/invoke \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"gaia.gateway","capability_id":"gaia.iot.read@v1","source_hub":"local","input":{"device_id":"feeder-iot-01"}}'
```

Un service payant correctement configuré doit renvoyer `402` et une offre de paiement. Contrôlez montant, réseau, actif et destinataire avant de payer. Un relevé livré sans paiement ne valide pas ce contrôle.

`--pay-to` déclare le destinataire ; terminez la configuration du paiement direct au vendeur dans le [guide opérateur](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.fr.md) avant l’ouverture publique. L’acheteur suit l’offre, autorise le paiement et relance l’invocation avec un client compatible. Conservez le reçu et confirmez la réception des fonds. Les crédits locaux créés pour les tests ne sont pas des revenus externes.

Cet exemple n’active pas Pay-on-Verified. Un relevé signé n’implique ni règlement conditionné à une vérification ni remboursement automatique d’un paiement direct déjà effectué. Le revenu net dépend des appels réellement payés, des frais, de l’hébergement et de l’entretien ; l’adhésion à la fédération ne garantit aucune vente.

## 5. Rejoignez la fédération selon les règles habituelles

Déployez Hub sur un HTTPS public selon le guide de production, gardez GAIA privée et remplacez `hub.example.com` par votre adresse. Conservez la capacité gratuite signée `hub.ping@v1`, créée par quickstart, pour les contrôles d’admission. Préservez clés et base de données lors du passage en production.

```bash
aimarket quickstart --url https://hub.example.com --no-buyer
aimarket doctor --url https://hub.example.com
curl --fail-with-body -sS https://modelmarket.dev/ai-market/v2/federation/announce \
  -H 'Content-Type: application/json' \
  -d '{"hub_url":"https://hub.example.com","hub_name":"My sensor hub"}'
```

Consultez le verdict à l’`assay_url` renvoyée. La visibilité dans le moniteur ou une annonce pending **ne** vaut pas admission, indexation ou routage. Corrigez les contrôles échoués selon les règles existantes. Voir [rejoindre la fédération](join-the-federation.fr.md). L’acheteur doit conserver le `source_hub` obtenu par la recherche lors de l’invocation.

Le point du capteur sur ATLAS est distinct de l’admission du Hub. L’apparition automatique sur la carte n’est pas promise : suivez le [guide GAIA → ATLAS](i18n/add-gaia-atlas-sensor.fr.md) pour les types pris en charge ou une nouvelle intégration revue.

## Connectez votre station

Pour discuter d’une première connexion, ouvrez une [GitHub Discussion](https://github.com/alexar76/aicom/discussions). Indiquez modèle, champs disponibles, zone approximative, intervalles d’observation et de mise à jour, format d’export et possibilité d’exploiter un Hub. Ne publiez aucun jeton ni aucune clé privée.

Le premier résultat utile est une mesure fraîche de votre appareil achetée par un client externe, avec reçu et paiement confirmé. Mesurez ensuite les achats répétés et la continuité du service. Identifiez séparément les achats de test. Un opérateur communautaire peut coordonner plusieurs propriétaires, mais le récepteur actuel à une seule station exige une extension ou une instance distincte par station indépendante.

Voir aussi : [sources et récepteurs GAIA](https://github.com/alexar76/gaia/blob/main/docs/i18n/LIVE-RELAYS.fr.md) · [guide opérateur Hub](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.fr.md) · [indicateurs publics de demande](https://verify.modelmarket.dev/demand.json).
