import json, os, time, random
import threading
import sys

# Ensure root directory is on sys.path so absolute imports work when executed from agent_core/
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
from datetime import datetime
try:
    from rich.console import Console
except Exception:
    class Console:  # minimal fallback
        def print(self, *args):
            print(*args)
        def rule(self, text):
            print("\n" + str(text))
from agent_core.shell_exec import run_shell_command
from agent_core.brain import decide_next_action
from queue_handler import get_next_command as get_queued_command
from ui.control_ui import launch_ui
from logger import log_memory
try:
    from memory.reflect import reflect_and_score
except Exception:
    # Optional dependency (transformers) may be missing; reflection is best-effort
    reflect_and_score = None

console = Console()

# File constants
MEMORY_FILE = os.path.join(ROOT_DIR, "agent_memory.json")
MODE_FILE = os.path.join(ROOT_DIR, "mode_flag.json")

# Load or initialize memory
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE) as f:
            return json.load(f)
    return {"history": [], "last_result": ""}

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

def get_mode():
    if os.path.exists(MODE_FILE):
        with open(MODE_FILE) as f:
            return json.load(f).get("mode", "auto")
    return "auto"

def agent_loop():
    i = 0
    while True:
        console.rule(f"[bold blue]Agent Loop @ {datetime.now()}")

        # Read mode each loop
        mode = get_mode()
        console.print(f"[bold yellow]Mode: {mode.upper()}")

        # Check for manual command first
        user_cmd = get_queued_command()
        if user_cmd:
            console.print(f"[MANUAL] {user_cmd}")
            result = run_shell_command(user_cmd)
            log_memory(user_cmd, result)
            console.print(f"[dim]{result[:500]}")
            time.sleep(3)
            continue

        # Fallback to auto mode
        if mode == "auto":
            cmd = decide_next_action()
            console.print(f"[AUTO] {cmd}")
            result = run_shell_command(cmd)
            log_memory(cmd, result)
            console.print(f"[dim]{result[:500]}")
        else:
            # Manual mode with empty queue -> idle
            time.sleep(3)
            continue

        # Periodic reflection
        i += 1
        if reflect_and_score and i % 5 == 0:
            try:
                reflection = reflect_and_score()
                console.print("REFLECTED:", reflection)
            except Exception as e:
                console.print(f"[red]Reflection failed: {e}")

        time.sleep(3)

if __name__ == "__main__":
    # Run both UI and agent loop
    ui_thread = threading.Thread(target=launch_ui)
    ui_thread.daemon = True
    ui_thread.start()
    agent_loop()
