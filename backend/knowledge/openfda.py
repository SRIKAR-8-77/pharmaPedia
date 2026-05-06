"""
OpenFDA drug label lookup — free, no auth, official FDA data.

Core pharmacovigilance insight: distinguish KNOWN adverse effects (already in the
FDA-approved label) from NOVEL signals (not yet disclosed) — novel HIGH signals
warrant regulatory escalation.
"""
import logging
import re
import httpx

logger = logging.getLogger(__name__)

_LABEL_BASE = "https://api.fda.gov/drug/label.json"
_cache: dict[str, dict] = {}  # drug_name → parsed label sections


def _parse_label(result: dict) -> dict:
    openfda = result.get("openfda", {})
    return {
        "brand_name": (openfda.get("brand_name") or [None])[0],
        "generic_name": (openfda.get("generic_name") or [None])[0],
        "adverse_reactions": " ".join(result.get("adverse_reactions", [])),
        "warnings_and_cautions": " ".join(result.get("warnings_and_cautions", [])),
        "boxed_warning": " ".join(result.get("boxed_warning", [])),
        "warnings": " ".join(result.get("warnings", [])),
        "indications_and_usage": " ".join(result.get("indications_and_usage", [])),
    }


def fetch_label(drug_name: str, timeout: float = 4.0) -> dict:
    """
    Fetch FDA drug label. Returns parsed sections dict or {}.
    Tries brand_name first, then generic_name search.
    Safe to call from pipeline (sync context).
    """
    key = drug_name.lower().strip()
    if key in _cache:
        return _cache[key]

    try:
        with httpx.Client(timeout=timeout, verify=False) as client:
            for field in ["openfda.brand_name", "openfda.generic_name"]:
                r = client.get(
                    _LABEL_BASE,
                    params={"search": f'{field}:"{drug_name}"', "limit": 1},
                )
                if r.status_code == 200:
                    results = r.json().get("results", [])
                    if results:
                        parsed = _parse_label(results[0])
                        _cache[key] = parsed
                        logger.debug(f"OpenFDA label fetched for '{drug_name}'")
                        return parsed

    except Exception as e:
        logger.debug(f"OpenFDA label fetch failed for '{drug_name}': {e}")

    _cache[key] = {}
    return {}


async def fetch_label_async(drug_name: str) -> dict:
    """Async version for API route handlers."""
    key = drug_name.lower().strip()
    if key in _cache:
        return _cache[key]

    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            for field in ["openfda.brand_name", "openfda.generic_name"]:
                r = await client.get(
                    _LABEL_BASE,
                    params={"search": f'{field}:"{drug_name}"', "limit": 1},
                )
                if r.status_code == 200:
                    results = r.json().get("results", [])
                    if results:
                        parsed = _parse_label(results[0])
                        _cache[key] = parsed
                        return parsed

    except Exception as e:
        logger.debug(f"OpenFDA async fetch failed for '{drug_name}': {e}")

    _cache[key] = {}
    return {}


def is_known_side_effect(drug_name: str, symptom: str) -> tuple[bool, str]:
    """
    Check whether symptom appears in the FDA-approved label's adverse reactions section.

    Returns (known: bool, excerpt: str).
    known=True  → manufacturer already disclosed this effect — lower novelty priority.
    known=False → potential NOVEL signal — higher regulatory interest.
    """
    label = fetch_label(drug_name)
    if not label:
        return False, ""

    search_text = (
        label.get("adverse_reactions", "") + " " +
        label.get("warnings_and_cautions", "") + " " +
        label.get("warnings", "")
    ).lower()

    symptom_lower = symptom.lower()

    if symptom_lower in search_text:
        idx = search_text.find(symptom_lower)
        start = max(0, idx - 80)
        end = min(len(search_text), idx + len(symptom_lower) + 80)
        excerpt = re.sub(r"\s+", " ", search_text[start:end]).strip()
        return True, excerpt

    # Also try partial word match for multi-word symptoms (e.g. "severe nausea" → "nausea")
    first_word = symptom_lower.split()[0] if " " in symptom_lower else None
    if first_word and len(first_word) > 4 and first_word in search_text:
        idx = search_text.find(first_word)
        start = max(0, idx - 80)
        end = min(len(search_text), idx + len(first_word) + 80)
        excerpt = re.sub(r"\s+", " ", search_text[start:end]).strip()
        return True, excerpt

    return False, ""
