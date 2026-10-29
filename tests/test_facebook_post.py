"""Facebook acceptance, token hygiene and deletion ordering: no real uploads."""
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs

import pytest

import facebook_post as fb
import scanner

# Deliberately synthetic: exercise redaction without embedding a key-like literal.
TOKEN = "-".join(("fake", "page", "credential", "for", "tests"))
PAGE = "123456789"
ROOT = Path(__file__).resolve().parent.parent
REAL_DIMENSIONS = fb.dimensions


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    for name in ("FACEBOOK_PAGE_ACCESS_TOKEN", "FACEBOOK_PAGE_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VIDEO_RECOVERY_DIR", str(tmp_path / "recovery"))
    monkeypatch.setattr(fb, "dimensions", lambda path: (1080, 1920))
    monkeypatch.setattr(fb.time, "sleep", lambda _: None)
    # Accidental real API access fails the test.
    monkeypatch.setattr(fb, "build_opener", lambda *_: pytest.fail("Unexpected network request"))


def configure(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("FACEBOOK_PAGE_ID", PAGE)


def video(tmp_path):
    p = tmp_path / "briefing.mp4"
    p.write_bytes(b"test-mp4-content")
    return p


class Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self, limit=65536):
        return self.body[:limit]


def fake_upload(monkeypatch, body=None, error=None, events=None, statuses=None):
    calls = []
    replies = [body or json.dumps({"video_id":"987654321", "upload_url":"https://rupload.facebook.com/video-upload/v25.0/987654321"}).encode(),
               b'{"success":true}', b'{"success":true}']
    states = list(statuses or [{"status":{"video_status":"ready", "publishing_phase":{"status":"complete"}}}])
    def send(req, timeout):
        calls.append(req)
        if events is not None and len(calls) == 1:
            events.append("facebook")
        if error:
            raise error
        if req.get_method() == "GET":
            state = states.pop(0) if len(states)>1 else states[0]
            return Response(json.dumps(state).encode())
        return Response(replies.pop(0))
    monkeypatch.setattr(fb, "build_opener", lambda *_: SimpleNamespace(open=send))
    return calls


def telegram(monkeypatch, events, ok=True):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-telegram-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

    def send(url, **kwargs):
        events.append("telegram")
        assert kwargs["files"]["video"][1].read()  # Source still exists at Telegram send time.
        assert kwargs["data"]["supports_streaming"] == "true"
        return SimpleNamespace(status_code=200 if ok else 500, text="failed")

    monkeypatch.setattr(scanner.SESSION, "post", send)


def test_no_credentials_is_disabled_and_source_is_untouched(tmp_path):
    p = video(tmp_path)
    assert fb.publish(p).status == "disabled"
    assert p.exists()


@pytest.mark.parametrize("missing", ["FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_ACCESS_TOKEN"])
def test_partial_configuration_retains_recovery_copy(monkeypatch, tmp_path, caplog, missing):
    configure(monkeypatch)
    monkeypatch.delenv(missing)
    p = video(tmp_path)
    assert fb.publish(p).status == "failed"
    assert p.exists()
    assert list((tmp_path / "recovery").glob("*.mp4"))[0].read_bytes() == p.read_bytes()
    assert "Facebook Reel publishing failed" in caplog.text and TOKEN not in caplog.text


def test_native_reel_start_raw_upload_finish_status_and_receipt(monkeypatch, tmp_path, caplog):
    configure(monkeypatch)
    calls = fake_upload(monkeypatch)
    p = video(tmp_path)
    with caplog.at_level(logging.INFO):
        result = fb.publish(p, "PlayReport ZA · football\nFive verified matches. 18+.")
    assert result == fb.UploadResult("uploaded", "987654321")
    assert len(calls)==4
    start, transfer, finish, status = calls
    assert start.full_url == f"https://graph.facebook.com/v25.0/{PAGE}/video_reels"
    assert parse_qs(start.data.decode()) == {"upload_phase":["start"]}
    assert transfer.full_url == "https://rupload.facebook.com/video-upload/v25.0/987654321"
    assert transfer.get_header("Authorization") == f"OAuth {TOKEN}"
    assert transfer.get_header("Offset") == "0"
    data = b"".join(transfer.data)
    assert data == p.read_bytes() and int(transfer.get_header("Content-length")) == len(data)
    assert int(transfer.get_header("File_size")) == len(data)
    assert TOKEN.encode() not in data
    fields = parse_qs(finish.data.decode())
    assert fields["upload_phase"] == ["finish"] and fields["video_state"] == ["PUBLISHED"]
    assert fields["video_id"] == ["987654321"]
    assert fields["description"] == ["PlayReport ZA · football\nFive verified matches. 18+."]
    assert status.get_method() == "GET" and "fields=status" in status.full_url
    for req in (start,finish,status):
        assert req.get_header("Authorization") == f"Bearer {TOKEN}"
    assert all(TOKEN not in req.full_url and not req.full_url.endswith('/videos') for req in calls)
    assert TOKEN not in caplog.text and p.exists()
    assert fb.published_id(p) == "987654321"
    assert TOKEN not in fb._receipt(p).read_text()
    assert fb.publish(p).video_id == "987654321" and len(calls) == 4


