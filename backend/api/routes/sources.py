from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Any, Optional
from datetime import datetime
import json
import logging

import httpx
from pydantic import BaseModel

from config import settings
from models.database import get_db, SourceLatency
from models import crud

logger = logging.getLogger(__name__)

router = APIRouter()


class GlobalSourceResponse(BaseModel):
    id: UUID
    domain: str
    name: str
    source_type: str
    url: str
    feed_url: Optional[str]
    reliability_tier: int
    supports_date_range: bool = False
    total_posts_pulled: Optional[int] = 0
    last_successful_run: Optional[datetime]
    added_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class AddConfirmedSourceRequest(BaseModel):
    name: str
    domain: str
    source_type: str        # "rss" | "api" | "reddit"
    url: str
    feed_url: Optional[str] = None
    project_id: Optional[UUID] = None
    keyword: Optional[str] = None
    supports_date_range: bool = False


class AddCustomSourceRequest(BaseModel):
    url: str                          # RSS feed URL or API fetch URL template
    name: str
    source_type: str                  # "rss" | "api"
    project_id: Optional[UUID] = None
    keyword: Optional[str] = None
    api_key: Optional[str] = None
    scraper_config: Optional[dict[str, Any]] = None   # full config for API sources (from probe-api)
    supports_date_range: bool = False


class ProbeApiRequest(BaseModel):
    url: str
    api_key: Optional[str] = None
    keyword: str = "aspirin"


@router.get("", response_model=list[GlobalSourceResponse])
async def list_global_sources(db: AsyncSession = Depends(get_db)):
    """List all global sources with their pull stats."""
    return await crud.list_global_sources(db)


@router.post("/{source_id}/toggle", response_model=GlobalSourceResponse)
async def toggle_global_source(
    source_id: UUID,
    enabled: bool,
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable a global source (affects all projects that use it)."""
    source = await crud.toggle_global_source(db, source_id, enabled)
    if not source:
        raise HTTPException(status_code=404, detail="Global source not found")
    return source


@router.post("/add-confirmed", response_model=GlobalSourceResponse, status_code=status.HTTP_201_CREATED)
async def add_confirmed_source(data: AddConfirmedSourceRequest, db: AsyncSession = Depends(get_db)):
    """
    Persist a source that the discovery agent found.
    The user explicitly confirms they want to add it.
    """
    gs = await crud.add_global_source(
        db,
        domain=data.domain[:255],
        name=data.name[:255],
        source_type=data.source_type,
        url=data.url,
        feed_url=data.feed_url,
        supports_date_range=data.supports_date_range,
    )
    if data.project_id and data.keyword:
        lat = SourceLatency.realtime if data.source_type == "reddit" else SourceLatency.daily
        await crud.link_project_to_global_source(db, data.project_id, gs.id, data.keyword, lat)
    await db.commit()
    await db.refresh(gs)
    return gs


@router.post("/add-custom", response_model=GlobalSourceResponse, status_code=status.HTTP_201_CREATED)
async def add_custom_source(data: AddCustomSourceRequest, db: AsyncSession = Depends(get_db)):
    """
    Add any RSS feed URL or API endpoint the user found themselves.
    A HEAD request confirms the URL is reachable before persisting.
    """
    from urllib.parse import urlparse
    domain = urlparse(data.url).netloc.lstrip("www.") or data.url[:255]

    # Quick reachability check
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            resp = await client.head(data.url)
            if resp.status_code >= 500:
                raise HTTPException(
                    status_code=400,
                    detail=f"URL returned server error ({resp.status_code}) — check the URL and try again",
                )
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Could not reach URL: {e}")

    if data.source_type == "api" and data.scraper_config:
        # Full config provided (from probe-api auto-detection)
        scraper_config = data.scraper_config
        if data.api_key:
            scraper_config["api_key"] = data.api_key
        feed_url = None
    elif data.source_type == "rss":
        scraper_config = {}
        feed_url = data.url
    else:
        scraper_config = {"api_key": data.api_key} if data.api_key else {}
        feed_url = None

    gs = await crud.add_global_source(
        db,
        domain=domain[:255],
        name=data.name[:255],
        source_type=data.source_type,
        url=data.url,
        feed_url=feed_url,
        scraper_config=scraper_config,
        supports_date_range=data.supports_date_range,
    )
    if data.project_id and data.keyword:
        lat = SourceLatency.realtime if data.source_type == "reddit" else SourceLatency.daily
        await crud.link_project_to_global_source(db, data.project_id, gs.id, data.keyword, lat)
    await db.commit()
    await db.refresh(gs)
    return gs


@router.post("/probe-api")
async def probe_api(data: ProbeApiRequest):
    """
    Probe a JSON API endpoint and use Gemini to auto-detect the response field mapping.
    Returns a scraper_config dict the frontend shows for confirmation before adding the source.
    """
    from urllib.parse import quote_plus
    probe_url = data.url.replace("{keyword}", quote_plus(data.keyword)) \
                        .replace("{limit}", "5") \
                        .replace("{since_iso}", "") \
                        .replace("{until_iso}", "")

    headers: dict = {"User-Agent": "PharmaPedia/1.0"}
    if data.api_key:
        headers["Authorization"] = f"Bearer {data.api_key}"

    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            resp = await client.get(probe_url, headers=headers)
            resp.raise_for_status()
            raw = resp.text[:6000]  # cap payload sent to LLM
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=400, detail=f"API returned {e.response.status_code}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Could not reach URL: {e}")

    if not settings.GEMINI_API_KEY:
        # Fallback: return a template config without LLM detection
        return {
            "fetch_url": data.url,
            "api_key": data.api_key or "",
            "items_path": "",
            "text_field": "text",
            "title_field": "title",
            "author_field": "author",
            "url_field": "url",
            "id_field": "id",
            "date_field": "created_at",
            "_note": "Gemini not configured — fill in fields manually",
        }

    prompt = f"""You are analyzing a JSON API response to configure a scraper.

API URL: {probe_url}
Response (first 6000 chars):
{raw}

Return ONLY valid JSON (no markdown) with these keys:
{{
  "fetch_url": "the URL template with {{keyword}}, {{limit}}, {{since_iso}}, {{until_iso}} placeholders where applicable",
  "items_path": "dot-notation path to the array of posts/results, empty string if root is the array",
  "text_field": "field name containing the main post text/body",
  "title_field": "field name for title, or empty string if none",
  "author_field": "field name for author/username, or empty string if none",
  "url_field": "field name for post URL/link, or empty string if none",
  "id_field": "field name for unique post ID, or empty string if none",
  "date_field": "field name for timestamp/date, or empty string if none",
  "supports_date_range": true or false
}}

Rules:
- items_path uses dot notation (e.g. "data.posts") or empty string if the root JSON is the array
- All field names must exist in the actual response objects
- If a field does not exist, use empty string"""

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        result = model.generate_content(prompt)
        text = result.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        detected = json.loads(text)
    except Exception as exc:
        logger.warning(f"probe-api Gemini failed: {exc}")
        detected = {
            "items_path": "",
            "text_field": "text",
            "title_field": "title",
            "author_field": "author",
            "url_field": "url",
            "id_field": "id",
            "date_field": "created_at",
            "supports_date_range": False,
        }

    detected["fetch_url"] = detected.get("fetch_url") or data.url
    if data.api_key:
        detected["api_key"] = data.api_key
    return detected


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_global_source(source_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete a global source and all its project links (cascade)."""
    deleted = await crud.delete_global_source(db, source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Global source not found")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
