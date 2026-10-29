# Recherche hebdomadaire — exemple synthétique

Analyse des définitions enregistrées et des vérifications de vos flux de travail.

| Dépendance | Résultat | Flux à vérifier |
|---|---|---|
| demo:research | Changements observés | 2 |
| demo:migration | Conditions d’observation modifiées | 1 |
| demo:offline | Données insuffisantes | 1 |

## demo:research

**Changements observés**

- Avant : 2026\-10\-26T09:00:00Z ; version du paquet 1\.0\.0 ; version du serveur 1\.0\.0 ; protocole 2025\-06\-18.
- Après : 2026\-10\-27T09:00:00Z ; version du paquet 1\.1\.0 ; version du serveur 1\.1\.0 ; protocole 2025\-06\-18.


### Lire les documents archivés

Nouvelle vérification nécessaire.

- [ ] legacy\_fetch: Vérifiez un remplacement ou épinglez le paquet précédent ; examinez le flux avant de l’exécuter\.

### Préparer la revue hebdomadaire des documents

Nouvelle vérification nécessaire.

- [ ] export\_brief: Vérifiez les confirmations, les permissions et les prix annoncés ; les annotations sont des déclarations du serveur\.
- [ ] search\_docs: Lisez les instructions modifiées ; rejouez une requête habituelle et vérifiez le choix de l’outil\.
- [ ] search\_docs: Vérifiez les entrées enregistrées, les champs requis et les types ; ajoutez un cas limite\.
- [ ] search\_docs: Rejouez le traitement du résultat : vérifiez les champs et types lus par le flux\.

### Changements des outils sélectionnés

**export\_brief: Modifié**

- destructiveHint: false → true. C’est une déclaration du serveur.
- readOnlyHint: true → false. C’est une déclaration du serveur.

**legacy\_fetch: Supprimé**


**search\_docs: Modifié**

- Nouveaux champs requis: workspace
- Changements de type: $/properties/limit, $/properties/workspace
- inputSchema: $\.&quot;properties&quot;\.&quot;limit&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;workspace&quot;\.&quot;type&quot;, $\.&quot;required&quot;\[1\]
- outputSchema: $\.&quot;properties&quot;\.&quot;items&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;results&quot;\.&quot;type&quot;
- Description supprimée: “using”
- Description ajoutée: “in”
- Description supprimée: “query\.”
- Description ajoutée: “selected workspace\. Include source links in the result\.”

Taille du JSON présenté au modèle en UTF-8 : liste complète 534 → 627 octets ; outils sélectionnés 534 → 451 octets.
Il ne s’agit ni de tokens ni d’économies réalisées.

## demo:migration

**Conditions d’observation modifiées**

- Avant : 2026\-10\-26T09:00:00Z ; version du paquet sans objet ; version du serveur 1 ; protocole 2025\-06\-18.
- Après : 2026\-10\-27T09:00:00Z ; version du paquet sans objet ; version du serveur 2 ; protocole 2026\-07\-28.

- Conditions modifiées : protocol ; les différences ne peuvent pas être attribuées uniquement à la mise à jour du paquet.

### Vérifier l’état du service après la migration MCP

Des observations comparables sont nécessaires.

- [ ] Vérifiez protocol, launcher et les conditions d’accès ; reprenez les deux instantanés dans le même contexte\.

### Changements des outils sélectionnés

Aucun changement détecté dans les définitions sélectionnées.

Taille du JSON présenté au modèle en UTF-8 : liste complète 94 → 94 octets ; outils sélectionnés 94 → 94 octets.
Il ne s’agit ni de tokens ni d’économies réalisées.

## demo:offline

**Données insuffisantes**

- Avant : 2026\-10\-26T09:00:00Z ; version du paquet sans objet ; version du serveur 1 ; protocole 2025\-06\-18.
- Après : 2026\-10\-27T09:00:00Z ; version du paquet sans objet ; version du serveur inconnue ; protocole inconnu.
Aucune paire de définitions obtenues avec succès. Les champs des outils n’ont pas été comparés.

- Limite: Aucune observation complète et réussie après la mise à jour\.

### Consulter l’état quotidien du service externe

Des observations comparables sont nécessaires.

- [ ] Vérifiez protocol, launcher et les conditions d’accès ; reprenez les deux instantanés dans le même contexte\.
- [ ] read\_status: Obtenez deux observations complètes et réussies dans des environnements comparables\.

### Changements des outils sélectionnés

**read\_status: Données insuffisantes**


## Limites de l’analyse

- Seules les définitions observées sont comparées, pas le comportement du serveur à l’exécution\.
- Un changement ne prouve pas une panne ; des définitions inchangées ne démontrent pas la sécurité\.
- Les flux sont liés aux outils explicitement sélectionnés, sans analyse sémantique\.
- La taille du JSON compact en UTF\-8 mesure des octets, pas des tokens, de l’argent ou des économies réalisées\.
- launch n’est représenté que par son empreinte ; les conditions de lancement ne sont pas exécutées et les secrets d’environnement ne sont pas affichés\.

[Données complètes, versions et empreintes SHA-256 des entrées](report.json).
