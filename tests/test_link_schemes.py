"""A stored link like `javascript://%0a...` ran script when opened, because
the page skipped its http:// prefix for anything containing `://`."""
import os
from unittest.mock import patch

import pytest

from tests.test_app import client, mock_result, write_task_args  # noqa: F401 (client is a fixture)

TASK_TEMPLATE = os.path.join(os.path.dirname(__file__), '..', 'templates', 'task.html')


@pytest.mark.parametrize('url', [
    'javascript:alert(1)', 'javascript://%0aalert(1)', 'JavaScript:alert(1)',
    ' javascript:alert(1)', 'javascript :alert(1)', 'data:text/html,x', 'vbscript:x',
])
@patch('app.subprocess.run')
def test_blocked_scheme_refused_before_taskwarrior(mock_run, client, url):  # noqa: F811
    response = client.post('/task/abc12345/url', json={'url': url})
    assert response.status_code == 400
    assert mock_run.call_count == 0


@pytest.mark.parametrize('url', [
    'https://example.com', 'http://example.com', 'example.com', 'obsidian://open?vault=x',
    'joplin://x-callback-url/openNote?id=1', 'https://example.com/javascript:x',
])
@patch('app.subprocess.run')
def test_allowed_urls_still_saved(mock_run, client, url):  # noqa: F811
    mock_run.side_effect = [
        mock_result(stdout='uda.url.type=string\n'),
        mock_result(stdout='Modified 1 task.'),
    ]
    response = client.post('/task/abc12345/url', json={'url': url})
    assert response.status_code == 200
    assert mock_run.call_args[0][0] == write_task_args('abc12345', 'modify', f'url:{url}')


def test_page_opens_links_only_through_the_scheme_check():
    with open(TASK_TEMPLATE, encoding='utf-8') as f:
        source = f.read()
    assert source.count('safeTaskLink(url)') == 2
    assert 'window.open(processedUrl' in source
    assert "'javascript:', 'data:', 'vbscript:'" in source
