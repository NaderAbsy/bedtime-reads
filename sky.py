"""Tonight's sky for one place: moon, sun, visible planets, space station passes and meteor showers.

Uses Skyfield (pip install skyfield). The planetary ephemeris (de421.bsp, ~17 MB) is downloaded once
into .skyfield/ and reused; the space station's orbit comes fresh from CelesTrak each evening.
"""

import math
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from skyfield import almanac
from skyfield.api import EarthSatellite, Loader, wgs84

try:
    from skyfield.magnitudelib import planetary_magnitude
except ImportError:  # older Skyfield
    planetary_magnitude = None

CACHE = Path(__file__).parent / ".skyfield"
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

    # Space station: passes from sunset to 01:00 that are sunlit while the observer's sky is dark.
    iss = []
    if fetch:
        try:
            lines = [l.strip() for l in fetch(ISS_TLE).decode().splitlines() if l.strip()]
            sat = EarthSatellite(lines[1], lines[2], lines[0], ts)
            end = ts.from_datetime(datetime.combine(day + timedelta(days=1), dtime(1, 0), tz))
            begin = sunset if sunset is not None else t0
            times, events = sat.find_events(place, begin, end, altitude_degrees=10.0)
            current = {}
            for t, e in zip(times, events):
                if e == 0:
                    current = {"rise": t}
                elif e == 1 and current:
                    current["top"] = t
                elif e == 2 and "top" in current:
                    current["set"] = t
                    top = current["top"]
                    s_alt = observer.at(top).observe(sun).apparent().altaz()[0].degrees
                    if sat.at(top).is_sunlit(eph) and s_alt < -6:
                        rel = lambda tt: (sat - place).at(tt).altaz()
                        r_alt, r_az, _ = rel(current["rise"])
                        m_alt, m_az, _ = rel(top)
                        e_alt, e_az, _ = rel(t)
                        iss.append({
                            "time": hm(current["rise"]),
                            "from": direction(r_az.degrees),
                            "top_alt": round(m_alt.degrees), "top_dir": direction(m_az.degrees),
                            "to": direction(e_az.degrees),
                            "minutes": max(1, round((t - current["rise"]) * 24 * 60)),
                        })
                    current = {}
        except Exception:
            iss = None  # orbit data unavailable tonight

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
    }
