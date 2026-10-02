#!/usr/bin/env python3
"""Turn site/index.html into a self-contained snapshot (preview/bedtime-reads.html).

Images are downloaded, shrunk with macOS `sips`, and embedded as data URIs, so the page
works where outside images are blocked (e.g. a Claude artifact link). macOS only.
"""

import base64
import re
import subprocess
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "site" / "index.html"
OUT = ROOT / "preview" / "bedtime-reads.html"
UA = "Mozilla/5.0 (compatible; BedtimeReads/1.0; personal reading page)"


def embed(job):
    url, width = job
    try:
        req = urllib.request.Request(url.replace("&amp;", "&"), headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=20).read()
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / "in", Path(d) / "out.jpg"
            src.write_bytes(raw)
            subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "70",
                            "--resampleWidth", str(width), str(src), "--out", str(dst)],
                           check=True, capture_output=True)
            return url, "data:image/jpeg;base64," + base64.b64encode(dst.read_bytes()).decode()
    except Exception as e:
        print(f"  ! image skipped: {url[:80]} ({e})")
        return url, None


def main():
    page = SRC.read_text(encoding="utf-8")

    # Full-width images (picture of the day, lead stories) get more pixels than thumbnails.
    jobs = {}
    for m in re.finditer(r'<(section class="potd"|article class="story lead"|article class="story")(.*?)</(section|article)>', page, re.S):
        width = 320 if m.group(1) == 'article class="story"' else 1200
        for src in re.findall(r'<img src="([^"]+)"', m.group(2)):
            jobs[src] = max(width, jobs.get(src, 0))

    with ThreadPoolExecutor(max_workers=10) as pool:
        for url, data in pool.map(embed, jobs.items()):
            if data:
                page = page.replace(f'src="{url}"', f'src="{data}"')
            else:  # drop the empty frame rather than show a blank box
                page = re.sub(r'<div class="thumb"><img src="%s"[^>]*></div>' % re.escape(url), "", page)

    # The artifact host supplies the document skeleton: keep the <title>, styles and body content.
    title = re.search(r"<title>.*?</title>", page, re.S).group(0)
    styles = "".join(re.findall(r"<style>.*?</style>", page, re.S))
    head_scripts = "".join(re.findall(r"<script>.*?</script>", page.split("</head>")[0], re.S))
    body = page.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(f"{title}\n{styles}\n{head_scripts}\n{body}", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB, {len(jobs)} images)")


if __name__ == "__main__":
    main()
