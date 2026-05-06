"""
RxNorm drug normalization — NIH API (free, no auth, no rate limit).

Extends the static RXNORM_MAP in step3_entities.py with live lookups for drugs
not in the hardcoded list. Results are cached in-memory for the process lifetime.
"""
import logging
import httpx

logger = logging.getLogger(__name__)

_RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"
_cache: dict[str, dict] = {}  # normalised drug_name → result dict


def lookup(drug_name: str, timeout: float = 3.0) -> dict:
    """
    Synchronous RxNorm lookup. Returns dict with keys:
      cui, canonical_name, synonyms  — or {} on failure.

    Safe to call from pipeline (sync context).
    """
    key = drug_name.lower().strip()
    if key in _cache:
        return _cache[key]

    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{_RXNAV_BASE}/rxcui.json", params={"name": key, "search": 1})
            r.raise_for_status()
            cui_list = r.json().get("idGroup", {}).get("rxnormId", [])
            if not cui_list:
                _cache[key] = {}
                return {}

            cui = cui_list[0]

            r2 = client.get(f"{_RXNAV_BASE}/rxcui/{cui}/properties.json")
            r2.raise_for_status()
            props = r2.json().get("properties", {})
            canonical = props.get("name", drug_name)

            result = {"cui": cui, "canonical_name": canonical}
            _cache[key] = result
            logger.debug(f"RxNorm: {drug_name} → {canonical} (CUI {cui})")
            return result

    except Exception as e:
        logger.debug(f"RxNorm lookup failed for '{drug_name}': {e}")
        _cache[key] = {}
        return {}


async def lookup_async(drug_name: str) -> dict:
    """Async version for API route handlers."""
    key = drug_name.lower().strip()
    if key in _cache:
        return _cache[key]

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(f"{_RXNAV_BASE}/rxcui.json", params={"name": key, "search": 1})
            r.raise_for_status()
            cui_list = r.json().get("idGroup", {}).get("rxnormId", [])
            if not cui_list:
                _cache[key] = {}
                return {}

            cui = cui_list[0]
            r2 = await client.get(f"{_RXNAV_BASE}/rxcui/{cui}/properties.json")
            r2.raise_for_status()
            props = r2.json().get("properties", {})
            canonical = props.get("name", drug_name)

            result = {"cui": cui, "canonical_name": canonical}
            _cache[key] = result
            return result

    except Exception as e:
        logger.debug(f"RxNorm async lookup failed for '{drug_name}': {e}")
        _cache[key] = {}
        return {}
