# Relay Scout

Autonomous Python health watchdog for the alexar76 AIMarket ecosystem.

## CLI

```bash
pip install -e ".[dev]"
relay-scout check --config relay-scout.yaml
relay-scout diff factory --config relay-scout.yaml
relay-scout watch --config relay-scout.yaml --once
```

## API (devtools ops)

```bash
python run_api.py  # listens on :8000
```

## Devtools ops acceptance scenarios

- **Deploy**: POST `/api/projects/{id}/deployments` → deployment status tracked (queued/running/succeeded).
- **Rollback**: POST `/api/deployments/{id}/rollback` → status `rolled back`.
- **Alert**: POST `/api/alerts` then POST `/api/alerts/{id}/ack` → open → ack → resolved.

## Tests

```bash
pytest -q
```
