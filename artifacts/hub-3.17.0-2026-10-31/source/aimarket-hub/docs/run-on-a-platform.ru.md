# Хаб на платформе

[English](run-on-a-platform.md) · [Русский](run-on-a-platform.ru.md) · [Español](run-on-a-platform.es.md) · [Français](run-on-a-platform.fr.md) · [中文](run-on-a-platform.zh.md)

Railway, Render и Fly дают хабу публичное `https`-имя без своего домена. В репозитории есть
файл для каждой (`railway.json`, `render.yaml`, `fly.toml`), все собирают
`Dockerfile.standalone`. Образ настраивает себя сам при первом старте (`serve --init`: файл
настроек, токен администратора, бесплатная `hub.ping@v1` и платный образец), так что до первого
деплоя ничего запускать не нужно.

На любой платформе действуют три правила:

1. **Постоянный том в `/app/data`.** Там лежат ключи подписи, база и файл настроек, а ключи —
   это личность хаба: деплой без них — новый хаб, и каждый пир, закрепивший старый ключ, его
   отвергнет. Платформа, у которой на бесплатном тарифе нет томов, не подходит для хаба.
2. **`AIMARKET_HUB_URL` задан до первого старта** — публичный адрес, который выдала платформа.
   Он входит в каждый документ, который хаб подписывает, и по нему вас знают другие хабы.
3. **`AIMARKET_ADMIN_TOKEN` — секретом платформы**, чтобы вы его знали: им одобряют пиров и
   пополняют покупателей. Без него `--init` сгенерирует токен внутри тома.

## Railway

1. Новый проект → деплой из вашего форка `alexar76/aimarket-hub`; `railway.json` выбирает
   `Dockerfile.standalone` и проверку здоровья.
2. Сервис → Settings → Networking → Generate Domain, целевой порт `9083`.
3. Добавьте том, смонтированный в `/app/data`.
4. Переменные: `AIMARKET_HUB_URL=https://<выданный домен>`, `AIMARKET_HUB_NAME`,
   `AIMARKET_ADMIN_TOKEN`, `PORT=9083`. Деплой.

## Render

New → Blueprint → ваш форк. `render.yaml` создаёт веб-сервис с диском 1 ГБ в `/app/data` и
спрашивает `AIMARKET_HUB_URL` (`https://<имя сервиса>.onrender.com`) и `AIMARKET_HUB_NAME`;
`AIMARKET_ADMIN_TOKEN` генерирует сам. Диск требует платного типа инстанса.

## Fly.io

```bash
fly launch --no-deploy --copy-config --name <your-app>
fly volumes create hub_data --size 1
fly secrets set AIMARKET_ADMIN_TOKEN=$(openssl rand -base64 32)
fly deploy
```

Сначала поправьте в `fly.toml` поля `app`, `AIMARKET_HUB_URL` (`https://<your-app>.fly.dev`) и
`AIMARKET_HUB_NAME`. Машина не засыпает (`auto_stop_machines = "off"`): хаб должен отвечать на
обход и пробы допуска в любое время.

## Дальше

`doctor` запускается откуда угодно, в том числе с вашего ноутбука, против публичного адреса:

```bash
uvx --from "aimarket-hub[pqc]" aimarket doctor --url https://<ваш хаб>
```

Когда `doctor` говорит `pass`, стучитесь — см. [Свой собственный хаб](operator-quickstart.ru.md#5-стук).
Чтобы выставить свой API, откройте shell на платформе (`railway ssh`, Render Shell,
`fly ssh console`) и выполните там `docker-entrypoint.sh add …`: команда пишет в собственную
базу хаба на томе от имени пользователя хаба, поэтому файлы остаются доступными хабу на запись.

Эти файлы следуют документированному формату каждой платформы; сам образ проверен на томе,
принадлежащем root, — именно такие тома монтируют эти платформы.
