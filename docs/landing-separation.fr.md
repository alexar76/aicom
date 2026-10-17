# Fabrique, catalogue et écosystème : trois adresses

[EN](landing-separation.md) · [RU](landing-separation.ru.md) · [ES](landing-separation.es.md) · [FR](landing-separation.fr.md) · [中文](landing-separation.zh.md)

- `https://magic-ai-factory.com/` : fabrique opérationnelle, générateur, catalogue et administration.
- `https://modeldev.modelmarket.dev/` : nouvelle page de présentation de la fabrique.
- `https://ecosystem.modelmarket.dev/` : atlas canonique de l’économie des machines.

Le bouton principal ouvre la fabrique réelle. Les produits pointent vers `/#products` ; générateur, agents, documentation et conditions ouvrent également l’application. L’atlas présente la fabrique via sa page marketing et ses cartes ouvrent les services. Les liens de l’écosystème utilisent son propre domaine.

L’accueil opérationnel a été restauré. Les achats de services restent activés : ce transfert ne modifie ni backend, ni compte, ni journal, ni budgets. Voir [le guide](factory-subcontracting.fr.md).

`app/HomePage.tsx` conserve la vitrine ; `components/factory/FactoryLanding.tsx` contient la présentation. Seul le frontend séparé compilé et lancé avec `AICOM_SITE_ROLE=factory-landing` affiche celle-ci. Il utilise `NEXT_PUBLIC_SITE_URL=https://modeldev.modelmarket.dev`, cinq routes (`/`, `/ru/`, `/es/`, `/fr/`, `/zh/`), ses liens canoniques et alternatives linguistiques, sans PWA ni widget de marché de l’application. Une compilation ordinaire conserve la fabrique.

L’atlas est généré depuis `scripts/github-io/` ; canonical, sitemap et métadonnées utilisent `ecosystem.modelmarket.dev`. `ATLAS_SITE_URL` permet de définir un autre domaine explicitement. Aucun push GitHub : l’ancienne redirection publiée y reste jusqu’à une publication autorisée séparément.

Les deux modèles tournent entièrement, répondent au glissement souris/doigt et aux flèches, sans bouton pause. La réduction des mouvements est respectée. Ce sont des illustrations, pas de la télémétrie. Les sections encyclopedia, school, guides, learn et oracles de modeldev sont conservées.

Production : application sur 9080 ; frontend modeldev sur 9088, conteneur `aicom-frontend-modeldev-20261011`, image `ai-factory-frontend:modeldev-final-20261011`. Atlas : `/var/www/ecosystem.modelmarket.dev` → `/var/www/ecosystem-atlas-20261011`. Sources et sauvegardes : `/root/domain-split-20261011/` ; `rollback-modeldev.sh` restaure l’ancien vhost sans arrêter la fabrique ni les achats. Certbot réutilise le compte existant, webroot, renouvellement automatique et hook nginx ; attendre la propagation DNS avant émission.

Vérifier langues, canonical, navigation, WebGL, sections conservées et API. Exécuter typecheck, build et `python3 scripts/github-io/validate.py`. [Résultats](evidence/domain-split-2026-10-11/README.md).
