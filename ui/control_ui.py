import tkinter as tk
import json
import os
from tkinter import scrolledtext

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_FILE = os.path.join(ROOT_DIR, "agent_memory.json")
MODE_FILE = os.path.join(ROOT_DIR, "mode_flag.json")
QUEUE_FILE = os.path.join(ROOT_DIR, "command_queue.json")

def read_file(path):
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return ""

def write_mode(mode):
    with open(MODE_FILE, "w") as f:
        json.dump({"mode": mode}, f)

def add_command_to_queue(cmd):
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE) as f:
            queue = json.load(f)
    else:
        queue = []
    queue.append(cmd)
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)

def launch_ui():
    root = tk.Tk()
    root.title("Operator Control Panel")

    # Mode toggle
    mode_label = tk.Label(root, text="Mode: AUTO / MANUAL")
    mode_label.pack()

    def toggle_mode():
        current = mode_var.get()
        write_mode(current)

    mode_var = tk.StringVar(value="auto")
    auto_button = tk.Radiobutton(root, text="Auto", variable=mode_var, value="auto", command=toggle_mode)
    manual_button = tk.Radiobutton(root, text="Manual", variable=mode_var, value="manual", command=toggle_mode)
    auto_button.pack()
    manual_button.pack()

    # Command entry
    cmd_entry = tk.Entry(root, width=80)
    cmd_entry.pack()

    def send_command():
        cmd = cmd_entry.get()
        add_command_to_queue(cmd)
        cmd_entry.delete(0, tk.END)

    send_button = tk.Button(root, text="Send Command", command=send_command)
    send_button.pack()

    # Memory display
    mem_box = scrolledtext.ScrolledText(root, height=20, width=100)
    mem_box.pack()

    def update_memory():
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE) as f:
                memory = json.load(f)
                mem_box.delete(1.0, tk.END)
                for item in memory.get("history", [])[-20:]:
                    mem_box.insert(tk.END, f"> {item['command']}\n{item['result'][:300]}\n\n")
        root.after(3000, update_memory)

    update_memory()
    root.mainloop()
