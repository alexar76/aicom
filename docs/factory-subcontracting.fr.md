# AICOM : achat de diagnostics externes

> 🌐 [English](factory-subcontracting.md) · [Русский](factory-subcontracting.ru.md) · [Español](factory-subcontracting.es.md) · [Français](factory-subcontracting.fr.md) · [中文](factory-subcontracting.zh.md)

AICOM développe ses produits avec ses propres agents. Elle peut désormais acheter un diagnostic limité via AIMarket avant une nouvelle correction interne. Le prestataire fournit des recommandations ; le développeur AICOM modifie le code et les contrôles QA existants décident de la suite.

La fonction est **désactivée par défaut**. Son installation ne déclenche aucun achat réel, approvisionnement de compte, enregistrement de prestataire ou envoi de code.

## Algorithme de décision

1. Avant une tâche de développement, sélectionner les anomalies QA high/critical qui désignent un fichier.
2. Associer chaque anomalie (fichier + titre) à la dernière tâche de développement terminée. Rejouer cette tâche ne compte pas une seconde fois. L'achat devient possible après trois observations : génération initiale et deux corrections internes terminées.
3. Respecter l'arrêt d'urgence, les blocages existants, le budget épuisé, l'absence de code produit et `external_diagnostics_allowed: false`. Les pauses opérateur et limites de correction restent applicables.
4. Préparer une demande contenant **un fichier autorisé**, l'anomalie et les critères d'acceptation. Son empreinte couvre le code et le contrat.
5. Vérifier le document well-known signé du Hub avec les clés épinglées par l'opérateur. Rechercher les capacités autorisées, exclure démonstrations, offres indisponibles et entrées incompatibles ; préférer le prix annoncé le plus bas.
6. Réserver atomiquement le montant dans les limites du produit et de la journée, en conservant une réserve de finition. Un seul achat au paiement inconnu est permis par produit et deux prestataires par anomalie. Un même prestataire n'est pas rappelé pour cette anomalie. Tout nouvel achat exige une nouvelle réparation interne terminée, même après un rapport rejeté.
7. Effectuer un appel unique, vérifier le reçu et valider le rapport. Un délai dépassé ou un paiement incertain conserve la réserve ; aucun nouvel appel payant automatique.
8. Transmettre le diagnostic accepté au développeur interne comme données tierces non fiables. Après une tâche de développement réussie, enregistrer la QA suivante. Le rapport ne change aucun état et ne supprime aucun contrôle.

Sans offre compatible, autorisation ou budget, les corrections internes continuent avec leurs limites existantes. Un diagnostic accepté n'est pas racheté pour la même anomalie. Après redémarrage, il peut être récupéré avant son utilisation interne si l'empreinte est inchangée.

## Configuration

