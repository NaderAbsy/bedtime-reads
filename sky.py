"""Tonight's sky for one place: moon, sun, visible planets, space station passes and meteor showers.

Uses Skyfield (pip install skyfield). The planetary ephemeris (de421.bsp, ~17 MB) is downloaded once
into .skyfield/ and reused; the space station's orbit comes fresh from CelesTrak each evening.
"""

import json
import math
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from skyfield import almanac, eclipselib
from skyfield.api import EarthSatellite, Loader, wgs84

try:
    from skyfield.magnitudelib import planetary_magnitude
except ImportError:  # older Skyfield
    planetary_magnitude = None

CACHE = Path(__file__).parent / ".skyfield"
FORECAST = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&hourly=cloud_cover_low,cloud_cover_mid,cloud_cover_high,precipitation_probability"
            "&timezone=auto&forecast_days=3")
ISS_TLE = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"

PLANETS = [("Mercury", "mercury"), ("Venus", "venus"), ("Mars", "mars"),
           ("Jupiter", "jupiter barycenter"), ("Saturn", "saturn barycenter")]

# Major annual showers (International Meteor Organization calendar): active window, peak, best rate per hour.
SHOWERS = [
    ("Quadrantids", (12, 28), (1, 12), (1, 3), 80),
    ("Lyrids", (4, 14), (4, 30), (4, 22), 18),
    ("Eta Aquariids", (4, 19), (5, 28), (5, 6), 50),
    ("Southern Delta Aquariids", (7, 12), (8, 23), (7, 30), 25),
    ("Perseids", (7, 17), (8, 24), (8, 12), 100),
    ("Draconids", (10, 6), (10, 10), (10, 8), 10),
    ("Orionids", (10, 2), (11, 7), (10, 21), 20),
    ("Leonids", (11, 6), (11, 30), (11, 17), 15),
    ("Geminids", (12, 4), (12, 20), (12, 14), 150),
    ("Ursids", (12, 17), (12, 26), (12, 22), 10),
]

COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
SHORT = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def direction(az_deg):
    return COMPASS[int((az_deg % 360) / 45 + 0.5) % 8]


def short_dir(az_deg):
    return SHORT[int((az_deg % 360) / 22.5 + 0.5) % 16]


def height(alt_deg):
    if alt_deg < 15:
        return "low"
    if alt_deg < 40:
        return "partway up"
    if alt_deg < 65:
        return "high"
    return "almost overhead"


def brightness(mag):
    if mag is None:
        return ""
    if mag < -2:
        return "very bright"
    if mag < 0.5:
        return "bright"
    if mag < 2:
        return "easy to see"
    return "faint"


def phase_name(deg):
    names = [(22.5, "New moon"), (67.5, "Waxing crescent"), (112.5, "First quarter"), (157.5, "Waxing gibbous"),
             (202.5, "Full moon"), (247.5, "Waning gibbous"), (292.5, "Last quarter"), (337.5, "Waning crescent"),
             (360.1, "New moon")]
    return next(name for limit, name in names if deg < limit)


def in_window(day, start, end):
    """Is `day` within a (month, day) range that may wrap over New Year?"""
    s = date(day.year, *start)
    e = date(day.year, *end)
    if e < s:  # wraps the year end
        return day >= s or day <= e
    return s <= day <= e


def showers_tonight(day, moon_lit):
    out = []
    for name, start, end, peak, zhr in SHOWERS:
        if not in_window(day, start, end):
            continue
        peak_day = date(day.year, *peak)
        if peak[0] == 1 and day.month == 12:
            peak_day = date(day.year + 1, *peak)
        days_to_peak = (peak_day - day).days
        if abs(days_to_peak) <= 1:
            when = "peaks tonight"
        elif days_to_peak > 1:
            when = f"active; peaks {peak_day.day} {peak_day:%B}"
        else:
            when = "active, past its peak"
        note = f"up to about {zhr} an hour at its peak from a dark site"
        if moon_lit > 0.6:
            note += "; the bright moon will hide the fainter ones"
        out.append({"name": name, "when": when, "note": note})
    return out


