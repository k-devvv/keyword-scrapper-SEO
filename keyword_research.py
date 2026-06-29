"""
Module 1 — Keyword Research
- Long-tail expander
- Search intent classifier
- Seasonal trend detector
- Keyword comparison
- Breakout keywords detector
"""

import sys
import logging
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

import json
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import requests
from bs4 import BeautifulSoup
import time
import random

app = FastAPI(title="Keyword Research Module")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def google_autocomplete(keyword: str, lang: str = "en", region: str = "IN") -> List[str]:
    """Fetch Google autocomplete suggestions — zero cost, no API key."""
    suggestions = []
    try:
        url = f"http://suggestqueries.google.com/complete/search?client=firefox&q={requests.utils.quote(keyword)}&hl={lang}&gl={region.lower()}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        suggestions = data[1] if len(data) > 1 else []
    except Exception as e:
        logging.warning(f"Autocomplete failed: {e}")
    return suggestions


def google_related_searches(keyword: str, region: str = "IN") -> List[str]:
    """Scrape 'related searches' from Google SERP bottom."""
    related = []
    try:
        url = f"https://www.google.com/search?q={requests.utils.quote(keyword)}&gl={region.lower()}&hl=en"
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        # Related searches are in <a> tags inside specific containers
        for tag in soup.select("div.k8XOCe a, a.gL9Hy, div[data-q] a"):
            text = tag.get_text(strip=True)
            if text and text not in related:
                related.append(text)
        # Also try another selector
        if not related:
            for tag in soup.find_all("p", {"data-q": True}):
                text = tag.get_text(strip=True)
                if text:
                    related.append(text)
    except Exception as e:
        logging.warning(f"Related searches scrape failed: {e}")
    return related[:10]


def people_also_ask(keyword: str, region: str = "IN") -> List[str]:
    """Scrape People Also Ask questions from Google."""
    questions = []
    try:
        url = f"https://www.google.com/search?q={requests.utils.quote(keyword)}&gl={region.lower()}&hl=en"
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup.select("div.related-question-pair span, div[jsname] .iDjcJe, .JlqpRe"):
            text = tag.get_text(strip=True)
            if text and "?" in text and text not in questions:
                questions.append(text)
    except Exception as e:
        logging.warning(f"PAA scrape failed: {e}")
    return questions[:10]


def classify_intent(keyword: str) -> Dict[str, Any]:
    """
    Rule-based search intent classifier.
    No API needed — pattern matching on keyword signals.
    """
    kw = keyword.lower().strip()
    
    informational_signals = [
        "what", "how", "why", "when", "who", "where", "which", "explain",
        "guide", "tutorial", "learn", "tips", "tricks", "examples", "meaning",
        "definition", "history", "difference between", "vs", "compare"
    ]
    commercial_signals = [
        "best", "top", "review", "reviews", "comparison", "vs", "alternative",
        "alternatives", "recommend", "recommended", "rated", "ranking", "worth it"
    ]
    transactional_signals = [
        "buy", "price", "cheap", "discount", "deal", "offer", "coupon", "order",
        "purchase", "shop", "free", "download", "get", "hire", "book", "subscribe"
    ]
    navigational_signals = [
        "login", "sign in", "sign up", "account", "official", "website", "app",
        "contact", "support", "near me", "location", "address", "number"
    ]

    scores = {
        "informational": sum(1 for s in informational_signals if s in kw),
        "commercial": sum(1 for s in commercial_signals if s in kw),
        "transactional": sum(1 for s in transactional_signals if s in kw),
        "navigational": sum(1 for s in navigational_signals if s in kw),
    }

    intent = max(scores, key=scores.get)
    if all(v == 0 for v in scores.values()):
        intent = "informational"  # default

    intent_meta = {
        "informational": {"color": "#3b82f6", "icon": "📚", "desc": "User wants to learn"},
        "commercial": {"color": "#f59e0b", "icon": "🔍", "desc": "User is comparing options"},
        "transactional": {"color": "#10b981", "icon": "💳", "desc": "User wants to buy/act"},
        "navigational": {"color": "#8b5cf6", "icon": "🧭", "desc": "User wants a specific site"},
    }

    return {
        "intent": intent,
        "confidence": "high" if scores[intent] >= 2 else "medium" if scores[intent] == 1 else "low",
        "scores": scores,
        **intent_meta[intent],
    }


