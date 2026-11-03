# Un hub sur une plateforme

[English](run-on-a-platform.md) · [Русский](run-on-a-platform.ru.md) · [Español](run-on-a-platform.es.md) · [Français](run-on-a-platform.fr.md) · [中文](run-on-a-platform.zh.md)

Railway, Render et Fly donnent à un hub un nom `https` public sans domaine à vous. Le dépôt
contient un fichier pour chacune (`railway.json`, `render.yaml`, `fly.toml`), qui construisent
tous `Dockerfile.standalone`. L'image se configure seule au premier démarrage (`serve --init` :
le fichier de réglages, un jeton d'administration, la `hub.ping@v1` gratuite et un exemple
payant), il n'y a donc rien à lancer avant le premier déploiement.

Trois règles valent sur toutes les plateformes :

1. **Un volume persistant sur `/app/data`.** Les clés de signature, la base et les réglages y
   vivent, et les clés sont l'identité du hub : un déploiement sans elles est un nouveau hub,
   que tout pair ayant épinglé l'ancienne clé refuse. Une plateforme sans volume dans son offre
   gratuite ne peut pas faire tourner un hub.
2. **`AIMARKET_HUB_URL` défini avant le premier démarrage**, à l'adresse publique fournie par la
   plateforme. Elle figure dans chaque document que le hub signe, et les autres hubs vous
   connaissent par elle.
3. **`AIMARKET_ADMIN_TOKEN` en secret de la plateforme**, pour que vous le connaissiez : il sert à
   approuver des pairs et à créditer des acheteurs. Sans lui, `--init` en génère un dans le volume.

## Railway

1. Nouveau projet → déployer depuis votre fork de `alexar76/aimarket-hub` ; `railway.json`
   choisit `Dockerfile.standalone` et la vérification de santé.
2. Service → Settings → Networking → Generate Domain, port cible `9083`.
3. Ajoutez un volume monté sur `/app/data`.
4. Variables : `AIMARKET_HUB_URL=https://<le domaine généré>`, `AIMARKET_HUB_NAME`,
   `AIMARKET_ADMIN_TOKEN`, `PORT=9083`. Déployez.

## Render

New → Blueprint → votre fork. `render.yaml` crée un service web avec un disque de 1 Go sur
`/app/data` et demande `AIMARKET_HUB_URL` (`https://<nom du service>.onrender.com`) et
`AIMARKET_HUB_NAME` ; il génère `AIMARKET_ADMIN_TOKEN`. Un disque exige un type d'instance payant.

## Fly.io

```bash
fly launch --no-deploy --copy-config --name <your-app>
fly volumes create hub_data --size 1
fly secrets set AIMARKET_ADMIN_TOKEN=$(openssl rand -base64 32)
fly deploy
```

Modifiez d'abord `app`, `AIMARKET_HUB_URL` (`https://<your-app>.fly.dev`) et `AIMARKET_HUB_NAME`
dans `fly.toml`. La machine reste allumée (`auto_stop_machines = "off"`) : un hub doit répondre
aux explorations et aux sondes d'admission à toute heure.

## Ensuite

`doctor` se lance de n'importe où, votre portable compris, contre l'adresse publique :

```bash
uvx --from "aimarket-hub[pqc]" aimarket doctor --url https://<votre hub>
```

Quand `doctor` dit `pass`, frappez — voir [Exploiter ce hub](operator-quickstart.fr.md#5-frapper-à-la-porte).
Pour publier votre propre API, ouvrez un shell sur la plateforme (`railway ssh`, Render Shell,
`fly ssh console`) et lancez-y `docker-entrypoint.sh add …` : la commande écrit dans la base du
hub sur le volume, sous l'utilisateur du hub, de sorte que les fichiers restent accessibles en
écriture au hub.

Ces fichiers suivent le format documenté de chaque plateforme ; l'image elle-même est testée sur
un volume appartenant à root, comme ceux que montent ces plateformes.
