"""Reviewed real club-kit portraits, offline only. Never guess identities or fetch on publish."""
from datetime import date, datetime
import hashlib
import io
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from club_crests import normal, registry

ROOT = Path(__file__).resolve().parent / 'assets/player-photos'


def club_key(team, country):
    """Reuse exact country-qualified crest aliases, not fuzzy name matching."""
    entry = registry().get((normal(country), normal(team)))
    return (normal(country), normal(entry['name'])) if entry else None


def review_date(value=None):
    if value is None:
        return datetime.now(ZoneInfo('Africa/Johannesburg')).date()
    if isinstance(value, datetime):
        return value.astimezone(ZoneInfo('Africa/Johannesburg')).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    return review_date(datetime.fromisoformat(value.replace('Z', '+00:00')))


def read(team, country, *, on=None):
    """Return (portrait, player name), or None on missing/stale/unsafe artwork.

    Review windows bound club association, not copyright or starting-XI claims.
    Both today's date AND the fixture date must be in the review window: an old
    fixture cannot revive an expired portrait, nor can today's review cover a
    fixture beyond its validity. No provider/API request is ever made here.
    """
    key = club_key(team, country)
    if key is None:
        return None
    try:
        data = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
        if data['version'] != 1 or not isinstance(data['entries'], list) or len(data['entries']) > 512:
            return None
        matches = [e for e in data['entries'] if club_key(e['team'], e['country']) == key]
        if len(matches) != 1:
            return None  # Never choose arbitrarily among conflicting entries.
        entry = matches[0]
        if entry.get('club_kit_verified') is not True or entry.get('owner_requested_use') is not True:
            return None
        start, end = date.fromisoformat(entry['reviewed_on']), date.fromisoformat(entry['valid_through'])
        if not all(start <= day <= end for day in (review_date(), review_date(on))):
            return None
        if not isinstance(entry['player'], str) or not entry['player'].strip():
            return None
        if not re.fullmatch(r'[a-z0-9-]+\.png', entry['file']):
            return None
        path = ROOT / entry['file']
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            return None
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            return None
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != 'PNG' or not all(0 < v <= 1024 for v in image.size):
                return None
            image.load()
            return image.convert('RGBA'), entry['player']
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def paste(canvas, portrait, box):
    """Contain the whole reviewed crop in an isolated frame; never cover text.

    No face generation, jersey replacement, mirroring, stretch or auto face crop.
    RGB and RGBA canvases supported (video slides use RGB). Callers reserve box.
    """
    from PIL import Image, ImageDraw
    x0, y0, x1, y1 = map(round, box)
    if x1 <= x0 or y1 <= y0:
        raise ValueError('Player portrait needs a positive reserved box')
    frame = Image.new('RGBA', (x1 - x0, y1 - y0), (9, 25, 34, 255))
    photo = portrait[0].copy()
    photo.thumbnail(frame.size, Image.Resampling.LANCZOS)
    frame.alpha_composite(photo, ((frame.width - photo.width) // 2, (frame.height - photo.height) // 2))
    ImageDraw.Draw(frame).rectangle((0, 0, frame.width - 1, frame.height - 1), outline='#62756e', width=1)
    canvas.paste(frame, (x0, y0), frame)
