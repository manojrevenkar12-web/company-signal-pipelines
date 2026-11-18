FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src:/app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && python -m venv /opt/dbt && /opt/dbt/bin/pip install --no-cache-dir dbt-core==1.12.7 dbt-postgres==1.11.0
ENV DBT_BIN=/opt/dbt/bin/dbt
COPY config config
COPY migrations migrations
COPY dbt dbt
COPY src src
COPY world world
COPY evals evals
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "signals.service.api:app", "--host", "0.0.0.0", "--port", "8000"]
