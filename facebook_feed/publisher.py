"""Independent Page feed/photo publisher. No Reel/video endpoints or delivery imports."""
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import urlencode, quote
from urllib.request import Request, build_opener
import uuid
from facebook_post import GRAPH_VERSION, _NoRedirect


class PublishError(RuntimeError):
    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.retryable = retryable  # Only meaningful BEFORE a creation request.


class PageFeed:
    def __init__(self, opener=None):
        self.page=os.getenv('FACEBOOK_PAGE_ID','').strip()
        supplied=os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN','').strip()
        self.credentials=[supplied]
        self.opener=opener or build_opener(_NoRedirect())
        if not supplied or not re.fullmatch(r'[1-9]\d*',self.page):
            raise PublishError('Missing Page credential or numeric Page ID')
        identity=self.call('GET','me',{'fields':'id'},credential=supplied)
        if str(identity.get('id'))==self.page:
            self.token=supplied
        else:
            value=self.call('GET',self.page,{'fields':'access_token'},credential=supplied).get('access_token')
            if not isinstance(value,str) or not value:
                raise PublishError('User credential cannot resolve the target Page credential')
            self.credentials.append(value)
            check=self.call('GET','me',{'fields':'id'},credential=value)
            if str(check.get('id'))!=self.page:
                raise PublishError('Resolved credential belongs to a different Page; nothing posted')
            self.token=value  # Memory only. Never include in output, state, URLs or artifact files.

    def redact(self,value):
        text=str(value)
        for credential in self.credentials:
            if credential:
                text=text.replace(credential,'[REDACTED]').replace(quote(credential,safe=''),'[REDACTED]')
        return re.sub(r'https?://\S+','[URL omitted]',' '.join(text.split()))[:800]

    def call(self,method,path,fields=None,credential=None,body=None,content_type=None):
        if not re.fullmatch(r'(?:me|[1-9]\d*)(?:/(?:feed|photos))?|\d+_\d+',path):
            raise PublishError('Unapproved Graph path')
        url=f'https://graph.facebook.com/{GRAPH_VERSION}/{path}'
        headers={'Authorization':f'Bearer {credential or self.token}'}
        if method=='GET':
            url+='?'+urlencode(fields or {})
        elif body is None:
            body=urlencode(fields or {}).encode()
            content_type='application/x-www-form-urlencoded'
        if body is not None:
            headers.update({'Content-Type':content_type,'Content-Length':str(len(body))})
        try:
            with self.opener.open(Request(url,data=body,headers=headers,method=method),timeout=45) as response:
                data=json.loads(response.read(256*1024))
        except HTTPError as error:
            try:
                value=json.loads(error.read(65536)).get('error') or {}
                detail=self.redact(value.get('message',''))
                code=int(value.get('code',0));subcode=int(value.get('error_subcode',0))
            except (ValueError,TypeError,AttributeError):
                detail='Response omitted';code=subcode=0
            raise PublishError(f'Graph HTTP {error.code}, code {code}, subcode {subcode}: {detail}', retryable=method=='GET' and (error.code==429 or error.code>=500)) from None
        except Exception:
            raise PublishError('Graph network/response failure; outcome may be ambiguous. No automatic retry.', retryable=method=='GET') from None
        if not isinstance(data,dict) or 'error' in data:
            raise PublishError('Invalid Graph response; inspect the Page before any manual retry')
        return data

    def send(self,post):
        if post.get('images'):
            raise PublishError('Two-picture posts require durable media staging; single-photo fallback blocked')
        if post.get('operation')=='edit':
            target=post['target_id']
            if not target.startswith(self.page+'_'):
                raise PublishError('Refusing to edit a post outside the configured Page')
            result=self.call('POST',target,{'message':post['caption']})
            if result.get('success') is not True:
                raise PublishError('Edit was not acknowledged; do not create a replacement automatically')
            return target
        if post.get('image'):
            image=Path(post['image'])
            if image.stat().st_size>8*1024*1024:
                raise PublishError('Graphic exceeds the local size cap')
            boundary='mr2odds-'+uuid.uuid4().hex
            fields=[]
            for name,value in (('caption',post['caption']),('published','true')):
                fields.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
            fields.append(f'--{boundary}\r\nContent-Disposition: form-data; name="source"; filename="Mr 2 Odds.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode())
            body=b''.join(fields)+image.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
            result=self.call('POST',self.page+'/photos',body=body,content_type=f'multipart/form-data; boundary={boundary}')
            identity=str(result.get('post_id',''))
        else:
            identity=str(self.call('POST',self.page+'/feed',{'message':post['caption']}).get('id',''))
        if not re.fullmatch(re.escape(self.page)+r'_\d+',identity):
            raise PublishError('No verifiable Page post ID returned; publication outcome unknown')
        return identity

    def stage_package(self,images,checkpoint):
        """Upload exactly two UNPUBLISHED photos. Never creates a feed post here."""
        if not isinstance(images,list) or len(images)!=2 or len(set(map(str,images)))!=2:
            raise PublishError('A match package needs two distinct pictures')
        paths=[Path(p) for p in images]
        if any(not p.is_file() or not 0<p.stat().st_size<=8*1024*1024 for p in paths):
            raise PublishError('Package picture missing or exceeds size cap')
        ids=[]
        for index,path in enumerate(paths):
            boundary='MatchPackage'+uuid.uuid4().hex
            body=(f'--{boundary}\r\nContent-Disposition: form-data; name="published"\r\n\r\nfalse\r\n'
                  f'--{boundary}\r\nContent-Disposition: form-data; name="source"; filename="match-{index+1}.jpg"\r\nContent-Type: image/jpeg\r\n\r\n').encode()
            body+=path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
            result=self.call('POST',self.page+'/photos',body=body,content_type=f'multipart/form-data; boundary={boundary}')
            identity=str(result.get('id',''))
            if not re.fullmatch(r'[1-9]\d*',identity) or identity in ids:
                raise PublishError('Photo staging acknowledgement invalid; no feed post created')
            ids.append(identity);checkpoint(list(ids))
        return ids

    def send_package(self,post,media_ids):
        if not isinstance(media_ids,list) or len(media_ids)!=2 or len(set(media_ids))!=2 or any(not isinstance(i,str) or not re.fullmatch(r'[1-9]\d*',i) for i in media_ids):
            raise PublishError('Two durably checkpointed photo IDs required')
        result=self.call('POST',self.page+'/feed',{'message':post['caption'],'published':'true',
            'attached_media':json.dumps([{'media_fbid':i} for i in media_ids])})
        identity=str(result.get('id',''))
        if not re.fullmatch(re.escape(self.page)+r'_\d+',identity):
            raise PublishError('Package feed acknowledgement missing; outcome unknown, no resend')
        return identity

    def verify_package_hash(self,identity,caption_hash,media_ids):
        if not re.fullmatch(re.escape(self.page)+r'_\d+',identity) or not isinstance(media_ids,list) or len(media_ids)!=2 or len(set(media_ids))!=2:
            raise PublishError('Package identity/media evidence unavailable; no resend')
        data=self.call('GET',identity,{'fields':'id,message,is_published,attachments{target,subattachments{target}}'})
        if (str(data.get('id'))!=identity or data.get('is_published') is not True or
            hashlib.sha256(str(data.get('message','')).encode()).hexdigest()!=caption_hash):
            raise PublishError('Package caption/publication not verified')
        found=[]
        try:
            if data['attachments'].get('paging',{}).get('next'):raise PublishError('Partial package attachments; keep reservation')
            for attachment in data['attachments']['data']:
                if attachment.get('subattachments',{}).get('paging',{}).get('next'):raise PublishError('Partial package photos; keep reservation')
                children=attachment['subattachments']['data'] if 'subattachments' in attachment else [attachment]
                found.extend(str(child['target']['id']) for child in children)
        except (KeyError,TypeError,AttributeError):
            raise PublishError('Package attachments unavailable; keep reservation') from None
        if found!=media_ids:
            raise PublishError('Both package photos/order not verified; keep reservation')
        return True

    def verify(self,identity,caption):
        if not identity.startswith(self.page+'_'):
            raise PublishError('Post does not belong to configured Page')
        data=self.call('GET',identity,{'fields':'id,message,is_published'})
        if str(data.get('id'))!=identity or str(data.get('message','')).strip()!=caption.strip() or data.get('is_published') is not True:
            raise PublishError('Post content not yet verified; keep reservation and inspect the Page')
        return True

    def find_reserved(self,entry):
        """Bounded positive discovery only; never infer that an empty feed is absence.

        Used for a lost POST acknowledgement/crashed run. Exact caption hash,
        configured Page, published flag and time proximity are all required.
        verify_hash performs a separate read-back before ledger reconciliation.
        """
        from datetime import timedelta
        from .content import local
        at=local(entry['at'])
        data=self.call('GET',self.page+'/feed',{'fields':'id,message,is_published,created_time',
            'limit':100,'since':int((at-timedelta(minutes=5)).timestamp()),
            'until':int((at+timedelta(minutes=15)).timestamp())})
        rows=data.get('data')
        if not isinstance(rows,list) or len(rows)>100:
            raise PublishError('Unverified Page feed discovery; reservation retained')
        found=[]
        for row in rows:
            if not isinstance(row,dict):continue
            identity=str(row.get('id',''))
            try:when=local(row['created_time'])
            except (KeyError,ValueError,TypeError):continue
            if (re.fullmatch(re.escape(self.page)+r'_\d+',identity) and row.get('is_published') is True and
                at-timedelta(minutes=5)<=when<=at+timedelta(minutes=15) and
                hashlib.sha256(str(row.get('message','')).encode()).hexdigest()==entry['caption_hash']):
                found.append(identity)
        return found[0] if len(found)==1 else None

    def verify_hash(self,identity,caption_hash):
        if not re.fullmatch(re.escape(self.page)+r'_\d+',identity):
            raise PublishError('Post does not belong to configured Page')
        data=self.call('GET',identity,{'fields':'id,message,is_published'})
        if str(data.get('id'))!=identity or data.get('is_published') is not True or hashlib.sha256(str(data.get('message','')).encode()).hexdigest()!=caption_hash:
            raise PublishError('Existing post does not match the reserved caption or is not published')
        return True
