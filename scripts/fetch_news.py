#!/usr/bin/env python3
"""Fetch hemp-building news feeds and write news.json (stdlib only).

Keeps the previous items for a source if a fetch fails, so the page never goes blank.
Skips items about cannabinoids/THC/CBD so the feed stays on hemp building and industry.
"sources" feed the Hemp News page; "orgs" (hemp organizations' own feeds, headlines only)
feed the "From hemp organizations" section on /news/.
"""
import json, re, sys, html, time, datetime, urllib.request, email.utils
import xml.etree.ElementTree as ET
from pathlib import Path

UA = "AdvancingHempNewsBot/1.0 (+https://blessedtouchla.com/advancinghemp/; advancinghemp@gmail.com)"
SOURCES = [
    {"id": "hempsupporter", "name": "Hemp Supporter", "site": "https://hempsupporter.com/",
     "url": "https://hempsupporter.com/feed/"},
    {"id": "google-hempcrete", "name": "Google News: \u201chempcrete\u201d", "site": "https://news.google.com/search?q=hempcrete",
     "url": "https://news.google.com/rss/search?q=hempcrete&hl=en-US&gl=US&ceid=US:en"},
    {"id": "r-hempcrete", "name": "Reddit r/hempcrete", "site": "https://www.reddit.com/r/hempcrete/",
     "url": "https://www.reddit.com/r/hempcrete/.rss"},
    {"id": "r-hemp", "name": "Reddit r/hemp", "site": "https://www.reddit.com/r/hemp/",
     "url": "https://www.reddit.com/r/hemp/.rss",
     # r/hemp is broad, so only keep posts that look like building, materials, industry or policy news.
     "require": r"hempcrete|hemp ?lime|build|construct|insulat|hurd|fib(er|re)|textile|fabric|rope|paper|plastic|material|processing|industrial|farm|crop|acre|law|bill\b|rules?\b|regulat|congress|senate|jobs?\b|econom|policy|wall"},
]
PER_SOURCE = 5
# Hemp organizations' own feeds. Headlines, dates and links only, credited to each org.
ORG_SOURCES = [
    {"id": "nihc", "name": "National Industrial Hemp Council", "site": "https://nihcoa.com/", "url": "https://nihcoa.com/feed/"},
    {"id": "ushba", "name": "U.S. Hemp Building Association", "site": "https://www.ushempbuilding.org/", "url": "https://www.ushempbuilding.org/blog-feed.xml"},
    {"id": "hbi", "name": "Hemp Building Institute", "site": "https://www.hempbuildinginstitute.org/", "url": "https://www.hempbuildinginstitute.org/blog-feed.xml"},
    {"id": "hempbuild", "name": "HempBuild Magazine", "site": "https://www.hempbuildmag.com/", "url": "https://www.hempbuildmag.com/home?format=rss"},
    {"id": "hemi", "name": "Hemp Education & Marketing Initiatives", "site": "https://hempinitiatives.org/", "url": "https://hempinitiatives.org/feed/"},
    {"id": "hfc", "name": "Hemp Feed Coalition", "site": "https://hempfeedcoalition.org/", "url": "https://hempfeedcoalition.org/feed/"},
    {"id": "indhemp", "name": "IND HEMP", "site": "https://indhemp.com/", "url": "https://indhemp.com/feed/"},
    {"id": "ihi", "name": "Industrial Hemp International", "site": "https://industrialhempinternational.com/", "url": "https://industrialhempinternational.com/feed/"},
    {"id": "eiha", "name": "European Industrial Hemp Association", "site": "https://eiha.org/", "url": "https://eiha.org/feed/"},
    {"id": "mhc", "name": "Midwest Hemp Council", "site": "https://www.midwesthempcouncil.com/", "url": "https://www.midwesthempcouncil.com/hempnews?format=rss"},
    {"id": "hemptoday", "name": "HempToday", "site": "https://hemptoday.net/", "url": "https://hemptoday.net/feed/"},
    # The committee covers all of agriculture, so keep only hemp and Farm Bill items.
    {"id": "house-ag", "name": "House Agriculture Committee", "site": "https://agriculture.house.gov/", "url": "https://agriculture.house.gov/news/rss.aspx",
     "require": r"hemp|farm bill|farm, food,? and national security", "https": True},
]
PER_ORG = 3
BLOCK_ANY = re.compile(r"marijuana|cannabis ?(club|shop|store|dispensary)|kush|stoner|seed ?co\b|witch\w* ?brew|humidity pack|fuck|shit|pegged|\blube\b|\bass\b|gelato|frosty", re.I)
BLOCK = re.compile(r"\b(thc|thca|cbd|cbg|cbn|delta[- ]?[89]|d8|d9|cannabinoid\w*|marijuana|weed|dispensar\w*|gumm(y|ies)|edibles?|vape\w*|pre-?rolls?|smok\w*|flowers?|kratom|psychedelic\w*|high|strains?|genetics|terps?|terpenes?|buds?|nugs?|420|stoned|blunts?|joints?|jars?|grow ?tents?|indoor grow)\b", re.I)
A = "{http://www.w3.org/2005/Atom}"
OUT = Path(__file__).resolve().parent.parent / "news.json"


