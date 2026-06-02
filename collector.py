"""
MGM Muthu — Morning Intelligence Collector v3
Improvements:
- Max 2 stories per competitor (no Iberostar flooding)
- Local hotel news near each MGM Muthu property
- All sections sorted newest first
- Better tour operator / OTA queries with direct newsroom feeds
- Macro: UK GfK, ONS, Irish CSO, cost of living, holiday spending
- Google Trends replaced with real article links
- Events: attendance figures, new announcements
- Tourism: forward-looking revenue strategy signals, all European feeder markets
"""

import json, datetime, hashlib, os, re, time, email.utils
import feedparser, requests
from bs4 import BeautifulSoup

OUTPUT_JSON   = "dashboard_data.json"
OUTPUT_HTML   = "dashboard_standalone.html"
TEMPLATE_FILE = "dashboard_template.html"
SNAPSHOT_FILE = "competitor_snapshot.json"
HEADERS       = {"User-Agent": "Mozilla/5.0 (compatible; MuthuIntelBot/3.0)"}
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

def gn(query):
    return f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en&gl=GB&ceid=GB:en"

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
    return dt is not None and dt >= CUTOFF

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

def sort_by_date(items):
    """Sort list of items newest first using age_label ordering via raw date stored."""
    return sorted(items, key=lambda x: x.get("_ts", 0), reverse=True)

def entry_to_item(entry, source, dot="info"):
    dt = parse_entry_date(entry)
    return {
        "title":  clean(entry.get("title", "")),
        "link":   entry.get("link", ""),
        "source": source,
        "age":    age_label(entry),
        "dot":    dot,
        "_ts":    dt.timestamp() if dt else 0,
    }

def strip_ts(items):
    for i in items:
        i.pop("_ts", None)
    return items

# ── RSS SOURCES ───────────────────────────────────────────────────────────────

