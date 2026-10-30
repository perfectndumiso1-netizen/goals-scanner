"""Independent artifact checkpoints: no writes/locks on the scanner's data branch."""
import hashlib
import json
from pathlib import Path
import re
import zipfile
from urllib.request import Request,build_opener
from facebook_post import _NoRedirect
from scripts.inspect_facebook_recovery import github_download


MAX_STATE_BYTES=16*1024*1024


class StateError(RuntimeError):
    pass


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    if path.name=='state.json' and len(text.encode())>MAX_STATE_BYTES:raise StateError('State checkpoint size bound exceeded; no mutation permitted')
    temporary=path.with_suffix('.tmp');temporary.write_text(text,encoding='utf-8')
    temporary.replace(path)


def namespace(repo,branch,publish):
    digest=hashlib.sha256(f'{repo}:{branch}:{"live" if publish else "dry"}:v1'.encode()).hexdigest()[:16]
    return 'pr-feed-state-'+digest+'-'


def restore(repo,branch,repository_id,prefix,token,directory):
    """Return None only for a genuinely absent checkpoint, never for a fetch/parse failure."""
    try:
        request=Request(f'https://api.github.com/repos/{repo}/actions/artifacts?per_page=100',
            headers={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json'})
        with build_opener(_NoRedirect()).open(request,timeout=30) as response:
            data=json.loads(response.read(2*1024*1024))
        candidates=[a for a in data['artifacts'] if a['name'].startswith(prefix) and not a['expired'] and
            (a.get('workflow_run') or {}).get('head_branch')==branch and
            str((a.get('workflow_run') or {}).get('head_repository_id'))==str(repository_id)]
        if not candidates:
            # More than one page could hide an older valid state. Never silently bootstrap from an incomplete index.
            if data.get('total_count',0)>100:
                for page in range(2,101):
                    next_request=Request(f'https://api.github.com/repos/{repo}/actions/artifacts?per_page=100&page={page}',headers=request.headers)
                    with build_opener(_NoRedirect()).open(next_request,timeout=30) as response:
                        more=json.loads(response.read(2*1024*1024))
                    candidates=[a for a in more['artifacts'] if a['name'].startswith(prefix) and not a['expired'] and
                        (a.get('workflow_run') or {}).get('head_branch')==branch and
                        str((a.get('workflow_run') or {}).get('head_repository_id'))==str(repository_id)]
                    if candidates or page*100>=data['total_count']:
                        break
                else:
                    raise StateError('State search bound reached; operator inspection required')
            if not candidates:
                return None
        latest=max(candidates,key=lambda a:(a['created_at'],a['id']))
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        archive=directory/'restore.zip'
        github_download(repo,f"actions/artifacts/{latest['id']}/zip",archive,token)
        with zipfile.ZipFile(archive) as source:
            files=[i for i in source.infolist() if i.filename=='state.json']
            if len(files)!=1 or files[0].file_size>MAX_STATE_BYTES:
                raise StateError('Invalid state checkpoint size/shape')
            state=json.loads(source.read(files[0]))
        archive.unlink()
        if state.get('schema')!=1 or state.get('namespace')!=prefix or not isinstance(state.get('posts'),list):
            raise StateError('State schema/namespace mismatch')
        return state
    except StateError:
        raise
    except Exception:
        raise StateError('Cannot restore durable feed state; publishing blocked, not reset') from None
