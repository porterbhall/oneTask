import json
import os
import subprocess
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, redirect, url_for

app = Flask(__name__, template_folder='templates', static_folder='static')

# Disable debug mode in production to avoid Werkzeug error pages
app.config['DEBUG'] = False

@app.before_request
def require_password():
    """Require HTTP Basic Auth if ONETASK_PASSWORD is set in the environment."""
    expected = os.environ.get('ONETASK_PASSWORD')
    if not expected:
        return
    auth = request.authorization
    if not auth or auth.password != expected:
        return Response(
            'Authentication required',
            401,
            {'WWW-Authenticate': 'Basic realm="OneTask"'}
        )

# Global overrides applied to every invocation so behavior doesn't ride on the
# user's interactive .taskrc settings (confirmation prompts, nag/verbose lines
# polluting parsed output). rc.hooks=off is applied separately, per-call, by
# run_task_command — see its `hooks` parameter (ON-93).
RC_OVERRIDES = ['rc.confirmation=off', 'rc.nag=', 'rc.verbose=nothing']

def run_task_command(args, timeout=30, hooks=False):
    """Run a TaskWarrior command via subprocess with timeout.

    hooks=False (default) appends rc.hooks=off, keeping read/query calls
    (export, _show, completed, ...) from firing the user's on-launch/on-exit
    hooks on every page load (ON-65). Mutating calls — anything that changes
    task state — must pass hooks=True so on-modify/on-add hooks fire the same
    way they do from the CLI (ON-93).
    """
    overrides = RC_OVERRIDES if hooks else RC_OVERRIDES + ['rc.hooks=off']
    try:
        result = subprocess.run(
            ['task'] + overrides + args,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"TaskWarrior command timed out after {timeout} seconds")
    except Exception as e:
        raise Exception(f"TaskWarrior command failed: {str(e)}")

def get_resolved_config():
    """Read TaskWarrior's resolved configuration via `task _show`.

    Returns a dict of the fully-resolved key/value config (UDAs, their types
    and values, etc.) as TaskWarrior itself resolves it from whatever rc file
    and includes are in effect. There's no path parameter here on purpose:
    TaskWarrior resolves its own config, and this never accepts or reads a
    user-supplied .taskrc path directly.
    """
    try:
        result = run_task_command(['_show'])
    except Exception:
        return {}

    if result.returncode != 0:
        return {}

    config = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        config[key.strip()] = value.strip()
    return config

def get_tasks_from_report(report_name='next'):
    """Get tasks from specified TaskWarrior report"""
    try:
        # Use TaskWarrior's export with report parameter - preserves filtering and ordering
        result = run_task_command(['export', report_name])
        
        if result.returncode != 0:
            raise Exception(f"TaskWarrior export {report_name} failed: {result.stderr}")
        
        if not result.stdout.strip():
            return []
        
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse TaskWarrior JSON: {str(e)}")
    except Exception as e:
        print(f"Error getting tasks from {report_name}: {e}")
        return []

# Fallback Pomodoro length used when the estimate UDA isn't configured at all
# (stock TaskWarrior has no `estimate` field, so there's nothing per-task to read).
DEFAULT_ESTIMATE_SECONDS = 25 * 60

def get_default_duration_seconds():
    """(seconds, configured) for the optional ONETASK_DEFAULT_DURATION
    override (ON-92) — lets users tune the un-estimated-task fallback
    instead of being stuck with DEFAULT_ESTIMATE_SECONDS, including 0 to
    start counting up immediately rather than counting down first.

    Requires at least one digit to count as 'configured': the shared
    duration parser silently returns 0 for pure garbage (no digits at
    all), which would otherwise be indistinguishable from a deliberate
    0=count-up value. Unset or unparseable both fall back to the
    built-in default, unconfigured, so the caller still shows the
    'set an estimate' notice rather than pretending this was intentional.
    """
    raw = os.environ.get('ONETASK_DEFAULT_DURATION', '').strip()
    if not raw or not any(c.isdigit() for c in raw):
        return DEFAULT_ESTIMATE_SECONDS, False
    return convert_taskwarrior_estimate_to_seconds(raw), True

def estimate_uda_defined(config):
    """Whether the `estimate` UDA is configured, per resolved TaskWarrior config (ON-66/A2)."""
    return any(key.startswith('uda.estimate.') for key in config)

def url_uda_defined(config):
    """Whether the `url` UDA is configured, per resolved TaskWarrior config (ON-68/A4)."""
    return any(key.startswith('uda.url.') for key in config)

