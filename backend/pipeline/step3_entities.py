"""
Step 3 — Entity extraction.

Fully open NER: no hardcoded drug or condition lists.
Primary: scispaCy en_core_sci_md — extracts drugs (CHEMICAL/SIMPLE_CHEMICAL),
         diseases/conditions (DISEASE), and findings/symptoms (SIGN_OR_SYMPTOM).
Project keywords: each project supplies its own monitored terms (drugs, diseases,
         generic names, conditions). These are matched directly and classified by
         NER label when possible, added to conditions otherwise.
Symptom patterns: a general adverse-event vocabulary catches patient-voice symptom
         language that NER models tend to miss in informal text.
RxNorm: brand→generic normalization when recognized drug names appear.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ─── General adverse-event symptom vocabulary ─────────────────────────────────
# These are OUTCOMES we measure — universal across any project focus area.
# Not drug-specific; kept here to catch informal patient-voice AE language.
SYMPTOM_LIST = [
    # HIGH severity AEs
    "anaphylaxis", "anaphylactic", "anaphylactic shock",
    "seizure", "seizures", "convulsion", "convulsions",
    "cardiac arrest", "heart attack", "myocardial infarction",
    "stroke", "blood clot", "pulmonary embolism", "dvt",
    "hospitalized", "hospitalization", "emergency room", "er visit", "icu",
    "pancreatitis",
    "thyroid cancer", "medullary thyroid",
    "gallbladder", "cholecystitis", "gallstones",
    "kidney failure", "renal failure", "acute kidney injury",
    "hypoglycemia", "low blood sugar", "blood sugar crash",
    # MED severity AEs
    "nausea", "vomiting", "diarrhea", "constipation",
    "stomach pain", "abdominal pain", "cramping",
    "fatigue", "exhaustion", "tired", "weakness",
    "dizziness", "lightheaded", "vertigo",
    "headache", "migraine",
    "rash", "hives", "urticaria", "itching", "pruritus",
    "hair loss", "alopecia",
    "acid reflux", "gerd", "heartburn", "indigestion",
    "discontinued", "stopped taking", "stopped medication",
    "adverse reaction", "adverse event", "side effect",
    "allergic reaction", "allergic",
    "weight loss", "appetite loss",
    # LOW severity AEs
    "dry mouth", "burping", "bloating", "gas",
    "insomnia", "sleep problems",
    "mood changes", "depression", "anxiety",
    "muscle pain", "myalgia",
    "sweating", "hot flashes", "flushing",
    "vision changes", "blurred vision",
    # Patient-voice experience language
    "injection site", "injection pain", "needle pain",
    "not working", "stopped working", "doesn't work",
    "feeling sick", "feeling worse", "feel awful",
]

# RxNorm brand→generic normalization — applied after NER finds drug names
RXNORM_MAP = {
    "ozempic": "semaglutide",
    "wegovy": "semaglutide",
    "rybelsus": "semaglutide",
    "mounjaro": "tirzepatide",
    "zepbound": "tirzepatide",
    "victoza": "liraglutide",
    "saxenda": "liraglutide",
    "trulicity": "dulaglutide",
    "jardiance": "empagliflozin",
    "farxiga": "dapagliflozin",
    "invokana": "canagliflozin",
    "januvia": "sitagliptin",
    "tradjenta": "linagliptin",
    "glucophage": "metformin",
    "lantus": "insulin glargine",
    "basaglar": "insulin glargine",
    "novolog": "insulin aspart",
    "humalog": "insulin lispro",
    "levemir": "insulin detemir",
    "lipitor": "atorvastatin",
    "actos": "pioglitazone",
    "amaryl": "glimepiride",
}

# Negation context — word-boundary regex against a 50-char look-behind window
_NEGATION_RE = re.compile(
    r"\b(no|not|never|without|denies|deny|absent|free from|negative for)\b",
    re.IGNORECASE,
)

# Compiled patterns
def _build_pattern(terms: list[str]) -> re.Pattern:
    sorted_terms = sorted(terms, key=len, reverse=True)
    escaped = [re.escape(t) for t in sorted_terms]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)

_SYMPTOM_RE = _build_pattern(SYMPTOM_LIST)
_DOSE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|ml|mcg|iu|units?)\b", re.IGNORECASE)

# Lazy-loaded scispaCy NLP
_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            try:
                _nlp = spacy.load("en_core_sci_md")
                logger.info("Loaded scispaCy en_core_sci_md")
            except OSError:
                try:
                    _nlp = spacy.load("en_core_web_sm")
                    logger.info("Loaded spaCy en_core_web_sm (fallback — limited biomedical NER)")
                except OSError:
                    logger.warning("No spaCy model available — keyword-only entity extraction")
                    _nlp = False
        except ImportError:
            logger.warning("spaCy not installed — keyword-only entity extraction")
            _nlp = False
    return _nlp


def _is_negated(text: str, match_start: int) -> bool:
    window = text[max(0, match_start - 50):match_start]
    return bool(_NEGATION_RE.search(window))


@dataclass
class EntityResult:
    drugs: list = field(default_factory=list)
    symptoms: list = field(default_factory=list)
    conditions: list = field(default_factory=list)
    dosages: list = field(default_factory=list)
    negated_entities: dict = field(default_factory=lambda: {"drugs": [], "symptoms": [], "conditions": []})


def extract_entities(text: str, project_keywords: Optional[list[str]] = None) -> EntityResult:
    """
    Step 3 — Extract biomedical entities from cleaned text.

    Uses fully open NER (scispaCy) to extract drugs, diseases, and symptoms
    without a hardcoded drug/condition list. Project keywords are matched
    directly as anchors for whatever the project is monitoring.
    """
    result = EntityResult()

    # 1. scispaCy NER — open extraction of all biomedical entity types
    nlp = _get_nlp()
    if nlp:
        _spacy_extract(text, nlp, result)

    # 2. Project keyword matching — catches project-specific terms the NER may miss
    if project_keywords:
        _keyword_extract(text, project_keywords, result, nlp)

    # 3. General symptom/AE pattern matching — universal adverse-event vocabulary
    _symptom_extract(text, result)

    # 4. Dosage patterns
    for m in _DOSE_RE.finditer(text):
        result.dosages.append(m.group().lower())

    # Deduplicate and normalize
    result.drugs = _dedup_normalize(result.drugs)
    result.symptoms = _dedup(result.symptoms)
    result.conditions = _dedup(result.conditions)
    result.negated_entities["drugs"] = _dedup(result.negated_entities["drugs"])
    result.negated_entities["symptoms"] = _dedup(result.negated_entities["symptoms"])

    return result


def _spacy_extract(text: str, nlp, result: EntityResult):
    """Extract all biomedical entities via scispaCy NER labels."""
    try:
        doc = nlp(text[:1500])  # cap for speed; most signal is in first ~1000 chars
        for ent in doc.ents:
            ent_text = ent.text.lower().strip()
            if len(ent_text) < 3:
                continue

            label = ent.label_

            if label in ("CHEMICAL", "SIMPLE_CHEMICAL", "DRUG"):
                if ent_text not in result.negated_entities["drugs"]:
                    result.drugs.append(ent_text)

            elif label in ("DISEASE",):
                # scispaCy tags both diseases and conditions under DISEASE
                if ent_text not in result.conditions:
                    result.conditions.append(ent_text)

            elif label in ("SIGN_OR_SYMPTOM", "FINDING"):
                if ent_text not in result.negated_entities["symptoms"]:
                    result.symptoms.append(ent_text)

    except Exception as e:
        logger.debug(f"spaCy extraction error: {e}")


def _keyword_extract(text: str, project_keywords: list[str], result: EntityResult, nlp):
    """
    Match project-defined keywords directly against the text.
    Classify each keyword as drug/condition by running its surrounding context
    through scispaCy if available; otherwise default to conditions.
    """
    text_lower = text.lower()

    # Build a one-shot pattern from all project keywords (longest first for greedy match)
    if not project_keywords:
        return
    pattern = _build_pattern(project_keywords)

    for m in pattern.finditer(text):
        kw = m.group().lower().strip()
        if len(kw) < 2:
            continue

        negated = _is_negated(text, m.start())

        # Determine entity type: check if scispaCy already classified a span at
        # this position. If not, use heuristic: RXNORM_MAP hit → drug, else condition.
        entity_type = _classify_keyword(kw, nlp, text, m.start(), m.end())

        if entity_type == "drug":
            target = result.negated_entities["drugs"] if negated else result.drugs
            target.append(kw)
        elif entity_type == "symptom":
            target = result.negated_entities["symptoms"] if negated else result.symptoms
            target.append(kw)
        else:
            # Default: treat as condition/tracked-entity
            if not negated and kw not in result.conditions:
                result.conditions.append(kw)


def _classify_keyword(kw: str, nlp, text: str, start: int, end: int) -> str:
    """
    Best-effort classification of a project keyword as drug/symptom/condition.
    Priority: RxNorm map → scispaCy span label → heuristic default (condition).
    """
    # RxNorm map is definitive for known drugs
    if kw in RXNORM_MAP or kw in RXNORM_MAP.values():
        return "drug"

    # Check scispaCy span label at this text position
    if nlp and nlp is not False:
        try:
            doc = nlp(text[max(0, start - 20):end + 20])
            for ent in doc.ents:
                if ent.label_ in ("CHEMICAL", "SIMPLE_CHEMICAL", "DRUG"):
                    return "drug"
                if ent.label_ in ("SIGN_OR_SYMPTOM", "FINDING"):
                    return "symptom"
                if ent.label_ == "DISEASE":
                    return "condition"
        except Exception:
            pass

    # Heuristic: keywords with dose-like suffixes are probably drug-related
    if re.search(r"\d+\s*mg\b", kw):
        return "drug"

    return "condition"


def _symptom_extract(text: str, result: EntityResult):
    """Match general AE symptom vocabulary against text."""
    for m in _SYMPTOM_RE.finditer(text):
        term = m.group().lower()
        if _is_negated(text, m.start()):
            if term not in result.negated_entities["symptoms"]:
                result.negated_entities["symptoms"].append(term)
        else:
            if term not in result.symptoms:
                result.symptoms.append(term)


def _dedup_normalize(terms: list[str]) -> list[str]:
    """Deduplicate and apply RxNorm brand→generic normalization."""
    seen = set()
    out = []
    for t in terms:
        normalized = RXNORM_MAP.get(t, t)
        if normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _dedup(terms: list[str]) -> list[str]:
    seen = set()
    return [t for t in terms if not (t in seen or seen.add(t))]
