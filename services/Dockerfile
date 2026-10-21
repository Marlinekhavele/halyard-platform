# One image recipe for every Python service.
#   docker build -f services/Dockerfile --build-arg SERVICE=accounts -t halyard/accounts .
# Build context is the repository root, so the shared package is available.
FROM python:3.12-slim

ARG SERVICE
ENV SERVICE=${SERVICE} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY packages/halyard-common /app/packages/halyard-common
RUN pip install "/app/packages/halyard-common[telemetry]"

COPY services/${SERVICE} /app/service
RUN pip install /app/service

RUN useradd --system --uid 10001 halyard && mkdir -p /data && chown halyard /data
USER halyard

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"
# Apply database migrations, then serve.
CMD ["sh", "-c", "alembic -c /app/service/alembic.ini upgrade head && exec uvicorn ${SERVICE}.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
