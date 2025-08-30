import json, time, subprocess, os, tempfile, threading, shutil, shlex
from datetime import datetime, timezone

MEMORY_FILE = "agent_memory.json"
# Use a re-entrant lock to prevent deadlocks when helper functions
# (e.g., load/save) are called while holding the lock.
_MEM_LOCK = threading.RLock()
try:
    from llm_client import call_llm  # optional
except Exception:
    call_llm = None

def _is_rate_limited_error(err) -> bool:
    """Heuristic check for 429/rate limit errors coming from providers."""
    msg = str(err or "").lower()
    return ("rate limit" in msg) or ("429" in msg) or ("rpd" in msg) or ("rate_limit_exceeded" in msg)


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

    # Skip code-fence markers or language-only fences accidentally enqueued
    if _is_code_fence_only(task):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": task,
            "output": "Skipped code fence marker/no-op.",
        }
        with _MEM_LOCK:
            memory = _normalize_memory(load_memory())
            memory.setdefault("logs", []).append(log_entry)
            memory.setdefault("state", {})
            memory["state"]["last_task"] = task
            memory["state"]["last_output"] = log_entry["output"]
            save_memory(memory)
        return log_entry, memory

    # Execute outside the lock (can take time)
    if task.startswith("llm:"):
        prompt = task.split("llm:", 1)[1].strip()
        if call_llm is None:
            output = "ERROR: LLM not available. Install openai and set OPENAI_API_KEY."
        else:
            try:
                # If the prompt is empty, interpret this as a quick "plan next steps" action.
                if not prompt:
                    mem_snapshot = load_memory()
                    context = _recent_context(mem_snapshot, max_logs=15)
                    planning_prompt = (
                        "You are AGENT-i. Propose 1-5 concrete next steps as executable shell commands "
                        "(bash on Ubuntu) or 'llm:' reasoning tasks.\n"
                        "Return STRICT JSON only: {\"tasks\":[\"...\"]}.\n"
                        "Avoid English sentences that are not commands.\n\n"
                        "Context:\n" + context
                    )
                    try:
                        reply = call_llm(planning_prompt)
                        suggestions = _safe_json_extract(reply)
                        suggestions = _coerce_tasks(suggestions)
                        for t in suggestions:
                            inject_task(t)
                        output = (
                            f"Planned {len(suggestions)} tasks:\n" + "\n".join(f"- {t}" for t in suggestions)
                        )
                    except Exception as e:
                        if _is_rate_limited_error(e):
                            suggestions = _coerce_tasks(_default_plan(prompt or None, max_new=5))
                            for t in suggestions:
                                inject_task(t)
                            output = (
                                "LLM rate-limited. Planned offline steps:\n" + "\n".join(f"- {t}" for t in suggestions)
                            )
                        else:
                            output = f"LLM planning error: {e}"
                else:
                    # Autonomous LLM task: ask for a concise answer AND concrete next steps to execute
                    mem_snapshot = load_memory()
                    context = _recent_context(mem_snapshot, max_logs=15)
                    planning_prompt = (
                        "You are AGENT-i, an autonomous local operator.\n"
                        "Task: " + prompt + "\n\n"
                        "Context:\n" + context + "\n\n"
                        "Respond in STRICT JSON only with keys 'answer' and 'tasks':\n"
                        "{\n  \"answer\": \"short guidance\",\n  \"tasks\": [\"cmd or llm: ...\"]\n}\n"
                        "Rules:\n- tasks must be exact Ubuntu bash commands or start with 'llm:'.\n- 1 to 5 tasks max.\n- Prefer actionable steps to inspect and modify local files when relevant."
                    )
                    try:
                        reply = call_llm(planning_prompt)
                        ans, sugg = _extract_answer_and_tasks(reply)
                        sugg = _coerce_tasks(sugg)
                        for t in sugg:
                            inject_task(t)
                        if ans and sugg:
                            output = ans.strip() + "\n\n" + (
                                f"Planned {len(sugg)} tasks:\n" + "\n".join(f"- {t}" for t in sugg)
                            )
                        elif ans:
                            output = ans.strip()
                        elif sugg:
                            output = (
                                f"Planned {len(sugg)} tasks:\n" + "\n".join(f"- {t}" for t in sugg)
                            )
                        else:
                            output = (reply or "").strip()
                    except Exception as e:
                        if _is_rate_limited_error(e):
                            sugg = _coerce_tasks(_default_plan(prompt, max_new=5))
                            for t in sugg:
                                inject_task(t)
                            output = (
                                "LLM rate-limited. Planned offline steps:\n" + "\n".join(f"- {t}" for t in sugg)
                            )
                        else:
                            # Fall back to raw answer or error
                            try:
                                output = call_llm(prompt)
                            except Exception as e2:
                                output = f"LLM Error: {e2}"
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

