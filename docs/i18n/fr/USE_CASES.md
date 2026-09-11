# Cas d’usage

Attested Memory s’adresse aux situations où **oublier coûte cher** et où
**la confiance aveugle coûte encore plus**. Ces scénarios montrent quand une
note, un log de chat ou un vector store ne suffisent pas — et quand
identité, truth state, provenance et settlement exact transforment le
contexte en quelque chose sur quoi agir.

Les noms de routes, headers et termes de paiement restent exacts dans toutes
les langues. Seul le texte explicatif est localisé.

## Second cerveau du fondateur qui survit au context rot

**Qui.** Un fondateur, chercheur ou opérateur qui passe chaque jour d’un outil,
d’un agent et d’un appareil à l’autre.

**Problème.** Les décisions vivent dans les chats, les dumps Notion et les
prompts à moitié écrits. Six semaines plus tard, personne ne peut dire
*pourquoi* un choix a été fait, quelles sources étaient fiables, ni quel
agent a inventé un résumé commode.

**Comment ça marche.**

1. Rédigez une Memory Unit avec la décision, le raisonnement, les tags et
   `source_refs`.
2. Signez en tant qu’actor (`X-Actor-ID` / public key / signature). La clé
   privée reste dans votre client.
3. Plus tard, cherchez via `/memory/api/search` et inspectez truth +
   provenance avant de réutiliser la mémoire dans un nouveau plan ou un run
   d’agent.

**Pourquoi l’attestation compte.** Vous ne récupérez pas « un paragraphe
similaire ». Vous récupérez une affirmation portable avec un actor et une
lignée.

**Démarrer.** [Personal Memory](/memory) · [Guide utilisateur](USER_GUIDE.md) ·
trial sur [/billing](/billing).

## War-room d’incident qui conserve la piste de décision

**Qui.** Ingénieurs on-call, SRE, security responders.

**Problème.** Le canal d’outage avance plus vite que le wiki. Le postmortem
est écrit de mémoire, la propriété de chaque appel est floue, et la semaine
suivante un agent rejoue une mitigation rejetée parce que rien n’a été signé
dans un namespace partagé.

**Comment ça marche.**

1. Ouvrez un workspace Team Memory OS et créez un team namespace.
2. Les membres écrivent notes d’incident, options rejetées et actions finales
   avec signatures d’actor.
3. Le SaaS gateway vérifie le membership ; le Hub n’accepte que les
   enregistrements `team:<id>` correspondants. Les requêtes ne fuient pas
   vers une autre équipe.

**Pourquoi l’attestation compte.** Les handoffs deviennent auditables. Le
offboarding révoque la clé ; les team assertions à courte durée expirent sans
chasse forensique dans les chats.

**Démarrer.** [Team Memory OS](/teams) ·
[Guide utilisateur § Team](USER_GUIDE.md).

## Savoir d’expert qui se vend sans fuite du corpus

**Qui.** Experts de domaine, research shops, boutiques d’advisory.

**Problème.** Publier le corpus entier gratuitement détruit le business.
Publier seulement un teaser détruit la confiance. L’acheteur a besoin de voir
la provenance avant de payer — le vendeur a besoin d’un accès borné dans le
temps, pas de copies perpétuelles par défaut.

**Comment ça marche.**

1. Publiez une Memory Unit avec des champs de summary publics et une
   visibility payante pour le corps.
2. L’acheteur parcourt le catalogue, inspecte truth/provenance, puis ouvre
   une invoice exacte Base USDC.
3. KOVA vérifie le transfert ; le Gateway émet un entitlement scopé. L’accès
   expire avec le plan.

**Pourquoi l’attestation compte.** Le discovery est honnête. Le settlement est
exact. L’entitlement est un scope cryptographique du produit, pas un lien PDF
« sur l’honneur ».

**Démarrer.** [Expert Memory Market](/market) · [Paiements](/billing).

## Handoff multi-agents avec continuité cryptographique

**Qui.** Opérateurs d’agents, équipes d’orchestration, workflows autonomes.

**Problème.** L’agent A dépose un résumé de chat pour l’agent B. Le résumé
n’est pas signé, partiellement halluciné et sans sources. L’échec ressemble à
« le modèle suivant était bête » alors que le vrai bug était la perte
silencieuse de provenance.

