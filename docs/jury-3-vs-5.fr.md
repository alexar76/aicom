# Jury de trois ou de cinq — mesuré

> 🌐 [English](jury-3-vs-5.md) · [Русский](jury-3-vs-5.ru.md) · [Español](jury-3-vs-5.es.md) · **Français** · [中文](jury-3-vs-5.zh.md)

Les mêmes 24 contrôles (12 tâches × une réponse honnête et une réponse subtilement fausse :
factorisation, tri, une somme, miles → km, jours entre deux dates, champs JSON obligatoires,
compter les voyelles, inverser une chaîne, primalité, une traduction, une capitale) sont passés une
fois par le jury Metis à cinq sièges le 2026-10-03. Les jurys plus petits sont calculés à partir des
mêmes votes individuels avec la règle du jury lui-même (majorité stricte de tout le jury, abstention
= pas de voix, score = accord × confiance médiane, seuil 0,7) : seule la composition change. Script :
[`metis/bench/jury_3v5.py`](https://github.com/alexar76/metis/blob/main/bench/jury_3v5.py) ; votes bruts :
[`metis/bench/results/2026-10-03-jury-3v5.json`](https://github.com/alexar76/metis/blob/main/bench/results/2026-10-03-jury-3v5.json).

| Composition | Décisions justes | Indéterminé | Décisions fausses | Attente, médiane / max (s) |
|---|---|---|---|---|
| 3 sièges, une lignée (DeepSeek, MiniMax, GLM) | 20/24 | 4 | 0 | 7.1 / 52.4 |
| 3 sièges, trois lignées (DeepSeek, Claude, Mistral) | 16/24 | 8 | 0 | 3.7 / 29.2 |
| 5 sièges (tous) | **21/24** | **3** | **0** | 7.1 / 52.4 |

| Juré | Votes faux sur 24 |
|---|---|
| Claude Sonnet 5.5 (Anthropic) | 0 |
| DeepSeek V4 Pro | 1 |
| GLM-5.3 (Zhipu) | 1 |
| MiniMax M3 | 2 |
| Mistral Medium 3.5 | 6 |

**Ce que cela montre**

- **Aucune composition n'a pris de décision fausse.** Le désaccord laisse le verdict indéterminé
  (l'acheteur est remboursé, le vendeur n'est pas mis en cause) ; il ne l'inverse jamais.
- **Cinq sièges décident le plus souvent** (21/24) : un vote faux ne bloque plus le verdict.
- **La diversité n'aide que si chaque juré est solide.** Le trio à trois lignées a fait le moins
  bien (16/24) parce que Mistral Medium 3.5 a voté faux 6 fois — surtout en acceptant des réponses
  fausses (une somme décalée d'un, un facteur faux, un mauvais compte de voyelles, « 97 n'est pas
  premier »). Dans un jury de cinq, les autres le mettent en minorité ; dans un jury de trois, il
  bloque chaque décision qu'il conteste.
- Le juré le plus lent fixe l'attente : GLM-5.3 a mis jusqu'à 52 s sur une factorisation difficile ;
  Claude et Mistral jamais plus de 9 s.

**Réserves.** 24 contrôles, une exécution, tâches vérifiables uniquement ; une tâche (champs JSON)
est discutable — sa réponse honnête invente une adresse e-mail et deux jurés ont objecté. Ces chiffres
sont indicatifs, pas un classement.

**Prochaine étape.** Remplacer le siège Mistral Medium par un modèle plus solide d'une autre lignée
(par exemple Mistral Large ou Gemini) et relancer les mêmes 24 contrôles : le script en fait une
comparaison de deux minutes.

## Remplacement du siège faible (le même jour)

| Candidat au cinquième siège | Votes faux | Abstentions | 5 sièges : justes | Verdict |
|---|---|---|---|---|
| Mistral Medium 3.5 | 6 / 24 | 0 | 21/24 | faible : acceptait des réponses fausses |
| Mistral Large 2512 | 1 / 2 répondus | 22 (`rate_limit` chez le fournisseur) | 20/24 | indisponible : un juré qui ne peut pas répondre s'abstient |
| **Gemini 3.8 Flash** | **1 / 24** | **0** | **22/24** | **conservé** (le trio à trois lignées DeepSeek + Claude + Gemini fait aussi 22/24) |

Chaque candidat a passé les mêmes 24 contrôles avec de nouveaux identifiants d'audit ; les votes bruts sont dans `metis/bench/results/`. Deux leçons : **mesurez un juré avant de lui faire confiance** (un modèle au nom prestigieux peut être la voix la plus faible) et **la disponibilité fait partie de la qualité** — un juré limité en débit s'abstient à chaque minute chargée. Avec ce changement, le jury a perdu sa lignée européenne : il couvre désormais des laboratoires chinois (DeepSeek, MiniMax, GLM) et américains (Anthropic, Google). Entre deux exécutions, le même trio a bougé d'une décision (20 → 21/24) : sur 24 contrôles, un écart d'une unité est du bruit.

## Nouveau test : Mistral avec le raisonnement activé

Le premier verdict sur Mistral Medium 3.5 était suspect : il répondait en une seconde quand les
autres réfléchissaient 3 à 50 s ; il a pu perdre à cause du *mode* et non du modèle. Les jurés
Metis ont reçu `extra_body` (fusionné dans chaque requête ; il ne peut remplacer ni le modèle ni
les messages) et Mistral a été relancé comme sixième siège avec `reasoning: {effort: medium}`
d'OpenRouter, puis `{effort: high}`.

| Mistral Medium 3.5 | Votes faux | Réponse médiane | Jetons de sortie |
|---|---|---|---|
| sans raisonnement | 6 / 24 | 1,1 s | — |
| `reasoning: medium` | 7 / 24 | 1,2 s | ~105 |
| `reasoning: high` | 6 / 24 | 1,1 s | ~100 |

L'interrupteur fonctionne — sur une question courte posée directement, le même modèle a consacré
273 à 2143 jetons au raisonnement — mais dans le jury, où la réponse doit être un seul verdict JSON
strict, il réfléchit à peine même en `high` et continue d'accepter des réponses fausses. Un juré qui
ne recalcule pas est un juré faible pour les calculs, quelle que soit sa réputation. **Décision :
Gemini 3.8 Flash garde le cinquième siège ; Mistral sort.**

**Correction des tableaux ci-dessus.** La tâche « combien de jours y a-t-il du 2026-01-01 au
2026-03-14 ? » était ambiguë : en comptant les deux bornes on obtient 73, la réponse « fausse », et
cinq jurés l'ont acceptée. Elle est désormais posée ainsi : « combien de jours après le 2026-01-01
tombe le 2026-03-14 ? ». Sans la paire d'origine, aucune composition n'a pris de décision fausse dans
aucune exécution. Sur le jeu corrigé, la composition finale — DeepSeek, MiniMax, GLM, Claude, Gemini —
décide **23 sur 24, aucune fausse** ; le trio DeepSeek + Claude + Gemini décide 22 sur 24 avec
l'attente la plus courte (médiane 5,4 s).
