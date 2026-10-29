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


class ReadOnlyAccessTests(unittest.TestCase):
    def test_reports_user_token_grants_and_target_tasks_without_publishing_or_secrets(self):
        replies=iter([{'id':'999'},{'id':'123','name':'PlayReport ZA'},
                      {'data':[{'permission':'pages_manage_posts','status':'granted'}]},
                      {'data':[{'id':'123','tasks':['CREATE_CONTENT']}]}])
        seen=[]
        def get(opener,request):
            self.assertEqual(request.get_method(),'GET')
            self.assertNotIn('access_token',request.full_url)
            seen.append(request.full_url)
            return next(replies)
        with patch.dict(os.environ,{'FACEBOOK_PAGE_ID':'123','FACEBOOK_PAGE_ACCESS_TOKEN':'synthetic'}), \
             patch.object(retry.fb,'_json',side_effect=get),patch.object(retry.fb,'publish') as publish:
            result=retry.check_access()
        publish.assert_not_called()
        self.assertEqual(result['publishing_attempts'],0)
        self.assertFalse(result['token_identity_matches_target_page'])
        self.assertTrue(result['target_in_managed_pages'])
        self.assertEqual(result['target_page_tasks'],['CREATE_CONTENT'])
        self.assertNotIn('synthetic',json.dumps(result))
        self.assertNotIn('999',json.dumps(result))

    def test_page_identity_does_not_try_user_only_endpoints(self):
        with patch.dict(os.environ,{'FACEBOOK_PAGE_ID':'123','FACEBOOK_PAGE_ACCESS_TOKEN':'synthetic'}), \
             patch.object(retry.fb,'_json',side_effect=[{'id':'123'},{'id':'123','name':'Page'}]) as get:
            result=retry.check_access()
        self.assertTrue(result['token_identity_matches_target_page'])
        self.assertEqual(get.call_count,2)


class PageTokenResolutionTests(unittest.TestCase):
    def tearDown(self):
        retry._transient_tokens.clear()

    def test_resolves_only_target_page_and_verifies_derived_identity(self):
        replies=iter([{'id':'999'},{'access_token':'synthetic-page'},{'id':'123'}])
        seen=[]
        def get(opener,request):
            self.assertEqual(request.get_method(),'GET')
            self.assertNotIn('synthetic-',request.full_url)
            seen.append((request.full_url,request.get_header('Authorization')))
            return next(replies)
        with patch.dict(os.environ,{'FACEBOOK_PAGE_ID':'123','FACEBOOK_PAGE_ACCESS_TOKEN':'synthetic-person'}),patch.object(retry.fb,'_json',side_effect=get):
            value,resolved=retry.resolve_target_page_token()
            self.assertEqual(value,'synthetic-page')
            self.assertTrue(resolved)
            self.assertNotIn('synthetic-page',retry.clean('Cannot use synthetic-page'))
        self.assertIn('/123?',seen[1][0])
        self.assertEqual(seen[2][1],'Bearer synthetic-page')

    def test_correct_page_token_needs_no_exchange(self):
        with patch.dict(os.environ,{'FACEBOOK_PAGE_ID':'123','FACEBOOK_PAGE_ACCESS_TOKEN':'synthetic-page'}),patch.object(retry.fb,'_json',return_value={'id':'123'}) as get:
            value,resolved=retry.resolve_target_page_token()
        self.assertFalse(resolved)
        self.assertEqual(get.call_count,1)

    def test_wrong_page_identity_is_rejected(self):
        with patch.dict(os.environ,{'FACEBOOK_PAGE_ID':'123','FACEBOOK_PAGE_ACCESS_TOKEN':'synthetic-person'}),patch.object(retry.fb,'_json',side_effect=[{'id':'999'},{'access_token':'synthetic-page'},{'id':'456'}]):
            with self.assertRaisesRegex(ValueError,'does not identify target Page'):
                retry.resolve_target_page_token()
