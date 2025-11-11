# OneTask

A Pomodoro-style task management web application that integrates with TaskWarrior to provide a focused, timer-based interface for completing tasks.

## Features

- **Timer Interface**: Visual countdown timer with click-to-pause functionality
- **TaskWarrior Integration**: Uses TaskWarrior's native report system, respecting all .taskrc configurations
- **Task Navigation**: Navigate through tasks with Previous/Next buttons
- **Visual Indicators**: Red background for overdue tasks
- **Task Completion**: Mark tasks complete/incomplete directly from the interface
- **Report Support**: Works with any configured TaskWarrior report (focus, next, ready, etc.)

## Requirements

- Python 3.12+
- TaskWarrior installed and configured
- Flask 3.1.1+

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/porterbhall/oneTask.git
   cd oneTask
   ```

2. **Create virtual environment** (recommended)
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Ensure TaskWarrior is installed**
   ```bash
   task --version  # Should show TaskWarrior version
   ```

## Usage

1. **Start the development server**
   ```bash
   python app.py
   ```

2. **Access the application**
   Open your browser to: http://localhost:5000/

   **Optional: Use custom TaskWarrior reports**
   You can specify any configured TaskWarrior report using the `report` query parameter:
   ```
   http://localhost:5000/?report=focus
   http://localhost:5000/?report=next
   http://localhost:5000/?report=ready
   ```
   
   OneTask uses TaskWarrior's native `task export <report>` command, so all your .taskrc report configurations (filters, sorting, columns) are automatically respected.

3. **Using the interface**
   - Tasks are automatically loaded from TaskWarrior
   - Click the timer to pause/resume
   - Use Previous/Next buttons to navigate tasks
   - Click "Complete Task" to mark tasks as done
   - Click "Uncomplete Task" to reopen completed tasks

## Task Data

The application works with standard TaskWarrior tasks and supports:
- Task priorities
- Time estimates (parsed from various formats)
- Task descriptions
- Task completion status

## Time Estimate Formats

OneTask parses time estimates in multiple formats:
- ISO 8601 duration: `PT1H30M`
- Human readable: `1h 30m`, `45m`, `2h`
- Numeric with units: `90m`, `1.5h`, `30s`

## API Endpoints

OneTask provides the following HTTP endpoints:

### GET /
Main application interface. Loads and displays tasks from the specified TaskWarrior report.

**Query Parameters:**
- `report` (optional): TaskWarrior report name (default: "next")
  - Examples: `/?report=focus`, `/?report=ready`, `/?report=someday`

### POST /complete_task
Marks a task as complete in TaskWarrior.

**Request Body:**
- `task_id`: TaskWarrior task ID to mark as complete

**Response:**
```json
{"status": "success", "message": "Task marked as complete"}
```

### POST /uncomplete_task
Marks a completed task as incomplete (reopens it).

**Request Body:**
- `task_id`: TaskWarrior task ID to mark as incomplete

**Response:**
```json
{"status": "success", "message": "Task marked as incomplete"}
```

### POST /capture
Adds a new task to TaskWarrior using native TaskWarrior syntax.

**Request Body:**
- `task`: Task description with optional TaskWarrior attributes
  - Examples: `"Fix bug in login system"`, `"Review PR priority:H project:web"`

**Response:**
```json
{"status": "success", "message": "Task captured successfully"}
```

## Deployment

### Development Deployment
```bash
# Basic development server
python app.py
```

### Production Considerations
- Use a production WSGI server (e.g., Gunicorn, uWSGI)
- Configure reverse proxy (nginx/Apache) for static files
- Set up proper TaskWarrior permissions for web user
- Consider containerization for consistent environments

### Future Docker Support
Docker containerization is planned for simplified deployment. This will include:
- Multi-stage builds for optimized image size
- TaskWarrior configuration management
- Environment-based configuration
- Health check endpoints

## Development

See `CLAUDE.md` for detailed development guidance and architecture information.

## Troubleshooting

### TaskWarrior Issues
- Ensure TaskWarrior is installed: `task --version`
- Check task data: `task list`
- Verify export functionality: `task export`

### Application Issues
- Check Python version: `python --version`
- Verify dependencies: `pip list`
- Check Flask logs for error messages

## License

MIT License - see LICENSE file for details.
