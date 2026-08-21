FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md relay-scout.yaml ./
COPY relay_scout ./relay_scout
COPY tests ./tests
RUN pip install --no-cache-dir -e ".[dev]"
EXPOSE 8000
CMD ["python", "run_api.py"]
