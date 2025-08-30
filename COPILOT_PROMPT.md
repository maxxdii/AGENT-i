# Copilot Prompt for AGENT-i

## COPILOT SYSTEM INSTRUCTIONS

You are tasked with a full-stack audit and refinement of this project.

Rules:
- Preserve all core logic and file structures; do not remove or break autonomy_core or persistence systems.
- Make every file fully functional, clean, and bug-free.
- Apply professional-grade UI polish (modern look, consistent colors, typography, responsive layout).
- Ensure that both `app.py` (desktop) and `web_ui/app.py` (Flask/Jinja2) run without errors.
- Improve error handling, logging, and state management — no silent failures.
- Optimize code style to PEP8 and standard conventions.
- Keep memory handling consistent across modules.
- Verify that every function and import resolves, every line of code runs.
- When in doubt, add comments instead of deleting existing logic.
- Deliver final code that is production-ready: stable, maintainable, and aesthetically polished.

Final Output:
- Corrected + improved code for every file in the repo.
- No broken references.
- A UI that looks “out of the park” professional.

# Copilot Prompt for AGENT-i

Purpose: guide Copilot (and contributors) to make precise, safe, end-to-end changes to AGENT-i.

## Project snapshot
- Name: AGENT-i — lightweight autonomous agent with a Flask + HTMX Web UI and optional legacy desktop UI.
- Language: Python 3.10+ (tested on 3.12).
- Entrypoints:
  - Web UI: `python -m web_ui.app` (or `./start.sh` to bootstrap venv + deps)
  - Legacy desktop UI: `python app.py` (requires Tk; desktop only)
- State: single file `agent_memory.json` with keys: `tasks[]`, `logs[]`, `state{}`.

## Execution model (contract)
- Tasks are strings executed sequentially.
- Shell tasks: run as the current user in bash; output appended to `logs`.
- LLM tasks: start with `llm:` and must produce JSON: `{ "answer": string, "tasks": string[] }`.
  - The agent extracts `tasks` and auto-enqueues them.
  - Answer is logged for context.
- Non-shell inputs are coerced to `llm:` automatically.
- Code-fence-only inputs (``` or ```lang) are ignored.

## LLM integration
- Env: `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`, `OPENAI_TEMPERATURE`, `OPENAI_MAX_TOKENS`).
- Uses OpenAI Python SDK (prefers new API, falls back to legacy). If unavailable or rate-limited, a local fallback planner creates safe next steps.
- Place a `.env` file in repo root if desired.

## Web UI (Flask + HTMX)
- Package: `web_ui/` (Blueprint in `routes.py`, app factory in `app.py`, templates in `templates/`, CSS in `static/`).
- Key routes:
  - `/` home: shows queue, logs, controls
  - `/task`, `/tasks/bulk`: enqueue tasks
  - `/agent/start`, `/agent/stop`: background loop
  - `/agent/auto`: short autonomy cycle
  - `/agent/full-auto`: continuous full autonomy
  - `/ask`: “Ask AI” answer + suggested tasks
  - `/refresh`, `/health`: partial + health
- GUI quick-actions (desktop only): Open URL, Click, Type, Copy, Paste. Warn once per session if headless.

## Core behaviors (autonomy_core.py)
- `inject_task`, `execute_next_task`: queue + execute; logs outputs; updates `state`.
- LLM JSON extraction: parse `answer`, `tasks` from responses; enqueue tasks.
- Planning: `plan_tasks_with_llm` uses LLM or fallback `_default_plan`.
- Autonomy loops: `autonomy_cycle` (short), `full_autonomy_loop` (continuous; persists goal and mode).
- Guards: skip code-fence-only; coerce non-shell to `llm:`.

## Environment & running
- One command: `./start.sh` (creates venv, installs deps, respects `PORT`).
- Manual:
  - `python -m pip install -r requirements.txt`
  - `PORT=5050 python -m web_ui.app`
- Health: `GET /health` → `{ ok: true }`.

## Coding practices
- Prefer minimal, surgical changes; avoid broad reformatting.
- Keep functions small; preserve public APIs unless changing all call sites.
- UI: keep templates semantic and HTMX-friendly; avoid blocking scripts.
- Security: tasks run as shell commands; never enqueue risky commands automatically; maintain guard that ignores code-fence-only inputs.
- Headless safety: GUI actions must be optional and warn when not applicable.

## Quality gates (green-before-done)
- Build/run: start server; ensure `/health` OK.
- Lint/type: repository has no strict linters; ensure no syntax errors.
- Tests: none present; include a smoke step when modifying routes/templates.
- Docs: update `README.md` if public behavior or commands change.

## Common changes (recipes)
1) Add a new Web route
   - Edit `web_ui/routes.py`; register handler on `bp`.
   - Add template/partial if needed in `web_ui/templates/`.
   - Smoke: run server, curl the new route.

2) Add a Quick Action button
   - Update `templates/index.html` in the “Quick Actions” block.
   - If it enqueues multiple tasks, submit via `/tasks/bulk` with `tasks_json`.
   - Keep JS escaping safe for shell and Python `-c`.

3) Extend LLM planning
   - Touch only `autonomy_core.py` LLM helpers.
   - Ensure `_coerce_tasks` prefixes safe `llm:` and skips fence-only content.
   - If public behavior changes, document in `README.md`.

## File map
- `autonomy_core.py` — queue, execute, plan, loops, persistence.
- `llm_client.py` — OpenAI integration (+ dotenv loading).
- `web_ui/` — Flask blueprint, templates, static assets.
- `start.sh` — venv bootstrap + run.
- `requirements.txt` — Flask, openai, dotenv, plus optional GUI deps (PyAutoGUI, Pillow, python-xlib).
- `README.md` — Quick start, endpoints, GUI notes, troubleshooting.

## Don’ts
- Don’t execute or enqueue code-fence-only inputs.
- Don’t remove the coercion of non-shell tasks to `llm:`.
- Don’t introduce blocking UI or long-running synchronous handlers.

## Success criteria
- Server starts with `./start.sh` or `python -m web_ui.app`.
- `/health` returns OK.
- UI loads without errors; quick actions enqueue valid tasks.
- LLM optional; fallback planner continues autonomy when LLM is unavailable.
