# Gitea wiki sources

**Language:** English by default. Optional companions: [`FAQ-RU.md`](FAQ-RU.md), [`FAQ-ES.md`](FAQ-ES.md), policy in [`Languages.md`](Languages.md).

Markdown in this folder is the **source of truth** for the [Gitea wiki](http://5.129.212.122/Superowner/aicom/wiki/Home).

## Update wiki

```bash
./scripts/push-gitea-wiki.sh
```

Or set `GITEA_WIKI_URL=http://USER:TOKEN@host/Superowner/aicom.wiki.git`.

## Pages

| File | Wiki URL slug |
|------|----------------|
| `Home.md` | Home |
| `_Sidebar.md` | (navigation) |
| `Quick-Start.md` | Quick-Start |
| … | Same as filename without `.md` |

Deep documentation remains in repository [`docs/`](../docs/README.md) — wiki pages summarize and link there.
