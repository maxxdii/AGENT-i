import json
import os

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
QUEUE_FILE = os.path.join(ROOT_DIR, "command_queue.json")

def get_next_command():
    if not os.path.exists(QUEUE_FILE):
        return None
    with open(QUEUE_FILE, "r") as f:
        try:
            queue = json.load(f)
            if not queue:
                return None
            cmd = queue.pop(0)
            with open(QUEUE_FILE, "w") as out:
                json.dump(queue, out, indent=2)
            return cmd
        except Exception:
            return None
