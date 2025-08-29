import json
import random

# === CONFIG ===
USE_LLM = False  # Set to True when you wire GPT/local model
MODEL = "gpt-4"  # or replace with llama.cpp, GPT4All, etc.

# === STATIC LOGIC (Fallback for now) ===
STATIC_COMMANDS = [
    "whoami",
    "uptime",
    "df -h",
    "ps aux | sort -nrk 3,3 | head -n 5",
    "netstat -tulnp",
    "curl ifconfig.me",
    "ls -la ~/Downloads",
    "du -sh ~/Documents/* | sort -hr | head -n 10"
]

def get_next_command(_memory=None):
    # Kept for backward compatibility; delegates to decide_next_action
    return decide_next_action()

def decide_next_action():
    # In future, use memory context to query LLM
    if not USE_LLM:
        return random.choice(STATIC_COMMANDS)

    # Placeholder for future LLM integration
    return "echo 'LLM mode not yet implemented'"
