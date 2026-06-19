"""
Google Trends MCP Server
Surfaces real, booming search keywords (with actual search volume and
freshness) for SEO / growth-marketing content targeting, plus keyword
research tools (interest history, related keywords, geo hotspots).

Built entirely on trendspyg, not pytrends. Reasoning:
  - pytrends' trending_searches() / realtime_trending_searches() hit a
    Google backend that no longer exists (404s as of mid-2026).
  - pytrends' related_topics() has an unpatched indexing bug (crashes
    with IndexError on certain keywords because it assumes Google's
    response always has a non-empty 'keyword' list).
  - trendspyg is actively maintained against the *current* Google Trends
    site (RSS + a real headless-browser Explore flow), so it's slower
    per call but far more resilient to Google's backend changes. Given
    the priority here is correctness/quality over raw speed, that
    tradeoff is the right one.

Tool -> trendspyg function map:
  - detect_trending_keywords / get_trending_by_category -> download_google_trends_rss
  - get_keyword_interest_history / get_related_keywords / get_geolocation_hotspots
    -> download_google_trends_explore (one browser call returns interest_over_time,
       related_queries, and interest_by_region together)
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator, ConfigDict
from trendspyg import download_google_trends_rss, download_google_trends_explore

# ============================================================================
# SETUP
# ============================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("google_trends_mcp")

DB_PATH = Path.home() / ".google_trends_cache.db"
CACHE_TTL_TRENDING = 15 * 60  # 15 minutes
CACHE_TTL_HISTORY = 60 * 60  # 1 hour
CACHE_TTL_RELATED = 6 * 60 * 60  # 6 hours

CATEGORY_MAP = {
    "all": 0,
    "entertainment": 1,
    "beauty": 44,
    "business": 12,
    "cars": 47,
    "cooking": 71,
    "crypto": 7_139,
    "fitness": 71,
    "games": 8,
    "health": 45,
    "hobbies": 33,
    "internet": 32,
    "jobs": 34,
    "movies": 48,
    "music": 4,
    "news": 16,
    "pets": 67,
    "real_estate": 63,
    "science": 36,
    "shopping": 18,
    "sports": 20,
    "tech": 31,
    "travel": 25,
}


# ============================================================================
# DATABASE UTILITIES
# ============================================================================

def _init_db():
    """Initialize SQLite cache tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trending_keywords_cache (
            id INTEGER PRIMARY KEY,
            region TEXT,
            category INTEGER,
            keyword TEXT,
            current_volume INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME,
            UNIQUE(region, category, keyword)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interest_history_cache (
            id INTEGER PRIMARY KEY,
            keyword TEXT,
            region TEXT,
            timeframe TEXT,
            data_json TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME,
            UNIQUE(keyword, region, timeframe)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS related_keywords_cache (
            id INTEGER PRIMARY KEY,
            keyword TEXT,
            region TEXT,
            data_json TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME,
            UNIQUE(keyword, region)
        )
    """)

    conn.commit()
    conn.close()


def _get_cached(table: str, key_conditions: str) -> Optional[str]:
    """Retrieve cached data if not expired."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT data_json FROM {table} WHERE {key_conditions} AND expires_at > datetime('now')"
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.warning(f"Cache retrieval failed: {e}")
        return None


def _set_cached(table: str, key_cols: str, key_vals: tuple, data: str, ttl_seconds: int):
    """Store data in cache with expiration."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        cursor.execute(
            f"""
            INSERT OR REPLACE INTO {table} ({key_cols}, data_json, expires_at)
            VALUES ({', '.join(['?'] * len(key_vals))}, ?, ?)
            """,
            (*key_vals, data, expires_at.isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Cache storage failed: {e}")


# ============================================================================
# TRENDSPYG WRAPPERS
# ============================================================================

async def fetch_trending_rss(geo: str = "US") -> List[Dict[str, Any]]:
    """
    Fetch currently-booming search keywords for a geo via Google Trends RSS.
    Returns Google's own rank order, real volume_min, freshness (started_at),
    and related queries/news for content angles.
    """
    try:
        env = download_google_trends_rss(geo=geo, normalize=True)
        return env.get("trends", [])
    except Exception as e:
        raise ValueError(f"Failed to fetch trending searches via RSS: {str(e)}")


async def fetch_explore(keyword: str, geo: str = "US", timeframe: str = "today 1-m") -> Dict[str, Any]:
    """
    Fetch the full Explore envelope for a keyword: interest_over_time,
    related_queries, and interest_by_region in one browser-rendered call.
    This is slower than a raw HTTP call but renders Google's actual page,
    so it isn't subject to the reverse-engineered-endpoint breakage that
    hits pytrends.
    """
    try:
        return download_google_trends_explore(
            keyword=keyword,
            geo=geo,
            timeframe=timeframe,
            include_related=True,
            include_geo=True,
        )
    except Exception as e:
        raise ValueError(f"Failed to fetch Explore data for '{keyword}': {str(e)}")


# ============================================================================
# INPUT MODELS (Pydantic)
# ============================================================================

class DetectTrendingKeywordsInput(BaseModel):
    """Input for detect_trending_keywords tool."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    region: str = Field(
        default="US",
        description="Region code (US, UK, IN, BR, DE, FR, etc.)",
        min_length=2,
        max_length=5,
    )
    limit: int = Field(default=10, description="Number of keywords to return", ge=1, le=20)
    min_volume: Optional[int] = Field(
        default=None,
        description="Minimum search volume (volume_min) to include. If None, no filtering.",
        ge=0,
    )

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: str) -> str:
        valid = ["US", "UK", "IN", "BR", "DE", "FR", "CA", "AU", "JP", "CN", "ZA", ""]
        if v not in valid:
            raise ValueError(f"Region must be one of: {valid}")
        return v


