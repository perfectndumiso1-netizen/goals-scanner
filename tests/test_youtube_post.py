"""YouTube auto-poster: metadata rules, the probe's verdict, and the resumable upload — all without the network."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import youtube_post as yt


class Resp:
    def __init__(self, status: int = 200, body: dict | None = None, headers: dict | None = None, text: str = ""):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = text or json.dumps(self._body)

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def _creds(monkeypatch):
    """Every test starts with credentials present but uploads switched off unless it says otherwise."""
    monkeypatch.setenv("YT_CLIENT_ID", "cid")
    monkeypatch.setenv("YT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("YT_REFRESH_TOKEN", "refresh")
    monkeypatch.delenv("YT_UPLOAD", raising=False)
    monkeypatch.delenv("YT_SLOTS", raising=False)
    monkeypatch.delenv("YT_UPLOAD_BREAKDOWN", raising=False)
    monkeypatch.delenv("YT_PRIVACY", raising=False)


# ------------------------------------------------------------------ switches

def test_nothing_publishes_without_the_switch_and_the_secrets(monkeypatch):
    assert yt.configured() and not yt.enabled()          # creds alone are not permission to post
    monkeypatch.setenv("YT_UPLOAD", "1")
    assert yt.enabled()
    for var in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
        assert not yt.configured()
        assert not yt.enabled()


def test_slots_default_to_the_morning_video_only():
    assert yt.slot_allowed("morning")
    assert not yt.slot_allowed("noon") and not yt.slot_allowed("evening")


def test_slots_can_be_widened(monkeypatch):
    monkeypatch.setenv("YT_SLOTS", "morning, Noon ,evening")
    assert {s for s in ("morning", "noon", "evening") if yt.slot_allowed(s)} == {"morning", "noon", "evening"}
    assert not yt.slot_allowed("manual")


def test_privacy_falls_back_to_public_and_breakdown_is_on_by_default(monkeypatch):
    assert yt.default_privacy() == "public"
    monkeypatch.setenv("YT_PRIVACY", "unlisted")
    assert yt.default_privacy() == "unlisted"
    monkeypatch.setenv("YT_PRIVACY", "nonsense")
    assert yt.default_privacy() == "public"
    assert yt.breakdown_enabled()
    monkeypatch.setenv("YT_UPLOAD_BREAKDOWN", "0")
    assert not yt.breakdown_enabled()


# ------------------------------------------------------------------ metadata

def _picks(n=3):
    return [{"home": f"Home {i}", "away": f"Away {i}", "label": "Over 1.5 goals", "odds": 1.5 + i / 100,
             "sel": "O15"} for i in range(n)]


def test_titles_and_descriptions_are_valid_and_never_promote_a_bookmaker():
    m = yt.meta(kind="shortlist", day="Tue 21 Oct", items=_picks(), recap="Yesterday: 6/9 won")
    assert m["title"] and len(m["title"]) <= 100 and "<" not in m["title"] and ">" not in m["title"]
    assert len(m["description"].encode()) <= 5000
    assert "not betting advice" in m["description"] and "18+" in m["description"]
    assert "Home 0 v Away 0" in m["description"] and "6/9 won" in m["description"]
    assert m["categoryId"] == yt.CATEGORY_SPORTS                  # Sports
    assert m["madeForKids"] is False
    for banned in ("sportybet", "betway", "1xbet", "http://", "https://", "www."):
        assert banned not in m["description"].lower()
        assert banned not in m["title"].lower()


def test_tags_stay_inside_the_500_character_budget():
    tags = yt.tags()
    assert tags and sum(len(t) + 1 for t in tags) <= 500
    assert len(set(tags)) == len(tags)


def test_long_descriptions_are_truncated_on_a_word_boundary():
    huge = "word " * 5000
    out = yt.clean(huge, 4000)
    assert len(out.encode()) <= 4000 and not out.endswith(" ")
    assert "<" not in yt.clean("a < b > c", 100)


def test_breakdown_metadata_carries_the_matches_and_the_photo_credits():
    matches = [{"home": "Lyon", "away": "Crystal Palace"}, {"home": "Porto", "away": "Braga"}]
    m = yt.meta(kind="breakdown", day="Tue 21 Oct", items=matches, credits="Stadium photos via Wikimedia Commons")
    assert "Match Breakdown" in m["title"]
    assert "Lyon v Crystal Palace" in m["description"] and "Porto v Braga" in m["description"]
    assert "Wikimedia" in m["description"] and "18+" in m["description"]


def test_sidecar_round_trip(tmp_path):
    video = tmp_path / "briefing-16x9.mp4"
    video.write_bytes(b"video")
    m = yt.meta(kind="shortlist", day="Tue 21 Oct", items=_picks(1))
    side = yt.write_meta(video, m)
    assert side.name == "briefing-16x9.mp4.json"
    assert yt.read_meta(video)["title"] == m["title"]
    assert yt.read_meta(tmp_path / "nothing.mp4") == {}
    (tmp_path / "broken.mp4").write_bytes(b"v")
    (tmp_path / "broken.mp4.json").write_text("{not json", encoding="utf-8")
    assert yt.read_meta(tmp_path / "broken.mp4") == {}


# ------------------------------------------------------------------ upload

def _upload_mock(monkeypatch, *, privacy_back="public", record=None):
    def fake(method, url, **kw):
        if record is not None:
            record.append((method, url, kw))
        if url == yt.TOKEN_URL:
            return Resp(body={"access_token": "tok", "expires_in": 3600})
        if url.startswith(yt.UPLOAD_URL):
            return Resp(headers={"Location": "https://upload.example/session"}, body={})
        if url == "https://upload.example/session":
            return Resp(body={"id": "vid123", "snippet": {"title": "x"},
                              "status": {"privacyStatus": privacy_back, "uploadStatus": "processed"}})
        return Resp(status=404, body={"error": "unexpected url"})

    monkeypatch.setattr(yt, "_request", fake)


def test_upload_sends_metadata_and_reads_back_the_real_privacy(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 2048)
    calls = []
    _upload_mock(monkeypatch, privacy_back="public", record=calls)
    res = yt.upload_video(video, {"title": "T", "description": "D", "tags": ["a"], "categoryId": "17"})
    assert res == {**res, "id": "vid123", "privacy": "public", "requested": "public", "locked": False}

    init = [c for c in calls if c[1].startswith(yt.UPLOAD_URL)][0]
    body = json.loads(init[2]["data"])
    assert body["status"]["privacyStatus"] == "public"
    assert body["status"]["selfDeclaredMadeForKids"] is False
    assert body["snippet"]["categoryId"] == "17"
    assert init[2]["headers"]["X-Upload-Content-Length"] == "2048"
    assert init[2]["headers"]["Authorization"] == "Bearer tok"


def test_an_unaudited_project_is_reported_as_locked_not_as_success(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    _upload_mock(monkeypatch, privacy_back="private")            # requested public, YouTube pinned private
    res = yt.upload_video(video, {"title": "T"})
    assert res["locked"] is True and res["requested"] == "public" and res["privacy"] == "private"
    assert yt.report(res).startswith("LOCKED")
    assert "audit" in yt.report(res).lower()


def test_a_private_request_is_not_mistaken_for_a_lock(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    _upload_mock(monkeypatch, privacy_back="private")
    res = yt.upload_video(video, {"title": "T"}, privacy="private")
    assert res["locked"] is False


def test_scheduling_goes_through_private_with_publish_at(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    calls = []
    _upload_mock(monkeypatch, privacy_back="private", record=calls)
    res = yt.upload_video(video, {"title": "T"}, privacy="public", publish_at="2026-10-22T05:30:00Z")
    body = json.loads([c for c in calls if c[1].startswith(yt.UPLOAD_URL)][0][2]["data"])
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["publishAt"] == "2026-10-22T05:30:00Z"
    assert res["locked"] is False


def test_bad_privacy_and_missing_files_fail_before_any_request(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("no request should be made")

    monkeypatch.setattr(yt, "_request", boom)
    with pytest.raises(yt.YTError):
        yt.upload_video(tmp_path / "nope.mp4", {"title": "T"})
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    with pytest.raises(yt.YTError):
        yt.upload_video(f, {"title": "T"}, privacy="unlisted-ish")


def test_upload_errors_are_reported_with_the_api_message(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")

    def fake(method, url, **kw):
        if url == yt.TOKEN_URL:
            return Resp(body={"access_token": "tok"})
        return Resp(status=403, body={"error": {"message": "quotaExceeded"}})

    monkeypatch.setattr(yt, "_request", fake)
    with pytest.raises(yt.YTError) as exc:
        yt.upload_video(video, {"title": "T"})
    assert "403" in str(exc.value) and "quota" in str(exc.value)


def test_no_credentials_means_no_upload(tmp_path, monkeypatch):
    for var in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    with pytest.raises(yt.YTError) as exc:
        yt.upload_video(video, {"title": "T"})
    assert "not configured" in str(exc.value)


def test_credentials_never_print_the_secret():
    c = yt.Creds("cid", "very-secret", "refresh-token")
    assert "very-secret" not in repr(c) and "refresh-token" not in repr(c)


# ------------------------------------------------------------------ scan hooks

def test_publish_hooks_do_nothing_without_the_master_switch(monkeypatch, tmp_path):
    video = tmp_path / "briefing.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(yt, "upload_video", lambda *_a, **_k: pytest.fail("must not upload"))
    assert yt.publish_shortlist(video, day="Tue 21 Oct", picks=_picks(), slot="morning") is None
    assert yt.publish_breakdown(video, day="Tue 21 Oct", matches=[]) is None
    assert not yt.read_meta(video)                            # no sidecar either


def test_publish_shortlist_respects_the_slot_switch(monkeypatch, tmp_path):
    video = tmp_path / "briefing.mp4"
    video.write_bytes(b"x")
    monkeypatch.setenv("YT_UPLOAD", "1")
    called = []
    monkeypatch.setattr(yt, "upload_video", lambda *_a, **_k: called.append(1) or {"id": "v", "private": "public"})
    assert yt.publish_shortlist(video, day="Tue 21 Oct", picks=_picks(), slot="noon") is None
    assert called == []
    assert yt.publish_shortlist(video, day="Tue 21 Oct", picks=_picks(), slot="morning")
    assert called == [1]
    assert yt.read_meta(video)["title"]                      # the sidecar was written for the upload step


def test_publish_breakdown_can_be_switched_off(monkeypatch, tmp_path):
    video = tmp_path / "breakdown.mp4"
    video.write_bytes(b"x")
    monkeypatch.setenv("YT_UPLOAD", "1")
    monkeypatch.setenv("YT_UPLOAD_BREAKDOWN", "0")
    monkeypatch.setattr(yt, "upload_video", lambda *_a, **_k: {"id": "v"})
    assert yt.publish_breakdown(video, day="Tue 21 Oct", matches=[]) is None
    monkeypatch.setenv("YT_UPLOAD_BREAKDOWN", "1")
    assert yt.publish_breakdown(video, day="Tue 21 Oct", matches=[{"home": "A", "away": "B"}]) == {"id": "v"}


# ------------------------------------------------------------------ probe

def test_probe_reports_ok_then_deletes_its_clip(monkeypatch, tmp_path):
    def fake_clip(dest, **_kw):
        Path(dest).write_bytes(b"clip")
        return Path(dest)

    monkeypatch.setattr(yt, "probe_clip", fake_clip)
    monkeypatch.setattr(yt, "access_token", lambda _c: "tok")
    monkeypatch.setattr(yt, "channel_info", lambda _t: {"id": "UC1", "title": "PlayReport", "subscribers": 12})
    monkeypatch.setattr(yt, "token_scopes", lambda _t: [yt.SCOPE])
    monkeypatch.setattr(yt, "upload_video", lambda *_a, **_k: {"id": "probe1", "privacy": "unlisted",
                                                               "requested": "unlisted", "locked": False})
    monkeypatch.setattr(yt, "video_status", lambda *_a, **_k: {"privacy": "unlisted"})
    deleted = []
    monkeypatch.setattr(yt, "delete_video", lambda vid, **_k: deleted.append(vid) or True)
    monkeypatch.setattr(yt.time, "sleep", lambda _s: None)
    res = yt.probe(work=tmp_path)
    assert res["locked"] is False and res["deleted"] is True and deleted == ["probe1"]
    assert yt.report(res).startswith("OK")


def test_probe_reports_a_locked_project_and_warns(monkeypatch, tmp_path):
    def fake_clip(dest, **_kw):
        Path(dest).write_bytes(b"clip")
        return Path(dest)

    monkeypatch.setattr(yt, "probe_clip", fake_clip)
    monkeypatch.setattr(yt, "access_token", lambda _c: "tok")
    monkeypatch.setattr(yt, "channel_info", lambda _t: {"id": "UC1", "title": "PlayReport"})
    monkeypatch.setattr(yt, "token_scopes", lambda _t: [yt.SCOPE])
    monkeypatch.setattr(yt, "upload_video", lambda *_a, **_k: {"id": "probe1", "privacy": "private",
                                                               "requested": "unlisted", "locked": True})
    monkeypatch.setattr(yt, "delete_video", lambda vid, **_k: True)
    monkeypatch.setattr(yt.time, "sleep", lambda _s: None)
    res = yt.probe(work=tmp_path)
    assert res["locked"] is True
    assert yt.report(res).startswith("LOCKED")


def test_probe_without_credentials_never_touches_youtube(monkeypatch):
    for var in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(yt.YTError):
        yt.probe()


def test_probe_clip_is_a_real_playable_video(tmp_path):
    try:
        clip = yt.probe_clip(tmp_path / "probe.mp4", seconds=1.0)
    except Exception as exc:                                    # noqa: BLE001
        pytest.skip(f"ffmpeg unavailable: {exc}")
    assert clip.exists() and clip.stat().st_size > 1000
    import subprocess

    import shortlist_reel as reel
    probe = subprocess.run([yt._ffmpeg(), "-i", str(clip)], capture_output=True, text=True).stderr
    assert "Video: h264" in probe and "Audio: aac" in probe
    assert abs(reel._probe(clip, yt._ffmpeg()) - 1.0) < 0.4
