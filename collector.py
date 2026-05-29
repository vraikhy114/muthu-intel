"""
MGM Muthu — Morning Intelligence Collector (GitHub Actions version)
Runs daily via .github/workflows/daily.yml
No Playwright needed — uses requests + BeautifulSoup only.

Output: dashboard_standalone.html (embed data into template)
        dashboard_data.json (raw data backup)
        competitor_snapshot.json (yesterday's offers for diff)
"""

import json, datetime, hashlib, os, re, time, email.utils
import feedparser, requests
from bs4 import BeautifulSoup

OUTPUT_JSON   = "dashboard_data.json"
OUTPUT_HTML   = "dashboard_standalone.html"
TEMPLATE_FILE = "dashboard_template.html"
SNAPSHOT_FILE = "competitor_snapshot.json"
HEADERS       = {"User-Agent": "Mozilla/5.0 (compatible; MuthuIntelBot/2.0)"}
MAX_AGE_DAYS  = 7
NOW_UTC       = datetime.datetime.now(datetime.timezone.utc)
CUTOFF        = NOW_UTC - datetime.timedelta(days=MAX_AGE_DAYS)
TODAY         = datetime.date.today().isoformat()

def ts():
    return datetime.datetime.now().strftime("%H:%M")

def safe_get(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"    ! GET failed {url[:60]}: {e}")
        return ""

def clean(text):
    return re.sub(r'\s+', ' ', text or "").strip()[:280]

# ── DATE HELPERS ──────────────────────────────────────────────────────────────

def parse_entry_date(entry):
    parsed = entry.get('published_parsed') or entry.get('updated_parsed')
    if parsed:
        try:
            return datetime.datetime(*parsed[:6], tzinfo=datetime.timezone.utc)
        except:
            pass
    pub_str = entry.get('published') or entry.get('updated', '')
    if pub_str:
        try:
            t = email.utils.parsedate_to_datetime(pub_str)
            if t.tzinfo is None:
                t = t.replace(tzinfo=datetime.timezone.utc)
            return t
        except:
            pass
    return None

def is_fresh(entry):
    dt = parse_entry_date(entry)
    if dt is None:
        return False
    return dt >= CUTOFF

def age_label(entry):
    dt = parse_entry_date(entry)
    if not dt:
        return ""
    diff = NOW_UTC - dt
    if diff.days == 0:
        h = diff.seconds // 3600
        m = (diff.seconds % 3600) // 60
        if h == 0:
            return f"{m}m ago" if m > 0 else "just now"
        return f"{h}h ago"
    elif diff.days == 1:
        return "yesterday"
    else:
        return dt.strftime("%-d %b")

# ── RSS FEEDS ─────────────────────────────────────────────────────────────────

