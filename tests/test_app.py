import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from app import app, convert_taskwarrior_estimate_to_seconds, format_task_for_display, sorting_key


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def mock_result(returncode=0, stdout='', stderr=''):
    """Build a fake subprocess.CompletedProcess."""
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


SAMPLE_TASK = {
    'uuid': 'abc12345-0000-0000-0000-000000000001',
    'description': 'Test task',
    'priority': '2',
    'status': 'pending',
    'estimate': '30m',
    'url': 'none',
    'annotations': [],
    'tags': [],
}


# ---------------------------------------------------------------------------
# Unit tests: convert_taskwarrior_estimate_to_seconds
# ---------------------------------------------------------------------------

class TestConvertEstimateToSeconds:
    def test_empty_string(self):
        assert convert_taskwarrior_estimate_to_seconds('') == 0

    def test_none(self):
        assert convert_taskwarrior_estimate_to_seconds(None) == 0

    def test_minutes(self):
        assert convert_taskwarrior_estimate_to_seconds('30m') == 1800

    def test_hours(self):
        assert convert_taskwarrior_estimate_to_seconds('2h') == 7200

    def test_hours_and_minutes(self):
        assert convert_taskwarrior_estimate_to_seconds('1h30m') == 5400

    def test_seconds(self):
        assert convert_taskwarrior_estimate_to_seconds('30s') == 30

    def test_all_units(self):
        assert convert_taskwarrior_estimate_to_seconds('1h30m45s') == 5445

    def test_trailing_number_treated_as_minutes(self):
        # A bare number with no unit is treated as minutes
        assert convert_taskwarrior_estimate_to_seconds('5') == 300

    def test_mins_suffix(self):
        # '5mins' → reads '5' then 'm' → 300; trailing 'ins' have no preceding number
        assert convert_taskwarrior_estimate_to_seconds('5mins') == 300

    def test_case_insensitive(self):
        assert convert_taskwarrior_estimate_to_seconds('2H') == 7200


# ---------------------------------------------------------------------------
# Unit tests: format_task_for_display
# ---------------------------------------------------------------------------

class TestFormatTaskForDisplay:
    def test_full_task(self):
        result = format_task_for_display(SAMPLE_TASK)
        assert result['name'] == 'Test task'
        assert result['priority'] == 2
        assert result['uuid'] == SAMPLE_TASK['uuid']
        assert result['task_id'] == SAMPLE_TASK['uuid']
        assert result['short_id'] == 'abc12345'
        assert result['total_seconds'] == 1800
        assert result['annotations'] == []
        assert result['tags'] == []
        assert result['formatted_task'] == '2: Test task'

    def test_missing_priority_defaults_to_2(self):
        task = {**SAMPLE_TASK, 'priority': ''}
        assert format_task_for_display(task)['priority'] == 2

    def test_missing_uuid_gives_unknown_short_id(self):
        task = {**SAMPLE_TASK, 'uuid': ''}
        assert format_task_for_display(task)['short_id'] == 'unknown'

    def test_missing_description_fallback(self):
        task = {k: v for k, v in SAMPLE_TASK.items() if k != 'description'}
        assert format_task_for_display(task)['name'] == 'No description'

    def test_short_id_is_first_8_chars_of_uuid(self):
        task = {**SAMPLE_TASK, 'uuid': 'deadbeef-cafe-babe-0000-000000000000'}
        assert format_task_for_display(task)['short_id'] == 'deadbeef'

    def test_annotations_passed_through(self):
        annotations = [{'entry': '20250101T000000Z', 'description': 'A note'}]
        task = {**SAMPLE_TASK, 'annotations': annotations}
        assert format_task_for_display(task)['annotations'] == annotations


# ---------------------------------------------------------------------------
# Unit tests: sorting_key
# ---------------------------------------------------------------------------

class TestSortingKey:
    def test_returns_correct_tuple(self):
        task = {'priority': 1, 'total_seconds': 300, 'name': 'Do thing'}
        assert sorting_key(task) == (1, 300, 'Do thing')

    def test_missing_priority_sorts_to_end(self):
        task = {'priority': None, 'total_seconds': 0, 'name': 'Thing'}
        assert sorting_key(task)[0] == float('inf')


