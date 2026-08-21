FROM python:3.12-slim

WORKDIR /workspace/services/api
COPY services/api/pyproject.toml ./
COPY services/api/app ./app
COPY services/api/data ./data
COPY services/api/alembic.ini ./
COPY services/api/migrations ./migrations
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
