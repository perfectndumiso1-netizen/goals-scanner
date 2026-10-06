"""Weather for a fixture — Open-Meteo (free, no key, no sign-up) + free geocoding for the venue.

Why this is the smallest useful weather layer:
  * the specification is explicit — normal weather means **no adjustment**, so the only thing worth fetching is
    whether conditions are genuinely relevant (severe);
  * forecasts are only meaningful near kick-off, so requests are limited to fixtures inside a short horizon
    (`RES_WEATHER_HORIZON_H`, default 48 h) and cached (`RES_TTL_H`);
  * nothing is guessed: a fixture whose venue cannot be geocoded simply carries a weather fact of "N/A".

Venue coordinates come from a cache (`data/research/venues.json`) filled by OpenStreetMap Nominatim, one request
per second at most, a handful of new venues per run — and kept forever afterwards, so the cost is paid once.
"""
from __future__ import annotations

import json
import logging
import os
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .facts import Fact, as_aware, make_fact

log = logging.getLogger("research.weather")

GEO_URL = "https://nominatim.openstreetmap.org/search"
GEO_UA = "PlayReport/1.0 (+https://github.com/perfectndumiso1-netizen/goals-scanner)"
OM_URL = "https://api.open-meteo.com/v1/forecast"
OM_SOURCE = "Open-Meteo (CC-BY 4.0)"
TIMEOUT = 20

# "Relevant" thresholds — deliberately conservative; anything below these is normal weather and never adjusts.
SEVERE_WIND_KMH = 45.0
SEVERE_RAIN_MM_H = 4.0
SEVERE_HEAT_C = 34.0
SEVERE_COLD_C = 1.0
STORM_CODES = {95, 96, 99}
SNOW_CODES = {71, 73, 75, 77, 85, 86, 56, 57, 66, 67}


def _slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    return "".join(ch if ch.isalnum() else "-" for ch in s).strip("-")


class Venues:
    """Cached venue coordinates.  `lookup()` returns None when the venue is unknown — never a guess."""

    def __init__(self, path: Path, budget: int = 8, min_interval_s: float = 1.1):
        self.path = Path(path)
        self.budget = int(budget)
        self.min_interval = float(min_interval_s)
        self.used = 0
        self._last_call = 0.0
        self.data: dict[str, dict] = {}
        self._dirty = False
        try:
            if self.path.exists():
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)
        self._dirty = False

    def lookup(self, venue: str, now: datetime) -> dict | None:
        key = _slug(venue)
        if not key:
            return None
        rec = self.data.get(key)
        if rec is not None:
            return rec if rec.get("lat") is not None else None
        if self.used >= self.budget:
            return None
        wait = self.min_interval - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(min(wait, 1.2))
        self._last_call = time.time()
        self.used += 1
        try:
            r = requests.get(GEO_URL, params={"q": f"{venue} stadium", "format": "json", "limit": 1},
                             headers={"User-Agent": GEO_UA}, timeout=TIMEOUT)
            hits = r.json() if r.status_code == 200 else []
        except Exception as exc:  # noqa: BLE001 - a collector must fail soft on any transport error
            log.warning("Geocoding failed for %r: %s", venue, exc)
            return None      # transport failure: NOT cached, so the next run retries rather than giving up
        # A successful query with no result is remembered (so we never hammer the geocoder for the same venue
        # every half hour); a *failed* request above is not, so a transient outage does not lose the venue.
        rec = {"lat": None, "lon": None, "display": "", "ts": now.strftime("%Y-%m-%d")}
        if hits:
            rec.update({"lat": float(hits[0]["lat"]), "lon": float(hits[0]["lon"]),
                        "display": str(hits[0].get("display_name") or "")[:120]})
        self.data[key] = rec
        self._dirty = True
        return rec if rec["lat"] is not None else None


class WeatherCache:
    """Persistent cache for forecasts + the per-run request budget.

    Keyed by rounded coordinates *and* the forecast hour, so the same fixture re-researched across the
    half-hourly runs costs nothing until the TTL expires.  Without this, ~250 fixtures per run would mean
    thousands of calls a day; with it, one forecast per (venue, hour) per TTL.
    """

    def __init__(self, path: Path | None, ttl_h: float = 6.0, budget: int = 60):
        self.path = Path(path) if path else None
        self.ttl_s = float(ttl_h) * 3600
        self.budget = int(budget)
        self.used = 0
        self.data: dict[str, dict] = {}
        self._dirty = False
        try:
            if self.path and self.path.exists():
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def get(self, key: str) -> dict | None:
        rec = self.data.get(key)
        if not rec or (time.time() - float(rec.get("ts", 0))) >= self.ttl_s:
            return None
        return rec.get("w")

    def put(self, key: str, w: dict) -> None:
        self.data[key] = {"ts": time.time(), "w": w}
        self.budget -= 1
        self.used += 1
        self._dirty = True

    @property
    def exhausted(self) -> bool:
        return self.budget <= 0

    def save(self) -> None:
        if not self._dirty or self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            cut = time.time() - max(self.ttl_s * 4, 86400)
            self.data = {k: v for k, v in self.data.items() if float(v.get("ts", 0)) > cut}
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, self.path)
            self._dirty = False
        except OSError as exc:
            log.warning("Weather cache save failed: %s", exc)


