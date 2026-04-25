import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from download_business_reports import DEFAULT_OUTPUT_DIR, ENV_PATH, DartError, download_business_reports, get_configured_api_key


APP_TITLE = "OpenDART Business Report Downloader"


class DownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x560")
        self.minsize(700, 500)

        self.message_queue = queue.Queue()
        self.worker = None

        self.company_var = tk.StringVar()
        self.api_key_var = tk.StringVar(value=get_configured_api_key())
        self.output_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.years_var = tk.IntVar(value=5)
        self.status_var = tk.StringVar(value="Ready")

        self.configure(bg="#f6f7f9")
        self._configure_style()
        self._build_layout()
        self.after(120, self._drain_queue)

    def _configure_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f6f7f9")
        style.configure("Header.TFrame", background="#17202a")
        style.configure("Title.TLabel", background="#17202a", foreground="#ffffff", font=("Segoe UI", 18, "bold"))
        style.configure("Subtitle.TLabel", background="#17202a", foreground="#b9c2cf", font=("Segoe UI", 10))
        style.configure("TLabel", background="#f6f7f9", foreground="#222831", font=("Segoe UI", 10))
        style.configure("Field.TLabel", background="#f6f7f9", foreground="#46515f", font=("Segoe UI", 9, "bold"))
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8))
        style.configure("Accent.TButton", background="#0f766e", foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#115e59"), ("disabled", "#94a3b8")])
        style.configure("Horizontal.TProgressbar", background="#0f766e", troughcolor="#d8dee8")

    def _build_layout(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(24, 22))
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Download the latest annual business report PDFs by company name.", style="Subtitle.TLabel").pack(anchor="w", pady=(6, 0))

        body = ttk.Frame(self, padding=(24, 18))
        body.pack(fill="both", expand=True)

        form = ttk.Frame(body)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Company", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        company = ttk.Entry(form, textvariable=self.company_var, font=("Segoe UI", 11))
        company.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        company.focus()

        ttk.Label(form, text=".env API key", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 6))
        api_key = ttk.Entry(form, textvariable=self.api_key_var, show="*", font=("Segoe UI", 10))
        api_key.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 14), padx=(0, 8))
        ttk.Button(form, text="Save .env", command=self._save_env).grid(row=3, column=2, sticky="ew", pady=(0, 14))

        ttk.Label(form, text="Output folder", style="Field.TLabel").grid(row=4, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(form, textvariable=self.output_var, font=("Segoe UI", 10)).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 14), padx=(0, 8))
        ttk.Button(form, text="Browse", command=self._browse_output).grid(row=5, column=2, sticky="ew", pady=(0, 14))

        ttk.Label(form, text="Reports", style="Field.TLabel").grid(row=6, column=0, sticky="w", pady=(0, 6))
        years = ttk.Spinbox(form, from_=1, to=10, textvariable=self.years_var, width=8)
        years.grid(row=7, column=0, sticky="w", pady=(0, 18))

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(4, 14))
        self.download_button = ttk.Button(actions, text="Download PDFs", style="Accent.TButton", command=self._start_download)
        self.download_button.pack(side="left")
        ttk.Label(actions, textvariable=self.status_var).pack(side="left", padx=(16, 0))

        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 14))

        log_frame = ttk.Frame(body)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=12, wrap="word", relief="flat", bg="#ffffff", fg="#1f2933", font=("Consolas", 10), padx=12, pady=10)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.pack(side="left", fill="both", expand=True)
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

    def _start_download(self):
        if self.worker and self.worker.is_alive():
            return
        company = self.company_var.get().strip()
        api_key = self.api_key_var.get().strip()
        if not company:
            messagebox.showwarning(APP_TITLE, "Enter a company name.")
            return
        if not api_key:
            messagebox.showwarning(APP_TITLE, "Enter an API key or save it in .env.")
            return

        self.download_button.state(["disabled"])
        self.progress.start(12)
        self.status_var.set("Working")
        self._log("")
        self._log(f"Starting download for: {company}")

        self.worker = threading.Thread(
            target=self._run_download,
            args=(company, api_key, self.years_var.get(), Path(self.output_var.get())),
            daemon=True,
        )
        self.worker.start()

    def _run_download(self, company, api_key, years, output_dir):
        try:
            result = download_business_reports(company, api_key=api_key, years=years, output_dir=output_dir, progress=self.message_queue.put)
            self.message_queue.put(("done", result))
        except Exception as exc:
            self.message_queue.put(("error", exc))

    def _drain_queue(self):
        try:
            while True:
                item = self.message_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "done":
                    result = item[1]
                    saved = len(result["downloaded"])
                    failed = len(result["failed"])
                    if failed:
                        self._finish(f"Finished with errors. Saved {saved}, failed {failed}.")
                    else:
                        self._finish(f"Done. Saved {saved} PDF file(s).")
                elif isinstance(item, tuple) and item[0] == "error":
                    exc = item[1]
                    self._finish("Failed")
                    messagebox.showerror(APP_TITLE, str(exc))
                    self._log(f"ERROR: {exc}")
                else:
                    self._log(str(item))
        except queue.Empty:
            pass
        self.after(120, self._drain_queue)

    def _finish(self, status):
        self.progress.stop()
        self.status_var.set(status)
        self.download_button.state(["!disabled"])
        self._log(status)

    def _log(self, message):
        self.log.insert("end", f"{message}\n")
        self.log.see("end")


def main():
    try:
        app = DownloaderApp()
        app.mainloop()
    except DartError as exc:
        messagebox.showerror(APP_TITLE, str(exc))


if __name__ == "__main__":
    main()
