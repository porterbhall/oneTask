# OneTask

> v2.1.0 · source-available, AGPL-3.0

A Pomodoro-style task management web application that wraps [TaskWarrior](https://taskwarrior.org/) in a focused, timer-based interface. It shows you one task at a time, counts down its time estimate, and lets you stay in flow without switching back to the terminal.

OneTask is a personal, single-user tool shared in case it's useful to you. See [Project status](#project-status) and [Security](#security) before running it.

## Features

- **Timer Interface**: Visual countdown timer with click-to-pause functionality
- **TaskWarrior Integration**: Uses TaskWarrior's native report system, respecting all `.taskrc` configurations
- **Task Navigation**: Navigate through tasks with Previous/Next buttons, or jump straight to one from the full List view
- **Task Identifiers**: Clickable 8-character task IDs for easy terminal lookup
- **Statistics Page**: Report-specific stats including pending tasks, completed today, and time estimates
- **Visual Indicators**: Red background for overdue tasks
- **Task Completion**: Mark tasks complete/incomplete directly from the interface
- **Report Support**: Works with any configured TaskWarrior report (focus, next, ready, etc.)
- **Inline Editing**: Edit a task's title (`T`) and priority directly in the task panel
- **Notes Management**: Add, view, and delete task annotations with configurable sort order (newest/oldest first); new-note form repositions to match sort order
- **Tag Management**: Add and remove tags directly in the task panel without using the TUI
- **URL Management**: Add or edit a task's URL link directly in the task panel without using the TUI
- **Keyboard Shortcuts**: `a` to open the info panel and focus the new note field; `T` to edit the title; Cmd+Enter to save; standard nav shortcuts (p/n/d/space/i/l)
- **Localhost by default**: Binds to `127.0.0.1` so a fresh install is reachable only from the machine it runs on. LAN access is opt-in and requires a password (see [Configuration](#configuration))
- **Configurable Port**: Set `ONETASK_PORT` to run on a port other than 5000

## Requirements

- Python 3.12+
- TaskWarrior installed and configured ([install guide](https://taskwarrior.org/download/))
- Flask 3.1.3+

OneTask does **not** bundle TaskWarrior — you install it separately (see [Acknowledgements](#acknowledgements)).

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/porterbhall/oneTask.git
   cd oneTask
   ```

2. **Create a virtual environment** (recommended)
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

1. **Start the server**
   ```bash
   python app.py
   ```

2. **Access the application**
   Open your browser to: http://localhost:5000/

   By default OneTask is reachable only from the machine it's running on. To reach it from your phone or another computer, see [Configuration](#configuration).

   **Optional: Use custom TaskWarrior reports**
   You can specify any configured TaskWarrior report using the `report` query parameter:
   ```
   http://localhost:5000/?report=focus
   http://localhost:5000/?report=next
   http://localhost:5000/?report=ready
   ```

   OneTask uses TaskWarrior's native `task export <report>` command, so all your `.taskrc` report configurations (filters, sorting, columns) are automatically respected.

3. **Using the interface**
   - Tasks are automatically loaded from TaskWarrior
   - Click the timer to pause/resume
   - Use Previous/Next buttons to navigate tasks
   - Click the task ID to copy it to clipboard for terminal use
   - Click "Stats" (upper left) to view report statistics
   - Click "Complete Task" to mark tasks as done
   - Click "Uncomplete Task" to reopen completed tasks

## Configuration

OneTask is configured through environment variables.

| Variable | Default | Purpose |
|----------|---------|---------|
| `ONETASK_PORT` | `5000` | Port the server listens on |
| `ONETASK_HOST` | `127.0.0.1` | Interface to bind to. Set to `0.0.0.0` to enable LAN access (requires `ONETASK_PASSWORD`) |
| `ONETASK_PASSWORD` | _(unset)_ | Password required to access the app. **Mandatory** for LAN access |
| `ONETASK_DEBUG` | _(off)_ | Enables Flask's debug mode/reloader. **Only takes effect when bound to localhost** — if set while bound beyond localhost, it is force-disabled with a notice, since the debugger allows remote code execution |

### Enabling access from your phone / other devices

LAN access is deliberately opt-in, and it requires a password so your task list isn't exposed unauthenticated to everything on your network:

```bash
export ONETASK_PASSWORD="choose-a-real-password"
export ONETASK_HOST="0.0.0.0"
python app.py
```

If you request LAN binding (`0.0.0.0`) **without** setting a password, OneTask will **not** expose itself unprotected. It starts on localhost only and prints a clear notice explaining that LAN access was skipped and how to enable it. Your app will still run — it just won't be reachable from other devices until a password is set.

Read [Security](#security) before exposing OneTask to any network.

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
- `task` (optional): UUID of the task to jump to (used by the List view). Falls back to the first task if not found.

### GET /list
Full-page list of every task in the specified report, for browsing or jumping to a specific task. Each row links back to `/` with the task pre-selected.

**Query Parameters:**
- `report` (optional): TaskWarrior report name (default: "next")
  - Examples: `/list?report=focus`, `/list?report=ready`

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

### GET /stats
Displays statistics for the current TaskWarrior report.

**Query Parameters:**
- `report` (optional): TaskWarrior report name (default: "next")
  - Examples: `/stats?report=focus`, `/stats?report=ready`

**Features:**
- Shows pending task count for the specified report
- Displays tasks completed today
- Calculates total time estimates for pending tasks
- Minimal text layout with navigation back to main interface

### GET /task/\<id\>/annotations
Returns all annotations (notes) for a task.

### POST /task/\<id\>/annotations
Adds an annotation to a task. Body: `{"annotation": "text"}`.

### DELETE /task/\<id\>/annotations/\<text\>
Removes a specific annotation by its URL-encoded text.

### GET /task/\<id\>/due
Returns the due date for a task.

### POST /task/\<id\>/due
Sets the due date for a task. Body: `{"due_date": "YYYY-MM-DD"}`.

### DELETE /task/\<id\>/due
Removes the due date from a task.

### GET /task/\<id\>/url
Returns the URL stored on a task.

### POST /task/\<id\>/url
Sets the URL on a task. Body: `{"url": "https://..."}`.

### DELETE /task/\<id\>/url
Removes the URL from a task.

### GET /task/\<id\>/tags
Returns the tags for a task.

### POST /task/\<id\>/tags
Adds a tag to a task. Body: `{"tag": "tagname"}`.

### DELETE /task/\<id\>/tags/\<tag\>
Removes a specific tag from a task.

### GET /tasks/by-tag/\<tag\>
Returns all tasks with the given tag.

## Security

**Read this before exposing OneTask to any network.**

OneTask is a single-user personal tool, not a hardened multi-user web application. Its security model is intentionally simple, and you should understand its limits:

- **Localhost by default.** A fresh install binds to `127.0.0.1` and is reachable only from the machine it runs on.
- **The password is basic gatekeeping, not strong authentication.** `ONETASK_PASSWORD` is a single shared password meant to keep casual visitors on your own network out. It is not a substitute for real auth, rate limiting, or account management.
- **LAN access requires a password.** OneTask will not expose itself to other devices without one.
- **Do not put OneTask directly on the public internet.** Your task list often contains sensitive personal and work detail, and the API lets a visitor *modify* tasks, not just read them. If you need remote access, place it behind a VPN, or an authenticated reverse proxy with TLS — never expose the raw port.
- **As-is, no warranty.** OneTask is provided under AGPL-3.0 with no warranty of any kind (see [License](#license)). You run it at your own risk.

The project also applies routine hygiene: Dependabot dependency alerts, input validation on task operations, secure error pages without information disclosure, and no debug mode in production.

To report a security vulnerability privately, see [`SECURITY.md`](SECURITY.md). Please don't open a public issue for security problems.

## Troubleshooting

### TaskWarrior Issues
- Ensure TaskWarrior is installed: `task --version`
- Check task data: `task list`
- Verify export functionality: `task export`

### Application Issues
- Check Python version: `python --version`
- Verify dependencies: `pip list`
- Check Flask logs for error messages
- Can't reach OneTask from another device? Confirm `ONETASK_HOST=0.0.0.0` **and** `ONETASK_PASSWORD` are both set (see [Configuration](#configuration))

## Project status

OneTask is a personal project, maintained by one person for their own use and shared in case it's useful to you.

- **Issues are welcome** as a place to document bugs and quirks — for your benefit and other forkers'. As the sole maintainer I may not respond or act on them, but they're read.
- **Pull requests are not accepted.** You are warmly encouraged to fork OneTask and adapt it to your needs. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Acknowledgements

OneTask stands entirely on [TaskWarrior](https://taskwarrior.org/), an excellent open-source command-line task manager by the Gothenburg Bit Factory, distributed under the MIT license. OneTask calls TaskWarrior as a separate program; you install and license it directly from that project. OneTask's AGPL-3.0 license covers OneTask only, not TaskWarrior.

Built with [Flask](https://flask.palletsprojects.com/) and [moment.js](https://momentjs.com/).

## License

OneTask is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)** — see the [`LICENSE`](LICENSE) file for the full text.

In short: you are free to use, study, modify, and share OneTask, including running it as a network service — but if you do, you must make your version's complete source code available to its users under the same license. This license covers OneTask only; TaskWarrior is licensed separately under MIT.
