"""Owner-authorised, date-bound ONE photo, plus cover-only repair of a known Reel.

Not imported by normal feed scheduling. Reservation checkpoint must precede send.
"""
from datetime import datetime
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import Request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import facebook_post as fb
from facebook_cover import match_rows,render_matches,apply_preferred
from facebook_feed.content import verified_fixtures,SAST,local
from facebook_feed.graphics import render
from facebook_feed.publisher import PageFeed
from facebook_feed.storage import restore,write

WORK=Path('tmp/facebook-one-match-test')
SOURCE=Path('tmp/facebook-one-test-source/data')
REQUEST=Path('config/facebook-one-match-test.json')


def validate(request,now):
    expiry=local(request['expires_at'])
    if request['date']!=now.date().isoformat() or expiry.date()!=now.date() or not now<expiry:
        raise ValueError('One-picture authorisation expired; no post or cover mutation')


def build(item,now,image):
    f=item['fixture'];h=item['home'];a=item['away']
    title=f"{f['home']} vs {f['away']}"
    kickoff=local(f['kickoff']).strftime('%d %B %Y · %H:%M SAST')
    caption=f"{title} — match stats.\n{kickoff}\n\nFive available competitive results per team; sample windows differ. Historical results are not a forecast."
    spec=dict(header='FOOTBALL · MATCH STATS',title='MATCH STATS',subtitle=title,
              context=kickoff+'\n5 available competitive results per team',rows=[
                  f"Goals scored: {h['scored']} | {a['scored']}",
                  f"Goals conceded: {h['conceded']} | {a['conceded']}",
                  f"Scored in: {h['scored_in']}/5 | {a['scored_in']}/5",
                  f"Wins: {h['wins']}/5 | {a['wins']}/5",
                  f"Form, newest first: {h['form']} | {a['form']}"],
              notes=[f"Left: {f['home']} · Right: {f['away']}",
                     f"{f['home']}: {h['start']} to {h['end']}",
                     f"{f['away']}: {a['start']} to {a['end']}"],
              question='Recent results, not a prediction.',
              footer='Five available results per team | Sample windows differ')
    render(spec,image)
    return dict(caption=caption,image=str(image),caption_hash=hashlib.sha256(caption.encode()).hexdigest(),image_hash=fb._digest(image))


def prepare_cover(request):
    cover=request['cover']
    info=json.loads((SOURCE/'facebook-retries'/cover['receipt']).read_text())
    history=json.loads((SOURCE/'app/telegram_state.json').read_text())
    recorded=history['briefing_history'][request['date']]
    # This edition contained five picks and rendering requires at least five.
    # Fail closed if the history has since been merged with a different edition.
    if len(recorded)!=5 or match_rows(recorded)!=cover['matches']:
        raise ValueError('Exact filmed-match history is no longer unambiguous')
    if info.get('kind')!=fb.KIND or str(info.get('video_id'))!=cover['video_id'] or info.get('sha256')!=cover['sha256']:
        raise ValueError('Known Reel receipt identity does not match; no video upload supported here')
    path=WORK/'known-reel.cover.jpg'
    render_matches(recorded,path,now=datetime.now(SAST))
    return dict(path=str(path),video_id=cover['video_id'],page_id=info['page_id'])


def outputs(prefix,send):
    target=os.environ.get('GITHUB_OUTPUT')
    if target:
        with open(target,'a') as stream:stream.write(f'prefix={prefix}\nshould_publish={str(send).lower()}\n')


