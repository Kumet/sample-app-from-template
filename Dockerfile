FROM python:3.11.11-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN python -m pip wheel --wheel-dir /wheels .


FROM python:3.11.11-slim-bookworm AS runtime

ENV HOME=/data \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 project-board \
    && useradd --uid 10001 --gid 10001 --home-dir /data --no-create-home \
        --shell /usr/sbin/nologin project-board \
    && mkdir /data \
    && chown 10001:10001 /data

COPY --from=builder /wheels /wheels

RUN python -m pip install --no-index --find-links=/wheels local-project-board \
    && rm -rf /wheels

WORKDIR /data
USER 10001:10001

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import json, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2); assert response.status == 200; assert json.load(response) == {'status': 'ok'}"]

CMD ["python", "-m", "uvicorn", "project_board.main:app", "--host", "0.0.0.0", "--port", "8000"]
