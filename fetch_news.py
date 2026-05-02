"""
A12 News Fetcher – Abteilung 12 Wirtschaft, Tourismus, Wissenschaft und Forschung
Amt der Steiermärkischen Landesregierung
Fetches RSS feeds, summarizes with Claude Haiku or Gemini, saves to docs/data.json
"""

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

# ── AI Provider Switch ────────────────────────────────────────────────────────
#
# To switch the AI provider, change this single value:
#   "claude"  → use Anthropic Claude Haiku 4.5 (requires ANTHROPIC_API_KEY secret)
#   "gemini"  → use Google Gemini 2.5 Flash   (requires GEMINI_API_KEY secret)
#
# Both API keys remain configured in GitHub Secrets, so switching is just a
# one-line code change — no GitHub setup needed when flipping providers.
AI_PROVIDER = "claude"

# ── Configuration ──────────────────────────────────────────────────────────────

# Anthropic (Claude)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
CLAUDE_HAIKU      = "claude-haiku-4-5"

# Google (Gemini)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
)

# Validate that the chosen provider has its API key
if AI_PROVIDER == "claude" and not ANTHROPIC_API_KEY:
    raise SystemExit("AI_PROVIDER='claude' but ANTHROPIC_API_KEY is missing.")
if AI_PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise SystemExit("AI_PROVIDER='gemini' but GEMINI_API_KEY is missing.")
if AI_PROVIDER not in ("claude", "gemini"):
    raise SystemExit(f"Invalid AI_PROVIDER: {AI_PROVIDER!r}. Must be 'claude' or 'gemini'.")

MAX_ITEMS_FROM_FEED    = 100
MAX_AGE_DAYS           = 7
MAX_ITEMS_PER_CATEGORY = 8     # Was 6 — number of headlines shown per category
MAX_TITLES_FOR_SUMMARY = 8     # Was 6 — number of headlines sent to AI for summary

# Pauses between AI calls. Claude Haiku has generous rate limits, so a short
# pause is sufficient. Gemini free tier is tighter, so longer pause + retries.
CLAUDE_PAUSE_SECONDS  = 10
CLAUDE_RETRY_ATTEMPTS = 5
CLAUDE_RETRY_WAIT     = 60
CLAUDE_HTTP_TIMEOUT   = 180

GEMINI_PAUSE_SECONDS  = 120
GEMINI_RETRY_ATTEMPTS = 10
GEMINI_RETRY_WAIT     = 120


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


# ── Claude API ─────────────────────────────────────────────────────────────────

def call_claude(prompt: str, max_tokens: int = 512) -> str:
    """Call Claude Haiku 4.5 via Anthropic Messages API with retry logic."""
    import json as _json
    import socket
    from urllib.error import URLError

    body = _json.dumps({
        "model": CLAUDE_HAIKU,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    for attempt in range(1, CLAUDE_RETRY_ATTEMPTS + 1):
        try:
            req = Request(
                ANTHROPIC_URL,
                data=body,
                headers={
                    "Content-Type":      "application/json",
                    "x-api-key":         ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urlopen(req, timeout=CLAUDE_HTTP_TIMEOUT) as resp:
                data = _json.loads(resp.read())
            text = data["content"][0]["text"].strip()
            print(f"  ✅ Claude Haiku OK — {len(text)} chars")
            return text

        except HTTPError as e:
            body_err = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                if attempt < CLAUDE_RETRY_ATTEMPTS:
                    print(f"  Claude 429 (attempt {attempt}/{CLAUDE_RETRY_ATTEMPTS}) – waiting {CLAUDE_RETRY_WAIT}s…")
                    time.sleep(CLAUDE_RETRY_WAIT)
                    continue
                return "Zusammenfassung konnte nicht erstellt werden (Rate Limit)."
            elif e.code in (500, 502, 503, 504, 529):
                if attempt < CLAUDE_RETRY_ATTEMPTS:
                    print(f"  Claude HTTP {e.code} (attempt {attempt}/{CLAUDE_RETRY_ATTEMPTS}) – waiting {CLAUDE_RETRY_WAIT}s…")
                    print(f"    body: {body_err[:200]}")
                    time.sleep(CLAUDE_RETRY_WAIT)
                    continue
                return "Zusammenfassung konnte nicht erstellt werden (Server Error)."
            else:
                print(f"  Claude HTTP error {e.code}: {body_err[:300]}")
                return "Zusammenfassung konnte nicht erstellt werden."

        except (socket.timeout, TimeoutError):
            if attempt < CLAUDE_RETRY_ATTEMPTS:
                print(f"  Claude timeout (attempt {attempt}/{CLAUDE_RETRY_ATTEMPTS}) – waiting {CLAUDE_RETRY_WAIT}s…")
                time.sleep(CLAUDE_RETRY_WAIT)
                continue
            return "Zusammenfassung konnte nicht erstellt werden (Timeout)."

        except URLError as e:
            if attempt < CLAUDE_RETRY_ATTEMPTS:
                print(f"  Claude URL error (attempt {attempt}/{CLAUDE_RETRY_ATTEMPTS}): {e} – waiting {CLAUDE_RETRY_WAIT}s…")
                time.sleep(CLAUDE_RETRY_WAIT)
                continue
            return "Zusammenfassung konnte nicht erstellt werden (Connection Error)."

        except Exception as e:
            print(f"  Claude error ({type(e).__name__}): {e}")
            return "Zusammenfassung konnte nicht erstellt werden."

    return "Zusammenfassung konnte nicht erstellt werden."


# ── Gemini API ─────────────────────────────────────────────────────────────────

def call_gemini(prompt: str, max_tokens: int = 2000) -> str:
    """Call Gemini 2.5 Flash via Google Generative Language API with retry logic."""
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


# ── Provider Dispatch ──────────────────────────────────────────────────────────

def summarize(titles, prompt) -> str:
    """Dispatches to the active AI provider based on AI_PROVIDER constant."""
    if not titles:
        return "Keine aktuellen Meldungen der letzten 7 Tage gefunden."
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    full_prompt = prompt + "\n\nNachrichtentitel:\n" + numbered

    if AI_PROVIDER == "claude":
        return call_claude(full_prompt, max_tokens=512)
    else:  # gemini
        return call_gemini(full_prompt, max_tokens=2000)


def get_pause_seconds() -> int:
    """Returns the appropriate pause between AI calls for the active provider."""
    return CLAUDE_PAUSE_SECONDS if AI_PROVIDER == "claude" else GEMINI_PAUSE_SECONDS


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    provider_label = "Claude Haiku 4.5" if AI_PROVIDER == "claude" else "Gemini 2.5 Flash"
    print(f"AI Provider: {provider_label}")
    print(f"Headlines per category: {MAX_ITEMS_PER_CATEGORY}")
    print(f"Headlines for summary:  {MAX_TITLES_FOR_SUMMARY}")

    output = {
        "generated": datetime.now(timezone.utc).strftime("%d. %B %Y, %H:%M UTC"),
        "ai_provider": provider_label,
        "categories": {},
    }

    pause = get_pause_seconds()

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

        print(f"  Calling {provider_label}…")
        summary = summarize(
            [i["title"] for i in items[:MAX_TITLES_FOR_SUMMARY]],
            cat["summary_prompt"],
        )
        print(f"  Summary: {summary[:80]}…")
        print(f"  Waiting {pause}s…")
        time.sleep(pause)

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
