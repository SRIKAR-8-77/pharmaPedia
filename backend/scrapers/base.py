from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class ScrapedPost:
    source: str
    keyword: str
    text: str
    timestamp: datetime
    title: Optional[str] = None
    author: Optional[str] = None
    url: Optional[str] = None
    external_id: Optional[str] = None
    upvotes: int = 0
    comment_count: int = 0


class BaseScraper(ABC):
    source_type: str = ""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def fetch(
        self,
        keyword: str,
        limit: int = 100,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[ScrapedPost]:
        """Fetch posts for a keyword within the optional time window [since, until]."""
        ...

    def _deduplicate(self, posts: List[ScrapedPost]) -> List[ScrapedPost]:
        seen = set()
        unique = []
        for post in posts:
            key = post.external_id or post.url or f"{post.source}:{post.text[:80]}"
            if key not in seen:
                seen.add(key)
                unique.append(post)
        return unique
