"""
Step 6 — Relevance scoring + MinHash LSH deduplication.
Weighted score: entity presence (0.4) + signal severity (0.3) + sentiment strength (0.2) + post length (0.1).
MinHash LSH via datasketch for near-duplicate detection across sources.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Lazy MinHash setup
_lsh = None
_minhash_cls = None
_LSH_THRESHOLD = 0.85
_NUM_PERM = 128


def _get_minhash():
    global _minhash_cls, _lsh
    if _minhash_cls is None:
        try:
            from datasketch import MinHash, MinHashLSH
            _minhash_cls = MinHash
            _lsh = MinHashLSH(threshold=_LSH_THRESHOLD, num_perm=_NUM_PERM)
            logger.info("MinHash LSH initialized")
        except ImportError:
            logger.warning("datasketch not installed — deduplication disabled")
            _minhash_cls = False
    return _minhash_cls


def _make_shingles(text: str, k: int = 4) -> set[str]:
    """Generate k-character shingles from text."""
    text = text.lower().strip()
    return {text[i:i+k] for i in range(len(text) - k + 1)}


def _make_minhash(text: str):
    MinHash = _get_minhash()
    if not MinHash:
        return None
    m = MinHash(num_perm=_NUM_PERM)
    for shingle in _make_shingles(text):
        m.update(shingle.encode("utf8"))
    return m


@dataclass
class RelevanceResult:
    score: float = 0.0
    is_duplicate: bool = False
    minhash_signature: list | None = None


def score_relevance(
    text: str,
    drugs: list[str],
    symptoms: list[str],
    conditions: list[str],
    has_signal: bool,
    severity: str | None,
    sentiment_score: float,
    post_id: str | None = None,
) -> RelevanceResult:
    """
    Step 6 — Compute relevance score (0.0–1.0) and check for near-duplicates.
    """
    # Entity presence component (0–0.4)
    has_drug = len(drugs) > 0
    has_symptom = len(symptoms) > 0
    has_condition = len(conditions) > 0
    entity_score = 0.0
    if has_drug and has_symptom:
        entity_score = 0.4
    elif has_drug or has_symptom:
        entity_score = 0.25
    elif has_condition:
        entity_score = 0.15
    # Bonus for multiple drug-symptom pairs
    if len(drugs) > 1 and len(symptoms) > 1:
        entity_score = min(0.4, entity_score + 0.05)

    # Signal severity component (0–0.3)
    severity_score = {"HIGH": 0.30, "MED": 0.20, "LOW": 0.10}.get(severity, 0.0) if has_signal else 0.0

    # Sentiment strength component (0–0.2)
    # Strong negative sentiment = more relevant for pharmacovigilance
    sentiment_strength = abs(sentiment_score)
    sentiment_component = min(0.2, sentiment_strength * 0.2)

    # Post length component (0–0.1)
    word_count = len(text.split())
    length_component = min(0.1, word_count / 500 * 0.1)

    total = entity_score + severity_score + sentiment_component + length_component
    total = round(min(1.0, total), 4)

    # MinHash deduplication
    is_dup = False
    minhash_sig = None
    minhash = _make_minhash(text)
    if minhash and _lsh is not None:
        try:
            neighbors = _lsh.query(minhash)
            if neighbors:
                is_dup = True
            else:
                key = post_id or text[:20]
                try:
                    _lsh.insert(key, minhash)
                except ValueError:
                    pass  # already inserted
            minhash_sig = minhash.hashvalues.tolist()
        except Exception as e:
            logger.debug(f"MinHash error: {e}")

    return RelevanceResult(
        score=total,
        is_duplicate=is_dup,
        minhash_signature=minhash_sig,
    )
