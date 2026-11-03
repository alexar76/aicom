# Faire de votre API existante un nœud

[English](run-a-node.md) · [Русский](run-a-node.ru.md) · [Español](run-a-node.es.md) · [Français](run-a-node.fr.md) · [中文](run-a-node.zh.md)

Vous vendez déjà quelque chose en HTTP — une route x402, un endpoint REST. Pour que les hubs de la
fédération vous trouvent, inutile de faire tourner un hub : `aimarket node` est un petit processus
qui se place à côté de votre API et parle le protocole pour elle.

- Il publie un `/.well-known/ai-market.json` signé et un manifeste signé des routes que vous
  nommez, signés à neuf à chaque lecture.
- Il répond à `POST /ai-market/v2/invoke` en appelant **votre** route — GET avec l'entrée en
  paramètres de requête, ou POST avec elle en JSON — et laisse passer les en-têtes de paiement
  x402 dans les deux sens : votre 402 arrive tel quel à l'acheteur, et la relance payée arrive à
  votre route avec son paiement. x402 V1 (offre dans le corps) et V2 (offre dans
  `PAYMENT-REQUIRED`) fonctionnent tous deux.
- Il signe un reçu pour chaque réponse 2xx de votre route.

Votre argent reste où il est : le nœud ne détient, ne vérifie ni ne déplace aucun paiement. Votre
route continue de le faire exactement comme aujourd'hui.

## 1. Décrivez vos routes

```bash
pip install "aimarket-hub[pqc]"            # Python 3.11+, ou : uvx --from "aimarket-hub[pqc]" aimarket …
aimarket node init                         # écrit node.toml
```

```toml
name = "Acme weather"
url = "https://api.acme.example"           # où les autres hubs joignent le nœud
upstream = "http://127.0.0.1:8000"         # votre API, telle qu'elle tourne aujourd'hui

[[capability]]
id = "weather.now@v1"
product = "acme-weather"
description = "Current weather for a city"
price_usd = 0.002                          # doit égaler ce que demande le 402 de votre route
method = "GET"
path = "/weather"
input_schema = { type = "object", required = ["city"], properties = { city = { type = "string" } } }
```

Une route gratuite, si vous en avez une, est la preuve la plus rapide pour l'admission : le bac à
sable l'appelle et vérifie la signature du nœud sur le reçu. Un nœud seulement payant est admis
sur sa porte : un appel non payé doit répondre 402 avec une offre qui nomme votre portefeuille et
le même prix que `price_usd`.

## 2. Lancez-le à côté de votre API

```bash
aimarket node serve --config node.toml     # → 127.0.0.1:9090 par défaut (--host, --port)
```

Envoyez-lui deux chemins de votre domaine public et laissez le reste tel quel. Caddy :

```
api.acme.example {
    handle /.well-known/ai-market.json { reverse_proxy 127.0.0.1:9090 }
    handle /ai-market/* { reverse_proxy 127.0.0.1:9090 }
    handle { reverse_proxy 127.0.0.1:8000 }
}
```

nginx : `location = /.well-known/ai-market.json` et `location /ai-market/`, tous deux avec
`proxy_pass http://127.0.0.1:9090;`. La clé du nœud (`data/node_signing_key` par défaut, et
`_mldsa` à côté) est son identité : sauvegardez-la.

## 3. Vérifiez, puis frappez

```bash
aimarket doctor --url https://api.acme.example   # le contrôle d'admission que feront les autres hubs
aimarket node knock                               # annonce à modelmarket.dev (--hub pour un autre)
```

La réponse contient `assay_url`, où le verdict apparaît. Sur un `pass`, les hubs à admission
automatique indexent vos capabilities : elles apparaissent dans leur recherche, dans leur
endpoint MCP (`market_search` / `market_invoke` sur `https://modelmarket.dev/mcp`) et sur leur
page `/hubs`. Un acheteur passé par un hub rencontre le 402 de votre route tel quel — en-tête compris —
et vous paie directement ; les hubs ne prennent pas de frais de routage sur une vente x402 directe
(le nœud déclare `payment_rails.seller_direct`, c'est ainsi qu'ils le savent).

## Ce qu'il ne fait pas

- Il ne fixe pas les prix et ne prend aucune part, pas plus que les hubs qui vous routent une vente
  x402 directe : ce qu'un acheteur paie à votre route vous revient en entier.
- Il ne rend pas votre route sûre ni correcte, et ne garantit pas la réponse : le reçu, signé par
  le nœud, atteste que votre route a répondu (capability, prix, heure, latence, succès), pas ce
  qu'elle a répondu.
- Le trafic d'acheteurs dans la fédération reste faible. Les compteurs en direct sont publics :
  `https://verify.modelmarket.dev/demand.json`.
