"""
Google Trends Dashboard - Web UI
Runs a FastAPI server that calls the MCP tools directly (no stdio nonsense)
and serves a clean dashboard at http://localhost:8000
"""

import sys
import logging
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import the tools directly from google_trends_mcp
sys.path.insert(0, r"C:\Users\krish\Downloads\google scrapper")

app = FastAPI(title="Google Trends Dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── lazy import so we don't need the path at build time ──────────────────────
def _get_tools():
    from trendspyg import download_google_trends_rss, download_google_trends_explore
    return download_google_trends_rss, download_google_trends_explore

# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/trending")
async def trending(region: str = "IN", limit: int = 20):
    try:
        download_google_trends_rss, _ = _get_tools()
        env = download_google_trends_rss(geo=region, normalize=True)
        trends = env.get("trends", [])[:limit]
        results = []
        for t in trends:
            results.append({
                "rank": t.get("rank"),
                "keyword": t.get("keyword"),
                "search_volume": t.get("volume_min"),
                "volume_text": t.get("volume_text"),
                "started_at": t.get("started_at"),
                "is_active": t.get("is_active"),
                "related_queries": t.get("related_queries", [])[:5],
                "news_titles": [n.get("title") for n in t.get("news", [])[:3] if n.get("title")],
            })
        return {"trending": results, "region": region, "timestamp": datetime.utcnow().isoformat() + "Z"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/history")
async def history(keyword: str, region: str = "IN", timeframe: str = "now 7-d"):
    try:
        _, download_google_trends_explore = _get_tools()
        env = download_google_trends_explore(keyword=keyword, geo=region, timeframe=timeframe, include_related=True, include_geo=False)
        points = env.get("interest_over_time", [])
        return {"keyword": keyword, "region": region, "timeframe": timeframe, "points": points}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/related")
async def related(keyword: str, region: str = "IN"):
    try:
        _, download_google_trends_explore = _get_tools()
        env = download_google_trends_explore(keyword=keyword, geo=region, timeframe="now 7-d", include_related=True, include_geo=False)
        return {"keyword": keyword, "region": region, "related_queries": env.get("related_queries", {})}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/geo")
async def geo(keyword: str, limit: int = 10):
    try:
        _, download_google_trends_explore = _get_tools()
        env = download_google_trends_explore(keyword=keyword, geo="", timeframe="now 7-d", include_related=False, include_geo=True)
        points = sorted(env.get("interest_by_region", []), key=lambda r: r["value"], reverse=True)[:limit]
        return {"keyword": keyword, "regions": [{"region": r["geo_name"], "interest": r["value"]} for r in points]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── HTML Dashboard ────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Google Trends Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f13; color: #e2e8f0; min-height: 100vh; }
  header { background: #1a1a2e; padding: 16px 32px; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #2d2d44; }
  header h1 { font-size: 20px; font-weight: 700; color: #fff; }
  header span { font-size: 12px; color: #4ade80; background: #14532d; padding: 3px 8px; border-radius: 99px; }
  .container { max-width: 1400px; margin: 0 auto; padding: 24px 32px; }
  .controls { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; align-items: center; }
  select, input { background: #1e1e30; border: 1px solid #3d3d5c; color: #e2e8f0; padding: 8px 12px; border-radius: 8px; font-size: 14px; }
  input { flex: 1; min-width: 200px; }
  button { background: #6366f1; color: white; border: none; padding: 8px 18px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; transition: background 0.2s; }
  button:hover { background: #4f46e5; }
  button.secondary { background: #374151; }
  button.secondary:hover { background: #4b5563; }
  .tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid #2d2d44; }
  .tab { padding: 10px 20px; cursor: pointer; color: #94a3b8; font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent; transition: all 0.2s; }
  .tab.active { color: #6366f1; border-bottom-color: #6366f1; }
  .tab:hover { color: #e2e8f0; }
  .panel { display: none; }
  .panel.active { display: block; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
  .card { background: #1a1a2e; border: 1px solid #2d2d44; border-radius: 12px; padding: 16px; transition: border-color 0.2s; }
  .card:hover { border-color: #6366f1; }
  .card-rank { font-size: 11px; color: #6366f1; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
  .card-keyword { font-size: 16px; font-weight: 700; color: #fff; margin-bottom: 8px; line-height: 1.3; }
  .card-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
  .badge { font-size: 11px; padding: 3px 8px; border-radius: 99px; font-weight: 600; }
  .badge-green { background: #14532d; color: #4ade80; }
  .badge-blue { background: #1e3a5f; color: #60a5fa; }
  .badge-orange { background: #431407; color: #fb923c; }
  .card-news { font-size: 12px; color: #64748b; margin-top: 8px; }
  .card-news li { list-style: none; padding: 3px 0; border-top: 1px solid #2d2d44; }
  .related-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .tag { font-size: 11px; background: #2d2d44; color: #94a3b8; padding: 3px 8px; border-radius: 99px; }
  .loader { text-align: center; padding: 60px; color: #64748b; }
  .loader-spinner { width: 40px; height: 40px; border: 3px solid #2d2d44; border-top-color: #6366f1; border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .error { background: #450a0a; border: 1px solid #7f1d1d; color: #fca5a5; padding: 16px; border-radius: 8px; margin: 16px 0; }
  .search-row { display: flex; gap: 12px; margin-bottom: 20px; }
  .result-block { background: #1a1a2e; border: 1px solid #2d2d44; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
  .result-block h3 { font-size: 14px; font-weight: 700; color: #6366f1; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }
  .query-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #2d2d44; font-size: 14px; }
  .query-item:last-child { border-bottom: none; }
  .query-bar { height: 4px; background: #6366f1; border-radius: 2px; margin-top: 4px; transition: width 0.5s; }
  .region-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #2d2d44; }
  .region-item:last-child { border-bottom: none; }
  .region-bar-wrap { flex: 1; margin: 0 12px; background: #2d2d44; border-radius: 2px; height: 6px; }
  .region-bar { height: 6px; background: #6366f1; border-radius: 2px; }
  .timestamp { font-size: 11px; color: #475569; margin-top: 12px; }
  .region-select { display: flex; gap: 8px; align-items: center; }
  .stat-row { display: flex; gap: 16px; margin-bottom: 20px; }
  .stat { background: #1a1a2e; border: 1px solid #2d2d44; border-radius: 10px; padding: 16px 20px; flex: 1; }
  .stat-val { font-size: 28px; font-weight: 800; color: #6366f1; }
  .stat-label { font-size: 12px; color: #64748b; margin-top: 4px; }
</style>
</head>
<body>
<header>
  <h1>📈 Google Trends Dashboard</h1>
  <span>LIVE</span>
</header>
<div class="container">
  <div class="tabs">
    <div class="tab active" onclick="switchTab('trending')">🔥 Trending Now</div>
    <div class="tab" onclick="switchTab('history')">📊 Interest History</div>
    <div class="tab" onclick="switchTab('related')">🔗 Related Keywords</div>
    <div class="tab" onclick="switchTab('geo')">🌍 Geo Hotspots</div>
  </div>

  <!-- TRENDING -->
  <div id="tab-trending" class="panel active">
    <div class="controls">
      <div class="region-select">
        <label style="font-size:13px;color:#94a3b8">Region:</label>
        <select id="tr-region" onchange="loadTrending()">
          <option value="IN">🇮🇳 India</option>
          <option value="US">🇺🇸 United States</option>
          <option value="GB">🇬🇧 United Kingdom</option>
          <option value="BR">🇧🇷 Brazil</option>
          <option value="DE">🇩🇪 Germany</option>
          <option value="FR">🇫🇷 France</option>
          <option value="JP">🇯🇵 Japan</option>
          <option value="AU">🇦🇺 Australia</option>
          <option value="CA">🇨🇦 Canada</option>
          <option value="SG">🇸🇬 Singapore</option>
          <option value="ZA">🇿🇦 South Africa</option>
          <option value="NG">🇳🇬 Nigeria</option>
          <option value="KR">🇰🇷 South Korea</option>
          <option value="MX">🇲🇽 Mexico</option>
        </select>
        <select id="tr-limit">
          <option value="10">Top 10</option>
          <option value="20" selected>Top 20</option>
          <option value="30">Top 30</option>
        </select>
        <button onclick="loadTrending()">Refresh</button>
      </div>
    </div>
    <div id="tr-stats" class="stat-row" style="display:none">
      <div class="stat"><div class="stat-val" id="st-count">-</div><div class="stat-label">Keywords Trending</div></div>
      <div class="stat"><div class="stat-val" id="st-top">-</div><div class="stat-label">Top Keyword</div></div>
      <div class="stat"><div class="stat-val" id="st-vol">-</div><div class="stat-label">Peak Volume</div></div>
    </div>
    <div id="tr-results" class="grid"><div class="loader"><div class="loader-spinner"></div>Loading live trends...</div></div>
    <div class="timestamp" id="tr-ts"></div>
  </div>

  <!-- HISTORY -->
  <div id="tab-history" class="panel">
    <div class="search-row">
      <input id="hist-kw" placeholder="Enter keyword e.g. ChatGPT" value="AI" />
      <select id="hist-region">
        <option value="IN">India</option><option value="US">US</option><option value="GB">UK</option>
        <option value="BR">Brazil</option><option value="DE">Germany</option><option value="JP">Japan</option>
      </select>
      <select id="hist-tf">
        <option value="now 1-H">Past 1 Hour</option>
        <option value="now 4-H">Past 4 Hours</option>
        <option value="now 1-d">Past 24 Hours</option>
        <option value="now 7-d" selected>Past 7 Days</option>
        <option value="today 1-m">Past Month</option>
        <option value="today 3-m">Past 3 Months</option>
        <option value="today 12-m">Past Year</option>
      </select>
      <button onclick="loadHistory()">Search</button>
    </div>
    <div id="hist-results"></div>
  </div>

  <!-- RELATED -->
  <div id="tab-related" class="panel">
    <div class="search-row">
      <input id="rel-kw" placeholder="Enter keyword e.g. ChatGPT" value="ChatGPT" />
      <select id="rel-region">
        <option value="IN">India</option><option value="US">US</option><option value="GB">UK</option>
      </select>
      <button onclick="loadRelated()">Search</button>
    </div>
    <div id="rel-results"></div>
  </div>

  <!-- GEO -->
  <div id="tab-geo" class="panel">
    <div class="search-row">
      <input id="geo-kw" placeholder="Enter keyword e.g. Olympics" value="Olympics" />
      <select id="geo-limit">
        <option value="10">Top 10</option>
        <option value="20">Top 20</option>
        <option value="30">Top 30</option>
      </select>
      <button onclick="loadGeo()">Search</button>
    </div>
    <div id="geo-results"></div>
  </div>
</div>

<script>
const BASE = 'http://localhost:8000';

function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  const tabs = ['trending','history','related','geo'];
  document.querySelectorAll('.tab')[tabs.indexOf(name)].classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
}

function loader(id) {
  document.getElementById(id).innerHTML = '<div class="loader"><div class="loader-spinner"></div>Fetching live data...</div>';
}

function err(id, msg) {
  document.getElementById(id).innerHTML = '<div class="error">⚠️ '+msg+'</div>';
}

async function loadTrending() {
  const region = document.getElementById('tr-region').value;
  const limit = document.getElementById('tr-limit').value;
  loader('tr-results');
  try {
    const r = await fetch(`${BASE}/api/trending?region=${region}&limit=${limit}`);
    const d = await r.json();
    if (d.error) { err('tr-results', d.error); return; }
    
    const top = d.trending[0];
    document.getElementById('st-count').textContent = d.trending.length;
    document.getElementById('st-top').textContent = top ? top.keyword.substring(0,20) : '-';
    document.getElementById('st-vol').textContent = top ? top.volume_text : '-';
    document.getElementById('tr-stats').style.display = 'flex';
    document.getElementById('tr-ts').textContent = 'Last updated: ' + new Date(d.timestamp).toLocaleTimeString();

    document.getElementById('tr-results').innerHTML = d.trending.map(t => `
      <div class="card">
        <div class="card-rank">#${t.rank}</div>
        <div class="card-keyword">${t.keyword}</div>
        <div class="card-meta">
          <span class="badge badge-green">${t.volume_text || 'N/A'} searches</span>
          ${t.is_active ? '<span class="badge badge-blue">🟢 Active</span>' : ''}
          ${t.started_at ? '<span class="badge badge-orange">'+new Date(t.started_at).toLocaleTimeString()+'</span>' : ''}
        </div>
        ${t.related_queries.length ? '<div class="related-tags">'+t.related_queries.map(q=>`<span class="tag">${q}</span>`).join('')+'</div>' : ''}
        ${t.news_titles.length ? '<ul class="card-news">'+t.news_titles.map(n=>`<li>📰 ${n}</li>`).join('')+'</ul>' : ''}
      </div>
    `).join('');
  } catch(e) { err('tr-results', 'Server error: '+e.message); }
}

async function loadHistory() {
  const kw = document.getElementById('hist-kw').value;
  const region = document.getElementById('hist-region').value;
  const tf = document.getElementById('hist-tf').value;
  if (!kw) return;
  loader('hist-results');
  try {
    const r = await fetch(`${BASE}/api/history?keyword=${encodeURIComponent(kw)}&region=${region}&timeframe=${encodeURIComponent(tf)}`);
    const d = await r.json();
    if (d.error) { err('hist-results', d.error); return; }
    const pts = d.points || [];
    if (!pts.length) { err('hist-results', 'No data found'); return; }
    const max = Math.max(...pts.map(p=>p.value));
    document.getElementById('hist-results').innerHTML = `
      <div class="result-block">
        <h3>Interest Over Time — "${d.keyword}" (${d.region})</h3>
        ${pts.map(p => `
          <div class="query-item">
            <span style="color:#94a3b8;font-size:12px">${new Date(p.date).toLocaleDateString()}</span>
            <div style="flex:1;margin:0 12px">
              <div class="query-bar" style="width:${(p.value/max*100)}%"></div>
            </div>
            <span style="font-weight:700;color:${p.value>70?'#4ade80':p.value>40?'#fbbf24':'#94a3b8'}">${p.value}</span>
          </div>
        `).join('')}
      </div>`;
  } catch(e) { err('hist-results', 'Server error: '+e.message); }
}

async function loadRelated() {
  const kw = document.getElementById('rel-kw').value;
  const region = document.getElementById('rel-region').value;
  if (!kw) return;
  loader('rel-results');
  try {
    const r = await fetch(`${BASE}/api/related?keyword=${encodeURIComponent(kw)}&region=${region}`);
    const d = await r.json();
    if (d.error) { err('rel-results', d.error); return; }
    const rq = d.related_queries || {};
    document.getElementById('rel-results').innerHTML = Object.entries(rq).map(([bucket, queries]) => `
      <div class="result-block">
        <h3>${bucket === 'top' ? '🔝 Top Queries' : '📈 Rising Queries'} — "${d.keyword}"</h3>
        ${queries.map(q => `
          <div class="query-item">
            <span>${q.query}</span>
            <span style="color:#6366f1;font-weight:700">${q.formatted_value}</span>
          </div>
        `).join('')}
      </div>
    `).join('') || '<div class="error">No related queries found</div>';
  } catch(e) { err('rel-results', 'Server error: '+e.message); }
}

async function loadGeo() {
  const kw = document.getElementById('geo-kw').value;
  const limit = document.getElementById('geo-limit').value;
  if (!kw) return;
  loader('geo-results');
  try {
    const r = await fetch(`${BASE}/api/geo?keyword=${encodeURIComponent(kw)}&limit=${limit}`);
    const d = await r.json();
    if (d.error) { err('geo-results', d.error); return; }
    document.getElementById('geo-results').innerHTML = `
      <div class="result-block">
        <h3>🌍 Geographic Interest — "${d.keyword}"</h3>
        ${d.regions.map((r,i) => `
          <div class="region-item">
            <span style="width:24px;color:#6366f1;font-weight:700">#${i+1}</span>
            <span style="min-width:160px">${r.region}</span>
            <div class="region-bar-wrap"><div class="region-bar" style="width:${r.interest}%"></div></div>
            <span style="font-weight:700;color:#4ade80">${r.interest}</span>
          </div>
        `).join('')}
      </div>`;
  } catch(e) { err('geo-results', 'Server error: '+e.message); }
}

// Auto-load on start
loadTrending();
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTML

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
