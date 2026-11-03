# Admission fédérée — essai sandbox, puis index automatique

> **English:** [federation-admission.md](./federation-admission.md) · **Русский:** [federation-admission.ru.md](./federation-admission.ru.md) · **Español:** [federation-admission.es.md](./federation-admission.es.md) · **中文:** [federation-admission.zh.md](./federation-admission.zh.md)
>
> Code : [`federation_assay.py`](../aimarket_hub/federation_assay.py) · [`api.py`](../aimarket_hub/api.py) · [`crawler.py`](../aimarket_hub/crawler.py) · [`config.py`](../aimarket_hub/config.py)
>
> Chemin d’adhésion : [`docs/join-the-federation.fr.md`](https://github.com/alexar76/aicom/blob/main/docs/join-the-federation.fr.md)

---

## Pourquoi

Un knock (`POST /federation/announce` ou `X-AIMarket-Crawler` entrant) est une
**observation**. Il ne doit jamais indexer un catalogue : ce serait de l’injection de
manifeste. Avant, la seule sortie de quarantaine était un humain à `/operator` cliquant
Approve pour chaque nouveau hub.

L’opérateur ne restera pas sur cette file. L’admission après quarantaine est donc
**automatique**, mais elle note **ce qui a tourné dans le sandbox**, pas le texte du
`.well-known`.

Analogue usine (on n’importe pas l’usine dans le hub) :

| Usine | Hub fédéré |
|---------|----------------|
| `product_automated_verify` — noter tests/artefacts, pas la vitrine | `analyze_sandbox_output` — safety gate + schema + pas d’IP privées |
| `docs/sandbox-trust-model.md` — isolation douce, pas un hyperviseur | POST HTTP borné vers *leur* invoke public (on n’exécute pas leur code ici) |
| `agents/surrogate_reviewer.py` — JSON approve/block | `AIMARKET_FEDERATION_JUDGE_URL` optionnel — **veto seulement**, evidence sans `name`/`description` |

Un LLM à qui l’on donne `name` / `description` tamponne le marketing fluide. Cette voie est fermée.

## Pipeline

```text
knock → pending (rien d’indexé)
     → contrôles durs (SSRF / schema / Ed25519 / same-origin)
     → POST sandbox de jusqu’à 3 capabilities publiques gratuites (le premier reçu signé gagne)
     → rien de gratuit ? on frappe à la payante la moins chère et on lit son 402 (sans payer)
     → analyser le payload vivant
     → veto LLM optionnel sur l’évidence (pas de brochure)
     → pass + AUTO_ADMIT=1 → trusted + crawl
     → fail / review → restent pending (bureau opérateur)
```

Déclenchement : tâche de fond après announce sans token ; fin de chaque cycle de crawl
(jusqu’à 3 pending) ; admin `POST /ai-market/v2/federation/assay`.

## Verdicts

| Verdict | Sens | Auto-admission |
|---------|------|----------------|
| `pass` | Durs + reçu signé + analyse non false + juge non false | oui si `AIMARKET_FEDERATION_AUTO_ADMIT=1` (défaut) |
| `review` | Rien d’offert publiquement, un 402 sans instructions de paiement, un prix qui contredit le catalogue, une capability payante servie sans paiement, analyse fail ou juge `block` | non |
| `fail` | SSRF, schema, mauvaise signature, clé différente | non |

Pas de `AIMARKET_FEDERATION_JUDGE_KEY` / `OPENROUTER_API_KEY` → le juge n’est pas
consulté et **l’auto-admission ne tourne pas**. L’opérateur Approuve à `/operator`.
En prod le modèle est MiniMax (`minimax/minimax-m3`) via OpenRouter, le même jeton
que le reste de la flotte.

## Environnement

| Variable | Default | Effet |
|----------|---------|--------|
| `AIMARKET_FEDERATION_ASSAY` | `1` | Interrupteur maître |
| `AIMARKET_FEDERATION_ASSAY_SANDBOX` | `1` | Sonder jusqu’à 3 capabilities publiques gratuites |
| `AIMARKET_FEDERATION_AUTO_ADMIT` | `1` | `pass` → `trusted` + crawl. Alias : `AIMARKET_FEDERATION_ASSAY_AUTO_TRUST` |
| `AIMARKET_FEDERATION_JUDGE_URL` | vide | POST chat compatible OpenAI |
| `AIMARKET_FEDERATION_JUDGE_REQUIRED` | `0` | Une erreur du juge bloque l’admission |
| `AIMARKET_FEDERATION_ASSAY_REQUIRE` | `0` | Approve humain refuse sans dernier `pass` |
| `AIMARKET_FEDERATION_ASSAY_LLM` | ignoré | Pas un juge de brochure |

## Bureau opérateur

`/operator` est la voie d’**exception** : hubs payants-only, vetos, dismiss. Ce n’est pas
la file d’admission en régime de croisière.

## Limites d’isolation

Le hub n’exécute pas le code du pair dans un venv local ni gVisor. Il POST vers leur invoke
public avec un plafond d’octets (`262_144`) appliqué **pendant le streaming**. Isolation
**douce**, comme le preview usine. Les gardes SSRF refusent toujours les cibles privées /
link-local.

La destination est choisie par [`federation_transport`](../aimarket_hub/federation_transport.py),
la règle qu’utilisent déjà les invokes routés : un pair qui se déclare hub (`hub_version`, ou
`v2` dans `protocol_versions`) est sondé sur son `/ai-market/v2/invoke`, car le `mcp_endpoint`
qu’il annonce parle MCP JSON-RPC. Un service de capabilities simple garde son endpoint annoncé.
