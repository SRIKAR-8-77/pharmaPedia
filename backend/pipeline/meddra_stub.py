"""
MedDRA normalization stub — 20 manual mappings.
Phase 5 replaces this with FAISS embedding similarity search across all 70,000+ MedDRA LLTs.
"""

MEDDRA_MAP: dict[str, dict] = {
    "nausea":              {"term": "Nausea",                   "code": "10028813", "llt_code": "10028813"},
    "vomiting":            {"term": "Vomiting",                 "code": "10047700", "llt_code": "10047700"},
    "diarrhea":            {"term": "Diarrhoea",                "code": "10012735", "llt_code": "10012727"},
    "constipation":        {"term": "Constipation",             "code": "10010774", "llt_code": "10010774"},
    "headache":            {"term": "Headache",                 "code": "10019211", "llt_code": "10019211"},
    "dizziness":           {"term": "Dizziness",                "code": "10013573", "llt_code": "10013573"},
    "fatigue":             {"term": "Fatigue",                  "code": "10016256", "llt_code": "10016256"},
    "rash":                {"term": "Rash",                     "code": "10037844", "llt_code": "10037844"},
    "hair loss":           {"term": "Alopecia",                 "code": "10001760", "llt_code": "10001760"},
    "alopecia":            {"term": "Alopecia",                 "code": "10001760", "llt_code": "10001760"},
    "anaphylaxis":         {"term": "Anaphylactic reaction",    "code": "10002198", "llt_code": "10002198"},
    "anaphylactic":        {"term": "Anaphylactic reaction",    "code": "10002198", "llt_code": "10002198"},
    "seizure":             {"term": "Seizure",                  "code": "10039906", "llt_code": "10039906"},
    "pancreatitis":        {"term": "Pancreatitis",             "code": "10033645", "llt_code": "10033645"},
    "hypoglycemia":        {"term": "Hypoglycaemia",            "code": "10020993", "llt_code": "10020993"},
    "low blood sugar":     {"term": "Hypoglycaemia",            "code": "10020993", "llt_code": "10020993"},
    "gallstones":          {"term": "Cholelithiasis",           "code": "10008316", "llt_code": "10008316"},
    "kidney failure":      {"term": "Acute kidney injury",      "code": "10069339", "llt_code": "10069339"},
    "thyroid cancer":      {"term": "Thyroid cancer",           "code": "10066474", "llt_code": "10066474"},
    "weight loss":         {"term": "Weight decreased",         "code": "10047899", "llt_code": "10047899"},
}


def lookup_meddra(symptom: str) -> dict | None:
    """Return MedDRA term/code for a symptom, or None if not mapped."""
    return MEDDRA_MAP.get(symptom.lower().strip())


def annotate_signals_with_meddra(signals: list[dict]) -> list[dict]:
    """Add meddra_term and meddra_code to each signal dict where available."""
    for signal in signals:
        sym = signal.get("symptom", "").lower()
        mapping = lookup_meddra(sym)
        if mapping:
            signal["meddra_term"] = mapping["term"]
            signal["meddra_code"] = mapping["code"]
        else:
            signal["meddra_term"] = None
            signal["meddra_code"] = None
    return signals