def test_receipts_are_specific_to_file_contents_and_page(monkeypatch, tmp_path):
    configure(monkeypatch)
    calls = fake_upload(monkeypatch)
    p = video(tmp_path)
    fb.publish(p)
    p.write_bytes(b"new-video")
    assert fb.published_id(p) is None
    calls2 = fake_upload(monkeypatch)
    fb.publish(p)
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "222")
    assert fb.published_id(p) is None
    calls3 = fake_upload(monkeypatch)
    fb.publish(p)
    assert len(calls) == len(calls2) == len(calls3) == 4


@pytest.mark.parametrize("body", [b"not json", b'{}', b'{"success":true}', b'{"id":"not-a-video-id"}', b'{"id":"123","error":{}}'])
def test_bad_response_is_not_success(monkeypatch, tmp_path, body):
    configure(monkeypatch)
    fake_upload(monkeypatch, body=body)
    p = video(tmp_path)
    result = fb.publish(p)
    assert result.status == "failed"
    assert p.exists()


def test_http_error_logs_numeric_codes_not_tokens_or_response_messages(monkeypatch, tmp_path, caplog):
    configure(monkeypatch)
    body = json.dumps({"error": {"code": 190, "error_subcode": 463, "message": TOKEN}}).encode()
    error = HTTPError("https://example.invalid/?access_token=" + TOKEN, 400, TOKEN, {}, io.BytesIO(body))
    fake_upload(monkeypatch, error=error)
    p = video(tmp_path)
    assert fb.publish(p).status == "failed"
    assert p.exists() and "Graph code 190" in caplog.text and "subcode 463" in caplog.text
    assert TOKEN not in caplog.text


@pytest.mark.parametrize("error", [URLError(TOKEN), TimeoutError(TOKEN), RuntimeError(TOKEN)])
def test_network_or_unexpected_failure_is_not_retried_or_logged_raw(monkeypatch, tmp_path, caplog, error):
    configure(monkeypatch)
    calls = fake_upload(monkeypatch, error=error)
    p = video(tmp_path)
    assert fb.publish(p).status == "failed"
    assert len(calls) == 1 and p.exists()
    assert TOKEN not in caplog.text


def test_video_chunks_are_bounded(tmp_path):
    p = video(tmp_path)
    p.write_bytes(b"x" * (fb.CHUNK_SIZE * 2 + 13))
    body = fb._VideoBody(p)
    chunks = list(body)
    assert max(map(len, chunks)) <= fb.CHUNK_SIZE
    assert sum(map(len, chunks)) == body.size


def test_bearer_token_cannot_follow_redirect():
    assert fb._NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid/") is None


@pytest.mark.parametrize("fb_ok,tg_ok,deleted", [(True,True,True),(False,True,False),(True,False,False),(False,False,False)])
def test_scanner_delivery_order_and_cleanup(monkeypatch, tmp_path, caplog, fb_ok, tg_ok, deleted):
    configure(monkeypatch)
    events = []
    fake_upload(monkeypatch, body=None if fb_ok else b'{}', events=events)
    telegram(monkeypatch, events, ok=tg_ok)
    p = video(tmp_path)
    assert scanner.send_telegram_video(p, "caption", width=1080, height=1920) is tg_ok
    assert events == ["facebook", "telegram"]
    assert p.exists() is not deleted
    if not fb_ok:
        assert "Facebook Reel publishing failed" in caplog.text
        assert list((tmp_path / "recovery").glob("*.mp4"))


def test_delete_after_false_is_respected(monkeypatch, tmp_path):
    configure(monkeypatch)
    fake_upload(monkeypatch)
    telegram(monkeypatch, [])
    p = video(tmp_path)
    assert scanner.send_telegram_video(p, "caption", delete_after=False, width=1080, height=1920)
    assert p.exists()


