# Google Trends MCP Server - Quick Start

Get it running in 5 minutes.

## 1. Extract & Navigate

```bash
cd /path/to/google_trends_mcp
```

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Takes ~30 seconds. Installs pytrends, FastMCP, pydantic, httpx, pandas.

## 3. Start the Server

```bash
python google_trends_mcp.py
```

You should see no output (server runs on stdio). This is normal. Ctrl+C to stop.

## 4. Test It (Optional)

In a new terminal:

```bash
python test_server.py
```

Runs 5 quick tests. Expect ~10-30s depending on network. Should see:
```
✓ Test passed
✓ Test passed
...
SUMMARY: 5 passed, 0 failed
```

## 5. Connect via MCP Inspector

In a new terminal:

```bash
npx @modelcontextprotocol/inspector python google_trends_mcp.py
```

Opens browser UI. Click any tool and call it with params.

## 6. Use in Claude

### Option A: Claude Desktop (macOS/Windows)

1. Stop the server (Ctrl+C from step 3)
2. Edit `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "google_trends": {
      "command": "python",
      "args": ["/full/path/to/google_trends_mcp.py"]
    }
  }
}
```

3. Restart Claude Desktop
4. Open a chat and ask: "Find the top 5 exploding keywords in tech right now"
5. Claude will use the tools automatically

### Option B: API (Anthropic SDK)

```python
import subprocess
import json
from anthropic import Anthropic

client = Anthropic()

# Start server in background
proc = subprocess.Popen(["python", "google_trends_mcp.py"], 
                        stdin=subprocess.PIPE, 
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)

# Then use with Claude...
# (Full example in README.md)
```

---

## What the Tools Do

1. **detect_trending_keywords** → Find exploding keywords with velocity scores
2. **get_keyword_interest_history** → See trend curves over time
3. **get_related_keywords** → Get context (related searches, topics)
4. **get_trending_by_category** → Explosions in specific categories
5. **get_geolocation_hotspots** → Which regions a keyword trends in

All return JSON. All have full error handling.

---

## Example Tool Calls

### Find Top Tech Keywords

```json
{
  "tool": "detect_trending_keywords",
  "params": {
    "region": "US",
    "category": "tech",
    "limit": 5
  }
}
```

Returns trending keywords with velocity scores (e.g., 450% = 450% spike).

### Analyze a Keyword

```json
{
  "tool": "get_keyword_interest_history",
  "params": {
    "keyword": "Claude AI",
    "timeframe": "today 1-m"
  }
}
```

Returns interest curve + peak dates + trend direction.

### Get Related Context

```json
{
  "tool": "get_related_keywords",
  "params": {
    "keyword": "ChatGPT"
  }
}
```

Returns related topics and search queries (for enrichment).

---

## Velocity Score Explained

- **Velocity >= 300%** = EXPLODING 🔥 (high confidence)
- **Velocity 100-300%** = TRENDING 📈 (medium confidence)
- **Velocity < 100%** = STABLE (low confidence)

Example:
```
If keyword went from 20 → 92 in 24h:
Velocity = ((92-20)/20)*100 = 360%
Status: EXPLODING, confidence 0.95
```

---

## Rate Limits & Performance

- **Speed**: 1-2 seconds per tool call (first time), <100ms if cached
- **Rate Limit**: Google throttles at ~15 req/min; server handles with exponential backoff
- **Data Freshness**: Trending Searches are ~15 min old; Interest curves are 1-2 days old

---

## Troubleshooting

**"Error: Failed to fetch trending searches"**
→ Google rate-limited. Wait 5-10 min, retry.

**Server won't start**
→ Check: `python --version` (need 3.8+), `pip install -r requirements.txt --upgrade`

**Test fails with "429" error**
→ Google rate-limited your IP. Normal. Wait a bit, try again.

**No output from server**
→ That's correct. stdio transport is silent. Use MCP Inspector to test.

---

## Read These Next

1. **README.md** — Full tool documentation with all parameters
2. **PHASE_1_RESEARCH_PLAN.md** — Deep technical design (architecture, formulas, caching strategy)
3. **PHASE_2_IMPLEMENTATION.md** — Implementation details, features, integration guide

---

## You're Ready

Run step 3 (start the server) and step 5 (MCP Inspector) to get immediate feedback.

Then decide: test it, deploy it, or extend it.

Go build. 🚀
