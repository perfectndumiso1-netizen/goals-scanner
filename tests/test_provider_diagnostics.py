"""No real key/account/network: provider rejection reporting must not leak raw values."""
from types import SimpleNamespace
from email.utils import format_datetime
from datetime import timezone
import pytest
from facebook_feed import provider
from test_facebook_feed import NOW, Response, cfg


@pytest.mark.parametrize('key,category',[
    ('token','credentials/account'),('api_key','credentials/account'),('ip','IP access'),
    ('requests','allowance/rate limit'),('rateLimit','allowance/rate limit'),
    ('plan','plan/season'),('season','plan/season'),('parameters','parameters'),
    ('unknown-sensitive-key','unclassified'),
])
def test_error_categories_never_include_provider_details(key,category):
    reason=provider.safe_error_reason({key:'sensitive-body https://example.invalid/private'},'status')
    assert category in reason and 'at status' in reason
    assert 'sensitive-body' not in reason and 'example.invalid' not in reason
    if key=='unknown-sensitive-key':
        assert key not in reason


@pytest.mark.parametrize('errors',[['sensitive-body'],'sensitive-body',True])
def test_unexpected_error_shapes_are_not_echoed(errors):
    reason=provider.safe_error_reason(errors,'sensitive-endpoint')
    assert 'unclassified' in reason and 'at provider endpoint' in reason
    assert 'sensitive-body' not in reason and 'sensitive-endpoint' not in reason


def test_http_success_with_auth_error_remains_failure(monkeypatch,cfg):
    monkeypatch.setenv('API_FOOTBALL_KEY','synthetic-test-only')
    def open(req,**kwargs):
        return Response({'errors':{'token':'private response'},'response':[]},
                        {'Date':format_datetime(NOW.astimezone(timezone.utc))})
    state={}
    api=provider.APIFootball(cfg,state,NOW,opener=SimpleNamespace(open=open))
    with pytest.raises(provider.ProviderError,match='at status: API credentials/account'):
        api.coverage()
    assert 'plan_checked' not in state['provider']
    assert state['provider']['requests']==1
