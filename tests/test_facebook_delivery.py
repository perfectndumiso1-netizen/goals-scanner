"""Automatic delivery must never duplicate a Reel or replay another channel."""
import io
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
import zipfile
import pytest
import facebook_post as fb
import facebook_delivery as delivery
from facebook_cover import apply_preferred
from scripts import facebook_recovery_queue as queue
from test_facebook_post import configure,video,fake_upload,PAGE,TOKEN,Response


@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    configure(monkeypatch)
    monkeypatch.setenv('VIDEO_RECOVERY_DIR',str(tmp_path/'recovery'))
    monkeypatch.setenv('FACEBOOK_AUTOMATION','1')
    monkeypatch.setattr(delivery.time,'sleep',lambda *a:None)
    monkeypatch.setattr(fb,'dimensions',lambda *a:(1080,1920))
    monkeypatch.setattr(delivery,'page_token',lambda _:TOKEN)
    monkeypatch.setattr(fb,'build_opener',lambda *a:pytest.fail('unexpected real network'))


def test_pending_processing_retries_only_get_and_preserves_one_native_session(monkeypatch,tmp_path,caplog):
    monkeypatch.setattr(fb,'STATUS_ATTEMPTS',2)
    pending={'status':{'processing_phase':{'status':'in_progress'}}}
    complete={'status':{'publishing_phase':{'status':'complete'}}}
    calls=fake_upload(monkeypatch,statuses=[pending,pending,pending,complete])
    path=video(tmp_path)
    assert fb.publish(path,'caption').status=='uploaded'
    assert [r.get_method() for r in calls].count('POST')==3
    assert len([r for r in calls if r.get_method()=='GET'])==4
    assert 'automatic safe retry' in caplog.text
    assert not any(r.levelname=='ERROR' for r in caplog.records)
    assert fb.published_id(path)=='987654321'


def test_timeout_after_finish_is_resumed_without_posting_finish_again(monkeypatch,tmp_path):
    path=video(tmp_path);calls=[]
    fb._save(path,dict(kind=fb.KIND,page_id=PAGE,video_id='987',sha256=fb._digest(path)),'finishing')
    def open(request,**kw):
        calls.append(request)
        if len(calls)==1:raise TimeoutError('omitted')
        return Response(b'{"status":{"publishing_phase":{"status":"complete"}}}')
    monkeypatch.setattr(fb,'build_opener',lambda *a:SimpleNamespace(open=open))
    assert fb.publish(path,'caption').video_id=='987'
    assert len(calls)==2 and all(r.get_method()=='GET' for r in calls)


def test_ambiguous_byte_transfer_is_never_reposted(monkeypatch,tmp_path):
    path=video(tmp_path);calls=[]
    def open(request,**kw):
        calls.append(request)
        if len(calls)==1:return Response(b'{"video_id":"987","upload_url":"https://rupload.facebook.com/video-upload/v25.0/987"}')
        raise TimeoutError('omitted')
    monkeypatch.setattr(fb,'build_opener',lambda *a:SimpleNamespace(open=open))
    assert fb.publish(path,'caption').status=='failed'
    assert len(calls)==2
    assert fb.publish(path,'caption').status=='failed' and len(calls)==2
    manifest=json.loads(next((tmp_path/'recovery').glob('*.delivery.json')).read_text())
    assert manifest['receipt_required'] and manifest['video_id']=='987'


def test_retry_budget_is_bounded_and_cover_is_retained(monkeypatch,tmp_path):
    monkeypatch.setattr(fb,'STATUS_ATTEMPTS',1)
    calls=fake_upload(monkeypatch,statuses=[{'status':{'video_status':'processing'}}])
    path=video(tmp_path);path.with_suffix('.cover.jpg').write_bytes(b'original matches only')
    assert fb.publish(path,'caption').status=='failed'
    assert len(calls)==7  # three mutations, four status rounds.
    directory=tmp_path/'recovery'
    assert next(directory.glob('briefing-9x16-reel-*.cover.jpg')).read_bytes()==b'original matches only'
    assert len(list(directory.glob('*.delivery.json')))==1


