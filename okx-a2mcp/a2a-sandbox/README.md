# OKX A2A sandbox

`onchainos agent activate` refuses to publish an OKX.AI provider until OKX's A2A daemon has an AI
runtime bound to it, and that daemon starts the runtime on messages from the OKX network with
permission checks bypassed by default. Our listing is A2MCP only (plain HTTPS, see `../`), so
nothing here should ever run an AI. This container exists to satisfy the check without putting
that daemon on a workstation:

- non-root user, no host mounts, no docker socket, no published ports, all capabilities dropped;
- Claude Code installed so the runtime is detected, never logged in, so it cannot execute;
- OKX's CLI and daemon installed inside by their own installer, state in a named volume.

```bash
docker build -t okx-a2a-sandbox .
docker network create okx-a2a-sandbox
docker run -d --name okx-a2a-sandbox --restart unless-stopped --network okx-a2a-sandbox \
  --cap-drop ALL --security-opt no-new-privileges --memory 1g --pids-limit 256 \
  -v okx-a2a-home:/home/okx okx-a2a-sandbox
docker exec okx-a2a-sandbox npx -y @okxweb3/onchainos-installer install
docker exec okx-a2a-sandbox okx-a2a ai-provider set --provider claude
docker exec okx-a2a-sandbox okx-a2a config permissions --preset auto
docker exec okx-a2a-sandbox okx-a2a agent bypass off
docker exec okx-a2a-sandbox onchainos wallet login --phase init     # the owner opens the link
docker exec okx-a2a-sandbox onchainos wallet login --phase poll --session-id ID
docker exec okx-a2a-sandbox onchainos agent activate --agent-id 14118 --preferred-language ru-RU
```