# ---------------------------------------------------------------------------
# Route tests: GET /
# ---------------------------------------------------------------------------

class TestShowList:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout=json.dumps([SAMPLE_TASK]))
        response = client.get('/')
        assert response.status_code == 200
        assert b'Test task' in response.data

    @patch('app.subprocess.run')
    def test_empty_report_shows_placeholder(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='[]')
        response = client.get('/')
        assert response.status_code == 200
        assert b'No tasks to display' in response.data

    @patch('app.subprocess.run')
    def test_custom_report_param(self, mock_run, client):
        mock_run.return_value = mock_result(stdout=json.dumps([SAMPLE_TASK]))
        client.get('/?report=focus')
        assert mock_run.call_args[0][0] == ['task', 'export', 'focus']

    @patch('app.subprocess.run')
    def test_invalid_json_from_taskwarrior_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='not valid json')
        response = client.get('/')
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: POST /complete_task
# ---------------------------------------------------------------------------

class TestCompleteTask:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Completed task 1.')
        response = client.post('/complete_task', json={'task_id': 'abc12345'})
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'completed'
        assert data['task_id'] == 'abc12345'

    def test_missing_task_id_returns_400(self, client):
        response = client.post('/complete_task', json={})
        assert response.status_code == 400

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(returncode=1, stderr='Task not found')
        response = client.post('/complete_task', json={'task_id': 'bad-id'})
        assert response.status_code == 500

    @patch('app.subprocess.run')
    def test_timeout_returns_408(self, mock_run, client):
        mock_run.side_effect = subprocess.TimeoutExpired(['task'], 30)
        response = client.post('/complete_task', json={'task_id': 'abc12345'})
        assert response.status_code == 408


# ---------------------------------------------------------------------------
# Route tests: POST /uncomplete_task
# ---------------------------------------------------------------------------

class TestUncompleteTask:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Modified 1 task.')
        response = client.post('/uncomplete_task', json={'task_id': 'abc12345'})
        assert response.status_code == 200
        assert response.get_json()['status'] == 'uncompleted'

    def test_missing_task_id_returns_400(self, client):
        response = client.post('/uncomplete_task', json={})
        assert response.status_code == 400

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(returncode=1, stderr='error')
        response = client.post('/uncomplete_task', json={'task_id': 'abc12345'})
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: POST /capture
# ---------------------------------------------------------------------------

