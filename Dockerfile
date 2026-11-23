# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 1000 --user-group --create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY frontend ./frontend
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

LABEL org.opencontainers.image.title="christmas-list-organiser" \
      org.opencontainers.image.description="Self-hosted Christmas gift planner with budgets and status tracking" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/ashleycollinge1/christmas-list-organiser"

USER app
EXPOSE 8000
ENTRYPOINT ["tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["web"]
