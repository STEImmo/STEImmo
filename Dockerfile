FROM python:3.13-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY . .

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && groupadd --gid 10001 steimmo \
    && useradd --uid 10001 --gid steimmo --no-create-home steimmo \
    && mkdir -p /app/media /app/staticfiles \
    && chown steimmo:steimmo /app/media /app/staticfiles

USER 10001:10001

EXPOSE 8000

ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]

FROM app AS development
USER root
RUN python -m pip install ".[dev]"

FROM app AS runtime
