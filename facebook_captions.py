"""Facebook-only Reel caption requested by the Page owner; Telegram stays untouched."""
from datetime import datetime
from zoneinfo import ZoneInfo

# Relevant broad + subject-specific terms, not a claimed Facebook popularity ranking.
HASHTAGS=('#FootballPredictions','#Football','#Soccer','#SoccerPredictions','#FootballTips')


def reel_caption(original='', *, now=None):
    local=now or datetime.now(ZoneInfo('Africa/Johannesburg'))
    if local.tzinfo is not None:local=local.astimezone(ZoneInfo('Africa/Johannesburg'))
    return "Today's Football Predictions\n"+local.strftime('%d %B %Y')+'\n\n'+' '.join(HASHTAGS)