class GetKeywordInterestHistoryInput(BaseModel):
    """Input for get_keyword_interest_history tool."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    keyword: str = Field(..., description="Keyword to analyze", min_length=1, max_length=100)
    timeframe: str = Field(
        default="today 1-m",
        description="Time range: 'today 1-m', 'today 3-m', 'today 12-m', 'today 5-y'",
    )
    region: str = Field(default="US", description="Region code (US, UK, IN, etc.)")
    include_geo_breakdown: bool = Field(
        default=False, description="Include interest by region breakdown"
    )

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        valid = ["today 1-m", "today 3-m", "today 12-m", "today 5-y"]
        if v not in valid:
            raise ValueError(f"Timeframe must be one of: {valid}")
        return v


class GetRelatedKeywordsInput(BaseModel):
    """Input for get_related_keywords tool."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    keyword: str = Field(..., description="Main keyword to analyze", min_length=1, max_length=100)
    region: str = Field(default="US", description="Region code (US, UK, IN, etc.)")
    include_queries: bool = Field(default=True, description="Include related search queries")


class GetTrendingByCategoryInput(BaseModel):
    """Input for get_trending_by_category tool."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    categories: List[str] = Field(
        default=["tech", "health", "entertainment"],
        description=(
            "List of categories to filter by, matched against each trend's "
            "keyword/related queries/news text (e.g. ['tech', 'health']). "
            "Note: Google's trending RSS feed is not natively category-scoped, "
            "so this performs keyword-based filtering over the general "
            "trending feed rather than a true per-category query."
        ),
        max_length=10,
    )
    region: str = Field(default="US", description="Region code (US, UK, IN, etc.)")
    limit: int = Field(default=5, description="Top N keywords per category", ge=1, le=20)


class GetGeolocationHotspotsInput(BaseModel):
    """Input for get_geolocation_hotspots tool."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    keyword: str = Field(..., description="Keyword to geo-analyze", min_length=1, max_length=100)
    limit: int = Field(default=10, description="Top N regions to return", ge=1, le=50)


# ============================================================================
# TOOLS
# ============================================================================