def test_permanent_permission_error_does_not_blindly_repeat_posts(monkeypatch,tmp_path):
    calls=fake_upload(monkeypatch,error=HTTPError('https://example.invalid',403,'denied',{},io.BytesIO(b'{}')))
    assert fb.publish(video(tmp_path),'caption').status=='failed'
    assert len(calls)==1


def test_page_resolution_is_verified_in_memory_with_header_credentials(monkeypatch):
    monkeypatch.undo();configure(monkeypatch)
    calls=[];responses=[{'id':'999'},{'access_token':'resolved-synthetic'},{'id':PAGE}]
    def open(request,**kw):calls.append(request);return Response(json.dumps(responses.pop(0)).encode())
    monkeypatch.setattr(fb,'build_opener',lambda *a:SimpleNamespace(open=open))
    assert delivery.page_token(fb)=='resolved-synthetic'
    assert len(calls)==3 and all(r.get_method()=='GET' for r in calls)
    assert all(TOKEN not in r.full_url and 'resolved-synthetic' not in r.full_url for r in calls)
    assert calls[-1].get_header('Authorization')=='Bearer resolved-synthetic'


def test_original_token_is_restored_even_when_resolution_fails(monkeypatch,tmp_path,caplog):
    def fail(_):raise ValueError('private-credential-omitted')
    monkeypatch.setattr(delivery,'page_token',fail)
    assert fb.publish(video(tmp_path),'caption').status=='failed'
    import os
    assert os.environ['FACEBOOK_PAGE_ACCESS_TOKEN']==TOKEN
    assert 'private-credential-omitted' not in caplog.text


def test_eventually_preferred_cover_does_not_repeat_thumbnail_post(tmp_path):
    cover=tmp_path/'video.cover.jpg';cover.write_bytes(b'image');calls=[]
    answers=[{'data':[{'id':'old','is_preferred':True}]},{'success':True},
             {'data':[{'id':'old','is_preferred':True}]},{'data':[{'id':'new','is_preferred':True}]}]
    def open(request,**kw):calls.append(request);return Response(json.dumps(answers.pop(0)).encode())
    opener=SimpleNamespace(open=open)
    assert apply_preferred(opener,'123','synthetic',cover,'v25.0')=='unconfirmed'
    assert apply_preferred(opener,'123','synthetic',cover,'v25.0')=='verified'
    assert [r.get_method() for r in calls]==['GET','POST','GET','GET']


