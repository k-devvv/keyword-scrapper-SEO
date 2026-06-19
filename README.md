# Google Trends MCP Server

Real-time trending keyword detection with velocity scoring. Feed exploding search trends into agentic workflows.

## Setup

### 1. Install Dependencies

```bash
cd /path/to/google_trends_mcp
pip install -r requirements.txt
```

### 2. Run the Server

```bash
python google_trends_mcp.py
```

The server starts on stdio (standard input/output) by default, listening for MCP protocol messages.

## Tools Available

### 1. `detect_trending_keywords`
Fetch real-time exploding keywords with velocity scoring.

**Parameters:**
- `region` (str): Region code (US, UK, IN, BR, DE, FR, etc.) — default: "US"
- `category` (str): Category filter (all, tech, health, entertainment, sports, etc.) — default: "all"
- `limit` (int): Top N keywords to return (1-30) — default: 10
- `velocity_threshold` (int, optional): Custom velocity threshold (%) — default: 300

**Response:**
```json
{
  "trending_keywords": [
    {
      "keyword": "Taylor Swift Eras Tour",
      "velocity_score": 450.5,
      "current_volume": 92,
      "volume_baseline": 20,
      "region": "US",
      "category": "all",
      "explosion_confidence": 0.95,
      "timestamp": "2025-01-15T10:30:00Z"
    }
  ],
  "region": "US",
  "category": "all",
  "window_hours": 24,
  "threshold_velocity": 300,
  "count": 5,
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

### 2. `get_keyword_interest_history`
Fetch detailed interest curve over time with trend direction detection.

**Parameters:**
- `keyword` (str): Keyword to analyze
- `timeframe` (str): Time range ('today 1-m', 'today 3-m', 'today 1-y', 'today 5-y') — default: "today 1-m"
- `region` (str): Region code — default: "US"
- `include_geo_breakdown` (bool): Add interest by region breakdown — default: false

**Response:**
```json
{
  "keyword": "Claude AI",
  "timeframe": "today 1-m",
  "region": "US",
  "interest_data": [
    {
      "date": "2025-01-15",
      "interest": 85,
      "ma_7day": 78.3,
      "ma_30day": 72.1
    }
  ],
  "peak_date": "2025-01-14",
  "peak_interest": 100,
  "trend_direction": "spike",
  "top_regions": [
    {
      "region": "US",
      "interest": 89
    }
  ],
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

### 3. `get_related_keywords`
Discover related topics and queries for context enrichment.

**Parameters:**
- `keyword` (str): Main keyword to analyze
- `region` (str): Region code — default: "US"
- `include_queries` (bool): Include related search queries — default: true

**Response:**
```json
{
  "keyword": "Taylor Swift Eras Tour",
  "region": "US",
  "related_topics": [
    {
      "topic": "The Eras Tour",
      "type": "Top",
      "interest": 100
    },
    {
      "topic": "Taylor Swift",
      "type": "Top",
      "interest": 95
    }
  ],
  "related_queries": [
    {
      "query": "eras tour tickets",
      "interest": 100
    },
    {
      "query": "eras tour dates",
      "interest": 92
    }
  ],
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

### 4. `get_trending_by_category`
Detect exploding keywords within specific categories.

**Parameters:**
- `categories` (list): Category names (e.g., ["tech", "health"]) — default: ["tech", "health", "entertainment"]
- `region` (str): Region code — default: "US"
- `limit` (int): Top N keywords per category — default: 5

**Response:**
```json
{
  "by_category": {
    "tech": [
      {
        "keyword": "Claude AI",
        "velocity_score": 520.3,
        "current_volume": 95,
        "explosion_confidence": 0.95
      }
    ],
    "health": [
      {
        "keyword": "Weight loss",
        "velocity_score": 210.1,
        "current_volume": 72,
        "explosion_confidence": 0.75
      }
    ]
  },
  "region": "US",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

### 5. `get_geolocation_hotspots`
Identify geographic regions where a keyword is trending.

**Parameters:**
- `keyword` (str): Keyword to geo-analyze
- `limit` (int): Top N regions to return (1-50) — default: 10

**Response:**
```json
{
  "keyword": "Taylor Swift Eras Tour",
  "top_regions": [
    {
      "region": "United States",
      "interest": 100,
      "rank": 1,
      "velocity_score": 420.5
    },
    {
      "region": "United Kingdom",
      "interest": 87,
      "rank": 2,
      "velocity_score": 350.2
    }
  ],
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

## Integration with Claude

### Via MCP Inspector

```bash
npx @modelcontextprotocol/inspector python /path/to/google_trends_mcp.py
```

Then call any tool directly in the inspector UI.

### Via Claude Desktop (macOS/Windows)

Add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "google_trends": {
      "command": "python",
      "args": ["/path/to/google_trends_mcp.py"]
    }
  }
}
```

Restart Claude Desktop, then use the tools in conversation.

### Via API (Anthropic SDK)

```python
from anthropic import Anthropic

client = Anthropic()

# Start the MCP server as subprocess
# then use with client.messages.create(...) with tools

response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=4096,
    tools=[...],  # Tools exposed by MCP server
    messages=[
        {
            "role": "user",
            "content": "What are the top 5 exploding keywords in tech right now?",
        }
    ],
)
```

---

## Velocity Score Explained

**Velocity Score** = % change in search interest over 24 hours.

- **Velocity >= 300%**: CRITICAL explosion (confidence: 0.95)
- **Velocity 100-300%**: TRENDING rise (confidence: 0.75)
- **Velocity < 100%**: STABLE (confidence: 0.50)

### Example

```
If a keyword had:
- Interest 24h ago: 20 (baseline)
- Current interest: 92 (now)

Velocity = ((92 - 20) / 20) * 100 = 360%
Status: EXPLODING 🔥
Confidence: 0.95
```

---

## Rate Limiting & Resilience

**Google Trends Limits:**
- ~10-15 requests per minute (soft limit)
- Server implements exponential backoff (2s → 4s → 8s → 16s)
- Retries up to 3 times before failing

**Data Freshness:**
- Trending Searches: ~15 minutes old
- Interest Over Time: ~1-2 days old
- Related Topics/Queries: ~24 hours old

---

## Caching Strategy

SQLite cache at `~/.google_trends_cache.db`:

| Data | TTL |
|------|-----|
| Trending Keywords | 15 minutes |
| Interest History | 1 hour |
| Related Keywords | 6 hours |

Cache automatically cleans expired entries on read.

---

## Troubleshooting

### "Error: Failed to fetch trending searches"

Usually means Google rate-limited the IP. Wait 5-10 minutes and retry.

### "No data found for keyword"

Keyword may be too niche or region-specific. Try a broader term or different region.

### Server won't start

Check Python version (requires 3.8+) and all dependencies installed:
```bash
pip install -r requirements.txt --upgrade
```

---

## Supported Regions

US, UK, IN, BR, DE, FR, CA, AU, JP, CN, ZA, and many others (any Google Trends region).

## Supported Categories

all, entertainment, beauty, business, cars, crypto, fitness, games, health, internet, jobs, movies, music, news, pets, real_estate, science, shopping, sports, tech, travel.

---

## Next Steps (Phase 4: Evaluations)

Build test questions like:
- "Find 3 exploding tech keywords in the US with their related queries"
- "Identify geographic hotspots for AI-related searches"
- "Compare velocity trends for ChatGPT vs Claude across regions"

Run evaluations with the MCP Inspector to verify correctness.

---

## Architecture

```
Agentic Workflow / Claude
         ↓ (stdio MCP Protocol)
Google Trends MCP Server
    ├── Tool Registry (5 tools)
    ├── PyTrends Wrapper (retry logic, error handling)
    ├── SQLite Cache (trending, history, related)
    └── Analytics Layer (velocity scoring, trend detection)
```

---

## Files

- `google_trends_mcp.py` — Main server implementation
- `requirements.txt` — Python dependencies
- `PHASE_1_RESEARCH_PLAN.md` — Full technical design document
- `README.md` — This file

---

Happy trending! 📈
"# keyword-scrapper-SEO" 