Copier [l'exemple](../config/procurement.example.json) vers `<AIFACTORY_DATA_ROOT>/config/procurement.json`.

| Paramètre | Signification |
|---|---|
| `enabled` | `true` après configuration d'un prestataire testé |
| `hub_url` | Hub HTTPS ; redirections non suivies |
| `hub_public_key` | Clé Ed25519 base64 vérifiée et épinglée |
| `hub_pq_public_key` | Clé ML-DSA-65 épinglée pour un Hub hybride ; vide pour Ed25519 seul |
| `providers` | Jusqu'à 10 paires autorisées `product_id` / `capability_id` |
| `share_globs` | Chemins autorisés relatifs au code du produit |
| `per_call_usd` | Plafond par achat : $0.25 initialement |
| `per_product_usd` | Dépenses et réserves externes : $0.50 |
| `per_day_usd` | $2.00 par journée UTC pour le journal partagé |
| `completion_reserve_usd` | $0.50 conservé pour la finition et la QA internes |

Fournir un compte credits dédié et approvisionné via `AIFACTORY_PROCUREMENT_API_KEY`, avec solde et permissions configurés dans le Hub. Cette version ne crée ni ne signe de mandate ; un compte qui l'exige refusera ce client. Définir un `AIFACTORY_MAX_PIPELINE_COST_USD` positif : désactiver le plafond global n'autorise pas des achats illimités.

La configuration est relue pour chaque tâche éligible. Ne pas enregistrer la clé API dans JSON. Tous les processus de l'entreprise doivent partager le répertoire de données et le journal pour avoir un plafond quotidien commun. Des installations distinctes ont des plafonds distincts.

Les offres doivent être exécutées par le Hub configuré (`source_hub: local`), y compris les endpoints externes qu'il appelle. Les offres fédérées et les budgets de sous-traitance ultérieure ne sont pas pris en charge.

La recherche doit déclarer explicitement `credits_eligible: true`. Les vendeurs exigeant un paiement direct sur chaîne sont exclus. Un ancien Hub sans ce champ ne fournit aucun candidat éligible : déployer d'abord la mise à jour du Hub. Tester la compatibilité credits et le contrat de diagnostic du prestataire.

## Partage de code et contrat

Le prestataire doit implémenter **`aicom.diagnosis/1`**. Une offre nommée `code.review@v1` n'est pas automatiquement compatible ; la tester avant de l'autoriser.

Entrée : `contract`, `issue`, `fingerprint`, `finding`, `files`, `acceptance`. Un fichier UTF-8 de 16 000 octets maximum est envoyé. Extensions : py, ts, tsx, js, jsx, go, rs, java, cs, html, css. Les chemins cachés, répertoires de secrets, liens symboliques, sorties de périmètre et motifs courants d'identifiants sont refusés. Le dépôt complet, les identifiants, le cahier des charges et les journaux d'exécution ne sont pas envoyés.

`share_globs` utilise Python fnmatch : `*` peut couvrir un séparateur de chemin. Définir des périmètres étroits. La détection des secrets est heuristique ; l'opérateur doit approuver les sources partageables.

Les chemins QA relatifs au produit, préfixés par `code/<product_id>/` ou `data/code/<product_id>/`, ainsi que les chemins absolus dans son répertoire de code sont normalisés vers la même identité. Les chemins hors de ce répertoire sont refusés.

Le champ `result` du Hub doit suivre cette forme ; l'exemple cite `return 1 / x` :
```json
{
  "contract": "aicom.diagnosis/1",
  "issue": "COPY_FROM_REQUEST",
  "fingerprint": "COPY_FROM_REQUEST",
  "diagnosis": [{
    "file": "app/main.py",
    "line": 2,
    "evidence": "return 1 / x",
    "explanation": "Zero input divides by zero.",
    "suggested_check": "Test divide(0) against the required error contract."
  }]
}
```

Recopier les identifiants de la demande et fournir 1 à 5 observations. Chaque citation doit correspondre à un fragment non vide de la ligne indiquée d'un fichier partagé. Explication et vérification suggérée sont obligatoires, chacune limitée à 2 000 caractères. Une version de source modifiée est refusée. Aucune suggestion n'est exécutée comme commande shell.

L'acceptation valide la structure et les références au code, pas la vérité du diagnostic. Le développeur doit vérifier les conclusions ; tests et QA restent actifs. Le reçu signe les champs de facturation, pas le texte du diagnostic. Ed25519 et la couche ML-DSA-65 présente ou requise sont vérifiées avec les clés épinglées.

## Paiement et reprise

`state/procurement.sqlite3` conserve commandes, empreintes, rapports, réserves et résultats QA. L'exécution (`in_flight`, `accepted`, `rejected`, `unresolved`) est séparée du paiement (`unknown`, `paid`, `not_charged`).

Un rapport rejeté peut tout de même être payé. Ce parcours credits ne promet pas de remboursement Pay-on-Verified. Les erreurs HTTP, reçus absents ou invalides, déconnexions et interruptions laissent le paiement inconnu. De nouveaux achats du produit sont bloqués ; le travail interne peut continuer si le budget restant le permet.

Après vérification de la facturation dans le Hub :
```bash
.venv/bin/python scripts/procurement_orders.py list --product PRODUCT_ID
.venv/bin/python scripts/procurement_orders.py reconcile \
  --order PURCHASE_ID --charged-usd 0.10 \
  --evidence "Hub billing reference and reconciliation reason"
```

Les montants de `list` sont en micro-USD : 100 000 = $0.10. Pour une autre installation, placer `--data-root PATH` avant la sous-commande. Le rapprochement enregistre le débit observé et sa justification, libère la réserve et ne rappelle pas le prestataire ni ne fabrique un rapport accepté. Indiquer zéro uniquement après confirmation de l'absence de débit.

Le contrôle global additionne **coûts LLM observés + achats débités + réserves inconnues**. SQLite sérialise les achats concurrents. Les réserves des jours précédents consomment aussi le plafond courant. Un appel LLM déjà en cours peut dépasser l'estimation restante : ce n'est pas une préautorisation stricte de tous les tokens.

## Tests et limites

Les tests utilisent le véritable signataire du Hub et un transport HTTP simulé, sans paiement réel. Ils couvrent transmission au développeur, signatures, rapports périmés, chemins, politiques désactivées, concurrence, paiement ambigu, reprise, rapprochement et maintien des contrôles QA.

Le journal conserve la prochaine QA et le nombre d'anomalies restantes. Il n'attribue pas d'économies causales et n'apprend pas automatiquement le classement des prestataires. Rapprochement automatique, développement entièrement externalisé, fédération, sous-traitance ultérieure et tâches longues sont hors du périmètre initial.

Code : [contrat](../core/procurement_contract.py), [journal](../core/procurement_store.py), [orchestration](../orchestrator/procurement.py), [reçus](../core/procurement_receipt.py).

## Vérification par appels réels — 2026-10-11

Les [résultats conservés](evidence/factory-subcontracting-live-2026-10-11.json) couvrent de vrais appels HTTPS vers un Hub temporaire et un appel réel à `minimax/minimax-m3` via le compte OpenRouter configuré dans la fabrique. Le rapport lié au code a été accepté, les signatures Ed25519 et ML-DSA-65 vérifiées, le solde **de test** est passé de $0.50 à $0.40 et la répétition n'a effectué aucun appel réseau. L'appel accepté a déclaré un coût de $0.00033588. Aucun compte ni catalogue de production n'a été modifié ; cela ne prouve ni un achat en production ni la construction complète d'un produit.

Deux essais précédents ont révélé un délai dépassé et un rapport mal structuré. Le premier a conservé la réserve sans nouvelle tentative ; le second a été comptabilisé comme payé mais rejeté. La requête exige désormais explicitement un tableau de 1–5 constats. Le premier appel n'a pas retourné de données d'usage : le coût total du modèle reste non rapproché.

Le Hub public `modelmarket.dev` a répondu HTTP 200, mais sa recherche déployée ne comportait pas `credits_eligible` et aucun prestataire compatible n'a été trouvé. L'achat en production reste à vérifier après mise à jour du Hub et déploiement d'un prestataire compatible.

Reproduire avec [le script](../scripts/procurement_live_probe.py) :
```bash
.venv/bin/python scripts/procurement_live_probe.py \
  --ssh-host YOUR_FACTORY_SSH_ALIAS --container aicom-app-1 \
  --output /tmp/procurement-live-result.json
```
Chaque exécution peut facturer un appel réel ; l'estimation selon les tarifs du modèle doit rester au plus à $0.25. La clé reste dans le conteneur distant. Hub, clés TLS, catalogue et crédits de test sont temporaires.

## Activé en production — 2026-10-11

La fabrique achète `aicom.diagnose@v1` au service approuvé `aicom-diagnostics` via `https://modelmarket.dev`. Ce premier prestataire appartient à l’opérateur, fonctionne séparément et utilise `minimax/minimax-m3`. Le Hub vérifie sa signature Ed25519 liée à la requête ; la fabrique vérifie le reçu Ed25519 + ML-DSA-65 du Hub. Metis reste aux étapes architecture et méthodologie, distinctes du diagnostic des erreurs de code répétées.

Limites : 0,25 $ par appel, 0,50 $ par produit, 2 $ par jour UTC, réserve de 0,50 $ pour terminer le travail interne. Le plafond total reste de 40 $. Seuls `backend/app/*.py` et `frontend/src/*.tsx` peuvent être partagés. Le compte a reçu un crédit opérateur unique de 2 $, sans recharge automatique. L’achat réussi a coûté 0,10 $, laissant 1,90 $. Ce sont des crédits accordés par l’opérateur, pas un dépôt fiat ni le revenu d’un client indépendant.

Le test utilisait un défaut synthétique et un vrai rapport du modèle. La livraison signée a réutilisé le rapport enregistré lors du contrôle précédent de signature, sans nouvelle inférence. Répéter la tâche acceptée n’a produit aucun appel réseau. Cinq refus antérieurs ont été rapprochés sans débit. L’adaptateur accepte un bloc JSON Markdown complet et la variante `suggest_check`, tout en validant strictement les citations et le contrat. Les 45 tests ciblés passent ; cela ne prouve pas la réparation complète d’un produit réel.

[Preuves](evidence/procurement-production-2026-10-11/README.md). Pour arrêter les achats : `enabled: false` dans `data/config/procurement.json`, sans redémarrage. Sources et retour arrière : `/root/procurement-release-20261011/`. Aucun push GitHub.
