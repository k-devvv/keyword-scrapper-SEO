# Google Trends MCP Server - Phase 1: Research & Planning

## Project Overview
Building a local Python MCP server that detects "exploding keywords" from Google Trends, feeding real-time trending data into agentic workflows. Primary metric: **Velocity Score** (% change in search volume over time window).

---

## Pytrends Capabilities Analysis

### Core API Methods Available

| Method | Purpose | Use Case |
|--------|---------|----------|
| `interest_over_time()` | Historical indexed data (0-100 scale) | Detect velocity, compare trend arcs |
| `interest_by_region()` | Geographic breakdown of searches | Isolate trending-by-geo (US, UK, IN, etc.) |
| `related_topics()` | Related keywords/topics | Context enrichment for exploding keywords |
| `related_queries()` | Related search queries | Query variation analysis |
| `trending_searches()` | Real-time trending in a specific region | Primary source for "exploding" detection |
| `top_charts()` | Top 20 by category/region | Tier 1 keyword discovery |
| `suggestions()` | Autocomplete suggestions | Keyword expansion |
| `historical_interest()` | Hourly data for past 7 days | High-resolution velocity detection |

### Key Constraints
- **Rate Limiting**: Google throttles heavy requests; pytrends handles via exponential backoff + optional proxies
- **Data Scale**: 0-100 indexed scale (normalized, not raw search volume)
- **Freshness**: Trending Searches updated ~15min; Interest Over Time has 1-2 day lag
- **Geo Specificity**: Different regions have different trending terms
- **Category Filter**: 0 = All categories; specific cat IDs available (Health, Finance, etc.)

---

## Tool Schema Design

### Primary Tools (MVP)

#### 1. `detect_trending_keywords`
**Purpose**: Fetch real-time exploding keywords with velocity scoring.

**Inputs**:
- `region` (str): 'US', 'UK', 'IN', 'BR', etc. (default: 'US')
- `category` (int): 0 (all), 71 (science), 45 (health), etc. (default: 0)
- `limit` (int): Top N keywords to return (default: 10, max: 30)

**Logic**:
1. Fetch `trending_searches(region, category)`
2. For each trending keyword, fetch `interest_over_time()` for last 24h
3. Calculate **Velocity Score**: `(current_interest - 24h_ago_interest) / 24h_ago_interest * 100`
4. Filter keywords with velocity >= 300% (configurable threshold)
5. Enrich with category context and geo data

**Output**:
```json
{
  "trending_keywords": [
    {
      "keyword": "Taylor Swift Eras Tour",
      "velocity_score": 450,
      "current_volume": 92,
      "volume_24h_ago": 20,
      "region": "US",
      "category": "entertainment",
      "explosion_confidence": 0.95,
      "timestamp": "2025-01-15T10:30:00Z"
    }
  ],
  "window_minutes": 1440,
  "threshold_velocity": 300
}
```

---

#### 2. `get_keyword_interest_history`
**Purpose**: Get detailed interest curve for a keyword to understand trajectory.

**Inputs**:
- `keyword` (str): Keyword to analyze
- `timeframe` (str): 'today 1-m' (1 month), 'today 3-m', 'today 1-y' (default: 'today 1-m')
- `region` (str): 'US', 'UK', 'IN', etc. (default: 'US')
- `geo_breakdown` (bool): Include interest by region (default: False)

**Logic**:
1. Fetch `interest_over_time()` for specified timeframe
2. Calculate moving averages (7-day, 30-day) to smooth noise
3. Detect peak dates and inflection points
4. Optionally fetch `interest_by_region()` for heatmap

**Output**:
```json
{
  "keyword": "AI safety",
  "timeframe": "today 1-m",
  "interest_data": [
    {"date": "2025-01-15", "interest": 85, "ma_7day": 78, "ma_30day": 72},
    ...
  ],
  "peak_date": "2025-01-14",
  "peak_interest": 100,
  "trend_direction": "spike",
  "top_regions": [
    {"region": "US", "interest": 89},
    {"region": "UK", "interest": 72}
  ]
}
```

---

#### 3. `get_related_keywords`
**Purpose**: Discover context and related searches for an exploding keyword.

**Inputs**:
- `keyword` (str): Main keyword
- `region` (str): 'US', 'UK', 'IN', etc. (default: 'US')
- `include_queries` (bool): Include related queries (default: True)

**Logic**:
1. Fetch `related_topics()` for the keyword
2. Fetch `related_queries()` for the keyword
3. Rank by search interest
4. Combine into unified "context" object

