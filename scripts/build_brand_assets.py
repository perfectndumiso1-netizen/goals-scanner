"""Reproduce the selected Mr 2 Odds logo exports; never alters the original profile photos.

Run from the repository root: python scripts/build_brand_assets.py
The full-colour source was selected by the owner, using their bundled profile portrait.
"""
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets/branding/mr-2-odds-logo.png'
MAIN = ROOT / 'android/app/src/main'


def artwork():
    """Preserve the complete chosen badge, removing only its outer square backdrop."""
    logo = Image.open(SOURCE).convert('RGBA')
    # The selected master has an oval ring within a square canvas. Keep its full
    # original placement/padding, with a small safety margin around the outer ring.
    mask = Image.new('L', logo.size, 0)
    w, h = logo.size
    ImageDraw.Draw(mask).ellipse((round(w*.142), round(h*.142), round(w*.859), round(h*.882)), fill=255)
    logo.putalpha(mask)
    return logo


def build():
    logo = artwork()
    if logo.width != logo.height:
        raise ValueError('Selected brand master must be square')
    exported = logo.resize((512, 512), Image.Resampling.LANCZOS)
    for path in (ROOT/'assets/reel/logo.png', MAIN/'assets/www/logo.png', MAIN/'res/drawable-nodpi/splash_logo.png'):
        path.parent.mkdir(parents=True, exist_ok=True)
        exported.save(path, optimize=True)
    for density, scale in (('mdpi', 1), ('hdpi', 1.5), ('xhdpi', 2), ('xxhdpi', 3), ('xxxhdpi', 4)):
        folder = MAIN/'res'/f'mipmap-{density}'
        folder.mkdir(parents=True, exist_ok=True)
        # Adaptive foreground is 108dp. The badge occupies ~71% of the master;
        # 92dp art therefore puts the complete badge inside the central 66dp safe zone.
        side = round(108*scale); art_side = round(92*scale)
        foreground = Image.new('RGBA', (side, side), (0, 0, 0, 0))
        art = logo.resize((art_side, art_side), Image.Resampling.LANCZOS)
        foreground.alpha_composite(art, ((side-art_side)//2, (side-art_side)//2))
        foreground.save(folder/'ic_launcher_foreground.png', optimize=True)
        logo.resize((round(48*scale), round(48*scale)), Image.Resampling.LANCZOS).save(folder/'ic_launcher.png', optimize=True)
    # Android 13 themed icons are monochrome by definition. Derive the face/badge
    # luminance mask from the same artwork, rather than retaining the old PR glyph.
    art = logo.resize((368, 368), Image.Resampling.LANCZOS)
    alpha = ImageOps.grayscale(art).point(lambda value: max(0, min(255, (value-35)*3)))
    mono = Image.new('RGBA', (432, 432), (255, 255, 255, 0))
    white = Image.new('RGBA', art.size, (255, 255, 255, 0)); white.putalpha(alpha)
    mono.alpha_composite(white, (32, 32))
    mono.save(MAIN/'res/drawable-nodpi/ic_launcher_monochrome.png', optimize=True)


if __name__ == '__main__':
    build()
