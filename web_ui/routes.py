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


def _agent_loop():
    while not _stop_event.is_set():
        core.execute_next_task()
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
    except Exception:
        pass


def stop_background_agent():
    _stop_event.set()
    try:
        mem = core.load_memory()
        if isinstance(mem.get('state'), dict):
            mem['state']['mode'] = 'stopped'
        else:
            mem['state'] = {'mode': 'stopped'}
        core.save_memory(mem)
    except Exception:
        pass


def _safe_logs(logs):
    safe = []
    for e in logs or []:
        if isinstance(e, dict):
            safe.append(e)
        else:
            safe.append({"timestamp": "", "task": "", "output": str(e)})
    return safe


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
    if task:
        core.inject_task(task)
    if request.headers.get('HX-Request'):
        # Return the refreshed tasks list fragment
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


@bp.get('/favicon.ico')
def favicon():
    # Silence 404s; you can add a real icon in web_ui/static later
    return ('', 204)
