#!/usr/bin/env python3
"""Download photos for public group posts listed in data/groups.json.

Run by .github/workflows/group-images.yml whenever data/groups.json changes. For each public post
with an "image_src" (a short-lived Facebook CDN URL) and no local image yet, it downloads the photo,
resizes it to at most 1000px, saves img/groups/YYYY-MM-DD/<id>.jpg, records "image"/"w"/"h", and
removes "image_src" so the page never hotlinks Facebook. Failures set "image_failed" and the post
is shown without a photo. Image folders for days that fell out of the window are deleted.
"""
import io, json, os, shutil, sys, urllib.request
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "groups.json")
IMGROOT = os.path.join(ROOT, "img", "groups")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
MAX_BYTES = 15 * 1024 * 1024


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("image too large")
    return data


def main():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    got = failed = 0
    keep_days = set()
    for day in data.get("days", []):
        keep_days.add(day["date"])
        for p in day.get("public", []):
            src = p.pop("image_src", None)
            rel = f"img/groups/{day['date']}/{p['id']}.jpg"
            if p.get("image"):
                continue
            if os.path.exists(os.path.join(ROOT, rel)) and not src:
                with Image.open(os.path.join(ROOT, rel)) as im:
                    p["image"], p["w"], p["h"] = rel, im.width, im.height
                continue
            if not src:
                continue
            try:
                if not src.startswith("https://"):
                    raise ValueError("not https")
                im = Image.open(io.BytesIO(fetch(src)))
                im.load()
                if im.mode not in ("RGB", "L"):
                    bg = Image.new("RGB", im.size, (251, 248, 241))
                    im = im.convert("RGBA")
                    bg.paste(im, mask=im.split()[-1])
                    im = bg
                im = im.convert("RGB")
                im.thumbnail((1000, 1000), Image.LANCZOS)
                out = os.path.join(ROOT, rel)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                im.save(out, "JPEG", quality=72, optimize=True, progressive=True)
                p["image"], p["w"], p["h"] = rel, im.width, im.height
                p.pop("image_failed", None)
                got += 1
            except Exception as e:
                print(f"image failed for {p['id']}: {e}", file=sys.stderr)
                p["image_failed"] = True
                failed += 1
    if os.path.isdir(IMGROOT):
        for d in os.listdir(IMGROOT):
            if d not in keep_days:
                shutil.rmtree(os.path.join(IMGROOT, d), ignore_errors=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"downloaded {got}, failed {failed}")


if __name__ == "__main__":
    main()
