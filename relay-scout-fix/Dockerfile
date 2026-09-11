FROM python:3.12-slim
WORKDIR /app
# run_api.py is the CMD below; without it the image built fine and then died with
# "can't open file '/app/run_api.py'" on every start. main.py is the CLI entry point.
COPY pyproject.toml README.md relay-scout.yaml run_api.py main.py ./
COPY relay_scout ./relay_scout
COPY tests ./tests
RUN pip install --no-cache-dir -e ".[dev]"
EXPOSE 8000
CMD ["python", "run_api.py"]
