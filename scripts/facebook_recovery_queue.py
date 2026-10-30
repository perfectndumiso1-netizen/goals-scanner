"""Resume saved Facebook sessions on ordinary scans; media remains in Actions artifacts."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import facebook_post as fb
from scripts.inspect_facebook_recovery import github_download
from scripts.retry_facebook_reel import extract_portrait


def load(path):
    if not path.exists():return {'version':1,'items':[]}
    data=json.loads(path.read_text())
    if data.get('version')!=1 or not isinstance(data.get('items'),list):raise ValueError('Recovery queue invalid; not resetting')
    return data


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2));temp.replace(path)


def register(path,directory,artifact):
    if not str(artifact).isdigit():return
    data=load(path);today=datetime.now(ZoneInfo('Africa/Johannesburg')).date().isoformat()
    for file in Path(directory).glob('*.delivery.json'):
        item=json.loads(file.read_text());digest=item.get('sha256','')
        if not re.fullmatch('[a-f0-9]{64}',digest) or item.get('file')!=f'briefing-9x16-reel-{digest[:20]}.mp4' or item.get('date')!=today:continue
        old=next((row for row in data['items'] if row['sha256']==digest),None)
        if old and old['status'] in ('confirmed','needs_attention'):continue
        if old:old.update(artifact_id=str(artifact))
        else:data['items'].append(dict(item,artifact_id=str(artifact),attempts=0,status='pending'))
    data['items']=data['items'][-16:];save(path,data)


def recover(path):
    data=load(path);today=datetime.now(ZoneInfo('Africa/Johannesburg')).date().isoformat()
    for item in sorted((r for r in data['items'] if r['status']=='pending'),key=lambda r:r['attempts'])[:1]:
        if item['date']!=today:item['status']='expired';save(path,data);continue
        item['attempts']+=1;save(path,data)
        try:
            work=Path('tmp/facebook-auto')/item['sha256'][:20];work.mkdir(parents=True,exist_ok=True)
            archive=work/'source.zip'
            github_download(os.environ['GITHUB_REPOSITORY'],f"actions/artifacts/{item['artifact_id']}/zip",archive,os.environ['GH_READ_TOKEN'])
            # A single scan may retain both editions. Select this exact digest and its sidecars.
            import zipfile
            selected=work/'selected.zip'
            with zipfile.ZipFile(archive) as source, zipfile.ZipFile(selected,'w') as target:
                for entry in source.infolist():
                    name=Path(entry.filename).name
                    stem=Path(item['file']).stem
                    if name==item['file'] or name in (item['file']+'.facebook-upload.json',stem+'.cover.jpg',stem+'.cover-state.json'):
                        target.writestr(name,source.read(entry))
            video=extract_portrait(selected,work);archive.unlink();selected.unlink()
            if fb._digest(video)!=item['sha256']:raise ValueError('Saved video digest mismatch')
            receipt=fb._read_receipt(video)
            if (item.get('receipt_required') and not receipt) or (item.get('video_id') and receipt.get('video_id')!=item['video_id']):
                raise ValueError('Saved session missing/invalid; new upload forbidden')
            result=fb.publish(video,item['caption'])
            receipt=fb._read_receipt(video)
            if result.status=='uploaded' and receipt.get('cover_status')!='unconfirmed':
                item.update(status='confirmed',video_id=result.video_id)
                print('::notice::Facebook saved delivery confirmed; no Telegram resend or new video render.')
            elif item['attempts']>=8:
                item['status']='needs_attention'
                print('::error::Facebook automatic recovery budget exhausted; saved media/session retained for inspection.')
        except Exception:
            if item['attempts']>=8:item['status']='needs_attention'
            print('::warning::Facebook saved recovery could not be confirmed; details/credentials omitted, next scan resumes within budget.')
        save(path,data)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['register','recover']);parser.add_argument('--state',required=True);parser.add_argument('--directory',default='tmp/video-recovery');parser.add_argument('--artifact-id',default='')
    args=parser.parse_args()
    if args.action=='register':register(Path(args.state),args.directory,args.artifact_id)
    else:recover(Path(args.state))


if __name__=='__main__':main()
