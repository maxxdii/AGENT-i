# AGENT-i

Lightweight autonomous agent with both a browser-based Web UI (headless-friendly) and a legacy desktop UI. Tasks are simple shell commands executed sequentially and persisted to `agent_memory.json`.

## Quick start (recommended: Web UI)

Works great in Codespaces or any headless Linux/WSL.

1) Ensure Python 3.10+ is available. If Flask isn’t installed, install it:

```bash
pip install Flask
```

2) Start the Web UI server:

```bash
python -m web_ui.app
```

3) Open the shown URL (default http://127.0.0.1:5000). In Codespaces, accept the port forwarding prompt or open the forwarded port manually.

4) In the UI:
- Add a task in the input (e.g., `echo hello`).
- Click Start to run the background agent loop; tasks will execute every ~2 seconds and logs will update live.
- Click Stop to pause the background loop.

API endpoints (optional):
- POST `/task` with form field `task=...` to enqueue a task.
- POST `/agent/start` to start the background loop.
- POST `/agent/stop` to stop it.

```bash
# enqueue a task
curl -X POST -d "task=echo via curl" http://127.0.0.1:5000/task
# start/stop agent
curl -X POST http://127.0.0.1:5000/agent/start
curl -X POST http://127.0.0.1:5000/agent/stop
```

## Alternate ways to run

### Programmatic (no UI)
You can enqueue and run tasks directly using the core module:

```bash
python - <<'PY'
import autonomy_core as core
core.inject_task('echo from autonomy')
entry, _ = core.execute_next_task()
print('Executed:', entry)
PY
```

### Legacy agent (desktop/Tk UI)
This starts the older agent loop and tries to launch a Tkinter desktop app. It won’t work in headless environments without a display.

```bash
python agent_core/main.py
```

If you’re on a desktop Linux and Tk isn’t installed:

```bash
sudo apt-get update && sudo apt-get install -y python3-tk
```

## How it works

- `autonomy_core.py` — single source of truth for tasks, logs, and state.
	- `inject_task(task)`: enqueue a shell command.
	- `execute_next_task()`: pops and runs the next task; appends a log entry `{timestamp, task, output}`; updates `state.last_task` and `state.last_output`.
	- Data is persisted in `agent_memory.json`.
- `web_ui/` — Flask + HTMX Web UI.
	- `web_ui/app.py` app factory; run with `python -m web_ui.app`.
	- `web_ui/routes.py` routes for home, add task, refresh, start/stop background loop.
- `agent_core/` — legacy agent demo and Tk controller (not required for Web UI).
- `memory/`, `logger.py`, `queue_handler.py` — optional/legacy features (manual queues, extra logs, and reflection). The Web UI doesn’t depend on them.

Schema: `agent_memory.json`

```jsonc
{
	"tasks": ["echo hello"],
	"logs": [
		{ "timestamp": "2025-08-29T00:00:00+00:00", "task": "echo hello", "output": "hello" }
	],
	"state": { "mode": "autonomous", "last_task": "echo hello", "last_output": "hello" }
}
```

Notes:
- The app now normalizes legacy `state` values. If `state` was a string (e.g., `"booting"`), it’s treated as `{"mode": "booting"}`.
- Avoid running the Web UI background agent and the legacy `agent_core/main.py` loop at the same time; both write to `agent_memory.json`.

## Troubleshooting

- Web UI 500 error after first run:
	- Stop all running agents. Delete `agent_memory.json` to reset, then start `python -m web_ui.app` again.
- Tkinter error “no display name”: You’re in a headless environment; use the Web UI instead, or run on a desktop with X11.
- Port already in use / change port:
	- `PORT=5050 python -m web_ui.app`
- Security: Tasks run as shell commands of the current user. Only enqueue commands you trust.

## Project layout

```
README.md
autonomy_core.py         # Core queue + execution + persistence
web_ui/                  # Headless-friendly Flask UI
	app.py
	routes.py
	templates/
	static/
agent_core/              # Legacy agent + Tk UI (headless-unfriendly)
ui/control_ui.py         # Legacy Tk window
agent_memory.json        # Persistent state/logs/tasks
memory/                  # Optional extra logs/reflection (not required by Web UI)
```

## License
Prototyping code; no warranty. Use at your own risk.