RSS_SOURCES = [
    {"feed": "https://skift.com/feed/",                      "section": "industry",  "source": "Skift"},
    {"feed": "https://www.hospitalitynet.org/rss/news.xml",  "section": "industry",  "source": "HospitalityNet"},
    {"feed": "https://www.phocuswire.com/rss",               "section": "industry",  "source": "PhocusWire"},
    {"feed": "https://www.travelandtourworld.com/feed/",      "section": "industry",  "source": "Travel & Tour World"},
    {"feed": "https://news.google.com/rss/search?q=Algarve+tourism+hotel&hl=en",            "section": "tourism",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Tenerife+tourism+hotel&hl=en",           "section": "tourism",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Scotland+Highlands+tourism&hl=en",       "section": "tourism",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Kenya+safari+tourism&hl=en",             "section": "tourism",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Cuba+tourism+hotel&hl=en",               "section": "tourism",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Jamaica+tourism+hotel&hl=en",            "section": "tourism",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Faro+airport+flights+2026&hl=en",        "section": "airline",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Tenerife+airport+flights&hl=en",         "section": "airline",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Inverness+airport+flights&hl=en",        "section": "airline",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Nairobi+JKIA+flights&hl=en",             "section": "airline",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Jamaica+Montego+Bay+airport&hl=en",      "section": "airline",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Jet2+TUI+Loveholidays+Algarve&hl=en",   "section": "operators", "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=TUI+Jet2+package+holiday+deals&hl=en",  "section": "operators", "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=UK+consumer+confidence+travel&hl=en",   "section": "macro",     "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=GBP+EUR+exchange+rate+travel&hl=en",    "section": "macro",     "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=%22MGM+Muthu%22+OR+%22Muthu+Hotels%22&hl=en", "section": "muthu", "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Muthu+Forte+Vale+OR+Muthu+Royal+Park+OR+Muthu+Keekorok&hl=en", "section": "muthu", "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Algarve+weather+forecast&hl=en",        "section": "weather",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Tenerife+weather+forecast&hl=en",       "section": "weather",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Jamaica+hurricane+weather&hl=en",       "section": "weather",   "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Albufeira+events+festival+2026&hl=en",  "section": "events",    "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Tenerife+events+festival+2026&hl=en",   "section": "events",    "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Scotland+Highlands+events+2026&hl=en",  "section": "events",    "source": "Google News"},
    {"feed": "https://news.google.com/rss/search?q=Albufeira+hotel+review&hl=en",          "section": "reputation","source": "Google News"},
]

def fetch_rss():
    print(f"  [{ts()}] Fetching {len(RSS_SOURCES)} RSS feeds (last {MAX_AGE_DAYS} days only)...")
    sections = {}
    seen_ids = set()
    total_fetched = total_kept = 0
    for s in RSS_SOURCES:
        try:
            feed = feedparser.parse(s["feed"])
            for entry in feed.entries[:10]:
                total_fetched += 1
                if not is_fresh(entry):
                    continue
                uid = hashlib.md5((entry.get("link","") + entry.get("title","")).encode()).hexdigest()
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)
                title = clean(entry.get("title",""))
                link  = entry.get("link","")
                if not title or len(title) < 15:
                    continue
                total_kept += 1
                item = {"title": title, "link": link, "source": s["source"],
                        "age": age_label(entry), "dot": "info"}
                sections.setdefault(s["section"], []).append(item)
        except Exception as e:
            print(f"    ! RSS error {s['source']}: {e}")
    print(f"    Fetched {total_fetched}, kept {total_kept} within {MAX_AGE_DAYS} days")
    return sections

# ── COMPETITOR CRAWL (static only — no Playwright needed) ────────────────────

COMPETITORS = [
    {"name": "Pestana",   "url": "https://www.pestana.com/en/promotions"},
    {"name": "Vila Galé", "url": "https://www.vilagale.com/en/promotions"},
    {"name": "Iberostar", "url": "https://www.iberostar.com/en/offers/"},
    {"name": "Riu",       "url": "https://www.riu.com/en/offers"},
    {"name": "H10",       "url": "https://www.h10hotels.com/en/offers"},
]
OFFER_SELECTORS = ["h2","h3","h4",".offer-title",".promotion-title",
                   "[class*='offer-name']","[class*='promo-title']",
                   "[class*='card-title']","[class*='deal-title']"]

def extract_offers(html):
    soup = BeautifulSoup(html, "html.parser")
    seen, offers = set(), []
    for sel in OFFER_SELECTORS:
        for el in soup.select(sel):
            t = clean(el.get_text())
            if (12 < len(t) < 160 and t not in seen
                    and not any(x in t.lower() for x in
                        ["cookie","privacy","login","menu","search","copyright",
                         "newsletter","sign in","follow","facebook","instagram"])):
                seen.add(t)
                offers.append(t)
    return offers[:15]

def fetch_competitors():
    print(f"  [{ts()}] Crawling {len(COMPETITORS)} competitor sites...")
    snapshot = json.load(open(SNAPSHOT_FILE)) if os.path.exists(SNAPSHOT_FILE) else {}
    results, new_snapshot = [], {}
    for c in COMPETITORS:
        print(f"    Scraping {c['name']}...")
        html = safe_get(c["url"])
        offers = extract_offers(html) if html else []
        new_snapshot[c["name"]] = offers
        old = set(snapshot.get(c["name"], []))
        for o in offers:
            dot = "new" if o not in old else "info"
            results.append({"title": f"{c['name']} — {o}", "source": c["name"],
                             "link": c["url"], "dot": dot, "age": "today"})
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(new_snapshot, f, indent=2)
    print(f"    {len(results)} competitor items collected")
    return results

# ── CURRENCY ──────────────────────────────────────────────────────────────────

