"""Free-licence stadium photography for match videos (Wikidata -> Wikimedia Commons category).

Why this exists: stock/press photos (Getty etc.) are copyrighted and put monetised videos at risk of
claims. Wikimedia Commons hosts photos under CC BY / CC BY-SA / CC0 / public domain, which are safe
to use when the author is credited. Every photo returned here carries a ready-made credit line.

Accuracy first: a club is resolved to its home ground through Wikidata (club -> "home venue"), and
photos are taken ONLY from that ground's own Commons category / lead image. Keyword search is never
used, so we cannot end up with a different stadium or a footballer who shares the name.
When nothing suitable is found the caller falls back to the generic stadium background.
"""
from __future__ import annotations

import html
import json
import logging
import re
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger("scanner")

UA = "PlayReport/2.0 (https://github.com/perfectndumiso1-netizen/goals-scanner; match videos)"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
MIN_WIDTH = 1100
THUMB_WIDTH = 1920
TIMEOUT = 20

# Free licences only. Non-free / fair-use files live on en.wikipedia, not Commons, so they never match.
_FREE_LICENSE = re.compile(
    r"^(?:cc[\s-]*by(?:[\s-]*sa)?(?:[\s-]*\d(?:\.\d)?)?(?:[\s-]+[a-z]{2,3})?|cc0(?:[\s-]*1\.0)?(?:\s+universal)?|public domain.*|pd\b.*)\s*$",
    re.I)
# Commercial use + cropping/blurring must be allowed, so NonCommercial and NoDerivatives are out.
_RESTRICTED = re.compile(r"(?:^|[\s-])(?:nc|nd)(?:[\s-]|$)", re.I)


def _is_free_license(lic: str) -> bool:
    return bool(lic) and bool(_FREE_LICENSE.search(lic.strip())) and not _RESTRICTED.search(lic)
_SENSITIVE_TITLE = re.compile(
    r"national[ _]guard|protest|\briot|police|militar|soldier|\barmy\b|armou?red|swat\b|curfew|unrest|demonstrat|funeral|memorial|"
    r"vigil|shooting|attack|bomb|crash|accident|flood|wildfire|covid|vaccin|quarantine|lockdown|evacuat|refugee|ambulance", re.I)
_BAD_TITLE = re.compile(
    r"logo|crest|badge|emblem|flag|coat[ _]of|\bmap\b|plan\b|seating|diagram|ticket|poster|\bkit\b|shirt|"
    r"scarf|signature|banner|pictogram|icon|march|queue|\bbus\b|train|tram|station|\bsign\b|"
    r"reception|band\b|portrait|player|training|interview|trophy|statue|plaque|museum|shop|store|"
    r"stage|concert|speech|rally|festival|party|radio|ffh|public viewing|fan ?(?:zone|fest|march)|press|conference|mayor|"
    r"minister|president|ceremony|auswärtsfahrt|fahrt|\btrip\b|bahnhof|hbf|"
    r"circuit|bugatti|24h|maquette|model|chantier|construction|luftaufnahme|anefo|nl-hana|archiv|"
    r"\b(19[0-9]{2})\b|voetbal-\d|team \w+ \w+ voetbal",
    re.I,
)
# Livescore-style names -> the name Wikidata knows the club by (only where they differ materially).
CLUB_ALIASES: dict[str, str] = {
    "deportivo a coruna": "Deportivo de La Coruña",
    "fc cologne": "1. FC Köln",
    "sc heerenveen": "SC Heerenveen",
    "excelsior": "SBV Excelsior",
    "wolves": "Wolverhampton Wanderers F.C.",
    "corum fk": "Çorum FK",
    "rizespor": "Çaykur Rizespor",
}


DISPLAY_NAMES: dict[str, str] = {
    "waldstadion": "Deutsche Bank Park",
    "estadio municipal de abanca riazor": "Estadio Abanca-Riazor",
    "benito stirpe stadium": "Stadio Benito Stirpe",
    "stade marie marvingt": "Stade Marie-Marvingt",
    "mapei stadium citta del tricolore": "Mapei Stadium",
    "rheinenergie stadion": "RheinEnergieStadion",
    "stadium municipal": "Stadium de Toulouse",
    "molineux stadium": "Molineux Stadium",
}


