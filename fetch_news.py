"""
A12 News Fetcher – Abteilung 12 Wirtschaft, Tourismus, Wissenschaft und Forschung
Amt der Steiermärkischen Landesregierung
Fetches RSS feeds, summarizes with Gemini, saves to docs/data.json
"""

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

# ── Configuration ──────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
)

MAX_ITEMS_FROM_FEED    = 100
MAX_AGE_DAYS           = 7
MAX_ITEMS_PER_CATEGORY = 6
MAX_TITLES_FOR_SUMMARY = 6
GEMINI_PAUSE_SECONDS   = 120
GEMINI_RETRY_ATTEMPTS  = 10
GEMINI_RETRY_WAIT      = 120


def gnews(query: str, lang: str = "de", country: str = "AT") -> str:
    from urllib.parse import quote
    return (
        f"https://news.google.com/rss/search"
        f"?q={quote(query)}&hl={lang}&gl={country}&ceid={country}:{lang}"
    )


CATEGORIES = {
    "wirtschaft": {
        "label": "Wirtschaft & Standort",
        "icon": "💼",
        "color": "#1a5c38",
        "feeds": [
            gnews("Wirtschaft Steiermark"),
            gnews("Wirtschaftsstandort Steiermark"),
            gnews("Unternehmensansiedlung Steiermark"),
            gnews("Industrie Steiermark"),
            gnews("KMU Förderung Steiermark"),
            gnews("Arbeitsmarkt Steiermark"),
            gnews("Beschäftigung Steiermark"),
            gnews("Wirtschaftsförderung Steiermark Land"),
            gnews("Investition Steiermark Wirtschaft"),
            gnews("Abteilung 12 Steiermark Wirtschaft"),
        ],
        "summary_prompt": (
            "Du bist Experte für Wirtschaftspolitik und Standortentwicklung in der Steiermark. "
            "Fasse die folgenden Nachrichtentitel zu Wirtschaft, Unternehmensansiedlungen, "
            "Förderungen und Arbeitsmarkt in der Steiermark in 2 prägnanten deutschen Sätzen zusammen. "
            "Antworte NUR mit Fließtext, keine Aufzählungen."
        ),
    },
    "tourismus": {
        "label": "Tourismus",
        "icon": "🏔️",
        "color": "#003399",
        "feeds": [
            gnews("Tourismus Steiermark"),
            gnews("Tourismuspolitik Steiermark"),
            gnews("Tourismusförderung Steiermark Land"),
            gnews("Urlaub Steiermark"),
            gnews("Nächtigungen Steiermark"),
            gnews("Tourismus Strategie Steiermark"),
            gnews("Graz Tourismus Stadtmarketing"),
            gnews("Therme Steiermark Tourismus"),
            gnews("Wintertourismus Steiermark"),
            gnews("Sommertourismus Steiermark"),
        ],
        "summary_prompt": (
            "Du bist Experte für Tourismus und Tourismusförderung in der Steiermark. "
            "Fasse die folgenden Nachrichtentitel zu Tourismus, Nächtigungszahlen, "
            "Tourismusstrategie und Tourismusförderung in 2 prägnanten deutschen Sätzen zusammen. "
            "Antworte NUR mit Fließtext, keine Aufzählungen."
        ),
    },
    "wissenschaft": {
        "label": "Wissenschaft & Forschung",
        "icon": "🔬",
        "color": "#c8102e",
        "feeds": [
            gnews("Wissenschaft Steiermark"),
            gnews("Forschung Steiermark"),
            gnews("TU Graz Forschung"),
            gnews("Universität Graz Forschung"),
            gnews("FH Joanneum Steiermark"),
            gnews("Forschungsförderung Steiermark Land"),
            gnews("Innovation Steiermark"),
            gnews("Startup Steiermark"),
            gnews("Technologie Steiermark"),
            gnews("Silicon Austria Steiermark"),
        ],
        "summary_prompt": (
            "Du bist Experte für Wissenschaft, Forschung und Innovation in der Steiermark. "
            "Fasse die folgenden Nachrichtentitel zu Forschungsprojekten, Universitäten, "
            "Innovationen und Forschungsförderung in 2 prägnanten deutschen Sätzen zusammen. "
            "Antworte NUR mit Fließtext, keine Aufzählungen."
        ),
    },
    "foerderungen": {
        "label": "Förderungen & EU-Programme",
        "icon": "💶",
        "color": "#5a5a5a",
        "feeds": [
            gnews("Förderung Steiermark Wirtschaft Land"),
            gnews("EU Förderung Steiermark"),
            gnews("EFRE Steiermark"),
            gnews("Wirtschaftsförderung Fonds Steiermark"),
            gnews("aws Förderung Steiermark"),
            gnews("FFG Förderung Steiermark Forschung"),
            gnews("Regionalförderung Steiermark"),
            gnews("Strukturfonds Steiermark EU"),
        ],
        "summary_prompt": (
            "Du bist Experte für Förderungen und EU-Programme in der Steiermark. "
            "Fasse die folgenden Nachrichtentitel zu Förderungen, EU-Programmen, "
            "Strukturfonds und Wirtschaftsförderungen in 2 prägnanten deutschen Sätzen zusammen. "
            "Antworte NUR mit Fließtext, keine Aufzählungen."
        ),
    },
    "innovation": {
        "label": "Innovation & Digitalisierung",
        "icon": "💡",
        "color": "#7b4f12",
        "feeds": [
            gnews("Digitalisierung Steiermark"),
            gnews("Künstliche Intelligenz Steiermark"),
            gnews("Smart City Graz Steiermark"),
            gnews("Startup Ökosystem Steiermark Graz"),
            gnews("Innovation Technologie Steiermark"),
            gnews("Cluster Steiermark Technologie"),
            gnews("Automotive Cluster Steiermark"),
            gnews("Green Tech Steiermark"),
            gnews("Wasserstoff Steiermark"),
            gnews("Kreativwirtschaft Steiermark"),
        ],
        "summary_prompt": (
            "Du bist Experte für Innovation und Digitalisierung in der Steiermark. "
            "Fasse die folgenden Nachrichtentitel zu Digitalisierung, KI, Startups, "
            "Technologieclustern und Green Tech in 2 prägnanten deutschen Sätzen zusammen. "
            "Antworte NUR mit Fließtext, keine Aufzählungen."
        ),
    },
}


