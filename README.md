# Bedtime Reads

A calm, single-page reading list for the iPad: space & stars, medicine, new papers from the
medical journals, physics, technology, general science, nature and tennis. It rebuilds itself
every day from free RSS feeds and costs nothing to run.

## What's in here

| File | What it does |
|---|---|
| `sources.json` | The feeds and sections. Edit this to add/remove sources or change how many stories each section shows. |
| `build.py` | Fetches the feeds, picks tonight's stories, writes `site/index.html`. Python 3.9+, no installs. |
| `template.html` | The page design (night + paper themes, text-size buttons). |
| `static/icon.png` | Home-screen icon. |
| `.github/workflows/daily.yml` | Rebuilds and publishes the page every day. |

## Try it locally

```bash
python3 build.py
```

Then open `site/index.html` in a browser.

## Put it online (free, one-time setup, ~10 minutes)

1. Create a free account at github.com.
2. Create a new **public** repository (e.g. `bedtime-reads`) and upload everything in this folder,
   including the hidden `.github` folder.
3. In the repo: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
4. **Settings → Actions → General → Workflow permissions → Read and write permissions** → Save.
5. **Actions** tab → *Build tonight's page* → **Run workflow** (first build).
6. After a minute the page is live at `https://<your-username>.github.io/bedtime-reads/`.

From then on it rebuilds itself daily at 15:00 UTC (18:00 Amman time). To change the time, edit the `cron`
line in `.github/workflows/daily.yml` (it's in UTC).

## On the iPad

Open the link in Safari → Share button → **Add to Home Screen**. It gets its own moon icon.

New Scientist stories are marked **Subscriber**. They open on New Scientist's own site, so they
read in full as long as he's logged in to New Scientist in Safari. The page never stores or sees
his login. To leave New Scientist out entirely, set `"include_new_scientist": false` in `sources.json`.

Stories marked **Journal** (NEJM, The Lancet, The BMJ, Nature Medicine) link to the journal's own
page. Abstracts are free; full text may need his hospital or society access.

Sponsored posts, webinars and newsletter round-ups are filtered out automatically.

## Notes

- A feed that's down is skipped for that day; the rest of the page still builds.
- Links he has already tapped turn a dimmer colour.
- Text size and night/paper choice are remembered on the iPad.
