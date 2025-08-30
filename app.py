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
    'bg': '#eef2ff',
    'surface': '#ffffff',
    'surface_light': '#f8faff',
    'primary': '#6c63ff',
    'primary_dark': '#4a43d0',
    'success': '#10b981',
    'danger': '#ef4444',
    'warning': '#f59e0b',
    'text': '#1f2343',
    'text_muted': '#6b6f86',
    'border': '#e5e9f5',
    'accent': '#a78bfa'
}

# Common UI strings
TITLE_EXPORT = "Export logs"
TITLE_PLAN = "Plan tasks"
TITLE_REFLECT = "Reflect"
TITLE_SYNTH = "Synthesis"

# Style and font constants
FONT_SANS = "Segoe UI"
FONT_MONO = "Consolas"
ST_CARD = "Card.TFrame"
ST_TITLE_LABEL = "Title.TLabel"
ST_HEADER_LABEL = "Header.TLabel"
ST_MUTED_LABEL = "Muted.TLabel"
ST_BTN_SUCCESS = "Success.TButton"
ST_BTN_DANGER = "Danger.TButton"


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
        self.agent_thread = None
        self.stop_event = threading.Event()
        self.auto_thread = None
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
    self.title_font = tkFont.Font(family=FONT_SANS, size=16, weight="bold")
    self.header_font = tkFont.Font(family=FONT_SANS, size=12, weight="bold")
    self.body_font = tkFont.Font(family=FONT_SANS, size=10)
    self.mono_font = tkFont.Font(family=FONT_MONO, size=9)

    style = ttk.Style()
    style.theme_use('clam')
    # Base
    style.configure("TFrame", background=COLORS['bg'], relief="flat")
    style.configure(ST_CARD, background=COLORS['surface'], relief="solid", borderwidth=1)
    style.configure("TLabel", background=COLORS['bg'], foreground=COLORS['text'], font=self.body_font)
    style.configure(ST_TITLE_LABEL, background=COLORS['bg'], foreground=COLORS['text'], font=self.title_font)
    style.configure(ST_HEADER_LABEL, background=COLORS['surface'], foreground=COLORS['text'], font=self.header_font)
    style.configure(ST_MUTED_LABEL, background=COLORS['bg'], foreground=COLORS['text_muted'], font=self.body_font)
    # Buttons
    style.configure("TButton", background=COLORS['primary'], foreground="white", font=self.body_font, relief="flat", borderwidth=0, padding=(12, 8))
    style.map("TButton", background=[('active', COLORS['primary_dark'])], relief=[('pressed', 'flat')])
    style.configure(ST_BTN_SUCCESS, background=COLORS['success'])
    style.map("Success.TButton", background=[('active', '#059669')])
    style.configure(ST_BTN_DANGER, background=COLORS['danger'])
    style.map("Danger.TButton", background=[('active', '#dc2626')])
    # Entry & Treeview
    style.configure("TEntry", fieldbackground=COLORS['surface_light'], foreground=COLORS['text'], borderwidth=1, relief="solid", font=self.body_font, insertcolor=COLORS['text'])
    style.configure("Treeview", background=COLORS['surface'], foreground=COLORS['text'], fieldbackground=COLORS['surface'], font=self.body_font, rowheight=24)
    style.configure("Treeview.Heading", background=COLORS['surface_light'], foreground=COLORS['text'], font=self.header_font)

    def _build_layout(self):
        """Build modern card-based layout"""
        # Main container with padding
        main_container = ttk.Frame(self.root)
        main_container.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        # Header with title and controls
    header = ttk.Frame(main_container, style=ST_CARD)
        header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 20))
        header.grid_columnconfigure(1, weight=1)

        # Title
    title_lbl = ttk.Label(header, text="🤖 AGENT-i", style=ST_TITLE_LABEL)
        title_lbl.grid(row=0, column=0, padx=20, pady=15)

        # Status indicator
        status_frame = ttk.Frame(header)
        status_frame.grid(row=0, column=1, padx=20)
    ttk.Label(status_frame, text="Status:", style=ST_MUTED_LABEL).grid(row=0, column=0, padx=(0, 8))
    self.state_lbl = ttk.Label(status_frame, textvariable=self.state_var, style=ST_HEADER_LABEL)
        self.state_lbl.grid(row=0, column=1)

        # Control buttons
        controls = ttk.Frame(header)
        controls.grid(row=0, column=2, padx=20, pady=15)
    self.start_btn = ttk.Button(controls, text="▶ Start Agent", command=self.start_agent, style=ST_BTN_SUCCESS)
        self.start_btn.grid(row=0, column=0, padx=(0, 8))
    self.stop_btn = ttk.Button(controls, text="⏹ Stop Agent", command=self.stop_agent, style=ST_BTN_DANGER)
        self.stop_btn.grid(row=0, column=1, padx=(0, 8))
        self.refresh_btn = ttk.Button(controls, text="🔄 Refresh", command=self.refresh_views)
        self.refresh_btn.grid(row=0, column=2, padx=(0, 8))
        self.export_btn = ttk.Button(controls, text="📥 Export", command=self.export_logs)
        self.export_btn.grid(row=0, column=3)

        # Autonomy helpers inline controls
    auto_frame = ttk.Frame(header)
        auto_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 12))
        auto_frame.grid_columnconfigure(6, weight=1)
    ttk.Label(auto_frame, text="Auto steps:", style=ST_MUTED_LABEL).grid(row=0, column=0, padx=(0, 6))
        self.auto_steps = ttk.Entry(auto_frame, width=6)
        self.auto_steps.insert(0, "5")
        self.auto_steps.grid(row=0, column=1, padx=(0, 10))
    ttk.Label(auto_frame, text="Goal:", style=ST_MUTED_LABEL).grid(row=0, column=2, padx=(0, 6))
        self.auto_goal = ttk.Entry(auto_frame, width=40)
        self.auto_goal.grid(row=0, column=3, padx=(0, 10))
        ttk.Button(auto_frame, text="⚙️ Auto Cycle", command=self.auto_cycle).grid(row=0, column=4, padx=(0, 10))
        ttk.Button(auto_frame, text="🧭 Plan", command=self.plan_tasks).grid(row=0, column=5, padx=(0, 10))
        ttk.Button(auto_frame, text="🪞 Reflect", command=self.reflect).grid(row=0, column=6, padx=(0, 10))
        ttk.Button(auto_frame, text="🧠 Synthesize", command=self.synthesize).grid(row=0, column=7)

        # Task Management Card
    tasks_card = ttk.Frame(main_container, style=ST_CARD)
        tasks_card.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(0, 20))
    tasks_header = ttk.Label(tasks_card, text="Task Queue", style=ST_HEADER_LABEL)
        tasks_header.grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="w")

        # Task list with modern styling
        list_frame = ttk.Frame(tasks_card)
        list_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=20, pady=(0, 15))
        self.tasks_list = tk.Listbox(list_frame, height=12, font=self.body_font, bg=COLORS['surface_light'], fg=COLORS['text'], selectbackground=COLORS['primary'], selectforeground='white', relief="flat", borderwidth=0, highlightthickness=1, highlightcolor=COLORS['primary'])
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
        # Ask AI button next to Add Task
        self.ask_ai_btn = ttk.Button(input_frame, text="💬 Ask AI", command=self.add_task_llm)
        self.ask_ai_btn.grid(row=0, column=2, padx=(8, 0))

        # Execution Logs Card
    logs_card = ttk.Frame(main_container, style=ST_CARD)
        logs_card.grid(row=1, column=1, columnspan=2, sticky="nsew", padx=(10, 0))
    logs_header = ttk.Label(logs_card, text="Execution History", style=ST_HEADER_LABEL)
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
    detail_card = ttk.Frame(main_container, style=ST_CARD)
        detail_card.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(20, 0))
    detail_header = ttk.Label(detail_card, text="📋 Selected Log Details", style=ST_HEADER_LABEL)
        detail_header.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="w")
        detail_frame = ttk.Frame(detail_card)
        detail_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.detail = ScrolledText(detail_frame, height=8, wrap=tk.WORD, font=self.mono_font, bg=COLORS['surface_light'], fg=COLORS['text'], insertbackground=COLORS['text'], relief="flat", borderwidth=0)
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

    # ---------- Autonomy helpers ----------
    def auto_cycle(self):
        if self.auto_thread and self.auto_thread.is_alive():
            return
        try:
            steps = int(self.auto_steps.get() or 5)
        except Exception:
            steps = 5
        goal = self.auto_goal.get().strip() or None
        def run():
            try:
                core.autonomy_cycle(goal=goal, max_steps=max(1, min(steps, 50)))
            finally:
                self.refresh_views()
        self.auto_thread = threading.Thread(target=run, name="auto-cycle", daemon=True)
        self.auto_thread.start()

    def plan_tasks(self):
        goal = self.auto_goal.get().strip() or None
        try:
            tasks = core.plan_tasks_with_llm(goal=goal)
        except Exception as e:
            messagebox.showerror(TITLE_PLAN, f"Planning failed: {e}")
            return
        if not tasks:
            messagebox.showinfo(TITLE_PLAN, "No tasks proposed (LLM unavailable or empty response).")
            return
        with self.lock:
            for t in tasks[:5]:
                core.inject_task(t)
        self.refresh_views()

    def reflect(self):
        try:
            tasks = core.reflect_on_last_output() or []
        except Exception as e:
            messagebox.showerror(TITLE_REFLECT, f"Reflection failed: {e}")
            return
        if not tasks:
            messagebox.showinfo("Reflect", "No suggestions (need at least one prior log, or LLM unavailable).")
            return
        with self.lock:
            for t in tasks[:3]:
                core.inject_task(t)
        self.refresh_views()

    def synthesize(self):
        try:
            out = core.synthesize_knowledge()
        except Exception as e:
            messagebox.showerror(TITLE_SYNTH, f"Failed: {e}")
            return
        if out:
            messagebox.showinfo(TITLE_SYNTH, "Session summary updated in state.")
        else:
            messagebox.showinfo(TITLE_SYNTH, "No summary (LLM unavailable).")

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
        # Skip code-fence-only markers
        try:
            if callable(getattr(core, "_is_code_fence_only", None)) and core._is_code_fence_only(task):  # type: ignore[attr-defined]
                messagebox.showinfo("Ignored", "Code-fence-only input was ignored.")
                self.new_task_entry.delete(0, tk.END)
                return
        except Exception:
            pass
        # Coerce non-shell to 'llm:' unless already prefixed
        try:
            if not task.lower().startswith('llm:'):
                is_cmd = getattr(core, "_is_shell_command", None)
                if callable(is_cmd) and not is_cmd(task):
                    task = f"llm: {task}"
        except Exception:
            pass
        with self.lock:
            core.inject_task(task)
        self.new_task_entry.delete(0, tk.END)
        self.refresh_views()

    def add_task_llm(self):
        task = self.new_task_entry.get().strip()
        if not task:
            return
        # Skip code-fence-only markers
        try:
            if callable(getattr(core, "_is_code_fence_only", None)) and core._is_code_fence_only(task):  # type: ignore[attr-defined]
                messagebox.showinfo("Ignored", "Code-fence-only input was ignored.")
                self.new_task_entry.delete(0, tk.END)
                return
        except Exception:
            pass
        if not task.lower().startswith('llm:'):
            task = f"llm: {task}"
        with self.lock:
            core.inject_task(task)
        self.new_task_entry.delete(0, tk.END)
        self.refresh_views()

    def export_logs(self):
        with self.lock:
            mem = self._safe_load_memory()
            logs = core.get_logs(mem)
        if not logs:
            messagebox.showinfo(TITLE_EXPORT, "No logs to export yet.")
            return
        path = filedialog.asksaveasfilename(
            title=TITLE_EXPORT,
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
            messagebox.showinfo(TITLE_EXPORT, f"Saved to {path}")
        except Exception as e:
            messagebox.showerror(TITLE_EXPORT, f"Failed to save: {e}")

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
