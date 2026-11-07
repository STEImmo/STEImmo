FROM python:3.13-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY . .

RUN python -m pip install --require-hashes --only-binary=:all: -r requirements/build.txt \
    && python -m pip install --require-hashes --only-binary=:all: -r requirements/runtime.txt \
    && python -m pip install --no-deps --no-build-isolation . \
    && python -m pip check \
    && groupadd --gid 10001 steimmo \
    && useradd --uid 10001 --gid steimmo --no-create-home steimmo \
    && mkdir -p /app/media /app/staticfiles \
    && chmod -R a+rX,go-w /app \
    && chown steimmo:steimmo /app/media /app/staticfiles

USER 10001:10001

EXPOSE 8000

ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]

FROM app AS development
ENV XDG_CACHE_HOME=/tmp/steimmo-cache
ARG STEIMMO_DEV_UID=10001
ARG STEIMMO_DEV_GID=10001
USER root
RUN test "$STEIMMO_DEV_UID" -gt 0 \
    && test "$STEIMMO_DEV_GID" -gt 0 \
    && python -m pip install --require-hashes --only-binary=:all: -r requirements/dev.txt \
    && python -m pip install --no-deps --no-build-isolation ".[dev]" \
    && python -m pip check \
    && groupmod --non-unique --gid "$STEIMMO_DEV_GID" steimmo \
    && usermod --non-unique --uid "$STEIMMO_DEV_UID" --gid steimmo steimmo \
    && chown steimmo:steimmo /app/media /app/staticfiles
USER ${STEIMMO_DEV_UID}:${STEIMMO_DEV_GID}

FROM app AS runtime
