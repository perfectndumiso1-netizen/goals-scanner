"""
Book configuration and metadata for African Wildlife and Nature: A Safari Colouring Adventure
"""
BOOK_TITLE = "African Wildlife and Nature"
BOOK_SUBTITLE = "A Safari Colouring Adventure"
BOOK_FULL_TITLE = "African Wildlife and Nature: A Safari Colouring Adventure"

AUTHOR = "Safari Wonders Press"
PUBLISHER = "Safari Wonders Press"
EDITION = "First Edition, 2025"
LANGUAGE = "en-US"

# Trim and print specs
TRIM_WIDTH_IN = 8.5
TRIM_HEIGHT_IN = 11.0
DPI = 300
TRIM_WIDTH_PX = int(TRIM_WIDTH_IN * DPI)   # 2550
TRIM_HEIGHT_PX = int(TRIM_HEIGHT_IN * DPI) # 3300

# Margins in inches (KDP safe zone)
MARGIN_TOP = 0.5
MARGIN_BOTTOM = 0.5
MARGIN_OUTSIDE = 0.5
MARGIN_INSIDE = 0.75  # gutter
SAFE_TOP_PX = int(MARGIN_TOP * DPI)
SAFE_BOTTOM_PX = int(MARGIN_BOTTOM * DPI)
SAFE_LEFT_PX = int(MARGIN_OUTSIDE * DPI)
SAFE_RIGHT_PX = int(MARGIN_OUTSIDE * DPI)

# Cover specs
PAGE_COUNT = 64  # target
PAPER_WHITE_THICKNESS = 0.002252
SPINE_WIDTH_IN = PAGE_COUNT * PAPER_WHITE_THICKNESS  # 0.144128
BLEED_IN = 0.125
COVER_WIDTH_IN = (TRIM_WIDTH_IN * 2) + SPINE_WIDTH_IN + (BLEED_IN * 2)
COVER_HEIGHT_IN = TRIM_HEIGHT_IN + (BLEED_IN * 2)
COVER_WIDTH_PX = int(COVER_WIDTH_IN * DPI)
COVER_HEIGHT_PX = int(COVER_HEIGHT_IN * DPI)

# Illustration specs
ILLUSTRATION_DPI = 300
# Usable area after margins
USABLE_WIDTH_PX = TRIM_WIDTH_PX - int((MARGIN_OUTSIDE + MARGIN_INSIDE) * DPI)
USABLE_HEIGHT_PX = TRIM_HEIGHT_PX - int((MARGIN_TOP + MARGIN_BOTTOM) * DPI)

# Age range
AGE_RANGE = "5-10"
CATEGORIES = ["Animals", "Nature", "African Wildlife"]

print(f"Book: {BOOK_FULL_TITLE}")
print(f"Trim: {TRIM_WIDTH_IN}x{TRIM_HEIGHT_IN} {DPI}DPI = {TRIM_WIDTH_PX}x{TRIM_HEIGHT_PX}px")
print(f"Spine: {SPINE_WIDTH_IN:.4f}in for {PAGE_COUNT} pages (white paper)")
print(f"Cover: {COVER_WIDTH_IN:.3f} x {COVER_HEIGHT_IN:.3f} in = {COVER_WIDTH_PX} x {COVER_HEIGHT_PX} px")
print(f"Usable: {USABLE_WIDTH_PX} x {USABLE_HEIGHT_PX} px")
