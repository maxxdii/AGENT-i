import os
import sys
import threading
from flask import Blueprint, render_template, request, redirect, url_for, jsonify

# Ensure root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import autonomy_core as core

bp = Blueprint('web', __name__)

_agent_thread = None
_stop_event = threading.Event()
_auto_thread = None
_full_auto_thread = None


def _agent_loop():
    while not _stop_event.is_set():
        try:
            core.execute_next_task()
        except Exception as e:
            print(f"Error in agent loop: {e}")
            # Continue running even if one task fails
        # small sleep to prevent tight loop; core pacing can be adjusted separately
        _stop_event.wait(2)


def start_background_agent():
    global _agent_thread
    if _agent_thread and _agent_thread.is_alive():
        return
    _stop_event.clear()
    _agent_thread = threading.Thread(target=_agent_loop, daemon=True)
    _agent_thread.start()
    try:
        mem = core.load_memory()
        if isinstance(mem.get('state'), dict):
            mem['state']['mode'] = 'autonomous'
        else:
            mem['state'] = {'mode': 'autonomous'}
        core.save_memory(mem)
    except Exception as e:
        print(f"Error updating state to autonomous: {e}")


def stop_background_agent():
    _stop_event.set()
    try:
        mem = core.load_memory()
        if isinstance(mem.get('state'), dict):
            mem['state']['mode'] = 'stopped'
        else:
            mem['state'] = {'mode': 'stopped'}
        core.save_memory(mem)
    except Exception as e:
        print(f"Error updating state to stopped: {e}")

def _start_full_autonomy(goal: str | None):
    try:
        def should_continue():
            return not _stop_event.is_set()
        core.full_autonomy_loop(goal=goal, should_continue=should_continue)
    except Exception as e:
        print(f"Error in full_autonomy_loop: {e}")


def _start_autonomy_cycle(goal: str | None, steps: int):
    try:
        core.autonomy_cycle(goal=goal, max_steps=max(1, min(steps, 50)))
    except Exception as e:
        print(f"Error in autonomy_cycle: {e}")


def _safe_logs(logs):
    safe = []
    for e in logs or []:
        if isinstance(e, dict):
            safe.append(e)
        else:
            safe.append({"timestamp": "", "task": "", "output": str(e)})
    return safe


@bp.post('/ask')
def ask_ai():
    """Synchronous ask endpoint: direct LLM answer plus suggested queueable tasks."""
    question = (request.form.get('q') or '').strip()
    if not question:
        return render_template('partials/ask_panel.html', question='', answer='Please enter a question.', suggestions=[])

    # Try to import call_llm from core; may be None if not configured
    try:
        from autonomy_core import call_llm  # type: ignore
    except Exception:
        call_llm = None

    # Build an answer
    if call_llm is None:
        answer = "LLM not available. Set OPENAI_API_KEY and ensure the OpenAI SDK is installed."
    else:
        try:
            prompt = (
                "You are AGENT-i, an autonomous assistant with a local task runner.\n"
                "In this 'Ask AI' panel you do not execute commands; provide concise, actionable guidance.\n"
                "Also propose up to 5 concrete next steps as exact shell commands (Ubuntu bash) or 'llm:' tasks.\n"
                "Make the guidance short.\n\n"
                f"User question: {question}\n"
            )
            answer = call_llm(prompt)
        except Exception as e:
            msg = str(e).lower()
            if any(s in msg for s in ["rate limit", "429", "rate_limit_exceeded", "rpd"]):
                answer = "LLM temporarily rate-limited. Using offline heuristics until capacity returns."
            else:
                answer = f"LLM Error: {e}"

    # Generate suggested tasks using the planner (best-effort)
    try:
        suggestions = core.plan_tasks_with_llm(goal=question, max_new=5) or []
    except Exception:
        suggestions = []

    return render_template('partials/ask_panel.html', question=question, answer=answer, suggestions=suggestions)


@bp.route('/')
def home():
    try:
        mem = core.load_memory()
        logs = _safe_logs(list(core.get_logs(mem))[-200:][::-1])
    except Exception:
        mem, logs = {"tasks": [], "logs": [], "state": {}}, []
    return render_template('index.html', mem=mem, logs=logs)


