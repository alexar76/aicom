## HELIOS v0.1.0

**Broadcast pipeline for the AIMarket ecosystem**

- YAML templates → TTS → ffmpeg render → YouTube upload (**private** until `helios approve`)
- **CALLIOPE** editorial scout + backfill queue for [@My-AI-Factory](https://www.youtube.com/@My-AI-Factory)
- POST-only HTTP API · fail-soft · no engagement bots
- EN / RU / ES docs + operator runbooks

### Quick start

```bash
pip install helios-broadcast
cp helios.config.example.yaml helios.config.yaml
helios auth
helios worker
```

**Landing:** [alexar76.github.io/helios](https://alexar76.github.io/helios/) · **Integration:** [helios-integration.md](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/helios-integration.md)
