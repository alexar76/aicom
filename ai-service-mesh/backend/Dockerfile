FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY ai_service_mesh ./ai_service_mesh
RUN pip install --no-cache-dir ".[postgres]"
ENV MESH_HOST=0.0.0.0
ENV MESH_PORT=8090
ENV MESH_DATA_DIR=/data
EXPOSE 8090
CMD ["python", "-m", "ai_service_mesh.main"]
