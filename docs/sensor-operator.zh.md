# 免费运行自己的传感器枢纽

[English](sensor-operator.md) · [Русский](sensor-operator.ru.md) · [Español](sensor-operator.es.md) · [Français](sensor-operator.fr.md) · [中文](sensor-operator.zh.md)

**在自己的基础设施上免费部署和使用 Hub + GAIA**，自行控制密钥、传感器数据和服务。本指南面向气象站所有者、本地传感器社区和小型 IoT 集成商。基础设施由你提供；自托管使用无需向我们支付软件许可费或订阅费。

通过常规准入后，AIMarket 联邦可成为你提供数据和服务的潜在销售市场。是否出售访问权限由你决定，价格也由你设定；不保证买方或收入。下文的付费服务示例展示这一可选路径。开始使用自己的枢纽无需购买数据，也无需先完成销售。

适合起步的服务是提供真实的本地观测，弥补买方只能获得预报或观测稀少的问题。请说明地点、测量字段、更新间隔和传感器的局限。简单复制公开数据源，需要额外说明其价值。

本文是可复现的配置指南，不是已完成硬件部署的案例，也不承诺收入。通过准入后，联邦使你的服务可被发现；买方仍需决定是否购买。

## 你需要运行什么

数据路径为：**你的传感器 → 你的适配器 → GAIA → 你的 Hub → 买方**。GAIA 接收读数并签署结果；Hub 发布服务、处理已配置的支付方式并返回回执。签名证明来源和完整性，本身并不能独立证明测量准确性。

无需先建立 API 业务，但必须能够把设备读数转换为下方 JSON 格式。接收端点并非适用于所有 Tasmota、ESPHome、Home Assistant、TTN 或 SenML 设备的自动连接器；硬件格式转换仍由适配器完成。

目前通用接收器支持 `temperature_c`、`humidity_pct`、`pressure_hpa`、`pm2_5_ugm3`，以及必需的 `latitude` 和 `longitude`。只发送实际测量的字段。设备标识为 `feeder-iot-01`，销售的能力为 `gaia.iot.read@v1`。一个实例目前只有一个通用 IoT 接收槽位；多站点部署需要明确扩展实现或使用独立实例，不能随意编造设备标识。

## 1. 启动私有 GAIA 提供方

需要 Docker、`curl`、`jq`、可导出真实读数的适配器，以及按照[运营者指南](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.zh.md)初始化的 Hub。示例在 Docker 中运行 GAIA，在**同一台机器**上直接运行 Hub。从已经审查的 AICOM 代码版本的仓库根目录构建：

```bash
docker build -f gaia/Dockerfile -t local/gaia-sensor .
export GAIA_FEEDER_TOKEN="$(openssl rand -hex 32)"
docker run -d --name gaia-sensor \
  -p 127.0.0.1:9320:9320 \
  -v gaia-sensor-data:/data \
  -e GAIA_FEEDER_TOKEN \
  -e GAIA_ENABLE_LIVE=1 -e GAIA_FEEDER_ENABLED=1 \
  -e GAIA_SIM_CONTROL=0 -e AIFACTORY_PROD=1 \
  -e GAIA_PUBLIC_URL=http://127.0.0.1:9320 \
  -e GAIA_KEY_DIR=/data/devices \
  -e GAIA_SIGNING_KEY_PATH=/data/gaia_signing_key \
  local/gaia-sensor
```

将生成的接收令牌保存在私有配置中；上传客户端必须使用同一值。持久保存 `/data` 卷中的网关和设备密钥。示例将 GAIA 绑定到 loopback，买方通过 Hub 访问。远程传感器需要受保护的 HTTPS 或私有网络接入上传端点，而不是公开暴露提供方端口。

当前启动流程同时需要 `GAIA_ENABLE_LIVE=1` 和 `GAIA_FEEDER_ENABLED=1`。GAIA 还会注册内置中继源和模拟器；本指南只在 Hub 上发布你自己的 `gaia.iot.read@v1` 服务。不要将模拟站点描述成真实硬件。

## 2. 发送真实观测

让适配器按以下结构写入 `station-reading.json`。发送前，将所有带引号的占位符替换为真实的 **JSON 数字**；模板本身不是测量数据。`observed_at` 是传感器实际观测的 Unix 秒时间戳，而不是旧数据再次上传的时间。

```json
{
  "device_id": "feeder-iot-01",
  "observed_at": "<observed_at>",
  "fields": {
    "latitude": "<latitude>",
    "longitude": "<longitude>",
    "temperature_c": "<temperature_c>"
  }
}
```

上传后，在本地读取同一设备：

```bash
curl --fail-with-body -sS http://127.0.0.1:9320/feeder/v1/ingest \
  -H "Authorization: Bearer $GAIA_FEEDER_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @station-reading.json

curl --fail-with-body -sS http://127.0.0.1:9320/ai-market/v2/invoke \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"gaia.gateway","capability_id":"gaia.iot.read@v1","input":{"device_id":"feeder-iot-01"}}'
```

接收请求应返回 `ok: true`，调用结果应包含读数和证明（attestation）。检查返回的设备、数值和来源。还要检查 JSON：读数不可用时，即使 HTTP 为 200，也可能返回 `ok: false`。这个本地提供方调用仅验证连接，不是销售。

