"""Static public privacy site: no credentials, sign-in gate or tracking dependencies."""
from html.parser import HTMLParser
from pathlib import Path
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1] / 'docs'


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.tags=[]; self.ids=[]; self.links=[]; self.feed(text)
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs); self.tags.append((tag,attrs))
        if 'id' in attrs:self.ids.append(attrs['id'])
        if tag in ('a','link','img'):self.links.append(attrs.get('href',attrs.get('src','')))


class PrivacySiteTests(unittest.TestCase):
    def test_expected_public_policy_and_homepage(self):
        text=(ROOT/'privacy-policy.html').read_text()
        for value in ('Privacy Policy — Mr 2 Odds','Ndumiso Msani','msanindumiso@gmail.com',
                      'com.playreport.app','2026-10-30','drive.file','Limited Use',
                      'https://perfectndumiso1-netizen.github.io/goals-scanner/privacy-policy.html',
                      'third-party connections','Android backup','18 and over'):
            self.assertIn(value,text)
        self.assertIn('privacy-policy.html',(ROOT/'index.html').read_text())
        self.assertTrue((ROOT/'.nojekyll').is_file())

    def test_local_links_assets_and_fragment_targets_exist(self):
        for name in ('index.html','privacy-policy.html'):
            page=Page((ROOT/name).read_text())
            self.assertEqual(len(page.ids),len(set(page.ids)))
            for href in page.links:
                url=urlsplit(href)
                if url.scheme:
                    self.assertIn(url.scheme,('https','mailto'));continue
                target=ROOT/url.path if url.path else ROOT/name
                if target.is_dir():target=target/'index.html'
                self.assertTrue(target.is_file(),(name,href))
                if url.fragment:
                    self.assertIn(url.fragment,Page(target.read_text()).ids)

    def test_public_site_has_no_active_tracking_or_login_requirements(self):
        for name in ('index.html','privacy-policy.html'):
            text=(ROOT/name).read_text();page=Page(text)
            self.assertNotIn('noindex',text.lower())
            for tag,attrs in page.tags:
                self.assertNotIn(tag,('script','iframe','form','input'))
                self.assertFalse(any(key.startswith('on') for key in attrs))
                if tag=='img' or (tag=='link' and attrs.get('rel')=='stylesheet'):
                    self.assertFalse(urlsplit(attrs.get('src',attrs.get('href',''))).netloc)

    def test_deletion_and_google_access_are_not_overpromised(self):
        text=(ROOT/'privacy-policy.html').read_text()
        self.assertIn('not a complete deletion',text)
        self.assertIn('does not automatically delete files',text)
        self.assertIn('broad permission',text)
        self.assertIn('third-party behavioural analytics SDK',text)
        self.assertIn('aggregated and anonymised',text)


if __name__=='__main__':unittest.main()
