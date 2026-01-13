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
    
    # Create short task identifier from UUID (first 8 characters)
    uuid = task.get('uuid', '')
    short_id = uuid[:8] if uuid else 'unknown'
    
    # Format the task for display
    formatted_task = {
        "name": task.get('description', 'No description'),
        "priority": priority_num,
        "time_estimate": estimate,
        "task_id": task.get('uuid', ''),  # Use UUID as primary identifier
        "uuid": task.get('uuid', ''),
        "total_seconds": total_seconds,
        "task_url": task.get('url', 'none'),
        "short_id": short_id,
        "annotations": task.get('annotations', []),
        "due_date": task.get('due', None),
        "tags": task.get('tags', [])
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
            tasks = [{'name': 'No tasks to display', 'priority': 2, 'total_seconds': 0, 'formatted_task': 'No tasks to display', 'task_id': '', 'uuid': '', 'task_url': 'none', 'short_id': ''}]
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
        short_ids = [task["short_id"] for task in tasks]
        task_annotations = [task["annotations"] for task in tasks]
        task_due_dates = [task["due_date"] for task in tasks]
        task_tags = [task["tags"] for task in tasks]
        num_tasks = len(tasks)
        
        return render_template('task.html', 
                             formatted_tasks=formatted_tasks, 
                             task_urls=task_urls, 
                             remaining_seconds=remaining_seconds, 
                             num_tasks=num_tasks, 
                             task_id=task_ids,
                             taskseries_id=uuids,  # Use UUID as taskseries_id for compatibility
                             truelist_id=uuids,    # Use UUID as truelist_id for compatibility
                             short_ids=short_ids,
                             task_annotations=task_annotations,
                             task_due_dates=task_due_dates,
                             task_tags=task_tags,
                             currentTaskIndex=0,
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
        result = run_task_command([str(task_id), 'modify', 'status:pending'])
        
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

@app.route('/stats')
def show_stats():
    """Display statistics for the current report"""
    # Get report name from query string (default to 'next')
    report_name = request.args.get('report', default='next')
    print(f"DEBUG: Showing stats for report: {report_name}")
    
    try:
        # Get current pending tasks from the report
        pending_tasks = get_tasks_from_report(report_name)
        pending_count = len(pending_tasks)
        
        # Calculate sum of time estimates for pending tasks
        total_estimate_seconds = sum(
            convert_taskwarrior_estimate_to_seconds(task.get('estimate', ''))
            for task in pending_tasks
        )
        
        # Get tasks completed today
        completed_today = 0
        try:
            # Query for tasks completed today
            completed_result = run_task_command(['completed', 'end:today'])
            
            if completed_result.returncode == 0 and completed_result.stdout.strip():
                # Count actual task entries by looking for lines that start with " - " (completed task indicator)
                output_lines = completed_result.stdout.strip().split('\n')
                task_lines = [line for line in output_lines if line.strip().startswith('- ')]
                completed_today = len(task_lines)
        except Exception as e:
            print(f"DEBUG: Error getting completed tasks: {e}")
            completed_today = 0
        
        # Convert total seconds to human readable format
        hours = total_estimate_seconds // 3600
        minutes = (total_estimate_seconds % 3600) // 60
        
        if hours > 0:
            time_estimate_display = f"{hours}h {minutes}m"
        elif minutes > 0:
            time_estimate_display = f"{minutes}m"
        else:
            time_estimate_display = "0m"
        
        # Capitalize first letter of report name for display
        report_display = report_name.capitalize()
        
        return render_template('stats.html',
                             report_name=report_display,
                             pending_count=pending_count,
                             completed_today=completed_today,
                             time_estimate=time_estimate_display,
                             current_report=report_name)
        
    except Exception as e:
        error_msg = f"Error generating stats: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return f"""
        <html>
        <head><title>OneTask - Stats Error</title></head>
        <body style="font-family: Arial, sans-serif; margin: 40px; color: #333;">
            <h1 style="color: #d32f2f;">Stats Error</h1>
            <p>Unable to generate statistics.</p>
            <p><a href="/">← Go back to OneTask</a></p>
            <p style="color: #666; font-size: 12px;">Error: {error_msg}</p>
        </body>
        </html>
        """, 500

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
        result = run_task_command([str(task_id), 'annotate', annotation_text])
        
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
        
        result = run_task_command([str(task_id), 'denotate', decoded_text])
        
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
        result = run_task_command([str(task_id), 'modify', f'due:{due_date}'])
        
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
        result = run_task_command([str(task_id), 'modify', 'due:'])
        
        if result.returncode != 0:
            error_msg = f"TaskWarrior modify due failed: {result.stderr}"
            return jsonify({'error': error_msg, 'status': 'error'}), 500
        
        return jsonify({'status': 'success', 'message': 'Due date removed successfully'})
        
    except Exception as e:
        error_msg = f"Error removing due date: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return jsonify({'error': error_msg, 'status': 'error'}), 500

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

if __name__ == '__main__':
    # Enable debug mode only when running directly (not in production)
    app.run(debug=True)