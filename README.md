# Bedtime Reads

A calm, single-page reading list for the iPad: tonight's picks, space & stars, medicine, new papers
from the medical journals, physics, technology, a long read, general science, nature and tennis.
It rebuilds itself every evening from free RSS feeds and costs nothing to run.

Live at **https://naderabsy.github.io/bedtime-reads/**

## What's in here

| File | What it does |
|---|---|
| `sources.json` | The feeds and sections. Edit this to add/remove sources, change how many stories each section shows, or choose which sections feed *Tonight's picks*. |
| `sky.py` | Works out *Tonight's sky over Amman*: moon phase, sunset and darkness, visible planets, space station passes, meteor showers. Uses Skyfield (`requirements.txt`). |
| `build.py` | Fetches the feeds, picks tonight's stories, adds reading times and journal abstracts, writes the page. Python 3.9+, no installs. |
| `template.html` | The page design (night + paper themes, text size, Save for later, Continue reading). |
| `data/feed_health.json` | How each source did on recent nights (consecutive failures, newest story). |
| `data/source_problems.md` | Exists only while a source needs attention; the workflow turns it into a GitHub issue. |
| `data/history.json` | Stories already shown on earlier nights, so each new edition leads with new ones. Kept for 30 days. |
| `site/` | The built page, plus `site/archive/` with the last 7 nights. |
| `static/icon.png` | Home-screen icon. |
| `make_preview.py` | Makes a self-contained snapshot with images embedded (macOS only; for sharing a preview). |
| `.github/workflows/daily.yml` | Rebuilds and publishes the page every evening. |

## How tonight's stories are chosen

- **New first.** Anything shown on an earlier night is skipped unless a section would otherwise be
  empty. Rebuilding on the same day keeps the same stories.
- **Varied.** At most two stories per source in a section.
- **Only real reads.** Blog housekeeping ("Time off", "On vacation"), journal corrections and retraction
  notices, link round-ups ("Weekend reads"), podcast and lecture posts are dropped, as is anything under
  150 words where the length can be measured reliably.
