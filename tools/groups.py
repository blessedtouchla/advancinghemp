#!/usr/bin/env python3
"""Normalize Victoria's Facebook-group captures into data/groups.json for Advancing Hemp.

Usage (from anywhere):  python3 /workspace/hemp/site/tools/groups.py [--raw-dir DIR] [--out FILE] [--no-remote]

Reads every raw-YYYY-MM-DD.json in the raw dir (default /workspace/hemp/groups), plus two
side files in the same dir:
  private-summaries.json  {"<post id>": "one neutral line, own words, no names/quotes"}
  skip.json               {"<post id>": "reason"}   (manual skips; automatic THC/CBD filter also applies)

Rules (confirmed by Victoria):
  * Public groups: author display name, group, date, <=300-char excerpt, "View on Facebook"
    (permalink, else the group URL), photo if one was captured (downloaded by the repo's
    group-images workflow; fbcdn is never hotlinked by the page).
  * Private groups: ONE neutral line per post from private-summaries.json. No names, quotes
    or photos; link to the group page only. Posts without a summary are held back and listed.
  * Skip THC/CBD/smokable promotions and spam.
Private raw data never leaves the box; only the normalized file is published.
"""
import argparse, glob, hashlib, json, os, re, sys, urllib.request
from datetime import datetime, timedelta, date

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMOTE = "https://raw.githubusercontent.com/blessedtouchla/advancinghemp/main/data/groups.json"
WINDOW_DAYS = 14
EXCERPT_MAX = 300

# Canonical group registry, keyed by Facebook group URL. Privacy here wins over the raw file
# (a group is treated as private if either says so).
GROUPS = {
    "https://www.facebook.com/groups/1392294576098522/": ("Industrial Hemp Academy", "public"),
    "https://www.facebook.com/groups/395029814965473/": ("Hemp Momma", "public"),
    "https://www.facebook.com/groups/growinghempassociation.org/": ("Growing Hemp Association", "public"),
    "https://www.facebook.com/groups/448586385680305/": ("Utah Hemp Growers Association", "private"),
    "https://www.facebook.com/groups/142962773764672/": ("Togo Hemp Association", "private"),
    "https://www.facebook.com/groups/2492877584288370/": ("Industrial Hemp Is Common Sense", "public"),
    "https://www.facebook.com/groups/HempcreteNetwork/": ("HempcreteNetwork.com", "public"),
    "https://www.facebook.com/groups/3396410027066803/": ("FarmDirectHemp Farm Network", "public"),
    "https://www.facebook.com/groups/LancashireJobsBoard": ("Hemp Education", "public"),
    "https://www.facebook.com/groups/475085136623739/": ("Hemp Building Association of New Zealand", "private"),
    "https://www.facebook.com/groups/568271623218736/": ("Hemp Building Australia", "public"),
    "https://www.facebook.com/groups/652149055682690/": ("Hempcrete building, development and discussion", "public"),
    "https://www.facebook.com/groups/260413469329951/": ("Michigan Hempcrete & Plastic Innovations", "public"),
}
EXCLUDED_GROUPS = ("hempcoin",)  # never shown

# Automatic skip: selling/promoting THC/CBD/smokables, plus common spam.
BLOCK = re.compile(r"\b(thc|cbd|cbg|cbn|thca|delta[\s-]?[89]|d[89]\b|hhc|cannabinoids?|gumm(y|ies)|edibles?|"
                   r"pre-?rolls?|blunts?|smokables?|smoke\s+shops?|vapes?|vaping|dispensar(y|ies)|"
                   r"flower\s+for\s+sale|kratom|420|weed|stoner|high\s+potency|"
                   r"crypto|forex|bitcoin|investment\s+opportunit|dm\s+me\s+for|whatsapp|telegram|"
                   r"loan\s+offer|work\s+from\s+home)\b", re.I)

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                      "august", "september", "october", "november", "december"], 1)}
MON3 = {k[:3]: v for k, v in MONTHS.items()}


def norm_url(u):
    u = (u or "").strip()
    if re.match(r"^https://www\.facebook\.com/groups/[^/?#]+$", u) and not u.endswith("LancashireJobsBoard"):
        u += "/"
    return u


