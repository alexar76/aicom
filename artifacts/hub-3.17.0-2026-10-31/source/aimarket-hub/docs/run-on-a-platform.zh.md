# 在平台上运行枢纽

[English](run-on-a-platform.md) · [Русский](run-on-a-platform.ru.md) · [Español](run-on-a-platform.es.md) · [Français](run-on-a-platform.fr.md) · [中文](run-on-a-platform.zh.md)

Railway、Render 和 Fly 无需自有域名就能给枢纽一个公开的 `https` 地址。仓库为每个平台都准备了配置文件（`railway.json`、`render.yaml`、`fly.toml`），它们都构建 `Dockerfile.standalone`。镜像在第一次启动时会自行完成设置（`serve --init`：设置文件、管理员令牌、免费的 `hub.ping@v1` 和一个收费示例），所以首次部署之前什么都不用运行。

在任何平台上都有三条规则：

1. **在 `/app/data` 挂载持久卷。**签名密钥、数据库和设置文件都在那里，而密钥就是枢纽的身份：没有它们的部署就是一个新枢纽，所有固定了旧密钥的对等节点都会拒绝它。免费档不提供卷的平台无法运行枢纽。
2. **在第一次启动之前设置 `AIMARKET_HUB_URL`**，值为平台分配的公网地址。它出现在枢纽签名的每一份文档里，其他枢纽也凭它认识你。
3. **把 `AIMARKET_ADMIN_TOKEN` 设为平台密钥**，这样你自己知道它：用它批准对等节点、给买家充值。若未设置，`--init` 会在卷内生成一个。

## Railway

1. 新建项目 → 从你 fork 的 `alexar76/aimarket-hub` 部署；`railway.json` 会选用 `Dockerfile.standalone` 和健康检查。
2. 服务 → Settings → Networking → Generate Domain，目标端口 `9083`。
3. 添加挂载在 `/app/data` 的卷。
4. 变量：`AIMARKET_HUB_URL=https://<生成的域名>`、`AIMARKET_HUB_NAME`、`AIMARKET_ADMIN_TOKEN`、`PORT=9083`。部署。

## Render

New → Blueprint → 你的 fork。`render.yaml` 会创建一个 Web 服务，在 `/app/data` 挂载 1 GB 磁盘，并要求填写 `AIMARKET_HUB_URL`（`https://<服务名>.onrender.com`）和 `AIMARKET_HUB_NAME`；`AIMARKET_ADMIN_TOKEN` 自动生成。磁盘需要付费实例类型。

## Fly.io

```bash
fly launch --no-deploy --copy-config --name <your-app>
fly volumes create hub_data --size 1
fly secrets set AIMARKET_ADMIN_TOKEN=$(openssl rand -base64 32)
fly deploy
```

先在 `fly.toml` 里修改 `app`、`AIMARKET_HUB_URL`（`https://<your-app>.fly.dev`）和 `AIMARKET_HUB_NAME`。机器保持运行（`auto_stop_machines = "off"`）：枢纽必须随时响应抓取和准入探测。

## 之后

`doctor` 可以在任何地方运行，包括你的笔记本，针对公网地址：

```bash
uvx --from "aimarket-hub[pqc]" aimarket doctor --url https://<你的枢纽>
```

当 `doctor` 显示 `pass` 时，就去敲门——见[自己运营这个枢纽](operator-quickstart.zh.md#5-敲门)。要挂上你自己的 API，在平台上打开 shell（`railway ssh`、Render Shell、`fly ssh console`），在那里运行 `docker-entrypoint.sh add …`：它以枢纽自己的用户身份写入卷上的枢纽数据库，因此这些文件仍然可以被枢纽写入。

这些文件遵循各平台文档规定的格式；镜像本身已在属于 root 的卷上测试过，这些平台挂载的正是这种卷。
