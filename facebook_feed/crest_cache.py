"""Optional public provider crests. No API keys, arbitrary URLs, or invented badges.

Caches are local, bounded and disposable; they are never publication-state evidence.
The renderer itself never downloads anything.
"""
from datetime import datetime,timezone
import io
from pathlib import Path
from time import time
from urllib.request import Request,build_opener
from facebook_post import _NoRedirect

MAX_BYTES=512*1024
MAX_DIMENSION=1024
MAX_CACHE_FILES=512
TTL=30*86400
NEGATIVE_TTL=6*3600


def decode(raw):
    from PIL import Image
    if len(raw)>MAX_BYTES:raise ValueError('Crest file too large')
    with Image.open(io.BytesIO(raw)) as image:
        if image.format!='PNG' or not all(0<n<=MAX_DIMENSION for n in image.size):raise ValueError('Invalid crest shape/format')
        image.load()
        return image.convert('RGBA')


def read_crest(path):
    if not path:return None
    try:
        path=Path(path)
        if path.is_symlink() or path.stat().st_size>MAX_BYTES:return None
        return decode(path.read_bytes())
    except Exception:return None  # Missing/invalid artwork must not fabricate a replacement.


def trim(directory):
    files=[p for p in directory.iterdir() if p.suffix in ('.png','.missing') and p.stem.isdigit() and not p.is_symlink()]
    for old in sorted(files,key=lambda p:p.stat().st_mtime)[:-MAX_CACHE_FILES]:old.unlink(missing_ok=True)


def fetch_crest(team_id,directory,opener=None,now=None):
    if type(team_id) is not int or not 1<=team_id<=2147483647:return None
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    stamp=time() if now is None else now
    path=directory/f'{team_id}.png';negative=directory/f'{team_id}.missing'
    if path.is_file() and not path.is_symlink() and 0<=stamp-path.stat().st_mtime<TTL and read_crest(path) is not None:return str(path)
    if negative.is_file() and 0<=stamp-negative.stat().st_mtime<NEGATIVE_TTL:return None
    # A public, fixed provider CDN path derived only from a validated team ID.
    # Never forward the football API key, Page token, or caller-provided URLs.
    request=Request(f'https://media.api-sports.io/football/teams/{team_id}.png',headers={'Accept':'image/png'})
    try:
        with (opener or build_opener(_NoRedirect())).open(request,timeout=4) as response:
            raw=response.read(MAX_BYTES+1)
        decode(raw)
        temporary=directory/f'{team_id}.tmp';temporary.unlink(missing_ok=True);temporary.write_bytes(raw);temporary.replace(path)
        negative.unlink(missing_ok=True)
        # Bound growth on persistent/local runners; no ledger or external path is deleted.
        trim(directory)
        return str(path)
    except Exception:
        try:
            if negative.is_symlink():negative.unlink()
            negative.write_text(datetime.now(timezone.utc).date().isoformat(),encoding='utf-8')
            trim(directory)
        except OSError:pass
        return None


def prepare(spec,directory):
    """Fetch at most the two selected match's actual team-ID crests before rendering."""
    match=spec['match'];crests={}
    for side in ('home','away'):
        try:result=fetch_crest(match.get(side+'_team_id'),directory)
        except Exception:result=None  # Optional artwork failures cannot make the score fake/stale.
        if result:crests[side]=result
    spec['crests']=crests
    return spec
