#!/usr/bin/env python3
"""
Test script for Google Trends MCP Server
Run basic sanity checks on the server without needing MCP Inspector.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add current dir to path
sys.path.insert(0, str(Path(__file__).parent))

from google_trends_mcp import (
    detect_trending_keywords,
    get_keyword_interest_history,
    get_related_keywords,
    get_trending_by_category,
    get_geolocation_hotspots,
    DetectTrendingKeywordsInput,
    GetKeywordInterestHistoryInput,
    GetRelatedKeywordsInput,
    GetTrendingByCategoryInput,
    GetGeolocationHotspotsInput,
)


async def test_detect_trending():
    """Test detect_trending_keywords tool."""
    print("\n" + "=" * 80)
    print("TEST 1: detect_trending_keywords")
    print("=" * 80)

    params = DetectTrendingKeywordsInput(region="US", category="tech", limit=5)
    result = await detect_trending_keywords(params)
    
    data = json.loads(result)
    print(json.dumps(data, indent=2))
    
    assert "trending_keywords" in data, "Missing trending_keywords field"
    assert isinstance(data["trending_keywords"], list), "trending_keywords should be list"
    print("✓ Test passed")


async def test_interest_history():
    """Test get_keyword_interest_history tool."""
    print("\n" + "=" * 80)
    print("TEST 2: get_keyword_interest_history")
    print("=" * 80)

    params = GetKeywordInterestHistoryInput(
        keyword="AI",
        timeframe="today 1-m",
        region="US",
        include_geo_breakdown=True
    )
    result = await get_keyword_interest_history(params)
    
    data = json.loads(result)
    print(json.dumps(data, indent=2)[:500] + "...")  # Truncate for readability
    
    assert "interest_data" in data, "Missing interest_data field"
    assert "peak_date" in data, "Missing peak_date field"
    assert "trend_direction" in data, "Missing trend_direction field"
    print("✓ Test passed")


async def test_related_keywords():
    """Test get_related_keywords tool."""
    print("\n" + "=" * 80)
    print("TEST 3: get_related_keywords")
    print("=" * 80)

    params = GetRelatedKeywordsInput(
        keyword="ChatGPT",
        region="US",
        include_queries=True
    )
    result = await get_related_keywords(params)
    
    data = json.loads(result)
    print(json.dumps(data, indent=2))
    
    assert "related_topics" in data, "Missing related_topics field"
    assert "related_queries" in data, "Missing related_queries field"
    print("✓ Test passed")


async def test_trending_by_category():
    """Test get_trending_by_category tool."""
    print("\n" + "=" * 80)
    print("TEST 4: get_trending_by_category")
    print("=" * 80)

    params = GetTrendingByCategoryInput(
        categories=["tech", "health"],
        region="US",
        limit=3
    )
    result = await get_trending_by_category(params)
    
    data = json.loads(result)
    print(json.dumps(data, indent=2)[:800] + "...")  # Truncate
    
    assert "by_category" in data, "Missing by_category field"
    assert isinstance(data["by_category"], dict), "by_category should be dict"
    print("✓ Test passed")


async def test_geolocation_hotspots():
    """Test get_geolocation_hotspots tool."""
    print("\n" + "=" * 80)
    print("TEST 5: get_geolocation_hotspots")
    print("=" * 80)

    params = GetGeolocationHotspotsInput(
        keyword="Olympics",
        limit=5
    )
    result = await get_geolocation_hotspots(params)
    
    data = json.loads(result)
    print(json.dumps(data, indent=2))
    
    assert "top_regions" in data, "Missing top_regions field"
    assert isinstance(data["top_regions"], list), "top_regions should be list"
    print("✓ Test passed")


async def main():
    """Run all tests."""
    print("\n🚀 Google Trends MCP Server - Test Suite")
    print("Running sanity checks...\n")

    tests = [
        ("Detect Trending Keywords", test_detect_trending),
        ("Keyword Interest History", test_interest_history),
        ("Related Keywords", test_related_keywords),
        ("Trending by Category", test_trending_by_category),
        ("Geolocation Hotspots", test_geolocation_hotspots),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            print(f"\n❌ {test_name} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 80)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    print("=" * 80)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
