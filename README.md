# Keyword Scrapper SEO — Real-Time Keyword Trend Detection MCP Server

A Model Context Protocol (MCP) server that detects trending search keywords in real time using Google Trends data — built for AI agent workflows, SEO keyword research automation, and content planning pipelines.

Unlike static keyword databases that update monthly, this surfaces **rising query velocity** — what's heating up right now, not what already peaked.

---

## Why This Exists

Traditional SEO tools show historical search volume. By the time a keyword shows up there, the trend window is often already closing. This server plugs directly into Claude (or any MCP-compatible agent) to surface momentum early — useful for content teams, SEO automation pipelines, and agentic workflows that need live signal, not lagging indicators.

**This is a discovery layer, not a keyword-suite replacement.** No search volume, no backlink data, no keyword difficulty scores — it does one thing well: real-time trend and velocity detection.

---

## Features

- **Trending keyword detection** — surfaces rising queries by velocity score
- **Interest-over-time history** — track a keyword's momentum curve
- **Related keyword expansion** — pulls associated rising/top queries for a seed term
- **Category-level trending** — breaks down trends by industry/vertical
- **Geo hotspot detection** — regional/city-level rising interest, built for local SEO
- **Local SQLite caching** — reduces redundant calls, respects rate limits
- **Retry + backoff logic** — resilient against Google Trends rate limiting

## Tech Stack

- Python
- FastMCP (Model Context Protocol server framework)
- pytrends (Google Trends API wrapper)
- SQLite (local caching layer)

---

## Installation

```bash
git clone https://github.com/k-devvv/keyword-scrapper-SEO.git
cd keyword-scrapper-SEO
pip install -r requirements.txt
```

## Usage

Run the MCP server and connect it to Claude Desktop (or any MCP client) via your MCP config:

```json
{
  "mcpServers": {
    "keyword-trends": {
      "command": "python",
      "args": ["path/to/google_trends_mcp.py"]
    }
  }
}
```

Once connected, query it conversationally through your agent — e.g. "what's trending in home restoration searches this week" or "show rising queries related to public adjuster."

---

## Available Tools

| Tool | Purpose |
|---|---|
| `detect_trending_keywords` | Finds keywords with rising search velocity |
| `get_interest_history` | Returns interest-over-time for a given keyword |
| `get_related_keywords` | Expands a seed keyword into related rising/top terms |
| `get_category_trends` | Trending breakdown by category/vertical |
| `get_geo_hotspots` | Regional/city-level rising interest for local SEO |

---

## Roadmap

- [ ] Notion API integration — auto-push trending keywords into a content calendar database
- [ ] Intent classification layer (informational / commercial / transactional)
- [ ] Batch processing for multi-seed keyword expansion
- [ ] Optional REST/dashboard wrapper for non-MCP use

---

## Limitations (Read Before Using)

- Google Trends is a relative-interest index (0–100), **not** absolute search volume
- Data has a freshness lag (15 min–24 hr depending on endpoint)
- Soft rate limits apply (~10–15 requests/min) — not built for high-throughput production load
- Single-source dependency on pytrends/Google Trends frontend — fragile to upstream changes

---

## License

MIT

## Author

Built solo by [Krishna Kumar K](https://github.com/k-devvv) — freelance AI automation engineer, Here to Scale.
