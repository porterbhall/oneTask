import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from app import (
    RC_OVERRIDES,
    app,
    convert_taskwarrior_estimate_to_seconds,
    format_due_date_display,
    format_end_date_display,
    format_estimate_display,
    format_task_for_display,
    get_resolved_config,
    sorting_key,
)


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


def task_args(*args):
    """Expected subprocess.run argv for a read/query `task` invocation — RC
    overrides plus rc.hooks=off, since reads stay hook-free (ON-65/ON-93)."""
    return ['task'] + RC_OVERRIDES + ['rc.hooks=off'] + list(args)


def write_task_args(*args):
    """Expected subprocess.run argv for a mutating `task` invocation — RC
    overrides only, with hooks left enabled so on-modify/on-add fire (ON-93)."""
    return ['task'] + RC_OVERRIDES + list(args)


CONFIG_WITH_ESTIMATE_UDA = mock_result(stdout='uda.estimate.type=duration\nuda.estimate.label=Est\n')
CONFIG_WITHOUT_ESTIMATE_UDA = mock_result(stdout='dateformat=Y-M-D\n')

CONFIG_WITH_REPORTS = mock_result(stdout=(
    'report.next.columns=id,description\n'
    'report.focus.columns=id,priority,description\n'
))


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

    def test_days(self):
        # Added for ON-98 — ONETASK_COMPLETED_WINDOW's own examples use
        # '7days', which silently parsed to 0 before 'd' was handled.
        assert convert_taskwarrior_estimate_to_seconds('7days') == 604800

    def test_days_short_form(self):
        assert convert_taskwarrior_estimate_to_seconds('7d') == 604800


# ---------------------------------------------------------------------------
# Unit tests: format_task_for_display
# ---------------------------------------------------------------------------

class TestFormatTaskForDisplay:
    def test_full_task(self):
        # SAMPLE_TASK's priority ('2') isn't in the default H/M/L scheme, so
        # it's still shown as-is (never coerced/guessed) but ranks unknown.
        result = format_task_for_display(SAMPLE_TASK)
        assert result['name'] == 'Test task'
        assert result['priority'] == '2'
        assert result['priority_rank'] == float('inf')
        assert result['uuid'] == SAMPLE_TASK['uuid']
        assert result['task_id'] == SAMPLE_TASK['uuid']
        assert result['short_id'] == 'abc12345'
        assert result['total_seconds'] == 1800
        assert result['annotations'] == []
        assert result['tags'] == []
        assert result['formatted_task'] == '2: Test task'

    def test_priority_resolved_against_actual_scheme(self):
        # ON-67/A3: with Porter's real scheme passed in, '2' ranks correctly.
        result = format_task_for_display(SAMPLE_TASK, priority_values=['1', '2', '3'])
        assert result['priority'] == '2'
        assert result['priority_rank'] == 1

    def test_missing_priority_has_no_value_or_rank(self):
        task = {**SAMPLE_TASK, 'priority': ''}
        result = format_task_for_display(task)
        assert result['priority'] == ''
        assert result['priority_rank'] == float('inf')
        assert result['formatted_task'] == 'Test task'

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

    def test_estimate_configured_defaults_true_and_uses_task_value(self):
        result = format_task_for_display(SAMPLE_TASK)
        assert result['estimate_is_default'] is False
        assert result['total_seconds'] == 1800

    def test_estimate_not_configured_falls_back_to_default(self):
        from app import DEFAULT_ESTIMATE_SECONDS
        # Even a task with its own 'estimate' value is ignored once the UDA
        # itself isn't configured — stock TaskWarrior wouldn't have set it.
        result = format_task_for_display(SAMPLE_TASK, estimate_configured=False)
        assert result['estimate_is_default'] is True
        assert result['total_seconds'] == DEFAULT_ESTIMATE_SECONDS

    def test_estimate_configured_but_task_value_missing_falls_back_to_default(self):
        # ON-84: the UDA is configured, but this specific task never got a
        # value set — same dead-timer symptom as the UDA being absent
        # entirely, so it gets the same default-plus-notice treatment.
        from app import DEFAULT_ESTIMATE_SECONDS
        task = {**SAMPLE_TASK, 'estimate': ''}
        result = format_task_for_display(task)
        assert result['estimate_is_default'] is True
        assert result['total_seconds'] == DEFAULT_ESTIMATE_SECONDS

    def test_estimate_configured_but_task_value_unparseable_falls_back_to_default(self):
        # An unparseable value (no digits/units recognized) also resolves
        # to 0 seconds and should degrade the same way, not hang or crash.
        from app import DEFAULT_ESTIMATE_SECONDS
        task = {**SAMPLE_TASK, 'estimate': 'garbage'}
        result = format_task_for_display(task)
        assert result['estimate_is_default'] is True
        assert result['total_seconds'] == DEFAULT_ESTIMATE_SECONDS

    def test_configured_default_used_without_notice(self):
        # ON-92: an admin-configured default is intended behavior, not a
        # misconfiguration, so the notice is suppressed even though the
        # task itself has no estimate.
        task = {**SAMPLE_TASK, 'estimate': ''}
        result = format_task_for_display(
            task, default_duration_seconds=300, default_duration_configured=True)
        assert result['estimate_is_default'] is False
        assert result['total_seconds'] == 300

    def test_configured_default_of_zero_means_count_up_without_notice(self):
        # ON-92: 0 is a legitimate configured value (start counting up
        # immediately), distinct from an unconfigured dead timer.
        task = {**SAMPLE_TASK, 'estimate': ''}
        result = format_task_for_display(
            task, default_duration_seconds=0, default_duration_configured=True)
        assert result['estimate_is_default'] is False
        assert result['total_seconds'] == 0

    def test_unconfigured_default_still_shows_notice(self):
        # Default params (no ON-92 override in play) behave exactly like
        # ON-84: built-in length, notice shown.
        from app import DEFAULT_ESTIMATE_SECONDS
        task = {**SAMPLE_TASK, 'estimate': ''}
        result = format_task_for_display(task)
        assert result['estimate_is_default'] is True
        assert result['total_seconds'] == DEFAULT_ESTIMATE_SECONDS

    def test_real_task_estimate_wins_over_configured_default(self):
        # A task's own estimate always takes priority over any default.
        result = format_task_for_display(
            SAMPLE_TASK, default_duration_seconds=300, default_duration_configured=True)
        assert result['estimate_is_default'] is False
        assert result['total_seconds'] == 1800


