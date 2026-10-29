"""Public copy, picture-first community posts and conservative visibility reporting."""
import json
from types import SimpleNamespace
from urllib.parse import parse_qs
import pytest
from facebook_feed import content,graphics,publisher
from facebook_captions import reel_caption
from test_facebook_feed import NOW,ROOT,source,Response


def test_feed_captions_and_graphics_have_no_brand_or_source_boilerplate(tmp_path):
    from facebook_feed.cli import config
    root=source(tmp_path);items=content.verified_fixtures(root,NOW,config(ROOT/'config/facebook-feed.json'))
    for post in [content.community(items,[],NOW,[]),content.match_card(items,NOW),content.weekly(items,root,NOW)]:
        public=json.dumps({'caption':post['caption'],'graphic':post['graphic']}).lower()
        assert 'playreport' not in public and 'source:' not in public and 'livescore' not in public
        assert 'scope' in json.dumps(post) or post.get('teams')
        assert post['graphic'] and post.get('source')  # Evidence stays internal.
        path=graphics.render(post['graphic'],tmp_path/(post['kind']+'.jpg'))
        from PIL import Image
        assert Image.open(path).size==(1080,1350)


def test_review_picture_keeps_losses_pending_and_real_denominator(tmp_path):
    book=[dict(kind='advisor',match_date='2026-10-28',country='England',home=str(i),away='A',sel='O15',status=s)
          for i,s in enumerate(['hit','miss','pending','void'])]
    post=content.community([],book,NOW,[])
    assert '1 won, 1 lost' in post['caption'] and '50.0%' in post['caption']
    assert '1 pending' in post['caption'] and '1 void' in post['caption']
    assert post['graphic'] and 'PlayReport' not in post['caption']
    graphics.render(post['graphic'],tmp_path/'review.jpg')


def test_reel_caption_is_natural_but_retains_count_record_and_safety():
    original='🎬 PlayReport 16:9 widescreen shortlist — Thu 29 Oct. Yesterday (all videos): 3/5 won · Today: 6 selection(s). A shortlist for your review, not an instruction to bet. 18+.'
    result=reel_caption(original)
    assert '6 picks' in result and '3 won, 2 lost' in result and 'Thu 29 Oct' in result and '18+' in result
    assert all(word not in result.lower() for word in ('playreport','16:9','selection(s)','source:'))
    assert 'Yesterday' not in reel_caption(original.replace('Yesterday (all videos): 3/5 won · ',''))
    assert original.startswith('🎬 PlayReport')  # Original caller/Telegram copy is untouched.


def test_nonstandard_reel_caption_does_not_destroy_factual_lines():
    result=reel_caption('PlayReport ZA\nHome 2–1 Away · FT\nSource: archive')
    assert result=='Home 2–1 Away · FT'


@pytest.mark.parametrize('privacy,hidden,restriction',[('EVERYONE',False,False),('SELF',False,True),('EVERYONE',True,True),(None,None,False)])
def test_owner_token_read_never_claims_public_visibility(monkeypatch,privacy,hidden,restriction):
    monkeypatch.setenv('FACEBOOK_PAGE_ID','123');monkeypatch.setenv('FACEBOOK_PAGE_ACCESS_TOKEN','synthetic')
    values=[{'id':'123'},{'id':'123_456','is_published':True,'is_hidden':hidden,'privacy':{'value':privacy},'application':{'name':'Example app'}}];calls=[]
    def open(request,**kw):calls.append(request);return Response(values.pop(0))
    client=publisher.PageFeed(SimpleNamespace(open=open));report=client.inspect_visibility('123_456')
    assert report['restriction_detected']==restriction
    assert report['public_visibility_verified'] is False
    assert all(c.get_method()=='GET' for c in calls)


def test_text_publish_explicitly_sets_published_true(monkeypatch):
    monkeypatch.setenv('FACEBOOK_PAGE_ID','123');monkeypatch.setenv('FACEBOOK_PAGE_ACCESS_TOKEN','synthetic')
    values=[{'id':'123'},{'id':'123_456'}];calls=[]
    def open(request,**kw):calls.append(request);return Response(values.pop(0))
    client=publisher.PageFeed(SimpleNamespace(open=open));assert client.send({'caption':'Match thoughts'})=='123_456'
    assert parse_qs(calls[-1].data.decode())['published']==['true']


def test_community_photo_dependency_and_diagnostic_are_safe():
    import yaml
    engine=yaml.safe_load((ROOT/'.github/workflows/facebook-feed-run.yml').read_text())
    install=next(s for s in engine['jobs']['feed']['steps'] if 'graphics dependency' in s.get('name',''))
    assert "inputs.kind == 'community'" in install['if']
    script=(ROOT/'scripts/check_facebook_visibility.py').read_text()
    assert '.send(' not in script and '.inspect_visibility(' in script
    assert 'FACEBOOK_FEED_PUBLISH' not in (ROOT/'.github/workflows/facebook-visibility.yml').read_text()


def test_reel_delivery_uses_new_caption_without_changing_telegram_or_media(monkeypatch,tmp_path):
    import scanner
    original='🎬 PlayReport 16:9 widescreen shortlist — Thu 29 Oct. Today: 5 selection(s). 18+.'
    landscape=tmp_path/'landscape.mp4';landscape.write_bytes(b'landscape')
    portrait=tmp_path/'portrait.mp4';portrait.write_bytes(b'portrait');seen={}
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','synthetic');monkeypatch.setenv('TELEGRAM_CHAT_ID','123')
    monkeypatch.setattr(scanner.facebook_mod,'requested',lambda:True)
    def publish(path,caption):
        seen['facebook']=(path,caption)
        return scanner.facebook_mod.UploadResult('uploaded','456')
    monkeypatch.setattr(scanner.facebook_mod,'publish',publish)
    def send(url,**kwargs):seen['telegram']=kwargs['data']['caption'];return SimpleNamespace(status_code=200,text='')
    monkeypatch.setattr(scanner.SESSION,'post',send)
    assert scanner.send_telegram_video(landscape,original,width=1920,height=1080,facebook_path=portrait,delete_after=False)
    assert seen['facebook'][0]==portrait and '5 picks' in seen['facebook'][1]
    assert 'PlayReport' not in seen['facebook'][1] and seen['telegram']==original
    assert landscape.read_bytes()==b'landscape' and portrait.read_bytes()==b'portrait'