RSS_SOURCES = [

    # ── INDUSTRY & HOTEL NEWS ─────────────────────────────────────────────────
    {"feed": "https://skift.com/feed/",                     "section": "industry", "source": "Skift"},
    {"feed": "https://www.hospitalitynet.org/rss/news.xml", "section": "industry", "source": "HospitalityNet"},
    {"feed": "https://www.phocuswire.com/rss",              "section": "industry", "source": "PhocusWire"},
    {"feed": "https://www.travelandtourworld.com/feed/",     "section": "industry", "source": "Travel & Tour World"},
    {"feed": gn("hotel industry news Europe 2026"),         "section": "industry", "source": "Google News"},
    {"feed": gn("all inclusive hotel trends Europe"),       "section": "industry", "source": "Google News"},
    # Local hotel news near MGM Muthu properties
    {"feed": gn("Albufeira hotel news 2026"),               "section": "industry", "source": "Google News"},
    {"feed": gn("Algarve hotel opening 2026"),              "section": "industry", "source": "Google News"},
    {"feed": gn("Tenerife Sur hotel news 2026"),            "section": "industry", "source": "Google News"},
    {"feed": gn("Inverness hotel Highland news"),           "section": "industry", "source": "Google News"},
    {"feed": gn("Nairobi Maasai Mara lodge hotel news"),    "section": "industry", "source": "Google News"},
    {"feed": gn("Havana Cuba hotel tourism news"),          "section": "industry", "source": "Google News"},
    {"feed": gn("Montego Bay Jamaica hotel news"),          "section": "industry", "source": "Google News"},

    # ── COMPETITORS ───────────────────────────────────────────────────────────
    {"feed": gn("Pestana Hotels offer promotion deal"),     "section": "competitors_raw", "source": "Pestana"},
    {"feed": gn("Iberostar Hotels offer promotion deal"),   "section": "competitors_raw", "source": "Iberostar"},
    {"feed": gn("Riu Hotels offer promotion Algarve Tenerife"), "section": "competitors_raw", "source": "Riu"},
    {"feed": gn("H10 Hotels offer promotion deal"),         "section": "competitors_raw", "source": "H10"},
    {"feed": gn("Vila Gale Hotels offer promotion"),        "section": "competitors_raw", "source": "Vila Galé"},
    {"feed": gn("Barcelo Hotels offer promotion"),          "section": "competitors_raw", "source": "Barceló"},
    {"feed": gn("Lopesan Hotels offer promotion"),          "section": "competitors_raw", "source": "Lopesan"},

    # ── TOUR OPERATORS & OTA ──────────────────────────────────────────────────
    {"feed": "https://www.jet2.com/en/news/rss",            "section": "operators", "source": "Jet2"},
    {"feed": gn("Jet2 Algarve Tenerife deal offer 2026"),   "section": "operators", "source": "Jet2"},
    {"feed": gn("TUI Algarve Tenerife package deal 2026"),  "section": "operators", "source": "TUI"},
    {"feed": gn("Loveholidays Algarve Tenerife deal"),      "section": "operators", "source": "Loveholidays"},
    {"feed": gn("On The Beach Algarve Portugal deal"),      "section": "operators", "source": "On The Beach"},
    {"feed": gn("easyJet holidays Algarve Tenerife 2026"),  "section": "operators", "source": "easyJet Holidays"},
    {"feed": gn("Booking.com Expedia Algarve hotel deal"),  "section": "operators", "source": "OTA"},
    {"feed": gn("Thomas Cook Algarve Tenerife package"),    "section": "operators", "source": "Thomas Cook"},

    # ── MACRO & CONSUMER CONFIDENCE ───────────────────────────────────────────
    {"feed": gn("UK consumer confidence GfK 2026"),         "section": "macro", "source": "GfK"},
    {"feed": gn("UK household spending travel holidays 2026"), "section": "macro", "source": "ONS"},
    {"feed": gn("British tourists holiday spending abroad 2026"), "section": "macro", "source": "Google News"},
    {"feed": gn("Ireland consumer spending travel 2026"),   "section": "macro", "source": "CSO Ireland"},
    {"feed": gn("Germany France Netherlands holiday travel 2026"), "section": "macro", "source": "Google News"},
    {"feed": gn("cost of living impact holidays travel UK 2026"), "section": "macro", "source": "Google News"},
    {"feed": gn("UK interest rates mortgage holiday spending"), "section": "macro", "source": "Google News"},
    {"feed": gn("European tourism demand summer 2026"),     "section": "macro", "source": "Google News"},

    # ── TOURISM STATISTICS ────────────────────────────────────────────────────
    {"feed": gn("Algarve tourism arrivals statistics 2026"), "section": "tourism", "source": "Google News"},
    {"feed": gn("Tenerife tourism overnight stays 2026"),   "section": "tourism", "source": "ISTAC"},
    {"feed": gn("Scotland Highlands tourism statistics 2026"), "section": "tourism", "source": "VisitScotland"},
    {"feed": gn("Kenya tourism arrivals statistics 2026"),  "section": "tourism", "source": "KTB"},
    {"feed": gn("Cuba tourism international arrivals 2026"), "section": "tourism", "source": "Google News"},
    {"feed": gn("Jamaica tourism arrivals statistics 2026"), "section": "tourism", "source": "JTB"},
    # Forward-looking revenue signals
    {"feed": gn("Algarve advance hotel bookings summer 2026"), "section": "tourism", "source": "Google News"},
    {"feed": gn("Tenerife hotel occupancy booking pace 2026"), "section": "tourism", "source": "Google News"},
    {"feed": gn("UK Germany Netherlands booking summer holidays early 2026"), "section": "tourism", "source": "Google News"},
    {"feed": gn("hotel length of stay trends Europe 2026"), "section": "tourism", "source": "Google News"},
    {"feed": gn("Algarve new hotel supply opening competition 2026"), "section": "tourism", "source": "Google News"},
    {"feed": gn("Portugal Spain hotel ADR rate increase 2026"), "section": "tourism", "source": "Google News"},

    # ── AIRLINE & AIRPORTS ────────────────────────────────────────────────────
    {"feed": gn("Faro airport new route flights 2026"),     "section": "airline", "source": "Google News"},
    {"feed": gn("Tenerife South airport new route 2026"),   "section": "airline", "source": "Google News"},
    {"feed": gn("Inverness airport new route flights 2026"), "section": "airline", "source": "Google News"},
    {"feed": gn("Nairobi JKIA new route international 2026"), "section": "airline", "source": "Google News"},
    {"feed": gn("Montego Bay Sangster airport flights 2026"), "section": "airline", "source": "Google News"},
    {"feed": gn("Ryanair easyJet Portugal Spain new route 2026"), "section": "airline", "source": "Google News"},
    {"feed": gn("TUI Jet2 charter flight capacity summer 2026"), "section": "airline", "source": "Google News"},

    # ── EVENTS & DEMAND CALENDAR ──────────────────────────────────────────────
    {"feed": gn("Albufeira Algarve event festival 2026 attendance"), "section": "events", "source": "Google News"},
    {"feed": gn("Tenerife event concert festival 2026 attendance"),  "section": "events", "source": "Google News"},
    {"feed": gn("Scotland Highlands event festival 2026"),           "section": "events", "source": "VisitScotland"},
    {"feed": gn("Kenya Maasai Mara event safari season 2026"),       "section": "events", "source": "Google News"},
    {"feed": gn("Jamaica event festival 2026 attendance"),           "section": "events", "source": "Google News"},
    {"feed": gn("UK bank holiday school holiday travel demand 2026"), "section": "events", "source": "Google News"},
    {"feed": gn("IRONMAN triathlon Portugal Spain 2026"),            "section": "events", "source": "Google News"},
    {"feed": gn("European football tournament impact tourism 2026"), "section": "events", "source": "Google News"},

    # ── WEATHER ───────────────────────────────────────────────────────────────
    {"feed": gn("Algarve weather forecast warning 2026"),   "section": "weather", "source": "Google News"},
    {"feed": gn("Tenerife weather forecast June July 2026"), "section": "weather", "source": "Google News"},
    {"feed": gn("Jamaica hurricane season forecast 2026"),  "section": "weather", "source": "NHC"},
    {"feed": gn("Kenya weather dry season safari 2026"),    "section": "weather", "source": "Google News"},

    # ── REPUTATION ────────────────────────────────────────────────────────────
    {"feed": gn("MGM Muthu hotel review TripAdvisor"),      "section": "reputation", "source": "Google News"},
    {"feed": gn("Albufeira hotel review rating 2026"),      "section": "reputation", "source": "Google News"},
    {"feed": gn("Pestana Iberostar Riu review rating 2026"), "section": "reputation", "source": "Google News"},

    # ── MGM MUTHU BRAND ───────────────────────────────────────────────────────
    {"feed": gn('"MGM Muthu" OR "Muthu Hotels"'),           "section": "muthu", "source": "Google News"},
    {"feed": gn("Muthu Forte Vale OR Muthu Royal Park OR Muthu Keekorok"), "section": "muthu", "source": "Google News"},
    {"feed": gn("Muthu Oura View OR Muthu Clube Praia OR Muthu Belver"), "section": "muthu", "source": "Google News"},
]