# ---------------------------------------------------------------------------
# Unit tests: get_default_duration_seconds (ON-92)
# ---------------------------------------------------------------------------

class TestGetDefaultDurationSeconds:
    def test_unset_falls_back_to_builtin_unconfigured(self, monkeypatch):
        from app import DEFAULT_ESTIMATE_SECONDS, get_default_duration_seconds
        monkeypatch.delenv('ONETASK_DEFAULT_DURATION', raising=False)
        seconds, configured = get_default_duration_seconds()
        assert seconds == DEFAULT_ESTIMATE_SECONDS
        assert configured is False

    def test_configured_duration_string_is_parsed(self, monkeypatch):
        from app import get_default_duration_seconds
        monkeypatch.setenv('ONETASK_DEFAULT_DURATION', '5min')
        seconds, configured = get_default_duration_seconds()
        assert seconds == 300
        assert configured is True

    def test_configured_zero_is_honored(self, monkeypatch):
        from app import get_default_duration_seconds
        monkeypatch.setenv('ONETASK_DEFAULT_DURATION', '0')
        seconds, configured = get_default_duration_seconds()
        assert seconds == 0
        assert configured is True

    def test_garbage_with_no_digits_falls_back_unconfigured(self, monkeypatch):
        # Must not be mistaken for a deliberate 0=count-up value — the
        # shared parser would otherwise silently resolve "banana" to 0.
        from app import DEFAULT_ESTIMATE_SECONDS, get_default_duration_seconds
        monkeypatch.setenv('ONETASK_DEFAULT_DURATION', 'banana')
        seconds, configured = get_default_duration_seconds()
        assert seconds == DEFAULT_ESTIMATE_SECONDS
        assert configured is False

    def test_blank_falls_back_unconfigured(self, monkeypatch):
        from app import DEFAULT_ESTIMATE_SECONDS, get_default_duration_seconds
        monkeypatch.setenv('ONETASK_DEFAULT_DURATION', '   ')
        seconds, configured = get_default_duration_seconds()
        assert seconds == DEFAULT_ESTIMATE_SECONDS
        assert configured is False

    def test_iso8601_duration_format_accepted(self, monkeypatch):
        from app import get_default_duration_seconds
        monkeypatch.setenv('ONETASK_DEFAULT_DURATION', 'PT25M')
        seconds, configured = get_default_duration_seconds()
        assert seconds == 1500
        assert configured is True


# ---------------------------------------------------------------------------
# Unit tests: get_completed_window_seconds (ON-98)
# ---------------------------------------------------------------------------

class TestGetCompletedWindowSeconds:
    def test_unset_is_disabled(self, monkeypatch):
        from app import get_completed_window_seconds
        monkeypatch.delenv('ONETASK_COMPLETED_WINDOW', raising=False)
        seconds, enabled = get_completed_window_seconds()
        assert seconds == 0
        assert enabled is False

    def test_explicit_zero_is_disabled(self, monkeypatch):
        # Unlike ONETASK_DEFAULT_DURATION, 0 has no meaning here other than
        # "off" — there's no count-up-immediately equivalent for a window.
        from app import get_completed_window_seconds
        monkeypatch.setenv('ONETASK_COMPLETED_WINDOW', '0')
        seconds, enabled = get_completed_window_seconds()
        assert seconds == 0
        assert enabled is False

    def test_configured_duration_string_is_parsed(self, monkeypatch):
        from app import get_completed_window_seconds
        monkeypatch.setenv('ONETASK_COMPLETED_WINDOW', '2hours')
        seconds, enabled = get_completed_window_seconds()
        assert seconds == 7200
        assert enabled is True

    def test_garbage_with_no_digits_is_disabled(self, monkeypatch):
        from app import get_completed_window_seconds
        monkeypatch.setenv('ONETASK_COMPLETED_WINDOW', 'banana')
        seconds, enabled = get_completed_window_seconds()
        assert seconds == 0
        assert enabled is False


# ---------------------------------------------------------------------------
# Unit tests: get_completed_and_deleted_tasks (ON-98)
# ---------------------------------------------------------------------------

