# Bedtime Reads

A calm, single-page reading list for the iPad: tonight's picks, space & stars, medicine, new papers
from the medical journals, physics, technology, a long read, general science, nature and tennis.
It rebuilds itself every evening from free RSS feeds and costs nothing to run.

Live at **https://naderabsy.github.io/bedtime-reads/**

## What's in here

| File | What it does |
|---|---|
| `sources.json` | The feeds and sections. Edit this to add/remove sources, change how many stories each section shows, or choose which sections feed *Tonight's picks*. |
| `build.py` | Fetches the feeds, picks tonight's stories, adds reading times and journal abstracts, writes the page. Python 3.9+, no installs. |
| `template.html` | The page design (night + paper themes, text size, Save for later, Continue reading). |
| `data/history.json` | Stories already shown on earlier nights, so each new edition leads with new ones. Kept for 30 days. |
| `site/` | The built page, plus `site/archive/` with the last 7 nights. |
| `static/icon.png` | Home-screen icon. |
| `make_preview.py` | Makes a self-contained snapshot with images embedded (macOS only; for sharing a preview). |
| `.github/workflows/daily.yml` | Rebuilds and publishes the page every evening. |

## How tonight's stories are chosen

- **New first.** Anything shown on an earlier night is skipped unless a section would otherwise be
  empty. Rebuilding on the same day keeps the same stories.
- **Varied.** At most two stories per source in a section.
- **Proper reporting before press releases.** Press-release sites (Medical Xpress, Phys.org) are used
  only when there isn't enough else. Listicles, photo galleries, quizzes, sponsored posts, webinars and
  newsletter round-ups are filtered out.
- **Tonight's picks** takes the top story from Long Read, From the Journals and Space & Stars and
  puts them at the top (they aren't repeated further down).
- **Reading time** comes from the publisher's own word count where available, otherwise from the
  article text. Paywalled stories (New Scientist, journals) don't get one.
- **Journal stories with no summary** (NEJM especially) get the abstract's conclusion from PubMed.

## Try it locally

```bash
python3 build.py
```

Then open `site/index.html` in a browser. Running it locally also updates `data/history.json`.

## Schedule

It rebuilds daily at 15:00 UTC (18:00 Amman time). To change the time, edit the `cron` line in
`.github/workflows/daily.yml` (it's in UTC). For a manual refresh: **Actions** tab →
*Build tonight's page* → **Run workflow**.

## On the iPad

Open the link in Safari → Share button → **Add to Home Screen**. It gets its own moon icon.

- **Save for later** on any story puts it in a *Saved for later* list at the top of the page. It stays
  there through daily updates until he taps **Done**.
- **Continue reading** at the top shows the last few stories he opened in the past week.
- **Previous nights** at the bottom opens any of the last 7 editions.
- Saved stories, text size and night/paper choice are stored on the iPad itself, so they don't
  appear on other devices.

New Scientist stories are marked **Subscriber**. They open on New Scientist's own site, so they
read in full as long as he's logged in to New Scientist in Safari. The page never stores or sees
his login. To leave New Scientist out entirely, set `"include_new_scientist": false` in `sources.json`.

Stories marked **Journal** (NEJM, The Lancet, The BMJ, Nature Medicine) link to the journal's own
page. Abstracts are free; full text may need his hospital or society access.

## Notes

- A feed that's down is retried once, then skipped for that day; the rest of the page still builds.
- Links he has already opened turn a dimmer colour.
