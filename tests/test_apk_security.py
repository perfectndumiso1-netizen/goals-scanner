"""Guards on the shipped Android shell, so a Play Protect problem cannot come back unnoticed.

These run in the normal test job on every push. They check the properties Play Protect actually judges and
that a careless edit would silently undo: the requested permissions, the SDK level the APK is built against,
the toolchain that supports it, and the three places where an allowlist or a digest check protects the app
(the WebView bridge, the HTTP helper, the updater).

They are string-level checks on purpose: the APK is built in a separate job, and the point is to fail fast,
before a build runs, with a message that says what was removed and why it matters.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android"
MAIN = ANDROID / "app" / "src" / "main"
JAVA = MAIN / "java" / "com" / "playreport" / "app"
WWW = MAIN / "assets" / "www"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ------------------------------------------------------------------ permissions and manifest
def test_no_install_packages_permission():
    """REQUEST_INSTALL_PACKAGES is what makes Play Protect see an app as an installer.

    Google's fraud pilot blocks Internet-sideloaded apps that declare it, and it is the loudest "can install
    other apps" signal to a user. The app only ever hands an APK to the system installer, which does not need
    this permission — so its return should be a deliberate decision, not an accident.
    """
    manifest = read(MAIN / "AndroidManifest.xml")
    assert "REQUEST_INSTALL_PACKAGES" not in manifest.replace("No REQUEST_INSTALL_PACKAGES", "")
    assert "INSTALL_PACKAGES" not in re.sub(r"<!--.*?-->", "", manifest, flags=re.S)


def test_manifest_keeps_the_expected_surface():
    manifest = read(MAIN / "AndroidManifest.xml")
    assert 'android:usesCleartextTraffic="false"' in manifest, "plaintext HTTP must stay off"
    assert 'android:exported="false"' in manifest, "the FileProvider must not be exported"
    assert 'android:allowBackup="true"' in manifest
    assert 'android:fullBackupContent="@xml/backup_rules"' in manifest
    assert 'android:dataExtractionRules="@xml/data_extraction_rules"' in manifest
    # one activity, no exported receivers or services
    assert manifest.count("<activity") == 1
    assert "<receiver" not in manifest and "<service" not in manifest


def test_backup_rules_cover_only_app_preferences():
    """One include is the whole rule: naming what to back up excludes the rest. What matters is that the
    scope never widens — an app that ships its cached data (and a downloaded APK) into a cloud backup is a
    privacy problem, not a convenience."""
    for name in ("backup_rules.xml", "data_extraction_rules.xml"):
        body = read(MAIN / "res" / "xml" / name)
        assert '<include domain="sharedpref" path="." />' in body, f"{name} must include the app's own preferences"
        for wide in ('domain="file"', 'domain="database"', 'domain="external"', 'domain="root"'):
            assert wide not in body, f"{name} must not widen the backup scope to {wide}"
        # an exclude of a path that is not included is dead weight and a lint error
        assert "<exclude" not in body, f"{name} should express its scope with includes only"


# ------------------------------------------------------------------ the SDK level Play Protect judges
def _gradle_version(text: str, key: str) -> int:
    m = re.search(rf"{key}\s*=\s*(\d+)", text)
    assert m, f"{key} not found in app/build.gradle.kts"
    return int(m.group(1))


def test_targets_a_current_sdk_level():
    """Play Protect warns when an app is built more than one SDK generation behind the device, and Google's
    own developer guidance ties that to the "built for an older version of Android" dialog."""
    gradle = read(ANDROID / "app" / "build.gradle.kts")
    assert _gradle_version(gradle, "compileSdk") >= 36, "compile against API 36 (Android 16) at least"
    assert _gradle_version(gradle, "targetSdk") >= 36, "target API 36 at least"


def test_toolchain_supports_that_sdk_level():
    """compileSdk 36 needs AGP 8.9.1+ and Gradle 8.11.1+; a silent downgrade breaks the build, not the app."""
    agp = re.search(r'com\.android\.application"\)\s*version\s*"([\d.]+)"', read(ANDROID / "build.gradle.kts"))
    assert agp, "AGP version not found"
    parts = [int(x) for x in agp.group(1).split(".")]
    assert tuple(parts) >= (8, 9, 1), f"AGP {agp.group(1)} cannot compile API 36"
    workflow = read(ROOT / ".github" / "workflows" / "build-app.yml")
    g = re.search(r'gradle-version:\s*"([\d.]+)"', workflow)
    assert g, "Gradle version not pinned in the workflow"
    assert tuple(int(x) for x in g.group(1).split(".")) >= (8, 11, 1), f"Gradle {g.group(1)} is too old for AGP 8.9.1"
    assert "testDebugUnitTest" in workflow, "the native security tests must run before the APK is published"


def test_lint_errors_block_a_release():
    gradle = read(ANDROID / "app" / "build.gradle.kts")
    assert "abortOnError = true" in gradle


# ------------------------------------------------------------------ the WebView bridge allowlist
def test_bridge_fetch_is_allowlisted():
    activity = read(JAVA / "MainActivity.kt")
    fetch = activity[activity.index("fun fetch(id: Int"):]
    fetch = fetch[: fetch.index("fun refreshDone")] if "fun refreshDone" in fetch else fetch
    assert "Security.webAllowed(url)" in fetch, "the bridge must refuse hosts outside the allowlist"
    assert "blocked host" in fetch, "a refused request must come back as an error, not a silent empty reply"


def test_webview_is_locked_down():
    activity = read(JAVA / "MainActivity.kt")
    for setting in ("allowFileAccess = false", "allowContentAccess = false",
                    "allowFileAccessFromFileURLs = false", "allowUniversalAccessFromFileURLs = false",
                    "javaScriptCanOpenWindowsAutomatically = false", "setSupportMultipleWindows(false)",
                    "MIXED_CONTENT_NEVER_ALLOW"):
        assert setting in activity, f"WebView hardening lost: {setting}"


def test_external_links_are_https_only():
    activity = read(JAVA / "MainActivity.kt")
    open_external = activity[activity.index("private fun openExternal"):]
    assert 'uri.scheme.equals("https"' in open_external, "only https may be handed to another app"


def test_http_helper_allowlists_every_request_and_redirect():
    net = read(JAVA / "Net.kt")
    assert "if (!Security.nativeAllowed(url)) return Response(0" in net, "get() must be allowlisted"
    assert "if (!Security.nativeAllowed(url)) return false" in net, "download() must be allowlisted"
    redirect = net[net.index("while (conn.responseCode in 300..399"):]
    assert "Security.nativeAllowed(loc)" in redirect, "the redirect target must be allowlisted too"


def test_updater_verifies_the_download_and_lets_android_install():
    updater = read(JAVA / "Updater.kt")
    # the digest must be COMPARED, not merely mentioned: the file is deleted when it does not match
    assert "digest.equals(Security.sha256(f)" in updater, "the download must be compared with the published SHA-256"
    assert "f.delete()" in updater, "an APK that fails the digest check must be deleted"
    assert "Intent.ACTION_VIEW" in updater, "the system installer is the only installer"
    assert 'application/vnd.android.package-archive' in updater
    assert "FLAG_GRANT_READ_URI_PERMISSION" in updater
    assert "PackageInstaller" not in updater.replace("no PackageInstaller session", "")


# ------------------------------------------------------------------ the page and the shell must agree
def test_page_and_shell_share_one_host_list():
    """The two lists live in different languages; if they drift, a feature breaks in a way that looks like a
    network error. Compare them literally."""
    security = read(JAVA / "Security.kt")
    block = security[security.index("val WEB_HOSTS"):security.index("val NATIVE_HOSTS")]
    kotlin_hosts = sorted(set(re.findall(r'"([a-z0-9.-]+\.[a-z]{2,})"', block)))

    core = read(WWW / "core.js")
    js_block = core[core.index("const API_HOSTS"):]
    js_block = js_block[: js_block.index("];")]
    js_hosts = sorted(set(re.findall(r"'([a-z0-9.-]+\.[a-z]{2,})'", js_block)))

    assert kotlin_hosts == js_hosts, f"host lists differ: shell {kotlin_hosts} vs page {js_hosts}"
    assert kotlin_hosts, "the allowlist must not be empty"


def test_page_refuses_off_list_urls():
    core = read(WWW / "core.js")
    assert "function hostAllowed(url)" in core, "the page needs its own host check"
    assert re.search(r"if\s*\(!hostAllowed\(url\)\)\s*throw", core), "getJson must actually refuse an off-list host"
    assert "u.port === '443'" in core or 'u.port === "443"' in core, "the page guard must refuse a non-standard port too"


def test_the_app_never_claims_to_install_by_itself():
    """The notification and settings copy both used to promise a silent install. Say what actually happens:
    the download is verified and Android asks."""
    notifier = read(JAVA / "Notifier.kt")
    assert "download and install" not in notifier, "the copy must not promise an automatic install"
    settings = read(WWW / "pages.js")
    assert re.search(r"Android (then )?asks", settings), "settings must say the install is Android's confirmation"
