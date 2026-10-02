#!/usr/bin/env python3
"""Fetch the feeds in sources.json and write a single bedtime reading page to site/index.html.

Standard library only, so it runs anywhere Python 3.9+ is installed (including GitHub Actions).
"""

import html
import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "site" / "index.html"
TEMPLATE = ROOT / "template.html"
STATIC = ROOT / "static"

UA = "Mozilla/5.0 (compatible; BedtimeReads/1.0; personal reading page)"
MAX_PER_SOURCE = 2          # keeps each section varied
SKIP_LINK_PATTERNS = ("/live/", "/video", "/videos/", "/av/", "/podcast")
# Adverts, webinars and newsletter round-ups that some feeds mix in with real articles.
SKIP_CATEGORY = re.compile(r"sponsor|partner|advertis|promoted|webinar|whitepaper|the download", re.I)
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "rss1": "http://purl.org/rss/1.0/",
}


# ---------- fetching & parsing ----------

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.img = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.parts.append(" ")
        if tag == "img" and not self.img:
            self.img = dict(attrs).get("src")

    def handle_endtag(self, tag):
        if tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "blockquote"):
            self.parts.append(" ")  # keep paragraphs from running together

    def handle_data(self, data):
        self.parts.append(data)


def strip_html(s):
    p = _Text()
    p.feed(s or "")
    text = re.sub(r"\s+", " ", html.unescape("".join(p.parts))).strip()
    return text, p.img


def shorten(text, limit=260):
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:–- ")
    return cut + "…"


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def clean_link(url):
    # Drop tracking parameters (utm_*), keep anything else.
    parts = urllib.parse.urlsplit(url.strip())
    q = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if not k.startswith("utm_")]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q)))


def first_image(el):
    # Feeds often list several sizes; take the widest so thumbnails stay sharp on the iPad's retina screen.
    best, best_w = None, -1
    for path in ("media:thumbnail", "media:content", "media:group/media:content"):
        for m in el.findall(path, NS):
            url = m.get("url")
            if url and (m.get("medium") in (None, "image") or re.search(r"\.(jpe?g|png|webp)", url, re.I)):
                w = int(m.get("width") or 0)
                if w > best_w:
                    best, best_w = url, w
    if not best:
        for enc in el.findall("enclosure"):
            if (enc.get("type") or "").startswith("image"):
                best = enc.get("url")
                break
    if best and "b-cdn.net/csz/news/tmb/" in best:  # Phys.org: swap 90px thumbnail for the 800px version
        best = best.replace("/tmb/", "/800a/")
    if best and "ichef.bbci.co.uk/ace/standard/240/" in best:  # BBC: 240px -> 976px
        best = best.replace("/240/", "/976/")
    return best


def parse_feed(raw, feed):
    root = ET.fromstring(raw)
    items = []
    entries = (root.findall("./channel/item") or root.findall("atom:entry", NS)
               or root.findall("rss1:item", NS))
    for el in entries:
        if el.tag.startswith("{%s}" % NS["rss1"]):  # RSS 1.0 / RDF (Nature, APS)
            title = el.findtext("rss1:title", "", NS)
            link = el.findtext("rss1:link", "", NS)
            body = el.findtext("rss1:description", "", NS) or el.findtext("content:encoded", "", NS)
            date = el.findtext("dc:date", "", NS)
        elif el.tag.endswith("entry"):  # Atom
            title = el.findtext("atom:title", "", NS)
            link_el = el.find("atom:link[@rel='alternate']", NS)
            if link_el is None:
                link_el = el.find("atom:link", NS)
            link = link_el.get("href") if link_el is not None else ""
            body = el.findtext("atom:summary", "", NS) or el.findtext("atom:content", "", NS)
            date = el.findtext("atom:published", "", NS) or el.findtext("atom:updated", "", NS)
        else:  # RSS
            title = el.findtext("title", "")
            link = el.findtext("link", "") or el.findtext("guid", "")
            body = el.findtext("description", "") or el.findtext("content:encoded", "", NS)
            date = el.findtext("pubDate", "") or el.findtext("dc:date", "", NS)
        summary, body_img = strip_html(body)
        # Journal feeds lead with citation boilerplate ("Nature Medicine, Published online: ...; doi:...").
        summary = re.sub(r"^[^;]{0,80}Published online:[^;]*;\s*doi:\S+\s*", "", summary)
        if re.match(r"^New England Journal of Medicine[^.]*\.[^.]*\.?$", summary):
            summary = ""
        title, _ = strip_html(title)
        title = re.sub(r"^\[[^\]]{1,30}\]\s*", "", title)  # "[Comment] ..." -> "..." (The Lancet)
        if not title or not link:
            continue
        categories = [c.text or c.get("term", "") for c in el.findall("category") + el.findall("atom:category", NS)]
        if any(SKIP_CATEGORY.search(c) for c in categories):
            continue
        items.append({
            "title": title,
            "link": clean_link(link),
            "summary": shorten(summary),
            "image": first_image(el) or body_img,
            "date": parse_date(date),
            "source": feed["name"],
            "badge": feed.get("badge") or ("Subscriber" if feed.get("subscriber") else ""),
        })
    return items


def load(feed):
    try:
        return feed, parse_feed(fetch(feed["url"]), feed), None
    except Exception as e:  # one broken feed should never break the page
        return feed, [], f"{type(e).__name__}: {e}"


# ---------- choosing tonight's picks ----------

