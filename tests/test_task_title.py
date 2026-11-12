"""The task title is plain text from TaskWarrior. Assigning it with innerHTML
ran any markup in it as part of the page."""
import json
import os
import re
from unittest.mock import patch

from tests.test_app import SAMPLE_TASK, client, mock_result  # noqa: F401 (client is a fixture)

TASK_TEMPLATE = os.path.join(os.path.dirname(__file__), '..', 'templates', 'task.html')


def test_title_is_never_assigned_as_html():
    with open(TASK_TEMPLATE, encoding='utf-8') as f:
        source = f.read()
    assert not re.search(r'innerHTML\s*=\s*formatted_tasks', source)
    assert len(re.findall(r'textContent\s*=\s*formatted_tasks', source)) == 4


@patch('app.subprocess.run')
def test_initial_render_escapes_markup(mock_run, client):  # noqa: F811
    task = {**SAMPLE_TASK, 'description': '<img src=x onerror=alert(1)>'}
    mock_run.return_value = mock_result(stdout=json.dumps([task]))
    body = client.get('/').get_data(as_text=True)
    assert '<img src=x onerror=alert(1)>' not in body
