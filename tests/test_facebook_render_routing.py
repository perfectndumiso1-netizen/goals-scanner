"""Daily renderer keeps Telegram landscape and builds a separate Facebook portrait cut."""
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import advisor_tracking
import scanner


@pytest.mark.parametrize('portrait_failure',[False,True])
def test_daily_renderer_routes_portrait_without_blocking_telegram(monkeypatch,tmp_path,portrait_failure):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','fake-tg');monkeypatch.setenv('TELEGRAM_CHAT_ID','123')
    monkeypatch.setenv('FACEBOOK_PAGE_ID','123');monkeypatch.setenv('FACEBOOK_PAGE_ACCESS_TOKEN','fake')
    monkeypatch.setenv('TMPDIR',str(tmp_path));monkeypatch.setattr(scanner,'ROOT',tmp_path)
    assets=tmp_path/'assets'/'reel';assets.mkdir(parents=True);(assets/'logo.png').write_bytes(b'logo')
    app=tmp_path/'latest.json';app.write_text(json.dumps({'meta':{'generated':'2026-10-28 08:00'},'fixtures':[]}))
    monkeypatch.setattr(scanner,'APP_FILE',app);monkeypatch.setattr(scanner,'DATA_DIR',tmp_path/'data')
    state={};monkeypatch.setattr(scanner,'_telegram_state',lambda now:(tmp_path/'state.json',state))
    monkeypatch.setattr(scanner,'yt_mod',None);monkeypatch.setattr(scanner,'drive_mod',None)
    picks=[{'home':f'H{i}','away':f'A{i}','sel':'O15','odds':1.2} for i in range(5)]
    monkeypatch.setattr(advisor_tracking,'selections',lambda payload:picks)
    built=[]
    def build(card,out,**kwargs):
        built.append((list(card),out,kwargs))
        if kwargs.get('aspect')=='9:16' and portrait_failure:
            raise RuntimeError('render error')
        out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(b'video')
        kwargs['work'].mkdir(parents=True,exist_ok=True)
        (kwargs['work']/'build_meta.json').write_text(json.dumps({'picks':card}))
    monkeypatch.setattr(scanner,'reel_mod',SimpleNamespace(build=build,video_picks=lambda *a,**k:(picks,[]),reel_results=lambda _:[]))
    sent=[]
    monkeypatch.setattr(scanner,'send_telegram_video',lambda path,caption,**kw:(sent.append((path,kw)) or True))
    scanner.maybe_send_daily_reel({},datetime(2026,10,28,8,0))
    assert len(built)==2 and built[0][0]==built[1][0]==picks
    assert built[0][2].get('aspect','16:9')=='16:9' and built[1][2]['aspect']=='9:16'
    assert len(sent)==1 and (sent[0][1]['width'],sent[0][1]['height'])==(1920,1080)
    assert sent[0][1]['facebook_path']==built[1][1]
    assert sent[0][0]==built[0][1]
    assert built[1][1].exists() is not portrait_failure
