import json, time, subprocess, os, tempfile, threading
from datetime import datetime, timezone

MEMORY_FILE = "agent_memory.json"
_MEM_LOCK = threading.Lock()
try:
    from llm_client import call_llm  # optional
except Exception:
    call_llm = None


def _normalize_memory(memory: dict) -> dict:
    """Ensure memory has expected shapes.

    - state: dict (coerce from legacy string -> {"mode": <str>})
    - logs: list
    - tasks: list
    """
    if not isinstance(memory, dict):
        memory = {}
    state = memory.get("state")
    if isinstance(state, str):
        memory["state"] = {"mode": state}
    elif not isinstance(state, dict):
        memory["state"] = {}
    if not isinstance(memory.get("logs"), list):
        memory["logs"] = []
    if not isinstance(memory.get("tasks"), list):
        memory["tasks"] = []
    return memory

def load_memory():
    """Load memory with retries to tolerate concurrent writers."""
    if not os.path.exists(MEMORY_FILE):
        return {"logs": [], "state": {}, "tasks": []}
    # Retry a few times if file is mid-write and JSON is invalid
    for _ in range(5):
        try:
            with _MEM_LOCK:
                with open(MEMORY_FILE, "r") as f:
                    data = json.load(f)
            return _normalize_memory(data)
        except json.JSONDecodeError:
            time.sleep(0.05)
        except FileNotFoundError:
            time.sleep(0.02)
    # Give up, return safe default but do not crash the UI
    return {"logs": [], "state": {}, "tasks": []}

def save_memory(memory):
    """Atomically write memory to disk to avoid partial reads."""
    memory = _normalize_memory(memory)
    dirname = os.path.dirname(MEMORY_FILE) or "."
    os.makedirs(dirname, exist_ok=True)
    with _MEM_LOCK:
        fd, tmp_path = tempfile.mkstemp(prefix=".mem.", dir=dirname)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(memory, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, MEMORY_FILE)
        finally:
            # If replace succeeded, tmp_path no longer exists; ignore failures
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

def inject_task(task, memory=None):
    with _MEM_LOCK:
        memory = _normalize_memory(memory or load_memory())
        memory.setdefault("tasks", []).append(task)
        save_memory(memory)

def get_logs(memory=None):
    memory = _normalize_memory(memory or load_memory())
    return memory.get("logs", [])

def execute_next_task(memory=None):
    # Pop a task inside the lock
    with _MEM_LOCK:
        memory = _normalize_memory(memory or load_memory())
        tasks = memory.get("tasks", [])
        if not tasks:
            return None, memory
        task = tasks.pop(0)
        save_memory(memory)  # persist the pop immediately

    # Execute outside the lock (can take time)
    if task.startswith("llm:"):
        prompt = task.split("llm:", 1)[1].strip()
        if call_llm is None:
            output = "ERROR: LLM not available. Install openai and set OPENAI_API_KEY."
        else:
            try:
                output = call_llm(prompt)
            except Exception as e:
                output = f"LLM Error: {e}"
    else:
        try:
            output = subprocess.getoutput(task)
        except Exception as e:
            output = f"ERROR: {e}"

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "output": output,
    }

    # Commit results inside the lock
    with _MEM_LOCK:
        memory = _normalize_memory(load_memory())
        memory.setdefault("logs", []).append(log_entry)
        memory.setdefault("state", {})
        memory["state"]["last_task"] = task
        memory["state"]["last_output"] = output
        save_memory(memory)
    return log_entry, memory

def run_autonomous_loop(delay=2):
    print("Agent autonomous mode: ON")
    while True:
        execute_next_task()
        time.sleep(delay)