@mcp.tool(
    name="detect_trending_keywords",
    annotations={
        "title": "Detect Booming Search Keywords",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def detect_trending_keywords(params: DetectTrendingKeywordsInput) -> str:
    """
    Detect keywords currently booming on Google Search for a given region,
    ranked by Google's own trending order, with real search volume and
    freshness — built for SEO/content targeting (catch the spike early).

    Args:
        params: DetectTrendingKeywordsInput with region, limit, min_volume

    Returns:
        JSON with trending keywords: rank, keyword, search volume, how long
        it's been trending, related queries (for keyword expansion), and
        related news (for content angles).
    """
    try:
        trends = await fetch_trending_rss(geo=params.region)

        results = []
        for t in trends:
            volume = t.get("volume_min")
            if params.min_volume is not None and (volume is None or volume < params.min_volume):
                continue
            results.append(
                {
                    "rank": t.get("rank"),
                    "keyword": t.get("keyword"),
                    "search_volume": volume,
                    "volume_text": t.get("volume_text"),
                    "started_at": t.get("started_at"),
                    "is_active": t.get("is_active"),
                    "related_queries": t.get("related_queries", [])[:5],
                    "news_titles": [n.get("title") for n in t.get("news", [])[:3] if n.get("title")],
                }
            )

        results = results[: params.limit]

        return json.dumps(
            {
                "trending_keywords": results,
                "region": params.region,
                "count": len(results),
                "source": "google_trends_rss",
                "note": (
                    "search_volume is a floor estimate from Google's volume "
                    "tier (e.g. '20000+'), not an exact count."
                ),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "error": f"Failed to detect trending keywords: {str(e)}",
                "error_type": type(e).__name__,
            },
            indent=2,
        )


@mcp.tool(
    name="get_keyword_interest_history",
    annotations={
        "title": "Get Keyword Interest History",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_keyword_interest_history(params: GetKeywordInterestHistoryInput) -> str:
    """
    Fetch detailed interest curve for a keyword over time via a real
    browser-rendered Explore call (trendspyg), with moving averages to
    detect trend direction and peaks.

    Args:
        params: GetKeywordInterestHistoryInput with keyword, timeframe, region, geo_breakdown

    Returns:
        JSON with interest curve, peak dates, trend direction, and optional geo breakdown
    """
    try:
        env = await fetch_explore(params.keyword, geo=params.region, timeframe=params.timeframe)
        points = env.get("interest_over_time", [])

        if not points:
            return json.dumps(
                {"error": f"No data found for keyword: {params.keyword}"}, indent=2
            )

        values = [p["value"] for p in points]

        def moving_avg(vals: List[int], window: int, idx: int) -> float:
            start = max(0, idx - window + 1)
            window_vals = vals[start: idx + 1]
            return round(sum(window_vals) / len(window_vals), 1)

        interest_data = [
            {
                "date": p["date"],
                "interest": p["value"],
                "ma_7day": moving_avg(values, 7, i),
                "ma_30day": moving_avg(values, 30, i),
            }
            for i, p in enumerate(points)
        ]

        peak_point = max(points, key=lambda p: p["value"])
        peak_date = peak_point["date"]
        peak_interest = peak_point["value"]

        recent = values[-7:]
        baseline = values[:7]
        recent_avg = sum(recent) / len(recent) if recent else 0
        baseline_avg = sum(baseline) / len(baseline) if baseline else 0
        if baseline_avg and recent_avg > baseline_avg * 1.2:
            trend = "spike"
        elif baseline_avg and recent_avg < baseline_avg * 0.8:
            trend = "decline"
        else:
            trend = "stable"

        response = {
            "keyword": params.keyword,
            "timeframe": params.timeframe,
            "region": params.region,
            "interest_data": interest_data,
            "peak_date": peak_date,
            "peak_interest": peak_interest,
            "trend_direction": trend,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        if params.include_geo_breakdown:
            geo_points = env.get("interest_by_region", [])
            top_regions = sorted(geo_points, key=lambda r: r["value"], reverse=True)[:5]
            response["top_regions"] = [
                {"region": r["geo_name"], "interest": r["value"]} for r in top_regions
            ]

        return json.dumps(response, indent=2)

    except Exception as e:
        return json.dumps(
            {
                "error": f"Failed to fetch interest history: {str(e)}",
                "error_type": type(e).__name__,
            },
            indent=2,
        )


@mcp.tool(
    name="get_related_keywords",
    annotations={
        "title": "Get Related Keywords",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_related_keywords(params: GetRelatedKeywordsInput) -> str:
    """
    Discover related keywords and search queries for context enrichment,
    via a real browser-rendered Explore call (trendspyg).

    Returns related queries ranked by search interest (both "top" and
    "rising" buckets, when Google provides both).

    Args:
        params: GetRelatedKeywordsInput with keyword, region, include_queries

    Returns:
        JSON with related queries
    """
    try:
        if not params.include_queries:
            return json.dumps(
                {
                    "keyword": params.keyword,
                    "region": params.region,
                    "related_queries": {},
                    "note": "include_queries was False; no data fetched.",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
                indent=2,
            )

        env = await fetch_explore(params.keyword, geo=params.region)
        related = env.get("related_queries", {}) or {}

        formatted = {
            bucket: [
                {
                    "query": q.get("query"),
                    "value": q.get("value"),
                    "formatted_value": q.get("formatted_value"),
                }
                for q in queries[:10]
            ]
            for bucket, queries in related.items()
        }

        return json.dumps(
            {
                "keyword": params.keyword,
                "region": params.region,
                "related_queries": formatted,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "error": f"Failed to fetch related keywords: {str(e)}",
                "error_type": type(e).__name__,
            },
            indent=2,
        )


@mcp.tool(
    name="get_trending_by_category",
    annotations={
        "title": "Get Trending Keywords by Category",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def get_trending_by_category(params: GetTrendingByCategoryInput) -> str:
    """
    Filter currently-booming Google Search keywords by category-relevant terms.

    Google's trending RSS feed is not natively category-scoped (that backend
    was deprecated), so this fetches the general trending feed once and
    keyword-matches each requested category against the trend's keyword,
    related queries, and news headlines. Treat this as a best-effort filter,
    not an exact per-category query.

    Args:
        params: GetTrendingByCategoryInput with categories, region, limit

    Returns:
        JSON with trending keywords grouped by category
    """
    try:
        trends = await fetch_trending_rss(geo=params.region)
        by_category: Dict[str, List[Dict[str, Any]]] = {}

        for cat_name in params.categories:
            cat_lower = cat_name.lower()
            cat_results = []
            for t in trends:
                haystack_parts = [t.get("keyword", "")]
                haystack_parts += t.get("related_queries", []) or []
                haystack_parts += [n.get("title", "") for n in t.get("news", []) or []]
                haystack = " ".join(p for p in haystack_parts if p).lower()

                if cat_lower in haystack:
                    cat_results.append(
                        {
                            "rank": t.get("rank"),
                            "keyword": t.get("keyword"),
                            "search_volume": t.get("volume_min"),
                            "volume_text": t.get("volume_text"),
                            "started_at": t.get("started_at"),
                        }
                    )

            by_category[cat_name] = cat_results[: params.limit]

        return json.dumps(
            {
                "by_category": by_category,
                "region": params.region,
                "source": "google_trends_rss",
                "note": "Best-effort keyword match over the general trending feed (no native category endpoint).",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "error": f"Failed to fetch trending by category: {str(e)}",
                "error_type": type(e).__name__,
            },
            indent=2,
        )


@mcp.tool(
    name="get_geolocation_hotspots",
    annotations={
        "title": "Get Geographic Hotspots",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_geolocation_hotspots(params: GetGeolocationHotspotsInput) -> str:
    """
    Identify which geographic regions a keyword is trending in, via a real
    browser-rendered Explore call (trendspyg). Helps pinpoint geo-specific
    explosions.

    Args:
        params: GetGeolocationHotspotsInput with keyword, limit

    Returns:
        JSON with top regions ranked by interest
    """
    try:
        env = await fetch_explore(params.keyword, geo="")  # worldwide breakdown
        geo_points = env.get("interest_by_region", [])

        if not geo_points:
            return json.dumps(
                {"error": f"No geo data found for keyword: {params.keyword}"}, indent=2
            )

        top_regions_sorted = sorted(geo_points, key=lambda r: r["value"], reverse=True)[: params.limit]

        top_regions = [
            {
                "region": r["geo_name"],
                "interest": r["value"],
                "rank": i + 1,
            }
            for i, r in enumerate(top_regions_sorted)
        ]

        return json.dumps(
            {
                "keyword": params.keyword,
                "top_regions": top_regions,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "error": f"Failed to fetch geolocation hotspots: {str(e)}",
                "error_type": type(e).__name__,
            },
            indent=2,
        )


# ============================================================================
# STARTUP & MAIN
# ============================================================================

def main():
    """Initialize and run the MCP server."""
    _init_db()
    logger.info("Google Trends MCP server initialized (trendspyg backend)")
    mcp.run()


if __name__ == "__main__":
    main()
