"""Three owner-requested video windows, expressed once in SAST (UTC+2)."""
from zoneinfo import ZoneInfo

SAST = ZoneInfo('Africa/Johannesburg')
WINDOWS = (('morning', 5 * 60, 7 * 60 + 20),
           ('noon', 11 * 60, 12 * 60 + 20),
           ('evening', 16 * 60, 17 * 60 + 20))


def slot(now):
    now = now.astimezone(SAST) if now.tzinfo else now
    minute = now.hour * 60 + now.minute
    return next((name for name, start, end in WINDOWS if start <= minute < end), None)
