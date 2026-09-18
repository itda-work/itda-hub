"""발견 문서 — Claude 가 읽는 두 문서가 스파이크의 전제를 만족하는지."""

import pytest
from django.core.management import call_command


@pytest.fixture
def catalog(db):
    call_command('seed_catalog', verbosity=0)


def test_인가_서버_메타데이터(client, catalog, settings):
    doc = client.get('/.well-known/oauth-authorization-server').json()
    assert doc['issuer'] == settings.HUB_BASE_URL
    assert 'S256' in doc['code_challenge_methods_supported']
    assert 'none' in doc['token_endpoint_auth_methods_supported'], (
        'CIMD 공개 클라이언트가 고르려면 none 이 있어야 한다'
    )
    assert doc['client_id_metadata_document_supported'] is True
    assert doc['registration_endpoint'].endswith('/o/register/')
    assert doc['scopes_supported'] == ['tool:kosis', 'tool:weather'], (
        '비공개 도구는 광고하지 않는다'
    )


def test_보호_리소스_메타데이터(client, catalog, settings):
    doc = client.get('/.well-known/oauth-protected-resource/mcp').json()
    assert doc['resource'] == settings.HUB_MCP_URL
    assert doc['authorization_servers'] == [settings.HUB_BASE_URL]
    assert doc['scopes_supported'] == ['tool:kosis', 'tool:weather']
