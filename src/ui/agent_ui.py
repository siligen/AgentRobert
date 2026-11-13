import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox, ttk
import threading
import os
import subprocess
import time
import urllib.request
import json
import queue
import markdown
from tkhtmlview import HTMLLabel
from datetime import datetime
from docx import Document
from docx.shared import Pt, RGBColor
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from src.core.document_engine import DocumentAIEngine

# Import communication tools for the push-client
import src.tools.communication_tools
from src.tools.communication_tools import fetch_unopened_emails, draft_or_send_email, get_credential, run_push_email_client, run_push_telegram_client, telegram_send_or_draft

class OllamaChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Agent Robert - Cognitive Local Workspace")
        self.root.geometry("750x800")
        self.root.configure(bg="#121212")
        
        # --- SESSION ISOLATION SETUP ---
        base_workspace = os.path.abspath("workspace")
        self.config_dir = os.path.abspath("config")
        self.cred_file = os.path.join(self.config_dir, "credentials.md")
        
        session_id = int(time.time())
        self.session_workspace = os.path.join(base_workspace, f"session_{session_id}")
        os.makedirs(self.session_workspace, exist_ok=True)
        # Expose the session path via environment variable for all internal tools
        os.environ["AGENT_WORKSPACE"] = self.session_workspace
        # Expose the application startup directory to expand the search/read space
        os.environ["APP_START_DIR"] = os.path.abspath(os.getcwd())
        
        self.engine = None
        self.is_thinking = False
        self.zoom_factor = 1.0
        
        # Sequential Task Processing Queue
        self.task_queue = queue.Queue()
        
        # Push-based Email Client State
        self.email_client_enabled = tk.BooleanVar(value=False)
        
        # Push-based Telegram Client State
        self.telegram_client_enabled = tk.BooleanVar(value=False)
        
        # Real-time state tracking dict for architecture visualization
        self.system_state = {
            "orchestrator_status": "Starting up...",
            "orchestrator_active_since": None,
            "active_tool": None,
            "spawned_agents": [],
            "tools_discovered": {},
            "token_usage": {"master": 0, "agents": {}}
        }

        # --- DEFAULT CREDENTIAL VALUES ---
        self.default_credentials = {
            "IMAP_SERVER": "imap.gmail.com",
            "SMTP_SERVER": "smtp.gmail.com"
        }

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Send.TButton", background="#2E7D32", foreground="#FFFFFF", font=("Arial", 10, "bold"))
        self.style.configure("Util.TButton", background="#333333", foreground="#FFFFFF", font=("Arial", 9))
        self.style.configure("Wait.TButton", background="#222222", foreground="#888888", font=("Arial", 10, "bold"))
        self.style.configure("Thinking.TButton", background="#B71C1C", foreground="#FFFFFF", font=("Arial", 10, "bold"))
        
        # Add high-visibility button configurations for dialog boxes
        self.style.configure("Success.TButton", background="#2E7D32", foreground="#FFFFFF", font=("Arial", 10, "bold"))
        self.style.configure("Danger.TButton", background="#C62828", foreground="#FFFFFF", font=("Arial", 10, "bold"))
        self.style.configure("Primary.TButton", background="#1565C0", foreground="#FFFFFF", font=("Arial", 10, "bold"))

        # --- DUAL PANE LAYOUT SYSTEM ---
        self.paned_window = tk.PanedWindow(
            root, 
            orient=tk.VERTICAL, 
            bg="#181818", 
            bd=0, 
            sashwidth=8,
            sashrelief=tk.RAISED,
            sashcursor="sb_v_double_arrow"
        )
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        # 1. TOP ARCHITECTURE FRAME
        top_pane_frame = tk.Frame(self.paned_window, bg="#181818", bd=1, relief=tk.FLAT)
        self.paned_window.add(top_pane_frame, minsize=240, height=280)

        arch_title_bar = tk.Frame(top_pane_frame, bg="#212121", height=30)
        arch_title_bar.pack(fill=tk.X, side=tk.TOP)
        
        arch_title_lbl = tk.Label(
            arch_title_bar, 
            text="⚙️ AGENT ROBERT: COGNITIVE SYSTEM ARCHITECTURE & PIPELINE FEED", 
            bg="#212121", 
            fg="#FFB74D", 
            font=("Arial", 9, "bold")
        )
        arch_title_lbl.pack(side=tk.LEFT, padx=10, pady=5)

        fit_btn = self.create_custom_control_btn(arch_title_bar, "Fit View", self.zoom_fit)
        fit_btn.pack(side=tk.RIGHT, padx=5, pady=3)
        
        zoom_out_btn = self.create_custom_control_btn(arch_title_bar, "Zoom Out", self.zoom_out)
        zoom_out_btn.pack(side=tk.RIGHT, padx=5, pady=3)
        
        zoom_in_btn = self.create_custom_control_btn(arch_title_bar, "Zoom In", self.zoom_in)
        zoom_in_btn.pack(side=tk.RIGHT, padx=5, pady=3)

        canvas_container = tk.Frame(top_pane_frame, bg="#121212")
        canvas_container.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        self.canvas = tk.Canvas(canvas_container, bg="#121212", bd=0, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self.start_pan)
        self.canvas.bind("<B1-Motion>", self.pan_canvas)
        self.canvas.bind("<MouseWheel>", self.mouse_zoom)
        self.canvas.bind("<Button-4>", self.mouse_zoom)
        self.canvas.bind("<Button-5>", self.mouse_zoom)
        self.canvas.bind("<Configure>", lambda e: self.zoom_fit())

        # 2. BOTTOM CHAT WORKSPACE FRAME
        bottom_pane_frame = tk.Frame(self.paned_window, bg="#121212")
        self.paned_window.add(bottom_pane_frame, minsize=350)

        top_bar = tk.Frame(bottom_pane_frame, bg="#121212")
        top_bar.pack(padx=15, pady=(10, 0), fill=tk.X)

        ttk.Button(top_bar, text="📂 Read File", style="Util.TButton", command=self.import_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(top_bar, text="💾 Save Chat Log", style="Util.TButton", command=self.export_chat).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(top_bar, text="⚙️ Config Comm Cred", style="Util.TButton", command=self.configure_comm_credentials).pack(side=tk.LEFT)

        # Push Email Client Toggle
        self.email_client_cb = ttk.Checkbutton(
            top_bar, 
            text="Email Client", 
            variable=self.email_client_enabled
        )
        self.email_client_cb.pack(side=tk.LEFT, padx=15)

        # Push Telegram Client Toggle
        self.telegram_client_cb = ttk.Checkbutton(
            top_bar,
            text="Telegram Client",
            variable=self.telegram_client_enabled
        )
        self.telegram_client_cb.pack(side=tk.LEFT, padx=5)

        # --- MODEL SELECTION WIDGET ---
        tk.Label(top_bar, text="Model:", bg="#121212", fg="#E0E0E0", font=("Arial", 9)).pack(side=tk.LEFT, padx=(15, 2))
        self.model_var = tk.StringVar()
        self.model_dropdown = ttk.Combobox(top_bar, textvariable=self.model_var, state="readonly", width=20)
        self.model_dropdown.pack(side=tk.LEFT, padx=(0, 5))
        self.model_dropdown.bind("<<ComboboxSelected>>", self.on_model_changed)
        
        # Async fetch models list from Ollama
        threading.Thread(target=self.fetch_ollama_models, daemon=True).start()
        # ------------------------------

        self.file_status = tk.Label(top_bar, text="No document attached", bg="#121212", fg="#9E9E9E", font=("Arial", 9, "italic"))
        self.file_status.pack(side=tk.RIGHT, padx=5)

        self.chat_history_html = ""
        self.chat_display = HTMLLabel(
            bottom_pane_frame, 
            html='<body style="background-color: #1E1E1E; margin: 0; padding: 0;"></body>', 
            bg="#1E1E1E", fg="#E0E0E0"
        )
        self.chat_display.pack(padx=15, pady=10, fill=tk.BOTH, expand=True)
        self.chat_display.config(background="#1E1E1E")
        
        self.append_msg("System Info", f"Active Workspace Session Dir: {self.session_workspace}", "system")
        self.append_msg("Agent Robert", "Waking up local model environment and execution interfaces...", "system")

        bottom_control_frame = tk.Frame(bottom_pane_frame, bg="#121212")
        bottom_control_frame.pack(padx=15, pady=(0, 15), fill=tk.X)
        
        self.entry_box = tk.Entry(bottom_control_frame, bg="#2D2D2D", fg="#FFFFFF", insertbackground="white", state='disabled')
        self.entry_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.entry_box.bind("<Return>", lambda e: self.send_message())

        self.send_button = ttk.Button(bottom_control_frame, text="Wait...", style="Wait.TButton", command=self.send_message)
        self.send_button.pack(side=tk.RIGHT)

        threading.Thread(target=self.async_init, daemon=True).start()
        self.schedule_timer_update()
        
        # Start Push Clients Background Daemons
        threading.Thread(target=run_push_email_client, args=(self._on_email_received, lambda: self.email_client_enabled.get()), daemon=True).start()
        threading.Thread(target=self._telegram_daemon_runner, daemon=True).start()
        
        # Start Task Queue Worker
        threading.Thread(target=self._process_queue, daemon=True).start()

    def _process_queue(self):
        """Sequential worker that handles tasks from the queue one by one."""
        while True:
            try:
                # Blocks until a task is available
                task = self.task_queue.get()
                if task is None: break # Poison pill to stop thread
                
                # task is a tuple: (func, args, kwargs)
                func, args, kwargs = task
                func(*args, **kwargs)
                
                self.task_queue.task_done()
            except Exception as e:
                print(f"Queue Worker Error: {e}")

    def _telegram_daemon_runner(self):
        """Background thread to initialize the Telegram MTProto client when enabled."""
        server_started = False
        while True:
            if self.telegram_client_enabled.get() and not server_started:
                creds = self.load_creds()
                api_id = creds.get("TELEGRAM_API_ID")
                api_hash = creds.get("TELEGRAM_API_HASH")
                bot_token = creds.get("TELEGRAM_BOT_TOKEN")
                
                if api_id and api_hash and bot_token:
                    server_started = True
                    try:
                        # Telethon is bidirectional by nature (MTProto)
                        run_push_telegram_client(self.process_incoming_telegram)
                    except Exception as e:
                        print(f"Telegram client error: {e}")
                        server_started = False
            time.sleep(5)

    def process_incoming_telegram(self, text, sender, chat_id):
        """Handles the injection of Telegram text messages and queues the agent pipeline."""
        subject = f"Telegram Message ({chat_id})"
        self.append_msg("Telegram User", f"[{subject}]\nFrom: {sender}\n\n{text}", "user")
        
        # UI state update
        self.is_thinking = True
        self.entry_box.config(state='disabled')
        self.send_button.config(text="🔴 Stop", style="Thinking.TButton")
        
        # Queue the task instead of spawning a thread
        self.task_queue.put((self._run_engine_task, (text, sender, subject, chat_id), {}))

    def _on_email_received(self, body, sender, subject):
        """Thread-safe UI injection handler called by the isolated push listener."""
        self.root.after(0, lambda: self.process_incoming_email(body, sender, subject))

    def process_incoming_email(self, body, sender, subject):
        """Handles the injection of email content and queues the agent pipeline."""
        self.append_msg("Email User", f"[{subject}]\n{body}", "user")
        
        # Update UI state to indicate processing
        self.is_thinking = True
        self.entry_box.config(state='disabled')
        self.send_button.config(text="🔴 Stop", style="Thinking.TButton")
        
        # Queue the task
        self.task_queue.put((self._run_engine_task, (body, sender, subject), {}))

    def fetch_ollama_models(self):
        """Fetches available Ollama tags dynamically to populate the dropdown menu."""
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode())
                models = [m['name'] for m in data.get('models', [])]
            
            if models:
                self.root.after(0, self.update_model_dropdown, models)
            else:
                self.root.after(0, self.update_model_dropdown, ["gemma4:31b"])
        except Exception as e:
            self.root.after(0, self.update_model_dropdown, ["gemma4:31b"])

    def update_model_dropdown(self, models):
        self.model_dropdown['values'] = models
        if models:
            if self.model_var.get() not in models:
                self.model_dropdown.current(0)
            if self.engine:
                self.engine.update_model(self.model_var.get())

    def on_model_changed(self, event=None):
        selected_model = self.model_var.get()
        if self.engine:
            try:
                self.engine.update_model(selected_model)
                self.append_msg("System Info", f"Active LLM model safely switched to: {selected_model}", "system")
            except Exception as e:
                self.append_msg("System Error", f"Failed to switch model runtime: {str(e)}", "system")

    def create_custom_control_btn(self, parent, text, command):
        btn = tk.Label(
            parent, text=text, bg="#333333", fg="#FFB74D", font=("Arial", 8, "bold"),
            padx=10, pady=3, relief=tk.FLAT, cursor="hand2"
        )
        btn.bind("<Button-1>", lambda e: command())
        btn.bind("<Enter>", lambda e: btn.config(bg="#444444", fg="#FFA726"))
        btn.bind("<Leave>", lambda e: btn.config(bg="#333333", fg="#FFB74D"))
        return btn

    def load_creds(self):
        creds = {}
        if os.path.exists(self.cred_file):
            with open(self.cred_file, "r") as f:
                for line in f:
                    if ":" in line and not line.startswith("#"):
                        k, v = line.split(":", 1)
                        creds[k.strip().replace("**", "")] = v.strip()
        return creds

    def save_creds(self, creds):
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.cred_file, "w") as f:
            f.write("# Communication Credentials\n\n")
            for k, v in creds.items():
                if v:
                    f.write(f"**{k}**: {v}\n")

    def configure_comm_credentials(self):
        """Starts the sequential communication configuration workflow."""
        self.configure_email_credentials()

    def configure_email_credentials(self):
        """Step 1: Configure Email Fields."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Configure Email Credentials (1/3)")
        dialog.geometry("520x350")
        dialog.configure(bg="#1E1E1E")
        dialog.transient(self.root)
        dialog.grab_set()

        creds = self.load_creds()
        entries = {}
        # Added AUTHORIZED_SENDERS to config UI
        fields = ["IMAP_SERVER", "SMTP_SERVER", "EMAIL_ADDRESS", "EMAIL_PASSWORD", "AUTHORIZED_OWNER", "AUTHORIZED_SENDERS"]
        
        tk.Label(dialog, text="Step 1: Email Configuration", bg="#1E1E1E", fg="#FFB74D", font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=2, pady=10)

        for idx, field in enumerate(fields):
            tk.Label(dialog, text=field.replace("_", " ") + ":", bg="#1E1E1E", fg="#FFFFFF").grid(row=idx+1, column=0, padx=10, pady=5, sticky="e")
            entry = tk.Entry(dialog, width=40, bg="#2D2D2D", fg="#FFFFFF", insertbackground="white")
            entry.grid(row=idx+1, column=1, padx=10, pady=5)
            # Populate with existing or default
            default_val = self.default_credentials.get(field, "")
            entry.insert(0, creds.get(field, default_val))
            entries[field] = entry

        def save_and_next():
            for field in fields:
                val = entries[field].get().strip()
                if val:
                    creds[field] = val
                elif field in creds:
                    del creds[field]
            self.save_creds(creds)
            dialog.destroy()
            self.configure_telegram_credentials()

        def skip():
            dialog.destroy()
            self.configure_telegram_credentials()

        btn_frame = tk.Frame(dialog, bg="#1E1E1E")
        btn_frame.grid(row=len(fields)+1, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="Save & Next", style="Primary.TButton", command=save_and_next).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Skip", style="Util.TButton", command=skip).pack(side=tk.LEFT, padx=10)

    def configure_telegram_credentials(self):
        """Step 2: Configure Telegram Fields."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Configure Telegram Credentials (2/3)")
        dialog.geometry("520x320")
        dialog.configure(bg="#1E1E1E")
        dialog.transient(self.root)
        dialog.grab_set()

        creds = self.load_creds()
        entries = {}
        fields = ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_BOT_TOKEN", "AUTHORIZED_TELEGRAM_USERS"]
        
        tk.Label(dialog, text="Step 2: Telegram Configuration", bg="#1E1E1E", fg="#FFB74D", font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=2, pady=10)

        for idx, field in enumerate(fields):
            tk.Label(dialog, text=field.replace("_", " ") + ":", bg="#1E1E1E", fg="#FFFFFF").grid(row=idx+1, column=0, padx=10, pady=5, sticky="e")
            entry = tk.Entry(dialog, width=40, bg="#2D2D2D", fg="#FFFFFF", insertbackground="white")
            entry.grid(row=idx+1, column=1, padx=10, pady=5)
            # Populate with existing
            entry.insert(0, creds.get(field, ""))
            entries[field] = entry

        def save_and_next():
            for field in fields:
                val = entries[field].get().strip()
                if val:
                    creds[field] = val
                elif field in creds:
                    del creds[field]
            self.save_creds(creds)
            dialog.destroy()
            self.configure_whatsapp_credentials()

        def skip():
            dialog.destroy()
            self.configure_whatsapp_credentials()

        btn_frame = tk.Frame(dialog, bg="#1E1E1E")
        btn_frame.grid(row=len(fields)+1, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="Save & Next", style="Primary.TButton", command=save_and_next).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Skip", style="Util.TButton", command=skip).pack(side=tk.LEFT, padx=10)

    def configure_whatsapp_credentials(self):
        """Step 3: Configure WhatsApp Fields."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Configure WhatsApp Credentials (3/3)")
        dialog.geometry("520x220")
        dialog.configure(bg="#1E1E1E")
        dialog.transient(self.root)
        dialog.grab_set()

        creds = self.load_creds()
        entries = {}
        fields = ["WHATSAPP_API_TOKEN", "WHATSAPP_PHONE_ID"]
        
        tk.Label(dialog, text="Step 3: WhatsApp Configuration", bg="#1E1E1E", fg="#FFB74D", font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=2, pady=10)

        for idx, field in enumerate(fields):
            tk.Label(dialog, text=field.replace("_", " ") + ":", bg="#1E1E1E", fg="#FFFFFF").grid(row=idx+1, column=0, padx=10, pady=5, sticky="e")
            entry = tk.Entry(dialog, width=40, bg="#2D2D2D", fg="#FFFFFF", insertbackground="white")
            entry.grid(row=idx+1, column=1, padx=10, pady=5)
            # Populate with existing
            entry.insert(0, creds.get(field, ""))
            entries[field] = entry

        def save_and_finish():
            for field in fields:
                val = entries[field].get().strip()
                if val:
                    creds[field] = val
                elif field in creds:
                    del creds[field]
            self.save_creds(creds)
            self.append_msg("System Guard", "Communication credentials updated in configuration.", "system")
            dialog.destroy()

        def skip():
            self.append_msg("System Guard", "Communication credentials setup completed.", "system")
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg="#1E1E1E")
        btn_frame.grid(row=len(fields)+1, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="Save & Finish", style="Success.TButton", command=save_and_finish).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Skip", style="Util.TButton", command=skip).pack(side=tk.LEFT, padx=10)

    def ask_credentials_ui(self, required_keys):
        """Thread-safe UI prompt to ask for strictly missing credentials."""
        result = [False]
        event = threading.Event()

        def draw():
            dialog = tk.Toplevel(self.root)
            dialog.title("Missing Credentials Required")
            dialog.geometry("500x300")
            dialog.configure(bg="#1E1E1E")
            dialog.transient(self.root)
            dialog.grab_set()
            
            tk.Label(dialog, text="The current operation requires missing credentials:", bg="#1E1E1E", fg="#FFB74D", font=("Arial", 11, "bold")).pack(pady=15)

            creds = self.load_creds()
            entries = {}
            
            form_frame = tk.Frame(dialog, bg="#1E1E1E")
            form_frame.pack(pady=10)

            for idx, field in enumerate(required_keys):
                tk.Label(form_frame, text=field.replace("_", " ") + ":", bg="#1E1E1E", fg="#FFFFFF").grid(row=idx, column=0, padx=10, pady=5, sticky="e")
                entry = tk.Entry(form_frame, width=35, bg="#2D2D2D", fg="#FFFFFF", insertbackground="white")
                entry.grid(row=idx, column=1, padx=10, pady=5)
                
                # Populate with existing or default
                default_val = self.default_credentials.get(field, "")
                entry.insert(0, creds.get(field, default_val))
                
                entries[field] = entry

            def save():
                for field in required_keys:
                    val = entries[field].get().strip()
                    if val:
                        creds[field] = val
                self.save_creds(creds)
                result[0] = True
                dialog.destroy()
                event.set()

            def cancel():
                result[0] = False
                dialog.destroy()
                event.set()

            btn_frame = tk.Frame(dialog, bg="#1E1E1E")
            btn_frame.pack(pady=20)

            # Updated tk.Button calls to styled ttk.Button calls for macOS visibility
            ttk.Button(btn_frame, text="Update", style="Success.TButton", command=save).pack(side=tk.LEFT, padx=10)
            ttk.Button(btn_frame, text="Cancel", style="Danger.TButton", command=cancel).pack(side=tk.LEFT, padx=10)
            
        self.root.after(0, draw)
        event.wait()
        return result[0]

    def ask_internet_permission_ui(self, description):
        """Thread-safe pop-up dialogue box executed in the main Tkinter thread."""
        result = [False]
        event = threading.Event()

        def draw_dialog():
            dialog = tk.Toplevel(self.root)
            dialog.title("🚨 SECURITY FIREWALL ALERT: Network Request")
            dialog.geometry("600x280")
            dialog.configure(bg="#1E1E1E")
            dialog.transient(self.root)
            dialog.grab_set()

            hdr = tk.Label(dialog, text="⚠️ NETWORK ACCESS SECURITY CONTROL CHECK", bg="#B71C1C", fg="#FFFFFF", font=("Arial", 11, "bold"), pady=8)
            hdr.pack(fill=tk.X)

            txt = tk.Message(
                dialog, 
                text=f"Agent Robert is requesting external connection permission:\n\n\"{description}\"\n\nAllow this external transaction?",
                bg="#1E1E1E", fg="#E0E0E0", font=("Arial", 11), width=560, justify=tk.LEFT
            )
            txt.pack(pady=15, padx=20, fill=tk.BOTH, expand=True)

            btn_frame = tk.Frame(dialog, bg="#1E1E1E")
            btn_frame.pack(side=tk.BOTTOM, pady=20)

            def allow():
                result[0] = True
                dialog.destroy()
                event.set()

            def deny():
                result[0] = False
                dialog.destroy()
                event.set()

            # Updated standard tk.Button calls to styled ttk.Button calls for macOS visibility
            allow_btn = ttk.Button(btn_frame, text="✅ Allow Connection", style="Success.TButton", command=allow)
            allow_btn.pack(side=tk.LEFT, padx=10)

            deny_btn = ttk.Button(btn_frame, text="❌ Deny Access", style="Danger.TButton", command=deny)
            deny_btn.pack(side=tk.LEFT, padx=10)

        self.root.after(0, draw_dialog)
        event.wait()
        return result[0]

    def async_init(self):
        try:
            # Check model value initialized from fetch, default if missing
            selected_model = self.model_var.get() or "gemma4:31b"
            
            self.engine = DocumentAIEngine(model_name=selected_model)
            self.engine.state_callback = self.handle_pipeline_event
            self.engine.permission_callback = self.ask_internet_permission_ui
            self.engine.credentials_callback = self.ask_credentials_ui
            
            self.root.after(0, self.on_init_success)
        except Exception as err:
            self.root.after(0, lambda e=err: self.append_msg("System Error", "Connection error: " + str(e), "system"))

    def on_init_success(self):
        self.system_state["orchestrator_status"] = "Ready"
        self.zoom_fit()
        self.append_msg("Agent Robert", "Ready! Local Sandbox Workspace Multi-Agent framework loaded.", "system")
        self.entry_box.config(state='normal')
        self.send_button.config(text="Send", style="Send.TButton")
        self.entry_box.focus()

    def schedule_timer_update(self):
        self.update_visualizer()
        self.root.after(1000, self.schedule_timer_update)

    def handle_pipeline_event(self, event_type: str, payload: dict):
        self.root.after(0, lambda: self._process_pipeline_event(event_type, payload))

    def _set_tool_idle(self, key):
        if key in self.system_state["tools_discovered"]:
            self.system_state["tools_discovered"][key]["status"] = "idle"
            self.system_state["tools_discovered"][key]["active_since"] = None
        self.zoom_fit()

    def _process_pipeline_event(self, event_type: str, payload: dict):
        if event_type == "master_status_change":
            status = payload.get("status", "Idle")
            self.system_state["orchestrator_status"] = status
            if status in ["Thinking...", "Executing Tool", "Processing response..."]:
                if not self.system_state.get("orchestrator_active_since"):
                    self.system_state["orchestrator_active_since"] = time.time()
            elif status in ["Idle", "Ready"]:
                self.system_state["orchestrator_active_since"] = None
        elif event_type == "master_token_update":
            self.system_state["token_usage"]["master"] = payload.get("tokens", 0)
        elif event_type == "sub_agent_token_update":
            role = payload.get("role")
            tokens = payload.get("tokens", 0)
            self.system_state["token_usage"]["agents"][role] = tokens
        elif event_type == "master_tool_start":
            tool_name = payload.get("tool_name")
            self.system_state["active_tool"] = tool_name
            self.system_state["orchestrator_status"] = f"Executing {tool_name}"
            if tool_name != "spawn_agent":
                key = ("Master", tool_name)
                if key not in self.system_state["tools_discovered"]:
                    self.system_state["tools_discovered"][key] = {
                        "status": "active",
                        "caller": "Master",
                        "tool_name": tool_name,
                        "call_count": 0,
                        "active_since": None
                    }
                t_entry = self.system_state["tools_discovered"][key]
                t_entry["status"] = "active"
                t_entry["call_count"] += 1
                t_entry["active_since"] = time.time()
            self.append_msg("System Tool Runner", f"Agent Robert calling tool: {tool_name}...", "system")
        elif event_type == "master_tool_end":
            active_t = self.system_state["active_tool"]
            if active_t and active_t != "spawn_agent":
                key = ("Master", active_t)
                if key in self.system_state["tools_discovered"]:
                    self.root.after(1000, lambda k=key: self._set_tool_idle(k))
            self.system_state["active_tool"] = None
            self.system_state["orchestrator_status"] = "Processing response..."
        elif event_type == "spawn_agent_start":
            role = payload.get("role", "Sub-Agent")
            task = payload.get("task", "")
            
            found = False
            for agent in self.system_state["spawned_agents"]:
                if agent["role"] == role:
                    agent["status"] = "Working..."
                    agent["active_since"] = time.time()
                    agent["active_tool"] = None
                    found = True
                    break
            if not found:
                self.system_state["spawned_agents"].append({
                    "role": role,
                    "status": "Working...",
                    "active_since": time.time(),
                    "active_tool": None
                })
            self.append_msg("Orchestrator", f"Agent Robert strictly delegated task to specialized Agent [{role}]: {task}", "orchestrator")
        elif event_type == "spawn_agent_end":
            role = payload.get("role")
            for agent in self.system_state["spawned_agents"]:
                if agent["role"] == role:
                    agent["status"] = "Idle"
                    agent["active_since"] = None
                    agent["active_tool"] = None
            self.append_msg("System", f"Agent [{role}] completed task and returned control to Agent Robert.", "system")
        elif event_type == "sub_agent_tool_start":
            role = payload.get("role")
            tool_name = payload.get("tool_name")
            for agent in self.system_state["spawned_agents"]:
                if agent["role"] == role:
                    agent["status"] = f"Running {tool_name}"
                    agent["active_tool"] = tool_name
            if tool_name != "spawn_agent":
                key = (role, tool_name)
                if key not in self.system_state["tools_discovered"]:
                    self.system_state["tools_discovered"][key] = {
                        "status": "active",
                        "caller": role,
                        "tool_name": tool_name,
                        "call_count": 0,
                        "active_since": None
                    }
                t_entry = self.system_state["tools_discovered"][key]
                t_entry["status"] = "active"
                t_entry["call_count"] += 1
                t_entry["active_since"] = time.time()
            self.append_msg("System Tool Runner", f"Agent [{role}] calling tool: {tool_name}...", "system")
        elif event_type == "sub_agent_tool_end":
            role = payload.get("role")
            for agent in self.system_state["spawned_agents"]:
                if agent["role"] == role:
                    active_t = agent["active_tool"]
                    key = (role, active_t)
                    if active_t and key in self.system_state["tools_discovered"]:
                        self.root.after(1000, lambda k=key: self._set_tool_idle(k))
                    agent["status"] = "Working..."
                    agent["active_tool"] = None
        elif event_type == "rag_notification":
            msg = payload.get("message", "")
            self.append_msg("RAG Manager", msg, "system")

        self.zoom_fit()

    def start_pan(self, event):
        self.canvas.scan_mark(int(self.canvas.canvasx(event.x)), int(self.canvas.canvasy(event.y)))

    def pan_canvas(self, event):
        self.canvas.scan_dragto(int(self.canvas.canvasx(event.x)), int(self.canvas.canvasy(event.y)), gain=1)

    def mouse_zoom(self, event):
        if event.num == 4 or event.delta > 0:
            self.zoom_in()
        elif event.num == 5 or event.delta < 0:
            self.zoom_out()

    def zoom_in(self):
        self.zoom_factor = min(3.0, self.zoom_factor + 0.1)
        self.update_visualizer()

    def zoom_out(self):
        self.zoom_factor = max(0.3, self.zoom_factor - 0.1)
        self.update_visualizer()

    def zoom_fit(self):
        view_w = self.canvas.winfo_width()
        view_h = self.canvas.winfo_height()
        if view_w <= 1: view_w = 750
        if view_h <= 1: view_h = 250
        
        num_agents = len(self.system_state.get("spawned_agents", []))
        nominal_content_width = max(500, num_agents * 220)
        
        tools_discovered = self.system_state.get("tools_discovered", {})
        if tools_discovered:
            tools_by_caller = {}
            for key, t_info in tools_discovered.items():
                caller = t_info["caller"]
                tools_by_caller.setdefault(caller, []).append(t_info)
            max_tools_under_one = max(len(t_list) for t_list in tools_by_caller.values()) if tools_by_caller else 0
            nominal_content_width = max(nominal_content_width, max_tools_under_one * 160)
            
        nominal_content_height = 380  
        scale_x = view_w / (nominal_content_width + 60)
        scale_y = view_h / (nominal_content_height + 40)
        
        self.zoom_factor = max(0.35, min(2.5, min(scale_x, scale_y)))
        self.update_visualizer()
        
        self.canvas.xview_moveto(0.0)
        self.canvas.yview_moveto(0.0)

    def update_visualizer(self):
        self.canvas.delete("all")
        
        v_width = int(1000 * self.zoom_factor)
        v_height = int(400 * self.zoom_factor)
        center_x = v_width // 2

        grid_step = int(50 * self.zoom_factor)
        if grid_step > 5:
            for grid_x in range(0, v_width, grid_step):
                self.canvas.create_line(grid_x, 0, grid_x, v_height, fill="#181818", width=1)
            for grid_y in range(0, v_height, grid_step):
                self.canvas.create_line(0, grid_y, v_width, grid_y, fill="#181818", width=1)

        orch_status = self.system_state.get("orchestrator_status", "Idle")
        orch_active_since = self.system_state.get("orchestrator_active_since")
        spawned = self.system_state.get("spawned_agents", [])
        tools_discovered = self.system_state.get("tools_discovered", {})

        bg_card_idle = "#212121"
        border_idle = "#3C3C3C"
        
        f_title_base = max(6, min(24, int(11 * self.zoom_factor)))
        f_subtitle_base = max(5, min(18, int(8 * self.zoom_factor)))
        f_timer_base = max(4, min(16, int(7 * self.zoom_factor)))
        
        f_title = ("Arial", f_title_base, "bold")
        f_subtitle = ("Arial", f_subtitle_base, "italic")
        f_timer = ("Arial", f_timer_base, "bold")
        
        is_orch_active = (orch_status != "Idle" and orch_status != "Ready")
        orch_bg = "#0D47A1" if is_orch_active else bg_card_idle
        orch_border = "#42A5F5" if is_orch_active else border_idle
        
        my = int(45 * self.zoom_factor)
        mw = int(100 * self.zoom_factor)
        mh = int(32 * self.zoom_factor) 
        
        self.canvas.create_rectangle(center_x - mw - 5, my - mh + 3, center_x + mw + 5, my + mh + 3, fill="#000000", outline="")
        self.canvas.create_rectangle(center_x - mw, my - mh, center_x + mw, my + mh, fill=orch_bg, outline=orch_border, width=max(1, int(2 * self.zoom_factor)))
        
        ring_r1 = int(8 * self.zoom_factor)
        ring_r2 = int(4 * self.zoom_factor)
        ring_x = center_x - int(80 * self.zoom_factor)
        
        ring_color = "#42A5F5" if is_orch_active else "#9E9E9E"
        if ring_r1 > 1:
            self.canvas.create_oval(ring_x - ring_r1, my - ring_r1, ring_x + ring_r1, my + ring_r1, fill="", outline=ring_color, width=max(1, int(2 * self.zoom_factor)))
            self.canvas.create_oval(ring_x - ring_r2, my - ring_r2, ring_x + ring_r2, my + ring_r2, fill=ring_color, outline="")

        self.canvas.create_text(
            center_x + int(5 * self.zoom_factor), my - int(12 * self.zoom_factor), 
            text="Agent Robert", fill="#FFFFFF", font=f_title, width=int(2 * mw * 0.95)
        )
        self.canvas.create_text(
            center_x + int(5 * self.zoom_factor), my + int(2 * self.zoom_factor), 
            text=f"State: {orch_status}", fill="#FFB74D" if is_orch_active else "#9E9E9E", font=f_subtitle, width=int(2 * mw * 0.95)
        )
        
        # Display Master Tokens
        master_tokens = self.system_state["token_usage"].get("master", 0)
        self.canvas.create_text(
            center_x + int(5 * self.zoom_factor), my + int(8 * self.zoom_factor), 
            text=f"Tokens: {master_tokens}", fill="#E0F7FA", font=f_timer, width=int(2 * mw * 0.95)
        )

        if is_orch_active and orch_active_since:
            elapsed_m = int((time.time() - orch_active_since) / 60)
            self.canvas.create_text(
                center_x + int(5 * self.zoom_factor), my + int(16 * self.zoom_factor), 
                text=f"Active: {elapsed_m}m", fill="#E0F7FA", font=f_timer, width=int(2 * mw * 0.95)
            )

        start_xa = center_x
        gap_a = int(180 * self.zoom_factor)
        agent_positions = {}
        
        ay = int(185 * self.zoom_factor)
        aw = int(85 * self.zoom_factor)
        ah = int(30 * self.zoom_factor) 
        
        if spawned:
            num_agents = len(spawned)
            gap_a = max(int(200 * self.zoom_factor), int((1000 - 100) * self.zoom_factor) // (num_agents + 1))
            start_xa = center_x - ((num_agents - 1) * gap_a) // 2
            
            for idx, agent in enumerate(spawned):
                ax = start_xa + idx * gap_a
                agent_positions[agent["role"]] = ax
                
                is_sub_active = (agent["status"] != "Idle")
                path_color = "#4CAF50" if is_sub_active else "#3C3C3C"
                path_width = max(1, int(2 * self.zoom_factor)) if is_sub_active else 1
                self.canvas.create_line(center_x, my + mh, ax, ay - ah, fill=path_color, width=path_width)
                
                abg = "#1B5E20" if is_sub_active else bg_card_idle
                aborder = "#66BB6A" if is_sub_active else border_idle
                
                self.canvas.create_rectangle(ax - aw - 5, ay - ah + 3, ax + aw + 5, ay + ah + 3, fill="#000000", outline="")
                self.canvas.create_rectangle(ax - aw, ay - ah, ax + aw, ay + ah, fill=abg, outline=aborder, width=max(1, int(2 * self.zoom_factor)))
                
                clean_role = agent["role"][:14] + ".." if len(agent["role"]) > 16 else agent["role"]
                self.canvas.create_text(
                    ax, ay - int(12 * self.zoom_factor), 
                    text=f"Agent - {clean_role}", fill="#90CAF9", font=f_title, width=int(2 * aw * 0.95)
                )
                self.canvas.create_text(
                    ax, ay + int(1 * self.zoom_factor), 
                    text=agent["status"], fill="#FFD54F" if is_sub_active else "#CFD8DC", font=f_subtitle, width=int(2 * aw * 0.95)
                )
                
                # Display Sub-Agent Tokens
                agent_role = agent["role"]
                agent_tokens = self.system_state["token_usage"]["agents"].get(agent_role, 0)
                self.canvas.create_text(
                    ax, ay + int(8 * self.zoom_factor), 
                    text=f"Tokens: {agent_tokens}", fill="#E8F5E9", font=f_timer, width=int(2 * aw * 0.95)
                )

                if is_sub_active and agent.get("active_since"):
                    elapsed_sub = int((time.time() - agent["active_since"]) / 60)
                    self.canvas.create_text(
                        ax, ay + int(15 * self.zoom_factor), 
                        text=f"Active: {elapsed_sub}m", fill="#E8F5E9", font=f_timer, width=int(2 * aw * 0.95)
                    )

        ty = int(320 * self.zoom_factor)
        tw = int(65 * self.zoom_factor)
        th = int(30 * self.zoom_factor) 
        
        if tools_discovered:
            active_callers = {"Master"} | {agent["role"] for agent in spawned}
            filtered_tools = {
                key: t_info for key, t_info in tools_discovered.items() 
                if t_info["caller"] in active_callers
            }
            
            tools_by_caller = {}
            for key, t_info in filtered_tools.items():
                caller = t_info["caller"]
                tools_by_caller.setdefault(caller, []).append(t_info)

            for caller, t_list in tools_by_caller.items():
                cx = center_x if caller == "Master" else agent_positions.get(caller, center_x)
                cy = my + mh if caller == "Master" else ay + ah 
                
                num_tools = len(t_list)
                gap_t = int(130 * self.zoom_factor) 
                start_xt = cx - ((num_tools - 1) * gap_t) // 2
                
                for t_idx, t_info in enumerate(t_list):
                    tx = start_xt + t_idx * gap_t
                    is_tool_active = (t_info["status"] == "active")
                    t_name = t_info["tool_name"]
                    
                    line_color = "#FF9800" if is_tool_active else "#2D2D2D"
                    line_width = max(1, int(3 * self.zoom_factor)) if is_tool_active else 1
                    line_dash = None if is_tool_active else (2, 2)
                    self.canvas.create_line(cx, cy, tx, ty - th, fill=line_color, width=line_width, dash=line_dash, arrow=tk.LAST)
                    
                    t_bg = "#E65100" if is_tool_active else "#1A1A1A"
                    t_border = "#FFB74D" if is_tool_active else "#424242"
                    t_fg = "#FFFFFF" if is_tool_active else "#757575"
                    
                    self.canvas.create_rectangle(tx - tw - 5, ty - th + 3, tx + tw + 5, ty + th + 3, fill="#000000", outline="")
                    self.canvas.create_rectangle(tx - tw, ty - th, tx + tw, ty + th, fill=t_bg, outline=t_border, width=max(1, int(1.5 * self.zoom_factor) if is_tool_active else 1))
                    
                    clean_tool_name = t_name[:14] + ".." if len(t_name) > 16 else t_name
                    self.canvas.create_text(
                        tx, ty - int(12 * self.zoom_factor), 
                        text=clean_tool_name, fill=t_fg, font=f_title, width=int(2 * tw * 0.95)
                    )
                    
                    call_count = t_info.get("call_count", 1)
                    self.canvas.create_text(
                        tx, ty + int(1 * self.zoom_factor), 
                        text=f"Calls: {call_count}", fill="#FFE082" if is_tool_active else "#616161", font=f_subtitle, width=int(2 * tw * 0.95)
                    )
                    
                    if is_tool_active and t_info.get("active_since"):
                        elapsed_t = int((time.time() - t_info["active_since"]) / 60)
                        self.canvas.create_text(
                            tx, ty + int(15 * self.zoom_factor), 
                            text=f"Active: {elapsed_t}m", fill="#E8F5E9", font=f_timer, width=int(2 * tw * 0.95)
                        )

    def append_msg(self, sender, text, tag):
        """Appends a message to the chat window using full markdown library support with precise color styling."""
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        
        styles = {
            "user": "color: #64B5F6; font-family: Arial, sans-serif; font-size: 13px; font-weight: bold;",
            "ai": "color: #81C784; font-family: Arial, sans-serif; font-size: 13px; font-weight: bold;",
            "system": "color: #9E9E9E; font-family: Arial, sans-serif; font-size: 11px; font-style: italic;",
            "orchestrator": "color: #FFB74D; font-family: Arial, sans-serif; font-size: 12px; font-weight: bold;"
        }
        style = styles.get(tag, "color: #E0E0E0; font-family: Arial, sans-serif; font-size: 13px;")
        
        # Map specific colors to apply directly to markdown child elements
        color_map = {
            "user": "#64B5F6",
            "ai": "#81C784",
            "system": "#9E9E9E",
            "orchestrator": "#FFB74D"
        }
        msg_color = color_map.get(tag, "#E0E0E0")
        
        # Pre-process text to ensure markdown bullet lists and numbered lists have a preceding blank line
        import re
        lines = text.split('\n')
        processed_lines = []
        for i, line in enumerate(lines):
            is_list_item = bool(re.match(r'^\s*[\*\-\+]\s+', line) or re.match(r'^\s*\d+\.\s+', line))
            if is_list_item and i > 0:
                prev_line = lines[i-1].strip()
                prev_is_list = bool(re.match(r'^\s*[\*\-\+]\s+', prev_line) or re.match(r'^\s*\d+\.\s+', prev_line))
                if prev_line != "" and not prev_is_list:
                    processed_lines.append("")
            processed_lines.append(line)
        preprocessed_text = '\n'.join(processed_lines)
        
        # Render using the full markdown library
        md_html = markdown.markdown(
            preprocessed_text,
            extensions=['extra', 'sane_lists', 'nl2br']
        )
        
        # Apply clean styling rules for HTML output elements
        md_html = md_html.replace('<ul>', '<ul style="margin-top: 4px; margin-bottom: 4px; padding-left: 20px;">')
        md_html = md_html.replace('<ol>', '<ol style="margin-top: 4px; margin-bottom: 4px; padding-left: 20px;">')
        
        # Dynamically inject the message color here
        md_html = md_html.replace('<li>', f'<li style="margin-bottom: 3px; color: {msg_color};">')
        
        md_html = md_html.replace('<h1>', f'<h1 style="color: {msg_color}; font-size: 1.4em; margin-top: 12px; margin-bottom: 6px;">')
        md_html = md_html.replace('<h2>', f'<h2 style="color: {msg_color}; font-size: 1.25em; margin-top: 10px; margin-bottom: 4px;">')
        md_html = md_html.replace('<h3>', f'<h3 style="color: {msg_color}; font-size: 1.15em; margin-top: 8px; margin-bottom: 4px;">')
        md_html = md_html.replace('<h4>', f'<h4 style="color: {msg_color}; font-size: 1.05em; margin-top: 6px; margin-bottom: 4px;">')
        
        md_html = md_html.replace('<pre>', '<pre style="background-color: #212121; padding: 6px; margin: 6px 0; border: 1px solid #333; border-radius: 4px;">')
        md_html = md_html.replace('<code>', '<code style="font-family: monospace; background-color: #2D2D2D; padding: 2px; color: #E0E0E0;">')
        
        # Dynamically inject the message color and reset font-weight for the body content here
        md_html = md_html.replace('<p>', f'<div style="margin-bottom: 8px; color: {msg_color}; font-weight: normal; font-style: normal;">').replace('</p>', '</div>')

        message_html = (
            f'<div style="{style}; margin-bottom: 12px; line-height: 1.4;">'
            f'<span style="opacity: 0.8; font-size: 0.9em;">{timestamp}</span> <b>{sender}:</b><br>'
            f'<div style="margin-top: 4px; margin-bottom: 8px;">{md_html}</div>'
            f'</div>'
        )
        
        self.chat_history_html += message_html
        
        full_html = (
            f'<body style="background-color: #1E1E1E; color: #E0E0E0; font-family: Arial, sans-serif; padding: 15px; margin: 0;">'
            f'{self.chat_history_html}'
            f'</body>'
        )
        self.chat_display.set_html(full_html)
        self.chat_display.config(background="#1E1E1E")
        self.chat_display.update_idletasks()
        self.chat_display.yview_moveto(1.0)

    def import_file(self):
        file_path = filedialog.askopenfilename(filetypes=[
            ("All Compatible Files", "*.docx *.doc *.txt *.md *.pdf *.xls *.xlsx *.ppt *.pptx *.vhdl *.v *.vs *.vh *.py *.cpp *.h *.hpp *.cc *.cxx *.csv *.png *.jpg *.jpeg *.gif *.bmp *.pl *.tcl *.sh"),
            ("C++ Source Files", "*.cpp *.h *.hpp *.cc *.cxx"),
            ("Spreadsheets & CSV", "*.xls *.xlsx *.csv"),
            ("Presentations", "*.ppt *.pptx"),
            ("HDL Files", "*.vhdl *.v *.vs *.vh"), ("Python Source", "*.py"),
            ("Scripting Files", "*.pl *.tcl *.sh"),
            ("Image Files", "*.png *.jpg *.jpeg *.gif *.bmp"),
            ("Text/Markdown Files", "*.txt *.md"), ("PDF Document", "*.pdf")
        ])
        if not file_path or not self.engine: return
        self.process_and_attach_file(file_path)

    def process_and_attach_file(self, file_path):
        try:
            filename = self.engine.attach_file(file_path)
            self.file_status.config(text="Attached: " + filename, fg="#81C784")
            self.append_msg("System", "Document loaded into context background: " + filename, "system")
            return True
        except Exception as e:
            messagebox.showerror("Read Failure", "Error: " + str(e))
            self.append_msg("System Error", f"Failed to attach document: {str(e)}", "system")
            return False

    def export_chat(self):
        if not self.engine or not self.engine.chat_history: return
        file_path = filedialog.asksaveasfilename(filetypes=[
            ("Text File", "*.txt"), ("Word Document", "*.docx"), ("PDF Document", "*.pdf")
        ], defaultextension=".txt")
        if not file_path: return
        try:
            file_str = self.engine._normalize_path(file_path)
            ext = os.path.splitext(file_str)[1].lower()
            content = self.engine.generate_chat_log()
            
            if ext == ".docx":
                doc = Document()
                style = doc.styles['Normal']
                style.font.name = 'Calibri'
                style.font.size = Pt(11)
                style.font.color.rgb = RGBColor(51, 51, 51)
                
                title_p = doc.add_paragraph()
                title_p.paragraph_format.space_before = Pt(0)
                title_p.paragraph_format.space_after = Pt(12)
                run_title = title_p.add_run("Conversational History Log")
                run_title.bold = True
                run_title.font.size = Pt(20)
                run_title.font.color.rgb = RGBColor(13, 71, 161)
                
                for msg in self.engine.chat_history:
                    if isinstance(msg, (HumanMessage, AIMessage)):
                        is_user = isinstance(msg, HumanMessage)
                        prefix = "YOU: " if is_user else "AI: "
                        p = doc.add_paragraph()
                        p.paragraph_format.space_before = Pt(4)
                        p.paragraph_format.space_after = Pt(8)
                        p.paragraph_format.line_spacing = 1.15
                        
                        run_prefix = p.add_run(prefix)
                        run_prefix.bold = True
                        if is_user:
                            run_prefix.font.color.rgb = RGBColor(21, 101, 192)
                        else:
                            run_prefix.font.color.rgb = RGBColor(46, 125, 50)
                            
                        run_content = p.add_run(msg.content)
                        run_content.font.color.rgb = RGBColor(51, 51, 51)
                doc.save(file_str)
            elif ext == ".pdf":
                temp = file_str + ".tmp.txt"
                with open(temp, "w", encoding="utf-8") as f: f.write(content)
                subprocess.run(["textutil", "-convert", "pdf", temp, "-output", file_str], check=True)
                if os.path.exists(temp): os.remove(temp)
            else:
                with open(file_str, "w", encoding="utf-8") as f: f.write(content)
            messagebox.showinfo("Success", "Chat log saved successfully.")
        except Exception as e:
            messagebox.showerror("Export Aborted", "Error: " + str(e))

    def send_message(self):
        if not self.engine: return
        
        if self.is_thinking:
            self.append_msg("System", "🔴 Interruption requested. Aborting active pipeline execution...", "system")
            self.engine.is_cancelled = True
            self.reenable()
            return

        user_text = self.entry_box.get().strip()
        if not user_text: return
        
        clean_path = self.engine._normalize_path(user_text)
        supported_extensions = {
            ".docx", ".doc", ".pdf", ".txt", ".md", ".csv",
            ".cpp", ".h", ".hpp", ".cc", ".cxx", ".py",
            ".vhdl", ".v", ".vs", ".vh", ".xls", ".xlsx",
            ".ppt", ".pptx", ".png", ".jpg", ".jpeg", ".gif", ".bmp",
            ".pl", ".tcl", ".sh"
        }
        _, ext = os.path.splitext(clean_path.lower())
        
        if ext in supported_extensions and os.path.exists(clean_path):
            self.entry_box.delete(0, tk.END)
            self.append_msg("You", f"Loading local file path: {clean_path}", "user")
            self.process_and_attach_file(clean_path)
            return

        self.is_thinking = True
        self.engine.is_cancelled = False 
        self.entry_box.delete(0, tk.END)
        self.entry_box.config(state='disabled')
        
        self.send_button.config(text="🔴 Stop", style="Thinking.TButton")
        self.append_msg("You", user_text, "user")
        
        # Queue the task
        self.task_queue.put((self._run_engine_task, (user_text,), {}))

    def _run_engine_task(self, user_text, email_recipient=None, email_subject=None, telegram_chat_id=None):
        """Threaded wrapper to safely run the main orchestrator engine. 
        If email_recipient or telegram_chat_id is provided, the response is sent back."""
        try:
            # Capture current files in session workspace before processing
            files_before = set(os.listdir(self.session_workspace)) if os.path.exists(self.session_workspace) else set()
            
            response = self.engine.run_orchestrator(user_text)
            
            # Handle UI response
            self.root.after(0, self.append_msg, "Agent Robert", response, "ai")
            
            # Email Response Logic
            if email_recipient:
                # Capture files created during this process
                files_after = set(os.listdir(self.session_workspace)) if os.path.exists(self.session_workspace) else set()
                new_files = list(files_after - files_before)
                
                # Filter out system logs if necessary, but usually we send generated files
                attachments = [os.path.join(self.session_workspace, f) for f in new_files]
                
                reply_subject = f"Re: {email_subject}" if email_subject else "Agent Robert Response"
                
                # Send the response via email
                draft_or_send_email(
                    to_address=email_recipient,
                    subject=reply_subject,
                    body=response,
                    attachments=attachments
                )
            
            # Telegram Response Logic
            if telegram_chat_id:
                telegram_send_or_draft(
                    chat_id=telegram_chat_id,
                    message=response
                )
                
        except Exception as e:
            self.root.after(0, self.append_msg, "System Error", f"Agent execution failed: {str(e)}", "system")
        finally:
            self.root.after(0, self.reenable)

    def reenable(self):
        """Re-enables UI elements safely from the main Tkinter thread."""
        self.is_thinking = False
        self.entry_box.config(state='normal')
        self.send_button.config(text="Send", style="Send.TButton")
        self.entry_box.focus()
        if self.system_state["orchestrator_status"] not in ["Idle", "Ready"]:
            self.system_state["orchestrator_status"] = "Ready"
        self.zoom_fit()

if __name__ == "__main__":
    root = tk.Tk()
    app = OllamaChatApp(root)
    root.mainloop()
