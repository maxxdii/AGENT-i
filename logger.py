import json
import os
from datetime import datetime, timezone

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(ROOT_DIR, "memory", "command_log.json")
MEM_FILE = os.path.join(ROOT_DIR, "memory", "memory.json")

def log_memory(cmd, result):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": cmd,
        "output": result
    }

    # Ensure log file exists
    if not os.path.exists(LOG_FILE):
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "w") as f:
            json.dump([], f)

    with open(LOG_FILE, "r") as f:
        logs = json.load(f)
    logs.append(entry)
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

    # also store to memory.json (trim to last 100)
    if not os.path.exists(MEM_FILE):
        with open(MEM_FILE, "w") as f:
            json.dump([], f)
    with open(MEM_FILE, "r") as f:
        memory = json.load(f)
    memory.append(entry)
    memory = memory[-100:]
    with open(MEM_FILE, "w") as f:
        json.dump(memory, f, indent=2)
