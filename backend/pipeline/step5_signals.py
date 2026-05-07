"""
Step 5 — Safety signal detection.

Design principle (from PRD §1.3): No LLM in the hot path.
This step is deterministic and fast.

Two-pass approach:
  Pass 1 — entity-driven:  classify severity of symptoms already extracted
            by step3 NER (scispaCy).  Since the NER handles word variations
            ("nauseated" → symptom "nausea"), this pass is variation-tolerant
            without any fuzzy matching.
  Pass 2 — text-scan:      regex scan of cleaned text catches severity terms
            the NER missed (informal language, multi-word phrases).

Causality scoring uses regex patterns on the cleaned text (sentence-level).
MedDRA annotation via the stub in pipeline/meddra_stub.py.
"""
import re
import logging
from dataclasses import dataclass, field

from pipeline.meddra_stub import annotate_signals_with_meddra
from knowledge.openfda import is_known_side_effect

logger = logging.getLogger(__name__)

# ── Severity tiers ─────────────────────────────────────────────────────────────
# These cover both entity-pass lookup AND text-scan pass.
# Organized by canonical term → severity so both passes share one structure.

HIGH_TERMS = {
    "anaphylaxis", "anaphylactic", "anaphylactic shock",
    "seizure", "seizures", "convulsion", "convulsions",
    "cardiac arrest", "heart attack", "myocardial infarction",
    "stroke", "pulmonary embolism", "blood clot", "dvt",
    "hospitalized", "hospitalised", "hospitalization", "hospitalisation",
    "emergency room", "er visit", "went to er", "went to the er",
    "intensive care", "icu", "life-threatening", "life threatening",
    "pancreatitis",
    "thyroid cancer", "medullary thyroid carcinoma", "medullary thyroid",
    "kidney failure", "renal failure", "acute kidney injury",
    "liver failure", "hepatic failure",
    "death", "fatal", "died", "passed away",
    "suicidal", "suicidal ideation", "suicide attempt", "self harm", "self-harm",
    "gallbladder surgery", "cholecystectomy",
    "severe hypoglycemia", "hypoglycemic coma", "diabetic coma",
    "respiratory failure", "stopped breathing",
    "sepsis", "septic shock",
    "angioedema",
}

MED_TERMS = {
    "discontinued", "stopped taking", "had to stop", "quit taking",
    "stopped the medication", "stopped the drug", "stopped treatment",
    "adverse reaction", "adverse event", "serious side effect",
    "allergic reaction", "allergic", "allergy", "allergic to",
    "gallstones", "gallbladder", "cholecystitis",
    "hair loss", "alopecia", "hair thinning",
    "severe nausea", "severe vomiting", "uncontrollable vomiting",
    "kidney problem", "kidney issue", "kidney damage",
    "vision loss", "blurred vision", "vision problem",
    "numbness", "tingling", "peripheral neuropathy",
    "hypoglycemia", "low blood sugar", "blood sugar crash",
    "injection site reaction", "injection site infection",
    "chest pain", "chest tightness",
    "shortness of breath", "difficulty breathing",
    "severe rash", "hives", "urticaria",
    "fainting", "passed out", "syncope",
    "severe headache", "worst headache",
    "severe fatigue", "extreme fatigue",
    "muscle weakness", "severe muscle pain", "rhabdomyolysis",
}

LOW_TERMS = {
    "nausea", "nauseous", "nauseated",
    "vomiting", "vomited", "threw up",
    "diarrhea", "diarrhoea",
    "constipation", "constipated",
    "headache", "migraine",
    "dizziness", "dizzy", "lightheaded", "light headed",
    "fatigue", "tired", "exhausted", "lethargy",
    "rash", "itching", "itchy",
    "dry mouth",
    "bloating", "bloated", "gas", "gassy", "belching", "burping",
    "stomach pain", "abdominal pain", "stomach cramps", "stomach ache",
    "insomnia", "sleep problem", "can't sleep",
    "muscle pain", "muscle ache", "myalgia", "joint pain",
    "sweating", "hot flash", "hot flush",
    "mood swing", "mood change", "irritable",
    "weight change", "appetite loss", "loss of appetite",
    "heartburn", "acid reflux", "indigestion",
    "back pain",
    "bruising", "easy bruising",
}

