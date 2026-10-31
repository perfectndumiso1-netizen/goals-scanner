"""Offline, country-qualified club crest registry. No API/provider ID guessing.

Only pinned, hash-verified local PNGs are read. Unknown identities omit artwork;
never substitute another crest, an app logo, a flag or an invented badge.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT=Path(__file__).resolve().parent/'assets/club-crests'


def normal(value):
    if not isinstance(value,str):return ''
    return ''.join(c for c in unicodedata.normalize('NFKD',value).casefold() if c.isalnum())


@lru_cache(maxsize=1)
def registry():
    try:
        data=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
        if data['version']!=1 or len(data['entries'])>512:return {}
        index={}
        for entry in data['entries']:
            country=normal(entry['country'])
            for alias in entry['aliases']:
                key=country,normal(alias)
                if key in index and (index[key] is None or index[key]['file']!=entry['file']):
                    index[key]=None  # Ambiguous aliases cannot select a badge.
                elif key not in index:index[key]=entry
        return index
    except (OSError,ValueError,KeyError,TypeError):return {}


def read(name,country):
    if not normal(name) or not normal(country):return None
    entry=registry().get((normal(country),normal(name)))
    if not entry:return None
    try:
        if not re.fullmatch(r'[a-z0-9-]+\.png',entry['file']):return None
        path=ROOT/entry['file']
        if path.is_symlink() or not path.is_file() or path.stat().st_size>512*1024:return None
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:return None
        from PIL import Image
        import io
        with Image.open(io.BytesIO(raw)) as image:
            if image.format!='PNG' or not all(0<v<=1024 for v in image.size):return None
            image.load();return image.convert('RGBA')
    except (OSError,ValueError,KeyError,TypeError):return None


def paste(canvas,name,country,center,size):
    image=read(name,country)
    if image is None:return False
    box=image.getbbox()
    if box:image=image.crop(box)
    from PIL import Image
    image.thumbnail((size,size),Image.Resampling.LANCZOS)
    canvas.alpha_composite(image,(round(center[0]-image.width/2),round(center[1]-image.height/2)))
    return True