# ── RSS Fetching ───────────────────────────────────────────────────────────────

def parse_pub_date(raw: str):
    if not raw:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(raw)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(raw.rstrip("Z") + "+00:00")
    except Exception:
        return None


def fetch_rss(url: str) -> list[dict]:
    items = []
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"})
        with urlopen(req, timeout=30) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        channel = root.find("channel")
        entries = channel.findall("item") if channel is not None else (
            root.findall("{http://www.w3.org/2005/Atom}entry") or root.findall("entry")
        )
        for item in entries[:MAX_ITEMS_FROM_FEED]:
            title = (item.findtext("title") or
                     item.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            title = re.sub(r"<[^>]+>", "", title).strip()
            link_el = item.find("link")
            link = (link_el.get("href") or link_el.text or "").strip() if link_el is not None else ""
            pub = (item.findtext("pubDate") or
                   item.findtext("{http://www.w3.org/2005/Atom}published") or "").strip()
            source_el = item.find("source")
            source = source_el.text.strip() if source_el is not None else ""
            if not source:
                try:
                    from urllib.parse import urlparse
                    source = urlparse(url).netloc.replace("www.", "")
                except Exception:
                    pass
            if title:
                items.append({
                    "title": title, "link": link,
                    "date_raw": pub, "date_parsed": parse_pub_date(pub), "source": source,
                })
    except Exception as e:
        print(f"  Warning: could not fetch {url[:70]}: {e}")
    return items


def filter_by_age(items, max_age_days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    result, skipped = [], 0
    for item in items:
        dt = item.get("date_parsed")
        if dt is None or dt >= cutoff:
            result.append(item)
        else:
            skipped += 1
    if skipped:
        print(f"  Filtered out {skipped} items older than {max_age_days} days")
    return result


def deduplicate(items):
    seen, result = set(), []
    for item in items:
        key = re.sub(r"\s+", " ", item["title"].lower().strip())
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def format_date(raw):
    if not raw:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(raw).strftime("%-d. %b %Y")
    except Exception:
        pass
    try:
        return datetime.fromisoformat(raw.rstrip("Z") + "+00:00").strftime("%-d. %b %Y")
    except Exception:
        return raw[:16]


# ── Gemini ─────────────────────────────────────────────────────────────────────

def call_gemini(prompt: str, max_tokens: int = 2000) -> str:
    import json as _json
    body = _json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
    }).encode()
    for attempt in range(1, GEMINI_RETRY_ATTEMPTS + 1):
        try:
            req = Request(GEMINI_URL, data=body,
                          headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=30) as resp:
                data = _json.loads(resp.read())
            print(f"  Finish reason: {data['candidates'][0].get('finishReason','unknown')}")
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except HTTPError as e:
            if e.code == 429:
                if attempt < GEMINI_RETRY_ATTEMPTS:
                    print(f"  Gemini 429 (attempt {attempt}/{GEMINI_RETRY_ATTEMPTS}) – waiting {GEMINI_RETRY_WAIT}s…")
                    time.sleep(GEMINI_RETRY_WAIT)
                else:
                    return "Zusammenfassung konnte nicht erstellt werden (Rate Limit)."
            else:
                print(f"  Gemini HTTP error {e.code}")
                return "Zusammenfassung konnte nicht erstellt werden."
        except Exception as e:
            print(f"  Gemini error: {e}")
            return "Zusammenfassung konnte nicht erstellt werden."
    return "Zusammenfassung konnte nicht erstellt werden."


