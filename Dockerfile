# syntax=docker/dockerfile:1.7
# One image for every Python service (api, feed, daemon, paper-trader, comparison) plus a
# static build of the web UI for the public nginx container.

ARG NODE_IMAGE=node:22-bookworm-slim
ARG PYTHON_IMAGE=python:3.12-slim-bookworm

FROM ${NODE_IMAGE} AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
# Optional "ca" secret: only for builds behind a TLS-inspecting proxy; ignored otherwise.
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca; fi; \
    npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ${PYTHON_IMAGE} AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 10001 quant
WORKDIR /app
COPY ecosystem-requirements.txt ./
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install -r ecosystem-requirements.txt
COPY backend/ backend/
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install ./backend
COPY scripts/ scripts/
COPY samples/ samples/
COPY --from=web /web/dist /app/frontend/dist
RUN mkdir -p /app/data && chown -R quant:quant /app/data
USER quant
ENV TERMINAL_PAPER_VENUE=testnet
EXPOSE 8000
CMD ["quant-terminal-api", "--host", "0.0.0.0", "--port", "8000"]
