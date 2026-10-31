"""Mr 2 Odds is a presentation change, not a new app, model or publishing policy."""
from datetime import datetime
from pathlib import Path
import ast
import hashlib
import json
import re
import xml.etree.ElementTree as ET

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT/'android/app/src/main'
WWW = MAIN/'assets/www'


def test_app_identity_and_saved_records_survive_rebrand():
    gradle = (ROOT/'android/app/build.gradle.kts').read_text()
    assert 'applicationId = "com.playreport.app"' in gradle
    assert 'namespace = "com.playreport.app"' in gradle
    version = re.search(r'val appVersionName = .*?\?: "(\d+\.\d+\.\d+)"', gradle).group(1)
    assert tuple(map(int, version.split('.'))) >= (1, 6, 85)
    core = (WWW/'core.js').read_text()
    for key in ('pr_settings','pr_favs_full','pr_nav','pr_latest','pr_d:'):
        assert key in core
    slip = (WWW/'slip.js').read_text()
    assert "'pr_tickets'" in slip and "'pr_slip'" in slip
    assert 'm.playreport' in (WWW/'export.js').read_text()


def test_public_app_brand_and_theme_references_are_consistent():
    names = ET.parse(MAIN/'res/values/strings.xml').getroot()
    assert names.find("string[@name='app_name']").text == 'Mr 2 Odds'
    assert '<title>Mr 2 Odds</title>' in (WWW/'index.html').read_text()
    assert 'Theme.Mr2Odds' in (MAIN/'AndroidManifest.xml').read_text()
    assert 'name="Theme.Mr2Odds"' in (MAIN/'res/values/themes.xml').read_text()
    for path in WWW.glob('*'):
        if path.suffix not in ('.js','.html','.css') or path.name=='marked.min.js':continue
        for line in path.read_text().splitlines():
            # These are display aliases for older reports/release notes, not old brand copy.
            if 'PlayReport' in line:assert '.replace(/PlayReport' in line, (path,line)
    for name in ('CheckWorker.kt','Notifier.kt'):
        assert 'Mr 2 Odds' in (MAIN/'java/com/playreport/app'/name).read_text()


def test_selected_logo_exports_are_identical_and_square():
    from scripts.build_brand_assets import artwork
    selected = artwork().resize((512,512),Image.Resampling.LANCZOS)
    paths = [ROOT/'assets/reel/logo.png',WWW/'logo.png',MAIN/'res/drawable-nodpi/splash_logo.png']
    assert len({p.read_bytes() for p in paths})==1
    for path in paths:
        image = Image.open(path).convert('RGBA')
        assert image.size==(512,512) and ImageChops.difference(image,selected).getbbox() is None
        assert image.getpixel((0,0))[3]==0
    assert (WWW/'editor.jpg').is_file() and (WWW/'editor_sq.jpg').is_file()