class TestGetCompletedAndDeletedTasks:
    @patch('app.subprocess.run')
    def test_filter_args_precede_export_and_group_the_or(self, mock_run):
        # Ad-hoc filters (unlike a named report) must come BEFORE the
        # command, and the OR needs explicit parens — confirmed empirically
        # against a live TaskWarrior install, not just assumed.
        from app import get_completed_and_deleted_tasks
        mock_run.return_value = mock_result(stdout='[]')
        get_completed_and_deleted_tasks(3600)
        assert mock_run.call_args[0][0] == task_args(
            'end.after:now-3600s', '(', 'status:completed', 'or', 'status:deleted', ')', 'export'
        )

    @patch('app.subprocess.run')
    def test_returns_parsed_tasks(self, mock_run):
        from app import get_completed_and_deleted_tasks
        mock_run.return_value = mock_result(stdout=json.dumps([SAMPLE_TASK]))
        result = get_completed_and_deleted_tasks(3600)
        assert result == [SAMPLE_TASK]

    @patch('app.subprocess.run')
    def test_command_failure_returns_empty_list(self, mock_run):
        from app import get_completed_and_deleted_tasks
        mock_run.return_value = mock_result(returncode=1, stderr='error')
        assert get_completed_and_deleted_tasks(3600) == []

    @patch('app.subprocess.run')
    def test_blank_output_returns_empty_list(self, mock_run):
        from app import get_completed_and_deleted_tasks
        mock_run.return_value = mock_result(stdout='')
        assert get_completed_and_deleted_tasks(3600) == []


# ---------------------------------------------------------------------------
# Unit tests: sorting_key
# ---------------------------------------------------------------------------

class TestSortingKey:
    def test_returns_correct_tuple(self):
        task = {'priority_rank': 0, 'total_seconds': 300, 'name': 'Do thing'}
        assert sorting_key(task) == (0, 300, 'Do thing')

    def test_missing_priority_sorts_to_end(self):
        task = {'priority_rank': float('inf'), 'total_seconds': 0, 'name': 'Thing'}
        assert sorting_key(task)[0] == float('inf')


# ---------------------------------------------------------------------------
# Unit tests: format_due_date_display / format_estimate_display
# ---------------------------------------------------------------------------

class TestFormatDueDateDisplay:
    def test_none_returns_none(self):
        assert format_due_date_display(None) is None

    def test_empty_string_returns_none(self):
        assert format_due_date_display('') is None

    def test_valid_taskwarrior_date(self):
        assert format_due_date_display('20260705T070000Z') == 'Jul 05, 2026'

    def test_unparseable_date_returned_as_is(self):
        assert format_due_date_display('not-a-date') == 'not-a-date'


class TestFormatEndDateDisplay:
    """format_end_date_display (ON-98) delegates straight to
    format_due_date_display — same on-disk TaskWarrior date format."""

    def test_none_returns_none(self):
        assert format_end_date_display(None) is None

    def test_valid_taskwarrior_date(self):
        assert format_end_date_display('20260827T140000Z') == 'Aug 27, 2026'


class TestFormatEstimateDisplay:
    def test_zero_returns_none(self):
        assert format_estimate_display(0) is None

    def test_none_returns_none(self):
        assert format_estimate_display(None) is None

    def test_minutes_only(self):
        assert format_estimate_display(1800) == '30m'

    def test_hours_only(self):
        assert format_estimate_display(7200) == '2h'

    def test_hours_and_minutes(self):
        assert format_estimate_display(5400) == '1h 30m'


# ---------------------------------------------------------------------------
# Unit tests: run_task_command / get_resolved_config (ON-65)
# ---------------------------------------------------------------------------

class TestRunTaskCommand:
    @patch('app.subprocess.run')
    def test_prepends_rc_overrides(self, mock_run):
        from app import run_task_command
        mock_run.return_value = mock_result(stdout='')
        run_task_command(['export', 'next'])
        assert mock_run.call_args[0][0] == task_args('export', 'next')

    @patch('app.subprocess.run')
    def test_rc_overrides_come_before_the_subcommand(self, mock_run):
        from app import run_task_command
        mock_run.return_value = mock_result(stdout='')
        run_task_command(['export'])
        argv = mock_run.call_args[0][0]
        assert argv[0] == 'task'
        assert argv[1:1 + len(RC_OVERRIDES)] == RC_OVERRIDES
        assert argv[1 + len(RC_OVERRIDES):] == ['rc.hooks=off', 'export']

    @patch('app.subprocess.run')
    def test_hooks_true_omits_rc_hooks_off(self, mock_run):
        # ON-93: mutating calls must not suppress on-modify/on-add hooks.
        from app import run_task_command
        mock_run.return_value = mock_result(stdout='')
        run_task_command(['1', 'done'], hooks=True)
        argv = mock_run.call_args[0][0]
        assert 'rc.hooks=off' not in argv
        assert argv == ['task'] + RC_OVERRIDES + ['1', 'done']

    @patch('app.subprocess.run')
    def test_hooks_false_is_the_default(self, mock_run):
        from app import run_task_command
        mock_run.return_value = mock_result(stdout='')
        run_task_command(['export'])
        assert 'rc.hooks=off' in mock_run.call_args[0][0]