def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def pick(items, count, max_age_days, seen):
    now = datetime.now(timezone.utc)
    fresh = [i for i in items
             if i["date"] and now - i["date"] <= timedelta(days=max_age_days)
             and not any(p in i["link"] for p in SKIP_LINK_PATTERNS)]
    # If a quiet day leaves too little, relax the age limit rather than show an empty section.
    if len(fresh) < count:
        fresh = [i for i in items if i["date"] and not any(p in i["link"] for p in SKIP_LINK_PATTERNS)]

    by_source = {}
    for i in sorted(fresh, key=lambda x: x["date"], reverse=True):
        by_source.setdefault(i["source"], []).append(i)

    # Each round takes the next-newest story from every source, newest sources first.
    order = sorted(by_source, key=lambda s: by_source[s][0]["date"], reverse=True)
    chosen = []
    for _ in range(MAX_PER_SOURCE):
        for src in order:
            queue = by_source[src]
            while queue and len(chosen) < count:
                i = queue.pop(0)
                key_l, key_t = i["link"].split("?")[0], norm_title(i["title"])
                if key_l in seen or key_t in seen:
                    continue
                seen.update((key_l, key_t))
                chosen.append(i)
                break
    chosen.sort(key=lambda x: x["date"], reverse=True)
    # Lead with a story that has a picture, if there is one.
    for n, i in enumerate(chosen):
        if i["image"]:
            chosen.insert(0, chosen.pop(n))
            break
    return chosen


# ---------- rendering ----------

def esc(s):
    return html.escape(s or "", quote=True)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def nasa_sized(url, width=1600):
    # nasa.gov serves resized copies on request, ~150 KB instead of several MB.
    if url and "nasa.gov/wp-content/uploads" in url and "?" not in url:
        return f"{url}?w={width}"
    return url


def render_story(i, lead=False):
    img = ""
    if i["image"]:
        img = f'<div class="thumb"><img src="{esc(i["image"])}" alt="" loading="lazy" decoding="async"></div>'
    badge = f'<span class="badge">{esc(i["badge"])}</span>' if i["badge"] else ""
    iso = i["date"].isoformat() if i["date"] else ""
    return f"""
      <article class="story{' lead' if lead else ''}">
        <a href="{esc(i["link"])}" target="_blank" rel="noopener">
          {img}
          <div class="text">
            <div class="meta"><span class="source">{esc(i["source"])}</span>{badge}<time datetime="{iso}"></time></div>
            <h3>{esc(i["title"])}</h3>
            {f'<p>{esc(i["summary"])}</p>' if i["summary"] else ''}
          </div>
        </a>
      </article>"""


def render(cfg, potd, sections):
    nav = "".join(f'<a href="#{slug(s["name"])}">{esc(s["name"])}</a>' for s, picks in sections if picks)
    hero = ""
    if potd:
        hero = f"""
    <section class="potd">
      <a href="{esc(potd["link"])}" target="_blank" rel="noopener">
        <img src="{esc(nasa_sized(potd["image"]))}" alt="{esc(potd["title"])}" decoding="async">
      </a>
      <div class="potd-text">
        <div class="eyebrow">Tonight’s picture · NASA Image of the Day</div>
        <h2>{esc(potd["title"])}</h2>
        <p>{esc(potd["summary"])}</p>
      </div>
    </section>"""

    body = ""
    for s, picks in sections:
        if not picks:
            continue
        stories = "".join(render_story(i, lead=(n == 0 and bool(i["image"]))) for n, i in enumerate(picks))
        body += f"""
    <section class="section" id="{slug(s["name"])}">
      <h2 class="section-title">{esc(s["name"])}</h2>
      <div class="stories">{stories}
      </div>
    </section>"""

    sources = sorted({f["name"] for s, _ in sections for f in s["feeds"]} | ({"NASA"} if potd else set()))
    built = datetime.now(timezone.utc).isoformat()
    page = TEMPLATE.read_text(encoding="utf-8")
    for key, val in {
        "{{TITLE}}": esc(cfg.get("title", "Bedtime Reads")),
        "{{BUILT}}": built,
        "{{NAV}}": nav,
        "{{HERO}}": hero,
        "{{SECTIONS}}": body,
        "{{SOURCES}}": esc(" · ".join(sources)),
    }.items():
        page = page.replace(key, val)
    return page


def main():
    cfg = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    sections_cfg = cfg["sections"]
    if not cfg.get("include_new_scientist", True):
        for s in sections_cfg:
            s["feeds"] = [f for f in s["feeds"] if not f.get("subscriber")]

    all_feeds = [f for s in sections_cfg for f in s["feeds"]]
    potd_feed = {"name": "NASA", "url": cfg["picture_of_the_day"]} if cfg.get("picture_of_the_day") else None
    jobs = all_feeds + ([potd_feed] if potd_feed else [])

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = {id(f): (items, err) for f, items, err in pool.map(load, jobs)}

    failures = [(f["name"], f["url"], results[id(f)][1]) for f in jobs if results[id(f)][1]]

    potd = None
    if potd_feed:
        potd_items = [i for i in results[id(potd_feed)][0] if i["image"]]
        potd = potd_items[0] if potd_items else None

    seen, sections = set(), []
    for s in sections_cfg:
        items = [i for f in s["feeds"] for i in results[id(f)][0]]
        sections.append((s, pick(items, s.get("count", 5), s.get("max_age_days", 4), seen)))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(cfg, potd, sections), encoding="utf-8")
    for f in STATIC.glob("*"):
        shutil.copy(f, OUT.parent / f.name)

    for s, picks in sections:
        print(f"{s['name']:<14} {len(picks)} stories  ({', '.join(sorted({i['source'] for i in picks}))})")
    print(f"Picture of the day: {potd['title'] if potd else 'none'}")
    for name, url, err in failures:
        print(f"  ! skipped {name} ({url}): {err}", file=sys.stderr)
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
