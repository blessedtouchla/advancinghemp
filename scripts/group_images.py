#!/usr/bin/env python3
"""Download photos for public group posts listed in data/groups.json.

Run by .github/workflows/group-images.yml whenever data/groups.json changes. For each public post
with an "image_src" (a short-lived Facebook CDN URL) and no local image yet, it downloads the photo,
resizes it to at most 1000px, saves img/groups/YYYY-MM-DD/<id>.jpg, records "image"/"w"/"h", and
removes "image_src" so the page never hotlinks Facebook. Failures set "image_failed" and the post
is shown without a photo. Image folders for days that fell out of the window are deleted.

It also unpacks photos saved on the box during capture (fbcdn URLs expire, and the GitHub connector can
only push text). tools/groups.py writes one staging file per post, data/incoming/<id>.txt:
    # advancinghemp image v1
    id=<post id>
    sha256=<hex digest of the decoded bytes>      (or  ref=<other post id>  to reuse that post's photo)
    <base64 of a small 4:3 AVIF/WebP/JPEG, any line length>
Each file is checked against its sha256, re-saved as img/groups/<card day>/<id>.jpg (this replaces any
older photo for that post), recorded as "image"/"w"/"h", and deleted. A file that fails the check is left
in place and reported so it can be re-pushed.
"""
import base64, hashlib, io, json, os, shutil, sys, urllib.request
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "groups.json")
IMGROOT = os.path.join(ROOT, "img", "groups")
INCOMING = os.path.join(ROOT, "data", "incoming")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
MAX_BYTES = 15 * 1024 * 1024


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("image too large")
    return data


def to_rgb(im):
    if im.mode not in ("RGB", "L"):
        bg = Image.new("RGB", im.size, (251, 248, 241))
        im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    return im.convert("RGB")


def parse_staged(path):
    head, body = {}, []
    with open(path, encoding="ascii") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            k, sep, v = line.partition("=")
            if sep and k in ("id", "sha256", "ref") and not body:
                head[k] = v.strip()
            else:
                body.append(line)
    return head, "".join(body)


def unpack_incoming(data):
    """Turn data/incoming/<id>.txt staging files into img/groups/<day>/<id>.jpg."""
    if not os.path.isdir(INCOMING):
        return 0, 0
    cards = {p["id"]: (day["date"], p) for day in data.get("days", []) for p in day.get("public", [])}
    files = sorted(f for f in os.listdir(INCOMING) if f.endswith(".txt"))
    staged = []
    for fn in files:
        try:
            staged.append((fn, parse_staged(os.path.join(INCOMING, fn))))
        except Exception as e:
            print(f"staged {fn}: unreadable ({e})", file=sys.stderr)
    staged.sort(key=lambda x: "ref" in x[1][0])  # real photos first, then references to them
    done = bad = 0
    for fn, (head, b64) in staged:
        path = os.path.join(INCOMING, fn)
        pid = head.get("id") or fn[:-4]
        if pid not in cards:
            print(f"staged {fn}: post {pid} is not in the feed window; removed", file=sys.stderr)
            os.remove(path)
            continue
        day, p = cards[pid]
        rel = f"img/groups/{day}/{pid}.jpg"
        out = os.path.join(ROOT, rel)
        try:
            if head.get("ref"):
                rday, rp = cards.get(head["ref"], (None, {}))
                if not rp.get("image") or not os.path.exists(os.path.join(ROOT, rp["image"])):
                    raise ValueError(f"ref {head['ref']} has no photo yet")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                if os.path.join(ROOT, rp["image"]) != out:
                    shutil.copyfile(os.path.join(ROOT, rp["image"]), out)
                w, h = rp["w"], rp["h"]
            else:
                raw = base64.b64decode(b64, validate=True)
                if hashlib.sha256(raw).hexdigest() != head.get("sha256", "").lower():
                    raise ValueError("sha256 mismatch (base64 damaged in transit)")
                im = Image.open(io.BytesIO(raw))
                im.load()
                im = to_rgb(im)
                im.thumbnail((1000, 1000), Image.LANCZOS)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                im.save(out, "JPEG", quality=85, optimize=True, progressive=True)
                w, h = im.width, im.height
        except Exception as e:
            print(f"staged {fn}: FAILED, left in place: {e}", file=sys.stderr)
            bad += 1
            continue
        p["image"], p["w"], p["h"] = rel, w, h
        p.pop("image_failed", None)
        p.pop("image_src", None)
        os.remove(path)
        done += 1
    return done, bad


def main():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    staged_ok, staged_bad = unpack_incoming(data)
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
                im = to_rgb(im)
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
    print(f"unpacked {staged_ok} staged, {staged_bad} staged failed; downloaded {got}, failed {failed}")


if __name__ == "__main__":
    main()
