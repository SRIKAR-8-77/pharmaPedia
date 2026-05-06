import html
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy imports so the module loads even if packages aren't installed yet
_ftfy = None
_detect = None


def _get_ftfy():
    global _ftfy
    if _ftfy is None:
        try:
            import ftfy
            _ftfy = ftfy
        except ImportError:
            _ftfy = False
    return _ftfy


def _get_detect():
    global _detect
    if _detect is None:
        try:
            from langdetect import detect, LangDetectException
            _detect = (detect, LangDetectException)
        except ImportError:
            _detect = False
    return _detect


@dataclass
class CleanResult:
    text: str
    language: str = "en"
    skip: bool = False
    skip_reason: Optional[str] = None


# Regex patterns compiled once
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MENTION_RE = re.compile(r"@\w+")
_SUBREDDIT_RE = re.compile(r"r/\w+")
_MARKDOWN_RE = re.compile(r"[*_~`#>|]")
_WHITESPACE_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def clean(text: str, title: Optional[str] = None) -> CleanResult:
    """
    Step 1 of the NLP pipeline — clean and gate raw post text.
    Returns CleanResult with skip=True if post should not be processed further.
    """
    # Combine title + body
    parts = []
    if title and title.strip():
        parts.append(title.strip())
    if text and text.strip():
        parts.append(text.strip())
    full = " ".join(parts)

    if not full.strip():
        return CleanResult(text="", skip=True, skip_reason="empty")

    # HTML entities + tags
    full = html.unescape(full)
    full = _HTML_TAG_RE.sub(" ", full)

    # Fix encoding artifacts (ftfy)
    ftfy = _get_ftfy()
    if ftfy:
        full = ftfy.fix_text(full)

    # Strip URLs, @mentions, subreddit refs, markdown
    full = _URL_RE.sub(" ", full)
    full = _MENTION_RE.sub(" ", full)
    full = _SUBREDDIT_RE.sub(" ", full)
    full = _MARKDOWN_RE.sub(" ", full)

    # Normalize whitespace
    full = _WHITESPACE_RE.sub(" ", full).strip()

    # Length gate — minimum 15 words
    word_count = len(full.split())
    if word_count < 15:
        return CleanResult(text=full, skip=True, skip_reason="too_short")

    # Language gate — English only for now
    lang = _detect_language(full)
    if lang and lang != "en":
        return CleanResult(text=full, language=lang, skip=True, skip_reason="non_english")

    return CleanResult(text=full, language=lang or "en", skip=False)


def _detect_language(text: str) -> Optional[str]:
    detect_pkg = _get_detect()
    if not detect_pkg:
        return "en"   # assume English if langdetect not installed
    detect, LangDetectException = detect_pkg
    try:
        return detect(text[:500])
    except LangDetectException:
        return None
    except Exception:
        return None
