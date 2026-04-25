import queue
import threading
import time
import tkinter as tk
import webbrowser
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk

from crawl_company_news import (
    DEFAULT_MAX_RESULTS as DEFAULT_NEWS_MAX_RESULTS,
    NewsCrawlerError,
    crawl_company_news,
    default_output_path as default_news_output_path,
    parse_date as parse_news_date,
    write_json as write_news_json,
)
from crawl_catch_recruits import (
    DEFAULT_MAX_RESULTS,
    CatchRecruitError,
    crawl_catch_recruits,
    default_output_path as default_catch_output_path,
    parse_date as parse_catch_date,
    write_json as write_catch_json,
)
from download_business_reports import (
    DEFAULT_OUTPUT_DIR,
    ENV_PATH,
    DartError,
    download_business_reports,
    download_naver_research_reports,
    get_configured_api_key,
    parse_date_arg,
    search_companies,
)


APP_TITLE = "OpenDART, Catch, and News Reader"
FONT_FAMILY = "Malgun Gothic"
MONO_FONT_FAMILY = "Malgun Gothic"


class DownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("860x680")
        self.minsize(780, 600)

        self.message_queue = queue.Queue()
        self.worker = None
        self.batch_worker = None
        self.catch_worker = None
        self.catch_links = {}
        self.lookup_tokens = {"reports": 0, "catch": 0, "news": 0, "batch": 0}
        self.lookup_after_ids = {"reports": None, "catch": None, "news": None, "batch": None}
        self.lookup_candidates = {"reports": [], "catch": [], "news": [], "batch": []}
        self.selected_corps = {"reports": None, "catch": None, "news": None, "batch": None}

        self.company_var = tk.StringVar()
        self.report_source_var = tk.StringVar(value="OpenDART business reports")
        self.api_key_var = tk.StringVar(value=get_configured_api_key())
        self.output_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.years_var = tk.IntVar(value=5)
        self.naver_count_var = tk.IntVar(value=10)
        self.naver_start_var = tk.StringVar(value=(date.today() - timedelta(days=365)).isoformat())
        self.naver_end_var = tk.StringVar(value=date.today().isoformat())
        self.status_var = tk.StringVar(value="Ready")

        self.catch_keyword_var = tk.StringVar()
        self.catch_output_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.catch_start_var = tk.StringVar(value=(date.today() - timedelta(days=30)).isoformat())
        self.catch_end_var = tk.StringVar(value=date.today().isoformat())
        self.catch_today_only_var = tk.BooleanVar(value=False)
        self.catch_status_var = tk.StringVar(value="Ready")

        self.news_company_var = tk.StringVar()
        self.news_start_var = tk.StringVar(value=(date.today() - timedelta(days=30)).isoformat())
        self.news_end_var = tk.StringVar(value=date.today().isoformat())
        self.news_source_var = tk.StringVar(value="all")
        self.news_output_var = tk.StringVar()
        self.news_max_results_var = tk.IntVar(value=DEFAULT_NEWS_MAX_RESULTS)
        self.news_status_var = tk.StringVar(value="Ready")

        self.batch_company_var = tk.StringVar()
        self.batch_dart_var = tk.BooleanVar(value=True)
        self.batch_naver_var = tk.BooleanVar(value=True)
        self.batch_catch_var = tk.BooleanVar(value=False)
        self.batch_news_var = tk.BooleanVar(value=True)
        self.batch_status_var = tk.StringVar(value="Ready")

        self.configure(bg="#f6f7f9")
        self._configure_style()
        self._build_layout()
        self._sync_report_source_fields()
        self.after(120, self._drain_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_style(self):
        self.ui_font = font.Font(family=FONT_FAMILY, size=10)
        self.ui_font_bold = font.Font(family=FONT_FAMILY, size=10, weight="bold")
        self.field_font = font.Font(family=FONT_FAMILY, size=9, weight="bold")
        self.title_font = font.Font(family=FONT_FAMILY, size=18, weight="bold")
        self.subtitle_font = font.Font(family=FONT_FAMILY, size=10)
        self.input_font = font.Font(family=FONT_FAMILY, size=11)
        self.log_font = font.Font(family=MONO_FONT_FAMILY, size=10)
        self.option_add("*Font", self.ui_font)
        self.option_add("*Entry.Font", self.input_font)
        self.option_add("*Text.Font", self.log_font)
        self.option_add("*Listbox.Font", self.ui_font)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f6f7f9")
        style.configure("Header.TFrame", background="#17202a")
        style.configure("Title.TLabel", background="#17202a", foreground="#ffffff", font=self.title_font)
        style.configure("Subtitle.TLabel", background="#17202a", foreground="#b9c2cf", font=self.subtitle_font)
        style.configure("TLabel", background="#f6f7f9", foreground="#222831", font=self.ui_font)
        style.configure("Field.TLabel", background="#f6f7f9", foreground="#46515f", font=self.field_font)
        style.configure("TButton", font=self.ui_font, padding=(12, 8))
        style.configure("Accent.TButton", background="#0f766e", foreground="#ffffff", font=self.ui_font_bold)
        style.configure("Stop.TButton", background="#b91c1c", foreground="#ffffff", font=self.ui_font_bold)
        style.configure("TEntry", font=self.input_font)
        style.configure("TCombobox", font=self.ui_font)
        style.configure("TSpinbox", font=self.ui_font)
        style.configure("Treeview", font=self.ui_font, rowheight=25)
        style.configure("Treeview.Heading", font=self.field_font)
        style.map("Accent.TButton", background=[("active", "#115e59"), ("disabled", "#94a3b8")])
        style.map("Stop.TButton", background=[("active", "#991b1b"), ("disabled", "#94a3b8")])
        style.configure("Horizontal.TProgressbar", background="#0f766e", troughcolor="#d8dee8")
        style.configure("TNotebook", background="#f6f7f9", borderwidth=0)
        style.configure("TNotebook.Tab", font=self.ui_font, padding=(14, 8))

    def _build_layout(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(24, 22))
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Download business report PDFs, read Catch postings, and crawl company news metadata.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(6, 0))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=18, pady=18)

        batch_tab = ttk.Frame(notebook, padding=(6, 6))
        reports_tab = ttk.Frame(notebook, padding=(6, 6))
        catch_tab = ttk.Frame(notebook, padding=(6, 6))
        news_tab = ttk.Frame(notebook, padding=(6, 6))
        notebook.add(batch_tab, text="Batch Run")
        notebook.add(reports_tab, text="Business Reports")
        notebook.add(catch_tab, text="Catch Recruits")
        notebook.add(news_tab, text="Company News")

        self._build_batch_tab(batch_tab)
        self._build_reports_tab(reports_tab)
        self._build_catch_tab(catch_tab)
        self._build_news_tab(news_tab)

    def _build_batch_tab(self, parent):
        form = ttk.Frame(parent)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Company / stock code", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        company = ttk.Entry(form, textvariable=self.batch_company_var, font=self.input_font)
        company.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        company.bind("<KeyRelease>", lambda event: self._on_lookup_key_release("batch", event))
        company.bind("<Return>", lambda event: self._select_active_company("batch", event))
        company.bind("<Down>", lambda event: self._focus_company_suggestions("batch", event))

        self.batch_suggestions = self._create_company_suggestion_list(form, "batch")
        self.batch_suggestions.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        self.batch_suggestions.grid_remove()

        ttk.Label(form, text="Tasks", style="Field.TLabel").grid(row=3, column=0, sticky="w", pady=(0, 6))
        task_frame = ttk.Frame(form)
        task_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        ttk.Checkbutton(task_frame, text="OpenDART business reports", variable=self.batch_dart_var).pack(side="left")
        ttk.Checkbutton(task_frame, text="Naver Finance research", variable=self.batch_naver_var).pack(side="left", padx=(14, 0))
        ttk.Checkbutton(task_frame, text="Catch Recruits", variable=self.batch_catch_var).pack(side="left", padx=(14, 0))
        ttk.Checkbutton(task_frame, text="Company News", variable=self.batch_news_var).pack(side="left", padx=(14, 0))

        ttk.Label(form, text="Settings source", style="Field.TLabel").grid(row=5, column=0, sticky="w", pady=(0, 6))
        ttk.Label(
            form,
            text="Batch uses the current settings from Business Reports, Catch Recruits, and Company News tabs.",
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 18))

        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(4, 14))
        self.batch_run_button = ttk.Button(
            actions,
            text="Run Selected Tasks",
            style="Accent.TButton",
            command=self._start_batch_run,
        )
        self.batch_run_button.pack(side="left")
        ttk.Label(actions, textvariable=self.batch_status_var).pack(side="left", padx=(16, 0))

        self.batch_progress = ttk.Progressbar(parent, mode="indeterminate")
        self.batch_progress.pack(fill="x", pady=(0, 14))

        log_frame = ttk.Frame(parent)
        log_frame.pack(fill="both", expand=True)
        self.batch_log = tk.Text(
            log_frame,
            height=18,
            wrap="word",
            relief="flat",
            bg="#ffffff",
            fg="#1f2933",
            font=self.log_font,
            padx=12,
            pady=10,
        )
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.batch_log.yview)
        self.batch_log.configure(yscrollcommand=scrollbar.set)
        self.batch_log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _build_reports_tab(self, parent):
        form = ttk.Frame(parent)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Source", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.report_source_combo = ttk.Combobox(
            form,
            textvariable=self.report_source_var,
            values=("OpenDART business reports", "Naver Finance research"),
            state="readonly",
            font=self.ui_font,
        )
        self.report_source_combo.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        self.report_source_combo.bind("<<ComboboxSelected>>", lambda _event: self._sync_report_source_fields())

        ttk.Label(form, text="Company / stock code", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 6))
        company = ttk.Entry(form, textvariable=self.company_var, font=self.input_font)
        company.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        company.bind("<KeyRelease>", self._on_company_key_release)
        company.bind("<Return>", lambda event: self._select_active_company("reports", event))
        company.bind("<Down>", lambda event: self._focus_company_suggestions("reports", event))
        company.focus()

        self.company_suggestions = tk.Listbox(
            form,
            height=6,
            activestyle="none",
            borderwidth=1,
            highlightthickness=0,
            relief="solid",
            bg="#ffffff",
            fg="#202124",
            selectbackground="#edf2f7",
            selectforeground="#111827",
            font=self.ui_font,
        )
        self.company_suggestions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        self.company_suggestions.grid_remove()
        self.company_suggestions.bind("<ButtonRelease-1>", lambda event: self._select_active_company("reports", event))
        self.company_suggestions.bind("<Return>", lambda event: self._select_active_company("reports", event))
        self.company_suggestions.bind("<Escape>", lambda _event: self._hide_company_suggestions())

        self.api_key_label = ttk.Label(form, text=".env API key", style="Field.TLabel")
        self.api_key_label.grid(row=5, column=0, sticky="w", pady=(0, 6))
        self.api_key_entry = ttk.Entry(form, textvariable=self.api_key_var, show="*", font=self.ui_font)
        self.api_key_entry.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 14), padx=(0, 8))
        self.save_env_button = ttk.Button(form, text="Save .env", command=self._save_env)
        self.save_env_button.grid(row=6, column=2, sticky="ew", pady=(0, 14))

        ttk.Label(form, text="Output folder", style="Field.TLabel").grid(row=7, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(form, textvariable=self.output_var, font=self.ui_font).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(0, 14), padx=(0, 8))
        ttk.Button(form, text="Browse", command=self._browse_output).grid(row=8, column=2, sticky="ew", pady=(0, 14))

        self.naver_start_label = ttk.Label(form, text="Naver start date", style="Field.TLabel")
        self.naver_start_label.grid(row=9, column=0, sticky="w", pady=(0, 6))
        self.naver_end_label = ttk.Label(form, text="Naver end date", style="Field.TLabel")
        self.naver_end_label.grid(row=9, column=1, sticky="w", pady=(0, 6), padx=(8, 0))
        self.naver_start_entry = ttk.Entry(form, textvariable=self.naver_start_var, font=self.ui_font, width=16)
        self.naver_start_entry.grid(row=10, column=0, sticky="ew", pady=(0, 14), padx=(0, 8))
        self.naver_end_entry = ttk.Entry(form, textvariable=self.naver_end_var, font=self.ui_font, width=16)
        self.naver_end_entry.grid(row=10, column=1, sticky="ew", pady=(0, 14), padx=(8, 8))

        self.report_count_label = ttk.Label(form, text="Reports", style="Field.TLabel")
        self.report_count_label.grid(row=11, column=0, sticky="w", pady=(0, 6))
        self.report_count_spinbox = ttk.Spinbox(form, from_=1, to=10, textvariable=self.years_var, width=8)
        self.report_count_spinbox.grid(row=12, column=0, sticky="w", pady=(0, 18))

        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(4, 14))
        self.download_button = ttk.Button(actions, text="Download PDFs", style="Accent.TButton", command=self._start_download)
        self.download_button.pack(side="left")
        ttk.Label(actions, textvariable=self.status_var).pack(side="left", padx=(16, 0))

        self.progress = ttk.Progressbar(parent, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 14))

        log_frame = ttk.Frame(parent)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=12, wrap="word", relief="flat", bg="#ffffff", fg="#1f2933", font=self.log_font, padx=12, pady=10)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _build_catch_tab(self, parent):
        form = ttk.Frame(parent)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Company / stock code", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        keyword = ttk.Entry(form, textvariable=self.catch_keyword_var, font=self.input_font)
        keyword.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        keyword.bind("<KeyRelease>", lambda event: self._on_lookup_key_release("catch", event))
        keyword.bind("<Return>", lambda event: self._select_active_company("catch", event))
        keyword.bind("<Down>", lambda event: self._focus_company_suggestions("catch", event))

        self.catch_suggestions = self._create_company_suggestion_list(form, "catch")
        self.catch_suggestions.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        self.catch_suggestions.grid_remove()

        ttk.Label(form, text="Output folder", style="Field.TLabel").grid(row=3, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(form, textvariable=self.catch_output_var, font=self.ui_font).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 14), padx=(0, 8))
        ttk.Button(form, text="Browse", command=self._browse_catch_output).grid(row=4, column=2, sticky="ew", pady=(0, 14))

        ttk.Label(form, text="Start date", style="Field.TLabel").grid(row=5, column=0, sticky="w", pady=(0, 6))
        ttk.Label(form, text="End date", style="Field.TLabel").grid(row=5, column=1, sticky="w", pady=(0, 6), padx=(8, 0))
        ttk.Entry(form, textvariable=self.catch_start_var, font=self.ui_font, width=16).grid(row=6, column=0, sticky="ew", pady=(0, 14), padx=(0, 8))
        ttk.Entry(form, textvariable=self.catch_end_var, font=self.ui_font, width=16).grid(row=6, column=1, sticky="ew", pady=(0, 14), padx=(8, 8))
        date_actions = ttk.Frame(form)
        date_actions.grid(row=6, column=2, sticky="ew", pady=(0, 14))
        ttk.Button(date_actions, text="Today", command=self._set_catch_dates_today).pack(side="left")
        ttk.Checkbutton(
            date_actions,
            text="Today only",
            variable=self.catch_today_only_var,
            command=self._sync_catch_today_only,
        ).pack(side="left", padx=(8, 0))

        ttk.Label(form, text=f"Max results: {DEFAULT_MAX_RESULTS}", style="Field.TLabel").grid(row=7, column=0, sticky="w", pady=(0, 18))

        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(4, 14))
        self.catch_read_button = ttk.Button(actions, text="Read Once", style="Accent.TButton", command=self._start_catch_once)
        self.catch_read_button.pack(side="left")
        ttk.Label(actions, textvariable=self.catch_status_var).pack(side="left", padx=(16, 0))

        self.catch_progress = ttk.Progressbar(parent, mode="indeterminate")
        self.catch_progress.pack(fill="x", pady=(0, 14))

        columns = ("company", "title", "start_date", "deadline", "career", "location")
        self.catch_table = ttk.Treeview(parent, columns=columns, show="headings", height=9)
        headings = {
            "company": "Company",
            "title": "Title",
            "start_date": "Opened",
            "deadline": "Deadline",
            "career": "Career",
            "location": "Location",
        }
        widths = {"company": 130, "title": 290, "start_date": 140, "deadline": 140, "career": 90, "location": 80}
        for column in columns:
            self.catch_table.heading(column, text=headings[column])
            self.catch_table.column(column, width=widths[column], anchor="w")
        self.catch_table.bind("<Double-1>", self._open_selected_catch_recruit)
        self.catch_table.pack(fill="both", expand=True, pady=(0, 14))

        log_frame = ttk.Frame(parent)
        log_frame.pack(fill="both", expand=True)
        self.catch_log = tk.Text(log_frame, height=8, wrap="word", relief="flat", bg="#ffffff", fg="#1f2933", font=self.log_font, padx=12, pady=10)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.catch_log.yview)
        self.catch_log.configure(yscrollcommand=scrollbar.set)
        self.catch_log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _build_news_tab(self, parent):
        form = ttk.Frame(parent)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Company", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        company = ttk.Entry(form, textvariable=self.news_company_var, font=self.input_font)
        company.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        company.bind("<KeyRelease>", lambda event: self._on_lookup_key_release("news", event))
        company.bind("<Return>", lambda event: self._select_active_company("news", event))
        company.bind("<Down>", lambda event: self._focus_company_suggestions("news", event))

        self.news_suggestions = self._create_company_suggestion_list(form, "news")
        self.news_suggestions.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        self.news_suggestions.grid_remove()

        ttk.Label(form, text="Start date", style="Field.TLabel").grid(row=3, column=0, sticky="w", pady=(0, 6))
        ttk.Label(form, text="End date", style="Field.TLabel").grid(row=3, column=1, sticky="w", pady=(0, 6), padx=(8, 0))
        ttk.Label(form, text="Source", style="Field.TLabel").grid(row=3, column=2, sticky="w", pady=(0, 6), padx=(8, 0))
        ttk.Entry(form, textvariable=self.news_start_var, font=self.ui_font, width=16).grid(row=4, column=0, sticky="ew", pady=(0, 14), padx=(0, 8))
        ttk.Entry(form, textvariable=self.news_end_var, font=self.ui_font, width=16).grid(row=4, column=1, sticky="ew", pady=(0, 14), padx=(8, 8))
        ttk.Combobox(
            form,
            textvariable=self.news_source_var,
            values=("all", "naver", "google"),
            state="readonly",
            font=self.ui_font,
            width=12,
        ).grid(row=4, column=2, sticky="ew", pady=(0, 14))

        ttk.Label(form, text="Max results per source", style="Field.TLabel").grid(row=5, column=0, sticky="w", pady=(0, 6))
        ttk.Label(form, text="JSON output file (optional)", style="Field.TLabel").grid(row=5, column=1, columnspan=2, sticky="w", pady=(0, 6), padx=(8, 0))
        ttk.Spinbox(form, from_=1, to=200, textvariable=self.news_max_results_var, width=10).grid(row=6, column=0, sticky="w", pady=(0, 14))
        ttk.Entry(form, textvariable=self.news_output_var, font=self.ui_font).grid(row=6, column=1, sticky="ew", pady=(0, 14), padx=(8, 8))
        ttk.Button(form, text="Browse", command=self._browse_news_output).grid(row=6, column=2, sticky="ew", pady=(0, 14))

        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(4, 14))
        self.news_button = ttk.Button(actions, text="Crawl News JSON", style="Accent.TButton", command=self._start_news_crawl)
        self.news_button.pack(side="left")
        ttk.Label(actions, textvariable=self.news_status_var).pack(side="left", padx=(16, 0))

        self.news_progress = ttk.Progressbar(parent, mode="indeterminate")
        self.news_progress.pack(fill="x", pady=(0, 14))

        columns = ("source", "publisher", "published_at", "title")
        self.news_table = ttk.Treeview(parent, columns=columns, show="headings", height=10)
        headings = {"source": "Source", "publisher": "Publisher", "published_at": "Published", "title": "Title"}
        widths = {"source": 80, "publisher": 160, "published_at": 180, "title": 430}
        for column in columns:
            self.news_table.heading(column, text=headings[column])
            self.news_table.column(column, width=widths[column], anchor="w")
        self.news_table.pack(fill="both", expand=True, pady=(0, 14))

        log_frame = ttk.Frame(parent)
        log_frame.pack(fill="both", expand=True)
        self.news_log = tk.Text(log_frame, height=8, wrap="word", relief="flat", bg="#ffffff", fg="#1f2933", font=self.log_font, padx=12, pady=10)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.news_log.yview)
        self.news_log.configure(yscrollcommand=scrollbar.set)
        self.news_log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _save_env(self):
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning(APP_TITLE, "Enter an OpenDART API key first.")
            return
        ENV_PATH.write_text(f"OPENDART_API_KEY={key}\n", encoding="utf-8")
        self._log(f"Saved API key to {ENV_PATH}")

    def _browse_output(self):
        selected = filedialog.askdirectory(initialdir=self.output_var.get() or str(DEFAULT_OUTPUT_DIR))
        if selected:
            self.output_var.set(selected)

    def _browse_catch_output(self):
        selected = filedialog.askdirectory(initialdir=self.catch_output_var.get() or str(DEFAULT_OUTPUT_DIR))
        if selected:
            self.catch_output_var.set(selected)

    def _browse_news_output(self):
        selected = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
            initialdir=str(DEFAULT_OUTPUT_DIR),
            initialfile="news_results.json",
        )
        if selected:
            self.news_output_var.set(selected)

    def _set_catch_dates_today(self):
        today = date.today().isoformat()
        self.catch_start_var.set(today)
        self.catch_end_var.set(today)

    def _sync_catch_today_only(self):
        if self.catch_today_only_var.get():
            self._set_catch_dates_today()

    def _create_company_suggestion_list(self, parent, kind):
        listbox = tk.Listbox(
            parent,
            height=6,
            activestyle="none",
            borderwidth=1,
            highlightthickness=0,
            relief="solid",
            bg="#ffffff",
            fg="#202124",
            selectbackground="#edf2f7",
            selectforeground="#111827",
            font=self.ui_font,
        )
        listbox.bind("<ButtonRelease-1>", lambda event: self._select_active_company(kind, event))
        listbox.bind("<Return>", lambda event: self._select_active_company(kind, event))
        listbox.bind("<Escape>", lambda _event: self._hide_company_suggestions(kind))
        return listbox

    def _lookup_var(self, kind):
        return {
            "batch": self.batch_company_var,
            "reports": self.company_var,
            "catch": self.catch_keyword_var,
            "news": self.news_company_var,
        }[kind]

    def _lookup_listbox(self, kind):
        return {
            "batch": self.batch_suggestions,
            "reports": self.company_suggestions,
            "catch": self.catch_suggestions,
            "news": self.news_suggestions,
        }[kind]

    def _lookup_status_var(self, kind):
        return {
            "batch": self.batch_status_var,
            "reports": self.status_var,
            "catch": self.catch_status_var,
            "news": self.news_status_var,
        }[kind]

    def _lookup_log(self, kind, message):
        if kind == "batch":
            self._batch_log(message)
        elif kind == "reports":
            self._log(message)
        elif kind == "catch":
            self._catch_log(message)
        else:
            self._news_log(message)

    def _on_company_key_release(self, event):
        return self._on_lookup_key_release("reports", event)

    def _on_lookup_key_release(self, kind, event):
        if event.keysym in {"Up", "Down", "Return", "Escape"}:
            return
        self.selected_corps[kind] = None
        if self.lookup_after_ids[kind]:
            self.after_cancel(self.lookup_after_ids[kind])
        self.lookup_after_ids[kind] = self.after(250, lambda: self._start_company_lookup(kind))

    def _start_company_lookup(self, kind="reports"):
        self.lookup_after_ids[kind] = None
        query = self._lookup_var(kind).get().strip()
        api_key = self.api_key_var.get().strip() or get_configured_api_key()
        if len(query) < 1:
            self._hide_company_suggestions(kind)
            return
        self.lookup_tokens[kind] += 1
        token = self.lookup_tokens[kind]
        self._lookup_status_var(kind).set("Searching companies...")
        threading.Thread(target=self._run_company_lookup, args=(kind, token, query, api_key), daemon=True).start()

    def _run_company_lookup(self, kind, token, query, api_key):
        try:
            candidates = search_companies(api_key, query, limit=10)
            self.message_queue.put(("company_suggestions", kind, token, query, candidates))
        except Exception as exc:
            self.message_queue.put(("company_suggestions_error", kind, token, exc))

    def _show_company_suggestions(self, kind, candidates):
        listbox = self._lookup_listbox(kind)
        self.lookup_candidates[kind] = candidates
        listbox.delete(0, "end")
        for corp in candidates:
            stock = corp["stock_code"] or "unlisted"
            listbox.insert("end", f"  {corp['corp_name']}    {stock}    {corp['corp_code']}")
        if candidates:
            listbox.selection_clear(0, "end")
            listbox.activate(0)
            listbox.grid()
        else:
            self._hide_company_suggestions(kind)

    def _hide_company_suggestions(self, kind="reports"):
        listbox = self._lookup_listbox(kind)
        listbox.delete(0, "end")
        listbox.grid_remove()
        self.lookup_candidates[kind] = []

    def _focus_company_suggestions(self, kind="reports", _event=None):
        listbox = self._lookup_listbox(kind)
        if self.lookup_candidates[kind]:
            listbox.focus_set()
            listbox.selection_set(0)
            listbox.activate(0)
            return "break"
        return None

    def _select_active_company(self, kind="reports", _event=None):
        candidates = self.lookup_candidates[kind]
        listbox = self._lookup_listbox(kind)
        if not candidates:
            return None
        selection = listbox.curselection()
        index = selection[0] if selection else listbox.index("active")
        if index < 0 or index >= len(candidates):
            index = 0
        selected = candidates[index]
        self.selected_corps[kind] = selected
        self._lookup_var(kind).set(selected["corp_name"])
        self._hide_company_suggestions(kind)
        self._lookup_status_var(kind).set(f"Selected {selected['corp_name']} / {selected['stock_code'] or 'unlisted'}")
        return "break"

    def _selected_report_source(self):
        return "naver" if self.report_source_var.get().startswith("Naver") else "dart"

    def _sync_report_source_fields(self):
        if self._selected_report_source() == "naver":
            self.selected_corps["reports"] = None
            self._hide_company_suggestions("reports")
            self.api_key_label.configure(text=".env API key (used for company suggestions)")
            self.api_key_entry.state(["disabled"])
            self.save_env_button.state(["disabled"])
            self.naver_start_entry.state(["!disabled"])
            self.naver_end_entry.state(["!disabled"])
            self.report_count_label.configure(text="Research PDFs")
            self.report_count_spinbox.configure(textvariable=self.naver_count_var, from_=1, to=50)
        else:
            self.api_key_label.configure(text=".env API key")
            self.api_key_entry.state(["!disabled"])
            self.save_env_button.state(["!disabled"])
            self.naver_start_entry.state(["disabled"])
            self.naver_end_entry.state(["disabled"])
            self.report_count_label.configure(text="Reports")
            self.report_count_spinbox.configure(textvariable=self.years_var, from_=1, to=10)

    def _selected_batch_tasks(self):
        tasks = []
        if self.batch_dart_var.get():
            tasks.append("dart")
        if self.batch_naver_var.get():
            tasks.append("naver")
        if self.batch_catch_var.get():
            tasks.append("catch")
        if self.batch_news_var.get():
            tasks.append("news")
        return tasks

    def _validate_batch_run(self):
        tasks = self._selected_batch_tasks()
        if not self.selected_corps["batch"]:
            messagebox.showwarning(APP_TITLE, "Choose a company from the batch search suggestions first.")
            return None
        if not tasks:
            messagebox.showwarning(APP_TITLE, "Choose at least one batch task.")
            return None
        api_key = self.api_key_var.get().strip()
        if "dart" in tasks and not api_key:
            messagebox.showwarning(APP_TITLE, "OpenDART batch task needs an API key.")
            return None

        try:
            naver_start = parse_date_arg(self.naver_start_var.get().strip(), "Naver start date")
            naver_end = parse_date_arg(self.naver_end_var.get().strip(), "Naver end date")
            if naver_start and naver_end and naver_start > naver_end:
                raise DartError("Naver start date must be earlier than or equal to Naver end date.")
        except DartError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return None

        try:
            news_start = parse_news_date(self.news_start_var.get().strip())
            news_end = parse_news_date(self.news_end_var.get().strip())
        except NewsCrawlerError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return None

        try:
            if self.catch_today_only_var.get():
                catch_start = date.today().isoformat()
                catch_end = catch_start
            else:
                catch_start = self.catch_start_var.get().strip()
                catch_end = self.catch_end_var.get().strip()
            parse_catch_date(catch_start)
            parse_catch_date(catch_end)
        except CatchRecruitError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return None
        if parse_catch_date(catch_end) < parse_catch_date(catch_start):
            messagebox.showwarning(APP_TITLE, "Catch end date must be the same as or later than start date.")
            return None

        return {
            "tasks": tasks,
            "corp": self.selected_corps["batch"],
            "api_key": api_key,
            "company": self.selected_corps["batch"]["corp_name"],
            "naver_start": naver_start,
            "naver_end": naver_end,
            "news_start": news_start,
            "news_end": news_end,
            "catch_start": catch_start,
            "catch_end": catch_end,
        }

    def _start_batch_run(self):
        if self.batch_worker and self.batch_worker.is_alive():
            return
        if self.worker and self.worker.is_alive() or self.catch_worker and self.catch_worker.is_alive():
            messagebox.showwarning(APP_TITLE, "Another task is already running.")
            return
        config = self._validate_batch_run()
        if not config:
            return

        self._hide_company_suggestions("batch")
        self.batch_log.delete("1.0", "end")
        self._set_batch_running(True)
        self._batch_log(f"Starting batch for {config['company']}")
        self.batch_worker = threading.Thread(target=self._run_batch, args=(config,), daemon=True)
        self.batch_worker.start()

    def _run_batch(self, config):
        try:
            completed = 0
            for task in config["tasks"]:
                if task == "dart":
                    self.message_queue.put(("batch_log", "Running OpenDART business reports..."))
                    result = download_business_reports(
                        config["company"],
                        api_key=config["api_key"],
                        years=self.years_var.get(),
                        output_dir=Path(self.output_var.get()),
                        progress=lambda message: self.message_queue.put(("batch_log", message)),
                        corp=config["corp"],
                    )
                    if result["failed"]:
                        raise DartError(f"OpenDART failed for {len(result['failed'])} report(s).")
                    completed += 1
                    self.message_queue.put(("batch_log", f"OpenDART done: {len(result['downloaded'])} PDF file(s)."))
                elif task == "naver":
                    self.message_queue.put(("batch_log", "Running Naver Finance research..."))
                    result = download_naver_research_reports(
                        config["company"],
                        count=self.naver_count_var.get(),
                        output_dir=Path(self.output_var.get()),
                        start_date=config["naver_start"],
                        end_date=config["naver_end"],
                        progress=lambda message: self.message_queue.put(("batch_log", message)),
                    )
                    if result["failed"]:
                        raise DartError(f"Naver Finance failed for {len(result['failed'])} PDF file(s).")
                    completed += 1
                    self.message_queue.put(("batch_log", f"Naver Finance done: {len(result['downloaded'])} PDF file(s)."))
                elif task == "catch":
                    self.message_queue.put(("batch_log", "Running Catch Recruits..."))
                    result, output_path = self._read_catch_to_file(
                        keyword=config["company"],
                        progress=lambda message: self.message_queue.put(("batch_log", message)),
                    )
                    completed += 1
                    self.message_queue.put(("batch_log", f"Catch done: {len(result['items'])} item(s), {output_path}"))
                    self.message_queue.put(("catch_result", result, output_path))
                elif task == "news":
                    self.message_queue.put(("batch_log", "Running Company News..."))
                    output_text = self.news_output_var.get().strip()
                    output_path = (
                        Path(output_text)
                        if output_text
                        else default_news_output_path(config["company"], config["news_start"], config["news_end"])
                    )
                    result = crawl_company_news(
                        company=config["company"],
                        start_date=config["news_start"],
                        end_date=config["news_end"],
                        source=self.news_source_var.get(),
                        max_results=self.news_max_results_var.get(),
                        progress=lambda message: self.message_queue.put(("batch_log", message)),
                    )
                    saved_path = write_news_json(result, output_path)
                    completed += 1
                    self.message_queue.put(("batch_log", f"News done: {len(result['items'])} item(s), {saved_path}"))
                    self.message_queue.put(("news_done", result, saved_path))
            self.message_queue.put(("batch_done", completed, len(config["tasks"])))
        except Exception as exc:
            self.message_queue.put(("batch_error", exc))

    def _start_download(self):
        if self.worker and self.worker.is_alive():
            return
        company = self.company_var.get().strip()
        source = self._selected_report_source()
        api_key = self.api_key_var.get().strip()
        if not company:
            messagebox.showwarning(APP_TITLE, "Enter a company name.")
            return
        if source == "dart" and not api_key:
            messagebox.showwarning(APP_TITLE, "Enter an API key or save it in .env.")
            return
        if not self.selected_corps["reports"]:
            messagebox.showwarning(APP_TITLE, "Choose a company from the search suggestions first.")
            return

        self._hide_company_suggestions("reports")
        self.download_button.state(["disabled"])
        self.report_source_combo.state(["disabled"])
        self.progress.start(12)
        self.status_var.set("Working")
        self._log("")
        if source == "naver":
            self._log(f"Starting Naver Finance research download for: {company}")
        else:
            self._log(f"Starting OpenDART download for: {company}")

        self.worker = threading.Thread(
            target=self._run_download,
            args=(
                source,
                company,
                api_key,
                self.years_var.get(),
                self.naver_count_var.get(),
                self.naver_start_var.get().strip(),
                self.naver_end_var.get().strip(),
                Path(self.output_var.get()),
                self.selected_corps["reports"],
            ),
            daemon=True,
        )
        self.worker.start()

    def _run_download(self, source, company, api_key, years, count, start_date, end_date, output_dir, corp):
        try:
            if source == "naver":
                result = download_naver_research_reports(
                    company,
                    count=count,
                    output_dir=output_dir,
                    start_date=start_date,
                    end_date=end_date,
                    progress=self.message_queue.put,
                )
            else:
                result = download_business_reports(
                    company,
                    api_key=api_key,
                    years=years,
                    output_dir=output_dir,
                    progress=self.message_queue.put,
                    corp=corp,
                )
            self.message_queue.put(("reports_done", result))
        except Exception as exc:
            self.message_queue.put(("reports_error", exc))

    def _start_news_crawl(self):
        if self.worker and self.worker.is_alive():
            return
        company = self.news_company_var.get().strip()
        if not company:
            messagebox.showwarning(APP_TITLE, "Enter a company name.")
            return
        if not self.selected_corps["news"]:
            messagebox.showwarning(APP_TITLE, "Choose a company from the search suggestions first.")
            return
        try:
            start_date = parse_news_date(self.news_start_var.get().strip())
            end_date = parse_news_date(self.news_end_var.get().strip())
        except NewsCrawlerError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return
        max_results = self.news_max_results_var.get()
        if max_results < 1:
            messagebox.showwarning(APP_TITLE, "Max results must be greater than 0.")
            return

        output_text = self.news_output_var.get().strip()
        output_path = Path(output_text) if output_text else default_news_output_path(company, start_date, end_date)

        self._hide_company_suggestions("news")
        self.news_button.state(["disabled"])
        self.news_progress.start(12)
        self.news_status_var.set("Working")
        self._news_log("")
        self._news_log(f"Starting news crawl for: {company}")
        self.worker = threading.Thread(
            target=self._run_news_crawl,
            args=(company, start_date, end_date, self.news_source_var.get(), max_results, output_path),
            daemon=True,
        )
        self.worker.start()

    def _run_news_crawl(self, company, start_date, end_date, source, max_results, output_path):
        try:
            result = crawl_company_news(
                company=company,
                start_date=start_date,
                end_date=end_date,
                source=source,
                max_results=max_results,
                progress=lambda message: self.message_queue.put(("news_log", message)),
            )
            saved_path = write_news_json(result, output_path)
            self.message_queue.put(("news_done", result, saved_path))
        except Exception as exc:
            self.message_queue.put(("news_error", exc))

    def _start_catch_once(self):
        if self.catch_worker and self.catch_worker.is_alive():
            return
        if not self._validate_catch_dates():
            return
        self._set_catch_running(True)
        self.catch_worker = threading.Thread(target=self._run_catch_once, daemon=True)
        self.catch_worker.start()

    def _run_catch_once(self):
        try:
            self._read_catch_and_save()
            self.message_queue.put(("catch_done", "Done."))
        except Exception as exc:
            self.message_queue.put(("catch_error", exc))

    def _read_catch_and_save(self):
        keyword = self.catch_keyword_var.get().strip()
        output_dir = Path(self.catch_output_var.get())
        if self.catch_today_only_var.get():
            start_date = date.today().isoformat()
            end_date = start_date
        else:
            start_date = self.catch_start_var.get().strip()
            end_date = self.catch_end_var.get().strip()

        def tell(message):
            self.message_queue.put(("catch_log", message))

        result = crawl_catch_recruits(
            keyword=keyword,
            max_results=DEFAULT_MAX_RESULTS,
            start_date=start_date,
            end_date=end_date,
            progress=tell,
        )
        output_path = output_dir / default_catch_output_path(keyword or "all").name
        write_catch_json(result, output_path)
        self.message_queue.put(("catch_result", result, output_path))

    def _validate_catch_dates(self):
        try:
            start_date = parse_catch_date(self.catch_start_var.get().strip())
            end_date = parse_catch_date(self.catch_end_var.get().strip())
        except CatchRecruitError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return False
        if end_date < start_date:
            messagebox.showwarning(APP_TITLE, "End date must be the same as or later than start date.")
            return False
        return True

    def _drain_queue(self):
        try:
            while True:
                item = self.message_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "reports_done":
                    result = item[1]
                    saved = len(result["downloaded"])
                    failed = len(result["failed"])
                    if failed:
                        self._finish_reports(f"Finished with errors. Saved {saved}, failed {failed}.")
                    else:
                        self._finish_reports(f"Done. Saved {saved} PDF file(s).")
                elif isinstance(item, tuple) and item[0] == "reports_error":
                    exc = item[1]
                    self._finish_reports("Failed")
                    messagebox.showerror(APP_TITLE, str(exc))
                    self._log(f"ERROR: {exc}")
                elif isinstance(item, tuple) and item[0] == "company_suggestions":
                    _message_type, kind, token, query, candidates = item
                    if token == self.lookup_tokens[kind] and query == self._lookup_var(kind).get().strip():
                        self._show_company_suggestions(kind, candidates)
                        self._lookup_status_var(kind).set(f"Found {len(candidates)} company match(es).")
                elif isinstance(item, tuple) and item[0] == "company_suggestions_error":
                    _message_type, kind, token, exc = item
                    if token == self.lookup_tokens[kind]:
                        self._hide_company_suggestions(kind)
                        self._lookup_status_var(kind).set("No company matches.")
                        self._lookup_log(kind, f"Company search: {exc}")
                elif isinstance(item, tuple) and item[0] == "news_log":
                    self._news_log(item[1])
                elif isinstance(item, tuple) and item[0] == "news_done":
                    self._show_news_result(item[1], item[2])
                    self._finish_news(f"Done. Saved {len(item[1]['items'])} news item(s).")
                elif isinstance(item, tuple) and item[0] == "news_error":
                    exc = item[1]
                    self._finish_news("Failed")
                    messagebox.showerror(APP_TITLE, str(exc))
                    self._news_log(f"ERROR: {exc}")
                elif isinstance(item, tuple) and item[0] == "catch_log":
                    self._catch_log(item[1])
                elif isinstance(item, tuple) and item[0] == "catch_result":
                    self._show_catch_result(item[1], item[2])
                elif isinstance(item, tuple) and item[0] == "catch_done":
                    self._finish_catch(item[1])
                elif isinstance(item, tuple) and item[0] == "catch_error":
                    exc = item[1]
                    self._finish_catch("Failed")
                    messagebox.showerror(APP_TITLE, str(exc))
                    self._catch_log(f"ERROR: {exc}")
                else:
                    self._log(str(item))
        except queue.Empty:
            pass
        self.after(120, self._drain_queue)

    def _finish_reports(self, status):
        self.progress.stop()
        self.status_var.set(status)
        self.download_button.state(["!disabled"])
        self.report_source_combo.state(["!disabled"])
        self._sync_report_source_fields()
        self._log(status)

    def _set_catch_running(self, running):
        if running:
            self.catch_read_button.state(["disabled"])
            self.catch_progress.start(12)
            self.catch_status_var.set("Reading...")
            self._catch_log("")
            self._catch_log(f"Starting Catch read for: {self.catch_keyword_var.get().strip() or 'all'}")
        else:
            self.catch_progress.stop()
            self.catch_read_button.state(["!disabled"])

    def _finish_catch(self, status):
        self._set_catch_running(False)
        self.catch_status_var.set(status)
        self._catch_log(status)

    def _show_catch_result(self, result, output_path):
        self.catch_links = {}
        for row_id in self.catch_table.get_children():
            self.catch_table.delete(row_id)
        for item in result["items"]:
            row_id = self.catch_table.insert(
                "",
                "end",
                values=(
                    item.get("company", ""),
                    item.get("title", ""),
                    item.get("start_date", ""),
                    item.get("deadline", ""),
                    item.get("career", ""),
                    item.get("location", ""),
                ),
            )
            self.catch_links[row_id] = item.get("link", "")
        message = f"Saved {len(result['items'])} recruit item(s): {Path(output_path).resolve()}"
        self.catch_status_var.set(message)
        self._catch_log(message)

    def _open_selected_catch_recruit(self, event=None):
        row_id = self.catch_table.identify_row(event.y) if event else ""
        if not row_id:
            selection = self.catch_table.selection()
            row_id = selection[0] if selection else ""
        if not row_id:
            return
        link = self.catch_links.get(row_id, "").strip()
        if not link:
            self._catch_log("No recruit link is available for the selected row.")
            return
        webbrowser.open(link)
        self._catch_log(f"Opened: {link}")

    def _finish_news(self, status):
        self.news_progress.stop()
        self.news_status_var.set(status)
        self.news_button.state(["!disabled"])
        self._news_log(status)

    def _show_news_result(self, result, output_path):
        for row_id in self.news_table.get_children():
            self.news_table.delete(row_id)
        for item in result["items"]:
            self.news_table.insert(
                "",
                "end",
                values=(
                    item.get("source", ""),
                    item.get("publisher", ""),
                    item.get("published_at", ""),
                    item.get("title", ""),
                ),
            )
        message = f"Saved {len(result['items'])} news item(s): {Path(output_path).resolve()}"
        self.news_status_var.set(message)
        self._news_log(message)
        if result.get("errors"):
            self._news_log(f"Source errors: {', '.join(result['errors'])}")

    def _log(self, message):
        self.log.insert("end", f"{message}\n")
        self.log.see("end")

    def _catch_log(self, message):
        self.catch_log.insert("end", f"{message}\n")
        self.catch_log.see("end")

    def _news_log(self, message):
        self.news_log.insert("end", f"{message}\n")
        self.news_log.see("end")

    def _on_close(self):
        self.destroy()


def main():
    try:
        app = DownloaderApp()
        app.mainloop()
    except (DartError, CatchRecruitError, NewsCrawlerError) as exc:
        messagebox.showerror(APP_TITLE, str(exc))


if __name__ == "__main__":
    main()

