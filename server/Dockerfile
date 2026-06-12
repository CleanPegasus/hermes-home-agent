FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/server

RUN python -m pip install --no-cache-dir --upgrade pip

COPY server/pyproject.toml server/uv.lock* ./
COPY server/app ./app
COPY server/tests ./tests

RUN python -m pip install --no-cache-dir -e . "psycopg[binary]>=3.2"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
