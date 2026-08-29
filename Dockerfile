FROM node:22-alpine AS web-builder

WORKDIR /workspace/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
ENV ACE_STATIC_EXPORT=1
ENV NEXT_PUBLIC_API_URL=""
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/services/api \
    ACE_MODEL_MODE=heuristic \
    ACE_DATABASE_URL=sqlite:////tmp/ace-public-demo.sqlite3 \
    ACE_WEB_STATIC_DIR=/workspace/apps/web/out

WORKDIR /workspace
COPY deploy/render/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --create-home --uid 10001 appuser

COPY services/api/app ./services/api/app
COPY services/api/data ./services/api/data
COPY services/api/migrations ./services/api/migrations
COPY services/api/alembic.ini ./services/api/alembic.ini
COPY --from=web-builder /workspace/apps/web/out ./apps/web/out

USER appuser
EXPOSE 10000
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
