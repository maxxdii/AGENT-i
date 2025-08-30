# AGENT-i

Lightweight autonomous agent with both a browser-based Web UI (headless-friendly) and a legacy desktop UI. Tasks are simple shell commands executed sequentially and persisted to `agent_memory.json`.

## Quick start (recommended: Web UI)

Works great in Codespaces or any headless Linux/WSL.

Option A — one-command bootstrap (creates venv, installs deps, starts server):

```bash
./start.sh
```

Option B — manual start:

1) Ensure Python 3.10+ is available and install deps:

```bash
python -m pip install -r requirements.txt
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
- Optional: Use “Auto Cycle” to run a short plan→execute→reflect loop. Provide steps and an optional goal.
- Optional: “Full Autonomy” to run continuous plan→execute→reflect cycles until stopped.

LLM setup (optional but recommended for smarter planning):

- Set your OpenAI API key in the environment or a .env file. Example:

```bash
echo 'OPENAI_API_KEY=sk-...yourkey...' > .env
```
- The app uses the OpenAI Python SDK (prefers new API, falls back to legacy). If the key is missing or rate-limited, it will use an offline fallback planner so autonomy keeps working.

API endpoints (optional):
- POST `/task` with form field `task=...` to enqueue a task.
- POST `/tasks/bulk` with `tasks_json=["cmd1","cmd2"]` to enqueue many.
- POST `/agent/start` to start the background loop.
- POST `/agent/stop` to stop it.
- POST `/agent/auto` with `steps` (1–50) and optional `goal` to run a short autonomy cycle.
- POST `/agent/full-auto` with optional `goal` to start continuous autonomy.
- GET `/health` returns `{ ok: true }` (used by the UI health indicator).

```bash
# enqueue a task
curl -X POST -d "task=echo via curl" http://127.0.0.1:5000/task
# start/stop agent
curl -X POST http://127.0.0.1:5000/agent/start
curl -X POST http://127.0.0.1:5000/agent/stop
```

### Restart the Web UI server

If it’s running in the foreground, press Ctrl+C, then start it again:

```bash
python -m web_ui.app
```

If it’s running elsewhere (or you’re unsure), kill and restart:

```bash
pkill -f "python -m web_ui.app" || true
./start.sh
```

Note on LLM rate limits:

- The app doesn’t impose any limits itself. If your provider returns a 429/rate_limit message, AGENT-i automatically switches to its offline planner so autonomy keeps running, and it will resume using the LLM once capacity is available. You can change the model via `OPENAI_MODEL` in `.env` to a tier with higher limits if needed.

## Alternate ways to run

### Modern desktop UI (Tk)
Local desktop control panel with Start/Stop, Add Task, and Autonomy helpers (Plan/Reflect/Synthesize/Auto Cycle).

```bash
python app.py
```

Notes:
- Requires a desktop with Tk. On Ubuntu: `sudo apt-get install -y python3-tk`
- In headless environments (Codespaces/servers), this will not run; use the Web UI instead.

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
	- `web_ui/routes.py` routes for home, ask, add task(s), refresh, start/stop, short and full autonomy.
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

### GUI control (desktop-only)

The Web UI includes quick actions to control your desktop:

- Open URL (uses Python `webbrowser`)
- Click at (x, y)
- Type text

Requirements and notes:

- Must run on a real desktop session (not headless). On Linux, ensure an X11 session or Wayland with proper compatibility. In Codespaces/headless servers, GUI control won’t work.
- Dependencies are included in `requirements.txt` (PyAutoGUI, Pillow). On Linux, you may also need `python3-Xlib` from pip (included) and sometimes system tools for screenshots; GUI actions here don’t require screenshots.
- Permissions: Some OSes require enabling accessibility/automation permissions for keyboard/mouse control.

Desktop setup tips:

- Linux (X11):
	- Ensure you are in a graphical session (not SSH/headless). If needed, use x11vnc/turbovnc to get a desktop.
	- Install Tk support for the legacy desktop UI: `sudo apt-get install -y python3-tk`
	- Wayland users may need to switch to an Xorg session for PyAutoGUI to work reliably.
- macOS:
	- Grant “Accessibility” permission to your terminal/app in System Settings → Privacy & Security → Accessibility.
	- First GUI action may trigger a permission prompt; approve it.
- Windows:
	- Run in a normal desktop session (not a Windows Server Core headless environment).
	- No special permissions usually required; if blocked, check antivirus or UAC prompts.

## Troubleshooting

- Web UI 500 error after first run:
	- Stop all running agents. Delete `agent_memory.json` to reset, then start `python -m web_ui.app` again.
- Tkinter error “no display name”: You’re in a headless environment; use the Web UI instead, or run on a desktop with X11.
- Port already in use / change port:
	- `PORT=5050 python -m web_ui.app`
 	- Or set `PORT=5050` before running `./start.sh`.
- Can’t curl 127.0.0.1 in Codespaces terminal while the browser works:
	- Use the forwarded browser link; the terminal sometimes can’t reach the forwarded port directly. The UI polls `/refresh`, and `/health` should show OK in the footer.
- Security: Tasks run as shell commands of the current user. Only enqueue commands you trust.
- Tasks that are only code-fence markers (like ``` or ```json) are ignored by the app; submit a real command or an `llm:` task.

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
