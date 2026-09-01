FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system inventory \
    && useradd --system --gid inventory --create-home inventory

WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN pip install --no-cache-dir .

USER inventory
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