class TestCapture:
    @patch('app.subprocess.run')
    def test_happy_path_json(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Created task 5.')
        response = client.post('/capture', json={'task': 'Buy milk +shopping'})
        assert response.status_code == 200
        assert mock_run.call_args[0][0] == ['task', 'add', 'Buy', 'milk', '+shopping']

    @patch('app.subprocess.run')
    def test_happy_path_form_data(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Created task 6.')
        response = client.post('/capture', data={'task': 'Read book'})
        assert response.status_code == 200

    def test_missing_task_returns_400(self, client):
        response = client.post('/capture', json={})
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Route tests: GET /task/<id>/annotations
# ---------------------------------------------------------------------------

class TestGetAnnotations:
    @patch('app.subprocess.run')
    def test_happy_path_with_annotations(self, mock_run, client):
        task = {**SAMPLE_TASK, 'annotations': [{'entry': '20250101T000000Z', 'description': 'A note'}]}
        mock_run.return_value = mock_result(stdout=json.dumps([task]))
        response = client.get('/task/abc12345/annotations')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'
        assert len(data['annotations']) == 1
        assert data['annotations'][0]['description'] == 'A note'

    @patch('app.subprocess.run')
    def test_task_not_found_returns_404(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='[]')
        response = client.get('/task/missing/annotations')
        assert response.status_code == 404

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_404(self, mock_run, client):
        # The route treats any non-zero returncode as "task not found"
        mock_run.return_value = mock_result(returncode=1, stderr='error')
        response = client.get('/task/abc12345/annotations')
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Route tests: POST /task/<id>/annotations
# ---------------------------------------------------------------------------

class TestAddAnnotation:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Annotated.')
        response = client.post('/task/abc12345/annotations', json={'annotation': 'My note'})
        assert response.status_code == 200
        assert response.get_json()['status'] == 'success'
        assert mock_run.call_args[0][0] == ['task', 'abc12345', 'annotate', 'My note']

    def test_missing_annotation_returns_400(self, client):
        response = client.post('/task/abc12345/annotations', json={})
        assert response.status_code == 400

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(returncode=1, stderr='error')
        response = client.post('/task/abc12345/annotations', json={'annotation': 'My note'})
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: DELETE /task/<id>/annotations/<text>
# ---------------------------------------------------------------------------

class TestDeleteAnnotation:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Denotated.')
        response = client.delete('/task/abc12345/annotations/my%20note')
        assert response.status_code == 200
        assert mock_run.call_args[0][0] == ['task', 'abc12345', 'denotate', 'my note']

    @patch('app.subprocess.run')
    def test_special_characters_decoded_correctly(self, mock_run, client):
        # Annotation text containing double quotes
        mock_run.return_value = mock_result(stdout='Denotated.')
        response = client.delete('/task/abc12345/annotations/note%20with%20%22quotes%22')
        assert response.status_code == 200
        assert mock_run.call_args[0][0] == ['task', 'abc12345', 'denotate', 'note with "quotes"']

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(returncode=1, stderr='No matching annotation')
        response = client.delete('/task/abc12345/annotations/nonexistent')
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: GET /task/<id>/due
# ---------------------------------------------------------------------------

class TestGetDueDate:
    @patch('app.subprocess.run')
    def test_happy_path_with_due_date(self, mock_run, client):
        task = {**SAMPLE_TASK, 'due': '20260401T000000Z'}
        mock_run.return_value = mock_result(stdout=json.dumps([task]))
        response = client.get('/task/abc12345/due')
        assert response.status_code == 200
        assert response.get_json()['due_date'] == '20260401T000000Z'

    @patch('app.subprocess.run')
    def test_no_due_date_returns_null(self, mock_run, client):
        mock_run.return_value = mock_result(stdout=json.dumps([SAMPLE_TASK]))
        response = client.get('/task/abc12345/due')
        assert response.status_code == 200
        assert response.get_json()['due_date'] is None

    @patch('app.subprocess.run')
    def test_task_not_found_returns_404(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='[]')
        response = client.get('/task/missing/due')
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Route tests: POST /task/<id>/due
# ---------------------------------------------------------------------------

class TestSetDueDate:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Modified 1 task.')
        response = client.post('/task/abc12345/due', json={'due_date': '2026-04-15'})
        assert response.status_code == 200
        assert mock_run.call_args[0][0] == ['task', 'abc12345', 'modify', 'due:2026-04-15']

    def test_missing_due_date_returns_400(self, client):
        response = client.post('/task/abc12345/due', json={})
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Route tests: DELETE /task/<id>/due
# ---------------------------------------------------------------------------

class TestRemoveDueDate:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Modified 1 task.')
        response = client.delete('/task/abc12345/due')
        assert response.status_code == 200
        assert mock_run.call_args[0][0] == ['task', 'abc12345', 'modify', 'due:']

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(returncode=1, stderr='error')
        response = client.delete('/task/abc12345/due')
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: GET /task/<id>/url
# ---------------------------------------------------------------------------

class TestGetTaskUrl:
    @patch('app.subprocess.run')
    def test_happy_path_with_url(self, mock_run, client):
        task = {**SAMPLE_TASK, 'url': 'https://example.com'}
        mock_run.return_value = mock_result(stdout=json.dumps([task]))
        response = client.get('/task/abc12345/url')
        assert response.status_code == 200
        assert response.get_json()['url'] == 'https://example.com'

    @patch('app.subprocess.run')
    def test_no_url_returns_null(self, mock_run, client):
        task = {k: v for k, v in SAMPLE_TASK.items() if k != 'url'}
        mock_run.return_value = mock_result(stdout=json.dumps([task]))
        response = client.get('/task/abc12345/url')
        assert response.status_code == 200
        assert response.get_json()['url'] is None

    @patch('app.subprocess.run')
    def test_task_not_found_returns_404(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='[]')
        response = client.get('/task/missing/url')
        assert response.status_code == 404

    @patch('app.subprocess.run')
    def test_subprocess_exception_returns_500(self, mock_run, client):
        mock_run.side_effect = Exception('unexpected error')
        response = client.get('/task/abc12345/url')
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: POST /task/<id>/url
# ---------------------------------------------------------------------------

class TestSetTaskUrl:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Modified 1 task.')
        response = client.post('/task/abc12345/url', json={'url': 'https://example.com'})
        assert response.status_code == 200
        assert mock_run.call_args[0][0] == ['task', 'abc12345', 'modify', 'url:https://example.com']

    def test_missing_url_returns_400(self, client):
        response = client.post('/task/abc12345/url', json={})
        assert response.status_code == 400

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(returncode=1, stderr='error')
        response = client.post('/task/abc12345/url', json={'url': 'https://example.com'})
        assert response.status_code == 500

    @patch('app.subprocess.run')
    def test_subprocess_exception_returns_500(self, mock_run, client):
        mock_run.side_effect = Exception('unexpected error')
        response = client.post('/task/abc12345/url', json={'url': 'https://example.com'})
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: DELETE /task/<id>/url
# ---------------------------------------------------------------------------

class TestRemoveTaskUrl:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Modified 1 task.')
        response = client.delete('/task/abc12345/url')
        assert response.status_code == 200
        assert mock_run.call_args[0][0] == ['task', 'abc12345', 'modify', 'url:']

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(returncode=1, stderr='error')
        response = client.delete('/task/abc12345/url')
        assert response.status_code == 500

    @patch('app.subprocess.run')
    def test_subprocess_exception_returns_500(self, mock_run, client):
        mock_run.side_effect = Exception('unexpected error')
        response = client.delete('/task/abc12345/url')
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: GET /stats
# ---------------------------------------------------------------------------

class TestShowStats:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        task = {**SAMPLE_TASK, 'estimate': '30m'}
        mock_run.side_effect = [
            mock_result(stdout=json.dumps([task])),      # get_tasks_from_report
            mock_result(stdout='- Task A\n- Task B\n'),  # completed today
        ]
        response = client.get('/stats')
        assert response.status_code == 200
        assert b'30m' in response.data
        assert b'Tasks completed today: 2' in response.data

    @patch('app.subprocess.run')
    def test_time_display_hours_and_minutes(self, mock_run, client):
        task = {**SAMPLE_TASK, 'estimate': '75m'}
        mock_run.side_effect = [
            mock_result(stdout=json.dumps([task, task])),  # 2 × 75m = 2h 30m
            mock_result(stdout=''),
        ]
        response = client.get('/stats')
        assert response.status_code == 200
        assert b'2h 30m' in response.data

    @patch('app.subprocess.run')
    def test_time_display_minutes_only(self, mock_run, client):
        task = {**SAMPLE_TASK, 'estimate': '45m'}
        mock_run.side_effect = [
            mock_result(stdout=json.dumps([task])),
            mock_result(stdout=''),
        ]
        response = client.get('/stats')
        assert response.status_code == 200
        assert b'45m' in response.data

    @patch('app.subprocess.run')
    def test_time_display_zero_when_no_estimates(self, mock_run, client):
        task = {**SAMPLE_TASK, 'estimate': ''}
        mock_run.side_effect = [
            mock_result(stdout=json.dumps([task])),
            mock_result(stdout=''),
        ]
        response = client.get('/stats')
        assert response.status_code == 200
        assert b'0m' in response.data

    @patch('app.subprocess.run')
    def test_custom_report_param(self, mock_run, client):
        mock_run.side_effect = [
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
            mock_result(stdout=''),
        ]
        response = client.get('/stats?report=focus')
        assert response.status_code == 200
        assert b'Focus' in response.data

    @patch('app.subprocess.run')
    def test_completed_today_fails_gracefully(self, mock_run, client):
        mock_run.side_effect = [
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
            Exception('completed query failed'),
        ]
        response = client.get('/stats')
        assert response.status_code == 200
        assert b'Tasks completed today: 0' in response.data

    @patch('app.subprocess.run')
    def test_outer_exception_returns_error_page(self, mock_run, client):
        # get_tasks_from_report re-raises json.JSONDecodeError, reaching the outer handler
        mock_run.return_value = mock_result(stdout='not valid json')
        response = client.get('/stats')
        assert response.status_code == 500
        assert b'Stats Error' in response.data


# ---------------------------------------------------------------------------
# Route tests: GET /tasks/by-tag/<tag>
# ---------------------------------------------------------------------------

class TestGetTasksByTag:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout=json.dumps([SAMPLE_TASK]))
        response = client.get('/tasks/by-tag/work')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'
        assert data['tag'] == 'work'
        assert len(data['tasks']) == 1
        assert data['tasks'][0]['description'] == 'Test task'
        assert data['tasks'][0]['short_id'] == 'abc12345'
        assert mock_run.call_args[0][0] == ['task', 'tag:work', 'export']

    @patch('app.subprocess.run')
    def test_no_tasks_returns_empty_list(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='')
        response = client.get('/tasks/by-tag/nonexistent')
        assert response.status_code == 200
        assert response.get_json()['tasks'] == []

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(returncode=1, stderr='error')
        response = client.get('/tasks/by-tag/work')
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: POST /task/<id>/description
# ---------------------------------------------------------------------------

class TestSetTaskDescription:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Modified 1 task.')
        response = client.post('/task/abc12345/description', json={'description': 'New task name'})
        assert response.status_code == 200
        assert response.get_json()['status'] == 'success'
        assert mock_run.call_args[0][0] == ['task', 'abc12345', 'modify', 'description:New task name']

    def test_missing_description_returns_400(self, client):
        response = client.post('/task/abc12345/description', json={})
        assert response.status_code == 400

    def test_blank_description_returns_400(self, client):
        response = client.post('/task/abc12345/description', json={'description': '   '})
        assert response.status_code == 400

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(returncode=1, stderr='error')
        response = client.post('/task/abc12345/description', json={'description': 'New name'})
        assert response.status_code == 500

    @patch('app.subprocess.run')
    def test_subprocess_exception_returns_500(self, mock_run, client):
        mock_run.side_effect = Exception('unexpected')
        response = client.post('/task/abc12345/description', json={'description': 'New name'})
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: POST /task/<id>/priority
# ---------------------------------------------------------------------------

class TestSetTaskPriority:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Modified 1 task.')
        response = client.post('/task/abc12345/priority', json={'priority': 1})
        assert response.status_code == 200
        assert response.get_json()['status'] == 'success'
        assert mock_run.call_args[0][0] == ['task', 'abc12345', 'modify', 'priority:1']

    def test_missing_priority_returns_400(self, client):
        response = client.post('/task/abc12345/priority', json={})
        assert response.status_code == 400

    def test_invalid_priority_value_returns_400(self, client):
        response = client.post('/task/abc12345/priority', json={'priority': 5})
        assert response.status_code == 400

    def test_non_numeric_priority_returns_400(self, client):
        response = client.post('/task/abc12345/priority', json={'priority': 'high'})
        assert response.status_code == 400

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(returncode=1, stderr='error')
        response = client.post('/task/abc12345/priority', json={'priority': 2})
        assert response.status_code == 500

    @patch('app.subprocess.run')
    def test_subprocess_exception_returns_500(self, mock_run, client):
        mock_run.side_effect = Exception('unexpected')
        response = client.post('/task/abc12345/priority', json={'priority': 2})
        assert response.status_code == 500
