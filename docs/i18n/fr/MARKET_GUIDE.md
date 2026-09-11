# Guide d’implémentation d’Expert Memory Market

Ce guide couvre les parcours production réels pour acheteurs, éditeurs et
intégrateurs d’agents. Découverte publique, livraison payante, comptabilité
éditeur et preuve sont volontairement des contrats distincts.

## Choisir le parcours d’accès avant l’intégration

- Utilisez le trial d’un jour pour valider UX et API sans transaction wallet.
- Utilisez Expert Pass pour sept jours d’exploration avec une clé `ask_` ciblée.
- Utilisez le paiement à la lecture lorsque chaque Memory Unit doit rémunérer son éditeur.
- Ne mélangez pas pass et revenu éditeur : le pass finance la vitrine, le capture Meter finance la répartition.

## Inspecter avant d’acheter

`GET /market/v1/listings?q=<sujet>` ne demande aucune clé. Chaque résultat
publie résumé, `rank_score`, `rank_reasons`, Truth, Provenance, prix et éditeur.
`GET /market/v1/listings/<memory_id>` ne renvoie jamais le corps payant.

Refusez les listings sans preuves publiques suffisantes. Un score élevé n’est
pas une consigne de confiance. Un claim rejeté reste sous un non vérifié et la
popularité ne compte pas dans le classement.

## Commencer avec le trial gratuit

Ouvrez `/` avec `trial=expert-market` ou utilisez l’assistant. Le navigateur
crée l’Actor Identity et conserve la clé privée localement. Gateway émet un
trial par actor et produit. Placez `ask_` dans un secret vault, jamais dans URL,
logs ou analytics client.

Le trial valide l’usage, sans paiement, répartition ni entitlement permanent.

## Acheter un pass ou une lecture livrée

Pour Expert Pass, ouvrez `/billing?plan=expert.pass.7d`, créez la facture exacte,
envoyez le canonical USDC sur Base et attendez la finality KOVA. Gateway émet la
clé pour sept jours ; le checkout la récupère pendant 48 heures.

Pour la lecture unitaire, créez et créditez un compte Attested Meter, gardez
`amk_` côté serveur puis appelez `POST /market/v1/read` avec `x-meter-key` et
`{"memory_id":"<id>"}`. Meter réserve le prix et capture seulement après
livraison ; échec ou refus libère la réservation.

## Publier et fixer un prix

- Créez une Memory Unit avec titre précis, résumé utile, tags et `source_refs`.
- Ajoutez les preuves Truth et Provenance disponibles avant la mise en vente.
- Inscrivez-vous via `POST https://meter.attestedmemory.net/v1/publishers` avec identité signée et adresse Base.
- Gardez la clé éditeur secrète et tarifez seulement votre `expert.read:<memory_id>` via `/v1/publishers/me/prices`.
- Vérifiez le listing public avant d’y envoyer des acheteurs.

La répartition standard est 70% éditeur / 30% plateforme ; Publisher Pro passe
à 85% / 15%. Au-dessus du minimum, l’opérateur émet `attested.payout/v1` signé
et enregistre le hash.

## Intégrer un agent autonome

- Séparez découverte et achat ; autorisez la dépense après examen des metadata.
- Définissez prix maximum, éditeurs, Truth states et politique de sources.
- Gardez `ask_` et `amk_` dans les secrets serveur et retirez-les des traces.
- Lisez `401` comme credential, `402` comme accès/solde, `403` comme scope et `429` comme backoff.
- Conservez listing ID, rank reasons, charge ID et provenance receipt avec le résultat.
- Rendez les factures idempotentes ; ne rejouez jamais un transfert avec un montant inventé.

## Déployer dans une équipe

- Choisissez une première catégorie et la décision qu’elle améliore.
- Préparez 10–20 listings forts avant d’inviter des acheteurs.
- Fixez le minimum de résumé public et de sources.
- Testez succès, memory inconnue, solde insuffisant, panne upstream et révocation.
- Mesurez discovery-to-read, refus, capture/release, accrual et backlog payout.

## Respecter les frontières de confiance et d’argent

Memory Market classe et sert la mémoire autorisée. Attested Meter gère réserve,
capture, comptabilité et payouts. Attested Prove rend les reçus vérifiables sans
clé API. KOVA vérifie le règlement exact par service-to-service authentifié et
reste disponible via fédération.

Aucun composant ne demande seed phrase ou clé privée. Les USDC vont directement
au destinataire et les payouts s’exécutent séparément. Voir
[KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md) et [MARKET_USE_CASES.md](MARKET_USE_CASES.md).
