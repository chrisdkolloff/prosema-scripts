"""Dynamic form widgets built from a JobSpec."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog
from typing import Any

import customtkinter as ctk

from gui.job_spec import FieldKind, FieldSpec, JobSpec, default_output_path, defaults_from_spec


class JobForm(ctk.CTkFrame):
    """Renders input fields for one job and collects parameter values."""

    def __init__(self, master, job: JobSpec, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.job = job
        self._widgets: dict[str, Any] = {}
        self._bool_vars: dict[str, tk.BooleanVar] = {}
        self._suggested_output: str | None = None
        self._build()

    def _build(self) -> None:
        defaults = defaults_from_spec(self.job)
        standard = [f for f in self.job.fields if not f.advanced]
        advanced = [f for f in self.job.fields if f.advanced]

        for fld in standard:
            self._add_field(fld, defaults[fld.name])

        if advanced:
            self._advanced_visible = False
            self._advanced_toggle = ctk.CTkButton(
                self,
                text="▶ Erweitert",
                width=120,
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray85", "gray25"),
                command=self._toggle_advanced,
            )
            self._advanced_toggle.grid(row=self._next_row(), column=0, sticky="w", pady=(8, 4))

            self._advanced_frame = ctk.CTkFrame(self, fg_color="transparent")
            for fld in advanced:
                self._add_field(fld, defaults[fld.name], parent=self._advanced_frame)
            self._advanced_frame.grid(row=self._next_row(), column=0, sticky="ew")
            self._advanced_frame.grid_remove()

        self.grid_columnconfigure(0, weight=1)

    def _next_row(self) -> int:
        return len(self._widgets) + (1 if hasattr(self, "_advanced_toggle") else 0)

    def _toggle_advanced(self) -> None:
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            self._advanced_frame.grid()
            self._advanced_toggle.configure(text="▼ Erweitert")
        else:
            self._advanced_frame.grid_remove()
            self._advanced_toggle.configure(text="▶ Erweitert")

    def _add_field(self, fld: FieldSpec, default: Any, parent: ctk.CTkFrame | None = None) -> None:
        parent = parent or self
        row = parent.grid_size()[1]

        label = ctk.CTkLabel(parent, text=fld.label, anchor="w")
        label.grid(row=row, column=0, sticky="w", pady=(6, 2))

        if fld.kind == FieldKind.BOOL:
            var = tk.BooleanVar(value=bool(default))
            self._bool_vars[fld.name] = var
            cb = ctk.CTkCheckBox(parent, text="", variable=var)
            cb.grid(row=row + 1, column=0, sticky="w", pady=(0, 4))
            self._widgets[fld.name] = cb
            return

        if fld.kind in (FieldKind.FILE_IN, FieldKind.FILE_OUT):
            row_frame = ctk.CTkFrame(parent, fg_color="transparent")
            row_frame.grid(row=row + 1, column=0, sticky="ew", pady=(0, 4))
            row_frame.grid_columnconfigure(0, weight=1)

            entry = ctk.CTkEntry(row_frame)
            entry.insert(0, str(default))
            entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            self._widgets[fld.name] = entry

            browse = ctk.CTkButton(
                row_frame,
                text="Durchsuchen…",
                width=110,
                command=lambda f=fld: self._browse_file(f),
            )
            browse.grid(row=0, column=1)

            if fld.kind == FieldKind.FILE_IN:
                entry.bind("<FocusOut>", lambda _e: self._maybe_update_output())
                entry.bind("<Return>", lambda _e: self._maybe_update_output())
            return

        entry = ctk.CTkEntry(parent)
        entry.insert(0, str(default))
        entry.grid(row=row + 1, column=0, sticky="ew", pady=(0, 4))
        self._widgets[fld.name] = entry

    def _browse_file(self, fld: FieldSpec) -> None:
        entry: ctk.CTkEntry = self._widgets[fld.name]
        if fld.kind == FieldKind.FILE_IN:
            path = filedialog.askopenfilename(
                title=fld.label,
                filetypes=[("Excel", "*.xlsx"), ("Alle Dateien", "*.*")],
            )
        else:
            initial = entry.get().strip()
            path = filedialog.asksaveasfilename(
                title=fld.label,
                defaultextension=".xlsx",
                initialfile=initial.split("/")[-1] if initial else "",
                filetypes=[("Excel", "*.xlsx"), ("Alle Dateien", "*.*")],
            )
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)
            if fld.kind == FieldKind.FILE_IN:
                self._maybe_update_output()

    def _maybe_update_output(self) -> None:
        input_entry = self._widgets.get("input")
        output_entry = self._widgets.get("output")
        if input_entry is None or output_entry is None:
            return

        input_path = input_entry.get().strip()
        if not input_path:
            return

        output_field = next((f for f in self.job.fields if f.name == "output"), None)
        if output_field is None or not output_field.output_name:
            return

        suggested = str(default_output_path(input_path, output_field.output_name))
        current = output_entry.get().strip()
        if not current or current == self._suggested_output or current == str(output_field.default):
            output_entry.delete(0, "end")
            output_entry.insert(0, suggested)
            self._suggested_output = suggested

    def collect_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for fld in self.job.fields:
            if fld.kind == FieldKind.BOOL:
                params[fld.name] = self._bool_vars[fld.name].get()
            else:
                params[fld.name] = self._widgets[fld.name].get()
        return params
