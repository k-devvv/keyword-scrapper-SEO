"""
Module 2 — SERP Analysis (Bing-powered)
Google blocks scrapers with reCAPTCHA at scale. Bing has far looser bot
detection and is genuinely free to scrape — same SEO value, Bing's ranking
instead of Google's, but rankings correlate heavily so this is a valid proxy.

- Top 10 results scraper (Bing)
- SERP feature detector
- Title + meta extractor
- Domain frequency counter
- Average word count estimator
"""

import sys
import logging
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

import json
import time
import re
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, quote_plus
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="SERP Analysis Module (Bing)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REGION_MARKET = {
    "IN": "en-IN", "US": "en-US", "GB": "en-GB", "AU": "en-AU",
    "CA": "en-CA", "SG": "en-SG", "DE": "de-DE", "FR": "fr-FR",
    "BR": "pt-BR", "JP": "ja-JP", "ZA": "en-ZA", "NG": "en-NG",
    "MX": "es-MX", "KR": "ko-KR",
}

# ── Core SERP scraper (Bing, via Playwright — Bing renders results with JS) ──

async def scrape_serp_bing(keyword: str, region: str = "IN", num: int = 10) -> Dict:
    """Scrape Bing SERP for a keyword using a real headless browser."""
    from playwright.async_api import async_playwright

    mkt = REGION_MARKET.get(region.upper(), "en-US")
    cc = region.upper()
    results = []
    features = {
        "featured_snippet": False,
        "people_also_ask": False,
        "video_results": False,
        "shopping": False,
        "local_pack": False,
        "image_pack": False,
        "knowledge_panel": False,
        "top_stories": False,
        "news_results": False,
    }
    try:
        url = f"https://www.bing.com/search?q={quote_plus(keyword)}&mkt={mkt}&cc={cc}&count={num}"
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                locale="en-US",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1800)
            html = await page.content()
            await browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # ── Detect features ───────────────────────────────────────────────────
        if soup.find("div", {"class": re.compile(r"b_ans|b_topAns|b_xlText")}):
            features["featured_snippet"] = True
        if soup.find("div", {"class": re.compile(r"b_rrsr|b_qna")}) or "people also ask" in r.text.lower():
            features["people_also_ask"] = True
        if soup.find("div", {"class": re.compile(r"b_videos|dg_u|mc_vtvc")}):
            features["video_results"] = True
        if soup.find("li", {"class": re.compile(r"b_ad|cpr_ad")}) or soup.find("div", {"class": "b_pag"}):
            features["shopping"] = True if soup.find("div", {"class": re.compile(r"pa_btn|br_addtoCart")}) else False
        if soup.find("div", {"class": re.compile(r"b_local|lcl_map")}):
            features["local_pack"] = True
        if soup.find("div", {"class": re.compile(r"dg_u|b_imgcap|b_imagePivot")}):
            features["image_pack"] = True
        if soup.find("div", {"class": re.compile(r"b_entityTP|b_factrow|wikipedia")}):
            features["knowledge_panel"] = True
        if soup.find("div", {"class": re.compile(r"b_nws|na_cnt")}):
            features["news_results"] = True
            features["top_stories"] = True

        # ── Extract organic results ───────────────────────────────────────────
        seen = set()
        for li in soup.select("li.b_algo"):
            try:
                h2 = li.find("h2")
                link = h2.find("a") if h2 else None
                if not h2 or not link:
                    continue
                href = link.get("href", "")
                if not href.startswith("http") or href in seen:
                    continue
                seen.add(href)
                domain = urlparse(href).netloc.replace("www.", "")
                snippet_el = li.select_one("div.b_caption p, p.b_lineclamp4, div.b_snippet")
                snippet = snippet_el.get_text(strip=True)[:300] if snippet_el else ""
                results.append({
                    "rank": len(results) + 1,
                    "title": h2.get_text(strip=True),
                    "url": href,
                    "domain": domain,
                    "snippet": snippet,
                })
                if len(results) >= num:
                    break
            except Exception:
                continue

        return {"results": results, "features": features}
    except Exception as e:
        return {"error": str(e), "results": [], "features": features}


