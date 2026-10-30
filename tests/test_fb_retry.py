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


class ExistingReelStatusTests(unittest.TestCase):
    def test_poll_existing_id_does_not_upload_again(self):
        from pathlib import Path
        receipt={'kind':retry.fb.KIND,'page_id':'123','video_id':'456','phase':'finishing'}
        statuses=iter([{'status':{'video_status':'processing','publishing_phase':{'status':'not_started'}}},
                       {'status':{'video_status':'ready','publishing_phase':{'status':'complete'}}}])
        def get(opener,request):
            self.assertEqual(request.get_method(),'GET')
            self.assertIn('/456?',request.full_url)
            return next(statuses)
        with patch.dict(os.environ,{'FACEBOOK_PAGE_ID':'123'}),patch.object(Path,'read_text',return_value=json.dumps(receipt)), \
             patch.object(Path,'write_text') as write,patch.object(retry,'resolve_target_page_token',return_value=('synthetic',True)), \
             patch.object(retry.fb,'_json',side_effect=get),patch.object(retry.time,'sleep'),patch.object(retry.fb,'publish') as publish:
            report=retry.check_existing_publication({'artifact_id':'789'},attempts=2,interval=0)
        publish.assert_not_called()
        self.assertEqual(report['status'],'uploaded')
        self.assertEqual(report['publishing_attempts'],0)
        self.assertEqual(json.loads(write.call_args.args[0])['phase'],'published')

    def test_pending_is_not_claimed_as_published(self):
        from pathlib import Path
        receipt={'kind':retry.fb.KIND,'page_id':'123','video_id':'456','phase':'finishing'}
        with patch.dict(os.environ,{'FACEBOOK_PAGE_ID':'123'}),patch.object(Path,'read_text',return_value=json.dumps(receipt)), \
             patch.object(Path,'write_text') as write,patch.object(retry,'resolve_target_page_token',return_value=('synthetic',True)), \
             patch.object(retry.fb,'_json',return_value={'status':{'video_status':'processing'}}):
            report=retry.check_existing_publication({'artifact_id':'789'},attempts=1)
        self.assertEqual(report['status'],'pending')
        write.assert_not_called()

    def test_mismatched_page_prevents_any_network_request(self):
        from pathlib import Path
        receipt={'kind':retry.fb.KIND,'page_id':'999','video_id':'456'}
        with patch.dict(os.environ,{'FACEBOOK_PAGE_ID':'123'}),patch.object(Path,'read_text',return_value=json.dumps(receipt)), \
             patch.object(retry,'resolve_target_page_token') as resolve:
            report=retry.check_existing_publication({'artifact_id':'789'})
        self.assertEqual(report['status'],'failed')
        resolve.assert_not_called()


class RetainedPortraitTests(unittest.TestCase):
    def test_hash_named_portrait_keeps_matching_native_receipt_and_cover(self):
        import tempfile,hashlib,zipfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder);body=b'original retained portrait'
            name='briefing-9x16-reel-'+hashlib.sha256(body).hexdigest()[:20]+'.mp4'
            archive=work/'source.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('recovery/'+name,body)
                z.writestr('recovery/'+name+'.facebook-upload.json','{"video_id":"123"}')
                z.writestr('recovery/'+Path(name).with_suffix('.cover.jpg').name,b'original cover')
                z.writestr('briefing-16x9.mp4',b'not the portrait')
            video=retry.extract_portrait(archive,work)
            self.assertEqual(video.read_bytes(),body)
            self.assertEqual(json.loads(retry.fb._receipt(video).read_text())['video_id'],'123')
            self.assertEqual(video.with_suffix('.cover.jpg').read_bytes(),b'original cover')

    def test_original_filename_still_works(self):
        import tempfile,zipfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder);archive=work/'source.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('deep/briefing-9x16-reel.mp4',b'original')
            self.assertEqual(retry.extract_portrait(archive,work).read_bytes(),b'original')

    def test_digest_mismatch_landscape_only_and_ambiguous_files_fail_closed(self):
        import tempfile,zipfile
        from pathlib import Path
        cases=[['briefing-9x16-reel-'+'0'*20+'.mp4'],['briefing-16x9.mp4'],
               ['a/briefing-9x16-reel.mp4','b/briefing-9x16-reel.mp4']]
        for names in cases:
            with self.subTest(names=names),tempfile.TemporaryDirectory() as folder:
                work=Path(folder);archive=work/'source.zip'
                with zipfile.ZipFile(archive,'w') as z:
                    for name in names:z.writestr(name,b'body')
                with self.assertRaises(ValueError):retry.extract_portrait(archive,work)


class PublishRequestSafetyTests(unittest.TestCase):
    def test_today_exact_caption_allowed_but_stale_expired_and_other_actions_rejected(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from facebook_captions import reel_caption
        now=datetime(2026,10,30,12,tzinfo=ZoneInfo('Africa/Johannesburg'))
        valid={'action':'publish','video_date':'2026-10-30','expires_at':'2026-10-30T16:00:00+02:00','caption':reel_caption(now=now)}
        retry.validate_publish_request(valid,now)
        for changes in ({'video_date':'2026-10-29'},{'expires_at':'2026-10-30T11:00:00+02:00'},
                        {'expires_at':'2026-10-30T16:00:00'},{'caption':'old caption'}, {'action':'unknown'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):retry.validate_publish_request({**valid,**changes},now)

    def test_saved_invalid_session_is_not_silently_discarded(self):
        from pathlib import Path
        source=Path('scripts/retry_facebook_reel.py').read_text()
        self.assertIn('if fb._receipt(video).exists() and not fb._read_receipt(video)',source)
        self.assertNotIn('send_telegram',source)
