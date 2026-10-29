import json
import os
import unittest
from unittest.mock import patch
from urllib.request import Request

from scripts import retry_facebook_reel as retry


class RetryTests(unittest.TestCase):
    def test_redacts_credentials_and_urls_recursively(self):
        sample_value='synthetic'+'-token'
        with patch.dict(os.environ,{'FACEBOOK_PAGE_ACCESS_TOKEN':sample_value,'GH_READ_TOKEN':'synthetic-github'}):
            safe=retry.clean_json({'error':{'message':f'Cannot use {sample_value} at https://example.invalid/?signature=private'},'other':'synthetic-github'})
        self.assertNotIn(sample_value,safe)
        self.assertNotIn('synthetic-github',safe)
        self.assertNotIn('signature=private',safe)
        self.assertIn('[REDACTED]',safe)
        self.assertIsInstance(json.loads(safe)['error'],dict)

    def test_detects_control_and_transfer_stages_without_logging_request_headers(self):
        req=Request('https://graph.facebook.com/v25.0/123/video_reels',data=b'upload_phase=start',headers={'Authorization':'private'})
        self.assertEqual(retry.stage(req),'start')
        req=Request('https://rupload.facebook.com/video-upload/v25.0/123',data=iter([b'media']))
        self.assertEqual(retry.stage(req),'byte_transfer')
        req=Request('https://graph.facebook.com/v25.0/123?fields=status')
        self.assertEqual(retry.stage(req),'publication_status')

    def test_keeps_codes_and_plain_language_error_without_secret(self):
        with patch.dict(os.environ,{'FACEBOOK_PAGE_ACCESS_TOKEN':'synthetic'}):
            safe=retry.clean_json({'message':'Invalid token synthetic','code':190,'error_subcode':463})
        error=json.loads(safe)
        self.assertEqual(error['code'],190)
        self.assertEqual(error['error_subcode'],463)
        self.assertNotIn('synthetic',error['message'])


if __name__=='__main__':unittest.main()
