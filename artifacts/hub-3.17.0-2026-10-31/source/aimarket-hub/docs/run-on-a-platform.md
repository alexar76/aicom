# Run a hub on a platform

[English](run-on-a-platform.md) · [Русский](run-on-a-platform.ru.md) · [Español](run-on-a-platform.es.md) · [Français](run-on-a-platform.fr.md) · [中文](run-on-a-platform.zh.md)

Railway, Render and Fly give a hub a public `https` name without a domain of your own. The
repository carries a config file for each (`railway.json`, `render.yaml`, `fly.toml`), all
building `Dockerfile.standalone`. The image sets itself up on its first start (`serve --init`:
the settings file, an admin token, the free `hub.ping@v1` and a priced sample), so there is
nothing to run before the first deploy.

Three rules hold on every platform:

1. **A persistent volume at `/app/data`.** The signing keys, the database and the settings
   file live there, and the keys are the hub's identity: a deploy without them is a new hub,
   and every peer that pinned the old key refuses it. A platform that offers no volume on its
   free tier cannot run a hub there.
2. **`AIMARKET_HUB_URL` set before the first start**, to the public address the platform gives
   you. It is inside every document the hub signs, and other hubs know you by it.
3. **`AIMARKET_ADMIN_TOKEN` as a platform secret**, so you know it: it approves peers and tops
   up buyers. Without it `--init` generates one inside the volume.

## Railway

1. New project → deploy from your fork of `alexar76/aimarket-hub`; `railway.json` selects
   `Dockerfile.standalone` and the health check.
2. Service → Settings → Networking → Generate Domain, target port `9083`.
3. Add a volume mounted at `/app/data`.
4. Variables: `AIMARKET_HUB_URL=https://<the generated domain>`, `AIMARKET_HUB_NAME`,
   `AIMARKET_ADMIN_TOKEN`, `PORT=9083`. Deploy.

## Render

New → Blueprint → your fork. `render.yaml` creates a web service with a 1 GB disk at
`/app/data` and asks for `AIMARKET_HUB_URL` (`https://<service name>.onrender.com`) and
`AIMARKET_HUB_NAME`; it generates `AIMARKET_ADMIN_TOKEN`. A disk needs a paid instance type.

## Fly.io

```bash
fly launch --no-deploy --copy-config --name <your-app>
fly volumes create hub_data --size 1
fly secrets set AIMARKET_ADMIN_TOKEN=$(openssl rand -base64 32)
fly deploy
```

Edit `app`, `AIMARKET_HUB_URL` (`https://<your-app>.fly.dev`) and `AIMARKET_HUB_NAME` in
`fly.toml` first. The machine stays on (`auto_stop_machines = "off"`): a hub has to answer
crawls and admission probes at any hour.

## Then

`doctor` runs from anywhere, your laptop included, against the public address:

```bash
uvx --from "aimarket-hub[pqc]" aimarket doctor --url https://<your hub>
```

When `doctor` says `pass`, knock — see [Run your own hub](operator-quickstart.md#5-the-knock).
To list your own API, open a shell on the platform (`railway ssh`, Render Shell,
`fly ssh console`) and run `docker-entrypoint.sh add …` there: it writes the hub's own
database on the volume, as the hub's own user, so the files stay writable by the hub.

These files follow each platform's documented format; the image itself is tested on a
root-owned volume like the ones these platforms mount.
