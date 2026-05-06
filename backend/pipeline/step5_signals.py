"""
Step 5 — Safety signal detection.
Classifies signals HIGH/MED/LOW, extracts context windows, scores causality,
and applies MedDRA stub normalization.
"""
import re
import logging
from dataclasses import dataclass, field

from pipeline.meddra_stub import annotate_signals_with_meddra
from knowledge.openfda import is_known_side_effect

logger = logging.getLogger(__name__)

# ─── Severity keyword sets ─────────────────────────────────────────────────────
HIGH_KEYWORDS = {
    "anaphylaxis", "anaphylactic", "anaphylactic shock",
    "seizure", "convulsion", "convulsions",
    "cardiac arrest", "heart attack", "myocardial infarction",
    "stroke", "pulmonary embolism",
    "hospitalized", "hospitalization", "emergency room", "er visit",
    "intensive care", "icu", "life-threatening",
    "pancreatitis",
    "thyroid cancer", "medullary thyroid carcinoma",
    "kidney failure", "renal failure", "acute kidney injury",
    "death", "fatal", "died",
    "suicidal", "suicide attempt",
    "gallbladder surgery", "cholecystectomy",
    "severe hypoglycemia", "hypoglycemic coma",
}

MED_KEYWORDS = {
    "discontinued", "stopped taking", "had to stop", "quit taking",
    "adverse reaction", "adverse event",
    "allergic reaction", "allergic", "allergy",
    "pancreatitis", "gallstones", "gallbladder",
    "hair loss", "alopecia",
    "severe nausea", "severe vomiting",
    "kidney problem", "kidney issue",
    "hypoglycemia", "low blood sugar",
    "vision loss", "blurred vision",
    "numbness", "tingling",
    "injection site reaction", "injection site",
}

LOW_KEYWORDS = {
    "nausea", "vomiting", "diarrhea", "constipation",
    "headache", "migraine",
    "dizziness", "lightheaded",
    "fatigue", "tired", "exhausted",
    "rash", "itching", "hives",
    "dry mouth", "bloating", "gas", "belching", "burping",
    "stomach pain", "abdominal pain",
    "insomnia", "sleep",
    "muscle pain", "myalgia",
    "sweating", "hot flash",
    "mood swing", "mood change",
    "weight change", "appetite",
}

# Causality signal patterns
CAUSALITY_PATTERNS = [
    (r"\bafter\s+taking\b", 0.7),
    (r"\bsince\s+(starting|taking|beginning)\b", 0.7),
    (r"\bcaused\s+by\b", 0.8),
    (r"\bdue\s+to\b", 0.6),
    (r"\bfrom\s+taking\b", 0.7),
    (r"\bbecause\s+of\b", 0.6),
    (r"\bstarted\s+(when|after)\b", 0.65),
    (r"\bbegan\s+(when|after)\b", 0.65),
    (r"\brelated\s+to\b", 0.55),
    (r"\bthink\s+it.?s\s+the\b", 0.5),
    (r"\bblame\s+the\b", 0.5),
]

_CAUSALITY_RES = [(re.compile(p, re.IGNORECASE), w) for p, w in CAUSALITY_PATTERNS]


@dataclass
class SignalResult:
    has_safety_signal: bool = False
    severity: str | None = None          # HIGH | MED | LOW
    signals: list = field(default_factory=list)
    causality: str | None = None         # definite | probable | possible | unlikely
    meddra_terms: list = field(default_factory=list)


def detect_signals(text: str, drugs: list[str], symptoms: list[str]) -> SignalResult:
    """
    Step 5 — Detect safety signals in cleaned post text.
    Cross-references detected drugs with symptom severity keywords.
    """
    result = SignalResult()
    text_lower = text.lower()

    # Find all symptom-level signals present in text
    detected_signals = []

    for kw_set, sev in [(HIGH_KEYWORDS, "HIGH"), (MED_KEYWORDS, "MED"), (LOW_KEYWORDS, "LOW")]:
        for kw in kw_set:
            if kw in text_lower:
                # Extract 50-char context window
                idx = text_lower.find(kw)
                context_start = max(0, idx - 25)
                context_end = min(len(text), idx + len(kw) + 25)
                context = text[context_start:context_end].strip()

                # Find associated drug (closest drug mention)
                associated_drug = _find_nearest_drug(text_lower, idx, drugs) or \
                                  (drugs[0] if drugs else "unknown")

                known_to_fda, fda_excerpt = is_known_side_effect(associated_drug, kw)
                detected_signals.append({
                    "drug": associated_drug,
                    "symptom": kw,
                    "severity": sev,
                    "context_window": context,
                    "confidence": _compute_confidence(text_lower, kw, sev),
                    "known_to_fda": known_to_fda,
                    "fda_excerpt": fda_excerpt,
                })

    if not detected_signals:
        return result

    # Deduplicate by (drug, symptom)
    seen = set()
    unique_signals = []
    for s in detected_signals:
        key = (s["drug"], s["symptom"])
        if key not in seen:
            seen.add(key)
            unique_signals.append(s)

    # Take highest severity
    severity_order = {"HIGH": 0, "MED": 1, "LOW": 2}
    unique_signals.sort(key=lambda x: severity_order[x["severity"]])
    top_severity = unique_signals[0]["severity"]

    # Causality scoring
    causality_score = _score_causality(text_lower)
    causality_label = _causality_label(causality_score)

    # MedDRA annotation
    annotate_signals_with_meddra(unique_signals)
    meddra_terms = [
        {"term": s["meddra_term"], "code": s["meddra_code"]}
        for s in unique_signals if s.get("meddra_term")
    ]

    result.has_safety_signal = True
    result.severity = top_severity
    result.signals = unique_signals
    result.causality = causality_label
    result.meddra_terms = meddra_terms
    return result


def _find_nearest_drug(text_lower: str, pos: int, drugs: list[str]) -> str | None:
    """Find the drug mentioned closest to position pos."""
    best_drug = None
    best_dist = float("inf")
    for drug in drugs:
        idx = text_lower.find(drug.lower())
        if idx == -1:
            continue
        dist = abs(idx - pos)
        if dist < best_dist:
            best_dist = dist
            best_drug = drug
    return best_drug


def _compute_confidence(text_lower: str, keyword: str, severity: str) -> float:
    """Heuristic confidence: base severity weight + causality signal bonus."""
    base = {"HIGH": 0.85, "MED": 0.70, "LOW": 0.55}[severity]
    causality_bonus = min(0.12, _score_causality(text_lower) * 0.15)
    # Length bonus — longer posts with more context are more reliable
    length_bonus = min(0.03, len(text_lower) / 10000)
    return round(min(0.99, base + causality_bonus + length_bonus), 3)


def _score_causality(text_lower: str) -> float:
    """Score how strongly causal language appears. 0.0–1.0."""
    score = 0.0
    for pattern, weight in _CAUSALITY_RES:
        if pattern.search(text_lower):
            score = max(score, weight)
    return score


def _causality_label(score: float) -> str:
    if score >= 0.75:
        return "definite"
    elif score >= 0.60:
        return "probable"
    elif score >= 0.45:
        return "possible"
    else:
        return "unlikely"