def parse_when(s, cap):
    """Turn Facebook's relative/absolute date text into an approximate datetime (capture tz)."""
    t = (s or "").lower().strip()
    t = re.sub(r"\(.*?\)", "", t).strip()
    if not t or t in ("just now", "now"):
        return cap
    m = re.match(r"^(an?|about an?|\d+)\s*(minute|min|m|hour|hr|h|day|d|week|wk|w|month|year|yr|y)s?\b(\s+ago)?", t)
    if m:
        n = 1 if m.group(1).startswith(("a", "about")) else int(m.group(1))
        u = m.group(2)
        if u in ("minute", "min", "m"): return cap - timedelta(minutes=n)
        if u in ("hour", "hr", "h"): return cap - timedelta(hours=n)
        if u in ("day", "d"): return cap - timedelta(days=n)
        if u in ("week", "wk", "w"): return cap - timedelta(weeks=n)
        if u == "month": return cap - timedelta(days=30 * n)
        return cap - timedelta(days=365 * n)
    m = re.match(r"^yesterday(?:\s+at\s+(\d{1,2}):(\d{2})\s*([ap]m))?", t)
    if m:
        d = cap - timedelta(days=1)
        return _at(d, m.group(1), m.group(2), m.group(3))
    m = re.match(r"^([a-z]+)\s+(\d{1,2})(?:,?\s+(\d{4}))?(?:\s+at\s+(\d{1,2}):(\d{2})\s*([ap]m))?", t)
    if m and (m.group(1) in MONTHS or m.group(1)[:3] in MON3):
        mo = MONTHS.get(m.group(1)) or MON3[m.group(1)[:3]]
        yr = int(m.group(3)) if m.group(3) else cap.year
        d = cap.replace(year=yr, month=mo, day=int(m.group(2)), hour=12, minute=0, second=0, microsecond=0)
        if not m.group(3) and d > cap + timedelta(days=1):
            d = d.replace(year=yr - 1)
        return _at(d, m.group(4), m.group(5), m.group(6))
    print(f"  ! unparsed date {s!r}; using capture time", file=sys.stderr)
    return cap


def _at(d, hh, mm, ap):
    if not hh:
        return d.replace(hour=12, minute=0, second=0, microsecond=0)
    h = int(hh) % 12 + (12 if ap == "pm" else 0)
    return d.replace(hour=h, minute=int(mm), second=0, microsecond=0)


def clean_text(t):
    t = (t or "").replace("\u00a0", " ")
    t = re.sub(r"https?://(?:www\.)?([^/\s]+)\S*", r"\1", t)      # bare URLs -> domain text
    t = re.sub(r"\s+", " ", t).strip()
    truncated = bool(re.search(r"(…|\.\.\.)\s*$", t))
    t = re.sub(r"\s*(…|\.\.\.)\s*$", "", t).strip()
    return t, truncated


def excerpt(t):
    t, cut = clean_text(t)
    if len(t) > EXCERPT_MAX:
        t = t[:EXCERPT_MAX + 1]
        sp = t.rfind(" ")
        t = t[:sp if sp > EXCERPT_MAX * 0.6 else EXCERPT_MAX]
        cut = True
    t = t.rstrip(" ,;:-–—")
    if cut:
        t = t.rstrip(" .,;:-–—!?")
    return t + ("…" if cut and t else "")


def pid(*parts):
    return hashlib.sha1("|".join(p or "" for p in parts).encode()).hexdigest()[:12]


