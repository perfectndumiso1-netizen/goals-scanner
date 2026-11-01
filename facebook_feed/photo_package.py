"""Validation/staging for one multi-photo post (four new; two legacy). Never resumes uncertain uploads."""
import hashlib
from datetime import datetime
from pathlib import Path
from . import content, storage
from .publisher import PageFeed, PublishError

FIELDS=('kind','topic','fixture_ids','operation','target_id','snapshot','image_sha256','image_sha256s','event_ids','slot_key')


def validate(post,entry,run_key):
    if entry.get('run_key')!=run_key or entry.get('status')!='reserved':
        raise ValueError('Package reservation ownership mismatch; no retry')
    if post.get('kind')!='editorial' or hashlib.sha256(post['caption'].encode()).hexdigest()!=entry.get('caption_hash') or any(post.get(k)!=entry.get(k) for k in FIELDS):
        raise ValueError('Package differs from durable reservation')
    images,hashes=post.get('images'),entry.get('image_sha256s')
    if not isinstance(images,list) or len(images) not in (2,4) or len(set(images))!=len(images) or not isinstance(hashes,list) or len(hashes)!=len(images):
        raise ValueError('Package needs all four reserved pictures (or an unchanged legacy pair)')
    if post.get('image')!=images[0] or entry.get('image_sha256')!=hashes[0]:
        raise ValueError('Package first-picture identity changed')
    for image,digest in zip(images,hashes):
        p=Path(image)
        if not p.is_file() or not 0<p.stat().st_size<=8*1024*1024 or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise ValueError('Package picture missing, changed or oversized')


def stage(work,now,run_key,factory=PageFeed):
    statepath=work/'checkpoint/state.json'
    state=content.load(statepath);plans=content.load(work/'plans.json')
    if not isinstance(plans,list) or len(plans)!=1:raise ValueError('Expected one match package')
    post=plans[0]
    entries=[e for e in state['posts'] if e.get('key')==post['key'] and e.get('run_key')==run_key]
    if len(entries)!=1:raise ValueError('Package reservation ownership mismatch')
    entry=entries[0];validate(post,entry,run_key)
    if entry.get('media_phase') or entry.get('media_ids'):raise ValueError('Package staging already attempted; no retry')
    if now>=content.local(post['expires_at']):
        entry.update(status='cancelled',delivery_failure='expired_before_mutation');storage.write(statepath,state);return False
    mutated=False
    try:
        publisher=factory()
        # Credential checks can take time. Never start uploads of expired content.
        if datetime.now(content.SAST)>=content.local(post['expires_at']):
            entry.update(status='cancelled',delivery_failure='expired_before_mutation');return False
        entry.update(status='unknown',media_phase='uploading');storage.write(statepath,state)
        def checkpoint(ids):
            entry['media_ids']=ids;storage.write(statepath,state)
        mutated=True
        ids=publisher.stage_package(post['images'],checkpoint)
        if not isinstance(ids,list) or len(ids)!=len(post['images']) or len(set(ids))!=len(ids):raise PublishError('Incomplete photo staging; keep reservation')
        entry.update(status='reserved',media_phase='staged',media_ids=ids)
        return True
    except PublishError as error:
        entry['error']=str(error)
        if not mutated:
            entry.update(status='cancelled',delivery_failure='preflight_temporary' if error.retryable else 'facebook_preflight_blocked')
        else:
            # This function only called /photos with published=false; it has NO
            # feed-creation call. Preserve orphan IDs but permit bounded fresh
            # preparation: retrying here cannot duplicate a public feed post.
            entry.update(status='cancelled',media_phase='upload_failed_unpublished',delivery_failure='unpublished_staging_incomplete')
        return False
    finally:
        storage.write(statepath,state)