def test_facebook_can_succeed_even_when_telegram_is_unconfigured(monkeypatch, tmp_path):
    configure(monkeypatch)
    fake_upload(monkeypatch)
    p = video(tmp_path)
    assert scanner.send_telegram_video(p, "caption", width=1080, height=1920) is False  # Preserve Telegram boolean contract.
    assert fb.published_id(p) and p.exists()


@pytest.mark.parametrize("fb_ok", [True,False])
def test_one_shot_workflow_sends_telegram_even_when_facebook_fails(monkeypatch, tmp_path, fb_ok):
    configure(monkeypatch)
    events = []
    fake_upload(monkeypatch, body=None if fb_ok else b'{}', events=events)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-telegram-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "tmp" / "briefing-reel.mp4"
    p.parent.mkdir()
    p.write_bytes(b"video")
    import urllib.request

    def send(req, timeout):
        events.append("telegram")
        return Response(b'{"ok":true,"result":{"message_id":1}}')

    monkeypatch.setattr(urllib.request, "urlopen", send)
    workflow = (ROOT / ".github/workflows/send-briefing.yml").read_text()
    script = workflow.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    import textwrap
    if fb_ok:
        exec(compile(textwrap.dedent(script), "one-shot-workflow", "exec"), {})
    else:
        with pytest.raises(SystemExit) as error:
            exec(compile(textwrap.dedent(script), "one-shot-workflow", "exec"), {})
        assert error.value.code == 1
    assert events == ["facebook", "telegram"]
    assert p.exists() is not fb_ok


def test_workflows_pass_secrets_and_preserve_recovery_artifacts():
    for name in ("scan", "send-briefing"):
        source = (ROOT / f".github/workflows/{name}.yml").read_text()
        assert "${{ secrets.FACEBOOK_PAGE_ACCESS_TOKEN }}" in source
        assert "${{ secrets.FACEBOOK_PAGE_ID }}" in source
        assert "if: always()" in source and "actions/upload-artifact@v4.6.2" in source
        assert "tmp/video-recovery" in source and "retention-days: 7" in source


@pytest.mark.parametrize('size', [(1920,1080),(1080,1080),(720,1280+100),(360,640),None])
def test_landscape_square_small_and_unknown_media_never_reach_facebook(monkeypatch, tmp_path, size):
    configure(monkeypatch)
    monkeypatch.setattr(fb,'dimensions',lambda p:size)
    p=video(tmp_path)
    assert fb.publish(p).status=='failed'
    assert p.exists() and list((tmp_path/'recovery').glob('*.mp4'))


def test_untrusted_upload_host_never_receives_token(monkeypatch,tmp_path):
    configure(monkeypatch)
    calls=fake_upload(monkeypatch,body=b'{"video_id":"123","upload_url":"https://evil.invalid/video-upload/v25.0/123"}')
    assert fb.publish(video(tmp_path)).status=='failed'
    assert len(calls)==1


def test_pending_reel_is_retained_and_resume_only_polls_same_id(monkeypatch,tmp_path):
    configure(monkeypatch)
    pending={'status':{'video_status':'processing','publishing_phase':{'status':'in_progress'}}}
    calls=fake_upload(monkeypatch,statuses=[pending])
    p=video(tmp_path)
    assert fb.publish(p).status=='failed'
    assert len(calls)==3+fb.STATUS_ATTEMPTS and p.exists()
    assert fb.published_id(p) is None
    assert json.loads(fb._receipt(p).read_text())['phase']=='finishing'
    assert list((tmp_path/'recovery').glob('*.facebook-upload.json'))
    resumed=fake_upload(monkeypatch)
    assert fb.publish(p).status=='uploaded'
    assert len(resumed)==1 and resumed[0].get_method()=='GET'
    assert '987654321' in resumed[0].full_url


def test_remote_processing_rejection_is_not_success(monkeypatch,tmp_path,caplog):
    configure(monkeypatch)
    fake_upload(monkeypatch,statuses=[{'status':{'video_status':'error','processing_phase':{'errors':[TOKEN]}}}])
    p=video(tmp_path)
    assert fb.publish(p).status=='failed' and p.exists()
    assert fb.published_id(p) is None and TOKEN not in caplog.text