def fetch_rss():
    print(f"  [{ts()}] Fetching {len(RSS_SOURCES)} RSS feeds (last {MAX_AGE_DAYS} days)...")
    sections = {}
    seen_ids = set()
    total_fetched = total_kept = 0

    for s in RSS_SOURCES:
        try:
            feed = feedparser.parse(s["feed"])
            for entry in feed.entries[:8]:
                total_fetched += 1
                if not is_fresh(entry):
                    continue
                title = clean(entry.get("title", ""))
                if not title or len(title) < 15:
                    continue
                uid = hashlib.md5((entry.get("link","") + title).encode()).hexdigest()
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)
                total_kept += 1
                item = entry_to_item(entry, s["source"])
                sections.setdefault(s["section"], []).append(item)
        except Exception as e:
            print(f"    ! RSS error {s['source']}: {e}")

    print(f"    Fetched {total_fetched}, kept {total_kept} within {MAX_AGE_DAYS} days")
    return sections

# ── COMPETITOR CRAWL with 2-per-brand cap ────────────────────────────────────

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
    print(f"  [{ts()}] Crawling {len(COMPETITORS)} competitor sites (max 2 per brand)...")
    snapshot = json.load(open(SNAPSHOT_FILE)) if os.path.exists(SNAPSHOT_FILE) else {}
    results, new_snapshot = [], {}

    for c in COMPETITORS:
        print(f"    Scraping {c['name']}...")
        html = safe_get(c["url"])
        offers = extract_offers(html) if html else []
        new_snapshot[c["name"]] = offers
        old = set(snapshot.get(c["name"], []))

        brand_count = 0
        for o in offers:
            if brand_count >= 2:   # MAX 2 per brand
                break
            dot = "new" if o not in old else "info"
            results.append({
                "title":  f"{c['name']} — {o}",
                "source": c["name"],
                "link":   c["url"],
                "dot":    dot,
                "age":    "today",
                "_ts":    NOW_UTC.timestamp()
            })
            brand_count += 1

    # Also merge RSS competitor news (capped at 2 per source brand)
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(new_snapshot, f, indent=2)
    print(f"    {len(results)} competitor items (crawl, 2-per-brand cap)")
    return results

def merge_rss_competitors(crawl_results, rss_sections):
    """Merge crawled offers with RSS news, cap total per brand at 2."""
    raw = rss_sections.get("competitors_raw", [])
    brand_counts = {}
    for item in crawl_results:
        src = item.get("source","")
        brand_counts[src] = brand_counts.get(src, 0) + 1

    for item in raw:
        src = item.get("source","")
        if brand_counts.get(src, 0) < 2:
            crawl_results.append(item)
            brand_counts[src] = brand_counts.get(src, 0) + 1

    return sort_by_date(crawl_results)