def classify(code: int | None, temp_c: float | None, rain_mm: float | None, wind_kmh: float | None) -> tuple[str, list[str]]:
    """(severity, reasons) — 'normal' | 'notable' | 'severe'.  Conservative by design."""
    reasons: list[str] = []
    severe = False
    if wind_kmh is not None and wind_kmh >= SEVERE_WIND_KMH:
        reasons.append(f"strong wind {wind_kmh:.0f} km/h")
        severe = True
    if rain_mm is not None and rain_mm >= SEVERE_RAIN_MM_H:
        reasons.append(f"heavy rain {rain_mm:.1f} mm/h")
        severe = True
    if temp_c is not None and temp_c >= SEVERE_HEAT_C:
        reasons.append(f"extreme heat {temp_c:.0f}°C")
        severe = True
    if temp_c is not None and temp_c <= SEVERE_COLD_C:
        reasons.append(f"freezing conditions {temp_c:.0f}°C")
        severe = True
    if code in STORM_CODES:
        reasons.append("thunderstorm forecast")
        severe = True
    if code in SNOW_CODES:
        reasons.append("snow / freezing precipitation forecast")
        severe = True
    if severe:
        return "severe", reasons
    notable = []
    if rain_mm is not None and rain_mm >= 1.0:
        notable.append(f"rain {rain_mm:.1f} mm/h")
    if wind_kmh is not None and wind_kmh >= 30.0:
        notable.append(f"brisk wind {wind_kmh:.0f} km/h")
    return ("notable", notable) if notable else ("normal", [])


def facts_for(fx, now: datetime, venues: Venues | None, cache: "WeatherCache | None", horizon_h: float = 48.0) -> list[Fact]:
    """One weather fact for the fixture's venue, or an honest N/A.

    Called only inside the horizon, and only when the venue is known; forecasts are served from the persistent
    cache until their TTL expires, and the cache carries the per-run request budget."""
    if venues is None:
        return []
    ko = as_aware(fx["kickoff"] if isinstance(fx["kickoff"], datetime) else datetime.fromisoformat(str(fx["kickoff"])),
                  now)
    now = as_aware(now, ko) or now      # both sides of every comparison below live in the same zone
    if (ko - now) > timedelta(hours=float(horizon_h)):
        return []                     # forecasts this far out are noise — no request, no fact
    if (now - ko) > timedelta(hours=6):
        return []                     # match long over; historical weather is not research for the next run
    venue = str(fx.get("venue") or f"{fx.get('home')} stadium")
    v = venues.lookup(venue, now)
    if not v:
        return [make_fact("weather", venue, "N/A — venue could not be located, no weather is fetched",
                          OM_SOURCE, now, confidence="provider", kind="weather_unavailable", value={})]
    if cache is None:
        cache = WeatherCache(None)
    ko_utc = ko.astimezone(timezone.utc) if ko.tzinfo is not None else ko.replace(tzinfo=timezone.utc)
    key = f"{v['lat']:.2f},{v['lon']:.2f}@{ko_utc:%Y-%m-%dT%H}"
    w = cache.get(key)
    if w is None:
        if cache.exhausted:
            return [make_fact("weather", venue, "N/A — weather not fetched this run (per-run request budget)",
                              OM_SOURCE, now, confidence="provider", kind="weather_unavailable", value={})]
        w = _forecast(v, ko)
        if w is None:
            return [make_fact("weather", venue, "N/A — weather service unavailable for this fixture",
                              OM_SOURCE, now, confidence="provider", kind="weather_unavailable", value={})]
        cache.put(key, w)
    severity, reasons = classify(w.get("code"), w.get("temp"), w.get("rain"), w.get("wind"))
    text = (f"{w['temp']:.0f}°C, rain {w['rain']:.1f} mm/h, wind {w['wind']:.0f} km/h"
            + (f" — {'; '.join(reasons)}" if reasons else ""))
    if severity == "normal":
        text += " — normal conditions, no adjustment by rule"
    return [make_fact("weather", venue, text, OM_SOURCE, now, confidence="provider", kind="conditions",
                      value={"severity": severity, "temp_c": w.get("temp"), "rain_mm": w.get("rain"),
                             "wind_kmh": w.get("wind"), "code": w.get("code"), "reasons": reasons,
                             "lat": v["lat"], "lon": v["lon"]})]


def _forecast(v: dict, ko: datetime) -> dict | None:
    day = ko.date()
    params = {"latitude": v["lat"], "longitude": v["lon"],
              "hourly": "temperature_2m,precipitation,wind_speed_10m,weather_code",
              "start_date": str(day), "end_date": str(day), "timezone": "UTC"}
    try:
        r = requests.get(OM_URL, params=params, timeout=TIMEOUT)
        d = r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError) as exc:
        log.warning("Open-Meteo failed: %s", exc)
        return None
    h = (d or {}).get("hourly") or {}
    times = h.get("time") or []
    want = ko.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:00")
    idx = None
    for i, t in enumerate(times):
        if str(t).startswith(want[:13]):
            idx = i
            break
    if idx is None:
        idx = min(len(times) - 1, max(0, ko.hour)) if times else None
    if idx is None:
        return None

    def _at(name):
        vals = h.get(name) or []
        return float(vals[idx]) if idx < len(vals) and vals[idx] is not None else None

    return {"temp": _at("temperature_2m"), "rain": _at("precipitation"), "wind": _at("wind_speed_10m"),
            "code": int(_at("weather_code")) if _at("weather_code") is not None else None}
