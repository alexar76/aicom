.PHONY: api dashboard test load install

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install ".[dev]"
	cd frontend && npm install

api:
	cd backend && PYTHONPATH=. .venv/bin/python -m ai_service_mesh.main

dashboard:
	cd frontend && npm run dev

test:
	cd backend && PYTHONPATH=. .venv/bin/pytest -q

load:
	cd backend && .venv/bin/locust -f load/locustfile.py --host http://127.0.0.1:8090