def _extract_answer_and_tasks(text: str) -> tuple[str, list[str]]:
    """Parse a JSON object with 'answer' and 'tasks'. On failure, fall back heuristics."""
    try:
        data = json.loads(text)
        ans = str(data.get("answer", "") or "").strip()
        tasks = data.get("tasks")
        if isinstance(tasks, list):
            return ans, [str(x).strip() for x in tasks if str(x).strip()]
    except Exception:
        pass
    # Fallback: derive tasks using the existing heuristic and use full text as answer
    return (text or "").strip(), _safe_json_extract(text)

def run_autonomous_loop(delay=2):
    print("Agent autonomous mode: ON")
    while True:
        execute_next_task()
        time.sleep(delay)


# ---------------- Advanced LLM autonomy helpers (optional) ---------------- #

def _recent_context(memory: dict, max_logs: int = 10) -> str:
    """Build a compact textual context from recent logs and state."""
    memory = _normalize_memory(memory)
    logs = (memory.get("logs") or [])[-max_logs:]
    state = memory.get("state", {})
    parts = [
        f"MODE: {state.get('mode', 'unknown')}",
        f"LAST_TASK: {state.get('last_task', '-')}",
    ]
    for e in logs:
        ts = e.get("timestamp", "")
        t = e.get("task", "")
        out = (e.get("output", "") or "").strip()
        if len(out) > 300:
            out = out[:300] + "..."
        parts.append(f"[{ts}] $ {t}\n{out}")
    return "\n".join(parts)


def _safe_json_extract(text: str):
    """Try to parse a JSON object with a 'tasks' array from text; fallback to list heuristics."""
    try:
        data = json.loads(text)
        tasks = data.get("tasks")
        if isinstance(tasks, list):
            return [str(x).strip() for x in tasks if str(x).strip()]
    except Exception:
        pass
    # Heuristic: take lines that look like list items
    lines = [l.strip("- •* \t") for l in (text or "").splitlines()]
    tasks = [l for l in lines if l]
    return tasks[:5]


def _is_shell_command(s: str) -> bool:
    """Heuristic: does this look like an executable shell command?"""
    s = (s or "").strip()
    if not s:
        return False
    if s.lower().startswith("llm:"):
        return False
    # Obvious shell syntax implies a command pipeline/compound
    if any(sym in s for sym in ["|", ";", "&&", "||", ">", "<", "$(`", "`", "$("]):
        return True
    try:
        parts = shlex.split(s)
        if not parts:
            return False
        first = parts[0]
    except Exception:
        first = s.split()[0]
    builtins = {"echo", "cd", "exit", "true", "false", "test", "[", "]", "printf", "pwd", "export", "set", "unset", "eval"}
    if first in builtins:
        return True
    # variable assignment like FOO=bar make may precede a command; treat as possibly valid
    if "=" in first and not first.startswith(("http://", "https://")):
        return True
    return shutil.which(first) is not None


def _coerce_tasks(tasks: list[str]) -> list[str]:
    """Normalize tasks to be either shell commands or 'llm:' tasks.

    Any item that doesn't look like a shell command is prefixed with 'llm: '.
    """
    out: list[str] = []
    for t in tasks or []:
        t = (str(t) or "").strip()
        if not t:
            continue
        # Drop code-fence only markers entirely
        if _is_code_fence_only(t):
            continue
        if t.lower().startswith("llm:"):
            out.append(t)
        elif _is_shell_command(t):
            out.append(t)
        else:
            out.append(f"llm: {t}")
    return out


def _is_code_fence_only(s: str) -> bool:
    """Return True if the string is just a Markdown code-fence marker like
    ``` or ```bash with no additional content.
    """
    s = (s or "").strip()
    if not s:
        return False
    if s == "```":
        return True
    # Language-only fence like ```json or ```bash
    if s.startswith("```") and ("\n" not in s) and (" " not in s) and len(s) > 3:
        return True
    return False


def _default_plan(goal: str | None = None, max_new: int = 5) -> list[str]:
    """Offline planning fallback when the LLM is unavailable or rate-limited.

    Produces safe, generic inspection steps plus a goal-oriented grep if provided.
    """
    goal = (goal or '').strip()
    tasks: list[str] = [
        "pwd",
        "ls -la",
        "grep -R -n 'def ' . | head -n 50 || true",
    ]
    if goal:
        g = goal.replace("'", "'\\''")
        tasks.append(f"grep -R -n '{g}' . | head -n 50 || true")
    tasks.append("curl -s http://127.0.0.1:5000/health || true")
    return tasks[:max_new]


def plan_tasks_with_llm(goal: str | None = None, max_new: int = 5) -> list[str]:
    """Use the LLM to propose the next concrete shell or LLM tasks.

    Returns a list of task strings (e.g., "echo hi" or "llm: summarize X").
    This does not mutate memory by itself; pair with inject_task().
    """
    if call_llm is None:
        return _coerce_tasks(_default_plan(goal, max_new=max_new))
    with _MEM_LOCK:
        mem = load_memory()
    context = _recent_context(mem)
    prompt = (
        "You are AGENT-i, an autonomous operator with local shell access.\n"
        "Goal: " + (goal or mem.get("state", {}).get("goal", "(none)")) + "\n\n"
        "Recent context (last actions and outputs):\n" + context + "\n\n"
        "Plan the next " + str(max_new) + " atomic steps to make progress.\n"
        "Return STRICT JSON ONLY: {\"tasks\":[\"...\"]}.\n"
        "Constraints:\n"
        "- Each item must be either an executable bash command (Ubuntu) or start with 'llm:' for reasoning.\n"
        "- Do NOT include plain English sentences that aren't executable.\n"
    )
    try:
        reply = call_llm(prompt)
        tasks = _coerce_tasks(_safe_json_extract(reply))
        return tasks or _coerce_tasks(_default_plan(goal, max_new=max_new))
    except Exception:
        return _coerce_tasks(_default_plan(goal, max_new=max_new))