# Build fast lookup: term → severity
_SEVERITY_MAP: dict[str, str] = {}
for _t in HIGH_TERMS: _SEVERITY_MAP[_t] = "HIGH"
for _t in MED_TERMS:  _SEVERITY_MAP[_t] = "MED"
for _t in LOW_TERMS:  _SEVERITY_MAP[_t] = "LOW"

_SEVERITY_ORDER = {"HIGH": 0, "MED": 1, "LOW": 2}

# ── Text-scan regex (Pass 2) ───────────────────────────────────────────────────
# Compiled from all severity terms; longest-first so multi-word phrases win.
def _build_scan_pattern(term_set: set[str]) -> re.Pattern:
    terms = sorted(term_set, key=len, reverse=True)
    return re.compile(
        r"(?<!\w)(" + "|".join(re.escape(t) for t in terms) + r")(?!\w)",
        re.IGNORECASE,
    )

_HIGH_RE = _build_scan_pattern(HIGH_TERMS)
_MED_RE  = _build_scan_pattern(MED_TERMS)
_LOW_RE  = _build_scan_pattern(LOW_TERMS)

# ── Causality patterns ─────────────────────────────────────────────────────────
# Sentence-level patterns; these require text-level context, not entity-level.
_CAUSALITY_PATTERNS = [
    (r"\bafter\s+(taking|starting|using|beginning)\b", 0.75),
    (r"\bsince\s+(starting|taking|beginning|using)\b", 0.75),
    (r"\bcaused\s+by\b", 0.85),
    (r"\bdue\s+to\b", 0.65),
    (r"\bfrom\s+(taking|using|starting)\b", 0.70),
    (r"\bbecause\s+of\b", 0.65),
    (r"\bstarted\s+(when|after)\b", 0.65),
    (r"\bbegan\s+(when|after|once)\b", 0.65),
    (r"\brelated\s+to\b", 0.55),
    (r"\bthink\s+it.?s\s+the\b", 0.50),
    (r"\bblame\s+the\b", 0.55),
    (r"\breaction\s+to\b", 0.70),
    (r"\bside\s+effect\s+of\b", 0.80),
    (r"\bstop(ped)?\s+(taking|using|the)\b", 0.60),
    (r"\bwithdrew?\s+from\b", 0.65),
    (r"\bwent\s+to\s+(the\s+)?(er|emergency|hospital)\b", 0.75),
]
_CAUSALITY_RES = [(re.compile(p, re.IGNORECASE), w) for p, w in _CAUSALITY_PATTERNS]

# ── Negation window ────────────────────────────────────────────────────────────
_NEGATION_RE = re.compile(
    r"\b(no|not|never|without|deny|denies|denying|absence of|"
    r"negative for|ruled out|didn.?t|doesn.?t|haven.?t|hasn.?t|"
    r"don.?t|won.?t|wasn.?t|aren.?t|isn.?t)\b",
    re.IGNORECASE,
)

def _is_negated(text: str, match_start: int, window: int = 60) -> bool:
    context = text[max(0, match_start - window):match_start]
    return bool(_NEGATION_RE.search(context))


@dataclass
class SignalResult:
    has_safety_signal: bool = False
    severity: str | None = None          # HIGH | MED | LOW
    signals: list = field(default_factory=list)
    causality: str | None = None         # definite | probable | possible | unlikely
    meddra_terms: list = field(default_factory=list)


