# Load tests

Start the API, then:

```bash
cd ai-service-mesh/backend
pip install locust
locust -f load/locustfile.py --host http://127.0.0.1:8090
```

Headless smoke (30s, 20 users):

```bash
locust -f load/locustfile.py --host http://127.0.0.1:8090 \
  --headless -u 20 -r 4 -t 30s --only-summary
```

Set `MESH_API_TOKEN` when testing authenticated task creation in production mode.
