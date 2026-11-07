FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SWITCHGUARD_PORT=8090 \
    SWITCHGUARD_DB_PATH=/app/data/switchguard.db

COPY pyproject.toml ./
RUN pip install --no-cache-dir fastapi uvicorn httpx pytest pydantic pyyaml

COPY blueprint ./blueprint
COPY demo_app ./demo_app
COPY tools ./tools
COPY fixtures ./fixtures
COPY scripts ./scripts
COPY switchguard-sre.template.yaml .env.example ./

RUN mkdir -p /app/data /app/postmortems

EXPOSE 8090

CMD ["uvicorn", "demo_app.main:app", "--host", "0.0.0.0", "--port", "8090"]