**Output**:
```json
{
  "keyword": "Taylor Swift Eras Tour",
  "related_topics": [
    {"topic": "The Eras Tour", "type": "Topic", "interest": 100},
    {"topic": "Taylor Swift", "type": "Topic", "interest": 95},
    {"topic": "Swiftie", "type": "Topic", "interest": 78}
  ],
  "related_queries": [
    {"query": "eras tour tickets", "interest": 100},
    {"query": "eras tour dates", "interest": 92},
    {"query": "eras tour movie", "interest": 88}
  ]
}
```

---

#### 4. `get_trending_by_category`
**Purpose**: Detect explosions within specific categories (health, tech, entertainment, etc.).

**Inputs**:
- `categories` (list): List of category names or IDs (e.g., ['tech', 'health']) (default: all)
- `region` (str): 'US', 'UK', 'IN', etc. (default: 'US')
- `limit` (int): Top N per category (default: 5)

**Logic**:
1. Map category names to Google Trends category IDs
2. For each category, fetch `top_charts()` or `trending_searches()`
3. Calculate velocity for each
4. Return sorted by velocity per category

**Output**:
```json
{
  "by_category": {
    "tech": [
      {"keyword": "Claude AI", "velocity_score": 520, ...},
      {"keyword": "OpenAI", "velocity_score": 380, ...}
    ],
    "health": [
      {"keyword": "Weight loss", "velocity_score": 210, ...}
    ]
  },
  "region": "US",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

#### 5. `get_geolocation_hotspots`
**Purpose**: Identify which regions a keyword is trending in (geo-specific spike detection).

**Inputs**:
- `keyword` (str): Keyword to geo-analyze
- `limit` (int): Top N regions (default: 10)

**Logic**:
1. Fetch `interest_by_region()` for the keyword
2. Rank by interest
3. Compare against baseline (24h ago if possible)
4. Highlight unexpected geographic explosions

**Output**:
```json
{
  "keyword": "Taylor Swift Eras Tour",
  "top_regions": [
    {"region": "US", "interest": 100, "rank": 1, "velocity_score": 420},
    {"region": "UK", "interest": 87, "rank": 2, "velocity_score": 350},
    {"region": "CA", "interest": 82, "rank": 3, "velocity_score": 290}
  ],
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

### Secondary Tools (Phase 2+)

- `compare_keywords()` - Compare search interest across multiple keywords
- `get_weekly_recap()` - Top trending keywords from past week
- `forecast_trend()` - Simple projection based on velocity trajectory
- `search_keyword_suggestions()` - Autocomplete suggestions for keyword discovery

---

## Data Model: Exploding Keywords Schema

```python
class ExplodingKeyword(BaseModel):
    keyword: str
    region: str  # 'US', 'UK', 'IN', etc.
    velocity_score: float  # % change in 24h window
    current_volume: int  # 0-100 normalized
    volume_baseline: int  # volume N hours ago
    category: Optional[str]  # 'entertainment', 'tech', etc.
    explosion_confidence: float  # 0-1 score
    peak_date: Optional[str]  # ISO 8601
    timestamp: str  # Detection timestamp (ISO 8601)
    source: str  # 'trending_searches', 'related_queries', etc.
```

---

## Architecture: Local MCP Server (stdio)

```
┌─────────────────────────────────────────────┐
│     Agentic Workflow / Claude Context       │
└────────────────┬────────────────────────────┘
                 │ stdio (MCP Protocol)
                 │
┌────────────────▼────────────────────────────┐
│   Google Trends MCP Server (FastMCP)        │
├─────────────────────────────────────────────┤
│  ▪ Tool Registration Layer                  │
│    - detect_trending_keywords               │
│    - get_keyword_interest_history           │
│    - get_related_keywords                   │
│    - get_trending_by_category               │
│    - get_geolocation_hotspots               │
├─────────────────────────────────────────────┤
│  ▪ Core Logic Layer                         │
│    - VelocityScorer (calc % change)         │
│    - TrendingKeywordDetector                │
│    - GeoHotspotAnalyzer                     │
│    - CategoryMapper (cat names → IDs)       │
├─────────────────────────────────────────────┤
│  ▪ Pytrends Wrapper                         │
│    - TrendReq client (handles auth, retry)  │
│    - exponential backoff on 429 responses   │
│    - optional proxy rotation                │
├─────────────────────────────────────────────┤
│  ▪ Cache Layer (SQLite)                     │
│    - trending_keywords_cache (TTL: 15min)   │
│    - interest_history_cache (TTL: 1h)       │
│    - related_keywords_cache (TTL: 6h)       │
└─────────────────────────────────────────────┘
```

---

## Error Handling Strategy

### Rate Limit Handling
- **Trigger**: HTTP 429 (Too Many Requests)
- **Response**: Exponential backoff (2s → 4s → 8s → 16s max)
- **Message**: "Google rate-limited. Retrying in 4s. Try again with longer intervals."

### Google Backend Changes
- **Trigger**: Unexpected response format, missing fields
- **Response**: Clear error message identifying which API method broke
- **Message**: "pytrends API changed. Interest by region unavailable. Use fallback method."

### Invalid Parameters
- **Trigger**: Unknown region, invalid category ID
- **Response**: Validate inputs with Pydantic; return suggestions
- **Message**: "Region 'XYZ' not supported. Try: US, UK, IN, BR, etc."

### Freshness Constraints
- **Info**: Trending Searches data is ~15min fresh; Interest Over Time is 1-2 days old
- **Message in response**: Include `data_freshness_lag_hours` field for transparency

---

## SQLite Cache Design

```sql
CREATE TABLE IF NOT EXISTS trending_keywords_cache (
    id INTEGER PRIMARY KEY,
    region TEXT,
    category INTEGER,
    keyword TEXT,
    velocity_score REAL,
    current_volume INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    UNIQUE(region, category, keyword)
);

CREATE TABLE IF NOT EXISTS interest_history_cache (
    id INTEGER PRIMARY KEY,
    keyword TEXT,
    region TEXT,
    timeframe TEXT,
    data_json TEXT,  -- JSON blob of interest curve
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    UNIQUE(keyword, region, timeframe)
);
```

---

## Velocity Score Formula

```python
def calculate_velocity_score(current: int, baseline: int, window_hours: int = 24) -> float:
    """
    Velocity Score = % change in search interest over N-hour window.
    
    current: current interest (0-100)
    baseline: interest at start of window (0-100)
    window_hours: time window (default 24h)
    
    Returns: % change (e.g., 450 = 450% spike)
    """
    if baseline == 0:
        # Edge case: no baseline data. If current > 0, score is unbounded.
        return 10000 if current > 0 else 0
    
    return ((current - baseline) / baseline) * 100
```

**Threshold Logic**:
- Velocity >= 300% → EXPLODING (high confidence)
- Velocity 100-300% → TRENDING (medium confidence)
- Velocity < 100% → STABLE (low confidence)

---

## Testing Strategy

### Unit Tests (Mocked Responses)
- Mock `TrendReq.interest_over_time()` to return fixed data
- Test velocity calculation against known good values
- Validate Pydantic models with edge cases

### Integration Tests (Live pytrends)
- Fetch real trending data from `trending_searches()`
- Verify response format matches schema
- Handle rate limits gracefully

### MCP Inspector Testing
- Start server: `python google_trends_mcp.py`
- Connect via `npx @modelcontextprotocol/inspector`
- Call `detect_trending_keywords` with various regions/categories
- Verify JSON schema compliance

---

## Implementation Roadmap

### Phase 2: Core Implementation
1. Project init + FastMCP boilerplate
2. Pytrends client wrapper (TrendReq setup, retry logic)
3. Implement tools 1-5 above
4. SQLite cache layer
5. Error handling with actionable messages

### Phase 3: Testing & Hardening
1. Unit tests for velocity scoring
2. Integration tests with live pytrends
3. MCP Inspector validation
4. Load test (many concurrent calls)
5. Document rate limit behavior

### Phase 4: Evaluations
1. Create 10 complex eval questions
2. Test agentic workflows (e.g., "Find 3 exploding tech keywords in US + their related queries")
3. Verify correctness against Google Trends web UI

---

## Key Decisions Made

✅ **Python + FastMCP** (proven stability, better pytrends support)
✅ **stdio transport** (local, no network overhead, tight integration with Claude)
✅ **SQLite caching** (lightweight, persistent, fast)
✅ **Velocity Score as primary metric** (simple, interpretable, real-time)
✅ **Real-time trending_searches() + 24h interest_over_time()** (balance freshness vs stability)
✅ **Pytrends native + optional proxy support** (handles Google blocks, no custom wrapper trap)

---

## Next Step

→ **Phase 2: Implementation** (Build the full MCP server)
