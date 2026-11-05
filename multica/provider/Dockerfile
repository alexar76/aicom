FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
USER app
EXPOSE 8090
CMD ["uvicorn", "multica_provider.app:app", "--host", "0.0.0.0", "--port", "8090"]