class TestGetResolvedConfig:
    @patch('app.subprocess.run')
    def test_calls_show_through_the_hardened_invocation(self, mock_run):
        mock_run.return_value = mock_result(stdout='')
        get_resolved_config()
        assert mock_run.call_args[0][0] == task_args('_show')

    @patch('app.subprocess.run')
    def test_parses_key_value_lines(self, mock_run):
        mock_run.return_value = mock_result(stdout=(
            'uda.estimate.type=duration\n'
            'uda.priority.values=H,M,L\n'
        ))
        config = get_resolved_config()
        assert config['uda.estimate.type'] == 'duration'
        assert config['uda.priority.values'] == 'H,M,L'

    @patch('app.subprocess.run')
    def test_skips_blank_lines_comments_and_lines_without_equals(self, mock_run):
        mock_run.return_value = mock_result(stdout=(
            '\n'
            '# a comment\n'
            'not a config line\n'
            'dateformat=Y-M-D\n'
        ))
        config = get_resolved_config()
        assert config == {'dateformat': 'Y-M-D'}

    @patch('app.subprocess.run')
    def test_returns_empty_dict_on_nonzero_returncode(self, mock_run):
        mock_run.return_value = mock_result(returncode=1, stderr='boom')
        assert get_resolved_config() == {}

    @patch('app.subprocess.run')
    def test_returns_empty_dict_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='task', timeout=30)
        assert get_resolved_config() == {}

    @patch('app.subprocess.run')
    def test_does_not_accept_a_path_argument(self, mock_run):
        # get_resolved_config takes no arguments — TaskWarrior resolves its
        # own config; there is no way to point it at a user-supplied path.
        import inspect
        assert inspect.signature(get_resolved_config).parameters == {}


class TestEstimateUdaDefined:
    def test_true_when_uda_estimate_keys_present(self):
        from app import estimate_uda_defined
        config = {'uda.estimate.type': 'duration', 'uda.estimate.label': 'Est'}
        assert estimate_uda_defined(config) is True

    def test_false_when_absent(self):
        from app import estimate_uda_defined
        config = {'dateformat': 'Y-M-D', 'uda.priority.values': 'H,M,L'}
        assert estimate_uda_defined(config) is False

    def test_false_for_empty_config(self):
        from app import estimate_uda_defined
        assert estimate_uda_defined({}) is False


class TestUrlUdaDefined:
    def test_true_when_uda_url_keys_present(self):
        from app import url_uda_defined
        config = {'uda.url.type': 'string', 'uda.url.label': 'URL'}
        assert url_uda_defined(config) is True

    def test_false_when_absent(self):
        from app import url_uda_defined
        config = {'dateformat': 'Y-M-D', 'uda.priority.values': 'H,M,L'}
        assert url_uda_defined(config) is False

    def test_false_for_empty_config(self):
        from app import url_uda_defined
        assert url_uda_defined({}) is False


class TestGetReportNames:
    def test_extracts_names_from_columns_keys(self):
        from app import get_report_names
        config = {
            'report.next.columns': 'id,description',
            'report.focus.columns': 'id,priority,description',
            'report.next.labels': 'ID,Description',  # not a .columns key -> ignored
            'dateformat': 'Y-M-D',
        }
        assert get_report_names(config) == {'next', 'focus'}

    def test_empty_config_returns_empty_set(self):
        from app import get_report_names
        assert get_report_names({}) == set()


class TestResolveReportName:
    def test_valid_report_passes_through_unchanged(self):
        from app import resolve_report_name
        assert resolve_report_name('focus', {'next', 'focus'}) == ('focus', False)

    def test_unknown_report_falls_back_to_next(self):
        from app import resolve_report_name
        assert resolve_report_name('bogus', {'next', 'focus'}) == ('next', True)

    def test_empty_report_names_trusts_request_as_is(self):
        # Config couldn't be resolved (report_names empty) — don't
        # second-guess the request; built-in reports must keep working
        # even if this detection layer can't run (ON-69/A5).
        from app import resolve_report_name
        assert resolve_report_name('next', set()) == ('next', False)
        assert resolve_report_name('anything', set()) == ('anything', False)


class TestGetPriorityValues:
    def test_reads_custom_scheme_from_config(self):
        from app import get_priority_values
        config = {'uda.priority.values': '1,2,3'}
        assert get_priority_values(config) == ['1', '2', '3']

    def test_falls_back_to_native_hml_when_key_absent(self):
        from app import get_priority_values, DEFAULT_PRIORITY_VALUES
        assert get_priority_values({}) == list(DEFAULT_PRIORITY_VALUES)

    def test_reads_native_scheme_explicitly(self):
        from app import get_priority_values
        config = {'uda.priority.values': 'H,M,L'}
        assert get_priority_values(config) == ['H', 'M', 'L']

    def test_strips_trailing_empty_entry(self):
        # TaskWarrior's own stock resolved config includes a trailing comma
        # (an explicit blank/none option) — filter it out of the value list.
        from app import get_priority_values
        config = {'uda.priority.values': 'H,M,L,'}
        assert get_priority_values(config) == ['H', 'M', 'L']

    def test_empty_after_filtering_returns_empty_list(self):
        # Key present but no usable values — signals "unknown scheme, degrade"
        # to callers rather than silently defaulting.
        from app import get_priority_values
        config = {'uda.priority.values': ',,,'}
        assert get_priority_values(config) == []


