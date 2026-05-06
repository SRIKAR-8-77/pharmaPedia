import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# PII entity types — exclude DATE_TIME (too many FPs on dosing schedules/durations)
# and LOCATION (generic place names are not PII in this context)
PII_ENTITY_TYPES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
    "MEDICAL_LICENSE", "US_SSN", "IP_ADDRESS",
]

# Lazy-loaded Presidio instances
_analyzer = None
_anonymizer = None


def _get_presidio():
    global _analyzer, _anonymizer
    if _analyzer is None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider

            # Use en_core_web_sm (already installed) — default would pull en_core_web_lg
            nlp_engine = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            }).create_engine()
            _analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
            _anonymizer = AnonymizerEngine()
        except Exception as e:
            logger.warning(f"Presidio not available: {e}. PII detection disabled.")
            _analyzer = False
            _anonymizer = False
    return _analyzer, _anonymizer


@dataclass
class PIIResult:
    has_pii: bool = False
    pii_types: list = field(default_factory=list)
    pii_spans: list = field(default_factory=list)
    redacted_text: Optional[str] = None
    original_text: str = ""


def detect_pii(text: str) -> PIIResult:
    """
    Step 2 — Detect and redact PII using Microsoft Presidio.
    Posts with PII above confidence 0.75 are held for human review.
    """
    result = PIIResult(original_text=text)
    analyzer, anonymizer = _get_presidio()

    if not analyzer:
        return result

    try:
        analysis_results = analyzer.analyze(
            text=text,
            language="en",
            entities=PII_ENTITY_TYPES,
            score_threshold=0.75,
        )

        if not analysis_results:
            return result

        result.has_pii = True
        result.pii_types = list({r.entity_type for r in analysis_results})
        result.pii_spans = [
            {
                "start": r.start,
                "end": r.end,
                "type": r.entity_type,
                "text": text[r.start:r.end],
                "score": round(r.score, 3),
            }
            for r in analysis_results
        ]

        # Redact with placeholder tokens
        anonymized = anonymizer.anonymize(text=text, analyzer_results=analysis_results)
        result.redacted_text = anonymized.text

    except Exception as e:
        logger.error(f"PII detection error: {e}")

    return result