def load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default="/workspace/hemp/groups")
    ap.add_argument("--out", default=os.path.join(SITE, "data", "groups.json"))
    ap.add_argument("--no-remote", action="store_true", help="don't merge image status from the live repo")
    a = ap.parse_args()

    raws = sorted(glob.glob(os.path.join(a.raw_dir, "raw-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json")))
    if not raws:
        sys.exit("no raw files found")
    summaries = load_json(os.path.join(a.raw_dir, "private-summaries.json"), {})
    manual_skip = load_json(os.path.join(a.raw_dir, "skip.json"), {})

    prev = {}
    if not a.no_remote:
        try:
            req = urllib.request.Request(REMOTE + "?t=" + str(int(datetime.now().timestamp())), headers={"User-Agent": "advancinghemp-groups/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                for d in json.load(r).get("days", []):
                    for p in d.get("public", []):
                        prev[p["id"]] = p
        except Exception as e:
            print(f"  (no remote data merged: {e})", file=sys.stderr)

    public, private, skipped, held = {}, {}, [], []
    latest_cap = None
    for path in raws:  # oldest first, so the first sighting's date wins
        raw = load_json(path, {})
        cap = datetime.fromisoformat(raw["captured_at"])
        latest_cap = cap if latest_cap is None or cap > latest_cap else latest_cap
        for g in raw.get("groups", []):
            url = norm_url(g.get("url"))
            name0 = g.get("name", "")
            if any(x in name0.lower() for x in EXCLUDED_GROUPS):
                continue
            name, priv = GROUPS.get(url, (re.sub(r"\.\.\.$", "", name0).strip(), "public"))
            is_private = priv == "private" or str(g.get("privacy", "")).lower().startswith("private")
            ginfo = {"name": name, "url": url}
            for p in g.get("posts", []):
                author = (p.get("author") or "").strip()
                text = p.get("text") or ""
                key_text, _ = clean_text(text)
                key = pid(author, key_text[:160])
                when = parse_when(p.get("date"), cap)
                if key in manual_skip or BLOCK.search(text):
                    reason = manual_skip.get(key) or "automatic THC/CBD/smokable/spam filter"
                    skipped.append({"id": key, "group": name, "private": is_private, "reason": reason,
                                    "text": key_text[:90]})
                    continue
                if is_private:
                    rec = private.setdefault(key, {"id": key, "groups": [], "when": when, "author": author,
                                                   "text": key_text})
                    if ginfo not in rec["groups"]:
                        rec["groups"].append(ginfo)
                    continue
                rec = public.get(key)
                if rec is None:
                    rec = public[key] = {"id": key, "author": author or "A group member", "groups": [],
                                         "excerpt": excerpt(text), "media": p.get("media") or "text",
                                         "link": None, "is_permalink": False, "when": when,
                                         "image_url": None}
                if ginfo not in rec["groups"]:
                    rec["groups"].append(ginfo)
                if p.get("permalink") and not rec["is_permalink"]:
                    rec["link"], rec["is_permalink"] = p["permalink"], True
                if p.get("image_url") and not rec["image_url"]:
                    rec["image_url"] = p["image_url"]

    # Private posts that are the same post as a public one (e.g. cross-posted) are already shown publicly.
    folded = [k for k in private if k in public]
    for k in folded:
        del private[k]

    cutoff = (latest_cap - timedelta(days=WINDOW_DAYS - 1)).date()
    days = {}
    for rec in public.values():
        d = rec["when"].date()
        if d < cutoff:
            continue
        out = {"id": rec["id"], "author": rec["author"], "groups": rec["groups"], "excerpt": rec["excerpt"],
               "media": rec["media"], "link": rec["link"] or rec["groups"][0]["url"],
               "is_permalink": rec["is_permalink"], "time": rec["when"].isoformat(timespec="minutes")}
        old = prev.get(rec["id"], {})
        if old.get("image"):
            out["image"] = old["image"]
            for k in ("w", "h"):
                if old.get(k): out[k] = old[k]
        elif old.get("image_failed"):
            out["image_failed"] = True
        elif rec["image_url"] and rec["image_url"].startswith("https://"):
            out["image_src"] = rec["image_url"]  # fetched + removed by .github/workflows/group-images.yml
        days.setdefault(d.isoformat(), {"public": [], "private": []})["public"].append(out)
    for rec in private.values():
        d = rec["when"].date()
        if d < cutoff:
            continue
        s = (summaries.get(rec["id"]) or "").strip()
        if not s:
            held.append(rec)
            continue
        days.setdefault(d.isoformat(), {"public": [], "private": []})["private"].append(
            {"id": rec["id"], "groups": rec["groups"], "summary": s, "_t": rec["when"].isoformat()})

    out_days = []
    for d in sorted(days, reverse=True):
        pub = sorted(days[d]["public"], key=lambda x: x["time"], reverse=True)
        pri = sorted(days[d]["private"], key=lambda x: x["_t"], reverse=True)
        for x in pri: x.pop("_t")
        out_days.append({"date": d, "public": pub, "private": pri})

    data = {"updated": latest_cap.isoformat(timespec="minutes"), "window_days": WINDOW_DAYS, "days": out_days}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")

    npub = sum(len(d["public"]) for d in out_days)
    npri = sum(len(d["private"]) for d in out_days)
    print(f"wrote {a.out}: {len(out_days)} days, {npub} public posts, {npri} private one-liners")
    print(f"  folded {len(folded)} private cross-posts that are already public; skipped {len(skipped)}")
    for s in skipped:
        print(f"  SKIP {s['id']} [{s['group']}] {s['reason']}: {s['text']!r}")
    pending = sum(1 for d in out_days for p in d["public"] if p.get("image_src"))
    print(f"  images pending download by the repo workflow: {pending}")
    if held:
        print(f"  HELD BACK {len(held)} private post(s) with no summary. Add lines to private-summaries.json:")
        for r in held:
            print(f"    \"{r['id']}\": \"...\"   # {', '.join(g['name'] for g in r['groups'])}: {r['text'][:140]!r}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
