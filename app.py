import os
import sys
import json
import time
import threading
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from tkinter.scrolledtext import ScrolledText
    import tkinter.font as tkFont
except Exception as e:
    print("Tkinter is required to run the UI:", e)
    sys.exit(1)

# Ensure we can import autonomy_core from the same folder as this file
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

import autonomy_core as core  # uses agent_memory.json in repo root

REFRESH_MS = 1000  # UI refresh cadence
SLEEP_SECS = 2     # Agent loop cadence
MAX_LOG_ROWS = 500

# Modern color scheme to match web UI
COLORS = {
    'bg': '#1a1d23',
    'surface': '#242831', 
    'surface_light': '#2d3441',
    'primary': '#3b82f6',
    'primary_dark': '#2563eb',
    'success': '#10b981',
    'danger': '#ef4444',
    'warning': '#f59e0b',
    'text': '#f8fafc',
    'text_muted': '#94a3b8',
    'border': '#374151',
    'accent': '#8b5cf6'
}


def ts_fmt(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"


class AgentApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AGENT-i • Autonomous AI Assistant")
        self.root.minsize(1200, 800)
        self.root.geometry("1400x900")
        self._apply_modern_theme()

        # State
        self.agent_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()

        # UI variables
        self.state_var = tk.StringVar(value="stopped")
        self.tasks_var = tk.StringVar(value="")

        # Build UI
        self._build_layout()
        self._configure_grid()

        # First paint
        self.refresh_views()
        self.root.after(REFRESH_MS, self._poll_refresh)

        # Handle close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- UI setup ----------
    def _apply_modern_theme(self):
        """Apply modern dark theme with professional styling"""
        self.root.configure(bg=COLORS['bg'])
        
        # Configure fonts
        self.title_font = tkFont.Font(family="Segoe UI", size=16, weight="bold")
        self.header_font = tkFont.Font(family="Segoe UI", size=12, weight="bold")
        self.body_font = tkFont.Font(family="Segoe UI", size=10)
        self.mono_font = tkFont.Font(family="Consolas", size=9)
        
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure ttk styles with modern colors
        style.configure("TFrame", background=COLORS['bg'], relief="flat")
        style.configure("Card.TFrame", background=COLORS['surface'], relief="solid", borderwidth=1)
        
        style.configure("TLabel", background=COLORS['bg'], foreground=COLORS['text'], 
                       font=self.body_font)
        style.configure("Title.TLabel", background=COLORS['bg'], foreground=COLORS['text'],
                       font=self.title_font)
        style.configure("Header.TLabel", background=COLORS['surface'], foreground=COLORS['text'],
                       font=self.header_font)
        style.configure("Muted.TLabel", background=COLORS['bg'], foreground=COLORS['text_muted'],
                       font=self.body_font)
        
        style.configure("TButton", background=COLORS['primary'], foreground="white",
                       font=self.body_font, relief="flat", borderwidth=0, padding=(12, 8))
        style.map("TButton", 
                 background=[('active', COLORS['primary_dark'])],
                 relief=[('pressed', 'flat')])
        
        style.configure("Success.TButton", background=COLORS['success'])
        style.map("Success.TButton", background=[('active', '#059669')])
        
        style.configure("Danger.TButton", background=COLORS['danger'])
        style.map("Danger.TButton", background=[('active', '#dc2626')])
        
        style.configure("TEntry", fieldbackground=COLORS['surface_light'], 
                       foreground=COLORS['text'], borderwidth=1, relief="solid",
                       font=self.body_font, insertcolor=COLORS['text'])
        
        style.configure("Treeview", background=COLORS['surface'], foreground=COLORS['text'],
                       fieldbackground=COLORS['surface'], font=self.body_font, rowheight=24)
        style.configure("Treeview.Heading", background=COLORS['surface_light'], 
                       foreground=COLORS['text'], font=self.header_font)

    def _build_layout(self):
        """Build modern card-based layout"""
        
        # Main container with padding
        main_container = ttk.Frame(self.root)
        main_container.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        
        # Header with title and controls
        header = ttk.Frame(main_container, style="Card.TFrame")
        header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 20))
        header.grid_columnconfigure(1, weight=1)
        
        # Title
        title_lbl = ttk.Label(header, text="🤖 AGENT-i", style="Title.TLabel")
        title_lbl.grid(row=0, column=0, padx=20, pady=15)
        
        # Status indicator
        status_frame = ttk.Frame(header)
        status_frame.grid(row=0, column=1, padx=20)
        
        ttk.Label(status_frame, text="Status:", style="Muted.TLabel").grid(row=0, column=0, padx=(0, 8))
        self.state_lbl = ttk.Label(status_frame, textvariable=self.state_var, style="Header.TLabel")
        self.state_lbl.grid(row=0, column=1)
        
        # Control buttons
        controls = ttk.Frame(header)
        controls.grid(row=0, column=2, padx=20, pady=15)
        
        self.start_btn = ttk.Button(controls, text="▶ Start Agent", command=self.start_agent, 
                                   style="Success.TButton")
        self.start_btn.grid(row=0, column=0, padx=(0, 8))
        
        self.stop_btn = ttk.Button(controls, text="⏹ Stop Agent", command=self.stop_agent,
                                  style="Danger.TButton")
        self.stop_btn.grid(row=0, column=1, padx=(0, 8))
        
        self.refresh_btn = ttk.Button(controls, text="🔄 Refresh", command=self.refresh_views)
        self.refresh_btn.grid(row=0, column=2, padx=(0, 8))
        
        self.export_btn = ttk.Button(controls, text="📥 Export", command=self.export_logs)
        self.export_btn.grid(row=0, column=3)

        # Task Management Card
        tasks_card = ttk.Frame(main_container, style="Card.TFrame")
        tasks_card.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(0, 20))
        
        tasks_header = ttk.Label(tasks_card, text="Task Queue", style="Header.TLabel")
        tasks_header.grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="w")
        
        # Task list with modern styling
        list_frame = ttk.Frame(tasks_card)
        list_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=20, pady=(0, 15))
        
        self.tasks_list = tk.Listbox(list_frame, height=12, font=self.body_font,
                                    bg=COLORS['surface_light'], fg=COLORS['text'],
                                    selectbackground=COLORS['primary'], 
                                    selectforeground='white', relief="flat",
                                    borderwidth=0, highlightthickness=1,
                                    highlightcolor=COLORS['primary'])
        self.tasks_list.grid(row=0, column=0, sticky="nsew")
        
        tasks_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tasks_list.yview)
        self.tasks_list.configure(yscroll=tasks_scroll.set)
        tasks_scroll.grid(row=0, column=1, sticky="ns")
        
        # Task input
        input_frame = ttk.Frame(tasks_card)
        input_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 20))
        input_frame.grid_columnconfigure(0, weight=1)
        
        self.new_task_entry = ttk.Entry(input_frame, font=self.body_font)
        self.new_task_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.new_task_entry.bind('<Return>', lambda e: self.add_task())
        
        self.add_task_btn = ttk.Button(input_frame, text="➕ Add Task", command=self.add_task)
        self.add_task_btn.grid(row=0, column=1)

        # Execution Logs Card
        logs_card = ttk.Frame(main_container, style="Card.TFrame")
        logs_card.grid(row=1, column=1, columnspan=2, sticky="nsew", padx=(10, 0))
        
        logs_header = ttk.Label(logs_card, text="Execution History", style="Header.TLabel")
        logs_header.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="w")
        
        # Treeview for logs
        logs_frame = ttk.Frame(logs_card)
        logs_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 15))
        
        columns = ("time", "task", "result")
        self.logs = ttk.Treeview(logs_frame, columns=columns, show="headings", selectmode="browse")
        self.logs.heading("time", text="⏰ Time")
        self.logs.heading("task", text="⚡ Task") 
        self.logs.heading("result", text="📄 Result (first 200 chars)")
        self.logs.column("time", width=160, stretch=False)
        self.logs.column("task", width=280, stretch=True)
        self.logs.column("result", width=400, stretch=True)
        self.logs.grid(row=0, column=0, sticky="nsew")
        
        logs_scroll_y = ttk.Scrollbar(logs_frame, orient="vertical", command=self.logs.yview)
        self.logs.configure(yscroll=logs_scroll_y.set)
        logs_scroll_y.grid(row=0, column=1, sticky="ns")

        # Log Detail Card
        detail_card = ttk.Frame(main_container, style="Card.TFrame")
        detail_card.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(20, 0))
        
        detail_header = ttk.Label(detail_card, text="📋 Selected Log Details", style="Header.TLabel")
        detail_header.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="w")
        
        detail_frame = ttk.Frame(detail_card)
        detail_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        
        self.detail = ScrolledText(detail_frame, height=8, wrap=tk.WORD, font=self.mono_font,
                                  bg=COLORS['surface_light'], fg=COLORS['text'],
                                  insertbackground=COLORS['text'], relief="flat",
                                  borderwidth=0)
        self.detail.grid(row=0, column=0, sticky="nsew")
        self.logs.bind("<<TreeviewSelect>>", self._on_log_select)

    def _configure_grid(self):
        """Configure grid weights for responsive layout"""
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        
        # Main container configuration
        main_container = self.root.winfo_children()[0]
        main_container.grid_columnconfigure(0, weight=1)
        main_container.grid_columnconfigure(1, weight=2) 
        main_container.grid_columnconfigure(2, weight=1)
        main_container.grid_rowconfigure(1, weight=2)
        main_container.grid_rowconfigure(2, weight=1)
        
        # Configure internal frames
        for child in main_container.winfo_children():
            if hasattr(child, 'grid_columnconfigure'):
                child.grid_columnconfigure(0, weight=1)
                if hasattr(child, 'grid_rowconfigure'):
                    child.grid_rowconfigure(1, weight=1)

    # ---------- Agent control ----------
    def start_agent(self):
        if self.agent_thread and self.agent_thread.is_alive():
            return
        self.stop_event.clear()
        self.agent_thread = threading.Thread(target=self._agent_loop, name="agent-loop", daemon=True)
        self.agent_thread.start()
        self.state_var.set("autonomous")

    def stop_agent(self):
        if not self.agent_thread:
            self.state_var.set("stopped")
            return
        self.stop_event.set()
        self.agent_thread.join(timeout=5)
        self.state_var.set("stopped")
        self.agent_thread = None
        # Persist state
        mem = core.load_memory()
        mem.setdefault("state", {})
        mem["state"]["mode"] = "stopped"
        core.save_memory(mem)

    def _agent_loop(self):
        # Initialize state
        with self.lock:
            mem = core.load_memory()
            mem.setdefault("state", {})
            mem["state"]["mode"] = "autonomous"
            core.save_memory(mem)

        while not self.stop_event.is_set():
            with self.lock:
                core.execute_next_task()
            # Allow quick stop
            if self.stop_event.wait(SLEEP_SECS):
                break

    # ---------- Data ops ----------
    def refresh_views(self):
        with self.lock:
            mem = self._safe_load_memory()
        # State
        state = mem.get("state", {})
        mode = state.get("mode", "stopped")
        self.state_var.set(mode)
        # Tasks
        self.tasks_list.delete(0, tk.END)
        for t in mem.get("tasks", []):
            self.tasks_list.insert(tk.END, t)
        # Logs -> latest first
        self.logs.delete(*self.logs.get_children())
        logs = list(core.get_logs(mem))[-MAX_LOG_ROWS:][::-1]
        for i, e in enumerate(logs):
            time_str = e.get("timestamp") or ts_fmt(time.time())
            task = str(e.get("task", ""))
            result = str(e.get("output", ""))[:200].replace("\n", " ")
            iid = f"row-{i}"
            self.logs.insert("", "end", iid=iid, values=(time_str, task, result))
            # Store full output in tags for detail view
            self.logs.set(iid, column="result", value=result)
            self.logs.item(iid, tags=(json.dumps(e),))

    def _safe_load_memory(self) -> dict:
        try:
            return core.load_memory()
        except Exception:
            return {"logs": [], "state": "stopped", "tasks": []}

    def add_task(self):
        task = self.new_task_entry.get().strip()
        if not task:
            return
        with self.lock:
            core.inject_task(task)
        self.new_task_entry.delete(0, tk.END)
        self.refresh_views()

    def export_logs(self):
        with self.lock:
            mem = self._safe_load_memory()
            logs = core.get_logs(mem)
        if not logs:
            messagebox.showinfo("Export logs", "No logs to export yet.")
            return
        path = filedialog.asksaveasfilename(
            title="Export logs",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
            initialfile=f"agent_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for e in logs:
                    f.write(f"[{e.get('timestamp','')}] $ {e.get('task','')}\n")
                    f.write((e.get('output','') or "") + "\n\n")
            messagebox.showinfo("Export logs", f"Saved to {path}")
        except Exception as e:
            messagebox.showerror("Export logs", f"Failed to save: {e}")

    # ---------- Events ----------
    def _on_log_select(self, _event=None):
        sel = self.logs.selection()
        if not sel:
            return
        try:
            payload = self.logs.item(sel[0], "tags")[0]
            entry = json.loads(payload)
        except Exception:
            entry = {}
        self.detail.delete("1.0", tk.END)
        self.detail.insert(tk.END, entry.get("output", ""))

    def _poll_refresh(self):
        # Periodically refresh views to reflect background activity
        try:
            self.refresh_views()
        finally:
            self.root.after(REFRESH_MS, self._poll_refresh)

    def on_close(self):
        try:
            self.stop_agent()
        finally:
            self.root.destroy()


def main():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        print("Tkinter failed to start (likely no DISPLAY).\n- If running in Codespaces/Headless: run this on a desktop or enable X11/VNC.\n- On Ubuntu desktop: sudo apt-get install -y python3-tk", f"\nDetails: {e}")
        sys.exit(2)
    AgentApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
