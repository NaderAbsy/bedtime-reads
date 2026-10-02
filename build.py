#!/usr/bin/env python3
"""Fetch the feeds in sources.json and write tonight's bedtime reading page.

Writes:
  site/index.html                 tonight's edition
  site/archive/YYYY-MM-DD.html    a copy for "Previous nights"
  data/history.json               what has been shown, so tomorrow's page leads with new stories

Standard library only, so it runs anywhere Python 3.9+ is installed (including GitHub Actions).
"""

import html
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

ROOT = Path(__file__).parent
SITE = ROOT / "site"
ARCHIVE = SITE / "archive"
HISTORY = ROOT / "data" / "history.json"
TEMPLATE = ROOT / "template.html"
STATIC = ROOT / "static"

UA = "Mozilla/5.0 (compatible; BedtimeReads/1.0; personal reading page)"
MAX_PER_SOURCE = 2          # keeps each section varied
WORDS_PER_MINUTE = 230
SKIP_LINK_PATTERNS = ("/live/", "/video", "/videos/", "/av/", "/podcast")
# Adverts, webinars and newsletter round-ups that some feeds mix in with real articles.
SKIP_CATEGORY = re.compile(r"sponsor|partner|advertis|promoted|webinar|whitepaper|the download", re.I)
# Listicles, galleries and quizzes: fine elsewhere, out of place on this page.
SKIP_TITLE = re.compile(
    r"^(these |the )?\d+\s+(\w+\s+){0,2}(photos|pictures|images|things|ways|reasons|facts|places)\b"
    r"|\bphotos of\b|\bin pictures\b|\bquiz\b|\bcrossword\b|\bpuzzle\b",
    re.I,
)
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "rss1": "http://purl.org/rss/1.0/",
}


# ---------- fetching & parsing ----------

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
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


def link_key(url):
    return url.split("?")[0].split("#")[0].rstrip("/").lower()


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
        if el.tag.startswith("{%s}" % NS["rss1"]):  # RSS 1.0 / RDF (Nature, APS, NEJM)
            title = el.findtext("rss1:title", "", NS)
            link = el.findtext("rss1:link", "", NS)
            body = el.findtext("rss1:description", "", NS) or el.findtext("content:encoded", "", NS)
            date_s = el.findtext("dc:date", "", NS)
        elif el.tag.endswith("entry"):  # Atom
            title = el.findtext("atom:title", "", NS)
            link_el = el.find("atom:link[@rel='alternate']", NS)
            if link_el is None:
                link_el = el.find("atom:link", NS)
            link = link_el.get("href") if link_el is not None else ""
            body = el.findtext("atom:summary", "", NS) or el.findtext("atom:content", "", NS)
            date_s = el.findtext("atom:published", "", NS) or el.findtext("atom:updated", "", NS)
        else:  # RSS 2.0
            title = el.findtext("title", "")
            link = el.findtext("link", "") or el.findtext("guid", "")
            body = el.findtext("description", "") or el.findtext("content:encoded", "", NS)
            date_s = el.findtext("pubDate", "") or el.findtext("dc:date", "", NS)
        summary, body_img = strip_html(body)
        # Journal feeds lead with citation boilerplate ("Nature Medicine, Published online: ...; doi:...").
        summary = re.sub(r"^[^;]{0,80}Published online:[^;]*;\s*doi:\S+\s*", "", summary)
        # Some feeds (The Guardian) give the standfirst and then the opening paragraph, which repeats it.
        opening = " ".join(summary.split()[:5])
        if len(opening) > 20 and summary.find(opening, len(opening)) > 0:
            summary = summary[:summary.find(opening, len(opening))].strip()
        # WordPress footer: "The post <title> appeared first on <site>."
        summary = re.sub(r"\s*The post .{0,300}? appeared first on .{0,80}$", "", summary)
        if re.match(r"^New England Journal of Medicine[^.]*\.[^.]*\.?$", summary):
            summary = ""
        title, _ = strip_html(title)
        title = re.sub(r"^\[[^\]]{1,30}\]\s*", "", title)  # "[Comment] ..." -> "..." (The Lancet)
        if not title or not link or SKIP_TITLE.search(title):
            continue
        categories = [c.text or c.get("term", "") for c in el.findall("category") + el.findall("atom:category", NS)]
        if any(SKIP_CATEGORY.search(c) for c in categories):
            continue
        link = clean_link(link)
        if any(p in link for p in SKIP_LINK_PATTERNS):
            continue
        items.append({
            "title": title,
            "link": link,
            "key": link_key(link),
            "summary": shorten(summary),
            "image": first_image(el) or body_img,
            "date": parse_date(date_s),
            "source": feed["name"],
            "badge": feed.get("badge") or ("Subscriber" if feed.get("subscriber") else ""),
            "low_priority": bool(feed.get("low_priority")),
            "subscriber": bool(feed.get("subscriber")),
            "journal": bool(feed.get("journal")),
            "page": None,
            "lead_ok": feed.get("lead_ok", True),
            "minutes": None,
        })
    return items


