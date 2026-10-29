"""One explicitly authorized Facebook-only retry of a retained portrait Reel."""
from __future__ import annotations
import argparse
import io
import json
import logging
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlsplit, urlencode
from urllib.request import Request, build_opener
import zipfile
import shutil

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import facebook_post as fb
from scripts.inspect_facebook_recovery import github_download, inspect_video


def clean(value):
    text=str(value)
    for name in ('FACEBOOK_PAGE_ACCESS_TOKEN','GH_READ_TOKEN'):
        secret=os.getenv(name,'').strip()
        if secret:
            text=text.replace(secret,'[REDACTED]').replace(quote(secret,safe=''),'[REDACTED]')
    text=re.sub(r'https?://\S+','[URL omitted]',text)
    text=re.sub(r'\bEAA[A-Za-z0-9_-]{20,}\b','[REDACTED]',text)
    return ' '.join(text.split())[:1500]


def stage(request):
    if urlsplit(request.full_url).hostname=='rupload.facebook.com':return 'byte_transfer'
    if request.data and isinstance(request.data,bytes):
        return (parse_qs(request.data.decode()).get('upload_phase') or ['control'])[0]
    return 'publication_status'


def check_access():
    """Read only: identity, target visibility, and user-token grants/Page tasks. Never fetch tokens."""
    page=os.getenv('FACEBOOK_PAGE_ID','').strip()
    auth=os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN','').strip()
    report={'status':'access_check_only','publishing_attempts':0,'telegram_attempts':0,'errors':[]}
    if not auth or not re.fullmatch(r'[1-9]\d*',page):
        report['errors'].append({'message':'Missing token or numeric target Page ID'})
        return report
    opener=build_opener(fb._NoRedirect())
    def get(node,fields):
        req=Request(f'https://graph.facebook.com/{fb.GRAPH_VERSION}/{node}?'+urlencode(fields),
                    headers={'Authorization':f'Bearer {auth}'},method='GET')
        try:
            return fb._json(opener,req)
        except HTTPError as error:
            try:
                data=json.loads(error.read(65536)).get('error') or {}
                detail={k:clean(data[k]) for k in ('message','code','error_subcode') if k in data}
            except (ValueError,TypeError,AttributeError):detail={}
            report['errors'].append({'check':node if node.startswith('me') else 'target_page',
                                     'http_status':error.code,**detail})
        except Exception as error:
            report['errors'].append({'check':'read_access','exception_type':type(error).__name__})
        return {}
    identity=get('me',{'fields':'id'})
    if identity.get('id'):
        report['token_identity_matches_target_page']=str(identity['id'])==page
    target=get(page,{'fields':'id,name'})
    report['target_page_readable']=str(target.get('id',''))==page
    if target.get('name'):report['target_page_name']=clean(target['name'])
    if report.get('token_identity_matches_target_page') is False:
        permissions=get('me/permissions',{})
        report['granted_page_permissions']=[str(row['permission']) for row in permissions.get('data',[])
            if row.get('status')=='granted' and str(row.get('permission','')).startswith('pages_')]
        accounts=get('me/accounts',{'fields':'id,tasks','limit':100})
        matching=[row for row in accounts.get('data',[]) if str(row.get('id'))==page]
        report['target_in_managed_pages']=bool(matching)
        report['target_page_tasks']=matching[0].get('tasks',[]) if matching else []
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True)
    args=parser.parse_args()
    request=json.loads(Path(args.request).read_text())
    if request.get('action')=='check_access':
        report=check_access()
        work=Path('tmp/facebook-retry');work.mkdir(parents=True,exist_ok=True)
        (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        message=json.dumps(report,separators=(',',':')).replace('%','%25').replace('\r','%0D').replace('\n','%0A')
        print('::notice::Facebook read-only access check: '+message,flush=True)
        return 0
    artifact=str(request['artifact_id'])
    if not re.fullmatch(r'[1-9]\d*',artifact):raise SystemExit('Invalid artifact ID')
    work=Path('tmp/facebook-retry');work.mkdir(parents=True,exist_ok=True)
    report={'source_artifact':artifact,'telegram_attempts':0,'rerendered':False,'errors':[]}
    original_json=fb._json
    class Capture(logging.Handler):
        def emit(self,record):
            if record.name=='scanner' and 'Facebook' in record.getMessage():
                report.setdefault('publisher_diagnostics',[]).append(clean(record.getMessage()))
    handler=Capture();logger=logging.getLogger('scanner');logger.addHandler(handler);logger.setLevel(logging.INFO)
    def control(opener,req):
        current=stage(req);report['last_stage']=current
        try:
            value=original_json(opener,req)
            if current=='publication_status':
                # Store only status/error information, not request headers or arbitrary Graph response fields.
                report['meta_status']=json.loads(clean_json(value.get('status') or {}))
            return value
        except HTTPError as error:
            body=error.read(65536)
            try:
                data=json.loads(body).get('error') or {}
                detail={k:clean(data[k]) for k in ('message','type','code','error_subcode','error_user_title','error_user_msg') if k in data}
            except (ValueError,TypeError,AttributeError):detail={'message':'Meta returned a non-JSON error body; body omitted'}
            report['errors'].append({'stage':current,'http_status':error.code,**detail})
            # Give the existing publisher the same response body, so its normal recovery logic still works.
            raise HTTPError(error.url,error.code,error.reason,error.headers,io.BytesIO(body)) from None
        except Exception as error:
            report['errors'].append({'stage':current,'exception_type':type(error).__name__})
            raise
    fb._json=control
    ok=False
    try:
        private=work/'source.zip'
        github_download(os.environ['GITHUB_REPOSITORY'],f'actions/artifacts/{artifact}/zip',private,os.environ['GH_READ_TOKEN'])
        video=work/'briefing-9x16-reel.mp4'
        with zipfile.ZipFile(private) as archive:
            matches=[i for i in archive.infolist() if Path(i.filename).name==video.name]
            if len(matches)!=1:raise ValueError('Expected exactly one original portrait video')
            with archive.open(matches[0]) as source,video.open('wb') as target:shutil.copyfileobj(source,target,1024*1024)
            receipt_name=video.name+'.facebook-upload.json'
            receipts=[i for i in archive.infolist() if Path(i.filename).name==receipt_name]
            if receipts:
                if len(receipts)!=1:raise ValueError('Ambiguous source receipts')
                (work/receipt_name).write_bytes(archive.read(receipts[0]))
        private.unlink()
        report['media']=inspect_video(video)
        if fb.dimensions(video)!=(1080,1920):raise ValueError('Original portrait dimensions do not match the verified source')
        saved=Path('state/data/facebook-retries')/(artifact+'.json')
        if saved.exists():
            shutil.copy2(saved,work/(video.name+'.facebook-upload.json'))
        result=fb.publish(video,request['caption'])
        report.update(status=result.status,reel_id=result.video_id)
        ok=result.status=='uploaded'
        if ok:report['url']=f'https://www.facebook.com/reel/{result.video_id}'
    except Exception as error:
        report.update(status='failed',failure_type=type(error).__name__)
    finally:
        fb._json=original_json;logger.removeHandler(handler)
        receipt=work/'briefing-9x16-reel.mp4.facebook-upload.json'
        if receipt.exists():
            saved=Path('state/data/facebook-retries')/(artifact+'.json')
            saved.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(receipt,saved)
        (work/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        message=json.dumps(report,ensure_ascii=False,separators=(',',':'))
        print('::notice::Facebook-only retry result: '+message.replace('%','%25').replace('\r','%0D').replace('\n','%0A'),flush=True)
        if os.getenv('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as target:target.write('## Facebook-only retry\n\n```json\n'+json.dumps(report,indent=2)+'\n```\n')
    return 0 if ok else 1


def clean_json(value):
    if isinstance(value,dict):return json.dumps({k:json.loads(clean_json(v)) for k,v in value.items()})
    if isinstance(value,list):return json.dumps([json.loads(clean_json(v)) for v in value])
    return json.dumps(clean(value) if isinstance(value,str) else value)


if __name__=='__main__':raise SystemExit(main())