def test_android_icons_use_new_art_with_adaptive_padding_and_themed_mask():
    for density,scale in (('mdpi',1),('hdpi',1.5),('xhdpi',2),('xxhdpi',3),('xxxhdpi',4)):
        folder = MAIN/'res'/f'mipmap-{density}'
        image = Image.open(folder/'ic_launcher_foreground.png').convert('RGBA')
        assert image.size==(round(108*scale),)*2
        assert image.getpixel((0,0))[3]==0
        assert image.getpixel((image.width//2,image.height//2))[3]==255
        assert Image.open(folder/'ic_launcher.png').size==(round(48*scale),)*2
    themed=Image.open(MAIN/'res/drawable-nodpi/ic_launcher_monochrome.png').convert('RGBA')
    assert themed.size==(432,432) and themed.getpixel((0,0))[3]==0
    assert themed.getchannel('A').getextrema()==(0,255)
    assert not (MAIN/'res/drawable/ic_launcher_monochrome.xml').exists()


def test_video_report_copy_is_new_brand_without_changing_legacy_data_keys():
    for name in ('shortlist_reel.py','match_breakdown.py','breakdown_script.py','scanner.py','pdfgen.py','youtube_post.py','facebook_post.py'):
        tree=ast.parse((ROOT/name).read_text())
        strings=[node.value for node in ast.walk(tree) if isinstance(node,ast.Constant) and isinstance(node.value,str)]
        assert any('Mr 2 Odds' in value for value in strings)
        assert not any('PlayReport' in value for value in strings)
    import sheet_model
    assert '"playreport": _pr_p' in (ROOT/'sheet_model.py').read_text()


def test_rebrand_does_not_insert_brand_into_exact_facebook_caption_or_cover():
    from facebook_captions import reel_caption
    from facebook_cover import match_rows
    assert reel_caption(now=datetime(2026,10,30)).startswith("Today's Football Predictions\n30 October 2026\n\n#FootballPredictions")
    assert 'Mr 2 Odds' not in reel_caption()
    assert match_rows([{'home':'Alpha','away':'Beta','brand':'Mr 2 Odds','odds':1.8,'sel':'O15'}])==[{'home':'Alpha','away':'Beta'}]
    cfg=json.loads((ROOT/'config/facebook-feed.json').read_text())
    assert set(cfg['authorized_kinds'])=={'editorial','results'}
    assert not cfg['app_scores']['rights_confirmed'] and not cfg['app_scores']['coverage_verified']


def test_release_filename_version_and_upgrade_safeguards():
    wf=(ROOT/'.github/workflows/build-app.yml').read_text()
    gradle = (ROOT/'android/app/build.gradle.kts').read_text()
    version = re.search(r'val appVersionName = .*?\?: "(\d+\.\d+\.\d+)"', gradle).group(1)
    assert f'APP_VERSION_NAME: "{version}"' in wf
    assert f"grep 'versionName={version}'" in wf
    assert f'Mr 2 Odds {version}' in (ROOT/'android/RELEASE_NOTES.md').read_text()
    assert '--title "Mr 2 Odds v${APP_VERSION_NAME}"' in wf
    assert 'Mr2Odds-${APP_VERSION_NAME}.apk' in wf
    for check in ('signing-key-continuity','increasing-version-code','adb install -r','apksigner','zipalign','com.playreport.app'):
        assert check in wf
    assert 'PlayReport.apk' not in wf


def test_music_schedule_and_model_files_remain_identical_to_before_rebrand():
    pins=json.loads((ROOT/'tests/fixtures/facebook-feed-reel-invariants.json').read_text())
    for name in ('.github/workflows/scan.yml','music.py','reel_insights.py','reel_verify.py','assets/reel/under_the_stadium_lights.mp3'):
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==pins[name]


def test_legacy_render_and_briefing_environment_keys_are_preserved(monkeypatch,tmp_path):
    import shortlist_reel
    marker=tmp_path/'app'/'days';marker.mkdir(parents=True)
    monkeypatch.setenv('PLAYREPORT_DATA_DIR',str(tmp_path))
    assert shortlist_reel._data_dir('days')==marker
    assert 'os.getenv("PLAYREPORT_BRIEFING_VIDEO")' in (ROOT/'scanner.py').read_text()
    for name in ('scanner.py','shortlist_reel.py'):
        assert 'MR 2 ODDS_' not in (ROOT/name).read_text()


def test_new_brand_keeps_original_silent_slide_timing():
    import shortlist_reel as reel
    import match_breakdown as breakdown
    import music
    for index,text in ((0,reel.INTRO_SCRIPT),(1,reel.CLOSER_SCRIPT)):
        old=text.replace('Mr 2 Odds','PlayReport')
        before=reel.frame_hold(reel.hold_seconds(index,music.reading_seconds(old)))
        after=reel.frame_hold(reel.hold_seconds(index,reel.script_reading_seconds(text)))
        assert before==after
    assert breakdown._holds([{'text':'Welcome back to Mr 2 Odds.'}])==breakdown._holds([{'text':'Welcome back to PlayReport.'}])
    assert ".replace(/Mr 2 Odds/g, 'Mr2Odds').trim().split" in (WWW/'pages.js').read_text()
