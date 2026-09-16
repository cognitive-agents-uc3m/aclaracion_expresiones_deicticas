FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements.txt

COPY gui.py student_local.py ./
COPY src ./src
COPY config ./config
COPY prompts ./prompts
COPY models ./models

RUN useradd --create-home --uid 10001 agente \
    && mkdir -p /var/lib/cognitive-agent \
    && chown -R agente:agente /app /var/lib/cognitive-agent

USER agente

EXPOSE 7860 7861

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/healthz', timeout=4)"

CMD ["python", "gui.py"]