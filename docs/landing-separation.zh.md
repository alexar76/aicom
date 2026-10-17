# 工厂、产品展示与生态系统：三个独立地址

[EN](landing-separation.md) · [RU](landing-separation.ru.md) · [ES](landing-separation.es.md) · [FR](landing-separation.fr.md) · [中文](landing-separation.zh.md)

- `https://magic-ai-factory.com/`：实际运行的工厂、生成器、产品展示与管理入口。
- `https://modeldev.modelmarket.dev/`：新的工厂宣传页。
- `https://ecosystem.modelmarket.dev/`：机器经济生态系统的规范图谱。

主按钮打开实际工厂。产品链接指向 `/#products`，生成器、智能体、文档和条款均打开实际应用。图谱通过宣传页介绍工厂，项目卡片链接到真实服务。生态系统链接使用独立域名。

原工厂主页已恢复，服务采购继续启用；域名迁移不改变后端、账户、订单日志或预算。参见[采购指南](factory-subcontracting.zh.md)。

`app/HomePage.tsx` 保留实际产品展示，`components/factory/FactoryLanding.tsx` 是宣传页。仅单独构建并以 `AICOM_SITE_ROLE=factory-landing` 运行的前端显示宣传页。它使用 `NEXT_PUBLIC_SITE_URL=https://modeldev.modelmarket.dev`，提供 `/`、`/ru/`、`/es/`、`/fr/`、`/zh/` 五种语言路径及对应 canonical 和语言替代链接，不安装应用 PWA 或市场组件。普通构建仍显示工厂。

图谱源文件位于 `scripts/github-io/`，canonical、sitemap 和社交元数据使用 `ecosystem.modelmarket.dev`。可通过 `ATLAS_SITE_URL` 显式覆盖构建域名。本次不推送 GitHub；现有 GitHub 网站的旧重定向保留，直到另行授权发布。

两个完整模型自动旋转，并支持鼠标／手指拖动和方向键，无暂停按钮。尊重系统减少动态效果设置。这些是概念示意图，不是实时数据。保留 modeldev 的 encyclopedia、school、guides、learn、oracles 旧内容。

生产环境：实际应用端口 9080；modeldev 前端端口 9088，容器 `aicom-frontend-modeldev-20261011`，镜像 `ai-factory-frontend:modeldev-final-20261011`。图谱路径 `/var/www/ecosystem.modelmarket.dev` 指向 `/var/www/ecosystem-atlas-20261011`。源文件和备份位于 `/root/domain-split-20261011/`；`rollback-modeldev.sh` 可恢复旧 vhost，不停止工厂或采购服务。Certbot 使用既有账户、webroot 验证、自动续期和 nginx 重载 hook；申请证书前应等待 DNS 传播。

检查五种语言、规范链接、导航、WebGL、保留内容和 API 健康。执行 typecheck、生产构建及 `python3 scripts/github-io/validate.py`。[验证结果](evidence/domain-split-2026-10-11/README.md)。
