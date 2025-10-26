import json
import subprocess
from flask import Flask, render_template, request, jsonify

app = Flask(__name__, template_folder='templates', static_folder='static')

# Disable debug mode in production to avoid Werkzeug error pages
app.config['DEBUG'] = False

def run_task_command(args, timeout=30):
    """Run a TaskWarrior command via subprocess with timeout"""
    try:
        result = subprocess.run(
            ['task'] + args,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"TaskWarrior command timed out after {timeout} seconds")
    except Exception as e:
        raise Exception(f"TaskWarrior command failed: {str(e)}")

def get_tasks_from_report(report_name='next'):
    """Get tasks from specified TaskWarrior report"""
    from datetime import datetime
    
    try:
        # Get all tasks and filter them ourselves
        # TaskWarrior 3.x export doesn't accept status filters directly
        result = run_task_command(['export'])
        
        if result.returncode != 0:
            raise Exception(f"TaskWarrior export failed: {result.stderr}")
        
        if not result.stdout.strip():
            return []
        
        all_tasks = json.loads(result.stdout)
        
        # Filter to only pending tasks first
        pending_tasks = [task for task in all_tasks if task.get('status') == 'pending']
        
        # Now filter based on the report type
        if report_name == 'focus':
            # Apply focus filter manually: ((project:Routine or project: ) and (tag:anyday or tag:weekday or tag:weekend or tag:someday) and (due: or due.by:today) and status:pending)
            filtered_tasks = []
            for task in pending_tasks:
                project = task.get('project')  # Can be None, empty string, or actual project
                tags = task.get('tags', [])
                due = task.get('due', '')
                
                # Check project condition: (project:Routine or project: )
                project_match = (project == 'Routine' or project is None or project == '')
                
                # Check tag condition: (tag:anyday or tag:weekday or tag:weekend or tag:someday)
                tag_match = any(tag in ['anyday', 'weekday', 'weekend', 'someday'] for tag in tags)
                
                # Check due condition: (due: or due.by:today) 
                # Empty due means no due date, otherwise check if due today or earlier
                from datetime import datetime
                today_str = datetime.now().strftime('%Y%m%dT235959Z')
                due_match = (due == '' or due is None or due <= today_str)
                
                if project_match and tag_match and due_match:
                    filtered_tasks.append(task)
            
            tasks = filtered_tasks
        elif report_name == 'unslotted':
            # Apply unslotted filter: status:pending and (estimate: or location: or (-weekday and -weekend and -anyday and -someday))
            filtered_tasks = []
            for task in pending_tasks:
                estimate = task.get('estimate', '')
                location = task.get('location', '')
                tags = task.get('tags', [])
                
                # Check if estimate or location is missing
                missing_metadata = (estimate == '' or location == '')
                
                # Check if missing time tags
                missing_time_tags = not any(tag in ['weekday', 'weekend', 'anyday', 'someday'] for tag in tags)
                
                if missing_metadata or missing_time_tags:
                    filtered_tasks.append(task)
            
            tasks = filtered_tasks
        elif report_name in ['next', 'ready']:
            # Filter for ready tasks (not blocked, not waiting, not scheduled in future)
            ready_tasks = []
            for task in pending_tasks:
                # Task is ready if it's not blocked, not waiting, and not scheduled for future
                is_blocked = task.get('depends') is not None
                is_waiting = task.get('wait') is not None and task.get('wait') != ''
                is_scheduled_future = task.get('scheduled') is not None and task.get('scheduled') > datetime.now().strftime('%Y%m%dT%H%M%SZ')
                
                if not is_blocked and not is_waiting and not is_scheduled_future:
                    ready_tasks.append(task)
            
            tasks = ready_tasks
        else:
            # For unknown reports, return all pending tasks
            tasks = pending_tasks
        
        # Sort by urgency (descending) to match TaskWarrior's default behavior
        tasks.sort(key=lambda x: x.get('urgency', 0), reverse=True)
        return tasks
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse TaskWarrior JSON: {str(e)}")

def format_task_for_display(task):
    """Convert TaskWarrior task to Milkbox-compatible format"""
    # Extract priority (TaskWarrior uses numeric priorities: 1, 2, 3)
    priority = task.get('priority', '')
    if priority:
        # TaskWarrior priority is already numeric (1, 2, 3)
        priority_num = int(priority)
    else:
        priority_num = 2  # Default priority
    
    # Get estimate and convert to seconds
    estimate = task.get('estimate', '')
    total_seconds = convert_taskwarrior_estimate_to_seconds(estimate)
    
    # Format the task for display
    formatted_task = {
        "name": task.get('description', 'No description'),
        "priority": priority_num,
        "time_estimate": estimate,
        "task_id": task.get('uuid', ''),  # Use UUID as primary identifier
        "uuid": task.get('uuid', ''),
        "total_seconds": total_seconds,
        "task_url": task.get('url', 'none')
    }
    
    # Format display name
    formatted_task["formatted_task"] = f"{formatted_task['priority']}: {formatted_task['name']}"
    
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

def sorting_key(task_details):
    """Sort tasks by priority, then by time estimate, then by name"""
    return (task_details["priority"] or float('inf'),
            task_details["total_seconds"],
            task_details["name"])

@app.route('/')
def show_list():
    """Main route - display tasks from specified report"""
    print(f"DEBUG: Starting show_list()")
    
    # Get report name from query string (default to 'next')
    report_name = request.args.get('report', default='next')
    print(f"DEBUG: Using report: {report_name}")
    
    try:
        # Get tasks from TaskWarrior
        raw_tasks = get_tasks_from_report(report_name)
        print(f"DEBUG: Got {len(raw_tasks)} tasks from TaskWarrior")
        
        if not raw_tasks:
            tasks = [{'name': 'No tasks to display', 'priority': 2, 'total_seconds': 0, 'formatted_task': 'No tasks to display', 'task_id': '', 'uuid': '', 'task_url': 'none'}]
        else:
            # Convert TaskWarrior tasks to Milkbox format
            # Note: raw_tasks are already sorted by urgency from get_tasks_from_report()
            tasks = [format_task_for_display(task) for task in raw_tasks]
        
        print(f"DEBUG: Formatted {len(tasks)} tasks for display")
        
        # Prepare data for template (matching Milkbox structure)
        task_ids = [task["task_id"] for task in tasks]
        uuids = [task["uuid"] for task in tasks]
        formatted_tasks = [task["formatted_task"] for task in tasks]
        task_urls = [task["task_url"] for task in tasks]
        remaining_seconds = [task["total_seconds"] for task in tasks]
        num_tasks = len(tasks)
        
        return render_template('task.html', 
                             formatted_tasks=formatted_tasks, 
                             task_urls=task_urls, 
                             remaining_seconds=remaining_seconds, 
                             num_tasks=num_tasks, 
                             task_id=task_ids,
                             taskseries_id=uuids,  # Use UUID as taskseries_id for compatibility
                             truelist_id=uuids,    # Use UUID as truelist_id for compatibility
                             currentTaskIndex=0)
        
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
        result = run_task_command([str(task_id), 'done'])
        
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
        result = run_task_command(['add'] + task_text.split())
        
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

if __name__ == '__main__':
    # Enable debug mode only when running directly (not in production)
    app.run(debug=True)