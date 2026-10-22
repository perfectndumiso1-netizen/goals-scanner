"""The Google Drive handoff: configuration gating, RS256 signing, the resumable upload and the scan hook."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

import drive_handoff as dh


# ------------------------------------------------------------------ a throwaway RSA key, built here
# A real key must never be committed, and the tests must not need openssl, so the DER is assembled by hand. The
# numbers are tiny: the point is the ASN.1 shape and the padding, not the strength of the key.
N = int(
    "ad4503d64dbf7f426812cb7faf7eccdde1e45f824c55205c529a320f3988f1b7"
    "7b14b3afcce71b26c196bec964e68115ec54afb984e0ed52487e616aae3ff295"
    "b45993f25b7dc1409e3462e52434ffb74f6d5fccee6fcf6883f411708e009560"
    "1582d43a6478df14ff2ed5c8ff3f05e1f05f159da29628d7048233f047b5a5d1", 16)
E = 65537
D = int(
    "ac0a4ab50e9d858e3a27ef46e8c9ce40c17a301b000fc601e5429551e89ec0e2"
    "9da300871dbc9a88f0ceecc0ab1ef42d006b55cfaed066d3bc873fd2dd11419b"
    "20af2fdbdf80eeda967568dd2c3324fa9ab9b240aa59ce2e38479990b4f6049d"
    "d288a9c99bbbb7e6ec0207232123c0295e70bb6c98c109446ee46339fbf7601", 16)


def _tlv(tag: int, body: bytes) -> bytes:
    n = len(body)
    if n < 0x80:
        return bytes([tag, n]) + body
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([tag, 0x80 | len(raw)]) + raw + body


def _int(v: int) -> bytes:
    raw = v.to_bytes((v.bit_length() + 7) // 8 or 1, "big")
    if raw[0] & 0x80:
        raw = b"\x00" + raw
    return _tlv(0x02, raw)


def _pkcs1() -> bytes:
    return _tlv(0x30, _int(0) + _int(N) + _int(E) + _int(D) + _int(3) + _int(7) + _int(11)
                + _int(13) + _int(17) + _int(19))


def _pkcs8() -> bytes:
    algo = _tlv(0x30, _tlv(0x06, bytes.fromhex("2a864886f70d010101")) + _tlv(0x05, b""))
    return _tlv(0x30, _int(0) + algo + _tlv(0x04, _pkcs1()))


def _pem(der: bytes, label: str = "PRIVATE KEY") -> str:
    body = base64.encodebytes(der).decode("ascii").strip()
    return f"-----BEGIN {label}-----\n{body}\n-----END {label}-----\n"


def _sa(**over) -> dict:
    sa = {"client_email": "handoff@playreport.iam.gserviceaccount.com",
          "private_key": _pem(_pkcs8()), "token_uri": dh.TOKEN_URL}
    sa.update(over)
    return sa


# ------------------------------------------------------------------ configuration

CRED_VARS = ("GDRIVE_SA_JSON", "GDRIVE_FOLDER_ID", "DRIVE_HANDOFF", "GDRIVE_CLIENT_ID",
             "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN", "YT_CLIENT_ID", "YT_CLIENT_SECRET")


def _clear(monkeypatch):
    for name in CRED_VARS:
        monkeypatch.delenv(name, raising=False)


def test_nothing_is_configured_without_the_secrets(monkeypatch):
    _clear(monkeypatch)
    assert dh.service_account() is None and dh.folder_id() == ""
    assert dh.configured() is False and dh.enabled() is False
    assert dh.mode() == "none"


def test_a_switched_on_but_incomplete_lane_says_so_out_loud(monkeypatch):
    """The bug this guards: for a whole day the handoff was ON, unconfigured, and silent — the videos only
    reached Telegram and nothing anywhere said why."""
    _clear(monkeypatch)
    monkeypatch.setenv("DRIVE_HANDOFF", "1")
    st = dh.status()
    assert st["switch_on"] is True and st["enabled"] is False
    assert st["missing"] == ["GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN", "GDRIVE_FOLDER_ID"]
    said = dh.describe()
    assert "ON but NOT configured" in said and "GDRIVE_REFRESH_TOKEN" in said
    assert "Telegram only" in said


def test_switched_off_says_it_is_off_rather_than_missing_secrets(monkeypatch):
    _clear(monkeypatch)
    assert dh.describe() == "Drive handoff is OFF (DRIVE_HANDOFF is not set to 1)"


def test_the_users_own_account_is_the_preferred_mode(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GDRIVE_CLIENT_ID", "cid")
    monkeypatch.setenv("GDRIVE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GDRIVE_REFRESH_TOKEN", "refresh")
    monkeypatch.setenv("GDRIVE_FOLDER_ID", "folder-123")
    monkeypatch.setenv("DRIVE_HANDOFF", "1")
    assert dh.mode() == "user"
    assert dh.enabled() is True and dh.missing() == []
    assert "your Google account" in dh.describe()


def test_the_youtube_oauth_client_can_be_reused(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("YT_CLIENT_ID", "cid")
    monkeypatch.setenv("YT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GDRIVE_REFRESH_TOKEN", "refresh")
    monkeypatch.setenv("GDRIVE_FOLDER_ID", "folder-123")
    assert dh.mode() == "user" and dh.configured() is True


def test_a_user_refresh_token_is_exchanged_and_wins_over_the_service_account(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GDRIVE_CLIENT_ID", "cid")
    monkeypatch.setenv("GDRIVE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GDRIVE_REFRESH_TOKEN", "refresh")
    monkeypatch.setenv("GDRIVE_SA_JSON", json.dumps(_sa()))
    seen = {}

    def fake_request(method, url, **kw):
        seen.update(kw.get("data") or {})
        return FakeResp(200, {"access_token": "user-token"})

    monkeypatch.setattr(dh, "_request", fake_request)
    assert dh.access_token() == "user-token"
    assert seen["grant_type"] == "refresh_token" and seen["refresh_token"] == "refresh"


def test_the_quota_refusal_explains_the_fix(monkeypatch):
    """Google's 'Service Accounts do not have storage quota' is the trap for a personal My Drive."""
    body = {"error": {"errors": [{"reason": "storageQuotaExceeded"}],
                      "message": "Service Accounts do not have storage quota. Leverage shared drives."}}
    monkeypatch.setattr(dh, "_request", lambda *a, **k: FakeResp(403, body, text=json.dumps(body)))
    with pytest.raises(dh.DriveError) as exc:
        dh.upload_bytes("tok", b"data", "name", fid="folder-123")
    msg = str(exc.value)
    assert "no storage quota" in msg and "scripts/drive_auth.py" in msg