def scrape_page_content(url: str) -> Dict:
    """Scrape a single page for title, meta, word count, H1/H2s."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        title = soup.find("title")
        title = title.get_text(strip=True)[:120] if title else ""
        meta = soup.find("meta", {"name": re.compile(r"description", re.I)})
        meta = meta.get("content", "")[:200] if meta else ""
        h1s = [h.get_text(strip=True) for h in soup.find_all("h1")][:3]
        h2s = [h.get_text(strip=True) for h in soup.find_all("h2")][:8]
        word_count = len(soup.get_text(separator=" ", strip=True).split())

        return {"title": title, "meta_description": meta, "h1s": h1s, "h2s": h2s, "word_count": word_count, "url": url}
    except Exception as e:
        return {"error": str(e), "url": url, "word_count": 0, "h2s": [], "h1s": []}


def get_domain_frequency(results):
    freq = {}
    for r in results:
        d = r.get("domain", "")
        freq[d] = freq.get(d, 0) + 1
    return sorted([{"domain": d, "count": c} for d, c in freq.items()], key=lambda x: -x["count"])


# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/api/serp")
async def serp(keyword: str, region: str = "IN", num: int = 10):
    data = await scrape_serp_bing(keyword, region=region, num=num)
    if "error" in data and not data.get("results"):
        return JSONResponse(status_code=500, content={"error": data["error"]})
    return {
        "keyword": keyword, "region": region,
        "results": data.get("results", []),
        "features": data.get("features", {}),
        "domain_frequency": get_domain_frequency(data.get("results", [])),
        "result_count": len(data.get("results", [])),
        "source": "bing",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/serp/deep")
async def serp_deep(keyword: str, region: str = "IN"):
    data = await scrape_serp_bing(keyword, region=region, num=10)
    results = data.get("results", [])
    enriched = []
    for res in results[:5]:
        content = scrape_page_content(res["url"])
        enriched.append({**res, **content})
        time.sleep(1)
    avg_wc = int(sum(r.get("word_count", 0) for r in enriched) / len(enriched)) if enriched else 0
    return {
        "keyword": keyword, "region": region,
        "top_5_analysis": enriched,
        "avg_word_count": avg_wc,
        "recommended_word_count": int(avg_wc * 1.2),
        "features": data.get("features", {}),
        "source": "bing",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/serp/features")
async def serp_features(keyword: str, region: str = "IN"):
    data = await scrape_serp_bing(keyword, region=region, num=10)
    features = data.get("features", {})
    active = [k for k, v in features.items() if v]
    return {
        "keyword": keyword, "region": region,
        "features": features, "active_features": active,
        "feature_count": len(active),
        "source": "bing",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/serp/domains")
async def serp_domains(keywords: str, region: str = "IN"):
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()][:5]
    domain_map: Dict = {}
    for kw in kw_list:
        data = await scrape_serp_bing(kw, region=region, num=10)
        for res in data.get("results", []):
            d = res["domain"]
            if d not in domain_map:
                domain_map[d] = {"domain": d, "total_appearances": 0, "keywords": []}
            domain_map[d]["total_appearances"] += 1
            if kw not in domain_map[d]["keywords"]:
                domain_map[d]["keywords"].append(kw)
        time.sleep(1.5)
    sorted_domains = sorted(domain_map.values(), key=lambda x: -x["total_appearances"])
    return {
        "keywords": kw_list, "region": region,
        "domain_dominance": sorted_domains[:20],
        "source": "bing",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SERP Analysis</title>
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
input, select { background: #1e1e30; border: 1px solid #3d3d5c; color: #e2e8f0; padding: 9px 14px; border-radius: 8px; font-size: 14px; }
input { flex: 1; min-width: 220px; }
button { background: #6366f1; color: white; border: none; padding: 9px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; }
button:hover { background: #4f46e5; }
.result-block { background: #1a1a2e; border: 1px solid #2d2d44; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
.result-block h3 { font-size: 13px; font-weight: 700; color: #6366f1; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; }
.serp-card { background: #12121f; border: 1px solid #2d2d44; border-radius: 10px; padding: 16px; margin-bottom: 10px; }
.serp-rank { font-size: 11px; color: #6366f1; font-weight: 800; margin-bottom: 6px; }
.serp-title a { color: #818cf8; text-decoration: none; font-size: 16px; font-weight: 700; }
.serp-title a:hover { text-decoration: underline; }
.serp-url { font-size: 12px; color: #10b981; margin: 4px 0 8px; }
.serp-snippet { font-size: 13px; color: #94a3b8; line-height: 1.6; }
.feature-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; margin-bottom: 16px; }
.feature-card { background: #12121f; border: 1px solid #2d2d44; border-radius: 8px; padding: 12px; text-align: center; }
.feature-card.active { border-color: #6366f1; background: #1a1a2e; }
.feature-icon { font-size: 24px; margin-bottom: 6px; }
.feature-name { font-size: 12px; font-weight: 600; }
.feature-card.active .feature-name { color: #6366f1; }
.feature-card:not(.active) .feature-name { color: #475569; }
.domain-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #2d2d44; flex-wrap: wrap; gap: 8px; }
.domain-row:last-child { border: none; }
.bar-wrap { flex: 1; margin: 0 14px; background: #2d2d44; border-radius: 2px; height: 6px; min-width: 60px; }
.bar { height: 6px; background: #6366f1; border-radius: 2px; }
.loader { text-align: center; padding: 60px; color: #64748b; }
.spinner { width: 36px; height: 36px; border: 3px solid #2d2d44; border-top-color: #6366f1; border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
@keyframes spin { to { transform: rotate(360deg); } }
.error { background: #450a0a; border: 1px solid #7f1d1d; color: #fca5a5; padding: 14px; border-radius: 8px; }
.deep-card { background: #12121f; border: 1px solid #2d2d44; border-radius: 10px; padding: 16px; margin-bottom: 12px; }
.deep-title { font-size: 15px; font-weight: 700; color: #818cf8; margin-bottom: 8px; }
.deep-meta { font-size: 13px; color: #64748b; margin-bottom: 8px; line-height: 1.5; }
.deep-stats { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.stat-pill { background: #1a1a2e; border: 1px solid #2d2d44; border-radius: 99px; padding: 4px 12px; font-size: 12px; }
.h2-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.h2-tag { background: #2d2d44; color: #94a3b8; padding: 3px 10px; border-radius: 6px; font-size: 12px; }
.wc-banner { background: #1a1a2e; border: 1px solid #6366f144; border-radius: 10px; padding: 16px 20px; margin-bottom: 20px; display: flex; gap: 30px; align-items: center; flex-wrap: wrap; }
.wc-stat { text-align: center; }
.wc-val { font-size: 28px; font-weight: 800; color: #6366f1; }
.wc-label { font-size: 12px; color: #64748b; margin-top: 2px; }
.kw-tag { background: #2d2d44; color: #94a3b8; padding: 3px 8px; border-radius: 6px; font-size: 11px; }
.note { font-size: 12px; color: #475569; background: #1a1a2e; border: 1px solid #2d2d44; padding: 10px 14px; border-radius: 8px; margin-bottom: 16px; }
.bing-badge { display: inline-block; background: #008373; color: white; font-size: 10px; padding: 2px 8px; border-radius: 4px; margin-left: 8px; font-weight: 700; }
</style>
</head>
<body>
<header>
  <h1>🔎 SERP Analysis <span class="bing-badge">BING-POWERED</span></h1>
  <div class="nav-links">
    <a href="http://localhost:8001">← Keyword Research</a>
    <a href="http://localhost:8000">← Trends Dashboard</a>
  </div>
</header>
<div class="container">
  <div class="note">ℹ️ Powered by Bing (Google blocks free scrapers with reCAPTCHA at scale). Bing rankings correlate strongly with Google for SEO purposes — same actionable insights, zero cost.</div>
  <div class="tabs">
    <div class="tab active" onclick="sw('serp')">📋 Top 10 Results</div>
    <div class="tab" onclick="sw('deep')">🔬 Deep Analysis</div>
    <div class="tab" onclick="sw('features')">⚡ SERP Features</div>
    <div class="tab" onclick="sw('domains')">🏆 Domain Dominance</div>
  </div>

  <div id="tab-serp" class="panel active">
    <div class="search-row">
      <input id="s-kw" placeholder="Keyword e.g. best SEO tools" value="best SEO tools" />
      <select id="s-region">
        <option value="IN">🇮🇳 India</option><option value="US">🇺🇸 US</option>
        <option value="GB">🇬🇧 UK</option><option value="AU">🇦🇺 Australia</option>
      </select>
      <select id="s-num"><option value="5">Top 5</option><option value="10" selected>Top 10</option></select>
      <button onclick="loadSerp()">Scrape SERP</button>
    </div>
    <div id="s-results"></div>
  </div>

  <div id="tab-deep" class="panel">
    <div class="search-row">
      <input id="d-kw" placeholder="Keyword e.g. digital marketing agency" value="digital marketing agency" />
      <select id="d-region"><option value="IN">India</option><option value="US">US</option><option value="GB">UK</option></select>
      <button onclick="loadDeep()">Deep Analyze Top 5</button>
    </div>
    <div id="d-results"></div>
  </div>

  <div id="tab-features" class="panel">
    <div class="search-row">
      <input id="f-kw" placeholder="Keyword e.g. how to lose weight" value="how to lose weight" />
      <select id="f-region"><option value="IN">India</option><option value="US">US</option><option value="GB">UK</option></select>
      <button onclick="loadFeatures()">Detect Features</button>
    </div>
    <div id="f-results"></div>
  </div>

  <div id="tab-domains" class="panel">
    <div class="search-row">
      <input id="dm-kws" placeholder="Keywords comma separated e.g. SEO tools,keyword research" value="SEO tools,keyword research,backlink checker" />
      <select id="dm-region"><option value="IN">India</option><option value="US">US</option><option value="GB">UK</option></select>
      <button onclick="loadDomains()">Analyze Dominance</button>
    </div>
    <div id="dm-results"></div>
  </div>
</div>

<script>
const BASE = 'http://localhost:8002';
const FEATURE_META = {
  featured_snippet:  { icon: '⭐', label: 'Featured Snippet' },
  people_also_ask:   { icon: '❓', label: 'People Also Ask' },
  video_results:     { icon: '🎥', label: 'Video Results' },
  shopping:          { icon: '🛒', label: 'Shopping' },
  local_pack:        { icon: '📍', label: 'Local Pack' },
  image_pack:        { icon: '🖼️', label: 'Image Pack' },
  knowledge_panel:   { icon: '📚', label: 'Knowledge Panel' },
  top_stories:       { icon: '📰', label: 'Top Stories' },
  news_results:      { icon: '🗞️', label: 'News Results' },
};
function sw(name) {
  const names = ['serp','deep','features','domains'];
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', names[i]===name));
  document.querySelectorAll('.panel').forEach((p,i) => p.classList.toggle('active', names[i]===name));
}
function loader(id, msg='Scraping Bing...') {
  document.getElementById(id).innerHTML = `<div class="loader"><div class="spinner"></div>${msg}</div>`;
}
function err(id, msg) {
  document.getElementById(id).innerHTML = `<div class="error">⚠️ ${msg}</div>`;
}
async function loadSerp() {
  const kw = document.getElementById('s-kw').value.trim();
  const region = document.getElementById('s-region').value;
  const num = document.getElementById('s-num').value;
  if (!kw) return;
  loader('s-results');
  try {
    const r = await fetch(`${BASE}/api/serp?keyword=${encodeURIComponent(kw)}&region=${region}&num=${num}`);
    const d = await r.json();
    if (d.error && !d.results?.length) { err('s-results', d.error); return; }
    const activeFeatures = Object.entries(d.features||{}).filter(([,v])=>v);
    document.getElementById('s-results').innerHTML = `
      ${activeFeatures.length ? `<div class="result-block"><h3>⚡ SERP Features (${activeFeatures.length})</h3>
        <div class="feature-grid">${Object.entries(d.features).map(([k,v])=>`
          <div class="feature-card ${v?'active':''}">
            <div class="feature-icon">${FEATURE_META[k]?.icon||'•'}</div>
            <div class="feature-name">${FEATURE_META[k]?.label||k}</div>
          </div>`).join('')}</div></div>` : ''}
      <div class="result-block"><h3>📋 Top ${d.result_count} Results — "${d.keyword}" (${d.region})</h3>
        ${d.results.length ? d.results.map(res=>`
          <div class="serp-card">
            <div class="serp-rank">#${res.rank}</div>
            <div class="serp-title"><a href="${res.url}" target="_blank">${res.title}</a></div>
            <div class="serp-url">${res.domain}</div>
            ${res.snippet?`<div class="serp-snippet">${res.snippet}</div>`:''}
          </div>`).join('') : '<div style="color:#64748b;padding:20px">No results found.</div>'}
      </div>
      ${d.domain_frequency?.length>1?`<div class="result-block"><h3>🏆 Domain Frequency</h3>
        ${d.domain_frequency.map(df=>`<div class="domain-row">
          <span style="min-width:180px;font-weight:600">${df.domain}</span>
          <div class="bar-wrap"><div class="bar" style="width:${df.count/d.domain_frequency[0].count*100}%"></div></div>
          <span style="font-weight:700;color:#6366f1">${df.count}x</span>
        </div>`).join('')}</div>` : ''}`;
  } catch(e) { err('s-results', e.message); }
}
async function loadDeep() {
  const kw = document.getElementById('d-kw').value.trim();
  const region = document.getElementById('d-region').value;
  if (!kw) return;
  loader('d-results', 'Fetching + analyzing top 5 pages...');
  try {
    const r = await fetch(`${BASE}/api/serp/deep?keyword=${encodeURIComponent(kw)}&region=${region}`);
    const d = await r.json();
    if (d.error) { err('d-results', d.error); return; }
    document.getElementById('d-results').innerHTML = `
      <div class="wc-banner">
        <div class="wc-stat"><div class="wc-val">${d.avg_word_count.toLocaleString()}</div><div class="wc-label">Avg Word Count</div></div>
        <div class="wc-stat"><div class="wc-val" style="color:#10b981">${d.recommended_word_count.toLocaleString()}</div><div class="wc-label">Recommended to Outrank</div></div>
        <div style="font-size:13px;color:#64748b;flex:1">Write at least <strong style="color:#10b981">${d.recommended_word_count.toLocaleString()} words</strong> to outrank top 5 for "<strong style="color:#e2e8f0">${d.keyword}</strong>"</div>
      </div>
      <div class="result-block"><h3>🔬 Top 5 Page Analysis</h3>
        ${d.top_5_analysis.map(p=>`<div class="deep-card">
          <div class="serp-rank">#${p.rank} — <a href="${p.url}" target="_blank" style="color:#10b981;font-size:12px">${p.domain}</a></div>
          <div class="deep-title">${p.title||'—'}</div>
          ${p.meta_description?`<div class="deep-meta">📝 ${p.meta_description}</div>`:''}
          <div class="deep-stats">
            <span class="stat-pill">📝 ${(p.word_count||0).toLocaleString()} words</span>
            ${p.h1s?.length?`<span class="stat-pill">H1: ${p.h1s[0]?.substring(0,50)||'—'}</span>`:''}
          </div>
          ${p.h2s?.length?`<div class="h2-list">${p.h2s.map(h=>`<span class="h2-tag">${h.substring(0,60)}</span>`).join('')}</div>`:''}
        </div>`).join('')}
      </div>`;
  } catch(e) { err('d-results', e.message); }
}
async function loadFeatures() {
  const kw = document.getElementById('f-kw').value.trim();
  const region = document.getElementById('f-region').value;
  if (!kw) return;
  loader('f-results', 'Detecting SERP features...');
  try {
    const r = await fetch(`${BASE}/api/serp/features?keyword=${encodeURIComponent(kw)}&region=${region}`);
    const d = await r.json();
    if (d.error) { err('f-results', d.error); return; }
    document.getElementById('f-results').innerHTML = `
      <div class="result-block"><h3>⚡ SERP Features — "${d.keyword}" — ${d.feature_count} active</h3>
        <div class="feature-grid">${Object.entries(d.features).map(([k,v])=>`
          <div class="feature-card ${v?'active':''}">
            <div class="feature-icon">${FEATURE_META[k]?.icon||'•'}</div>
            <div class="feature-name">${FEATURE_META[k]?.label||k}</div>
            <div style="font-size:11px;margin-top:4px;color:${v?'#4ade80':'#475569'}">${v?'✓ Present':'✗ Not found'}</div>
          </div>`).join('')}
        </div>
      </div>`;
  } catch(e) { err('f-results', e.message); }
}
async function loadDomains() {
  const kws = document.getElementById('dm-kws').value.trim();
  const region = document.getElementById('dm-region').value;
  if (!kws) return;
  loader('dm-results', 'Analyzing domain dominance...');
  try {
    const r = await fetch(`${BASE}/api/serp/domains?keywords=${encodeURIComponent(kws)}&region=${region}`);
    const d = await r.json();
    if (d.error) { err('dm-results', d.error); return; }
    const top = d.domain_dominance[0]?.total_appearances||1;
    document.getElementById('dm-results').innerHTML = `
      <div class="result-block"><h3>🏆 Domain Dominance — ${d.keywords.length} keywords</h3>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">${d.keywords.map(k=>`<span class="kw-tag">${k}</span>`).join('')}</div>
        ${d.domain_dominance.map(dom=>`<div class="domain-row">
          <span style="min-width:180px;font-weight:600">${dom.domain}</span>
          <div class="bar-wrap"><div class="bar" style="width:${dom.total_appearances/top*100}%"></div></div>
          <span style="font-weight:700;color:#6366f1;min-width:30px">${dom.total_appearances}x</span>
          <div style="display:flex;gap:4px;flex-wrap:wrap">${dom.keywords.map(k=>`<span class="kw-tag">${k}</span>`).join('')}</div>
        </div>`).join('')}
      </div>`;
  } catch(e) { err('dm-results', e.message); }
}
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTML

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="warning")
