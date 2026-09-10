FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home pocket
USER pocket
EXPOSE 8000
CMD ["uvicorn", "pocket_alpha.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
