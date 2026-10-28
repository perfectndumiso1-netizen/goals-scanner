"""Facebook acceptance, token hygiene and deletion ordering: no real uploads."""
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

import facebook_post as fb
import scanner

# Deliberately synthetic: exercise redaction without embedding a key-like literal.
TOKEN = "-".join(("fake", "page", "credential", "for", "tests"))
PAGE = "123456789"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    for name in ("FACEBOOK_PAGE_ACCESS_TOKEN", "FACEBOOK_PAGE_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VIDEO_RECOVERY_DIR", str(tmp_path / "recovery"))
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


def fake_upload(monkeypatch, body=b'{"id":"987654321"}', error=None, events=None):
    calls = []

    def send(req, timeout):
        calls.append(req)
        if events is not None:
            events.append("facebook")
        if error:
            raise error
        return Response(body)

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
    assert "Facebook publishing failed" in caplog.text and TOKEN not in caplog.text


def test_streamed_multipart_bearer_auth_and_receipt(monkeypatch, tmp_path, caplog):
    configure(monkeypatch)
    calls = fake_upload(monkeypatch)
    p = video(tmp_path)
    with caplog.at_level(logging.INFO):
        result = fb.publish(p, "PlayReport ZA · football\nFive verified matches. 18+.")
    assert result == fb.UploadResult("uploaded", "987654321")
    req = calls[0]
    assert req.full_url == f"https://graph-video.facebook.com/v25.0/{PAGE}/videos"
    assert TOKEN not in req.full_url
    assert req.get_header("Authorization") == f"Bearer {TOKEN}"
    data = b"".join(req.data)
    assert int(req.get_header("Content-length")) == len(data)
    assert b'name="source"' in data and p.read_bytes() in data
    assert b'name="published"\r\n\r\ntrue' in data
    assert b'name="description"' in data
    assert TOKEN.encode() not in data
    assert TOKEN not in caplog.text
    assert p.exists()  # Uploader does not own deletion.
    assert fb.published_id(p) == "987654321"
    assert TOKEN not in fb._receipt(p).read_text()
    assert fb.publish(p).video_id == "987654321" and len(calls) == 1


def test_receipts_are_specific_to_file_contents_and_page(monkeypatch, tmp_path):
    configure(monkeypatch)
    calls = fake_upload(monkeypatch)
    p = video(tmp_path)
    fb.publish(p)
    p.write_bytes(b"new-video")
    assert fb.published_id(p) is None
    fb.publish(p)
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "222")
    assert fb.published_id(p) is None
    fb.publish(p)
    assert len(calls) == 3


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
    body = fb._VideoBody(p, "caption")
    chunks = list(body)
    assert max(map(len, chunks)) <= fb.CHUNK_SIZE
    assert sum(map(len, chunks)) == body.size


def test_bearer_token_cannot_follow_redirect():
    assert fb._NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid/") is None


@pytest.mark.parametrize("fb_ok,tg_ok,deleted", [(True,True,True),(False,True,False),(True,False,False),(False,False,False)])
def test_scanner_delivery_order_and_cleanup(monkeypatch, tmp_path, caplog, fb_ok, tg_ok, deleted):
    configure(monkeypatch)
    events = []
    fake_upload(monkeypatch, body=b'{"id":"456"}' if fb_ok else b'{}', events=events)
    telegram(monkeypatch, events, ok=tg_ok)
    p = video(tmp_path)
    assert scanner.send_telegram_video(p, "caption", width=1920, height=1080) is tg_ok
    assert events == ["facebook", "telegram"]
    assert p.exists() is not deleted
    if not fb_ok:
        assert "Facebook publishing failed" in caplog.text
        assert list((tmp_path / "recovery").glob("*.mp4"))


def test_delete_after_false_is_respected(monkeypatch, tmp_path):
    configure(monkeypatch)
    fake_upload(monkeypatch)
    telegram(monkeypatch, [])
    p = video(tmp_path)
    assert scanner.send_telegram_video(p, "caption", delete_after=False)
    assert p.exists()


def test_facebook_can_succeed_even_when_telegram_is_unconfigured(monkeypatch, tmp_path):
    configure(monkeypatch)
    fake_upload(monkeypatch)
    p = video(tmp_path)
    assert scanner.send_telegram_video(p, "caption") is False  # Preserve Telegram boolean contract.
    assert fb.published_id(p) and p.exists()


@pytest.mark.parametrize("fb_ok", [True,False])
def test_one_shot_workflow_sends_telegram_even_when_facebook_fails(monkeypatch, tmp_path, fb_ok):
    configure(monkeypatch)
    events = []
    fake_upload(monkeypatch, body=b'{"id":"456"}' if fb_ok else b'{}', events=events)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-telegram-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "tmp" / "briefing.mp4"
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