class TestPriorityRank:
    def test_ranks_by_position_in_scheme(self):
        from app import priority_rank
        values = ['1', '2', '3']
        assert priority_rank('1', values) == 0
        assert priority_rank('2', values) == 1
        assert priority_rank('3', values) == 2

    def test_unset_value_sorts_last(self):
        from app import priority_rank
        assert priority_rank('', ['H', 'M', 'L']) == float('inf')
        assert priority_rank(None, ['H', 'M', 'L']) == float('inf')

    def test_unrecognized_value_sorts_last(self):
        from app import priority_rank
        assert priority_rank('Z', ['H', 'M', 'L']) == float('inf')


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
        assert mock_run.call_args[0][0] == task_args('export', 'focus')

    @patch('app.subprocess.run')
    def test_invalid_json_from_taskwarrior_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='not valid json')
        response = client.get('/')
        assert response.status_code == 500

    @patch('app.subprocess.run')
    def test_task_param_jumps_to_matching_task(self, mock_run, client):
        other_task = {**SAMPLE_TASK, 'uuid': 'def67890-0000-0000-0000-000000000002', 'description': 'Second task'}
        mock_run.return_value = mock_result(stdout=json.dumps([SAMPLE_TASK, other_task]))
        response = client.get(f'/?task={other_task["uuid"]}')
        assert response.status_code == 200
        # current-task-id is rendered only for the selected task's short_id
        assert b'id="current-task-id">def67890<' in response.data
        # the JS currentTaskIndex must match the server-selected index too, or every
        # JS-driven read (annotations, due date, tags, URL, countdown) silently falls
        # back to task 0 regardless of what the server-rendered HTML shows
        assert b'var currentTaskIndex = 1;' in response.data

    @patch('app.subprocess.run')
    def test_unknown_task_param_falls_back_to_first(self, mock_run, client):
        mock_run.return_value = mock_result(stdout=json.dumps([SAMPLE_TASK]))
        response = client.get('/?task=does-not-exist')
        assert response.status_code == 200
        assert b'id="current-task-id">abc12345<' in response.data

    @patch('app.subprocess.run')
    def test_default_estimate_notice_hidden_when_uda_configured(self, mock_run, client):
        mock_run.side_effect = [
            CONFIG_WITH_ESTIMATE_UDA,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
        ]
        response = client.get('/')
        assert response.status_code == 200
        assert b'var estimateIsDefault = [false]' in response.data

    @patch('app.subprocess.run')
    def test_default_estimate_notice_shown_when_uda_not_configured(self, mock_run, client):
        # ON-66/A2: stock TaskWarrior has no `estimate` UDA at all — surface the
        # fallback state instead of a dead/empty timer.
        mock_run.side_effect = [
            CONFIG_WITHOUT_ESTIMATE_UDA,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
        ]
        response = client.get('/')
        assert response.status_code == 200
        assert b'var estimateIsDefault = [true]' in response.data
        assert b'No estimate configured' in response.data

    @patch('app.subprocess.run')
    def test_renders_custom_priority_scheme(self, mock_run, client):
        # ON-67/A3: Porter's real config (uda.priority.values=1,2,3) must be
        # what the page's priority editor is populated from, not a hardcoded list.
        task = {**SAMPLE_TASK, 'priority': '1'}
        mock_run.side_effect = [
            mock_result(stdout='uda.priority.values=1,2,3\n'),
            mock_result(stdout=json.dumps([task])),
        ]
        response = client.get('/')
        assert response.status_code == 200
        assert b'var priorityValues = ["1", "2", "3"]' in response.data
        assert b'1: Test task' in response.data

    @patch('app.subprocess.run')
    def test_renders_native_priority_scheme_when_not_customized(self, mock_run, client):
        # Stock TaskWarrior — no uda.priority.values override -> native H/M/L.
        task = {**SAMPLE_TASK, 'priority': 'H'}
        mock_run.side_effect = [
            mock_result(stdout='dateformat=Y-M-D\n'),
            mock_result(stdout=json.dumps([task])),
        ]
        response = client.get('/')
        assert response.status_code == 200
        assert b'var priorityValues = ["H", "M", "L"]' in response.data
        assert b'H: Test task' in response.data

    @patch('app.subprocess.run')
    def test_unset_priority_shows_no_prefix(self, mock_run, client):
        task = {**SAMPLE_TASK, 'priority': ''}
        mock_run.side_effect = [
            mock_result(stdout='uda.priority.values=1,2,3\n'),
            mock_result(stdout=json.dumps([task])),
        ]
        response = client.get('/')
        assert response.status_code == 200
        assert b'var formatted_tasks = ["Test task"]' in response.data

    @patch('app.subprocess.run')
    def test_url_configured_true_when_uda_present(self, mock_run, client):
        mock_run.side_effect = [
            mock_result(stdout='uda.url.type=string\n'),
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
        ]
        response = client.get('/')
        assert response.status_code == 200
        assert b'var urlConfigured = true' in response.data

    @patch('app.subprocess.run')
    def test_url_configured_false_when_uda_absent(self, mock_run, client):
        # ON-68/A4: stock TaskWarrior has no `url` UDA at all.
        mock_run.side_effect = [
            mock_result(stdout='dateformat=Y-M-D\n'),
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
        ]
        response = client.get('/')
        assert response.status_code == 200
        assert b'var urlConfigured = false' in response.data

    @patch('app.subprocess.run')
    def test_valid_report_shows_no_fallback_notice(self, mock_run, client):
        mock_run.side_effect = [
            CONFIG_WITH_REPORTS,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
        ]
        response = client.get('/?report=focus')
        assert response.status_code == 200
        assert b'not found' not in response.data

    @patch('app.subprocess.run')
    def test_unknown_report_falls_back_to_next_with_notice(self, mock_run, client):
        # ON-69/A5: a typo'd/missing report must not silently render as an
        # empty report — show a clear notice and fall back to 'next'.
        mock_run.side_effect = [
            CONFIG_WITH_REPORTS,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
        ]
        response = client.get('/?report=totallyBogusReportName')
        assert response.status_code == 200
        assert b'Report "totallyBogusReportName" not found' in response.data
        # the actual data fetch used the fallback, not the bogus name
        assert mock_run.call_args[0][0] == task_args('export', 'next')

    @patch('app.subprocess.run')
    def test_unresolvable_config_does_not_block_built_in_reports(self, mock_run, client):
        # If the config fetch itself fails/returns nothing, report validation
        # can't run — built-in reports must still work unchanged (AC).
        mock_run.side_effect = [
            mock_result(returncode=1, stderr='task: command not found'),
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
        ]
        response = client.get('/?report=next')
        assert response.status_code == 200
        assert b'not found' not in response.data
        assert mock_run.call_args[0][0] == task_args('export', 'next')


