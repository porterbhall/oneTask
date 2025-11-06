# OneTask

A Pomodoro-style task management web application that integrates with TaskWarrior to provide a focused, timer-based interface for completing tasks.

## Features

- **Timer Interface**: Visual countdown timer with click-to-pause functionality
- **TaskWarrior Integration**: Seamlessly works with your existing TaskWarrior setup
- **Task Navigation**: Navigate through tasks with Previous/Next buttons
- **Visual Indicators**: Red background for overdue tasks
- **Task Completion**: Mark tasks complete/incomplete directly from the interface
- **Priority Sorting**: Tasks sorted by priority, time estimate, then name

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
   You can specify a custom TaskWarrior report using the `report` query parameter:
   ```
   http://localhost:5000/?report=your_report_name
   ```
   
   This allows you to use any configured TaskWarrior report (e.g., `next`, `overdue`, `today`) to filter which tasks appear in the interface.

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