def summarize_with_gemini(titles, prompt):
    if not titles:
        return "Keine aktuellen Meldungen der letzten 7 Tage gefunden."
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    return call_gemini(prompt + "\n\nNachrichtentitel:\n" + numbered, max_tokens=2000)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    output = {
        "generated": datetime.now(timezone.utc).strftime("%d. %B %Y, %H:%M UTC"),
        "categories": {},
    }

    for cat_id, cat in CATEGORIES.items():
        print(f"\n── {cat['label']} ──")
        all_items = []
        for feed_url in cat["feeds"]:
            print(f"  Fetching: {feed_url[:80]}…")
            all_items.extend(fetch_rss(feed_url))

        print(f"  {len(all_items)} total items before filtering")
        all_items = filter_by_age(all_items, MAX_AGE_DAYS)
        items = deduplicate(all_items)[:MAX_ITEMS_PER_CATEGORY]
        print(f"  {len(items)} unique items after filter")

        for item in items:
            item["date"] = format_date(item.pop("date_raw", ""))
            item.pop("date_parsed", None)

        print("  Calling Gemini…")
        summary = summarize_with_gemini(
            [i["title"] for i in items[:MAX_TITLES_FOR_SUMMARY]], cat["summary_prompt"]
        )
        print(f"  Summary: {summary[:80]}…")
        print(f"  Waiting {GEMINI_PAUSE_SECONDS}s…")
        time.sleep(GEMINI_PAUSE_SECONDS)

        output["categories"][cat_id] = {
            "label":   cat["label"],
            "icon":    cat["icon"],
            "color":   cat["color"],
            "summary": summary,
            "items":   items,
        }

    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("\n✅ docs/data.json written successfully.")


if __name__ == "__main__":
    main()