def cloud_forecast(lat, lon, day, fetch, moon_lit, moon_up_evening):
    """Tonight's stargazing outlook from Open-Meteo (free, no account), 20:00 to midnight.

    Low cloud blocks everything; high, thin cloud mostly lets the moon and bright planets through,
    so it counts for less."""
    try:
        data = json.loads(fetch(FORECAST.format(lat=lat, lon=lon)))
    except Exception:
        return None
    h = data["hourly"]
    want = [f"{day.isoformat()}T{hh:02d}:00" for hh in (20, 21, 22, 23)] + [f"{(day + timedelta(days=1)).isoformat()}T00:00"]
    hours = []
    for stamp in want:
        if stamp not in h["time"]:
            continue
        n = h["time"].index(stamp)
        low, mid, high = (h[k][n] or 0 for k in ("cloud_cover_low", "cloud_cover_mid", "cloud_cover_high"))
        eff = min(100, round(max(low, mid * 0.85, high * 0.45)))
        hours.append({"hour": stamp[11:13], "cloud": eff, "rain": h["precipitation_probability"][n] or 0,
                      "thin": high > 60 and low < 20 and mid < 30})
    if not hours:
        return None
    avg = sum(x["cloud"] for x in hours) / len(hours)
    if avg < 20:
        verdict, rating = "Clear skies tonight", "good"
    elif avg < 45:
        verdict, rating = "Mostly clear, with some cloud", "good"
    elif avg < 75:
        verdict, rating = "Partly cloudy: look for gaps", "fair"
    else:
        verdict, rating = "Cloudy tonight", "poor"
    notes = []
    first, last = hours[0]["cloud"], hours[-1]["cloud"]
    if first >= 60 and last <= 30:
        clear_at = next(x["hour"] for x in hours if x["cloud"] <= 30)
        notes.append(f"clearing from about {clear_at}:00")
    elif first <= 30 and last >= 60:
        cloud_at = next(x["hour"] for x in hours if x["cloud"] >= 60)
        notes.append(f"clouding over from about {cloud_at}:00")
    if any(x["thin"] for x in hours) and rating != "good":
        notes.append("mostly thin high cloud, so the moon and bright planets should still show")
    if max(x["rain"] for x in hours) >= 50:
        notes.append("chance of rain")
    if rating == "good":
        if moon_lit < 0.25 or not moon_up_evening:
            notes.append("no bright moon, so it's a dark sky for faint stars")
        elif moon_lit > 0.75:
            notes.append("a bright moon will wash out fainter stars")
    return {"verdict": verdict, "rating": rating, "notes": notes, "hours": hours}


def iss_passes(sat, place, observer, sun, eph, begin, end, hm, day_label=None):
    """Visible passes: the station is sunlit while the observer's sky is dark."""
    out, current = [], {}
    times, events = sat.find_events(place, begin, end, altitude_degrees=10.0)
    for t, e in zip(times, events):
        if e == 0:
            current = {"rise": t}
        elif e == 1 and current:
            current["top"] = t
        elif e == 2 and "top" in current:
            top = current["top"]
            s_alt = observer.at(top).observe(sun).apparent().altaz()[0].degrees
            if sat.at(top).is_sunlit(eph) and s_alt < -6:
                rel = lambda tt: (sat - place).at(tt).altaz()
                r_alt, r_az, _ = rel(current["rise"])
                m_alt, m_az, _ = rel(top)
                e_alt, e_az, _ = rel(t)
                out.append({
                    "time": hm(current["rise"]), "day": day_label,
                    "from": direction(r_az.degrees),
                    "top_alt": round(m_alt.degrees), "top_dir": direction(m_az.degrees),
                    "to": direction(e_az.degrees),
                    "minutes": max(1, round((t - current["rise"]) * 24 * 60)),
                })
            current = {}
    return out


