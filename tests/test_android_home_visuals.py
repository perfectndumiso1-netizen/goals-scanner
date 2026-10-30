"""Run dependency-free Home UI collection regressions in the existing Python CI."""
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_home_visual_collection_regressions():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js required for bundled Home collection tests')
    result = subprocess.run([node, '--test', 'android/home_visual_test.cjs'], cwd=ROOT,
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_home_visual_assets_are_local_and_narrow_screen_rules_are_present():
    css = (ROOT / 'android/app/src/main/assets/www/app.css').read_text().split('/* Home 1.6.87', 1)[1]
    assert 'https://' not in css and '@import' not in css and 'url(' not in css
    assert 'prefers-reduced-motion' in (ROOT / 'android/app/src/main/assets/www/app.css').read_text()
    assert '@media (max-width:480px)' in css
    assert '.home-quick:focus-visible' in css
    source = (ROOT / 'android/app/src/main/assets/www/views.js').read_text()
    assert "if (state.homeTab !== 'eighty') parts.push(strongMarketsCard(d))" in source
    assert "favs.length && state.homeTab !== 'eighty'" in source
