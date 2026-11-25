FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir . && useradd -r ocp && mkdir /data && chown ocp /data
ENV OCP_ROOT=/app OCP_DB=/data/ocp.sqlite3
USER ocp
EXPOSE 8080
CMD ["uvicorn", "ocp.service.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
