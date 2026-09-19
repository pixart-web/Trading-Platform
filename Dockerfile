FROM python:3.12-slim-bookworm AS dependencies
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
COPY requirements-runtime.lock ./
RUN "$VIRTUAL_ENV/bin/pip" install --no-cache-dir --requirement requirements-runtime.lock

FROM python:3.12-slim-bookworm AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
COPY --chown=10001:10001 src ./src
COPY --chown=10001:10001 alembic.ini ./
COPY --chown=10001:10001 migrations ./migrations
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin pocket
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=4s --start-period=15s --retries=4 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3).read()"]
CMD ["uvicorn", "pocket_alpha.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