def test_queue_registration_and_next_scan_resume_same_receipt(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    path=video(tmp_path);path.with_suffix('.cover.jpg').write_bytes(b'cover')
    info=dict(kind=fb.KIND,page_id=PAGE,video_id='987',sha256=fb._digest(path))
    fb._save(path,info,'finishing');delivery.stage(path,'caption',fb)
    directory=tmp_path/'recovery';archive=tmp_path/'artifact.zip'
    with zipfile.ZipFile(archive,'w') as target:
        for file in directory.iterdir():target.write(file,file.name)
    state=tmp_path/'state.json';queue.register(state,directory,'123')
    monkeypatch.setenv('GITHUB_REPOSITORY','owner/repo');monkeypatch.setenv('GH_READ_TOKEN','synthetic')
    def download(repo,resource,dest,token):dest.write_bytes(archive.read_bytes())
    monkeypatch.setattr(queue,'github_download',download)
    def publish(video,caption):
        assert caption=='caption' and fb._read_receipt(video)['video_id']=='987'
        assert video.with_suffix('.cover.jpg').read_bytes()==b'cover'
        return fb.UploadResult('uploaded','987')
    monkeypatch.setattr(fb,'publish',publish)
    queue.recover(state)
    result=queue.load(state)['items'][0]
    assert result['status']=='confirmed' and result['attempts']==1
    queue.register(state,directory,'456')
    assert queue.load(state)['items'][0]['status']=='confirmed'


def test_corrupt_queue_is_not_reset(tmp_path):
    path=tmp_path/'state.json';path.write_text('{"version":99,"items":[]}')
    with pytest.raises(ValueError):queue.load(path)


def test_late_publication_applies_cover_then_retries_cover_only(monkeypatch,tmp_path):
    path=video(tmp_path);path.with_suffix('.cover.jpg').write_bytes(b'matches only')
    fb._save(path,dict(kind=fb.KIND,page_id=PAGE,video_id='987',sha256=fb._digest(path)),'finishing')
    calls=[];answers=[{'status':{'publishing_phase':{'status':'complete'}}},
                     {'data':[{'id':'old','is_preferred':True}]},{'success':True},
                     {'data':[{'id':'old','is_preferred':True}]},{'data':[{'id':'new','is_preferred':True}]}]
    def open(request,**kw):calls.append(request);return Response(json.dumps(answers.pop(0)).encode())
    monkeypatch.setattr(fb,'build_opener',lambda *a:SimpleNamespace(open=open))
    assert fb.publish(path,'caption').status=='uploaded'
    assert fb._read_receipt(path)['cover_status']=='verified'
    assert sum(r.get_method()=='POST' for r in calls)==1
    assert all('/video_reels' not in r.full_url and 'rupload.' not in r.full_url for r in calls)


def test_missing_saved_receipt_in_recovery_never_starts_new_upload(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    path=video(tmp_path)
    fb._save(path,dict(kind=fb.KIND,page_id=PAGE,video_id='987',sha256=fb._digest(path)),'finishing')
    delivery.stage(path,'caption',fb)
    directory=tmp_path/'recovery';archive=tmp_path/'artifact.zip'
    with zipfile.ZipFile(archive,'w') as target:
        for file in directory.iterdir():
            if not file.name.endswith('facebook-upload.json'):target.write(file,file.name)
    state=tmp_path/'state.json';queue.register(state,directory,'123')
    monkeypatch.setenv('GITHUB_REPOSITORY','owner/repo');monkeypatch.setenv('GH_READ_TOKEN','synthetic')
    monkeypatch.setattr(queue,'github_download',lambda repo,resource,dest,token:dest.write_bytes(archive.read_bytes()))
    monkeypatch.setattr(fb,'publish',lambda *a:pytest.fail('Missing receipt must not create new Reel'))
    queue.recover(state)
    assert queue.load(state)['items'][0]['status']=='pending'


def test_saved_recovery_confirms_only_its_explicit_edition_without_telegram_resend(monkeypatch,tmp_path):
    import video_delivery_health as health
    from datetime import datetime
    monkeypatch.chdir(tmp_path)
    day=datetime.now(health.SAST).date().isoformat()
    tracker=tmp_path/'app'/'video_delivery.json'
    path=video(tmp_path)
    fb._save(path,dict(kind=fb.KIND,page_id=PAGE,video_id='987',sha256=fb._digest(path)),'finishing')
    with health.edition_context(tracker,day,'noon'):
        health.observe('telegram','confirmed','456')
        delivery.stage(path,'caption',fb)
    directory=tmp_path/'recovery';archive=tmp_path/'artifact.zip'
    with zipfile.ZipFile(archive,'w') as target:
        for file in directory.iterdir():target.write(file,file.name)
    state=tmp_path/'state.json';queue.register(state,directory,'123')
    monkeypatch.setenv('GITHUB_REPOSITORY','owner/repo');monkeypatch.setenv('GH_READ_TOKEN','synthetic')
    monkeypatch.setattr(queue,'github_download',lambda repo,resource,dest,token:dest.write_bytes(archive.read_bytes()))
    def publish(video,caption):
        assert fb._read_receipt(video)['video_id']=='987'
        return fb.UploadResult('uploaded','987')
    monkeypatch.setattr(fb,'publish',publish)
    queue.recover(state)
    row=health.load(tracker)['days'][day]['noon']
    assert row['lanes']['telegram']['receipt_id']=='456'
    assert row['lanes']['facebook']['receipt_id']=='987'
    assert row['lanes']['facebook']['status']=='confirmed'
    assert set(health.load(tracker)['days'][day])=={'noon'}