**Comment ça marche.**

1. L’agent A écrit une Memory Unit de handoff signée : contraintes, outils
   utilisés, sources, risques ouverts.
2. L’agent B la récupère avec la même politique actor/team et vérifie la
   provenance avant de continuer.
3. Le truth state voyage avec l’unit — les contradictions restent visibles au
   lieu d’être lissées en prose confiante.

**Pourquoi l’attestation compte.** La continuité est une propriété de
l’enregistrement, pas de celui qui a laissé l’onglet ouvert.

**Démarrer.** [Developers](/developers) ·
[Guide utilisateur § Actor identity](USER_GUIDE.md).

## Due diligence et recherche avec des claims liés aux sources

**Qui.** Analystes, counsel, équipes investment et vendor-review.

**Problème.** Les notes de diligence citent « le deck », « le call » et
« quelque chose de Slack ». Quand un claim est contesté, la chaîne de
custodie est un sentiment.

**Comment ça marche.**

1. Capturez chaque claim matériel comme Memory Unit avec des `source_refs`
   explicites.
2. Attachez ou mettez à jour le truth state à mesure que l’evidence arrive
   (confirmed, disputed, insufficient).
3. Reconstruisez le dossier plus tard à partir des provenance receipts, pas
   d’un folklore reconstruit.

**Pourquoi l’attestation compte.** Les reviewers débattent du claim et de son
evidence, pas de qui avait les notes « les plus récentes ».

**Démarrer.** Produit Personal ou Team · [Glossaire](GLOSSARY.md).

## Accès payant automatisé quand le navigateur a disparu

**Qui.** Acheteurs qui paient depuis une wallet app, scripts qui settlent des
invoices, et opérateurs qui ne peuvent pas garder un onglet de checkout.

**Problème.** Le checkout classique meurt à la fermeture de l’onglet. Les flux
manuels « colle le tx hash » génèrent des tickets support et des paiements
partiels ambigus.

**Comment ça marche.**

1. `POST /v1/billing/orders` avec un `Idempotency-Key` unique, un plan et un
   payer.
2. Envoyez le montant exact de USDC canonique sur Base au destinataire de
   l’invoice.
3. KOVA fait correspondre token, payer, recipient, amount et profondeur de
   confirmation.
4. Le Gateway active automatiquement la clé produit. Un poll de
   `GET /v1/billing/orders/{id}` avec le checkout token renvoie la clé une
   fois confirmed — même si la session navigateur d’origine a disparu.

**Pourquoi l’attestation compte.** Mouvement d’argent et émission
d’entitlement sont liés par l’identité exacte de l’invoice, pas par une
capture d’écran de wallet.

**Démarrer.** [Billing](/billing) ·
[Guide utilisateur § Buy access](USER_GUIDE.md).

## Offboarding sûr sans orpheliner l’institution

**Qui.** Team leads, security, IT.

**Problème.** Un opérateur qui part a encore des exports de chat et des notes
personnelles contenant les vrais runbooks. Révoquer Slack ne révoque pas la
mémoire institutionnelle qui n’a jamais vécu dans un système contrôlé.

**Comment ça marche.**

1. Gardez le savoir opérationnel dans Team Memory OS sous un namespace
   explicite.
2. Faites une rotation ou révoquez immédiatement la clé SaaS au départ.
3. Les team assertions expirent en minutes ; la politique du Hub exige
   toujours des actor proofs pour les reads et writes protégés.

**Pourquoi l’attestation compte.** L’accès se termine comme un événement du
control plane, pas comme l’espoir que quelqu’un a vidé un dossier Drive.

**Démarrer.** [Team Memory OS](/teams).

## À quoi cela ne sert pas

- Une archive générale de chats sans discipline d’identité ni de sources.
- Un endroit pour stocker des private keys de wallet, seed phrases ou
  credentials bruts.
- Des dumps « partager avec le monde » sans policy de visibility.
- Des paiements crypto arrondis ou approximatifs — le montant exact de USDC
  *est* l’invoice.

Si votre workflow tolère la perte silencieuse d’authorship, de sources et de
finalité de paiement, un carnet suffit. Sinon, commencez par la surface
produit correspondante ci-dessus et gardez les contrats du Hub exacts.
