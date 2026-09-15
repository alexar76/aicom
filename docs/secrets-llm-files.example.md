# LLM API key files (optional)

Create on the host (not committed):

```bash
mkdir -p data/secrets/llm
install -m 600 /dev/null data/secrets/llm/deepseek_api_key
# paste key into the file (no trailing newline required)
```

Then either rely on the `./data` bind mount (entrypoint reads these paths) or use:

```bash
docker compose -f docker-compose.yml -f docker-compose.secrets.yml up -d
```