def test_a_missing_folder_points_at_sharing(monkeypatch):
    monkeypatch.setattr(dh, "_request", lambda *a, **k: FakeResp(404, {"error": "nf"}, text="not found"))
    with pytest.raises(dh.DriveError) as exc:
        dh.upload_bytes("tok", b"data", "name", fid="folder-123")
    assert "404" in str(exc.value) and "Share it" in str(exc.value)


def test_the_switch_needs_both_the_secrets_and_the_flag(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GDRIVE_SA_JSON", json.dumps(_sa()))
    monkeypatch.setenv("GDRIVE_FOLDER_ID", "folder-123")
    assert dh.mode() == "service-account"
    assert dh.configured() is True and dh.enabled() is False
    monkeypatch.setenv("DRIVE_HANDOFF", "1")
    assert dh.enabled() is True


def test_a_broken_or_partial_json_is_treated_as_unconfigured(monkeypatch):
    for bad in ("{not json", json.dumps({"client_email": "x@y"}), json.dumps({"private_key": "k"})):
        _clear(monkeypatch)
        monkeypatch.setenv("GDRIVE_SA_JSON", bad)
        monkeypatch.setenv("GDRIVE_FOLDER_ID", "folder-123")
        monkeypatch.setenv("DRIVE_HANDOFF", "1")
        assert dh.service_account() is None
        assert dh.enabled() is False


def test_titles_have_no_extension(monkeypatch):
    assert dh.title_for(Path("/tmp/briefing-16x9.mp4")) == "briefing-16x9"
    assert dh.title_for(Path("shortlist.2026-10-21.mp4")) == "shortlist.2026-10-21"


# ------------------------------------------------------------------ signing

@pytest.mark.parametrize("der", [_pkcs1(), _pkcs8()])
def test_the_private_key_is_read_from_pkcs1_and_pkcs8(der):
    n, d = dh.rsa_key(_pem(der, "RSA PRIVATE KEY" if der is _pkcs1() else "PRIVATE KEY"))
    assert n == N and d == D


def test_the_signature_is_a_valid_pkcs1_v15_sha256_signature():
    import hashlib

    token = dh.sign_rs256("hello.playreport", _pem(_pkcs8()))
    k = (N.bit_length() + 7) // 8
    raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    assert len(raw) == k
    em = pow(int.from_bytes(raw, "big"), E, N).to_bytes(k, "big")
    expected = (b"\x00\x01" + b"\xff" * (k - len(dh._SHA256_DIGEST_INFO) - 32 - 3) + b"\x00"
                + dh._SHA256_DIGEST_INFO + hashlib.sha256(b"hello.playreport").digest())
    assert em == expected


def test_the_jwt_carries_the_service_account_identity_and_scope():
    tok = dh.assertion(_sa(), now=1_700_000_000)
    header, claims, _sig = tok.split(".")
    pad = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))  # noqa: E731
    assert json.loads(pad(header))["alg"] == "RS256"
    body = json.loads(pad(claims))
    assert body["iss"] == "handoff@playreport.iam.gserviceaccount.com"
    assert body["scope"] == dh.SCOPE and body["aud"] == dh.TOKEN_URL
    assert body["exp"] - body["iat"] == dh.JWT_LIFETIME


