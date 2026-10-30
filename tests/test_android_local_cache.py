"""Cache regression entrypoint for the existing Python test workflow; no workflow changes.

Host SQLite checks SQL/schema contracts only, NOT Android instrumentation.
"""
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
WWW = ROOT / 'android/app/src/main/assets/www'
JAVA = ROOT / 'android/app/src/main/java/com/playreport/app'


def test_cache_repository_regressions():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js required for bundled WebView repository tests')
    result = subprocess.run([node, '--test', 'android/cache_test.cjs'], cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name', ['resource-cache.js', 'core.js', 'app.js', 'leagues.js', 'pages.js', 'views.js'])
def test_updated_webview_scripts_parse(name):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js unavailable')
    result = subprocess.run([node, '--check', str(WWW / name)], text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_sqlite_schema_retains_one_atomic_resource_and_validator_metadata():
    source = (JAVA / 'JsonCache.kt').read_text()
    db = sqlite3.connect(':memory:')
    for sql in re.findall(r'db.execSQL\("(CREATE TABLE [^"]+)"\)', source):
        db.execute(sql)
    row = ('url', '{"fixtures":[{"id":"unchanged"}]}', 'etag', 'last-modified', 100, 50, '2026-10-30', 32)
    db.execute('INSERT INTO resources VALUES (?,?,?,?,?,?,?,?)', row)
    db.execute('UPDATE resources SET checked=? WHERE url=?', (200, 'url'))
    # A 304 updates freshness only: original payload and its change timestamp survive.
    assert db.execute('SELECT body,etag,checked,updated FROM resources').fetchone() == (row[1], 'etag', 200, 50)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO resources VALUES (?,?,?,?,?,?,?,?)', row)
    db.close()


def test_cache_bridge_is_async_and_preferences_and_package_identity_are_not_migrated():
    source = (JAVA / 'MainActivity.kt').read_text()
    for method in ('cacheRead', 'cacheWrite', 'cacheTouch', 'cacheClear', 'cacheFailure', 'fetchConditional'):
        body = source.split('fun ' + method + '(', 1)[1].split('@JavascriptInterface', 1)[0]
        assert 'pool.execute' in body
    gradle = (ROOT / 'android/app/build.gradle.kts').read_text()
    assert 'applicationId = "com.playreport.app"' in gradle
    assert 'firebase' not in gradle.lower() and 'supabase' not in gradle.lower()
    core = (WWW / 'core.js').read_text()
    assert "key: (k) => 'pr_d:' + k" in core
    assert "k.startsWith('pr_d:')" in core  # pruning/size/clear target the active namespace.
    assert 'playreport-check' in source  # preserve the unique existing worker identifier.
    assert 'NetworkType.CONNECTED' in source


def test_http_conditional_get_and_durable_worker_share_existing_backend():
    net = (JAVA / 'Net.kt').read_text()
    worker = (JAVA / 'CheckWorker.kt').read_text()
    sync = (JAVA / 'PublishedSync.kt').read_text()
    assert 'If-None-Match' in net and 'If-Modified-Since' in net and 'Retry-After' in net
    assert 'ConcurrentHashMap' in net and 'CompletableFuture' in net
    assert 'PublishedSync.heartbeat(ctx)' in worker and 'PublishedSync.refresh(ctx, meta)' in worker
    assert 'JsonCache.shared(context)' in sync and 'Net.LATEST_JSON' in sync
    assert 'cache_sync_after' in sync and 'cache_meta_after' in sync
    cache = (JAVA / 'JsonCache.kt').read_text()
    assert 'beginTransaction()' in cache and 'setTransactionSuccessful()' in cache
    assert 'expectedEpoch != epoch()' in cache  # late writes cannot restore cleared data.
    assert '32L * 1024 * 1024' in cache and '8 * 1024 * 1024' in cache