更新间隔应短于当前 600 秒的新鲜度限制。无数据或数据过期时，接收器不可用。目前只在**进程内存**中保存最后一次观测：重启后必须先上传新读数，再接受购买。持久保存密钥不等于保存历史数据。

## 3. 在自己的 Hub 发布读数

在已初始化 Hub 的工作目录和环境中，将 `SENSOR_PAY_TO` 设置为**你的收款钱包地址**，绝不能填入私钥。示例价格为每次调用 $0.002，你可以自行定价。在本地获取 GAIA 网关公钥并将其固定到目录条目：

```bash
: "${SENSOR_PAY_TO:?Set SENSOR_PAY_TO to your receiving wallet address}"
GAIA_PROVIDER_KEY="$(curl -fsS http://127.0.0.1:9320/.well-known/ai-market.json | jq -er .signer_public_key)"
export AIMARKET_INVOKE_HOST_GATEWAY=127.0.0.1
aimarket add gaia.iot.read@v1 \
  --product gaia.gateway \
  --url http://127.0.0.1:9320/ai-market/v2/invoke \
  --provider-pubkey "$GAIA_PROVIDER_KEY" \
  --price 0.002 --pay-to "$SENSOR_PAY_TO" \
  --name "Local station readings" \
  --description "Current measurements from the operator's own station" \
  --input-schema '{"type":"object","properties":{"device_id":{"type":"string","enum":["feeder-iot-01"]}},"required":["device_id"],"additionalProperties":false}'
```

使用同一 Hub 数据库启动或重启 `aimarket serve`，并在服务环境中保留 `AIMARKET_INVOKE_HOST_GATEWAY=127.0.0.1`。这明确允许 Hub 调用本地提供方。若 Hub 在容器内或另一台机器上，请遵循[生产部署指南](https://github.com/alexar76/aimarket-hub/blob/main/docs/production-deployment.md)的网络配置；容器内的 loopback 指向容器自身。

GAIA 已对提供方响应签名；`--provider-pubkey` 使 Hub 能够验证这些签名。本地 `aimarket add` 发布你自己的服务。在他人的 Hub 上发布则需要遵循另一个准入流程。

## 4. 检查支付要求

不携带支付信息或 sandbox 请求头，调用 Hub：

```bash
curl -sS -i http://127.0.0.1:9083/ai-market/v2/invoke \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"gaia.gateway","capability_id":"gaia.iot.read@v1","source_hub":"local","input":{"device_id":"feeder-iot-01"}}'
```

对于已配置支付的付费服务，应返回 `402` 和支付报价。付款前核对金额、网络、资产和收款方。若未付款就获得读数，则支付限制检查未通过。

`--pay-to` 用于声明收款方；公开运行前，请按照[运营者指南](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.zh.md)完成卖方直接收款配置。真实买方按照报价授权支付，再通过受支持的客户端重新调用。保存回执并确认到账。为测试创建的本地积分余额不是外部收入。

本示例不启用 Pay-on-Verified。读数具有签名，不意味着按验证结果结算，也不意味着已经完成的直接支付会自动退款。净收入取决于实际付费使用、手续费、托管和设备维护；加入联邦并不保证销售。

## 5. 按照正常规则加入联邦

按照生产指南通过公共 HTTPS 部署 Hub，让 GAIA 保持私有，并将 `hub.example.com` 替换为实际地址。保留 quickstart 创建的免费签名能力 `hub.ping@v1`，供准入检查使用。迁移到生产环境时保留原有密钥和数据库。

```bash
aimarket quickstart --url https://hub.example.com --no-buyer
aimarket doctor --url https://hub.example.com
curl --fail-with-body -sS https://modelmarket.dev/ai-market/v2/federation/announce \
  -H 'Content-Type: application/json' \
  -d '{"hub_url":"https://hub.example.com","hub_name":"My sensor hub"}'
```

在返回的 `assay_url` 查看结论。监控中可见或声明处于 pending 状态，**不**意味着已获准入、索引或路由。检查失败时，应依照现有规则修正。参见[加入联邦](join-the-federation.zh.md)。买方调用时应保留搜索返回的 `source_hub`。

ATLAS 上的传感器标记与 Hub 准入是独立步骤。不能承诺自动出现在地图上：受支持的类型请按照 [GAIA → ATLAS 指南](i18n/add-gaia-atlas-sensor.zh.md)配置，新的集成则需审查。

## 连接你的站点

如需讨论首次接入，请在 [GitHub Discussions](https://github.com/alexar76/aicom/discussions) 发帖，说明设备型号、可用字段、大致覆盖区域、观测及更新间隔、导出格式，以及是否能够运行 Hub。不要发布令牌或私钥。

第一个有用的里程碑是：外部客户端购买了来自你设备的新鲜读数，并获得回执且完成到账确认。随后观察重复购买和持续运行情况。测试购买应单独标记。社区运营者可以协调多个所有者，但当前单槽位接收器需要扩展，或为每个独立站点部署单独实例。

另见：[GAIA 实时数据源与接收器](https://github.com/alexar76/gaia/blob/main/docs/i18n/LIVE-RELAYS.zh.md) · [Hub 运营者指南](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.zh.md) · [公开需求指标](https://verify.modelmarket.dev/demand.json)。