# ------------------------------------------------------------------ upload

class FakeResp:
    def __init__(self, status=200, body=None, headers=None, text=""):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}
        self.text = text or json.dumps(self._body)

    def json(self):
        return self._body


def test_the_upload_is_resumable_and_lands_in_the_folder_with_video_mime(monkeypatch):
    calls = []

    def fake_request(method, url, **kw):
        calls.append((method, url, kw))
        if method == "POST":
            return FakeResp(200, {"id": "file-1"}, headers={"Location": "https://upload.example/session"})
        return FakeResp(200, {"id": "file-1", "name": "briefing-16x9", "size": "24"})

    monkeypatch.setattr(dh, "_request", fake_request)
    out = dh.upload_bytes("tok", b"x" * 24, "briefing-16x9", fid="folder-123")
    assert out == {"id": "file-1", "name": "briefing-16x9", "size": 24, "link": None}

    start, put = calls
    assert start[2]["params"]["uploadType"] == "resumable"
    meta = json.loads(start[2]["data"])
    assert meta["name"] == "briefing-16x9" and not meta["name"].endswith(".mp4")   # Zapier → YouTube
    assert meta["mimeType"] == "video/mp4" and meta["parents"] == ["folder-123"]
    assert put[0] == "PUT" and put[1] == "https://upload.example/session"
    assert put[2]["headers"]["Content-Type"] == "video/mp4"


def test_a_failed_upload_start_raises_a_readable_error(monkeypatch):
    monkeypatch.setattr(dh, "_request", lambda *a, **k: FakeResp(403, {"error": "no"}, text="forbidden"))
    with pytest.raises(dh.DriveError) as exc:
        dh.upload_bytes("tok", b"data", "name", fid="folder-123")
    assert "403" in str(exc.value)


def test_a_dry_run_sends_a_two_kb_stand_in_and_never_the_video(monkeypatch, tmp_path):
    sent = {}

    def fake_upload(token, payload, name, *, fid=None, mime=dh.VIDEO_MIME):
        sent.update(size=len(payload), name=name, mime=mime, fid=fid)
        return {"id": "x", "name": name, "size": len(payload), "link": None}

    monkeypatch.setattr(dh, "upload_bytes", fake_upload)
    video = tmp_path / "briefing-16x9.mp4"
    video.write_bytes(b"v" * 10_000)
    res = dh.upload_video(video, dry_run=True, token="tok", fid="folder-123")
    assert res["dry_run"] is True
    assert sent["size"] == dh.DRY_RUN_BYTES and sent["mime"] == "text/plain"
    assert sent["name"] == "briefing-16x9 (dry run)"
    assert video.read_bytes() == b"v" * 10_000                  # the video is never modified


