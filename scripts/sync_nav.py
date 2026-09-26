#!/usr/bin/env python3
"""Rewrite the main nav and the footer "Explore" list in every page from data/nav.json.

data/nav.json is written by tools/build.py (the NAV list): [["slug/", "Label (HTML)"], ...].
Run by .github/workflows/sync-nav.yml when data/nav.json changes, so adding a nav item only
needs data/nav.json (plus any new page) to be pushed. Output matches tools/build.py exactly.
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://blessedtouchla.com/advancinghemp/"
SKIP = (".git/", ".github/", "assets/", "data/", "img/", "scripts/", "tools/")
CUR = ' aria-current="page"'


def slug_for(rel):
    if rel == "404.html":
        return "404/"
    if rel == "index.html":
        return ""
    if rel.endswith("/index.html"):
        return rel[: -len("index.html")]
    return None


def main():
    nav = json.loads((ROOT / "data" / "nav.json").read_text(encoding="utf-8"))
    changed = 0
    for f in sorted(ROOT.rglob("*.html")):
        rel = f.relative_to(ROOT).as_posix()
        slug = slug_for(rel)
        if slug is None or rel.startswith(SKIP):
            continue
        depth = slug.count("/")
        r = "../" * depth if depth else "./"
        links = "".join(f'<a href="{r}{s}"{CUR if s == slug else ""}>{n}</a>' for s, n in nav)
        foot = "".join(f'<li><a href="{r}{s}">{n}</a></li>' for s, n in nav[1:])
        if rel == "404.html":
            links = links.replace('href="../', 'href="' + SITE)
            foot = foot.replace('href="../', 'href="' + SITE)
        t = f.read_text(encoding="utf-8")
        new = re.sub(r'<nav class="nav" aria-label="Main">.*?</nav>',
                     lambda m: f'<nav class="nav" aria-label="Main">{links}</nav>', t, count=1, flags=re.S)
        new = re.sub(r"(<h4>Explore</h4>\n<ul>).*?(</ul>)", lambda m: m.group(1) + foot + m.group(2), new, count=1, flags=re.S)
        if new != t:
            f.write_text(new, encoding="utf-8")
            changed += 1
            print("updated", rel)
    print(f"nav synced: {changed} page(s) changed")


if __name__ == "__main__":
    main()