# ---------------------------------------------------------------------------
# Route tests: GET /list
# ---------------------------------------------------------------------------

class TestShowTaskList:
    """/list is the combined stats + list screen (ON-62/B0)."""

    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.side_effect = [
            CONFIG_WITH_ESTIMATE_UDA,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
            mock_result(stdout='- Task A\n'),
        ]
        response = client.get('/list')
        assert response.status_code == 200
        assert b'Test task' in response.data
        assert b'Back to OneTask' in response.data

    @patch('app.subprocess.run')
    def test_empty_report_shows_placeholder(self, mock_run, client):
        mock_run.side_effect = [
            CONFIG_WITH_ESTIMATE_UDA,
            mock_result(stdout='[]'),
            mock_result(stdout=''),
        ]
        response = client.get('/list')
        assert response.status_code == 200
        assert b'No tasks to display' in response.data

    @patch('app.subprocess.run')
    def test_custom_report_param(self, mock_run, client):
        mock_run.side_effect = [
            CONFIG_WITH_ESTIMATE_UDA,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
            mock_result(stdout=''),
        ]
        client.get('/list?report=focus')
        assert mock_run.call_args_list[1][0][0] == task_args('export', 'focus')

    @patch('app.subprocess.run')
    def test_task_row_links_to_main_view(self, mock_run, client):
        mock_run.side_effect = [
            CONFIG_WITH_ESTIMATE_UDA,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
            mock_result(stdout=''),
        ]
        response = client.get('/list')
        assert f'/?report=next&task={SAMPLE_TASK["uuid"]}'.encode() in response.data

    @patch('app.subprocess.run')
    def test_marks_default_estimate_when_uda_not_configured(self, mock_run, client):
        mock_run.side_effect = [
            CONFIG_WITHOUT_ESTIMATE_UDA,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
            mock_result(stdout=''),
        ]
        response = client.get('/list')
        assert response.status_code == 200
        assert b'(default)' in response.data

    @patch('app.subprocess.run')
    def test_unknown_report_falls_back_to_next_with_notice(self, mock_run, client):
        mock_run.side_effect = [
            CONFIG_WITH_REPORTS,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
            mock_result(stdout=''),
        ]
        response = client.get('/list?report=totallyBogusReportName')
        assert response.status_code == 200
        assert b'Report "totallyBogusReportName" not found' in response.data
        assert mock_run.call_args_list[1][0][0] == task_args('export', 'next')

    @patch('app.subprocess.run')
    def test_stats_header_reflects_pending_and_estimate(self, mock_run, client):
        task = {**SAMPLE_TASK, 'estimate': '30m'}
        mock_run.side_effect = [
            CONFIG_WITH_ESTIMATE_UDA,
            mock_result(stdout=json.dumps([task, task])),  # 2 x 30m = 1h
            mock_result(stdout='- Task A\n- Task B\n'),    # 2 completed today
        ]
        response = client.get('/list')
        assert response.status_code == 200
        assert b'>2<' in response.data  # pending count
        assert b'>1h<' in response.data  # estimate remaining
        assert b'Done today' in response.data

    @patch('app.subprocess.run')
    def test_stats_header_uses_default_estimate_when_uda_not_configured(self, mock_run, client):
        # ON-66/A2's per-task fallback flows straight into the header total —
        # no separate branch needed here.
        task = {**SAMPLE_TASK, 'estimate': ''}
        mock_run.side_effect = [
            CONFIG_WITHOUT_ESTIMATE_UDA,
            mock_result(stdout=json.dumps([task, task])),  # 2 x 25m default = 50m
            mock_result(stdout=''),
        ]
        response = client.get('/list')
        assert response.status_code == 200
        assert b'>50m<' in response.data

    @patch('app.subprocess.run')
    def test_completed_deleted_section_hidden_when_window_unset(self, mock_run, client, monkeypatch):
        monkeypatch.delenv('ONETASK_COMPLETED_WINDOW', raising=False)
        mock_run.side_effect = [
            CONFIG_WITH_ESTIMATE_UDA,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
            mock_result(stdout=''),
        ]
        response = client.get('/list')
        assert response.status_code == 200
        assert b'Completed or deleted' not in response.data
        # No 4th call — the query is skipped entirely, not just hidden in the template.
        assert mock_run.call_count == 3

    @patch('app.subprocess.run')
    def test_completed_deleted_section_shown_with_rows(self, mock_run, client, monkeypatch):
        monkeypatch.setenv('ONETASK_COMPLETED_WINDOW', '7days')
        completed = {**SAMPLE_TASK, 'uuid': 'aaaa1111-0000-0000-0000-000000000000',
                     'description': 'Finished thing', 'status': 'completed', 'end': '20260827T120000Z'}
        deleted = {**SAMPLE_TASK, 'uuid': 'bbbb2222-0000-0000-0000-000000000000',
                   'description': 'Removed thing', 'status': 'deleted', 'end': '20260826T120000Z'}
        mock_run.side_effect = [
            CONFIG_WITH_ESTIMATE_UDA,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
            mock_result(stdout=''),
            mock_result(stdout=json.dumps([completed, deleted])),
        ]
        response = client.get('/list')
        assert response.status_code == 200
        body = response.data.decode()
        assert 'Completed or deleted' in body
        assert 'Finished thing' in body
        assert 'Removed thing' in body
        assert 'Uncomplete' in body
        assert 'Restore' in body
        assert 'status-completed' in body
        assert 'status-deleted' in body
        assert mock_run.call_count == 4

    @patch('app.subprocess.run')
    def test_completed_deleted_sorted_most_recent_first(self, mock_run, client, monkeypatch):
        monkeypatch.setenv('ONETASK_COMPLETED_WINDOW', '7days')
        older = {**SAMPLE_TASK, 'uuid': 'aaaa1111-0000-0000-0000-000000000000',
                 'description': 'Older one', 'status': 'completed', 'end': '20260825T120000Z'}
        newer = {**SAMPLE_TASK, 'uuid': 'bbbb2222-0000-0000-0000-000000000000',
                 'description': 'Newer one', 'status': 'completed', 'end': '20260827T120000Z'}
        mock_run.side_effect = [
            CONFIG_WITH_ESTIMATE_UDA,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
            mock_result(stdout=''),
            mock_result(stdout=json.dumps([older, newer])),  # deliberately out of order
        ]
        response = client.get('/list')
        body = response.data.decode()
        assert body.index('Newer one') < body.index('Older one')

    @patch('app.subprocess.run')
    def test_completed_deleted_empty_state_message(self, mock_run, client, monkeypatch):
        monkeypatch.setenv('ONETASK_COMPLETED_WINDOW', '7days')
        mock_run.side_effect = [
            CONFIG_WITH_ESTIMATE_UDA,
            mock_result(stdout=json.dumps([SAMPLE_TASK])),
            mock_result(stdout=''),
            mock_result(stdout='[]'),
        ]
        response = client.get('/list')
        assert b'Nothing completed or deleted recently' in response.data


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
        assert mock_run.call_args[0][0] == write_task_args('add', 'Buy', 'milk', '+shopping')

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
        assert mock_run.call_args[0][0] == write_task_args('abc12345', 'annotate', 'My note')

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
        assert mock_run.call_args[0][0] == write_task_args('abc12345', 'denotate', 'my note')

    @patch('app.subprocess.run')
    def test_special_characters_decoded_correctly(self, mock_run, client):
        # Annotation text containing double quotes
        mock_run.return_value = mock_result(stdout='Denotated.')
        response = client.delete('/task/abc12345/annotations/note%20with%20%22quotes%22')
        assert response.status_code == 200
        assert mock_run.call_args[0][0] == write_task_args('abc12345', 'denotate', 'note with "quotes"')

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
        assert mock_run.call_args[0][0] == write_task_args('abc12345', 'modify', 'due:2026-04-15')

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
        assert mock_run.call_args[0][0] == write_task_args('abc12345', 'modify', 'due:')

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
        mock_run.side_effect = [
            mock_result(stdout='uda.url.type=string\n'),  # get_resolved_config
            mock_result(stdout='Modified 1 task.'),       # modify
        ]
        response = client.post('/task/abc12345/url', json={'url': 'https://example.com'})
        assert response.status_code == 200
        assert mock_run.call_args[0][0] == write_task_args('abc12345', 'modify', 'url:https://example.com')

    def test_missing_url_returns_400(self, client):
        response = client.post('/task/abc12345/url', json={})
        assert response.status_code == 400

    @patch('app.subprocess.run')
    def test_url_uda_not_configured_returns_400_without_firing_modify(self, mock_run, client):
        # ON-68/A4: stock TaskWarrior has no `url` UDA — reject cleanly and
        # never attempt the modify that TaskWarrior would reject anyway.
        mock_run.return_value = mock_result(stdout='dateformat=Y-M-D\n')
        response = client.post('/task/abc12345/url', json={'url': 'https://example.com'})
        assert response.status_code == 400
        assert mock_run.call_count == 1

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.side_effect = [
            mock_result(stdout='uda.url.type=string\n'),
            mock_result(returncode=1, stderr='error'),
        ]
        response = client.post('/task/abc12345/url', json={'url': 'https://example.com'})
        assert response.status_code == 500

    @patch('app.subprocess.run')
    def test_subprocess_exception_returns_500(self, mock_run, client):
        mock_run.side_effect = [
            mock_result(stdout='uda.url.type=string\n'),
            Exception('unexpected error'),
        ]
        response = client.post('/task/abc12345/url', json={'url': 'https://example.com'})
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: DELETE /task/<id>/url
# ---------------------------------------------------------------------------