def test_a_missing_video_is_an_error_but_not_a_crash(monkeypatch, tmp_path):
    with pytest.raises(dh.DriveError):
        dh.upload_video(tmp_path / "nope.mp4", token="tok", fid="folder-123")


# ------------------------------------------------------------------ scan hook

def test_the_hook_does_nothing_when_the_switch_is_off(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setattr(dh, "upload_video", lambda *a, **k: pytest.fail("uploaded with the switch off"))
    assert dh.handoff(tmp_path / "video.mp4") is None


def test_the_hook_uploads_then_tells_telegram(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("GDRIVE_SA_JSON", json.dumps(_sa()))
    monkeypatch.setenv("GDRIVE_FOLDER_ID", "folder-123")
    monkeypatch.setenv("DRIVE_HANDOFF", "1")
    monkeypatch.setattr(dh, "upload_video",
                        lambda path, dry_run=False: {"id": "f1", "name": "briefing-16x9", "size": 2048})
    said = []
    res = dh.handoff(tmp_path / "briefing-16x9.mp4", notify=said.append)
    assert res["id"] == "f1"
    assert said == ["📤 YouTube handoff: briefing-16x9 → PlayReport/YouTube"]


def test_a_drive_failure_is_reported_and_swallowed(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("GDRIVE_SA_JSON", json.dumps(_sa()))
    monkeypatch.setenv("GDRIVE_FOLDER_ID", "folder-123")
    monkeypatch.setenv("DRIVE_HANDOFF", "1")

    def boom(*_a, **_k):
        raise dh.DriveError("quota exceeded")

    monkeypatch.setattr(dh, "upload_video", boom)
    said = []
    assert dh.handoff(tmp_path / "briefing-16x9.mp4", notify=said.append) is None
    assert said and "quota exceeded" in said[0] and said[0].startswith("⚠️")


def test_the_scanner_calls_the_handoff_before_it_sends_to_telegram():
    src = (Path(__file__).resolve().parent.parent / "scanner.py").read_text(encoding="utf-8")
    assert "import drive_handoff as drive_mod" in src
    assert src.index("drive_mod.handoff(out_16x9") < src.index("ok_16x9 = send_telegram_video(")


def test_the_scanner_warns_when_the_lane_is_on_but_unconfigured():
    """A silent skip is what let a switched-on-but-unconfigured handoff look healthy; the scan must say why."""
    src = (Path(__file__).resolve().parent.parent / "scanner.py").read_text(encoding="utf-8")
    assert "if drive_mod.enabled():" in src
    assert "drive_mod.describe()" in src
    assert "drive_handoff_warned" in src              # once a day, not once per video slot
    assert "Drive handoff did not run" in src


def test_the_workflow_passes_the_user_credentials_through():
    from pathlib import Path as _P
    wf = (_P(__file__).resolve().parent.parent / ".github" / "workflows" / "scan.yml").read_text(encoding="utf-8")
    for name in ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN",
                 "GDRIVE_FOLDER_ID", "GDRIVE_SA_JSON", "DRIVE_HANDOFF"):
        assert f"{name}:" in wf, name


# ------------------------------------------------------------------ the one-time authorisation helper

def test_the_auth_helper_asks_for_the_right_scope_and_redirect():
    sys_path = str(Path(__file__).resolve().parent.parent / "scripts")
    import importlib.util
    spec = importlib.util.spec_from_file_location("drive_auth", Path(sys_path) / "drive_auth.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    url = mod.auth_url("cid.apps.googleusercontent.com")
    assert "accounts.google.com/o/oauth2/v2/auth" in url
    assert "drive.file" in url and "access_type=offline" in url
    assert f"127.0.0.1%3A{mod.PORT}" in url
    assert mod.PORT != 8765                       # never collide with scripts/yt_auth.py
    assert mod._code_from("http://127.0.0.1:8766/?code=abc123&scope=x") == "abc123"
    assert mod._code_from("  abc123  ") == "abc123"
