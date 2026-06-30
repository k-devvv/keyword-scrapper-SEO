"""
Module 3 — Competitor Intelligence
Fetches a known URL directly (not search results) — far more reliable than
SERP scraping since there's no bot-detection on a single page request.

- Competitor keyword extractor (meta, headers, body text frequency)
- Sitemap-based publish frequency tracker
- Internal link structure mapper
- H1/H2 structure extractor
- Content gap finder (compare 2 domains' keyword footprints)
"""

import sys
import logging
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

import re
import json
import time
from collections import Counter
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="Competitor Intelligence Module")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

STOPWORDS = set("""
a an the and or but is are was were be been being have has had do does did will would
could should may might must can to of in on at by for with about against between into
through during before after above below from up down out off over under again further
then once here there when where why how all any both each few more most other some such
no nor not only own same so than too very s t just don should now this that these those
i you he she it we they what which who whom your yours my our ours their theirs its
""".split())

# ── Core scraping ──────────────────────────────────────────────────────────────

def fetch_page(url: str) -> Dict[str, Any]:
    """Fetch and parse a single page — title, meta, headers, body text, links."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        domain = urlparse(url).netloc.replace("www.", "")

        for tag in soup(["script", "style"]):
            tag.decompose()

        title = soup.find("title")
        title = title.get_text(strip=True) if title else ""

        meta_desc = soup.find("meta", {"name": re.compile(r"description", re.I)})
        meta_desc = meta_desc.get("content", "") if meta_desc else ""

        meta_kw = soup.find("meta", {"name": re.compile(r"keywords", re.I)})
        meta_kw = meta_kw.get("content", "") if meta_kw else ""

        h1s = [h.get_text(strip=True) for h in soup.find_all("h1")]
        h2s = [h.get_text(strip=True) for h in soup.find_all("h2")]
        h3s = [h.get_text(strip=True) for h in soup.find_all("h3")]

        body = soup.find("body")
        body_text = body.get_text(separator=" ", strip=True) if body else ""
        word_count = len(body_text.split())

        # Internal vs external links
        internal_links, external_links = [], []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(url, href)
            link_domain = urlparse(full).netloc.replace("www.", "")
            if not full.startswith("http"):
                continue
            if link_domain == domain:
                internal_links.append(full)
            else:
                external_links.append(full)

        return {
            "url": url, "domain": domain, "title": title,
            "meta_description": meta_desc, "meta_keywords": meta_kw,
            "h1s": h1s, "h2s": h2s, "h3s": h3s,
            "word_count": word_count, "body_text": body_text,
            "internal_links": list(set(internal_links))[:50],
            "external_links": list(set(external_links))[:20],
            "internal_link_count": len(set(internal_links)),
            "external_link_count": len(set(external_links)),
        }
    except Exception as e:
        return {"error": str(e), "url": url}


def extract_keywords_from_text(text: str, top_n: int = 30) -> List[Dict]:
    """Extract most frequent meaningful phrases (1-3 word n-grams) from body text."""
    words = re.findall(r"[a-zA-Z]+(?:'[a-zA-Z]+)?", text.lower())
    words = [w for w in words if w not in STOPWORDS and len(w) > 2]

    unigrams = Counter(words)
    bigrams = Counter(zip(words, words[1:]))
    trigrams = Counter(zip(words, words[1:], words[2:]))

    results = []
    for w, c in unigrams.most_common(top_n):
        if c >= 3:
            results.append({"keyword": w, "frequency": c, "type": "unigram"})
    for (w1, w2), c in bigrams.most_common(top_n):
        if c >= 2:
            results.append({"keyword": f"{w1} {w2}", "frequency": c, "type": "bigram"})
    for (w1, w2, w3), c in trigrams.most_common(15):
        if c >= 2:
            results.append({"keyword": f"{w1} {w2} {w3}", "frequency": c, "type": "trigram"})

    return sorted(results, key=lambda x: -x["frequency"])[:top_n]


def fetch_sitemap(domain: str) -> List[Dict]:
    """Try common sitemap locations to estimate publish frequency."""
    urls_to_try = [
        f"https://{domain}/sitemap.xml",
        f"https://{domain}/sitemap_index.xml",
        f"https://www.{domain}/sitemap.xml",
        f"https://{domain}/post-sitemap.xml",
    ]
    entries = []
    for su in urls_to_try:
        try:
            r = requests.get(su, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "xml")
            locs = soup.find_all("loc")
            lastmods = soup.find_all("lastmod")
            if not locs:
                continue
            for i, loc in enumerate(locs[:200]):
                entry = {"url": loc.get_text(strip=True)}
                if i < len(lastmods):
                    entry["lastmod"] = lastmods[i].get_text(strip=True)
                entries.append(entry)
            if entries:
                break
        except Exception:
            continue
    return entries


def analyze_publish_frequency(sitemap_entries: List[Dict]) -> Dict:
    """Analyze publish dates from sitemap to estimate posting cadence."""
    dated = [e for e in sitemap_entries if e.get("lastmod")]
    if not dated:
        return {"error": "No dated entries found in sitemap"}

    dates = []
    for e in dated:
        try:
            d = e["lastmod"][:10]  # YYYY-MM-DD
            dates.append(d)
        except Exception:
            continue

    if not dates:
        return {"error": "Could not parse dates"}

    dates_sorted = sorted(dates, reverse=True)
    by_month = Counter([d[:7] for d in dates_sorted])  # YYYY-MM

    return {
        "total_dated_urls": len(dates),
        "most_recent": dates_sorted[0] if dates_sorted else None,
        "oldest": dates_sorted[-1] if dates_sorted else None,
        "posts_per_month": dict(sorted(by_month.items(), reverse=True)[:12]),
        "avg_posts_per_month": round(sum(by_month.values()) / len(by_month), 1) if by_month else 0,
    }


# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/api/analyze")
async def analyze(url: str):
    """Full single-page competitor analysis."""
    data = fetch_page(url)
    if "error" in data:
        return JSONResponse(status_code=500, content=data)

    keywords = extract_keywords_from_text(data["body_text"], top_n=30)
    data["top_keywords"] = keywords
    del data["body_text"]  # don't send full text back
    data["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return data


@app.get("/api/sitemap")
async def sitemap(domain: str):
    """Analyze a domain's sitemap for publish frequency."""
    domain = domain.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
    entries = fetch_sitemap(domain)
    if not entries:
        return JSONResponse(status_code=404, content={"error": "No sitemap found at common locations"})

    freq = analyze_publish_frequency(entries)
    return {
        "domain": domain,
        "total_urls_found": len(entries),
        "frequency_analysis": freq,
        "recent_urls": [e["url"] for e in entries[:10]],
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/compare")
async def compare(url1: str, url2: str):
    """Compare keyword footprint of two competitor pages."""
    data1 = fetch_page(url1)
    data2 = fetch_page(url2)

    if "error" in data1 or "error" in data2:
        return JSONResponse(status_code=500, content={
            "error1": data1.get("error"), "error2": data2.get("error")
        })

    kw1 = {k["keyword"] for k in extract_keywords_from_text(data1["body_text"], top_n=50)}
    kw2 = {k["keyword"] for k in extract_keywords_from_text(data2["body_text"], top_n=50)}

    only_1 = list(kw1 - kw2)[:20]
    only_2 = list(kw2 - kw1)[:20]
    shared = list(kw1 & kw2)[:20]

    return {
        "page1": {"url": url1, "domain": data1["domain"], "title": data1["title"], "word_count": data1["word_count"]},
        "page2": {"url": url2, "domain": data2["domain"], "title": data2["title"], "word_count": data2["word_count"]},
        "unique_to_page1": only_1,
        "unique_to_page2": only_2,
        "shared_keywords": shared,
        "gap_count_page1": len(only_1),
        "gap_count_page2": len(only_2),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/links")
async def links(url: str):
    """Internal link structure of a page."""
    data = fetch_page(url)
    if "error" in data:
        return JSONResponse(status_code=500, content=data)
    return {
        "url": url, "domain": data["domain"],
        "internal_links": data["internal_links"],
        "external_links": data["external_links"],
        "internal_link_count": data["internal_link_count"],
        "external_link_count": data["external_link_count"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Competitor Intelligence</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f13; color: #e2e8f0; min-height: 100vh; }
header { background: #1a1a2e; padding: 16px 32px; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #2d2d44; }
header h1 { font-size: 20px; font-weight: 700; color: #fff; }
.nav-links { margin-left: auto; display: flex; gap: 16px; }
.nav-links a { font-size: 13px; color: #6366f1; text-decoration: none; }
.container { max-width: 1400px; margin: 0 auto; padding: 24px 32px; }
.tabs { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 1px solid #2d2d44; }
.tab { padding: 10px 20px; cursor: pointer; color: #94a3b8; font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent; }
.tab.active { color: #6366f1; border-bottom-color: #6366f1; }
.panel { display: none; }
.panel.active { display: block; }
.search-row { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
input { background: #1e1e30; border: 1px solid #3d3d5c; color: #e2e8f0; padding: 9px 14px; border-radius: 8px; font-size: 14px; flex: 1; min-width: 220px; }
button { background: #6366f1; color: white; border: none; padding: 9px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; }
button:hover { background: #4f46e5; }
.result-block { background: #1a1a2e; border: 1px solid #2d2d44; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
.result-block h3 { font-size: 13px; font-weight: 700; color: #6366f1; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; }
.loader { text-align: center; padding: 60px; color: #64748b; }
.spinner { width: 36px; height: 36px; border: 3px solid #2d2d44; border-top-color: #6366f1; border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
@keyframes spin { to { transform: rotate(360deg); } }
.error { background: #450a0a; border: 1px solid #7f1d1d; color: #fca5a5; padding: 14px; border-radius: 8px; }
.meta-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #2d2d44; font-size: 13px; }
.meta-row:last-child { border: none; }
.meta-label { color: #64748b; }
.meta-val { color: #e2e8f0; font-weight: 600; max-width: 70%; text-align: right; }
.kw-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; }
.kw-card { background: #12121f; border: 1px solid #2d2d44; border-radius: 8px; padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; }
.kw-text { font-size: 13px; font-weight: 600; }
.kw-freq { font-size: 11px; background: #2d2d44; color: #6366f1; padding: 2px 8px; border-radius: 99px; }
.h-tag { background: #2d2d44; color: #94a3b8; padding: 3px 10px; border-radius: 6px; font-size: 12px; margin: 2px; display: inline-block; }
.stat-row { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.stat { background: #1a1a2e; border: 1px solid #2d2d44; border-radius: 10px; padding: 16px 20px; flex: 1; min-width: 140px; }
.stat-val { font-size: 24px; font-weight: 800; color: #6366f1; }
.stat-label { font-size: 11px; color: #64748b; margin-top: 4px; text-transform: uppercase; }
.gap-col { background: #12121f; border: 1px solid #2d2d44; border-radius: 10px; padding: 16px; }
.gap-col h4 { font-size: 12px; color: #94a3b8; margin-bottom: 10px; text-transform: uppercase; }
.gap-item { padding: 6px 0; border-bottom: 1px solid #2d2d44; font-size: 13px; }
.gap-item:last-child { border: none; }
.gap-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.month-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #2d2d44; font-size: 13px; }
.month-row:last-child { border: none; }
.link-list { max-height: 300px; overflow-y: auto; font-size: 12px; color: #64748b; }
.link-list div { padding: 4px 0; border-bottom: 1px solid #2d2d4422; word-break: break-all; }
</style>
</head>
<body>
<header>
  <h1>🕵️ Competitor Intelligence</h1>
  <div class="nav-links">
    <a href="http://localhost:8001">← Keyword Research</a>
    <a href="http://localhost:8000">← Trends Dashboard</a>
  </div>
</header>
<div class="container">
  <div class="tabs">
    <div class="tab active" onclick="sw('analyze')">🔬 Page Analysis</div>
    <div class="tab" onclick="sw('sitemap')">📅 Publish Frequency</div>
    <div class="tab" onclick="sw('compare')">⚔️ Keyword Gap</div>
    <div class="tab" onclick="sw('links')">🔗 Link Structure</div>
  </div>

  <div id="tab-analyze" class="panel active">
    <div class="search-row">
      <input id="a-url" placeholder="Competitor URL e.g. https://example.com/blog/seo-guide" value="https://en.wikipedia.org/wiki/Search_engine_optimization" />
      <button onclick="loadAnalyze()">Analyze Page</button>
    </div>
    <div id="a-results"></div>
  </div>

  <div id="tab-sitemap" class="panel">
    <div class="search-row">
      <input id="sm-domain" placeholder="Domain e.g. example.com" value="moz.com" />
      <button onclick="loadSitemap()">Check Publish Frequency</button>
    </div>
    <div id="sm-results"></div>
  </div>

  <div id="tab-compare" class="panel">
    <div class="search-row">
      <input id="c-url1" placeholder="Your page URL" value="" />
      <input id="c-url2" placeholder="Competitor page URL" value="" />
      <button onclick="loadCompare()">Find Keyword Gap</button>
    </div>
    <div id="c-results"></div>
  </div>

  <div id="tab-links" class="panel">
    <div class="search-row">
      <input id="l-url" placeholder="Page URL" value="https://en.wikipedia.org/wiki/Search_engine_optimization" />
      <button onclick="loadLinks()">Map Link Structure</button>
    </div>
    <div id="l-results"></div>
  </div>
</div>

<script>
const BASE = 'http://localhost:8003';
function sw(name) {
  const names = ['analyze','sitemap','compare','links'];
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', names[i]===name));
  document.querySelectorAll('.panel').forEach((p,i) => p.classList.toggle('active', names[i]===name));
}
function loader(id, msg='Fetching page...') {
  document.getElementById(id).innerHTML = `<div class="loader"><div class="spinner"></div>${msg}</div>`;
}
function err(id, msg) {
  document.getElementById(id).innerHTML = `<div class="error">⚠️ ${msg}</div>`;
}

async function loadAnalyze() {
  const url = document.getElementById('a-url').value.trim();
  if (!url) return;
  loader('a-results');
  try {
    const r = await fetch(`${BASE}/api/analyze?url=${encodeURIComponent(url)}`);
    const d = await r.json();
    if (d.error) { err('a-results', d.error); return; }
    document.getElementById('a-results').innerHTML = `
      <div class="stat-row">
        <div class="stat"><div class="stat-val">${d.word_count.toLocaleString()}</div><div class="stat-label">Word Count</div></div>
        <div class="stat"><div class="stat-val">${d.h1s.length}</div><div class="stat-label">H1 Tags</div></div>
        <div class="stat"><div class="stat-val">${d.h2s.length}</div><div class="stat-label">H2 Tags</div></div>
        <div class="stat"><div class="stat-val">${d.internal_link_count}</div><div class="stat-label">Internal Links</div></div>
      </div>
      <div class="result-block">
        <h3>📄 Page Metadata</h3>
        <div class="meta-row"><span class="meta-label">Title</span><span class="meta-val">${d.title||'—'}</span></div>
        <div class="meta-row"><span class="meta-label">Meta Description</span><span class="meta-val">${d.meta_description||'—'}</span></div>
        <div class="meta-row"><span class="meta-label">Domain</span><span class="meta-val">${d.domain}</span></div>
      </div>
      ${d.h1s.length||d.h2s.length?`<div class="result-block">
        <h3>📐 Content Structure</h3>
        ${d.h1s.length?`<div style="margin-bottom:10px"><strong style="font-size:12px;color:#94a3b8">H1:</strong> ${d.h1s.map(h=>`<span class="h-tag">${h}</span>`).join('')}</div>`:''}
        ${d.h2s.length?`<div><strong style="font-size:12px;color:#94a3b8">H2:</strong> ${d.h2s.map(h=>`<span class="h-tag">${h}</span>`).join('')}</div>`:''}
      </div>`:''}
      <div class="result-block">
        <h3>🔑 Top Keywords (by frequency)</h3>
        <div class="kw-grid">
          ${d.top_keywords.map(k=>`<div class="kw-card"><span class="kw-text">${k.keyword}</span><span class="kw-freq">${k.frequency}x</span></div>`).join('')}
        </div>
      </div>`;
  } catch(e) { err('a-results', e.message); }
}

async function loadSitemap() {
  const domain = document.getElementById('sm-domain').value.trim();
  if (!domain) return;
  loader('sm-results', 'Checking sitemap...');
  try {
    const r = await fetch(`${BASE}/api/sitemap?domain=${encodeURIComponent(domain)}`);
    const d = await r.json();
    if (d.error) { err('sm-results', d.error); return; }
    const fa = d.frequency_analysis;
    document.getElementById('sm-results').innerHTML = `
      <div class="stat-row">
        <div class="stat"><div class="stat-val">${d.total_urls_found}</div><div class="stat-label">URLs in Sitemap</div></div>
        <div class="stat"><div class="stat-val">${fa.avg_posts_per_month||'—'}</div><div class="stat-label">Avg Posts/Month</div></div>
        <div class="stat"><div class="stat-val" style="font-size:14px">${fa.most_recent||'—'}</div><div class="stat-label">Most Recent</div></div>
      </div>
      ${fa.posts_per_month?`<div class="result-block">
        <h3>📅 Publish Frequency (last 12 months)</h3>
        ${Object.entries(fa.posts_per_month).map(([month,count])=>`
          <div class="month-row"><span>${month}</span><span style="font-weight:700;color:#6366f1">${count} posts</span></div>
        `).join('')}
      </div>`:''}
      <div class="result-block">
        <h3>🆕 Recent URLs</h3>
        <div class="link-list">${d.recent_urls.map(u=>`<div>${u}</div>`).join('')}</div>
      </div>`;
  } catch(e) { err('sm-results', e.message); }
}

async function loadCompare() {
  const url1 = document.getElementById('c-url1').value.trim();
  const url2 = document.getElementById('c-url2').value.trim();
  if (!url1 || !url2) return;
  loader('c-results', 'Comparing pages...');
  try {
    const r = await fetch(`${BASE}/api/compare?url1=${encodeURIComponent(url1)}&url2=${encodeURIComponent(url2)}`);
    const d = await r.json();
    if (d.error1 || d.error2) { err('c-results', d.error1||d.error2); return; }
    document.getElementById('c-results').innerHTML = `
      <div class="result-block">
        <h3>⚔️ ${d.page1.domain} vs ${d.page2.domain}</h3>
        <div class="meta-row"><span class="meta-label">${d.page1.domain}</span><span class="meta-val">${d.page1.word_count} words</span></div>
        <div class="meta-row"><span class="meta-label">${d.page2.domain}</span><span class="meta-val">${d.page2.word_count} words</span></div>
      </div>
      <div class="gap-grid">
        <div class="gap-col">
          <h4>🟢 Only in ${d.page1.domain} (${d.gap_count_page1})</h4>
          ${d.unique_to_page1.map(k=>`<div class="gap-item">${k}</div>`).join('')||'<div class="gap-item" style="color:#475569">None</div>'}
        </div>
        <div class="gap-col">
          <h4>🔴 Only in ${d.page2.domain} (${d.gap_count_page2}) — content gap to fill</h4>
          ${d.unique_to_page2.map(k=>`<div class="gap-item">${k}</div>`).join('')||'<div class="gap-item" style="color:#475569">None</div>'}
        </div>
      </div>
      <div class="result-block" style="margin-top:16px">
        <h3>🤝 Shared Keywords (${d.shared_keywords.length})</h3>
        <div class="kw-grid">${d.shared_keywords.map(k=>`<div class="kw-card"><span class="kw-text">${k}</span></div>`).join('')}</div>
      </div>`;
  } catch(e) { err('c-results', e.message); }
}

async function loadLinks() {
  const url = document.getElementById('l-url').value.trim();
  if (!url) return;
  loader('l-results', 'Mapping link structure...');
  try {
    const r = await fetch(`${BASE}/api/links?url=${encodeURIComponent(url)}`);
    const d = await r.json();
    if (d.error) { err('l-results', d.error); return; }
    document.getElementById('l-results').innerHTML = `
      <div class="stat-row">
        <div class="stat"><div class="stat-val">${d.internal_link_count}</div><div class="stat-label">Internal Links</div></div>
        <div class="stat"><div class="stat-val">${d.external_link_count}</div><div class="stat-label">External Links</div></div>
      </div>
      <div class="result-block">
        <h3>🔗 Internal Links (${d.internal_links.length})</h3>
        <div class="link-list">${d.internal_links.map(u=>`<div>${u}</div>`).join('')}</div>
      </div>
      <div class="result-block">
        <h3>🌐 External Links (${d.external_links.length})</h3>
        <div class="link-list">${d.external_links.map(u=>`<div>${u}</div>`).join('')}</div>
      </div>`;
  } catch(e) { err('l-results', e.message); }
}
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTML

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003, log_level="warning")