def reflect_on_last_output() -> list[str]:
    """Ask the LLM to reflect on the last step and suggest fixes or next steps."""
    if call_llm is None:
        return []
    with _MEM_LOCK:
        mem = load_memory()
    last = (mem.get("logs") or [])[-1] if mem.get("logs") else None
    if not last:
        return []
    prompt = (
        "You are AGENT-i. Reflect on the last action and its output.\n"
        f"Task: {last.get('task','')}\n\nOutput:\n{last.get('output','')}\n\n"
        "Identify issues and propose 1-3 concrete next tasks.\n"
        "Return STRICT JSON ONLY: {\"tasks\":[\"...\"]}.\n"
        "Each item must be an executable bash command or start with 'llm:'."
    )
    try:
        reply = call_llm(prompt)
        suggestions = _coerce_tasks(_safe_json_extract(reply))
        # Save reflection text briefly
        with _MEM_LOCK:
            mem = load_memory()
            mem.setdefault("state", {})["reflection"] = reply[:2000]
            save_memory(mem)
        return suggestions
    except Exception:
        return []


def synthesize_knowledge() -> str | None:
    """Periodically summarize session knowledge and store in memory state."""
    if call_llm is None:
        return None
    with _MEM_LOCK:
        mem = load_memory()
    prompt = (
        "You are AGENT-i. Create a concise, actionable summary of the session so far\n"
        "including goals, completed steps, blockers, and next priorities (bullets)."
        " Keep it under 300 words."
        "\n\nContext:\n" + _recent_context(mem, max_logs=25)
    )
    try:
        reply = call_llm(prompt)
        with _MEM_LOCK:
            mem = load_memory()
            mem.setdefault("state", {})["summary"] = reply[:4000]
            save_memory(mem)
        return reply
    except Exception:
        return None


def autonomy_cycle(goal: str | None = None, max_steps: int = 10, interval: float = 1.5,
                   enable_chaining: bool = True, enable_reflection: bool = True,
                   enable_synthesis_every: int = 5):
    """Run a short autonomy cycle that chains planning -> execution -> reflection.

    This is opt-in and does not change existing behavior unless called by the host.
    """
    steps = 0
    with _MEM_LOCK:
        mem = load_memory()
        if goal:
            mem.setdefault("state", {})["goal"] = goal
            save_memory(mem)

    while steps < max_steps:
        # Plan if queue empty
        with _MEM_LOCK:
            mem = load_memory()
            queue_empty = not mem.get("tasks")
        if enable_chaining and queue_empty:
            for t in plan_tasks_with_llm(goal):
                inject_task(t)

        # Execute one
        execute_next_task()
        steps += 1

        # Reflect and chain more
        if enable_reflection:
            for t in (reflect_on_last_output() or [])[:3]:
                inject_task(t)

        # Periodic synthesis
        if enable_synthesis_every and steps % enable_synthesis_every == 0:
            synthesize_knowledge()

        time.sleep(interval)


def full_autonomy_loop(interval: float = 1.0, goal: str | None = None, should_continue=None,
                       enable_reflection: bool = True, enable_synthesis_every: int = 5):
    """Continuously plan -> execute -> reflect -> synthesize until should_continue() returns False.

    The caller can pass a should_continue() callback to integrate external stop controls.
    Sets state.mode = 'full_auto'.
    """
    steps = 0
    with _MEM_LOCK:
        mem = load_memory()
        mem.setdefault("state", {})["mode"] = "full_auto"
        if goal:
            mem["state"]["goal"] = goal
        save_memory(mem)

    while True:
        if callable(should_continue) and not should_continue():
            break

        # Plan if queue empty
        with _MEM_LOCK:
            mem = load_memory()
            queue_empty = not mem.get("tasks")
        if queue_empty:
            for t in plan_tasks_with_llm(goal):
                inject_task(t)

        # Execute one
        execute_next_task()
        steps += 1

        # Reflect and chain more
        if enable_reflection:
            for t in (reflect_on_last_output() or [])[:3]:
                inject_task(t)

        # Periodic synthesis
        if enable_synthesis_every and steps % enable_synthesis_every == 0:
            synthesize_knowledge()

        # Keep mode sticky and persist goal for UI visibility
        with _MEM_LOCK:
            mem = load_memory()
            mem.setdefault("state", {})["mode"] = "full_auto"
            if goal:
                mem["state"]["goal"] = goal
            save_memory(mem)

        time.sleep(interval)