def detect_signals(
    text: str,
    drugs: list[str],
    symptoms: list[str],
    project_keywords: list[str] | None = None,
) -> SignalResult:
    """
    Step 5 — Detect safety signals.

    Pass 1: classify each symptom from step3 NER output against severity tiers.
            This is variation-tolerant because scispaCy en_core_sci_md already
            normalised "nauseated" → "nausea", "went to ER" → entity, etc.

    Pass 2: regex scan of cleaned text for severity terms the NER may have missed
            (informal phrasing, negation-escaped terms, MED/HIGH multi-word phrases).

    Causality: sentence-level regex on cleaned text (always).
    """
    result = SignalResult()
    text_lower = text.lower()
    detected: list[dict] = []

    # ── Pass 1: entity-driven (primary, variation-tolerant) ──────────────────
    for sym in symptoms:
        sym_lower = sym.lower().strip()
        sev = _SEVERITY_MAP.get(sym_lower)
        if not sev:
            # Try prefix match for compound terms (e.g. "severe nausea" when entity is "nausea")
            for term, s in _SEVERITY_MAP.items():
                if sym_lower in term or term in sym_lower:
                    sev = s
                    break
        if not sev:
            continue

        # Check the entity isn't negated in context
        idx = text_lower.find(sym_lower)
        if idx >= 0 and _is_negated(text_lower, idx):
            continue

        associated_drug = _find_nearest_drug(text_lower, idx if idx >= 0 else 0, drugs)
        context = _extract_context(text, idx if idx >= 0 else 0, sym_lower)
        known, fda_excerpt = is_known_side_effect(associated_drug or "", sym_lower)

        detected.append({
            "drug": associated_drug or (drugs[0] if drugs else "unknown"),
            "symptom": sym_lower,
            "severity": sev,
            "context_window": context,
            "confidence": _compute_confidence(text_lower, sev),
            "known_to_fda": known,
            "fda_excerpt": fda_excerpt,
            "source": "ner",
        })

    # ── Pass 2: text scan (catches what NER missed) ───────────────────────────
    # Only runs on HIGH and MED terms (higher stakes; LOW from NER is enough).
    ner_found_symptoms = {s.lower() for s in symptoms}

    for scan_re, sev in [(_HIGH_RE, "HIGH"), (_MED_RE, "MED"), (_LOW_RE, "LOW")]:
        for m in scan_re.finditer(text_lower):
            term = m.group(0).lower()
            if term in ner_found_symptoms:
                continue  # already captured in Pass 1
            if _is_negated(text_lower, m.start()):
                continue

            associated_drug = _find_nearest_drug(text_lower, m.start(), drugs)
            context = _extract_context(text, m.start(), term)
            known, fda_excerpt = is_known_side_effect(associated_drug or "", term)

            detected.append({
                "drug": associated_drug or (drugs[0] if drugs else "unknown"),
                "symptom": term,
                "severity": sev,
                "context_window": context,
                "confidence": _compute_confidence(text_lower, sev),
                "known_to_fda": known,
                "fda_excerpt": fda_excerpt,
                "source": "text_scan",
            })

    if not detected:
        return result

    # ── Deduplicate by (drug, symptom) keeping highest severity ──────────────
    seen: dict[tuple, dict] = {}
    for sig in detected:
        key = (sig["drug"], sig["symptom"])
        if key not in seen or _SEVERITY_ORDER[sig["severity"]] < _SEVERITY_ORDER[seen[key]["severity"]]:
            seen[key] = sig
    unique = sorted(seen.values(), key=lambda x: _SEVERITY_ORDER[x["severity"]])

    # ── Causality scoring ─────────────────────────────────────────────────────
    causality_score = _score_causality(text_lower)
    causality_label = _causality_label(causality_score)

    # Update confidence with causality bonus
    for sig in unique:
        bonus = min(0.12, causality_score * 0.15)
        sig["confidence"] = round(min(0.99, sig["confidence"] + bonus), 3)

    # ── MedDRA annotation ─────────────────────────────────────────────────────
    annotate_signals_with_meddra(unique)
    meddra_terms = [
        {"term": s["meddra_term"], "code": s["meddra_code"]}
        for s in unique if s.get("meddra_term")
    ]

    result.has_safety_signal = True
    result.severity = unique[0]["severity"]   # highest severity first
    result.signals = unique
    result.causality = causality_label
    result.meddra_terms = meddra_terms
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_context(text: str, pos: int, term: str) -> str:
    start = max(0, pos - 30)
    end = min(len(text), pos + len(term) + 30)
    return text[start:end].strip()


def _find_nearest_drug(text_lower: str, pos: int, drugs: list[str]) -> str | None:
    best, best_dist = None, float("inf")
    for drug in drugs:
        idx = text_lower.find(drug.lower())
        if idx == -1:
            continue
        dist = abs(idx - pos)
        if dist < best_dist:
            best_dist = dist
            best = drug
    return best


def _compute_confidence(text_lower: str, severity: str) -> float:
    base = {"HIGH": 0.82, "MED": 0.68, "LOW": 0.52}[severity]
    length_bonus = min(0.03, len(text_lower) / 10000)
    return round(min(0.96, base + length_bonus), 3)


def _score_causality(text_lower: str) -> float:
    score = 0.0
    for pattern, weight in _CAUSALITY_RES:
        if pattern.search(text_lower):
            score = max(score, weight)
    return score


def _causality_label(score: float) -> str:
    if score >= 0.80:   return "definite"
    elif score >= 0.65: return "probable"
    elif score >= 0.50: return "possible"
    else:               return "unlikely"
