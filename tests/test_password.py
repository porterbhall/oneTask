"""ONETASK_PASSWORD (HTTP Basic Auth). These had no tests before."""
import base64
from unittest.mock import patch

import pytest

from tests.test_app import client, mock_result  # noqa: F401 (client is a fixture)


def _basic_auth(username, password):
    token = base64.b64encode(f'{username}:{password}'.encode('utf-8')).decode('ascii')
    return {'Authorization': f'Basic {token}'}


@patch('app.subprocess.run')
def test_no_password_set_allows_requests(mock_run, client):  # noqa: F811
    mock_run.return_value = mock_result(stdout='[]')
    assert client.get('/').status_code == 200


@patch('app.subprocess.run')
def test_missing_credentials_refused(mock_run, client, monkeypatch):  # noqa: F811
    monkeypatch.setenv('ONETASK_PASSWORD', 'secret')
    response = client.get('/')
    assert response.status_code == 401
    assert response.headers['WWW-Authenticate'] == 'Basic realm="OneTask"'
    assert mock_run.call_count == 0


@pytest.mark.parametrize('password', ['wrong', 'secre', 'secrets', '', 'SECRET'])
@patch('app.subprocess.run')
def test_wrong_password_refused(mock_run, client, monkeypatch, password):  # noqa: F811
    monkeypatch.setenv('ONETASK_PASSWORD', 'secret')
    assert client.get('/', headers=_basic_auth('any', password)).status_code == 401
    assert mock_run.call_count == 0


@patch('app.subprocess.run')
def test_right_password_allowed_with_any_username(mock_run, client, monkeypatch):  # noqa: F811
    monkeypatch.setenv('ONETASK_PASSWORD', 'secret')
    mock_run.return_value = mock_result(stdout='[]')
    assert client.get('/', headers=_basic_auth('anyone', 'secret')).status_code == 200


@patch('app.subprocess.run')
def test_non_ascii_password(mock_run, client, monkeypatch):  # noqa: F811
    monkeypatch.setenv('ONETASK_PASSWORD', 'pässwörd')
    mock_run.return_value = mock_result(stdout='[]')
    assert client.get('/', headers=_basic_auth('u', 'pässwörd')).status_code == 200
    assert client.get('/', headers=_basic_auth('u', 'passwort')).status_code == 401


def test_bearer_token_refused(client, monkeypatch):  # noqa: F811
    monkeypatch.setenv('ONETASK_PASSWORD', 'secret')
    assert client.get('/', headers={'Authorization': 'Bearer secret'}).status_code == 401


@patch('app.subprocess.run')
def test_writes_refused_without_password(mock_run, client, monkeypatch):  # noqa: F811
    monkeypatch.setenv('ONETASK_PASSWORD', 'secret')
    assert client.post('/complete_task', json={'task_id': 'abc12345'}).status_code == 401
    assert mock_run.call_count == 0
