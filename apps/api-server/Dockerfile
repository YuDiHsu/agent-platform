FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/
WORKDIR /srv

COPY apps/api-server/pyproject.toml apps/api-server/uv.lock /srv/apps/api-server/
WORKDIR /srv/apps/api-server
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/api-server /srv/apps/api-server
COPY packages /srv/packages

ENV PATH="/srv/apps/api-server/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