def load(feed):
    err = None
    for _ in range(2):  # news sites sometimes hiccup; one retry is enough
        raw = b""
        try:
            raw = fetch(feed["url"])
            return feed, parse_feed(raw, feed), None
        except Exception as e:  # one broken feed should never break the page
            err = f"{type(e).__name__}: {e}"
            if raw:
                err += f" | got: {raw[:120]!r}"
            time.sleep(3)
    return feed, [], err


# ---------- choosing tonight's stories ----------

def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def pick(items, count, max_age_days, used, shown_before, now):
    """Choose a section's stories: new-to-him first, varied across sources, newest first."""
    dated = [i for i in items if i["date"]]
    age = lambda i: now - i["date"]
    is_new = lambda i: i["key"] not in shown_before
    tiers = [
        [i for i in dated if is_new(i) and age(i) <= timedelta(days=max_age_days)],
        # A quiet day: reach further back for something he hasn't seen before repeating anything.
        [i for i in dated if is_new(i) and age(i) <= timedelta(days=max_age_days * 3)],
        [i for i in dated if age(i) <= timedelta(days=max_age_days)],
        dated,
    ]

    chosen, per_source = [], {}

    def take(i, cap=True):
        k_t = norm_title(i["title"])
        if i["key"] in used or k_t in used or (cap and per_source.get(i["source"], 0) >= MAX_PER_SOURCE):
            return False
        used.update((i["key"], k_t))
        per_source[i["source"]] = per_source.get(i["source"], 0) + 1
        chosen.append(i)
        return True

    for n, tier in enumerate(tiers):
        by_source = {}
        for i in sorted(tier, key=lambda x: x["date"], reverse=True):
            by_source.setdefault(i["source"], []).append(i)
        # Proper reporting before press-release sites; within that, the freshest source first.
        order = sorted(by_source, key=lambda s: (by_source[s][0]["low_priority"], -by_source[s][0]["date"].timestamp()))
        progress = True
        while len(chosen) < count and progress:
            progress = False
            for src in order:
                queue = by_source[src]
                while queue and len(chosen) < count:
                    if take(queue.pop(0), cap=(n < len(tiers) - 1)):
                        progress = True
                        break

    return chosen


def is_paywalled(item):
    """Open the article; publishers mark locked pages with isAccessibleForFree: false."""
    if item["subscriber"]:  # his own subscription (New Scientist) is allowed through
        return False
    try:
        item["page"] = fetch(item["link"], timeout=15).decode("utf-8", "replace")
    except Exception:
        return False  # can't tell (some free sites block automated visits); keep it
    return bool(re.search(r'"isAccessibleForFree"\s*:\s*"?false', item["page"], re.I))


def finish(candidates, count):
    """Drop anything behind a sign-up wall, keep the best `count`, newest first, a photo on top."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        locked = list(pool.map(is_paywalled, candidates))
    chosen = [i for i, lock in zip(candidates, locked) if not lock][:count]
    chosen.sort(key=lambda x: x["date"], reverse=True)
    # Lead with a real photo: prefer sources whose pictures aren't charts or figures.
    leads = [i for i in chosen if i["image"] and i["lead_ok"] and not i["low_priority"]] or \
            [i for i in chosen if i["image"]]
    if leads:
        chosen.remove(leads[0])
        chosen.insert(0, leads[0])
    return chosen, sum(locked)


# ---------- extra detail for the chosen stories ----------

def reading_minutes(item):
    """Estimate reading time from the article's paragraphs. Subscriber-only sources are skipped."""
    if item["subscriber"]:
        return
    page = item["page"]
    if page is None:
        try:
            page = fetch(item["link"], timeout=15).decode("utf-8", "replace")
        except Exception:
            return

    def count(fragment):
        n = 0
        for p in re.findall(r"<p[^>]*>(.*?)</p>", fragment, re.S | re.I):
            w = len(re.sub(r"<[^>]+>", " ", p).split())
            if w >= 8:  # skip captions, bylines and buttons
                n += w
        return n

    # Best: the publisher's own word count. Next: the <article> body. Last resort: the whole page.
    stated = re.search(r'"wordCount"\s*:\s*"?(\d+)', page)
    words = int(stated.group(1)) if stated else 0
    if not words:
        words = max((count(a) for a in re.findall(r"<article\b.*?</article>", page, re.S | re.I)), default=0)
    if words < 150:
        words = count(page)
    if 150 <= words <= 15000:
        item["minutes"] = max(1, round(words / WORDS_PER_MINUTE))