class TestRemoveTaskUrl:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.side_effect = [
            mock_result(stdout='uda.url.type=string\n'),
            mock_result(stdout='Modified 1 task.'),
        ]
        response = client.delete('/task/abc12345/url')
        assert response.status_code == 200
        assert mock_run.call_args[0][0] == write_task_args('abc12345', 'modify', 'url:')

    @patch('app.subprocess.run')
    def test_url_uda_not_configured_returns_400_without_firing_modify(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='dateformat=Y-M-D\n')
        response = client.delete('/task/abc12345/url')
        assert response.status_code == 400
        assert mock_run.call_count == 1

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.side_effect = [
            mock_result(stdout='uda.url.type=string\n'),
            mock_result(returncode=1, stderr='error'),
        ]
        response = client.delete('/task/abc12345/url')
        assert response.status_code == 500

    @patch('app.subprocess.run')
    def test_subprocess_exception_returns_500(self, mock_run, client):
        mock_run.side_effect = [
            mock_result(stdout='uda.url.type=string\n'),
            Exception('unexpected error'),
        ]
        response = client.delete('/task/abc12345/url')
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: GET /stats
# ---------------------------------------------------------------------------

class TestShowStats:
    """/stats is now a redirect to the combined /list view (ON-62/B0)."""

    def test_redirects_to_list(self, client):
        response = client.get('/stats')
        assert response.status_code == 302
        assert response.headers['Location'] == '/list?report=next'

    def test_redirect_preserves_report_param(self, client):
        response = client.get('/stats?report=focus')
        assert response.status_code == 302
        assert response.headers['Location'] == '/list?report=focus'


