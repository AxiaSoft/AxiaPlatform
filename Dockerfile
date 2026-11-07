FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    AXIA_DB=/app/data/axiasoft.sqlite3

WORKDIR /app

COPY server ./server
COPY public ./public

RUN mkdir -p /app/data \
    && useradd --system --uid 10001 --no-create-home appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Container health check uses the unmetered, never-shed health endpoint.
HEALTHCHECK --interval=30s --timeout=4s --start-period=8s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

# SIGTERM handling: the server closes its listener and finishes in-flight work.
STOPSIGNAL SIGTERM

CMD ["python", "-u", "server/app.py"]
