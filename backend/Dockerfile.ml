FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Both files are required — requirements-ml.txt adds transformers, FAISS,
# sentence-transformers, and spaCy models used by the NLP pipeline.
COPY requirements.txt requirements-ml.txt ./
RUN uv pip install --system --no-cache -r requirements.txt && \
    uv pip install --system --no-cache -r requirements-ml.txt

# Download models at build time so containers work without internet at runtime.
#
# spaCy en_core_web_sm: used by Presidio PII (step2) + NER fallback (step3).
# en_core_sci_md (scispaCy biomedical) cannot be installed — it requires
# spaCy<3.8 which conflicts with spacy==3.8.14; step3 falls back to en_core_web_sm.
#
# cardiffnlp sentiment: the HuggingFace transformers library auto-downloads
# models on first use, but that silently pulls ~500MB at container startup.
# Pre-baking it here makes offline / cold-start runs reliable; step4 falls
# back to VADER if this model is unavailable.
RUN python -m spacy download en_core_web_sm && \
    python -c "\
from transformers import AutoTokenizer, AutoModelForSequenceClassification; \
AutoTokenizer.from_pretrained('cardiffnlp/twitter-roberta-base-sentiment-latest'); \
AutoModelForSequenceClassification.from_pretrained('cardiffnlp/twitter-roberta-base-sentiment-latest'); \
print('Sentiment model cached.')"

COPY . .

EXPOSE 8000
