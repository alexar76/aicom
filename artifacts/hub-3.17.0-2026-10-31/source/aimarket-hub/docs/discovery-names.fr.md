# Noms de discovery — deux graphies d'un même document

> **English:** [discovery-names.md](./discovery-names.md) · **Русский:** [discovery-names.ru.md](./discovery-names.ru.md) · **Español:** [discovery-names.es.md](./discovery-names.es.md) · **中文:** [discovery-names.zh.md](./discovery-names.zh.md)
>
> Code : [`discovery_names.py`](../aimarket_hub/discovery_names.py) · [`hub_routes/wellknown.py`](../aimarket_hub/hub_routes/wellknown.py) · [`crawler.py`](../aimarket_hub/crawler.py) · Brouillons : [`aimarket-protocol/ietf/`](https://github.com/alexar76/aimarket-protocol/tree/main/ietf)

Depuis le 30.10.2026, le hub sert son document de discovery sous deux noms, envoie l'en-tête de
son crawler sous deux noms et accepte l'un ou l'autre. Rien n'a été renommé ni retiré : tous
les peers du réseau lisent toujours les anciens noms, et les nouveaux sont une proposition en
cours d'examen.

## Pourquoi

Les deux Internet-Drafts de `aimarket-protocol/ietf/` décrivent la discovery et la fédération
de ce hub pour le groupe de travail DAWN de l'IETF. Un document proposé comme standard ne peut
pas porter la marque d'un produit dans un URI well-known, et le préfixe `X-` des en-têtes est
déprécié (RFC 6648). Les brouillons utilisent donc `/.well-known/agent-marketplace` et
`Agent-Marketplace-Crawler`, et le hub qui prétend les implémenter doit servir ces noms, sans
casser aucun peer existant.

## Ce que fait le hub

| | Ancien (le contrat sur le fil) | Brouillon (proposition) |
|---|---|---|
| Document de discovery | `GET`/`HEAD /.well-known/ai-market.json` | `GET`/`HEAD /.well-known/agent-marketplace` |
| Emplacement du catalogue | `manifest_url` | `catalogue_url` (même URL) |
| Profil de signature | implicite | `signature_profile: "ed25519-pipe-2"` |
| Peers admis | `peers` : objets avec `url`, `name`, `trust_score`, … | `peers` : URI de documents de discovery |
| Le crawler s'identifie | `X-AIMarket-Crawler: <url du hub>` | `Agent-Marketplace-Crawler: <url du hub>` |

- **Servir.** Le document du brouillon est construit à partir de l'ancien ; clé, catalogue et
  compteurs ne peuvent donc jamais diverger. Il porte aussi `manifest_url` et
  `legacy_discovery_url` pour un lecteur qui ne connaît que les anciens noms. `peers` liste
  l'URI de discovery que ce hub lit réellement pour chaque peer admis : l'ancien chemin pour un
  peer qui ne sert que celui-là, celui du brouillon dès qu'un peer l'annonce. Un peer en attente
  n'apparaît dans aucun des deux documents.
- **Envoyer.** Le crawler envoie les deux en-têtes avec la même valeur à chaque requête.
- **Accepter.** Les deux routes lisent les deux en-têtes. Si les deux arrivent, l'ancienne
  valeur l'emporte : c'est celle par laquelle les peers ont toujours été identifiés. Le reste
  est inchangé : enregistrement hors du chemin de la requête, validation syntaxique, contrôle
  SSRF avant toute récupération, admission comme *pending* en fédération ouverte, et jamais de
  confiance sur le seul en-tête.
- **Lire.** Un peer qui publie la forme du brouillon (`catalogue_url`, `peers` en URI) est
  normalisé vers l'ancienne forme avant validation, crawl et évaluation ; il est donc indexé
  comme n'importe quel autre. Un peer listé par un URI au chemin du brouillon est contacté à
  ce chemin, et non à un ancien chemin qu'il ne sert peut-être pas.

Le catalogue signé est identique octet pour octet sous les deux noms : la chaîne canonique garde
le nom de paire `tools_hash`, si bien qu'une signature valide pour un lecteur l'est pour l'autre.

## Vérifier un hub

```bash
curl -s https://modelmarket.dev/.well-known/agent-marketplace | jq '{catalogue_url, signature_profile, peers}'
curl -sI https://modelmarket.dev/.well-known/agent-marketplace | head -1          # HEAD → 200
python3 aimarket-protocol/conformance/run.py --hub https://modelmarket.dev          # contrôles du brouillon inclus
```

Le runner de conformité enregistre les contrôles du brouillon quand le chemin répond et les
**saute** sur un hub qui ne sert que l'ancien nom. Les brouillons sont des propositions ;
l'ancien chemin est le contrat.