def pubmed_summary(item):
    """Journal feeds (NEJM especially) often give no summary. Pull the abstract's conclusion from PubMed."""
    m = re.search(r"10\.\d{4,9}/[^\s?#&]+", urllib.parse.unquote(item["link"]))
    if not m:
        return
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    try:
        q = urllib.parse.quote(m.group(0).rstrip(".") + "[doi]")
        ids = json.loads(fetch(f"{base}esearch.fcgi?db=pubmed&retmode=json&term={q}"))["esearchresult"]["idlist"]
        if not ids:
            return
        time.sleep(0.4)  # PubMed asks for at most 3 requests a second
        xml = fetch(f"{base}efetch.fcgi?db=pubmed&rettype=abstract&retmode=xml&id={ids[0]}").decode("utf-8", "replace")
    except Exception:
        return
    parts = re.findall(r'<AbstractText(?:[^>]*Label="([^"]*)")?[^>]*>(.*?)</AbstractText>', xml, re.S)
    if not parts:
        return
    conclusions = [t for label, t in parts if label.upper().startswith("CONCLUSION")]
    text = strip_html(conclusions[0] if conclusions else parts[0][1])[0]
    item["summary"] = shorten(("Conclusions: " if conclusions else "") + text, 320)


def enrich(stories):
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(reading_minutes, stories))
    for i in stories:
        if not i["summary"] and i["journal"]:
            pubmed_summary(i)
            time.sleep(0.4)


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


def long_date(d):
    return f"{d:%A} {d.day} {d:%B}"


def render_story(i, kind="", label=""):
    img = ""
    if i["image"]:
        img = f'<div class="thumb"><img src="{esc(i["image"])}" alt="" loading="lazy" decoding="async"></div>'
    badge = f'<span class="badge">{esc(i["badge"])}</span>' if i["badge"] else ""
    minutes = f'<span class="mins">{i["minutes"]} min read</span>' if i["minutes"] else ""
    iso = i["date"].isoformat() if i["date"] else ""
    eyebrow = f'<div class="pick-label">{esc(label)}</div>' if label else ""
    return f"""
      <article class="story{' ' + kind if kind else ''}{'' if i['image'] else ' no-image'}" data-k="{esc(i["key"])}">
        {img}
        <div class="text">
          {eyebrow}
          <div class="meta"><span class="source">{esc(i["source"])}</span>{badge}<time datetime="{iso}"></time>{minutes}</div>
          <h3><a href="{esc(i["link"])}" target="_blank" rel="noopener">{esc(i["title"])}</a></h3>
          {f'<p>{esc(i["summary"])}</p>' if i["summary"] else ''}
          <button class="save" type="button" aria-pressed="false">Save for later</button>
        </div>
      </article>"""


def render(cfg, edition, built, potd, picks, sections, editions, base, is_archive):
    nav = "".join(f'<a href="#{slug(s["name"])}">{esc(s["name"])}</a>' for s, stories in sections if stories)

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

    picks_html = ""
    if picks:
        cards = "".join(render_story(i, "pick", label) for label, i in picks)
        picks_html = f"""
    <section class="section picks" id="tonights-picks">
      <h2 class="section-title">Tonight’s picks</h2>
      <div class="pick-grid">{cards}
      </div>
    </section>"""

    body = ""
    for s, stories in sections:
        if not stories:
            continue
        cards = "".join(render_story(i, "lead" if n == 0 and i["image"] else "") for n, i in enumerate(stories))
        body += f"""
    <section class="section" id="{slug(s["name"])}">
      <h2 class="section-title">{esc(s["name"])}</h2>
      <div class="stories">{cards}
      </div>
    </section>"""

    prefix = "" if is_archive else "archive/"
    others = [d for d in editions if d != edition][:7]
    archive = ""
    if others:
        links = "".join(f'<a href="{prefix}{d.isoformat()}.html">{d:%a} {d.day} {d:%b}</a>' for d in others)
        archive = f'<nav class="previous" aria-label="Previous nights"><span>Previous nights</span>{links}</nav>'

    banner = ""
    if is_archive:
        banner = f'<p class="banner">This is the edition from {long_date(edition)}. <a href="../">Go to tonight’s →</a></p>'

    sources = sorted({f["name"] for s, _ in sections for f in s["feeds"]} | ({"NASA"} if potd else set()))
    page = TEMPLATE.read_text(encoding="utf-8")
    for key, val in {
        "{{TITLE}}": esc(cfg.get("title", "Bedtime Reads")),
        "{{BASE}}": base,
        "{{EDITION}}": long_date(edition),
        "{{BANNER}}": banner,
        "{{BUILT}}": built,
        "{{NAV}}": nav,
        "{{HERO}}": hero,
        "{{PICKS}}": picks_html,
        "{{SECTIONS}}": body,
        "{{ARCHIVE}}": archive,
        "{{SOURCES}}": esc(" · ".join(sources)),
    }.items():
        page = page.replace(key, val)
    return page