@bp.post('/task')
def add_task():
    task = (request.form.get('task') or '').strip()
    # Skip code-fence-only markers (``` or ```lang) to avoid no-op/bad tasks
    try:
        _is_fence = getattr(core, "_is_code_fence_only", None)
        if callable(_is_fence) and _is_fence(task):
            # Do not enqueue; just refresh UI/redirect as if handled
            if request.headers.get('HX-Request'):
                mem = core.load_memory()
                return render_template('partials/tasks.html', mem=mem)
            return redirect(url_for('web.home'))
    except Exception:
        pass
    # If submitted via the "Ask AI" button, ensure it is treated as an LLM task
    if request.form.get('is_llm') and task and not task.lower().startswith('llm:'):
        task = f"llm: {task}"
    # Heuristic: if not explicitly LLM and not a shell command, coerce to 'llm: '
    if task and not task.lower().startswith('llm:'):
        try:
            _is_cmd = getattr(core, "_is_shell_command", None)
            if callable(_is_cmd) and not _is_cmd(task):
                task = f"llm: {task}"
        except Exception:
            pass
    if task:
        core.inject_task(task)
    if request.headers.get('HX-Request'):
        # Return the refreshed tasks list fragment
        mem = core.load_memory()
        return render_template('partials/tasks.html', mem=mem)
    return redirect(url_for('web.home'))


@bp.post('/tasks/bulk')
def add_tasks_bulk():
    """Add multiple tasks at once. Accepts a newline-separated 'tasks' field or JSON array in 'tasks_json'."""
    tasks_str = (request.form.get('tasks') or '').strip()
    tasks_json = (request.form.get('tasks_json') or '').strip()
    tasks: list[str] = []
    if tasks_json:
        try:
            import json as _json
            parsed = _json.loads(tasks_json)
            if isinstance(parsed, list):
                tasks = [str(t).strip() for t in parsed if str(t).strip()]
        except Exception:
            tasks = []
    elif tasks_str:
        tasks = [t.strip() for t in tasks_str.splitlines() if t.strip()]

    # Normalize tasks if helper available
    try:
        normalizer = getattr(core, "_coerce_tasks", None)
        if callable(normalizer):
            tasks = normalizer(tasks)
    except Exception:
        pass

    for t in tasks:
        core.inject_task(t)

    if request.headers.get('HX-Request'):
        mem = core.load_memory()
        return render_template('partials/tasks.html', mem=mem)
    return redirect(url_for('web.home'))


@bp.get('/refresh')
def refresh():
    try:
        mem = core.load_memory()
        logs = _safe_logs(list(core.get_logs(mem))[-200:][::-1])
    except Exception:
        mem, logs = {"tasks": [], "logs": [], "state": {}}, []
    return render_template('partials/state_logs.html', mem=mem, logs=logs)


@bp.post('/agent/start')
def start_agent():
    start_background_agent()
    return jsonify(status='started')


@bp.post('/agent/stop')
def stop_agent():
    stop_background_agent()
    return jsonify(status='stopped')


@bp.post('/agent/auto')
def start_autonomy():
    global _auto_thread
    steps = request.form.get('steps', type=int) or 5
    goal = (request.form.get('goal') or '').strip() or None
    if _auto_thread and _auto_thread.is_alive():
        return jsonify(status='busy')
    _auto_thread = threading.Thread(target=_start_autonomy_cycle, args=(goal, steps), daemon=True)
    _auto_thread.start()
    return jsonify(status='started', steps=steps)


@bp.post('/agent/full-auto')
def start_full_auto():
    global _full_auto_thread
    goal = (request.form.get('goal') or '').strip() or None
    if _full_auto_thread and _full_auto_thread.is_alive():
        return jsonify(status='already-running')
    _stop_event.clear()
    _full_auto_thread = threading.Thread(target=_start_full_autonomy, args=(goal,), daemon=True)
    _full_auto_thread.start()
    return jsonify(status='started', mode='full_auto')


@bp.get('/health')
def health():
    if request.headers.get('HX-Request'):
        return '<span id="health" style="color:#10b981">Health: OK</span>'
    return jsonify(ok=True, service='AGENT-i', status='ok')


@bp.get('/favicon.ico')
def favicon():
    # Silence 404s; you can add a real icon in web_ui/static later
    return ('', 204)
