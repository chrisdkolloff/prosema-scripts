"""PROSEMA desktop GUI."""

from __future__ import annotations

import sys
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox, Event

from gui.job_spec import JobSpec, RunResult
from gui.registry import JOBS
from gui.runner import JobRunner
from gui.widgets import JobForm, ScrollableFrame

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ProsemaApp(ctk.CTk):
    SIDEBAR_WIDTH = 200

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("green")

        self.title("PROSEMA Werkzeuge")
        self.geometry("820x620")
        self.minsize(720, 520)

        self._jobs: dict[str, JobSpec] = {job.id: job for job in JOBS}
        self._forms: dict[str, JobForm] = {}
        self._current_job_id: str | None = None

        self._runner = JobRunner(
            on_log=self._append_log,
            on_success=self._on_success,
            on_error=self._on_error,
            on_finished=self._on_finished,
        )

        self._build_layout()
        self._check_setup()

        if JOBS:
            self._select_job(JOBS[0].id)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=self.SIDEBAR_WIDTH, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(len(JOBS) + 1, weight=1)

        title = ctk.CTkLabel(
            sidebar,
            text="PROSEMA",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.grid(row=0, column=0, padx=16, pady=(20, 16), sticky="w")

        self._job_buttons: dict[str, ctk.CTkButton] = {}
        for idx, job in enumerate(JOBS, start=1):
            btn = ctk.CTkButton(
                sidebar,
                text=job.title,
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray85", "gray25"),
                command=lambda jid=job.id: self._select_job(jid),
            )
            btn.grid(row=idx, column=0, padx=12, pady=4, sticky="ew")
            self._job_buttons[job.id] = btn

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        self._scroll = ScrollableFrame(main)
        self._scroll.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        content = self._scroll.inner
        content.grid_columnconfigure(0, weight=1)

        self._job_title = ctk.CTkLabel(
            content,
            text="",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
        )
        self._job_title.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        self._job_description = ctk.CTkLabel(
            content,
            text="",
            anchor="w",
            wraplength=560,
            justify="left",
            text_color=("gray30", "gray70"),
        )
        self._job_description.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        content.bind("<Configure>", self._update_description_wrap)

        self._form_container = ctk.CTkFrame(content, fg_color="transparent")
        self._form_container.grid(row=2, column=0, sticky="ew")
        self._form_container.grid_columnconfigure(0, weight=1)

        action_row = ctk.CTkFrame(content, fg_color="transparent")
        action_row.grid(row=3, column=0, sticky="new", pady=(8, 8))
        self._generate_btn = ctk.CTkButton(
            action_row,
            text="Generieren",
            width=140,
            command=self._on_generate,
        )
        self._generate_btn.pack(side="left")

        log_label = ctk.CTkLabel(main, text="Protokoll", anchor="w")
        log_label.grid(row=1, column=0, sticky="ew", pady=(4, 4))

        self._log = ctk.CTkTextbox(main, height=180, state="disabled")
        self._log.grid(row=2, column=0, sticky="ew")

    def _update_description_wrap(self, event: Event) -> None:
        width = event.width - 24
        if width > 100:
            self._job_description.configure(wraplength=width)

    def _check_setup(self) -> None:
        if not (PROJECT_ROOT / ".venv").is_dir():
            messagebox.showerror(
                "Einrichtung fehlt",
                "Die Einrichtung wurde noch nicht ausgeführt.\n\n"
                "Bitte zuerst setup.command doppelklicken.",
            )

    def _select_job(self, job_id: str) -> None:
        if self._current_job_id == job_id:
            return

        for jid, btn in self._job_buttons.items():
            if jid == job_id:
                btn.configure(fg_color=("gray75", "gray25"))
            else:
                btn.configure(fg_color="transparent")

        for child in self._form_container.winfo_children():
            child.grid_remove()

        job = self._jobs[job_id]
        if job_id not in self._forms:
            form = JobForm(self._form_container, job)
            form.grid(row=0, column=0, sticky="ew")
            self._forms[job_id] = form
        else:
            self._forms[job_id].grid()

        self._current_job_id = job_id
        self._job_title.configure(text=job.title)
        self._job_description.configure(text=job.description)
        self.after_idle(self._scroll.refresh)

    def _on_generate(self) -> None:
        if self._current_job_id is None or self._runner.running:
            return

        job = self._jobs[self._current_job_id]
        params = self._forms[self._current_job_id].collect_params()
        self._generate_btn.configure(state="disabled")
        self._append_log(f"\n--- {job.title} ---")
        self._runner.run(job, params)

    def _append_log(self, text: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _on_success(self, result: RunResult, captured: str) -> None:
        if captured:
            self._append_log(captured)
        self._append_log(result.summary)
        for line in result.details:
            self._append_log(line)
        if result.show_success_dialog:
            self.after(0, lambda: messagebox.showinfo("Fertig", result.summary))

    def _on_error(self, message: str) -> None:
        self._append_log(message)
        self.after(0, lambda: messagebox.showerror("Fehler", message))

    def _on_finished(self) -> None:
        self.after(0, lambda: self._generate_btn.configure(state="normal"))


def main() -> None:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    app = ProsemaApp()
    app.mainloop()


if __name__ == "__main__":
    main()
