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
- **Pictures:** a story the feed gives no picture for borrows its article's own preview image, unless that
  image is the site's default (a logo or share card, or the same on several stories, or the site's front-page
  image), is under 400px wide, or doesn't load. Journals are skipped (their preview images are figures or
  covers). A source can name where its pictures live (`image_pattern`; used for ESA).
- **Long Read** shows four stories (one of them can move up to Tonight's picks). Picks prefer a story
  within the section's age limit, and a real photo. Sources: Aeon, Quanta, Knowable, Undark, and Big Think's
  *Starts With A Bang* science column (the feed also carries lifestyle posts, so only that column's links
  are kept via `link_contains`). Checked and left out: Asimov Press (Substack-hosted, so GitHub's servers
  are refused; half its posts are interviews), Ars Technica Features (mostly gadget reviews), Scientific
  American (subscriber-only), Wired (metered), Noema (politics and philosophy), The Conversation's topic
  feeds (stale or off-topic), Hakai (future dates).
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

It rebuilds every morning at 10:23 Amman time, with a backup run at 12:53. GitHub starts scheduled runs
late: measured over 54 runs in October and November 2026, the median delay was 3.9 hours and the worst was
8, and builds scheduled for the afternoon were landing between 20:00 and 23:30. Scheduling in the morning
means even an 8-hour delay still finishes before the evening. A second run on the same day keeps the
stories the first one chose, and a run that starts after midnight still counts as the previous day's
edition, so no date is ever skipped. To change the times, edit the `cron` lines in
`.github/workflows/daily.yml` (they're in UTC; Amman is UTC+3). Don't schedule earlier than 03:00 UTC.
For a manual refresh: **Actions** tab → *Build tonight's page* → **Run workflow**.

If an edition is late or a build fails, readers are told: after 20:00 in Amman with no edition for the day
yet, or when the newest edition is older than yesterday's, a notice at the top says so (the page first
checks whether a newer edition exists and reloads to it instead).

## For readers

Several people can read it, each on their own phone, iPad or computer, with no accounts. Everything personal
(saved stories, what's been opened, section order, text size, theme) is kept on each device separately.
New readers see a short welcome card once; **How this page works** in the footer shows it again.

On an iPhone or iPad: open the link in Safari → Share button → **Add to Home Screen**. It gets its own moon icon.
In the home-screen app, pull down from the top of the page to refresh (iPadOS doesn't provide this
for home-screen apps, so the page does).

- **Save for later** on any story adds it to **Saved reads**. The **Saved** button at the top (next to
  A– / A+) shows how many are waiting and opens the list. Each saved story has **Read** and **Done**;
  Done removes it, with **Undo** for a few seconds in case of a slip. Saved reads stay through the daily
  updates until the reader taps Done. The link `…/bedtime-reads/#saved` opens the list directly.
- **Hide or reorder sections:** each section has a **Hide** button (with Undo), and **Arrange** at the
  end of the section buttons opens a list to show, hide and move sections up or down. Remembered on the device.
- **New** tags mark stories this device hasn't had on screen before. A story counts as seen after it has
  been at least half visible for a second. Tags are decided when the page loads and never disappear while
  it's open; a device's first visit shows none (everything would be new). Works on previous nights too, so
  it's a way to catch up on what was missed. Kept per device, for 30 days.
- **Share** on any story opens the device's share sheet (Messages, WhatsApp, Mail), or copies the link.
- **Continue reading** at the top shows the last few stories opened on that device in the past week.
- **Previous nights** at the bottom: Tonight plus every kept night (about a week), the same row on every
  edition with the one being viewed highlighted. Older editions are rewritten each night so they also link
  to newer ones.
- Stories already opened turn grey. This uses each device's own browsing history, so one reader's
  reading never greys out stories for anyone else.

Every link opens straight to the full article, with no account needed.

New Scientist is switched off. Its feeds are still in `sources.json`; setting
`"include_new_scientist": true` brings them back, marked **Subscriber**, for readers with their own login.

## Notes

- A feed that's down is retried once, then skipped for that day; the rest of the page still builds.
- If a source fails 3 nights in a row, or publishes nothing new for 30 days, the workflow opens an issue
  titled *Some reading sources need attention* on the repository, which emails the owner. It closes
  itself once every source works again.
- When a reader comes back to the page, it checks `edition.json` and reloads itself if a newer edition is out,
  so nobody has to pull down to refresh. Archive pages don't do this.