def get_pytrends_data(keywords: List[str], timeframe: str = "today 3-m", geo: str = "IN") -> Dict:
    """Fetch comparison + seasonal data from pytrends."""
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=330, timeout=(10, 30))
        kws = keywords[:5]  # pytrends max 5
        pt.build_payload(kws, timeframe=timeframe, geo=geo)
        iot = pt.interest_over_time()
        if iot.empty:
            return {"error": "No data returned"}
        
        result = {}
        for kw in kws:
            if kw in iot.columns:
                vals = iot[kw].tolist()
                dates = [str(d.date()) for d in iot.index.tolist()]
                recent = vals[-7:] if len(vals) >= 7 else vals
                baseline = vals[:7] if len(vals) >= 7 else vals
                recent_avg = sum(recent) / len(recent) if recent else 0
                baseline_avg = sum(baseline) / len(baseline) if baseline else 1
                growth = round((recent_avg - baseline_avg) / baseline_avg * 100, 1) if baseline_avg else 0
                
                result[kw] = {
                    "values": vals,
                    "dates": dates,
                    "peak": max(vals),
                    "current": vals[-1] if vals else 0,
                    "growth_pct": growth,
                    "trend": "📈 Rising" if growth > 20 else "📉 Declining" if growth < -20 else "➡️ Stable",
                }
        return result
    except Exception as e:
        return {"error": str(e)}


def detect_breakouts(keywords: List[str], geo: str = "IN") -> List[Dict]:
    """Detect keywords with explosive recent growth using pytrends."""
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=330, timeout=(10, 30))
        breakouts = []
        
        for i in range(0, len(keywords), 5):
            batch = keywords[i:i+5]
            try:
                pt.build_payload(batch, timeframe="now 7-d", geo=geo)
                iot = pt.interest_over_time()
                if iot.empty:
                    continue
                for kw in batch:
                    if kw not in iot.columns:
                        continue
                    vals = iot[kw].tolist()
                    if len(vals) < 4:
                        continue
                    mid = len(vals) // 2
                    first_half = sum(vals[:mid]) / mid if mid else 1
                    second_half = sum(vals[mid:]) / (len(vals) - mid)
                    growth = round((second_half - first_half) / first_half * 100, 1) if first_half > 0 else 0
                    breakouts.append({
                        "keyword": kw,
                        "growth_pct": growth,
                        "current_interest": vals[-1],
                        "is_breakout": growth >= 100,
                        "label": "🔥 Breakout" if growth >= 200 else "📈 Surging" if growth >= 100 else "↗️ Growing" if growth >= 20 else "➡️ Stable",
                    })
                time.sleep(1)
            except Exception:
                continue
        
        return sorted(breakouts, key=lambda x: x["growth_pct"], reverse=True)
    except Exception as e:
        return [{"error": str(e)}]


# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/api/longtail")
async def longtail(keyword: str, region: str = "IN"):
    """Long-tail keyword expander using Google autocomplete."""
    try:
        modifiers = [
            "", "how to", "best", "what is", "why", "when", "free",
            "top", "vs", "for beginners", "tutorial", "guide", "tips",
            "2024", "2025", "online", "near me", "without", "with",
        ]
        all_suggestions = set()
        
        # Base autocomplete
        base = google_autocomplete(keyword, region=region)
        all_suggestions.update(base)
        
        # Alphabet expansion (a-z prefix)
        for char in "abcdefghijklmnoprstw":
            suggestions = google_autocomplete(f"{keyword} {char}", region=region)
            all_suggestions.update(suggestions)
            if len(all_suggestions) >= 60:
                break
            time.sleep(0.2)
        
        # Modifier expansion
        for mod in modifiers[:8]:
            q = f"{mod} {keyword}".strip()
            suggestions = google_autocomplete(q, region=region)
            all_suggestions.update(suggestions)
        
        # Filter — remove exact match, keep only related
        results = [s for s in all_suggestions if keyword.lower() in s.lower() or any(w in s.lower() for w in keyword.lower().split())]
        results = sorted(set(results))[:60]
        
        # Classify intent for each
        enriched = []
        for kw in results:
            intent = classify_intent(kw)
            enriched.append({
                "keyword": kw,
                "intent": intent["intent"],
                "intent_icon": intent["icon"],
                "intent_color": intent["color"],
            })
        
        return {
            "seed": keyword,
            "region": region,
            "count": len(enriched),
            "keywords": enriched,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/intent")
async def intent(keyword: str):
    """Classify search intent for a keyword."""
    try:
        result = classify_intent(keyword)
        paa = people_also_ask(keyword)
        return {
            "keyword": keyword,
            "intent": result,
            "people_also_ask": paa,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/compare")
async def compare(keywords: str, region: str = "IN", timeframe: str = "today 3-m"):
    """Compare multiple keywords over time using pytrends."""
    try:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()][:5]
        data = get_pytrends_data(kw_list, timeframe=timeframe, geo=region)
        return {
            "keywords": kw_list,
            "region": region,
            "timeframe": timeframe,
            "data": data,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/breakout")
async def breakout(keywords: str, region: str = "IN"):
    """Detect breakout keywords from a comma-separated list."""
    try:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()][:15]
        results = detect_breakouts(kw_list, geo=region)
        return {
            "keywords": kw_list,
            "region": region,
            "results": results,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/seasonal")
async def seasonal(keyword: str, region: str = "IN"):
    """Detect seasonal patterns for a keyword over 12 months."""
    try:
        data = get_pytrends_data([keyword], timeframe="today 12-m", geo=region)
        if "error" in data:
            return JSONResponse(status_code=500, content=data)
        kw_data = data.get(keyword, {})
        return {
            "keyword": keyword,
            "region": region,
            "seasonal_data": kw_data,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Keyword Research</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f13; color: #e2e8f0; min-height: 100vh; }
header { background: #1a1a2e; padding: 16px 32px; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #2d2d44; }
header h1 { font-size: 20px; font-weight: 700; color: #fff; }
header a { font-size: 13px; color: #6366f1; text-decoration: none; margin-left: auto; }
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
.result-block h3 { font-size: 13px; font-weight: 700; color: #6366f1; margin-bottom: 14px; text-transform: uppercase; letter-spacing: 1px; }
.kw-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
.kw-card { background: #12121f; border: 1px solid #2d2d44; border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 6px; }
.kw-text { font-size: 14px; font-weight: 600; color: #e2e8f0; }
.intent-badge { font-size: 11px; padding: 3px 8px; border-radius: 99px; display: inline-block; width: fit-content; }
.loader { text-align: center; padding: 60px; color: #64748b; }
.spinner { width: 36px; height: 36px; border: 3px solid #2d2d44; border-top-color: #6366f1; border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
@keyframes spin { to { transform: rotate(360deg); } }
.error { background: #450a0a; border: 1px solid #7f1d1d; color: #fca5a5; padding: 14px; border-radius: 8px; }
.compare-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #2d2d44; }
.compare-row:last-child { border: none; }
.bar-wrap { flex: 1; margin: 0 14px; background: #2d2d44; border-radius: 2px; height: 6px; }
.bar { height: 6px; border-radius: 2px; }
.trend-badge { font-size: 12px; padding: 3px 10px; border-radius: 99px; background: #1e1e30; }
.breakout-card { background: #12121f; border: 1px solid #2d2d44; border-radius: 10px; padding: 14px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.breakout-kw { font-size: 15px; font-weight: 700; }
.breakout-label { font-size: 12px; padding: 3px 10px; border-radius: 99px; background: #1a1a2e; }
.growth-pos { color: #4ade80; }
.growth-neg { color: #f87171; }
.paa-item { padding: 10px 0; border-bottom: 1px solid #2d2d44; font-size: 14px; color: #cbd5e1; }
.paa-item:last-child { border: none; }
.paa-item::before { content: "❓ "; }
.intent-big { display: flex; gap: 20px; align-items: flex-start; flex-wrap: wrap; margin-bottom: 20px; }
.intent-box { background: #12121f; border: 1px solid #2d2d44; border-radius: 12px; padding: 20px; flex: 1; min-width: 200px; text-align: center; }
.intent-icon { font-size: 36px; margin-bottom: 8px; }
.intent-name { font-size: 18px; font-weight: 800; margin-bottom: 4px; }
.intent-desc { font-size: 13px; color: #64748b; }
.score-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 13px; border-bottom: 1px solid #2d2d44; }
.seasonal-row { display: flex; justify-content: space-between; align-items: center; padding: 7px 0; border-bottom: 1px solid #2d2d44; font-size: 13px; }
.month-bar-wrap { flex: 1; margin: 0 12px; background: #2d2d44; border-radius: 2px; height: 5px; }
.month-bar { height: 5px; background: #6366f1; border-radius: 2px; }
.count-badge { font-size: 12px; background: #1e1e30; color: #6366f1; padding: 4px 10px; border-radius: 99px; margin-left: 10px; }
</style>
</head>
<body>
<header>
  <h1>🔍 Keyword Research</h1>
  <a href="http://localhost:8000">← Back to Trends Dashboard</a>
</header>
<div class="container">
  <div class="tabs">
    <div class="tab active" onclick="sw('longtail')">📝 Long-tail Expander</div>
    <div class="tab" onclick="sw('intent')">🎯 Intent Classifier</div>
    <div class="tab" onclick="sw('compare')">📊 Keyword Comparison</div>
    <div class="tab" onclick="sw('breakout')">🔥 Breakout Detector</div>
    <div class="tab" onclick="sw('seasonal')">📅 Seasonal Trends</div>
  </div>

  <!-- LONG-TAIL -->
  <div id="tab-longtail" class="panel active">
    <div class="search-row">
      <input id="lt-kw" placeholder="Seed keyword e.g. digital marketing" value="digital marketing" />
      <select id="lt-region">
        <option value="IN">🇮🇳 India</option><option value="US">🇺🇸 US</option>
        <option value="GB">🇬🇧 UK</option><option value="AU">🇦🇺 Australia</option>
      </select>
      <button onclick="loadLongtail()">Expand Keywords</button>
    </div>
    <div id="lt-results"></div>
  </div>

  <!-- INTENT -->
  <div id="tab-intent" class="panel">
    <div class="search-row">
      <input id="int-kw" placeholder="Keyword to classify e.g. best laptop 2024" value="best laptop 2024" />
      <button onclick="loadIntent()">Classify Intent</button>
    </div>
    <div id="int-results"></div>
  </div>

  <!-- COMPARE -->
  <div id="tab-compare" class="panel">
    <div class="search-row">
      <input id="cmp-kws" placeholder="Keywords comma separated e.g. AI,ChatGPT,Claude" value="AI,ChatGPT,Claude" />
      <select id="cmp-region">
        <option value="IN">India</option><option value="US">US</option><option value="GB">UK</option>
      </select>
      <select id="cmp-tf">
        <option value="now 7-d">7 Days</option>
        <option value="today 1-m">1 Month</option>
        <option value="today 3-m" selected>3 Months</option>
        <option value="today 12-m">12 Months</option>
      </select>
      <button onclick="loadCompare()">Compare</button>
    </div>
    <div id="cmp-results"></div>
  </div>

  <!-- BREAKOUT -->
  <div id="tab-breakout" class="panel">
    <div class="search-row">
      <input id="bo-kws" placeholder="Keywords to check e.g. AI agent,vibe coding,Claude,Gemini" value="AI agent,vibe coding,Claude,Gemini,n8n,LangChain" />
      <select id="bo-region">
        <option value="IN">India</option><option value="US">US</option><option value="GB">UK</option>
      </select>
      <button onclick="loadBreakout()">Detect Breakouts</button>
    </div>
    <div id="bo-results"></div>
  </div>

  <!-- SEASONAL -->
  <div id="tab-seasonal" class="panel">
    <div class="search-row">
      <input id="sea-kw" placeholder="Keyword e.g. cricket" value="cricket" />
      <select id="sea-region">
        <option value="IN">India</option><option value="US">US</option><option value="GB">UK</option>
      </select>
      <button onclick="loadSeasonal()">Analyze Seasonality</button>
    </div>
    <div id="sea-results"></div>
  </div>
</div>

<script>
const BASE = 'http://localhost:8001';
const COLORS = ['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6'];

function sw(name) {
  const names = ['longtail','intent','compare','breakout','seasonal'];
  document.querySelectorAll('.tab').forEach((t,i) => { t.classList.toggle('active', names[i]===name); });
  document.querySelectorAll('.panel').forEach((p,i) => { p.classList.toggle('active', names[i]===name); });
}
function loader(id, msg='Fetching data...') {
  document.getElementById(id).innerHTML = `<div class="loader"><div class="spinner"></div>${msg}</div>`;
}
function err(id, msg) {
  document.getElementById(id).innerHTML = `<div class="error">⚠️ ${msg}</div>`;
}

async function loadLongtail() {
  const kw = document.getElementById('lt-kw').value.trim();
  const region = document.getElementById('lt-region').value;
  if (!kw) return;
  loader('lt-results', 'Expanding keywords via Google Autocomplete...');
  try {
    const r = await fetch(`${BASE}/api/longtail?keyword=${encodeURIComponent(kw)}&region=${region}`);
    const d = await r.json();
    if (d.error) { err('lt-results', d.error); return; }
    const byIntent = {};
    d.keywords.forEach(k => {
      if (!byIntent[k.intent]) byIntent[k.intent] = [];
      byIntent[k.intent].push(k);
    });
    document.getElementById('lt-results').innerHTML = `
      <div class="result-block">
        <h3>Long-tail Keywords for "${d.seed}" <span class="count-badge">${d.count} found</span></h3>
        ${Object.entries(byIntent).map(([intent, kws]) => `
          <div style="margin-bottom:20px">
            <div style="font-size:13px;color:#94a3b8;margin-bottom:10px;font-weight:600">${kws[0].intent_icon} ${intent.toUpperCase()} (${kws.length})</div>
            <div class="kw-grid">
              ${kws.map(k => `
                <div class="kw-card">
                  <div class="kw-text">${k.keyword}</div>
                  <span class="intent-badge" style="background:${k.intent_color}22;color:${k.intent_color}">${k.intent_icon} ${k.intent}</span>
                </div>
              `).join('')}
            </div>
          </div>
        `).join('')}
      </div>`;
  } catch(e) { err('lt-results', e.message); }
}

async function loadIntent() {
  const kw = document.getElementById('int-kw').value.trim();
  if (!kw) return;
  loader('int-results', 'Classifying intent...');
  try {
    const r = await fetch(`${BASE}/api/intent?keyword=${encodeURIComponent(kw)}`);
    const d = await r.json();
    if (d.error) { err('int-results', d.error); return; }
    const i = d.intent;
    document.getElementById('int-results').innerHTML = `
      <div class="intent-big">
        <div class="intent-box" style="border-color:${i.color}44">
          <div class="intent-icon">${i.icon}</div>
          <div class="intent-name" style="color:${i.color}">${i.intent.toUpperCase()}</div>
          <div class="intent-desc">${i.desc}</div>
          <div style="margin-top:8px;font-size:12px;color:#64748b">Confidence: ${i.confidence}</div>
        </div>
        <div class="result-block" style="flex:2;margin-bottom:0">
          <h3>Signal Scores</h3>
          ${Object.entries(i.scores).map(([type, score]) => `
            <div class="score-row">
              <span style="color:#94a3b8">${type}</span>
              <span style="font-weight:700;color:${score>0?'#4ade80':'#475569'}">${score} signals</span>
            </div>
          `).join('')}
        </div>
      </div>
      ${d.people_also_ask.length ? `
      <div class="result-block">
        <h3>People Also Ask</h3>
        ${d.people_also_ask.map(q => `<div class="paa-item">${q}</div>`).join('')}
      </div>` : ''}`;
  } catch(e) { err('int-results', e.message); }
}

async function loadCompare() {
  const kws = document.getElementById('cmp-kws').value.trim();
  const region = document.getElementById('cmp-region').value;
  const tf = document.getElementById('cmp-tf').value;
  if (!kws) return;
  loader('cmp-results', 'Comparing keywords via pytrends...');
  try {
    const r = await fetch(`${BASE}/api/compare?keywords=${encodeURIComponent(kws)}&region=${region}&timeframe=${encodeURIComponent(tf)}`);
    const d = await r.json();
    if (d.error) { err('cmp-results', d.error); return; }
    if (d.data.error) { err('cmp-results', d.data.error); return; }
    const entries = Object.entries(d.data);
    const maxPeak = Math.max(...entries.map(([,v]) => v.peak || 0));
    document.getElementById('cmp-results').innerHTML = `
      <div class="result-block">
        <h3>Keyword Comparison — ${d.region} (${d.timeframe})</h3>
        ${entries.map(([kw, v], i) => `
          <div class="compare-row">
            <span style="min-width:140px;font-weight:600;color:${COLORS[i]}">${kw}</span>
            <div class="bar-wrap"><div class="bar" style="width:${(v.peak/maxPeak*100)}%;background:${COLORS[i]}"></div></div>
            <span style="min-width:60px;text-align:right;font-weight:700">Peak: ${v.peak}</span>
            <span class="trend-badge" style="margin-left:10px">${v.trend}</span>
            <span class="${v.growth_pct>=0?'growth-pos':'growth-neg'}" style="min-width:70px;text-align:right;font-weight:700">${v.growth_pct>=0?'+':''}${v.growth_pct}%</span>
          </div>
        `).join('')}
      </div>`;
  } catch(e) { err('cmp-results', e.message); }
}

async function loadBreakout() {
  const kws = document.getElementById('bo-kws').value.trim();
  const region = document.getElementById('bo-region').value;
  if (!kws) return;
  loader('bo-results', 'Detecting breakout keywords... (may take 30s)');
  try {
    const r = await fetch(`${BASE}/api/breakout?keywords=${encodeURIComponent(kws)}&region=${region}`);
    const d = await r.json();
    if (d.error) { err('bo-results', d.error); return; }
    document.getElementById('bo-results').innerHTML = `
      <div class="result-block">
        <h3>Breakout Analysis — ${d.region}</h3>
        ${d.results.map(k => `
          <div class="breakout-card">
            <div>
              <div class="breakout-kw">${k.keyword}</div>
              <div style="font-size:12px;color:#64748b;margin-top:4px">Current interest: ${k.current_interest}</div>
            </div>
            <div style="display:flex;align-items:center;gap:10px">
              <span class="${k.growth_pct>=0?'growth-pos':'growth-neg'}" style="font-size:18px;font-weight:800">${k.growth_pct>=0?'+':''}${k.growth_pct}%</span>
              <span class="breakout-label">${k.label}</span>
            </div>
          </div>
        `).join('')}
      </div>`;
  } catch(e) { err('bo-results', e.message); }
}

async function loadSeasonal() {
  const kw = document.getElementById('sea-kw').value.trim();
  const region = document.getElementById('sea-region').value;
  if (!kw) return;
  loader('sea-results', 'Analyzing 12-month seasonality...');
  try {
    const r = await fetch(`${BASE}/api/seasonal?keyword=${encodeURIComponent(kw)}&region=${region}`);
    const d = await r.json();
    if (d.error) { err('sea-results', d.error); return; }
    const sd = d.seasonal_data;
    if (!sd || sd.error) { err('sea-results', sd?.error || 'No data'); return; }
    const max = sd.peak || 1;
    document.getElementById('sea-results').innerHTML = `
      <div class="result-block">
        <h3>Seasonal Pattern — "${d.keyword}" (${d.region}, 12 months)</h3>
        <div style="display:flex;gap:20px;margin-bottom:16px;flex-wrap:wrap">
          <div style="background:#12121f;padding:14px 20px;border-radius:8px;border:1px solid #2d2d44">
            <div style="font-size:22px;font-weight:800;color:#6366f1">${sd.peak}</div>
            <div style="font-size:12px;color:#64748b">Peak Interest</div>
          </div>
          <div style="background:#12121f;padding:14px 20px;border-radius:8px;border:1px solid #2d2d44">
            <div style="font-size:22px;font-weight:800;color:#10b981">${sd.current}</div>
            <div style="font-size:12px;color:#64748b">Current Interest</div>
          </div>
          <div style="background:#12121f;padding:14px 20px;border-radius:8px;border:1px solid #2d2d44">
            <div style="font-size:22px;font-weight:800;color:${sd.growth_pct>=0?'#4ade80':'#f87171'}">${sd.growth_pct>=0?'+':''}${sd.growth_pct}%</div>
            <div style="font-size:12px;color:#64748b">Growth vs Baseline</div>
          </div>
          <div style="background:#12121f;padding:14px 20px;border-radius:8px;border:1px solid #2d2d44">
            <div style="font-size:22px;font-weight:800">${sd.trend}</div>
            <div style="font-size:12px;color:#64748b">Trend Direction</div>
          </div>
        </div>
        ${sd.dates ? sd.dates.map((date, i) => `
          <div class="seasonal-row">
            <span style="min-width:100px;color:#94a3b8">${date}</span>
            <div class="month-bar-wrap"><div class="month-bar" style="width:${(sd.values[i]/max*100)}%"></div></div>
            <span style="font-weight:700;color:${sd.values[i]>70?'#4ade80':sd.values[i]>40?'#fbbf24':'#94a3b8'}">${sd.values[i]}</span>
          </div>
        `).join('') : ''}
      </div>`;
  } catch(e) { err('sea-results', e.message); }
}
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTML

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")