def get_report_names(config):
    """Set of valid TaskWarrior report names, derived from resolved config —
    every report defines a `report.<name>.columns` key (ON-69/A5)."""
    names = set()
    for key in config:
        if key.startswith('report.') and key.endswith('.columns'):
            names.add(key[len('report.'):-len('.columns')])
    return names

def resolve_report_name(requested, report_names):
    """(effective_name, was_invalid) for a requested report. Falls back to
    'next' when the requested report isn't in the known set. If the known
    set is empty (config couldn't be resolved), trust the request as-is
    rather than second-guess it — built-in reports must keep working even
    if this detection layer can't run (ON-69/A5)."""
    if not report_names or requested in report_names:
        return requested, False
    return 'next', True

# Native TaskWarrior priority scheme, used when uda.priority.values isn't
# customized (this is also literally what a stock install resolves to).
DEFAULT_PRIORITY_VALUES = ('H', 'M', 'L')

def get_priority_values(config):
    """Ordered list of valid priority values (highest first), per resolved
    config's `uda.priority.values`. Falls back to native H/M/L when the key
    is entirely absent (matches TaskWarrior's own default). Returns an empty
    list if the key resolves to no usable values — callers should treat that
    as an unknown scheme and degrade rather than guess (ON-67/A3)."""
    if 'uda.priority.values' not in config:
        return list(DEFAULT_PRIORITY_VALUES)
    return [v for v in config['uda.priority.values'].split(',') if v]

def priority_rank(value, priority_values):
    """Sort rank for a priority value within the given scheme; unset or
    unrecognized values sort last."""
    if not value:
        return float('inf')
    try:
        return priority_values.index(value)
    except ValueError:
        return float('inf')

def format_task_for_display(task, estimate_configured=True, priority_values=None,
                             default_duration_seconds=DEFAULT_ESTIMATE_SECONDS,
                             default_duration_configured=False):
    """Convert TaskWarrior task to Milkbox-compatible format"""
    if priority_values is None:
        priority_values = list(DEFAULT_PRIORITY_VALUES)

    # Priority is whatever value TaskWarrior actually has for this task
    # (native H/M/L, a custom numeric scheme, or unset) — never assumed
    # to be a specific numeric scheme (ON-67/A3).
    priority = task.get('priority') or ''

    # Get estimate and convert to seconds. If the estimate UDA isn't configured
    # at all, there's no per-task value to read, so fall back to a default
    # Pomodoro length rather than a dead 0-second timer. The UDA can also be
    # configured but left unset (or unparseable) on a specific task — same
    # dead-timer symptom, different cause — so treat a 0-second result the
    # same way (ON-84).
    if estimate_configured:
        estimate = task.get('estimate', '')
        total_seconds = convert_taskwarrior_estimate_to_seconds(estimate)
    else:
        estimate = ''
        total_seconds = 0

    if total_seconds:
        estimate_is_default = False
    else:
        # Falling back — to an admin-configured default if there is one
        # (ON-92; may itself be 0, meaning count up immediately), otherwise
        # the built-in length. A configured default is intended behavior,
        # so the notice below only fires for the true "nothing configured
        # anywhere" case.
        total_seconds = default_duration_seconds
        estimate_is_default = not default_duration_configured

    # Create short task identifier from UUID (first 8 characters)
    uuid = task.get('uuid', '')
    short_id = uuid[:8] if uuid else 'unknown'

    # Format the task for display
    formatted_task = {
        "name": task.get('description', 'No description'),
        "priority": priority,
        "priority_rank": priority_rank(priority, priority_values),
        "time_estimate": estimate,
        "task_id": task.get('uuid', ''),  # Use UUID as primary identifier
        "uuid": task.get('uuid', ''),
        "total_seconds": total_seconds,
        "estimate_is_default": estimate_is_default,
        "task_url": task.get('url', 'none'),
        "short_id": short_id,
        "annotations": task.get('annotations', []),
        "due_date": task.get('due', None),
        "tags": task.get('tags', [])
    }

    # Format display name — omit the prefix entirely when priority is unset,
    # rather than implying a priority the task doesn't actually have.
    formatted_task["formatted_task"] = (
        f"{priority}: {formatted_task['name']}" if priority else formatted_task['name']
    )

    return formatted_task

def convert_taskwarrior_estimate_to_seconds(estimate):
    """Convert TaskWarrior estimate format to seconds"""
    if not estimate:
        return 0
    
    total_seconds = 0
    estimate = estimate.lower()
    
    # Handle TaskWarrior format: '5mins', '2h', '1h30m'
    current_number = ''
    for char in estimate:
        if char.isdigit():
            current_number += char
        elif char.isalpha():
            if current_number:
                num = int(current_number)
                if char == 'h':
                    total_seconds += num * 3600
                elif char == 'm':
                    total_seconds += num * 60
                elif char == 's':
                    total_seconds += num
                current_number = ''
    
    # Add any remaining number as minutes if no unit specified
    if current_number:
        total_seconds += int(current_number) * 60
    
    return total_seconds