- **No double coverage.** When two outlets report the same news under different headlines, only one
  is shown (headlines are compared by their meaningful words; study-design terms like "randomized
  trial" don't count).
- **Proper reporting before press releases.** Press-release sites (Medical Xpress, Phys.org) are used
  only when there isn't enough else. Listicles, photo galleries, quizzes, sponsored posts, webinars and
  newsletter round-ups are filtered out.
- **Free to read, no sign-up.** Before a story goes on the page, the builder opens it and drops it if
  the publisher marks it as subscriber-only (`isAccessibleForFree: false`), then fills the gap with
  the next story. Sources that need an account (New Scientist, STAT, MedPage Today, NEJM, The Lancet,
  The BMJ, MIT Technology Review, Nautilus) are left out.
- **Tonight's picks** takes the top story from Long Read, From the Journals and Space & Stars and
  puts them at the top (they aren't repeated further down).
- **Reading time** comes from the publisher's own word count where available, otherwise from the
  article text.
- **Journal stories** show the abstract's conclusion from PubMed when the feed has no summary or only a
  one-liner (JAMA). Papers are found by DOI, or by title within the journal. All journals are open access:
  JAMA Network Open (its *most read* list, tried first and allowed to reach back a month), PLOS Medicine,
  eClinicalMedicine, BMJ Medicine, and the free articles in Nature Medicine. Correction notices
  ("Error in…", "Corrigendum…") and journals' editorials about themselves are skipped.
- **Journals checked and left out:** Lancet Healthy Longevity and Lancet Digital Health (papers not open
  access), Cell Reports Medicine (some reviews not open access and can't be checked automatically),
  eBioMedicine (free but mostly lab research).

## Medicine sources

Chosen for a clinician: Derek Lowe's *In the Pipeline* (Science), *Sensible Medicine*, *Science-Based
Medicine*, *Retraction Watch* and *The Transmitter* (neuroscience), with The Guardian, BBC and Medical
Xpress health news only filling gaps. Paid-only newsletter posts are filtered out by the sign-up check.
Newsletters hosted on substack.com (e.g. Eric Topol's *Ground Truths*) can't be used: Substack refuses
GitHub's servers.

## Tonight's sky over Amman

Calculated fresh each evening for Amman (set in `sources.json` under `location`):

- **Stargazing outlook:** tonight's cloud forecast from Open-Meteo (free, no account), 20:00 to midnight,
  as a one-line verdict plus hourly cloud. Low cloud counts fully; thin high cloud counts for less, since
  the moon and bright planets usually show through it. Notes a dark (moonless) sky or a bright moon.
- **Moon:** a drawing of tonight's phase, how much is lit, moonrise/set.
- **Sun:** sunset and when it's fully dark.
- **Planets to see** around 21:00, where to look and how bright.
- **Space station:** tonight's visible passes; otherwise the next one this week, or a note when it's
  only passing before dawn (orbit data from CelesTrak).
- **Meteors:** showers active tonight.
- **Coming up:** the week's moon phases, the Moon passing close to a planet, shower peaks not yet
  active, and any lunar eclipse in the next month that's visible from Amman.

If the astronomy library isn't installed, the page simply builds without this panel.

## Try it locally

```bash
pip3 install -r requirements.txt   # optional, for the sky panel
python3 build.py
```

Then open `site/index.html` in a browser. Running it locally also updates `data/history.json`.

## Schedule

It rebuilds every afternoon at 15:23 Amman time, with a backup run at 17:53. GitHub often starts
scheduled runs late (it has been 3–7 hours on the hour), hence the odd minutes and the backup. A second
run on the same evening keeps the stories the first one chose, and a run that starts after midnight still
counts as the previous evening's edition, so no date is ever skipped. To change the times, edit the
`cron` lines in `.github/workflows/daily.yml` (they're in UTC; Amman is UTC+3). For a manual refresh: **Actions** tab →
*Build tonight's page* → **Run workflow**.

## On the iPad

Open the link in Safari → Share button → **Add to Home Screen**. It gets its own moon icon.
In the home-screen app, pull down from the top of the page to refresh (iPadOS doesn't provide this
for home-screen apps, so the page does).

- **Save for later** on any story adds it to **Saved reads**. The **Saved** button at the top (next to
  A– / A+) shows how many are waiting and opens the list. Each saved story has **Read** and **Done**;
  Done removes it, with **Undo** for a few seconds in case of a slip. Saved reads stay through the daily
  updates until he taps Done. The link `…/bedtime-reads/#saved` opens the list directly.
- **Hide or reorder sections:** each section has a **Hide** button (with Undo), and **Arrange** at the
  end of the section buttons opens a list to show, hide and move sections up or down. Remembered on the device.
- **Continue reading** at the top shows the last few stories he opened in the past week.
- **Previous nights** at the bottom: Tonight plus every kept night (about a week), the same row on every
  edition with the one being viewed highlighted. Older editions are rewritten each night so they also link
  to newer ones.
- Saved stories, text size and night/paper choice are stored on the iPad itself, so they don't
  appear on other devices.

Every link opens straight to the full article, with no account needed.

New Scientist is switched off. Its feeds are still in `sources.json`; setting
`"include_new_scientist": true` brings them back, marked **Subscriber**, for reading with his own login.

## Notes

- A feed that's down is retried once, then skipped for that day; the rest of the page still builds.
- If a source fails 3 nights in a row, or publishes nothing new for 30 days, the workflow opens an issue
  titled *Some reading sources need attention* on the repository, which emails the owner. It closes
  itself once every source works again.
- Links he has already opened turn a dimmer colour.
- When he comes back to the page, it checks `edition.json` and reloads itself if a newer edition is out,
  so he never has to pull down to refresh. Archive pages don't do this.
