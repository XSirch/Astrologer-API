"""
Location search endpoints.

The mobile app uses these endpoints instead of calling GeoNames directly so
credentials, throttling, and cache policy stay on the VPS.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from logging import getLogger
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

from ..config.settings import settings

logger = getLogger(__name__)
router = APIRouter(prefix="/locations")

GEONAMES_SEARCH_URL = "https://secure.geonames.org/searchJSON"
MAX_ROWS_LIMIT = 10
MIN_QUERY_LEN = 2
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 60


@dataclass
class CacheEntry:
    expires_at: float
    data: list[dict[str, Any]]


_city_cache: dict[str, CacheEntry] = {}
_rate_limits: dict[str, list[float]] = {}


def _cache_key(query: str, lang: str, max_rows: int) -> str:
    return f"{query.strip().casefold()}:{lang.strip().casefold()}:{max_rows}"


def _enforce_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    hits = [ts for ts in _rate_limits.get(client, []) if ts >= window_start]
    if len(hits) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Too many city search requests.")
    hits.append(now)
    _rate_limits[client] = hits


def _normalize_timezone(raw: Any) -> str | None:
    if isinstance(raw, dict):
        value = raw.get("timeZoneId") or raw.get("timezoneId") or raw.get("name")
        return str(value) if value else None
    if isinstance(raw, str):
        return raw or None
    return None


def normalize_geoname(raw: dict[str, Any]) -> dict[str, Any] | None:
    try:
        lat = float(raw["lat"])
        lng = float(raw["lng"])
    except (KeyError, TypeError, ValueError):
        return None

    name = str(raw.get("name") or raw.get("toponymName") or "").strip()
    country_name = str(raw.get("countryName") or "").strip()
    country_code = str(raw.get("countryCode") or "").strip().upper()
    if not name or not country_code:
        return None

    admin_name = str(raw.get("adminName1") or "").strip() or None
    timezone = _normalize_timezone(raw.get("timezone"))

    return {
        "id": str(raw.get("geonameId") or f"{name}:{country_code}:{lat}:{lng}"),
        "name": name,
        "countryName": country_name or country_code,
        "countryCode": country_code,
        "adminName": admin_name,
        "latitude": lat,
        "longitude": lng,
        "timezone": timezone,
    }


async def fetch_geonames_cities(query: str, lang: str, max_rows: int) -> list[dict[str, Any]]:
    if not settings.geonames_username:
        raise HTTPException(
            status_code=503,
            detail="GeoNames username is not configured on the server.",
        )

    params = {
        "q": query,
        "lang": lang,
        "maxRows": max_rows,
        "username": settings.geonames_username,
        "featureClass": "P",
        "style": "FULL",
        "isNameRequired": "true",
        "type": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(GEONAMES_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        logger.warning("GeoNames city search failed for query=%r: %s", query, exc)
        raise HTTPException(status_code=502, detail="GeoNames city search failed.") from exc

    status = payload.get("status")
    if isinstance(status, dict):
        message = status.get("message") or "GeoNames returned an error."
        raise HTTPException(status_code=502, detail=str(message))

    cities: list[dict[str, Any]] = []
    for item in payload.get("geonames", []):
        if not isinstance(item, dict):
            continue
        normalized = normalize_geoname(item)
        if normalized:
            cities.append(normalized)
    return cities[:max_rows]


@router.get("/cities")
async def search_cities(
    request: Request,
    q: str = Query(min_length=MIN_QUERY_LEN, max_length=80),
    lang: str = Query(default="en", min_length=2, max_length=5),
    maxRows: int = Query(default=MAX_ROWS_LIMIT, ge=1, le=MAX_ROWS_LIMIT),
) -> dict[str, Any]:
    _enforce_rate_limit(request)

    query = q.strip()
    if len(query) < MIN_QUERY_LEN:
        raise HTTPException(status_code=400, detail="Query must have at least 2 characters.")

    safe_lang = lang.strip().lower()[:5] or "en"
    safe_max_rows = min(maxRows, MAX_ROWS_LIMIT)
    key = _cache_key(query, safe_lang, safe_max_rows)
    now = time.time()

    cached = _city_cache.get(key)
    if cached and cached.expires_at > now:
        return {"cities": cached.data, "cached": True}

    cities = await fetch_geonames_cities(query, safe_lang, safe_max_rows)
    _city_cache[key] = CacheEntry(expires_at=now + CACHE_TTL_SECONDS, data=cities)
    return {"cities": cities, "cached": False}