# ---------- main ----------

def main():
    cfg = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    tz = timezone.utc
    if ZoneInfo and cfg.get("timezone"):
        try:
            tz = ZoneInfo(cfg["timezone"])
        except Exception:
            pass
    now = datetime.now(timezone.utc)
    edition = now.astimezone(tz).date()

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

    # History: stories first shown on an earlier night count as "seen". Same-day rebuilds stay stable.
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else {}
    shown_before = {k for k, d in history.items() if d < edition.isoformat()}

    used, sections, locked = set(), [], 0
    for s in sections_cfg:
        items = [i for f in s["feeds"] for i in results[id(f)][0]]
        count = s.get("count", 4)
        # Take spares, so stories dropped for being behind a sign-up wall can be replaced.
        candidates = pick(items, count * 2 + 2, s.get("max_age_days", 4), used, shown_before, now)
        stories, n_locked = finish(candidates, count)
        locked += n_locked
        sections.append((s, stories))

    # Tonight's picks: the lead story of chosen sections, moved to the top (not shown twice).
    picks = []
    for name in cfg.get("picks", []):
        for s, stories in sections:
            if s["name"] == name and stories:
                picks.append((name, stories.pop(0)))

    shown = [i for _, i in picks] + [i for _, stories in sections for i in stories]
    enrich(shown)

    for i in shown:
        history.setdefault(i["key"], edition.isoformat())
    cutoff = (edition - timedelta(days=cfg.get("history_days", 30))).isoformat()
    history = {k: d for k, d in sorted(history.items()) if d >= cutoff}
    HISTORY.parent.mkdir(exist_ok=True)
    HISTORY.write_text(json.dumps(history, indent=0, sort_keys=True) + "\n")

    # Previous nights: keep a week or so of editions.
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    keep_from = edition - timedelta(days=cfg.get("archive_days", 7))
    for f in ARCHIVE.glob("*.html"):
        try:
            if date.fromisoformat(f.stem) < keep_from:
                f.unlink()
        except ValueError:
            pass
    editions = sorted({date.fromisoformat(f.stem) for f in ARCHIVE.glob("*.html")} | {edition}, reverse=True)

    built = now.isoformat()
    (SITE / "index.html").write_text(
        render(cfg, edition, built, potd, picks, sections, editions, base="", is_archive=False), encoding="utf-8")
    (ARCHIVE / f"{edition.isoformat()}.html").write_text(
        render(cfg, edition, built, potd, picks, sections, editions, base="../", is_archive=True), encoding="utf-8")
    for f in STATIC.glob("*"):
        shutil.copy(f, SITE / f.name)

    print(f"Edition {edition}  ({len(shown_before)} stories remembered from earlier nights)")
    for label, i in picks:
        print(f"Pick      {label}: {i['title'][:70]}")
    for s, stories in sections:
        new = sum(1 for i in stories if i["key"] not in shown_before)
        print(f"{s['name']:<20} {len(stories)} stories, {new} new  ({', '.join(sorted({i['source'] for i in stories}))})")
    print(f"Skipped {locked} stories that need a sign-up or subscription")
    timed = sum(1 for i in shown if i["minutes"])
    print(f"Reading times found for {timed} of {len(shown)} stories")
    print(f"Picture of the day: {potd['title'] if potd else 'none'}")
    for name, url, err in failures:
        print(f"  ! skipped {name} ({url}): {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