def clean(s, n=None):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or "")).replace("\ufeff", "")
    s = re.sub(r"submitted by\s+/u/\S+|\[link\]|\[comments\]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if n and len(s) > n:
        s = s[: n - 1].rsplit(" ", 1)[0] + "\u2026"
    return s


def iso(d):
    if not d:
        return None
    try:
        return email.utils.parsedate_to_datetime(d).astimezone(datetime.timezone.utc).isoformat()
    except Exception:
        pass
    try:
        return datetime.datetime.fromisoformat(d.replace("Z", "+00:00")).astimezone(datetime.timezone.utc).isoformat()
    except Exception:
        return None


def fetch(url, tries=3):
    urls = [url]
    last = None
    for attempt in range(tries):
        for u in urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                head = raw[:500].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
                if not (head.startswith(b"<?xml") or head.startswith(b"<rss") or head.startswith(b"<feed")):
                    raise ValueError("response was not an RSS/Atom feed")
                return raw
            except Exception as e:
                last = e
        time.sleep(15 * (attempt + 1))
    raise last


def _entity(m):
    name = m.group(1)
    if name in ("amp", "lt", "gt", "quot", "apos"):
        return m.group(0)
    u = html.unescape(m.group(0))
    return "".join("&#%d;" % ord(ch) for ch in u) if u != m.group(0) else "&amp;" + name + ";"


def xml_root(raw):
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        # Some feeds (e.g. Squarespace) use HTML entities like &nbsp; that XML doesn't define.
        txt = re.sub(r"&([A-Za-z][A-Za-z0-9]*);", _entity, raw.decode("utf-8", "replace"))
        return ET.fromstring(txt.encode("utf-8"))


def parse(raw):
    root = xml_root(raw)
    items = []
    if root.tag == A + "feed":
        for e in root.findall(A + "entry"):
            link = ""
            for l in e.findall(A + "link"):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", "")
            items.append({
                "title": clean(e.findtext(A + "title")),
                "link": link,
                "date": iso(e.findtext(A + "published") or e.findtext(A + "updated")),
                "summary": clean(e.findtext(A + "content") or e.findtext(A + "summary"), 220),
            })
    else:
        for it in root.iter("item"):
            src = it.find("source")
            items.append({
                "title": clean(it.findtext("title")),
                "link": (it.findtext("link") or "").strip(),
                "date": iso(it.findtext("pubDate")),
                "summary": clean(it.findtext("description"), 220),
                "publisher": clean(src.text) if src is not None else None,
            })
    return items


def collect(sources, old, per, now):
    out = []
    for s in sources:
        entry = {k: s[k] for k in ("id", "name", "site")}
        try:
            items = parse(fetch(s["url"]))
            items = [i for i in items if i["title"] and i["link"] and not BLOCK.search(i["title"] + " " + (i.get("summary") or ""))
                     and not BLOCK_ANY.search(i["title"] + " " + (i.get("summary") or "") + " " + i["link"])]
            if s.get("require"):
                req = re.compile(s["require"], re.I)
                items = [i for i in items if req.search(i["title"] + " " + (i.get("summary") or ""))]
            seen, uniq = set(), []
            for i in items:
                key = re.sub(r"\W+", "", re.sub(r" - [^-]+$", "", i["title"]).lower())
                if key not in seen:
                    seen.add(key); uniq.append(i)
            items = uniq
            if s.get("https"):
                for i in items:
                    i["link"] = re.sub(r"^http://", "https://", i["link"])
            if s["id"] == "google-hempcrete":
                for i in items:
                    i["summary"] = ""  # Google News descriptions are just link lists
            items.sort(key=lambda i: i["date"] or "", reverse=True)
            entry.update(items=items[:per], fetched=now, ok=True)
            print(f"{s['id']}: {len(items)} usable items", file=sys.stderr)
        except Exception as e:
            prev = old.get(s["id"], {})
            entry.update(items=prev.get("items", []), fetched=prev.get("fetched"), ok=False, error=str(e)[:200])
            print(f"{s['id']}: FAILED {e}", file=sys.stderr)
        out.append(entry)
        time.sleep(2)
    return out


def main():
    old, old_orgs = {}, {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text())
            old = {s["id"]: s for s in prev.get("sources", [])}
            old_orgs = {s["id"]: s for s in prev.get("orgs", [])}
        except Exception:
            pass
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    out = collect(SOURCES, old, PER_SOURCE, now)
    orgs = collect(ORG_SOURCES, old_orgs, PER_ORG, now)
    for o in orgs:  # headlines only on the org section
        for i in o["items"]:
            i.pop("summary", None); i.pop("publisher", None)
    OUT.write_text(json.dumps({"updated": now, "sources": out, "orgs": orgs}, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