def prepare():
    if os.environ.get('GITHUB_REF_NAME')!='main':raise ValueError('One-photo test must use main; no branch-specific duplicate ledgers')
    now=datetime.now(SAST);request=json.loads(REQUEST.read_text());validate(request,now)
    WORK.mkdir(parents=True,exist_ok=True)
    prefix='mr2-one-photo-'+hashlib.sha256((os.environ['GITHUB_REPOSITORY']+':'+os.environ['GITHUB_REF_NAME']).encode()).hexdigest()[:16]+'-'
    state=restore(os.environ['GITHUB_REPOSITORY'],os.environ['GITHUB_REF_NAME'],os.environ['GITHUB_REPOSITORY_ID'],prefix,os.environ['GH_READ_TOKEN'],WORK/'restore')
    state=state or dict(schema=1,namespace=prefix,posts=[])
    checkpoint=WORK/'checkpoint/state.json'
    if state['posts']:
        # Unknown outcomes remain reserved: never blindly repost after a rerun.
        write(checkpoint,state);outputs(prefix,False)
        print('::notice::One-photo test already reserved/attempted. No second photo or Reel will be sent.')
        return
    config=json.loads(Path('config/facebook-feed.json').read_text())
    eligible=[i for i in verified_fixtures(SOURCE/'app',now,config) if i['fixture']['id']==request['fixture_id'] and i['fixture']['country']!='Australia']
    if len(eligible)!=1:raise ValueError('Exact match lacks fresh verified results; nothing posted')
    post=build(eligible[0],now,WORK/'match-stats.jpg')
    write(WORK/'evidence.json',eligible[0]);(WORK/'caption.txt').write_text(post['caption'])
    try:cover=prepare_cover(request)
    except Exception:
        cover=None
        print('::warning::Existing Reel cover history could not be verified; no video upload or guessed cover. Photo test remains separate.')
    row=dict(request_id=request['request_id'],status='reserved',caption_hash=post['caption_hash'],image_hash=post['image_hash'])
    state['posts'].append(row)
    if cover:state['cover_status']='reserved'
    write(checkpoint,state);write(WORK/'plan.json',dict(request=request,post=post,cover=cover))
    outputs(prefix,True)


def send():
    plan=json.loads((WORK/'plan.json').read_text());validate(plan['request'],datetime.now(SAST))
    checkpoint=WORK/'checkpoint/state.json';state=json.loads(checkpoint.read_text());row=state['posts'][0];post=plan['post']
    if row['status']!='reserved' or row['caption_hash']!=hashlib.sha256(post['caption'].encode()).hexdigest() or row['image_hash']!=fb._digest(Path(post['image'])):
        raise ValueError('Reservation/media mismatch; publishing blocked')
    page=PageFeed()
    # Persist known identity immediately, before read-back, so verification failures never cause a repost.
    try:
        identity=page.send(post);row.update(status='known_id',post_id=identity);write(checkpoint,state)
        for attempt in range(3):
            try:page.verify(identity,post['caption']);row['status']='verified';break
            except Exception:
                if attempt==2:raise
                time.sleep(5*(attempt+1))
        print(f'::notice::One match-stats photo API-verified: https://www.facebook.com/{identity}')
    except Exception:
        row['status']='unknown' if not row.get('post_id') else 'known_id'
        print('::error::Photo outcome not confirmed; durable reservation kept. Do not blindly repost.')
    finally:write(checkpoint,state)
    cover=plan.get('cover')
    if cover:
        try:
            if cover['page_id']!=page.page:raise ValueError('Page mismatch')
            status=fb._json(page.opener,Request(f"https://graph.facebook.com/{fb.GRAPH_VERSION}/{cover['video_id']}?fields=status",headers={'Authorization':f'Bearer {page.token}'})).get('status') or {}
            if (status.get('publishing_phase') or {}).get('status')!='complete':raise ValueError('Known Reel not yet published')
            for attempt in range(3):
                state['cover_status']=apply_preferred(page.opener,cover['video_id'],page.token,Path(cover['path']),fb.GRAPH_VERSION)
                if state['cover_status']=='verified':break
                time.sleep(5*(attempt+1))
            print('::notice::Existing Reel preferred cover: '+str(state['cover_status'])+'. No video was uploaded.')
        except Exception:
            state['cover_status']='unconfirmed'
            print('::warning::Meta did not confirm the preferred cover. Existing Reel left published; no replacement video.')
        finally:write(checkpoint,state)
    if row['status']!='verified':raise SystemExit(1)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','send']);args=parser.parse_args()
    try:
        if args.action=='prepare':prepare()
        else:send()
    except SystemExit:raise
    except Exception:
        # Never stringify network exceptions, URLs, credentials or provider payloads.
        raise SystemExit('One-match test blocked or could not be confirmed. Inspect saved safe artifacts; no automatic photo repost.') from None


if __name__=='__main__':main()