@pytest.mark.parametrize('stage',['transfer','finish'])
def test_unacknowledged_stage_keeps_file_and_does_not_publish_again(monkeypatch,tmp_path,stage):
    configure(monkeypatch)
    calls=[]
    def send(req,timeout):
        calls.append(req)
        if len(calls)==1:
            return Response(b'{"video_id":"123","upload_url":"https://rupload.facebook.com/video-upload/v25.0/123"}')
        if stage=='transfer' or len(calls)==3:
            return Response(b'{"success":false}')
        return Response(b'{"success":true}')
    monkeypatch.setattr(fb,'build_opener',lambda *_:SimpleNamespace(open=send))
    p=video(tmp_path)
    assert fb.publish(p).status=='failed' and p.exists()
    assert len(calls)==(2 if stage=='transfer' else 3)


def test_old_ordinary_video_receipt_cannot_skip_reel_publication(monkeypatch,tmp_path):
    configure(monkeypatch)
    p=video(tmp_path)
    fb._receipt(p).write_text(json.dumps({'video_id':'111','page_id':PAGE,'sha256':fb._digest(p)}))
    assert fb.published_id(p) is None
    calls=fake_upload(monkeypatch)
    assert fb.publish(p).status=='uploaded' and len(calls)==4


def test_landscape_telegram_send_does_not_call_facebook(monkeypatch,tmp_path):
    configure(monkeypatch)
    events=[]
    telegram(monkeypatch,events)
    p=video(tmp_path)
    assert scanner.send_telegram_video(p,'caption',width=1920,height=1080)
    assert events==['telegram'] and not p.exists()


@pytest.mark.parametrize('fb_ok,tg_ok',[(True,True),(False,True),(True,False),(False,False)])
def test_separate_portrait_and_landscape_routing_and_cleanup(monkeypatch,tmp_path,fb_ok,tg_ok):
    configure(monkeypatch)
    events=[]
    calls=fake_upload(monkeypatch,body=None if fb_ok else b'{}',events=events)
    telegram(monkeypatch,events,ok=tg_ok)
    landscape=video(tmp_path)
    portrait=tmp_path/'portrait.mp4';portrait.write_bytes(b'portrait-data')
    monkeypatch.setattr(fb,'dimensions',lambda p:(1080,1920) if p==portrait else (1920,1080))
    assert scanner.send_telegram_video(landscape,'caption',width=1920,height=1080,facebook_path=portrait) is tg_ok
    assert events==['facebook','telegram']
    if fb_ok:
        assert calls[1].data.path==portrait
    assert landscape.exists() is not (fb_ok and tg_ok)
    assert portrait.exists() is not (fb_ok and tg_ok)


def test_missing_portrait_does_not_block_telegram_or_upload_landscape(monkeypatch,tmp_path):
    configure(monkeypatch)
    events=[];telegram(monkeypatch,events)
    p=video(tmp_path)
    assert scanner.send_telegram_video(p,'caption',width=1920,height=1080,facebook_path=tmp_path/'missing.mp4')
    assert events==['telegram'] and p.exists()
    assert list((tmp_path/'recovery').glob('*.mp4'))


def test_one_shot_routes_only_portrait_to_facebook(monkeypatch,tmp_path):
    configure(monkeypatch)
    events=[];calls=fake_upload(monkeypatch,events=events)
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','fake-tg');monkeypatch.setenv('TELEGRAM_CHAT_ID','123')
    monkeypatch.chdir(tmp_path)
    (tmp_path/'tmp').mkdir()
    landscape=tmp_path/'tmp'/'briefing.mp4';landscape.write_bytes(b'landscape')
    portrait=tmp_path/'tmp'/'briefing-reel.mp4';portrait.write_bytes(b'portrait')
    import urllib.request,textwrap
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**kw:Response(b'{"ok":true,"result":{"message_id":1}}'))
    source=(ROOT/'.github/workflows/send-briefing.yml').read_text()
    script=source.split("python3 - <<'PY'\n",1)[1].split('\n          PY',1)[0]
    exec(compile(textwrap.dedent(script),'one-shot-workflow','exec'),{})
    assert calls[1].data.path==Path('tmp/briefing-reel.mp4')
    assert not landscape.exists() and not portrait.exists()


@pytest.mark.parametrize('rotation,sar,expected',[(0,'1:1',(1080,1920)),(90,'1:1',None),(0,'2:1',None)])
def test_actual_metadata_inspector_checks_rotation_and_pixel_shape(monkeypatch,tmp_path,rotation,sar,expected):
    monkeypatch.setattr(fb.shutil,'which',lambda tool:'/tools/ffprobe')
    data={'streams':[{'width':1080,'height':1920,'sample_aspect_ratio':sar,'side_data_list':[{'rotation':rotation}]}]}
    monkeypatch.setattr(fb.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout=json.dumps(data)))
    assert REAL_DIMENSIONS(video(tmp_path))==expected
