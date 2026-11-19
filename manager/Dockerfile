# Build context: the repository root (see compose.yaml).
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
WORKDIR /app
COPY manager/manager /app/manager
COPY webui/functions /app/webui/functions
COPY webui/presets /app/webui/presets
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "manager"]