# ---------------------------------------------------------------------------
# Route tests: POST /task/<id>/delete
# ---------------------------------------------------------------------------

class TestDeleteTask:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Deleted 1 task.')
        response = client.post('/task/abc12345/delete')
        assert response.status_code == 200
        assert response.get_json()['status'] == 'success'
        # Soft delete (TaskWarrior `delete`), not `purge` — and hooks stay
        # on since this is a mutating call (ON-93).
        assert mock_run.call_args[0][0] == write_task_args('abc12345', 'delete')

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(returncode=1, stderr='Task does not exist')
        response = client.post('/task/bad-id/delete')
        assert response.status_code == 500
        assert response.get_json()['status'] == 'error'

    @patch('app.subprocess.run')
    def test_timeout_returns_408(self, mock_run, client):
        mock_run.side_effect = subprocess.TimeoutExpired(['task'], 30)
        response = client.post('/task/abc12345/delete')
        assert response.status_code == 408


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
        assert mock_run.call_args[0][0] == task_args('tag:work', 'export')

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
        assert mock_run.call_args[0][0] == write_task_args('abc12345', 'modify', 'description:New task name')

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
    def test_happy_path_custom_scheme(self, mock_run, client):
        mock_run.side_effect = [
            mock_result(stdout='uda.priority.values=1,2,3\n'),  # get_resolved_config
            mock_result(stdout='Modified 1 task.'),             # modify
        ]
        response = client.post('/task/abc12345/priority', json={'priority': '1'})
        assert response.status_code == 200
        assert response.get_json()['status'] == 'success'
        assert mock_run.call_args[0][0] == write_task_args('abc12345', 'modify', 'priority:1')

    @patch('app.subprocess.run')
    def test_happy_path_native_scheme(self, mock_run, client):
        mock_run.side_effect = [
            mock_result(stdout='dateformat=Y-M-D\n'),  # no uda.priority.values -> native H/M/L
            mock_result(stdout='Modified 1 task.'),
        ]
        response = client.post('/task/abc12345/priority', json={'priority': 'H'})
        assert response.status_code == 200
        assert mock_run.call_args[0][0] == write_task_args('abc12345', 'modify', 'priority:H')

    def test_missing_priority_returns_400(self, client):
        response = client.post('/task/abc12345/priority', json={})
        assert response.status_code == 400

    @patch('app.subprocess.run')
    def test_value_not_in_configured_scheme_returns_400(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='uda.priority.values=1,2,3\n')
        response = client.post('/task/abc12345/priority', json={'priority': '5'})
        assert response.status_code == 400

    @patch('app.subprocess.run')
    def test_native_scheme_rejects_legacy_numeric_value(self, mock_run, client):
        # ON-67/A3: on stock TaskWarrior (H/M/L), a blind '1' must be rejected
        # instead of silently accepted, which is exactly the bug this story fixes.
        mock_run.return_value = mock_result(stdout='dateformat=Y-M-D\n')
        response = client.post('/task/abc12345/priority', json={'priority': '1'})
        assert response.status_code == 400

    @patch('app.subprocess.run')
    def test_unknown_scheme_returns_400_without_firing_modify(self, mock_run, client):
        # Degrade case from the AC: scheme resolves to no usable values ->
        # reject cleanly, and never attempt the destructive modify call.
        mock_run.return_value = mock_result(stdout='uda.priority.values=,,,\n')
        response = client.post('/task/abc12345/priority', json={'priority': '1'})
        assert response.status_code == 400
        assert mock_run.call_count == 1

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.side_effect = [
            mock_result(stdout='uda.priority.values=1,2,3\n'),
            mock_result(returncode=1, stderr='error'),
        ]
        response = client.post('/task/abc12345/priority', json={'priority': '2'})
        assert response.status_code == 500

    @patch('app.subprocess.run')
    def test_subprocess_exception_returns_500(self, mock_run, client):
        mock_run.side_effect = [
            mock_result(stdout='uda.priority.values=1,2,3\n'),
            Exception('unexpected'),
        ]
        response = client.post('/task/abc12345/priority', json={'priority': '2'})
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Route tests: DELETE /task/<id>/priority
# ---------------------------------------------------------------------------

class TestRemoveTaskPriority:
    @patch('app.subprocess.run')
    def test_happy_path(self, mock_run, client):
        mock_run.return_value = mock_result(stdout='Modified 1 task.')
        response = client.delete('/task/abc12345/priority')
        assert response.status_code == 200
        assert mock_run.call_args[0][0] == write_task_args('abc12345', 'modify', 'priority:')

    @patch('app.subprocess.run')
    def test_subprocess_failure_returns_500(self, mock_run, client):
        mock_run.return_value = mock_result(returncode=1, stderr='error')
        response = client.delete('/task/abc12345/priority')
        assert response.status_code == 500