# ── CURRENCY ──────────────────────────────────────────────────────────────────

def fetch_currency():
    print(f"  [{ts()}] Fetching live currency rates...")
    pairs = []
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=GBP&to=EUR,USD", timeout=10)
        rates = r.json().get("rates", {})
        # Get yesterday's rates for delta
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        r2 = requests.get(f"https://api.frankfurter.app/{yesterday}?from=GBP&to=EUR,USD", timeout=10)
        old_rates = r2.json().get("rates", {})

        for code, label in [("EUR","GBP / EUR"),("USD","GBP / USD")]:
            current = rates.get(code, 0)
            previous = old_rates.get(code, current)
            delta = current - previous
            direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
            delta_str = f"{delta:+.3f}" if delta != 0 else "unchanged"
            pairs.append({"pair": label, "val": f"{current:.3f}",
                          "delta": delta_str, "dir": direction})
    except Exception as e:
        print(f"    ! Currency error: {e}")
        pairs = [{"pair":"GBP / EUR","val":"n/a","delta":"","dir":"flat"},
                 {"pair":"GBP / USD","val":"n/a","delta":"","dir":"flat"}]
    try:
        r3 = requests.get("https://api.frankfurter.app/latest?from=EUR&to=KES", timeout=10)
        kes = r3.json().get("rates",{}).get("KES",0)
        pairs.append({"pair":"EUR / KES","val":f"{kes:.1f}","delta":"live","dir":"flat"})
    except:
        pairs.append({"pair":"EUR / KES","val":"n/a","delta":"","dir":"flat"})
    return pairs

# ── TRENDS — now returns real article links ───────────────────────────────────

TREND_SEARCHES = [
    {"dest": "Algarve holidays",         "query": "Algarve holidays summer 2026 demand"},
    {"dest": "Tenerife all-inclusive",   "query": "Tenerife all inclusive booking 2026"},
    {"dest": "Kenya safari",             "query": "Kenya safari booking demand 2026"},
    {"dest": "Scotland Highlands hotel", "query": "Scotland Highlands hotel booking 2026"},
    {"dest": "Cuba holidays",            "query": "Cuba holidays travel 2026"},
    {"dest": "Jamaica all-inclusive",    "query": "Jamaica all inclusive holiday 2026"},
]

def fetch_trends():
    print(f"  [{ts()}] Fetching search demand articles...")
    results = []
    for t in TREND_SEARCHES:
        url = gn(t["query"])
        try:
            feed = feedparser.parse(url)
            fresh = [e for e in feed.entries if is_fresh(e)]
            # Return up to 2 real article links per destination
            articles = []
            for entry in fresh[:2]:
                title = clean(entry.get("title",""))
                if title and len(title) > 15:
                    articles.append({
                        "title": title,
                        "link":  entry.get("link",""),
                        "age":   age_label(entry),
                        "_ts":   parse_entry_date(entry).timestamp() if parse_entry_date(entry) else 0
                    })
            results.append({
                "dest":        t["dest"],
                "articles_24h": len(fresh),
                "bar":         min(len(fresh) * 12, 100),
                "articles":    articles
            })
        except:
            results.append({"dest": t["dest"], "articles_24h": 0, "bar": 0, "articles": []})
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
    print(f"  MGM Muthu Collector v3 — {TODAY} {ts()}")
    print(f"  Filter: last {MAX_AGE_DAYS} days | Cutoff: {CUTOFF.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*55}\n")

    sections    = fetch_rss()
    crawl_comp  = fetch_competitors()
    competitors = merge_rss_competitors(crawl_comp, sections)
    currency    = fetch_currency()
    trends      = fetch_trends()

    def prep(key, limit):
        items = sort_by_date(sections.get(key, []))[:limit]
        return strip_ts(items)

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
        "muthu":       prep("muthu",       8),
        "industry":    prep("industry",   10),
        "competitors": strip_ts(competitors[:10]),
        "tourism":     prep("tourism",     8),
        "airline":     prep("airline",     7),
        "operators":   prep("operators",   8),
        "macro":       prep("macro",       7),
        "events":      prep("events",      7),
        "weather":     prep("weather",     5),
        "reputation":  prep("reputation",  6),
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    build_standalone(payload)

    print(f"\n  Summary: {json.dumps(summary)}")
    print(f"  [DONE] {ts()}\n{'='*55}\n")

if __name__ == "__main__":
    main()