def format_due_date_display(due_date):
    """Format a TaskWarrior due date (ISO8601 basic, e.g. 20260705T070000Z) for display"""
    if not due_date:
        return None
    try:
        return datetime.strptime(due_date, '%Y%m%dT%H%M%SZ').strftime('%b %d, %Y')
    except ValueError:
        return due_date

def format_estimate_display(total_seconds):
    """Format a task's time estimate in seconds as a short human string, or None if unset"""
    if not total_seconds:
        return None
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m"

def sorting_key(task_details):
    """Sort tasks by priority rank (within the actual configured scheme,
    highest priority first), then by time estimate, then by name."""
    return (task_details["priority_rank"],
            task_details["total_seconds"],
            task_details["name"])

@app.route('/')
def show_list():
    """Main route - display tasks from specified report"""
    print(f"DEBUG: Starting show_list()")
    
    # Get report name from query string (default to 'next')
    requested_report_name = request.args.get('report', default='next')

    try:
        # Get tasks from TaskWarrior
        config = get_resolved_config()
        estimate_configured = estimate_uda_defined(config)
        priority_values = get_priority_values(config)
        url_configured = url_uda_defined(config)
        default_duration_seconds, default_duration_configured = get_default_duration_seconds()

        # ON-69/A5: an unknown report (typo, or a custom report a stock
        # install doesn't have) falls back to 'next' with a clear notice,
        # instead of silently rendering as an empty/misleading report.
        report_name, report_invalid = resolve_report_name(requested_report_name, get_report_names(config))
        print(f"DEBUG: Using report: {report_name}")

        raw_tasks = get_tasks_from_report(report_name)
        print(f"DEBUG: Got {len(raw_tasks)} tasks from TaskWarrior")

        if not raw_tasks:
            tasks = [{'name': 'No tasks to display', 'priority': '', 'total_seconds': 0, 'estimate_is_default': False, 'formatted_task': 'No tasks to display', 'task_id': '', 'uuid': '', 'task_url': 'none', 'short_id': '', 'annotations': [], 'due_date': None, 'tags': []}]
        else:
            # Convert TaskWarrior tasks to Milkbox format
            # Note: raw_tasks are already sorted by urgency from get_tasks_from_report()
            tasks = [format_task_for_display(task, estimate_configured, priority_values,
                                              default_duration_seconds, default_duration_configured)
                     for task in raw_tasks]

        print(f"DEBUG: Formatted {len(tasks)} tasks for display")

        # Prepare data for template (matching Milkbox structure)
        task_ids = [task["task_id"] for task in tasks]
        uuids = [task["uuid"] for task in tasks]
        formatted_tasks = [task["formatted_task"] for task in tasks]
        task_urls = [task["task_url"] for task in tasks]
        remaining_seconds = [task["total_seconds"] for task in tasks]
        estimate_is_default = [task["estimate_is_default"] for task in tasks]
        short_ids = [task["short_id"] for task in tasks]
        task_annotations = [task["annotations"] for task in tasks]
        task_due_dates = [task["due_date"] for task in tasks]
        task_tags = [task["tags"] for task in tasks]
        task_names = [task["name"] for task in tasks]
        task_priorities = [task["priority"] for task in tasks]
        num_tasks = len(tasks)

        # Jump to a specific task (e.g. from the list view) by UUID
        current_task_index = 0
        requested_uuid = request.args.get('task')
        if requested_uuid and requested_uuid in uuids:
            current_task_index = uuids.index(requested_uuid)

        return render_template('task.html',
                             formatted_tasks=formatted_tasks,
                             task_urls=task_urls,
                             remaining_seconds=remaining_seconds,
                             estimate_is_default=estimate_is_default,
                             priority_values=priority_values,
                             url_configured=url_configured,
                             report_invalid=report_invalid,
                             requested_report_name=requested_report_name,
                             num_tasks=num_tasks,
                             task_id=task_ids,
                             taskseries_id=uuids,  # Use UUID as taskseries_id for compatibility
                             truelist_id=uuids,    # Use UUID as truelist_id for compatibility
                             short_ids=short_ids,
                             task_annotations=task_annotations,
                             task_due_dates=task_due_dates,
                             task_tags=task_tags,
                             task_names=task_names,
                             task_priorities=task_priorities,
                             currentTaskIndex=current_task_index,
                             report_name=report_name)
        
    except TimeoutError as e:
        error_msg = f"TaskWarrior timeout: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return f"""
        <html>
        <head><title>OneTask - Timeout</title></head>
        <body style="font-family: Arial, sans-serif; margin: 40px; color: #333;">
            <h1 style="color: #d32f2f;">TaskWarrior Timeout</h1>
            <p>TaskWarrior is taking too long to respond.</p>
            <p><strong>What you can try:</strong></p>
            <ul>
                <li>Wait a moment and <a href="javascript:location.reload()">refresh the page</a></li>
                <li>Check if TaskWarrior is working: <code>task --version</code></li>
                <li>Try again in a few minutes</li>
            </ul>
            <p style="color: #666; font-size: 12px;">Error: {error_msg}</p>
        </body>
        </html>
        """, 408
    except Exception as e:
        error_msg = f"TaskWarrior error: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return f"""
        <html>
        <head><title>OneTask - Error</title></head>
        <body style="font-family: Arial, sans-serif; margin: 40px; color: #333;">
            <h1 style="color: #d32f2f;">TaskWarrior Error</h1>
            <p>Unable to connect to TaskWarrior.</p>
            <p><strong>What you can try:</strong></p>
            <ul>
                <li>Check if TaskWarrior is installed: <code>task --version</code></li>
                <li>Verify your TaskWarrior configuration</li>
                <li><a href="javascript:location.reload()">Refresh the page</a></li>
            </ul>
            <p style="color: #666; font-size: 12px;">Error: {error_msg}</p>
        </body>
        </html>
        """, 500

def count_completed_today():
    """Count of tasks completed today, via `task completed end:today`."""
    try:
        completed_result = run_task_command(['completed', 'end:today'])
        if completed_result.returncode == 0 and completed_result.stdout.strip():
            # Count actual task entries by looking for lines that start with " - " (completed task indicator)
            output_lines = completed_result.stdout.strip().split('\n')
            task_lines = [line for line in output_lines if line.strip().startswith('- ')]
            return len(task_lines)
    except Exception as e:
        print(f"DEBUG: Error getting completed tasks: {e}")
    return 0

@app.route('/list')
def show_task_list():
    """Combined stats + list view for a report (ON-62/B0): a stats summary
    header (pending, completed today, estimate remaining) above the full
    task list, reached from the timer view's top-left 'List' link."""
    requested_report_name = request.args.get('report', default='next')

    try:
        config = get_resolved_config()
        estimate_configured = estimate_uda_defined(config)
        priority_values = get_priority_values(config)
        default_duration_seconds, default_duration_configured = get_default_duration_seconds()
        report_name, report_invalid = resolve_report_name(requested_report_name, get_report_names(config))
        raw_tasks = get_tasks_from_report(report_name)
        tasks = [format_task_for_display(task, estimate_configured, priority_values,
                                          default_duration_seconds, default_duration_configured)
                 for task in raw_tasks] if raw_tasks else []
        for task in tasks:
            task['due_date_display'] = format_due_date_display(task['due_date'])
            task['estimate_display'] = format_estimate_display(task['total_seconds'])

        # Stats summary derived from the same task fetch used for the list
        # below — one TaskWarrior export covers both, where /stats and
        # /list previously each fetched it independently.
        pending_count = len(tasks)
        total_estimate_seconds = sum(task['total_seconds'] for task in tasks)
        estimate_display = format_estimate_display(total_estimate_seconds) or '0m'
        completed_today = count_completed_today()

        return render_template('list.html',
                             tasks=tasks,
                             report_name=report_name,
                             report_invalid=report_invalid,
                             requested_report_name=requested_report_name,
                             pending_count=pending_count,
                             completed_today=completed_today,
                             estimate_display=estimate_display)

    except Exception as e:
        error_msg = f"Error building task list: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return f"""
        <html>
        <head><title>OneTask - List Error</title></head>
        <body style="font-family: Arial, sans-serif; margin: 40px; color: #333;">
            <h1 style="color: #d32f2f;">List Error</h1>
            <p>Unable to build the task list.</p>
            <p><a href="/">← Go back to OneTask</a></p>
            <p style="color: #666; font-size: 12px;">Error: {error_msg}</p>
        </body>
        </html>
        """, 500

@app.route('/complete_task', methods=['POST'])
def complete_task():
    """Complete a task using TaskWarrior"""
    try:
        # Get task ID from request (could be ID or UUID)
        task_id = request.json.get('task_id')
        
        if not task_id:
            return jsonify({'error': 'No task ID provided', 'status': 'error'}), 400
        
        print(f"DEBUG: Completing task {task_id}")
        
        # Complete the task via TaskWarrior
        result = run_task_command([str(task_id), 'done'], hooks=True)
        
        if result.returncode != 0:
            error_msg = f"TaskWarrior completion failed: {result.stderr}"
            print(f"DEBUG: {error_msg}")
            return jsonify({'error': error_msg, 'status': 'error'}), 500
        
        print(f"DEBUG: Task {task_id} completed successfully")
        print(f"DEBUG: TaskWarrior output: {result.stdout}")
        
        completed_task_info = {
            'task_id': task_id,
            'status': 'completed',
            'message': 'Task marked as completed successfully',
            'taskwarrior_output': result.stdout.strip()
        }
        
        return jsonify(completed_task_info)
        
    except TimeoutError as e:
        error_msg = f"TaskWarrior timeout: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'timeout'}), 408
    except Exception as e:
        error_msg = f"Error completing task: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'error'}), 500

@app.route('/uncomplete_task', methods=['POST'])
def uncomplete_task():
    """Uncomplete a task using TaskWarrior"""
    try:
        # Get task ID from request (UUID)
        task_id = request.json.get('task_id')
        
        if not task_id:
            return jsonify({'error': 'No task ID provided', 'status': 'error'}), 400
        
        print(f"DEBUG: Uncompleting task {task_id}")
        
        # TaskWarrior 3.x doesn't have a direct uncomplete command
        # We need to modify the task to set status back to pending
        result = run_task_command([str(task_id), 'modify', 'status:pending'], hooks=True)
        
        if result.returncode != 0:
            error_msg = f"TaskWarrior uncomplete failed: {result.stderr}"
            print(f"DEBUG: {error_msg}")
            return jsonify({'error': error_msg, 'status': 'error'}), 500
        
        print(f"DEBUG: Task {task_id} uncompleted successfully")
        print(f"DEBUG: TaskWarrior output: {result.stdout}")
        
        uncompleted_task_info = {
            'task_id': task_id,
            'status': 'uncompleted',
            'message': 'Task successfully marked as incomplete',
            'taskwarrior_output': result.stdout.strip()
        }
        
        return jsonify(uncompleted_task_info)
        
    except TimeoutError as e:
        error_msg = f"TaskWarrior timeout: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'timeout'}), 408
    except Exception as e:
        error_msg = f"Error uncompleting task: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'error'}), 500

@app.route('/capture', methods=['POST'])
def capture_task():
    """Capture a new task using TaskWarrior native syntax"""
    try:
        # Get task text from form data or JSON
        task_text = request.form.get('task') or request.json.get('task')
        
        if not task_text:
            return jsonify({'error': 'No task text provided', 'status': 'error'}), 400
        
        print(f"DEBUG: Capturing task: {task_text}")
        
        # Add the task via TaskWarrior
        # Split the task text and add it using 'task add'
        result = run_task_command(['add'] + task_text.split(), hooks=True)
        
        if result.returncode != 0:
            error_msg = f"TaskWarrior add failed: {result.stderr}"
            print(f"DEBUG: {error_msg}")
            return jsonify({'error': error_msg, 'status': 'failed'}), 400
        
        print(f"DEBUG: Task captured successfully")
        print(f"DEBUG: TaskWarrior output: {result.stdout}")
        
        return jsonify({
            'status': 'success', 
            'message': 'Task added successfully',
            'taskwarrior_output': result.stdout.strip()
        }), 200
        
    except TimeoutError as e:
        error_msg = f"TaskWarrior timeout: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'timeout'}), 408
    except Exception as e:
        error_msg = f"Error capturing task: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'failed'}), 500

@app.route('/stats')
def show_stats():
    """Deprecated standalone stats page — the stats summary now lives as a
    header on /list (ON-62/B0). Redirect so old bookmarks/links keep working."""
    report_name = request.args.get('report', default='next')
    return redirect(url_for('show_task_list', report=report_name))

@app.errorhandler(500)
def internal_error(error):
    return f"""
    <html>
    <head><title>OneTask - Server Error</title></head>
    <body style="font-family: Arial, sans-serif; margin: 40px; color: #333;">
        <h1 style="color: #d32f2f;">Server Error</h1>
        <p>Something went wrong with the OneTask application.</p>
        <p><strong>What you can try:</strong></p>
        <ul>
            <li><a href="javascript:location.reload()">Refresh the page</a></li>
            <li>Check if TaskWarrior is working</li>
            <li>Verify your TaskWarrior configuration</li>
        </ul>
        <p><a href="/">← Go back to OneTask</a></p>
    </body>
    </html>
    """, 500

@app.errorhandler(408)
def timeout_error(error):
    return f"""
    <html>
    <head><title>OneTask - Request Timeout</title></head>
    <body style="font-family: Arial, sans-serif; margin: 40px; color: #333;">
        <h1 style="color: #d32f2f;">Request Timeout</h1>
        <p>The request took too long to complete.</p>
        <p><strong>What you can try:</strong></p>
        <ul>
            <li>Wait a moment and <a href="javascript:location.reload()">try again</a></li>
            <li>Check if TaskWarrior is responding</li>
            <li>Try again in a few minutes</li>
        </ul>
        <p><a href="/">← Go back to OneTask</a></p>
    </body>
    </html>
    """, 408

@app.route('/task/<task_id>/annotations', methods=['GET'])
def get_task_annotations(task_id):
    """Get all annotations for a specific task"""
    try:
        # Get task details including annotations
        result = run_task_command([str(task_id), 'export'])
        
        if result.returncode != 0:
            return jsonify({'error': 'Task not found', 'status': 'error'}), 404
        
        task_data = json.loads(result.stdout)
        if not task_data:
            return jsonify({'error': 'Task not found', 'status': 'error'}), 404
        
        task = task_data[0]
        annotations = task.get('annotations', [])
        
        return jsonify({'annotations': annotations, 'status': 'success'})
        
    except Exception as e:
        error_msg = f"Error getting annotations: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'error'}), 500

@app.route('/task/<task_id>/annotations', methods=['POST'])
def add_task_annotation(task_id):
    """Add annotation to a task"""
    try:
        annotation_text = request.json.get('annotation')
        if not annotation_text:
            return jsonify({'error': 'Annotation text required', 'status': 'error'}), 400
        
        # Add annotation via TaskWarrior
        result = run_task_command([str(task_id), 'annotate', annotation_text], hooks=True)
        
        if result.returncode != 0:
            error_msg = f"TaskWarrior annotate failed: {result.stderr}"
            return jsonify({'error': error_msg, 'status': 'error'}), 500
        
        return jsonify({'status': 'success', 'message': 'Annotation added successfully'})
        
    except Exception as e:
        error_msg = f"Error adding annotation: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'error'}), 500

@app.route('/task/<task_id>/annotations/<annotation_text>', methods=['DELETE'])
def delete_task_annotation(task_id, annotation_text):
    """Delete specific annotation from a task by text"""
    try:
        # TaskWarrior denotate expects the annotation text, not index
        # URL decode the annotation text
        from urllib.parse import unquote
        decoded_text = unquote(annotation_text)
        
        print(f"DEBUG: Attempting to delete annotation: '{decoded_text}' from task {task_id}")
        
        result = run_task_command([str(task_id), 'denotate', decoded_text], hooks=True)
        
        if result.returncode != 0:
            error_msg = f"TaskWarrior denotate failed: {result.stderr.strip()}"
            print(f"DEBUG: {error_msg}")
            print(f"DEBUG: TaskWarrior stdout: {result.stdout.strip()}")
            return jsonify({'error': error_msg, 'status': 'error'}), 500
        
        print(f"DEBUG: Successfully deleted annotation from task {task_id}")
        return jsonify({'status': 'success', 'message': 'Annotation deleted successfully'})
        
    except Exception as e:
        error_msg = f"Error deleting annotation: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'error'}), 500

@app.route('/task/<task_id>/due', methods=['GET'])
def get_task_due_date(task_id):
    """Get due date for a specific task"""
    try:
        result = run_task_command([str(task_id), 'export'])
        
        if result.returncode != 0:
            return jsonify({'error': 'Task not found', 'status': 'error'}), 404
        
        task_data = json.loads(result.stdout)
        if not task_data:
            return jsonify({'error': 'Task not found', 'status': 'error'}), 404
        
        task = task_data[0]
        due_date = task.get('due', None)
        
        return jsonify({'due_date': due_date, 'status': 'success'})
        
    except Exception as e:
        error_msg = f"Error getting due date: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'error'}), 500

@app.route('/task/<task_id>/due', methods=['POST'])
def set_task_due_date(task_id):
    """Set or update due date for a task"""
    try:
        due_date = request.json.get('due_date')
        if not due_date:
            return jsonify({'error': 'Due date required', 'status': 'error'}), 400
        
        # Set due date via TaskWarrior
        result = run_task_command([str(task_id), 'modify', f'due:{due_date}'], hooks=True)
        
        if result.returncode != 0:
            error_msg = f"TaskWarrior modify due failed: {result.stderr}"
            return jsonify({'error': error_msg, 'status': 'error'}), 500
        
        return jsonify({'status': 'success', 'message': 'Due date updated successfully'})
        
    except Exception as e:
        error_msg = f"Error setting due date: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'error'}), 500

@app.route('/task/<task_id>/due', methods=['DELETE'])
def remove_task_due_date(task_id):
    """Remove due date from a task"""
    try:
        # Remove due date by setting it to empty
        result = run_task_command([str(task_id), 'modify', 'due:'], hooks=True)
        
        if result.returncode != 0:
            error_msg = f"TaskWarrior modify due failed: {result.stderr}"
            return jsonify({'error': error_msg, 'status': 'error'}), 500
        
        return jsonify({'status': 'success', 'message': 'Due date removed successfully'})
        
    except Exception as e:
        error_msg = f"Error removing due date: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'error'}), 500

@app.route('/task/<task_id>/url', methods=['GET'])
def get_task_url(task_id):
    try:
        result = run_task_command([str(task_id), 'export'])
        if result.returncode != 0:
            return jsonify({'error': 'Task not found', 'status': 'error'}), 404
        task_data = json.loads(result.stdout)
        if not task_data:
            return jsonify({'error': 'Task not found', 'status': 'error'}), 404
        url = task_data[0].get('url', None)
        return jsonify({'url': url, 'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/task/<task_id>/url', methods=['POST'])
def set_task_url(task_id):
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'URL required', 'status': 'error'}), 400
        # ON-68/A4: on stock TaskWarrior `url` isn't a known attribute, so
        # `modify url:...` would be rejected — check first rather than let
        # that raw TaskWarrior error surface to the user.
        if not url_uda_defined(get_resolved_config()):
            return jsonify({'error': 'URL feature not available (url UDA not configured)', 'status': 'error'}), 400
        result = run_task_command([str(task_id), 'modify', f'url:{url}'], hooks=True)
        if result.returncode != 0:
            return jsonify({'error': f'TaskWarrior modify failed: {result.stderr}', 'status': 'error'}), 500
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/task/<task_id>/url', methods=['DELETE'])
def remove_task_url(task_id):
    try:
        if not url_uda_defined(get_resolved_config()):
            return jsonify({'error': 'URL feature not available (url UDA not configured)', 'status': 'error'}), 400
        result = run_task_command([str(task_id), 'modify', 'url:'], hooks=True)
        if result.returncode != 0:
            return jsonify({'error': f'TaskWarrior modify failed: {result.stderr}', 'status': 'error'}), 500
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/task/<task_id>/tags', methods=['GET'])
def get_task_tags(task_id):
    try:
        result = run_task_command([str(task_id), 'export'])
        if result.returncode != 0:
            return jsonify({'error': 'Task not found', 'status': 'error'}), 404
        task_data = json.loads(result.stdout)
        if not task_data:
            return jsonify({'error': 'Task not found', 'status': 'error'}), 404
        tags = task_data[0].get('tags', [])
        return jsonify({'tags': tags, 'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/task/<task_id>/tags', methods=['POST'])
def add_task_tag(task_id):
    try:
        tag = request.json.get('tag', '').strip()
        if not tag:
            return jsonify({'error': 'Tag required', 'status': 'error'}), 400
        result = run_task_command([str(task_id), 'modify', f'+{tag}'], hooks=True)
        if result.returncode != 0:
            return jsonify({'error': f'TaskWarrior modify failed: {result.stderr}', 'status': 'error'}), 500
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/task/<task_id>/tags/<tag>', methods=['DELETE'])
def remove_task_tag(task_id, tag):
    try:
        from urllib.parse import unquote
        decoded_tag = unquote(tag)
        result = run_task_command([str(task_id), 'modify', f'-{decoded_tag}'], hooks=True)
        if result.returncode != 0:
            return jsonify({'error': f'TaskWarrior modify failed: {result.stderr}', 'status': 'error'}), 500
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/task/<task_id>/delete', methods=['POST'])
def delete_task(task_id):
    """Soft-delete a task (ON-96). Uses TaskWarrior's `delete`, which flips
    status to 'deleted' rather than purging — recoverable via `task undo`
    from the CLI, or the ON-98 list section's Restore action. The modal on
    the frontend is the only confirmation gate (oneTask already runs with
    rc.confirmation=off, so TaskWarrior itself won't prompt)."""
    try:
        result = run_task_command([str(task_id), 'delete'], hooks=True)
        if result.returncode != 0:
            return jsonify({'error': f'TaskWarrior delete failed: {result.stderr}', 'status': 'error'}), 500
        return jsonify({'status': 'success'})
    except TimeoutError as e:
        return jsonify({'error': f'TaskWarrior timeout: {str(e)}', 'status': 'timeout'}), 408
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/tasks/by-tag/<tag>', methods=['GET'])
def get_tasks_by_tag(tag):
    """Get all tasks with a specific tag"""
    try:
        # Query TaskWarrior for tasks with specific tag
        # Correct syntax: task tag:tagname export
        result = run_task_command([f'tag:{tag}', 'export'])
        
        if result.returncode != 0:
            error_msg = f"TaskWarrior tag query failed: {result.stderr}"
            return jsonify({'error': error_msg, 'status': 'error'}), 500
        
        if not result.stdout.strip():
            return jsonify({'tasks': [], 'status': 'success'})
        
        tasks_data = json.loads(result.stdout)
        
        # Format tasks for display in modal
        tasks = []
        for task in tasks_data:
            tasks.append({
                'description': task.get('description', 'No description'),
                'uuid': task.get('uuid', ''),
                'short_id': task.get('uuid', '')[:8] if task.get('uuid') else 'unknown'
            })
        
        return jsonify({'tasks': tasks, 'tag': tag, 'status': 'success'})
        
    except Exception as e:
        error_msg = f"Error getting tasks by tag: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'error'}), 500

@app.route('/task/<task_id>/description', methods=['POST'])
def set_task_description(task_id):
    try:
        description = request.json.get('description', '').strip()
        if not description:
            return jsonify({'error': 'Description required', 'status': 'error'}), 400
        result = run_task_command([str(task_id), 'modify', f'description:{description}'], hooks=True)
        if result.returncode != 0:
            return jsonify({'error': f'TaskWarrior modify failed: {result.stderr}', 'status': 'error'}), 500
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/task/<task_id>/priority', methods=['POST'])
def set_task_priority(task_id):
    try:
        priority = request.json.get('priority')
        if priority is None or str(priority).strip() == '':
            return jsonify({'error': 'Priority required', 'status': 'error'}), 400
        priority = str(priority).strip()

        # Validate against the user's actual scheme (ON-67/A3) — never fire a
        # modify with a value that isn't one of the configured/native options.
        priority_values = get_priority_values(get_resolved_config())
        if priority not in priority_values:
            valid = ', '.join(priority_values) if priority_values else '(none configured)'
            return jsonify({'error': f'Priority must be one of: {valid}', 'status': 'error'}), 400

        result = run_task_command([str(task_id), 'modify', f'priority:{priority}'], hooks=True)
        if result.returncode != 0:
            return jsonify({'error': f'TaskWarrior modify failed: {result.stderr}', 'status': 'error'}), 500
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/task/<task_id>/priority', methods=['DELETE'])
def remove_task_priority(task_id):
    try:
        result = run_task_command([str(task_id), 'modify', 'priority:'], hooks=True)
        if result.returncode != 0:
            return jsonify({'error': f'TaskWarrior modify failed: {result.stderr}', 'status': 'error'}), 500
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('ONETASK_PORT', 5000))
    host = os.environ.get('ONETASK_HOST', '127.0.0.1')
    password = os.environ.get('ONETASK_PASSWORD', '')

    if host != '127.0.0.1' and not password:
        print(
            '\n'
            '┌─────────────────────────────────────────────────────────────┐\n'
            '│  LAN access skipped: ONETASK_PASSWORD is not set.           │\n'
            '│                                                             │\n'
            '│  To enable LAN access, set both env vars and restart:       │\n'
            '│    export ONETASK_PASSWORD="choose-a-real-password"         │\n'
            '│    export ONETASK_HOST="0.0.0.0"                            │\n'
            '│                                                             │\n'
            '│  Running on localhost only (127.0.0.1).                     │\n'
            '└─────────────────────────────────────────────────────────────┘\n',
            flush=True
        )
        host = '127.0.0.1'
    elif host != '127.0.0.1':
        print(
            f'Warning: binding to {host} — OneTask is reachable from other devices on your network.',
            flush=True
        )

    debug_requested = os.environ.get('ONETASK_DEBUG', '').lower() in ('1', 'true', 'yes', 'on')
    debug_mode = debug_requested and host == '127.0.0.1'

    if debug_requested and not debug_mode:
        print(
            '\n'
            '┌─────────────────────────────────────────────────────────────┐\n'
            '│  ONETASK_DEBUG ignored: debug mode is only permitted when   │\n'
            '│  bound to localhost (127.0.0.1).                            │\n'
            '│                                                             │\n'
            '│  The Werkzeug debugger allows remote code execution, so it  │\n'
            '│  cannot be combined with LAN/network binding.               │\n'
            '└─────────────────────────────────────────────────────────────┘\n',
            flush=True
        )

    print(f'Debug mode: {"ON" if debug_mode else "off"}', flush=True)

    app.run(host=host, port=port, debug=debug_mode)