def display_name(label: str) -> str:
    """Presentable stadium name for on-screen captions."""
    key = _norm(label)
    if key in DISPLAY_NAMES:
        return DISPLAY_NAMES[key]
    label = str(label or "").strip()
    return label[:1].upper() + label[1:]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def _get_json(url: str, params: dict) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", str(s or ""))
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _claim_value(claims: dict, prop: str):
    for c in claims.get(prop) or []:
        quals = c.get("qualifiers") or {}
        if quals.get("P582"):  # has an end date -> a former ground
            continue
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if v:
            return v
    return None


def venue_info(team: str) -> dict | None:
    """{'name', 'qid', 'category', 'image'} for the club's current home ground, via Wikidata."""
    q = CLUB_ALIASES.get(_norm(team), team)
    try:
        found = _get_json(WIKIDATA_API, {
            "action": "wbsearchentities", "format": "json", "language": "en", "type": "item",
            "limit": 8, "search": q,
        })
        wanted = ("football club", "soccer club", "football team", "association football", "men's team", "sports club")
        unwanted = ("women", "reserve", "youth", "u19", "u21", "rugby", "handball", "basketball", "game in", "european football")
        venue_id = None
        for e in found.get("search") or []:
            desc = str(e.get("description") or "").lower()
            if not any(w in desc for w in wanted) or any(w in desc for w in unwanted):
                continue
            ent = _get_json(WIKIDATA_API, {"action": "wbgetentities", "format": "json", "ids": e["id"], "props": "claims"})
            claims = ((ent.get("entities") or {}).get(e["id"]) or {}).get("claims") or {}
            venue = _claim_value(claims, "P115")
            if isinstance(venue, dict) and venue.get("id"):
                venue_id = venue["id"]
                break
        if not venue_id:
            return None
        v = _get_json(WIKIDATA_API, {"action": "wbgetentities", "format": "json", "ids": venue_id,
                                     "props": "labels|claims", "languages": "en"})
        ve = (v.get("entities") or {}).get(venue_id) or {}
        vclaims = ve.get("claims") or {}
        cat = _claim_value(vclaims, "P373")
        img = _claim_value(vclaims, "P18")
        return {
            "name": ((ve.get("labels") or {}).get("en") or {}).get("value") or "",
            "qid": venue_id,
            "category": cat if isinstance(cat, str) else None,
            "image": img if isinstance(img, str) else None,
        }
    except Exception as exc:  # noqa: BLE001
        log.info("venue lookup failed for %s: %s", team, exc)
        return None


def _candidate_from_page(page: dict, *, lead: bool = False) -> dict | None:
    infos = page.get("imageinfo") or []
    if not infos:
        return None
    ii = infos[0]
    meta = ii.get("extmetadata") or {}
    lic = _strip_html((meta.get("LicenseShortName") or {}).get("value", ""))
    if not _is_free_license(lic):
        return None
    if str((meta.get("NonFree") or {}).get("value", "")).lower() in ("1", "true", "yes"):
        return None
    if str(ii.get("mime") or "") not in ("image/jpeg", "image/png"):
        return None
    w, h = int(ii.get("width") or 0), int(ii.get("height") or 0)
    if w < MIN_WIDTH or h <= 0 or not (1.25 <= w / h <= 2.4):
        return None
    title = str(page.get("title") or "")
    if _SENSITIVE_TITLE.search(title):
        return None
    if not lead and _BAD_TITLE.search(title):
        return None
    artist = _strip_html((meta.get("Artist") or {}).get("value", "")) or _strip_html((meta.get("Credit") or {}).get("value", ""))
    artist = re.sub(r"^(Own work|Photo by|Photograph by|Author:?)\s*,?\s*", "", artist, flags=re.I)
    artist = re.split(r"\s+(?:from|at|via)\s+", artist)[0].strip() or artist
    if len(artist) > 34:
        artist = artist[:33].rstrip() + "…"
    return {
        "title": title,
        "url": ii.get("thumburl") or ii.get("url"),
        "width": w, "height": h,
        "license": lic,
        "artist": artist or "Wikimedia Commons contributor",
        "page": ii.get("descriptionurl") or "",
        "lead": lead,
    }