def fetch_currency():
    print(f"  [{ts()}] Fetching currency rates...")
    pairs = []
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=GBP&to=EUR,USD", timeout=10)
        rates = r.json().get("rates", {})
        pairs.append({"pair":"GBP / EUR","val":f"{rates.get('EUR',0):.3f}","delta":"live","dir":"flat"})
        pairs.append({"pair":"GBP / USD","val":f"{rates.get('USD',0):.3f}","delta":"live","dir":"flat"})
    except Exception as e:
        print(f"    ! Currency error: {e}")
        pairs = [{"pair":"GBP / EUR","val":"n/a","delta":"","dir":"flat"},
                 {"pair":"GBP / USD","val":"n/a","delta":"","dir":"flat"}]
    try:
        r2 = requests.get("https://api.frankfurter.app/latest?from=EUR&to=KES", timeout=10)
        kes = r2.json().get("rates",{}).get("KES",0)
        pairs.append({"pair":"EUR / KES","val":f"{kes:.1f}","delta":"live","dir":"flat"})
    except:
        pairs.append({"pair":"EUR / KES","val":"n/a","delta":"","dir":"flat"})
    return pairs

# ── TRENDS PROXY ──────────────────────────────────────────────────────────────

TREND_TERMS = [
    {"term": "Algarve holidays",         "dest": "Algarve holidays"},
    {"term": "Tenerife all inclusive",   "dest": "Tenerife all-inclusive"},
    {"term": "Kenya safari 2026",        "dest": "Kenya safari"},
    {"term": "Scotland highlands hotel", "dest": "Scotland Highlands hotel"},
    {"term": "Cuba holidays 2026",       "dest": "Cuba holidays"},
    {"term": "Jamaica all inclusive",    "dest": "Jamaica all-inclusive"},
]

def fetch_trends():
    print(f"  [{ts()}] Fetching search demand signals...")
    results = []
    for t in TREND_TERMS:
        url = f"https://news.google.com/rss/search?q={requests.utils.quote(t['term'])}&hl=en"
        try:
            feed = feedparser.parse(url)
            fresh = [e for e in feed.entries if is_fresh(e)]
            count = len(fresh)
            results.append({"dest": t["dest"], "articles_24h": count, "bar": min(count * 12, 100)})
        except:
            results.append({"dest": t["dest"], "articles_24h": 0, "bar": 0})
        time.sleep(0.3)
    return results

# ── BUILD STANDALONE HTML ─────────────────────────────────────────────────────

def build_standalone(payload):
    if not os.path.exists(TEMPLATE_FILE):
        print(f"  ! Template not found: {TEMPLATE_FILE}")
        return
    with open(TEMPLATE_FILE, encoding="utf-8") as f:
        html = f.read()
    data_js = json.dumps(payload, ensure_ascii=False, separators=(',',':'))
    standalone = html.replace('const EMBEDDED_DATA = {};', f'const EMBEDDED_DATA = {data_js};')
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(standalone)
    print(f"  [OK] {OUTPUT_HTML} written ({len(standalone)//1024}KB)")

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print(f"  MGM Muthu Collector — {TODAY} {ts()}")
    print(f"  Filter: last {MAX_AGE_DAYS} days | Cutoff: {CUTOFF.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*55}\n")

    sections    = fetch_rss()
    competitors = fetch_competitors()
    currency    = fetch_currency()
    trends      = fetch_trends()

    summary = {
        "total_stories":      sum(len(v) for v in sections.values()) + len(competitors),
        "muthu_mentions":     len(sections.get("muthu", [])),
        "competitor_changes": sum(1 for c in competitors if c.get("dot") == "new"),
        "new_routes":         len(sections.get("airline", [])),
        "events":             len(sections.get("events", [])),
        "weather_alerts":     sum(1 for w in sections.get("weather", [])
                                  if any(x in w["title"].lower()
                                         for x in ["warning","alert","extreme","heatwave","storm","hurricane"])),
    }

    payload = {
        "generated":   datetime.datetime.now().isoformat(),
        "date_label":  datetime.date.today().strftime("%A %d %B %Y"),
        "filter_days": MAX_AGE_DAYS,
        "summary":     summary,
        "currency":    currency,
        "trends":      trends,
        "muthu":       sections.get("muthu",     [])[:8],
        "industry":    sections.get("industry",  [])[:8],
        "competitors": competitors[:12],
        "tourism":     sections.get("tourism",   [])[:8],
        "airline":     sections.get("airline",   [])[:7],
        "operators":   sections.get("operators", [])[:6],
        "macro":       sections.get("macro",     [])[:5],
        "events":      sections.get("events",    [])[:6],
        "weather":     sections.get("weather",   [])[:5],
        "reputation":  sections.get("reputation",[])[:6],
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    build_standalone(payload)

    print(f"\n  Summary: {json.dumps(summary)}")
    print(f"  [DONE] {ts()}\n{'='*55}\n")

if __name__ == "__main__":
    main()
