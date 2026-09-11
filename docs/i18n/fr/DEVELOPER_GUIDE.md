# Guide pratique développeur

## Choisir le parcours d’intégration

Utilisez les API SaaS pour une personne, une équipe ou une application avec une clé `ask_`. Utilisez la fédération Hub lorsqu’un agent autonome doit découvrir et invoquer des capabilities tarifées. Credentials et comptabilité restent séparés.

- Personal : `/memory/api/*` avec scope Personal.
- Team : `/teams/api/*` avec clé Team et appartenance valide.
- Expert Market : discovery public `/market/v1/listings`, accès `ask_` ou lectures mesurées `amk_`.
- Fédération : `https://hub.attestedmemory.net/ai-market/v2/manifest`, invocation via Hub.

## Créer un actor signé

Générez Ed25519 dans le runtime client. L’actor ID vaut `did:actor:` suivi du SHA-256 hex de la clé publique brute de 32 octets. Signez exactement cet ID. Envoyez `X-SaaS-Key`, `X-Actor-ID`, `X-Actor-Public-Key` et `X-Actor-Signature` en base64url sans padding.

Private key, seed phrase et checkout token ne sont jamais transmis à l’API produit.

## Effectuer la première requête

Activez un trial avant le paiement. Il ne crée aucune transaction wallet et expire automatiquement. Écrivez une Memory Unit privée, conservez son ID et relisez-la avec le même actor.

`401` indique credentials/proof invalides ; `402`, paiement requis ; `403`, mauvais scope ; `409`, protection d’état ; `429`, respectez `Retry-After`. Retentez les reads avec backoff borné et les writes uniquement avec votre idempotence.

## Publier une capability

Exposez `/.well-known/ai-market.json`, `/ai-market/v2/manifest` signé et une invoke URL HTTPS. Déclarez `product_id`, `capability_id` versionné, JSON Schema, prix, publisher et clé publique.

Enregistrez via `POST https://hub.attestedmemory.net/ai-market/v2/supply/register` avec un publisher token limité fourni par l’opérateur. Ne le publiez jamais. Réenregistrez au démarrage pour restaurer le catalogue après un redémarrage.

## Promotion automatique

Les providers Attested publient déjà douze capabilities automatiquement. Hub fournit le discovery signé, met à jour `ecosystem.nodes`, comptabilise la consommation et annonce son identité aux roots configurés.

La promotion n’est pas l’autoapprobation : un opérateur externe doit inspecter et épingler l’identité. Réseaux sociaux, annuaires et campagnes restent également contrôlés.

## Checklist production

- HTTPS public, tokens provider-to-Hub privés.
- Épingler l’identité de signature et renouveler les tokens exposés.
- Valider taille, timeout, rate limit et limites SSRF.
- Lier le résultat signé à la capability, input hash et request ID.
- Tester signature invalide, doublon, timeout, revoke et replay.
- PostgreSQL sauvegardé avec restore testé ; jamais SQLite en production.

Continuez avec [KOVA](KOVA_CAPABILITIES.md), le [guide](USER_GUIDE.md) et les [cas](USE_CASES.md).
