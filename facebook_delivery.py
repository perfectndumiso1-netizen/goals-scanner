"""Bounded Facebook-only delivery retries. No renderer or other delivery channels."""
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import shutil
import time
from urllib.request import Request
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

log=logging.getLogger('scanner')


def page_token(fb):
    """Verify Page identity; resolve an authorised user token for this Page only."""
    token=os.environ.get('FACEBOOK_PAGE_ACCESS_TOKEN','').strip()
    page=os.environ.get('FACEBOOK_PAGE_ID','').strip()
    if not token or not page.isdigit():raise ValueError('Missing Page configuration')
    opener=fb.build_opener(fb._NoRedirect())
    def read(node,fields,credential):
        for attempt in range(3):
            try:
                return fb._json(opener,Request(f'https://graph.facebook.com/{fb.GRAPH_VERSION}/{node}?fields={fields}',headers={'Authorization':f'Bearer {credential}'}))
            except HTTPError as error:
                if error.code not in (429,500,502,503,504) or attempt==2:raise
            except (URLError,TimeoutError):
                if attempt==2:raise
            time.sleep(5*(attempt+1))
    if str(read('me','id',token).get('id'))==page:return token
    resolved=read(page,'access_token',token).get('access_token')
    if not isinstance(resolved,str) or not resolved or str(read('me','id',resolved).get('id'))!=page:
        raise ValueError('Configured credential cannot identify the target Page')
    return resolved


def _stage(path,caption,fb):
    """Keep media outside Git; workflow artifact + tiny state queue provide durability."""
    path=Path(path)
    if not path.is_file():return
    directory=Path(os.getenv('VIDEO_RECOVERY_DIR') or fb.ROOT/'tmp/video-recovery')
    directory.mkdir(parents=True,exist_ok=True)
    digest=fb._digest(path); target=directory/f'briefing-9x16-reel-{digest[:20]}.mp4'
    if path.resolve()!=target.resolve():shutil.copy2(path,target)
    for source,dest in ((fb._receipt(path),fb._receipt(target)),
                        (path.with_suffix('.cover.jpg'),target.with_suffix('.cover.jpg')),
                        (path.with_suffix('.cover-state.json'),target.with_suffix('.cover-state.json'))):
        if source.is_file() and source.resolve()!=dest.resolve():shutil.copy2(source,dest)
    manifest=dict(file=target.name,sha256=digest,caption=caption,
                  date=datetime.now(ZoneInfo('Africa/Johannesburg')).date().isoformat(),
                  receipt_required=fb._receipt(path).exists(),video_id=fb._read_receipt(path).get('video_id'))
    import video_delivery_health as video_health
    manifest.update(video_health.identity())
    target.with_suffix('.delivery.json').write_text(json.dumps(manifest))


def stage(path,caption,fb):
    try:_stage(path,caption,fb)
    except OSError:
        log.error('Facebook recovery artifact could not be saved; original retained, other delivery channels will still be attempted.')


def deliver(path,caption,fb,once):
    """Four bounded rounds; never repeat ambiguous byte uploads or finish POSTs."""
    old=os.environ.get('FACEBOOK_PAGE_ACCESS_TOKEN'); previous=os.environ.get('FACEBOOK_RETRY_ATTEMPT')
    result=fb.UploadResult('failed')
    try:
        os.environ['FACEBOOK_RETRY_ATTEMPT']='1'
        try:os.environ['FACEBOOK_PAGE_ACCESS_TOKEN']=page_token(fb)
        except Exception:
            # Credential/body/URL details deliberately omitted. No publishing attempt.
            log.error('Facebook Page authorisation could not be verified; check Page permissions or token expiry. Video retained.')
            stage(path,caption,fb)
            return result
        for attempt in range(4):
            result=once(path,caption)
            if result.status=='uploaded':
                receipt=fb._read_receipt(Path(path))
                if receipt.get('cover_status')=='unconfirmed' and attempt<3:
                    time.sleep(10*(attempt+1));continue  # Published receipt: thumbnail-only work, never reupload.
                if receipt.get('cover_status')=='unconfirmed':stage(path,caption,fb)
                return result
            receipt=fb._read_receipt(Path(path))
            if not result.retryable or receipt.get('phase')=='uploading':break
            if attempt<3:
                log.warning('Facebook delivery pending/transient; automatic safe retry %d/3 on the same saved session.',attempt+1)
                time.sleep(10*(attempt+1))
        stage(path,caption,fb)
        log.error('Facebook delivery not confirmed after bounded retries. Durable recovery queued; no other channels resent.')
        return result
    finally:
        if old is None:os.environ.pop('FACEBOOK_PAGE_ACCESS_TOKEN',None)
        else:os.environ['FACEBOOK_PAGE_ACCESS_TOKEN']=old
        if previous is None:os.environ.pop('FACEBOOK_RETRY_ATTEMPT',None)
        else:os.environ['FACEBOOK_RETRY_ATTEMPT']=previous
