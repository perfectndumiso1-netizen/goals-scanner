"""Facebook-only public copy. Does not alter Telegram, video cards, picks or delivery."""
import re


def reel_caption(original):
    text=str(original or '')
    picks=re.search(r'Today:\s*(\d+)\s+selection\(s\)',text)
    if picks:
        day=re.search(r'shortlist\s*[—–-]\s*([^\n.]+)\.',text)
        heading='Today’s football shortlist'+(f' · {day.group(1).strip()}' if day else '')
        count=int(picks.group(1));lines=[heading,'',f'{count} pick'+('s' if count!=1 else '')+' to look through before kick-off.']
        recap=re.search(r'Yesterday \(all videos\):\s*(\d+)/(\d+)\s+won',text)
        if recap:
            won,total=map(int,recap.groups())
            if 0<=won<=total:
                lines+=['',f'Yesterday’s settled video picks: {won} won, {total-won} lost.']
        lines+=['','18+ · No result is guaranteed.']
        return '\n'.join(lines)
    # Keep factual information for non-standard callers; remove boilerplate, not whole paragraphs.
    lines=[]
    for line in text.splitlines():
        if re.match(r'^\s*(?:source|sources|data source)\s*:',line,re.I):continue
        line=re.sub(r'\bplayreport(?:\s+za)?\b','',line,flags=re.I)
        line=re.sub(r'(?:Facebook Reel\s*[·|—-]?\s*)?9:16|16:9(?: widescreen)?','',line,flags=re.I)
        line=line.strip(' ·—|')
        if line:lines.append(line)
    return '\n'.join(lines) or 'Today’s football shortlist.\n\n18+ · No result is guaranteed.'