def tonight(lat, lon, elevation_m, tz, day, fetch=None):
    loader = Loader(str(CACHE), verbose=False)
    ts = loader.timescale()
    eph = loader("de421.bsp")
    earth, sun, moon = eph["earth"], eph["sun"], eph["moon"]
    place = wgs84.latlon(lat, lon, elevation_m=elevation_m)
    observer = earth + place

    noon = datetime.combine(day, dtime(12, 0), tz)
    t0, t1 = ts.from_datetime(noon), ts.from_datetime(noon + timedelta(days=1))
    local = lambda t: t.utc_datetime().astimezone(tz)
    hm = lambda t: local(t).strftime("%H:%M")

    # Sunset, and when the sky is properly dark (astronomical twilight ends).
    times, events = almanac.find_discrete(t0, t1, almanac.sunrise_sunset(eph, place))
    sunset = next((t for t, e in zip(times, events) if not e), None)
    sunrise = next((t for t, e in zip(times, events) if e), None)
    times, events = almanac.find_discrete(t0, t1, almanac.dark_twilight_day(eph, place))
    dark = next((t for t, e in zip(times, events) if e == 0), None)

    # Moon
    t_eve = ts.from_datetime(datetime.combine(day, dtime(21, 0), tz))
    phase = almanac.moon_phase(eph, t_eve).degrees
    lit = float(almanac.fraction_illuminated(eph, "moon", t_eve))
    times, events = almanac.find_discrete(t0, t1, almanac.risings_and_settings(eph, moon, place))
    evening = ts.from_datetime(datetime.combine(day, dtime(17, 0), tz))
    morning = ts.from_datetime(datetime.combine(day + timedelta(days=1), dtime(6, 0), tz))
    moon_events = [("rises" if e else "sets", hm(t)) for t, e in zip(times, events) if evening.tt <= t.tt <= morning.tt]
    alt, az, _ = observer.at(t_eve).observe(moon).apparent().altaz()

    # Planets: where to look around bedtime. Try 21:00 first, then later until midnight,
    # then early evening (for planets that set soon after dark).
    base = datetime.combine(day, dtime(20, 0), tz)
    order = list(range(4, 17)) + list(range(0, 4))  # quarter-hours after 20:00
    samples = [ts.from_datetime(base + timedelta(minutes=15 * k)) for k in order]
    planets = []
    for label, key in PLANETS:
        body = eph[key]
        best = None
        for t in samples:
            s_alt = observer.at(t).observe(sun).apparent().altaz()[0].degrees
            if s_alt > -8:
                continue
            p_alt, p_az, _ = observer.at(t).observe(body).apparent().altaz()
            if p_alt.degrees >= 10:
                best = (t, p_alt.degrees, p_az.degrees)
                break
        if not best:
            continue
        mag = None
        if planetary_magnitude:
            try:
                mag = float(planetary_magnitude(observer.at(best[0]).observe(body)))
            except Exception:
                pass
        planets.append({
            "name": label, "time": hm(best[0]), "alt": round(best[1]), "dir": direction(best[2]),
            "height": height(best[1]), "brightness": brightness(mag),
        })
    planets.sort(key=lambda p: p["time"] < "20:00" or p["time"] > "23:59")

    def evening_window(d):
        start = ts.from_datetime(datetime.combine(d, dtime(18, 0), tz))
        stop = ts.from_datetime(datetime.combine(d + timedelta(days=1), dtime(1, 0), tz))
        return start, stop

    # Space station: tonight's visible passes, and the next ones this week.
    iss, iss_next, iss_morning, sat = [], [], None, None
    if fetch:
        try:
            lines = [l.strip() for l in fetch(ISS_TLE).decode().splitlines() if l.strip()]
            sat = EarthSatellite(lines[1], lines[2], lines[0], ts)
            begin = sunset if sunset is not None else t0
            iss = iss_passes(sat, place, observer, sun, eph, begin, evening_window(day)[1], hm)
            for k in range(1, 8):
                d = day + timedelta(days=k)
                passes = iss_passes(sat, place, observer, sun, eph, *evening_window(d), hm, day_label=d)
                iss_next += passes
                if len(iss_next) >= 2:
                    break
            # Some weeks the station only passes before dawn; say so rather than just "none".
            if not iss and not iss_next:
                for k in range(1, 8):
                    d = day + timedelta(days=k)
                    a = ts.from_datetime(datetime.combine(d, dtime(3, 0), tz))
                    b = ts.from_datetime(datetime.combine(d, dtime(7, 0), tz))
                    morning_passes = iss_passes(sat, place, observer, sun, eph, a, b, hm, day_label=d)
                    if morning_passes:
                        iss_morning = morning_passes[0]
                        break
        except Exception:
            iss = None  # orbit data unavailable tonight

    # ---------- coming up: the next week (and a month for eclipses) ----------
    coming = []
    label = lambda d: f"{d:%a} {d.day} {d:%b}"

    if iss is not None and not iss and iss_next:
        p = iss_next[0]
        bright = "very bright, " if p["top_alt"] >= 50 else ""
        coming.append({"date": p["day"], "text": f"Space station visible at {p['time']}: {bright}climbs to "
                       f"{p['top_alt']}° in the {p['top_dir']}, {p['minutes']} min."})

    # Moon phases in the next 7 days.
    wk0, wk1 = ts.from_datetime(datetime.combine(day + timedelta(days=1), dtime(0, 0), tz)), \
               ts.from_datetime(datetime.combine(day + timedelta(days=8), dtime(0, 0), tz))
    times, phases = almanac.find_discrete(wk0, wk1, almanac.moon_phases(eph))
    phase_text = {0: "New moon: the darkest skies of the month", 1: "First quarter moon",
                  2: "Full moon", 3: "Last quarter moon"}
    for t, ph in zip(times, phases):
        d = local(t).date()
        coming.append({"date": d, "text": phase_text[int(ph)] + "."})

    # The moon passing close to a bright planet in the evening sky.
    for k in range(1, 8):
        d = day + timedelta(days=k)
        t = ts.from_datetime(datetime.combine(d, dtime(21, 0), tz))
        m_pos = observer.at(t).observe(moon).apparent()
        m_alt = m_pos.altaz()[0].degrees
        for name, key in PLANETS:
            p_pos = observer.at(t).observe(eph[key]).apparent()
            sep = m_pos.separation_from(p_pos).degrees
            p_alt, p_az, _ = p_pos.altaz()
            if sep < 6 and p_alt.degrees > 10 and m_alt > 10:
                coming.append({"date": d, "text": f"The Moon passes close to {name} ({sep:.0f}° apart), "
                               f"in the {direction(p_az.degrees)} at 21:00."})

    # Meteor shower peaks in the next 14 days.
    for name, start, end, peak, zhr in SHOWERS:
        if in_window(day, start, end):
            continue  # already active: the Meteors box covers it
        for year in (day.year, day.year + 1):
            pd = date(year, *peak)
            if 1 <= (pd - day).days <= 14:
                coming.append({"date": pd, "text": f"{name} meteor shower peaks (up to about {zhr} an hour)."})

    # Lunar eclipses in the next 30 days that can be seen from here.
    try:
        e0 = ts.from_datetime(datetime.combine(day, dtime(12, 0), tz))
        e1 = ts.from_datetime(datetime.combine(day + timedelta(days=30), dtime(12, 0), tz))
        e_times, e_kinds, _ = eclipselib.lunar_eclipses(e0, e1, eph)
        for t, kind in zip(e_times, e_kinds):
            if observer.at(t).observe(moon).apparent().altaz()[0].degrees > 0:
                coming.append({"date": local(t).date(), "text": f"{eclipselib.LUNAR_ECLIPSES[kind]} lunar eclipse, "
                               f"visible from here, greatest at {hm(t)}."})
    except Exception:
        pass

    coming.sort(key=lambda c: c["date"])
    for c in coming:
        c["when"] = label(c["date"])
        c["date"] = c["date"].isoformat()

    moon_up_evening = any(verb == "rises" and t < "22:00" for verb, t in moon_events) or bool(alt.degrees > 0)
    weather = cloud_forecast(lat, lon, day, fetch, lit, moon_up_evening) if fetch else None

    return {
        "sunset": hm(sunset) if sunset is not None else None,
        "dark": hm(dark) if dark is not None else None,
        "sunrise": hm(sunrise) if sunrise is not None else None,
        "moon": {
            "phase": phase_name(phase), "deg": float(phase), "lit": lit, "waxing": bool(phase < 180),
            "events": moon_events, "up_at_9": bool(alt.degrees > 0),
            "dir_at_9": direction(az.degrees), "alt_at_9": round(alt.degrees),
        },
        "planets": planets,
        "iss": iss,
        "showers": showers_tonight(day, lit),
        "iss_next": [dict(p, day=f"{p['day']:%a} {p['day'].day} {p['day']:%b}") for p in iss_next[:1]],
        "iss_morning": dict(iss_morning, day=f"{iss_morning['day']:%a} {iss_morning['day'].day} {iss_morning['day']:%b}") if iss_morning else None,
        "coming": coming[:6],
        "weather": weather,
    }
