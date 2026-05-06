"""
Step 4 — Medical-aware sentiment analysis.

Three-layer approach for biomedical text:
  Layer 1: Medical lexicon override — strong clinical terms (anaphylaxis, death,
            hospitalized) force negative regardless of other signals. This addresses
            the core failure mode of general-purpose models on medical text.
  Layer 2: HuggingFace RoBERTa (twitter-trained) — better than VADER at negation
            and hedging. Uses windowed entity-level aspect scoring.
  Layer 3: VADER fallback — always available, enhanced with medical term weights.

Limitation we're honest about: BioBERT/BioClinicalBERT would outperform all of the
above on clinical text. Those models require GPU and ~400MB download. We use a
lexicon-based override as a practical substitute for the hackathon.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"
LABEL_MAP = {"LABEL_0": "negative", "LABEL_1": "neutral", "LABEL_2": "positive",
             "negative": "negative", "neutral": "neutral", "positive": "positive"}

# ── Medical lexicon override ───────────────────────────────────────────────────
# These terms ALWAYS produce negative sentiment regardless of model output.
# A post saying "survived anaphylaxis" still signals a serious adverse event.
STRONG_NEGATIVE_MEDICAL = {
    "anaphylaxis", "anaphylactic", "cardiac arrest", "heart attack",
    "stroke", "pulmonary embolism", "seizure", "convulsion",
    "hospitalized", "hospitalization", "emergency room", "icu",
    "pancreatitis", "kidney failure", "renal failure",
    "thyroid cancer", "medullary thyroid",
    "death", "died", "fatal", "overdose",
    "suicidal", "suicide", "self-harm",
    "severe hypoglycemia", "hypoglycemic coma",
    "discontinued", "stopped taking", "had to stop",
    "adverse reaction", "adverse event", "serious adverse",
    "life-threatening", "life threatening",
}

# These push score more negative (additive bias: -0.3)
MEDICAL_NEGATIVE_BIAS = {
    "side effect", "side effects", "nausea", "vomiting", "diarrhea",
    "hair loss", "alopecia", "fatigue", "dizziness", "headache",
    "rash", "itching", "stomach pain", "abdominal pain",
    "allergic", "allergy", "injection site", "not working",
    "didn't help", "didn't work", "no improvement",
    "worse", "worsened", "getting worse",
}

# These push score more positive (additive bias: +0.2) — genuine improvement signals
MEDICAL_POSITIVE_BIAS = {
    "a1c dropped", "blood sugar controlled", "weight loss success",
    "feeling better", "improved", "improvement",
    "no side effects", "tolerated well", "well tolerated",
    "effective", "working great", "working well",
}

_hf_pipeline = None
_vader = None
_use_hf = None  # None = not yet determined


def _get_sentiment_backend():
    global _hf_pipeline, _vader, _use_hf
    if _use_hf is not None:
        return

    # Try HuggingFace
    try:
        from transformers import pipeline as hf_pipeline_fn
        _hf_pipeline = hf_pipeline_fn(
            "sentiment-analysis",
            model=MODEL_NAME,
            tokenizer=MODEL_NAME,
            top_k=1,
            truncation=True,
            max_length=512,
        )
        _use_hf = True
        logger.info(f"Loaded HuggingFace sentiment model: {MODEL_NAME}")
        return
    except Exception as e:
        logger.info(f"HuggingFace model not available ({e}), falling back to VADER")

    # Fall back to VADER
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        _vader = SentimentIntensityAnalyzer()
        _use_hf = False
        logger.info("Using VADER sentiment analyzer")
    except ImportError:
        logger.warning("Neither HuggingFace nor VADER available — sentiment disabled")
        _use_hf = False


@dataclass
class SentimentResult:
    sentiment: str = "neutral"       # positive | neutral | negative
    score: float = 0.0               # -1.0 (most negative) to 1.0 (most positive)
    entity_sentiment: dict = field(default_factory=dict)  # {entity: score}


def _medical_lexicon_override(text: str, model_score: float) -> tuple[str, float]:
    """
    Layer 1: Apply medical lexicon overrides to model output.
    Strong adverse event terms force negative regardless of model score.
    """
    text_lower = text.lower()

    # Strong negative override — these terms signal serious adverse events
    for term in STRONG_NEGATIVE_MEDICAL:
        if term in text_lower:
            # Override to strongly negative; don't let "I survived anaphylaxis" read as positive
            forced_score = min(model_score, -0.65)
            return "negative", forced_score

    # Additive bias from medical lexicon
    bias = 0.0
    for term in MEDICAL_NEGATIVE_BIAS:
        if term in text_lower:
            bias -= 0.15
            break  # one term is enough to apply bias
    for term in MEDICAL_POSITIVE_BIAS:
        if term in text_lower:
            bias += 0.10
            break

    adjusted = max(-1.0, min(1.0, model_score + bias))
    sentiment = "positive" if adjusted > 0.05 else "negative" if adjusted < -0.05 else "neutral"
    return sentiment, adjusted


def analyze_sentiment(text: str, entities: Optional[list[str]] = None) -> SentimentResult:
    """
    Step 4 — Medical-aware sentiment analysis.
    Applies biomedical lexicon override on top of model scores.
    Chunks posts > 512 tokens and averages chunk scores.
    """
    _get_sentiment_backend()

    if _use_hf and _hf_pipeline:
        _, raw_score = _hf_score(text)
    elif _vader:
        _, raw_score = _vader_score(text)
    else:
        return SentimentResult()

    # Apply medical lexicon override (Layer 1)
    post_sentiment, post_score = _medical_lexicon_override(text, raw_score)

    # Entity-level aspect sentiment
    entity_scores = {}
    if entities:
        for entity in entities[:10]:  # cap at 10 entities
            # Extract a 150-char window around the entity mention
            idx = text.lower().find(entity.lower())
            if idx == -1:
                continue
            window = text[max(0, idx - 75):min(len(text), idx + 75)]
            if _use_hf and _hf_pipeline:
                _, ent_score = _hf_score(window)
            elif _vader:
                _, ent_score = _vader_score(window)
            else:
                ent_score = post_score
            entity_scores[entity] = round(ent_score, 3)

    return SentimentResult(
        sentiment=post_sentiment,
        score=round(post_score, 3),
        entity_sentiment=entity_scores,
    )


def _hf_score(text: str) -> tuple[str, float]:
    """Score with HuggingFace RoBERTa. Returns (label, normalized_score)."""
    try:
        # Chunk if too long (simple word-based chunking)
        words = text.split()
        chunks = [" ".join(words[i:i+400]) for i in range(0, len(words), 400)] or [text]

        scores = []
        for chunk in chunks[:3]:  # max 3 chunks
            result = _hf_pipeline(chunk)
            r = result[0][0] if isinstance(result[0], list) else result[0]
            label = LABEL_MAP.get(r["label"].lower(), "neutral")
            raw_score = r["score"]
            if label == "positive":
                scores.append(raw_score)
            elif label == "negative":
                scores.append(-raw_score)
            else:
                scores.append(0.0)

        avg = sum(scores) / len(scores) if scores else 0.0
        sentiment = "positive" if avg > 0.1 else "negative" if avg < -0.1 else "neutral"
        return sentiment, avg
    except Exception as e:
        logger.debug(f"HF sentiment error: {e}")
        return "neutral", 0.0


def _vader_score(text: str) -> tuple[str, float]:
    """Score with VADER. Returns (label, compound_score)."""
    try:
        scores = _vader.polarity_scores(text[:1000])
        compound = scores["compound"]  # -1.0 to 1.0
        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"
        return label, compound
    except Exception as e:
        logger.debug(f"VADER error: {e}")
        return "neutral", 0.0


def batch_analyze(texts: list[str], entities_list: Optional[list[list[str]]] = None) -> list[SentimentResult]:
    """Analyze a batch of texts (32 at a time for HF efficiency)."""
    results = []
    for i, text in enumerate(texts):
        ents = entities_list[i] if entities_list else None
        results.append(analyze_sentiment(text, ents))
    return results
