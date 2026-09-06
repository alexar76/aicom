# Guide utilisateur

## Paiement et clé

Dans `/billing`, choisir Personal, Team ou Market. La facture indique le montant,
le destinataire, le token, la chain et l’expiration. Envoyer le montant exact sur
Base, attendre les confirmations puis coller le tx hash. La clé `ask_...` n’est
affichée qu’une fois. Utiliser `GET /v1/keys/me`, `POST /v1/keys/rotate` et
`POST /v1/keys/revoke` pour la gérer.

## Identité et mémoire

Envoyer la clé payée active comme `X-SaaS-Key`, séparément de la preuve de l’actor.

Les requêtes protégées exigent `X-Actor-ID`, `X-Actor-Public-Key` et
`X-Actor-Signature`. La clé privée reste dans le client. Écrire via
`/memory/api/memories` et rechercher via `/memory/api/search`.

## Équipes

Créer une équipe via `/teams/api/teams`, gérer les membres via
`/teams/api/teams/{team_id}/members` et envoyer `team_id` à chaque opération.
Le Gateway valide la membership, le Hub l’assertion courte et la signature.

`401` indique des credentials invalides, `403` un scope incorrect, `402` un
paiement requis et `429` une limite dépassée. Ne jamais envoyer de clé privée.

## 7. Trial

Demander le trial via `/v1/trials` : Personal dure 7 jours, Team 14 jours et
Expert Market 1 jour. Le Gateway émet une clé unique `ask_...` sans paiement et
la lie à un actor vérifié. L’accès expire automatiquement ; pour continuer,
effectuer le paiement exact en USDC sur Base. Voir [TRIAL.md](TRIAL.md).