_IMGINFO = {"prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": THUMB_WIDTH}


def _lead_candidate(filename: str) -> dict | None:
    data = _get_json(COMMONS_API, {"action": "query", "format": "json", "titles": f"File:{filename}", **_IMGINFO})
    for p in ((data.get("query") or {}).get("pages") or {}).values():
        c = _candidate_from_page(p, lead=True)
        if c:
            return c
    return None


def _category_candidates(category: str, limit: int = 60) -> list[dict]:
    data = _get_json(COMMONS_API, {
        "action": "query", "format": "json", "generator": "categorymembers",
        "gcmtitle": f"Category:{category}", "gcmtype": "file", "gcmlimit": limit, **_IMGINFO,
    })
    out = []
    for p in ((data.get("query") or {}).get("pages") or {}).values():
        c = _candidate_from_page(p)
        if c:
            out.append(c)
    return out


def _is_monochrome(path: Path) -> bool:
    """True for black-and-white / archival scans (mean colour saturation almost zero)."""
    try:
        from PIL import Image, ImageStat
        im = Image.open(path).convert("RGB")
        im.thumbnail((160, 160))
        return ImageStat.Stat(im.convert("HSV")).mean[1] < 18  # 0-255 scale
    except Exception:  # noqa: BLE001
        return False


def _pitch_share(path: Path) -> float:
    """Share of grass-green pixels. A photo that shows the pitch scores well; sky, a floodlight mast or a facade does not."""
    try:
        import numpy as np
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.thumbnail((200, 200))
        hsv = np.asarray(im.convert("HSV"), dtype=np.float32)
        hue, sat, val = hsv[..., 0] * 360.0 / 255.0, hsv[..., 1] / 255.0, hsv[..., 2] / 255.0
        return float(((hue > 70) & (hue < 160) & (sat > 0.25) & (val > 0.20)).mean())
    except Exception:  # noqa: BLE001
        return 0.0


PITCH_MIN = 0.06           # below this a photo is probably not showing the ground at all


def pitch_centering(im, target_w: int, target_h: int) -> tuple[float, float]:
    """Centering for ImageOps.fit that keeps the pitch in frame.

    Only matters when the picture must be cropped vertically (a wide card cut from a tall photo) and the centred crop
    would show little pitch (mostly sky): then the window slides to where the grass is. Otherwise the default centre."""
    try:
        import numpy as np
        w, h = im.size
        win_h = w * target_h / max(1, target_w)
        if w <= 0 or h <= 0 or win_h >= h - 1:
            return (0.5, 0.5)
        small = im.convert("RGB")
        small.thumbnail((240, 240))
        sw, sh = small.size
        hsv = np.asarray(small.convert("HSV"), dtype=np.float32)
        hue, sat, val = hsv[..., 0] * 360.0 / 255.0, hsv[..., 1] / 255.0, hsv[..., 2] / 255.0
        rows = ((hue > 70) & (hue < 160) & (sat > 0.25) & (val > 0.20)).astype(np.float32).mean(axis=1)
        win = max(1, int(round(win_h * sh / h)))
        cum = np.concatenate([[0.0], np.cumsum(rows)])
        centre_top = (sh - win) // 2
        if (cum[centre_top + win] - cum[centre_top]) / win >= 0.12:
            return (0.5, 0.5)                                    # the usual crop already shows plenty of pitch
        best, best_top = -1.0, centre_top
        for top in range(0, sh - win + 1):
            score = (cum[top + win] - cum[top]) / win - 0.05 * abs((top + win / 2) / sh - 0.5)
            if score > best:
                best, best_top = score, top
        return (0.5, best_top / max(1, sh - win))
    except Exception:  # noqa: BLE001
        return (0.5, 0.5)


