import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import zipfile

from scripts import inspect_facebook_recovery as inspect


class InvestigationTests(unittest.TestCase):
    def test_extracts_known_facts_without_copying_credentials_or_urls(self):
        log = '\n'.join([
            'INFO reel built briefing-16x9.mp4 [16:9] (480.2s, 25000 KB) music=track.mp3',
            'INFO reel built briefing-9x16-reel.mp4 [9:16] (480.2s, 26000 KB) music=track.mp3',
            'ERROR Facebook Reel publishing failed for briefing-9x16-reel.mp4: HTTP 400, Graph code 190, subcode 463; check Page access, token expiry, Reel permissions and media limits.',
            'unrelated Authorization: Bearer do-not-copy-this',
            'https://storage.invalid/?signature=do-not-copy-this',
        ])
        facts = inspect.safe_evidence(log)
        self.assertEqual(len(facts), 3)
        self.assertEqual(facts[1]['aspect'], '9:16')
        self.assertEqual(facts[2]['graph_subcode'], 463)
        self.assertNotIn('do-not-copy-this', json.dumps(facts))

    def test_unknown_failure_does_not_echo_unsafe_details(self):
        facts = inspect.safe_evidence('Facebook Reel publishing failed for reel.mp4: secret=do-not-copy-this https://storage.invalid')
        self.assertEqual(len(facts), 1)
        self.assertNotIn('do-not-copy-this', json.dumps(facts))

    def test_local_credential_preflight_is_distinguishable_from_meta_rejection(self):
        facts=inspect.safe_evidence('Facebook Reel publishing failed for reel.mp4: set both FACEBOOK_PAGE_ACCESS_TOKEN and a numeric FACEBOOK_PAGE_ID')
        self.assertIn('no Meta request',facts[0]['reason'])
        self.assertNotIn('http_status',facts[0])

    def test_storage_request_has_no_authorization_header(self):
        calls=[]
        class Opener:
            def open(self,request,**kwargs):
                calls.append(request)
                if len(calls)==1:
                    raise HTTPError(request.full_url,302,'redirect',{'Location':'https://production.blob.core.windows.net/saved?signature=private'},None)
                return io.BytesIO(b'file')
        with tempfile.TemporaryDirectory() as root,patch.object(inspect,'build_opener',return_value=Opener()):
            inspect.github_download('owner/repo','actions/jobs/1/logs',Path(root)/'file','synthetic')
        self.assertEqual(calls[0].get_header('Authorization'),'Bearer synthetic')
        self.assertIsNone(calls[1].get_header('Authorization'))

    def test_unexpected_redirect_host_is_blocked(self):
        class Opener:
            def open(self,request,**kwargs):
                raise HTTPError(request.full_url,302,'redirect',{'Location':'https://other.invalid/file'},None)
        with tempfile.TemporaryDirectory() as root,patch.object(inspect,'build_opener',return_value=Opener()):
            with self.assertRaisesRegex(RuntimeError,'Unexpected GitHub storage host'):
                inspect.github_download('owner/repo','actions/jobs/1/logs',Path(root)/'file','synthetic')

    def test_only_selected_media_and_whitelisted_receipt_fields_are_inspected(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); archive=root/'source.zip'
            with zipfile.ZipFile(archive,'w') as source:
                source.writestr('../../briefing-9x16-reel.mp4',b'media')
                source.writestr('arbitrary.bin',b'ignore')
                source.writestr('reel.mp4.facebook-upload.json',json.dumps({'kind':'facebook_reel_9x16','phase':'transferred','video_id':'123','unexpected_secret':'do-not-copy-this'}))
            with patch.object(inspect,'inspect_video',side_effect=lambda p:{'file':p.name}):
                videos,receipts=inspect.inspect_archive(archive,root)
            self.assertEqual(videos,[{'file':'briefing-9x16-reel.mp4'}])
            self.assertEqual((root/'briefing-9x16-reel.mp4').read_bytes(),b'media')
            self.assertNotIn('do-not-copy-this',json.dumps(receipts))


if __name__=='__main__':
    unittest.main()
