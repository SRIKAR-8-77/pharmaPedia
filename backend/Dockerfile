FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Lite stack — no PyTorch/transformers. Sentiment falls back to VADER automatically.
# spaCy en_core_web_sm handles PII (presidio) + NER. datasketch handles dedup.
COPY requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt

RUN python -m spacy download en_core_web_sm

COPY . .

EXPOSE 8000