def credit_line(c: dict) -> str:
    """Short on-screen / caption credit, e.g. 'Photo: Jane Doe / CC BY-SA 4.0 / Wikimedia Commons'."""
    return f"Photo: {c.get('artist')} / {c.get('license')} / Wikimedia Commons"


def _download(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read()
        if len(raw) < 20_000:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        return True
    except Exception as exc:  # noqa: BLE001
        log.info("photo download failed %s: %s", str(url)[:80], exc)
        return False


def venue_photos(team: str, dest_dir: Path, n: int = 3) -> list[dict]:
    """Up to `n` distinct free-licence photos of `team`'s ground, downloaded into `dest_dir`.

    Returns [{'path': Path, 'credit': str, 'title': str, 'stadium': str}, ...] (possibly empty).
    """
    dest_dir = Path(dest_dir)
    info = venue_info(team)
    if not info:
        return []
    cands: list[dict] = []
    try:
        if info.get("image"):
            lead = _lead_candidate(info["image"])
            if lead:
                cands.append(lead)
    except Exception as exc:  # noqa: BLE001
        log.info("lead photo lookup failed for %s: %s", team, exc)
    try:
        if info.get("category"):
            rest = _category_candidates(info["category"])
            seen = {c["title"] for c in cands}
            # biggest first: they crop best to both 1920x1080 and 1080x1920
            rest.sort(key=lambda c: -(c["width"] * c["height"]))
            cands.extend(c for c in rest if c["title"] not in seen)
    except Exception as exc:  # noqa: BLE001
        log.info("category photo lookup failed for %s: %s", team, exc)
    # Try a few more candidates than we need and prefer the ones that actually show the pitch (first in the original
    # order, so the curated lead image still wins when it is a good picture of the ground).
    kept: list[tuple[int, float, dict, Path]] = []
    slug = _norm(team).replace(" ", "_") or "venue"
    for i, c in enumerate(cands[: max(n * 4, 8)]):
        dest = dest_dir / f"{slug}_c{i + 1}.jpg"
        if not _download(c["url"], dest):
            continue
        if _is_monochrome(dest):
            dest.unlink(missing_ok=True)
            continue
        share = _pitch_share(dest)
        kept.append((i, share, c, dest))
        if len([k for k in kept if k[1] >= PITCH_MIN]) >= n:
            break
    kept.sort(key=lambda k: (k[1] < PITCH_MIN, k[0]))
    if any(k[1] >= PITCH_MIN for k in kept):
        for k in [k for k in kept if k[1] < PITCH_MIN]:
            k[3].unlink(missing_ok=True)
        kept = [k for k in kept if k[1] >= PITCH_MIN]
    out: list[dict] = []
    for _, _share, c, tmp in kept:
        if len(out) < n:
            dest = dest_dir / f"{slug}_{len(out) + 1}.jpg"
            if tmp != dest:
                tmp.replace(dest)
            out.append({"path": dest, "credit": credit_line(c), "title": c["title"], "stadium": display_name(info.get("name") or "")})
        else:
            tmp.unlink(missing_ok=True)
    return out


def photos_by_title(titles: list[str], dest_dir: Path, team: str | None = None, stadium: str | None = None) -> list[dict]:
    """Download specific, hand-vetted Commons files (titles with or without the 'File:' prefix).

    Same licence/size checks as automatic discovery. Returns the same dict shape as venue_photos().
    """
    dest_dir = Path(dest_dir)
    name = stadium
    if not name and team:
        info = venue_info(team)
        name = (info or {}).get("name") or ""
    out: list[dict] = []
    slug = _norm(team or "venue").replace(" ", "_") or "venue"
    for t in titles:
        fn = re.sub(r"^(File|Image):", "", str(t), flags=re.I).strip()
        try:
            c = _lead_candidate(fn)
        except Exception as exc:  # noqa: BLE001
            log.info("photo lookup failed for %s: %s", fn, exc)
            continue
        if not c:
            continue
        dest = dest_dir / f"{slug}_{len(out) + 1}.jpg"
        if _download(c["url"], dest) and not _is_monochrome(dest):
            out.append({"path": dest, "credit": credit_line(c), "title": c["title"], "stadium": display_name(name or "")})
    return out
