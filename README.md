# OneTask

> v2.3.0 · source-available, AGPL-3.0

A Pomodoro-style task management web application that wraps [TaskWarrior](https://taskwarrior.org/) in a focused, timer-based interface. It shows you one task at a time, counts down its time estimate, and lets you stay in flow without switching back to the terminal.

OneTask is a personal, single-user tool shared in case it's useful to you. See [Project status](#project-status) and [Security](#security) before running it.

## Features

- **Timer Interface**: Visual countdown timer with click-to-pause functionality
- **TaskWarrior Integration**: Uses TaskWarrior's native report system, respecting all `.taskrc` configurations
- **Task Navigation**: Navigate through tasks with Previous/Next buttons, or jump straight to one from the full List view
- **Task Identifiers**: Clickable 8-character task IDs for easy terminal lookup
- **Combined List + Stats View**: The List screen shows pending count, completed-today, and total time estimate as a header above the full task list
- **Visual Indicators**: Red background for overdue tasks
- **Task Completion**: Mark tasks complete/incomplete directly from the interface
- **Report Support**: Works with any configured TaskWarrior report — built-ins like `next` and `ready` work out of the box; a personal report like `focus` needs to be defined first (see [Optional customizations](#optional-customizations))
- **Inline Editing**: Edit a task's title (`T`) and priority directly in the task panel; priority can be cleared entirely, not just changed
- **Notes Management**: Add, view, and delete task annotations with configurable sort order (newest/oldest first); new-note form repositions to match sort order
- **Tag Management**: Add and remove tags directly in the task panel without using the TUI
- **URL Management**: Add or edit a task's URL link directly in the task panel without using the TUI
- **Keyboard Shortcuts**: `a` to open the info panel and focus the new note field; `T` to edit the title; `S` to jump between the timer and the List view; Cmd+Enter to save; standard nav shortcuts (p/n/d/space/i/l)
- **Mobile / Touch Support**: The timer, details panel, and List view adapt to phone-sized screens (portrait and landscape) — thumb-sized controls, a swipe-to-dismiss Details bottom sheet, tap-to-expand notes, and a touch-friendly priority picker. Fully additive: desktop behavior and layout are unchanged
- **Click-to-copy**: Task IDs, note text, and the List view's stats summary all copy to the clipboard on click/tap
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

## Setup

OneTask runs against a stock TaskWarrior install with no configuration required — it degrades gracefully wherever it can. Two small `.taskrc` additions unlock its full feature set, though. Neither is required to start using OneTask; add them whenever you want the features they unlock.

If you've never edited `.taskrc` before: it's a plain text file, usually at `~/.taskrc`, created automatically the first time you run any `task` command. Add the lines below anywhere in it and save — no OneTask restart needed, since it reads TaskWarrior's config fresh on every request.

```ini
# Unlocks the countdown timer's per-task time estimate
uda.estimate.type=duration
uda.estimate.label=Est

# Unlocks the URL field in the task details panel
uda.url.type=string
uda.url.label=URL
```

- **`estimate`** fuels the Pomodoro countdown — set it per task with `task <id> modify estimate:25min` (TaskWarrior's own CLI parses bare `25m` as 25 *months*, not minutes — spell out `min` or use ISO 8601 `PT25M`). Without this UDA configured, OneTask falls back to a 25-minute default timer and shows a "no estimate configured" notice, instead of a dead 0:00 countdown.
- **`url`** lets you attach a link to a task and open it from the timer view. Without this UDA configured, the URL field is hidden entirely from the details panel — you won't see a broken control.

See [Optional customizations](#optional-customizations) below for further tuning once the basics are working.

## Usage

1. **Start the server**
   ```bash
   python app.py
   ```

2. **Access the application**
   Open your browser to: http://localhost:5000/

   By default OneTask is reachable only from the machine it's running on. To reach it from your phone or another computer, see [Configuration](#configuration).

   **Optional: Use a specific TaskWarrior report**
   You can specify any configured TaskWarrior report using the `report` query parameter. These are built in to TaskWarrior and work on any install:
   ```
   http://localhost:5000/?report=next
   http://localhost:5000/?report=ready
   ```

   A report like `focus` is a **personal, custom** report, not a built-in one — `/?report=focus` will fail until you define it yourself. See [Optional customizations](#optional-customizations) for how.

   OneTask uses TaskWarrior's native `task export <report>` command, so all your `.taskrc` report configurations (filters, sorting, columns) are automatically respected. Requesting a report that doesn't exist falls back to `next` with a clear notice rather than erroring out.

3. **Using the interface**
   - Tasks are automatically loaded from TaskWarrior
   - Click the timer to pause/resume
   - Use Previous/Next buttons to navigate tasks
   - Click the task ID to copy it to clipboard for terminal use
   - Click "List" (upper left) to browse the full task list along with pending/completed-today/estimate-remaining stats; "Return to oneTask" (also upper left, on the List view) or the `S` key jumps back
   - Click "Complete Task" to mark tasks as done
   - Click "Uncomplete Task" to reopen completed tasks
   - On a phone, tap "Details" (below the timer controls) to open the same task panel as a bottom sheet — swipe down or tap outside it to dismiss

## Configuration

OneTask is configured through environment variables.

| Variable | Default | Purpose |
|----------|---------|---------|
| `ONETASK_PORT` | `5000` | Port the server listens on |
| `ONETASK_HOST` | `127.0.0.1` | Interface to bind to. Set to `0.0.0.0` to enable LAN access (requires `ONETASK_PASSWORD`) |
| `ONETASK_PASSWORD` | _(unset)_ | Password required to access the app. **Mandatory** for LAN access |
| `ONETASK_DEBUG` | _(off)_ | Enables Flask's debug mode/reloader. **Only takes effect when bound to localhost** — if set while bound beyond localhost, it is force-disabled with a notice, since the debugger allows remote code execution |
| `ONETASK_DEFAULT_DURATION` | `25min` | Timer length used for a task with no `estimate` value (see [Time Estimate Formats](#time-estimate-formats) for accepted formats). Set to `0` to start counting up from 0:00 immediately instead of counting down first. Missing or unparseable values fall back to the 25-minute built-in default |

### Enabling access from your phone / other devices

LAN access is deliberately opt-in, and it requires a password so your task list isn't exposed unauthenticated to everything on your network:

```bash
export ONETASK_PASSWORD="choose-a-real-password"
export ONETASK_HOST="0.0.0.0"
python app.py
```

If you request LAN binding (`0.0.0.0`) **without** setting a password, OneTask will **not** expose itself unprotected. It starts on localhost only and prints a clear notice explaining that LAN access was skipped and how to enable it. Your app will still run — it just won't be reachable from other devices until a password is set.

Read [Security](#security) before exposing OneTask to any network.

## Optional customizations

> **These are all optional.** OneTask works fully without any of them — this section is for tuning TaskWarrior itself to get more out of the app. None of it is a OneTask setting; it all lives in your `.taskrc`. See [Setup](#setup) above for the two additions that unlock OneTask features (not just cosmetic tuning).

### A numeric priority scheme (1/2/3 instead of High/Medium/Low)

TaskWarrior's default priority scheme is `H`/`M`/`L`. OneTask reads whatever scheme is actually configured — its priority editor and sort order adapt to it automatically, so if you'd rather see 1/2/3:

```ini
uda.priority.type=string
uda.priority.label=Priority
uda.priority.values=1,2,3
```

### Urgency coefficients (better task ordering)

TaskWarrior's reports sort by "urgency," a weighted score you control with coefficients. If you've added the `estimate` UDA (from [Setup](#setup)) and a custom priority scheme (above), you can weight them into that score:

```ini
urgency.uda.priority.1.coefficient=500   # push priority-1 tasks to the top
urgency.uda.priority.2.coefficient=50
urgency.uda.priority.3.coefficient=1

urgency.uda.estimate.5mins.coefficient=3 # prefer quick tasks when tied
urgency.uda.estimate.10mins.coefficient=2
urgency.uda.estimate.20mins.coefficient=1

urgency.due.coefficient=1
```

These numbers are a starting point, not a fixed recipe — tune them to match how you want tasks ranked. See TaskWarrior's [urgency documentation](https://taskwarrior.org/docs/urgency/) for the full coefficient list.

### A custom `focus` report

`focus` (referenced elsewhere in this README as an example) isn't a built-in TaskWarrior report — it's a personal one, defined in `.taskrc` like any other:

```ini
report.focus.description=Where I should focus
report.focus.columns=id,priority,estimate,due,project,description.count
report.focus.labels=ID,P,Est.,Due,Project,Description
report.focus.sort=urgency-
report.focus.filter=status:pending
```

Adjust `filter` to whatever narrows down "what should I work on right now" for you — this example just shows all pending tasks; TaskWarrior's filter syntax supports much more (project, tags, due dates, and boolean combinations of them).

### Other personal UDAs

You can define any TaskWarrior UDA and OneTask will simply leave it alone — it carries whatever attributes your reports export without needing to know about them. For example, a UDA for tracking recurring-task due-date math:

```ini
uda.relativeRecurDue.type=duration
uda.relativeRecurDue.label=Rel. Rec. Due
```

has nothing to do with OneTask specifically — it's here as a pattern for extending TaskWarrior with whatever attributes are useful to your own workflow, not something OneTask reads or requires.

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
- `report` (optional): TaskWarrior report name (default: "next"). Built-in examples: `/?report=next`, `/?report=ready`. An unrecognized report name (e.g. a typo, or a custom report you haven't defined) falls back to `next` with a clear notice rather than erroring out.
- `task` (optional): UUID of the task to jump to (used by the List view). Falls back to the first task if not found.

### GET /list
Combined stats summary (pending count, completed today, estimate remaining) and full task list for the specified report, for browsing or jumping to a specific task. Each row links back to `/` with the task pre-selected. Reached via the "List" link (upper left) on the main interface.

**Query Parameters:**
- `report` (optional): TaskWarrior report name (default: "next")
  - Examples: `/list?report=next`, `/list?report=ready`

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
Redirects to `/list?report=<report>` — the stats summary now lives as a header on the combined list screen rather than a separate page.

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

### POST /task/\<id\>/priority
Sets a task's priority. Body: `{"priority": "H"}` (or whatever value from your configured `uda.priority.values` scheme — native H/M/L by default). Rejected with a 400 if the value isn't one of the resolved scheme's actual values.

### DELETE /task/\<id\>/priority
Clears a task's priority entirely.

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
