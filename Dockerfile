FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    DEBUG=false \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY .chainlit/config.toml .chainlit/config.toml
COPY chainlit.md .

# Cache the same tokenizer and CPU model used by retrieval. No PDF is processed.
RUN python -c "from iphone_guide_chatbot.config.settings import get_config, CACHE_PATH; from iphone_guide_chatbot.ingestion.embeddings import load_tokenizer; from sentence_transformers import SentenceTransformer; config = get_config(); load_tokenizer(config); SentenceTransformer(config['model_name'], revision=config['model_revision'], device='cpu', cache_folder=CACHE_PATH)"

# Runtime queries use the cached model; Qdrant and Gemini still use the network.
ENV HF_HUB_OFFLINE=1

RUN useradd --create-home appuser \
    && mkdir -p logs .files \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000', timeout=4)" || exit 1

CMD ["python", "-m", "chainlit", "run", "src/iphone_guide_chatbot/ui/app.py", "--headless", "--host", "0.0.0.0", "--port", "8000"]
