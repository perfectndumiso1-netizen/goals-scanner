"""Recent actual league meetings; no simulated scores or implied home advantage."""
from pathlib import Path
from football_artwork import background, text, GOLD, MUTED
from club_crests import paste
from .content import local


def render(spec, path):
    rows = spec['meetings']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5:
        raise ValueError('H2H requires one to five verified meetings')
    seen = set(); previous = None
    names = {spec['home_id']: spec['home'], spec['away_id']: spec['away']}
    if len(names) != 2:
        raise ValueError('H2H teams must differ')
    for row in rows:
        if type(row.get('id')) is not int or row['id'] <= 0 or row['id'] in seen:
            raise ValueError('Duplicate/unverified H2H match')
        seen.add(row['id'])
        if {row.get('home_id'), row.get('away_id')} != set(names):
            raise ValueError('H2H identity mismatch')
        if row['home'] != names[row['home_id']] or row['away'] != names[row['away_id']]:
            raise ValueError('H2H name mismatch')
        score = row.get('score')
        if not isinstance(score, (list, tuple)) or len(score) != 2 or any(type(v) is not int or not 0 <= v <= 99 for v in score):
            raise ValueError('Unverified H2H score')
        stamp = local(row['date'])
        if stamp >= min(local(spec['checked_at']), local(spec['kickoff'])) or previous and stamp > previous:
            raise ValueError('H2H must be completed and newest first')
        previous = stamp
    image, draw = background(1350)
    from football_artwork import brand
    brand(image, draw)
    text(draw, 'RECENT HEAD-TO-HEAD', 540, 139, 46, True)
    for side, cx in (('home', 275), ('away', 805)):
        paste(image, spec[side], spec.get('country'), (cx, 277), 112)
        text(draw, spec[side].upper(), cx, 365, 32, True, width=430)
    text(draw, 'VS', 540, 266, 32, True, fill=GOLD)
    text(draw, spec['league'], 540, 420, 26, True)
    text(draw, f"{len(rows)} RECENT LEAGUE MEETING{'S' if len(rows) != 1 else ''}", 540, 477, 26, True, fill=GOLD)
    for index, row in enumerate(rows):
        top = 540 + index*119
        draw.rounded_rectangle((64, top, 1016, top+105), radius=16, fill=(6,20,29,245), outline=(75,99,101,255))
        text(draw, local(row['date']).strftime('%d %b %Y'), 540, top+11, 22, fill=MUTED)
        text(draw, row['home'], 280, top+54, 26, True, width=350)
        text(draw, f"{row['score'][0]}–{row['score'][1]}", 540, top+50, 34, True, fill=GOLD, width=130)
        text(draw, row['away'], 800, top+54, 26, True, width=350)
    text(draw, 'Newest first · actual home team on the left', 540, 1180, 23, fill=MUTED)
    text(draw, 'League seasons '+ ' / '.join(map(str, spec['seasons']))+' · last 730 days', 540, 1225, 22, fill=MUTED)
    text(draw, local(spec['kickoff']).strftime('Next meeting: %d %b %Y · %H:%M SAST'), 540, 1270, 22, fill=MUTED)
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    image.convert('RGB').save(path, quality=95)
    return path
