"""Dynamic form widgets built from a JobSpec."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Any

import customtkinter as ctk

from gui.job_spec import FieldKind, FieldSpec, JobSpec, default_output_path, defaults_from_spec


def _next_grid_row(parent: tk.Misc) -> int:
    max_row = -1
    for child in parent.winfo_children():
        info = child.grid_info()
        if info:
            row = int(info["row"])
            span = int(info.get("rowspan", 1))
            max_row = max(max_row, row + span - 1)
    return max_row + 1


class ScrollableFrame(ctk.CTkFrame):
    """Canvas-based vertical scroll area with a fixed viewport height."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        bg = self._apply_appearance_mode(self.cget("bg_color"))
        self._canvas = tk.Canvas(self, highlightthickness=0, bg=bg)
        self._scrollbar = ctk.CTkScrollbar(self, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar.grid(row=0, column=1, sticky="ns")

        self._inner = ctk.CTkFrame(self._canvas, fg_color="transparent")
        self._window_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<Enter>", self._bind_mousewheel)
        self._canvas.bind("<Leave>", self._unbind_mousewheel)
        self._inner.bind("<Enter>", self._bind_mousewheel)
        self._inner.bind("<Leave>", self._unbind_mousewheel)

    @property
    def inner(self) -> ctk.CTkFrame:
        return self._inner

    def refresh(self) -> None:
        self._canvas.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_inner_configure(self, _event: tk.Event) -> None:
        self.refresh()

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._window_id, width=event.width)

    def _bind_mousewheel(self, _event: tk.Event) -> None:
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind_all("<Button-4>", self._on_mousewheel)
        self._canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event) -> None:
        self._canvas.unbind_all("<MouseWheel>")
        self._canvas.unbind_all("<Button-4>")
        self._canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        elif sys.platform == "darwin":
            self._canvas.yview_scroll(-int(event.delta), "units")
        else:
            self._canvas.yview_scroll(-int(event.delta / 6), "units")


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
            self._advanced_toggle.grid(row=self._next_row(), column=0, sticky="w", pady=(16, 6))

            self._advanced_frame = ctk.CTkFrame(self, fg_color="transparent")
            for fld in advanced:
                self._add_field(fld, defaults[fld.name], parent=self._advanced_frame)
            self._advanced_frame.grid(row=self._next_row(), column=0, sticky="ew")
            self._advanced_frame.grid_remove()

        self.grid_columnconfigure(0, weight=1)

    def _next_row(self) -> int:
        return _next_grid_row(self)

    def _toggle_advanced(self) -> None:
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            self._advanced_frame.grid()
            self._advanced_toggle.configure(text="▼ Erweitert")
        else:
            self._advanced_frame.grid_remove()
            self._advanced_toggle.configure(text="▶ Erweitert")
        self._refresh_scroll()

    def _refresh_scroll(self) -> None:
        widget: tk.Misc | None = self
        while widget is not None:
            if isinstance(widget, ScrollableFrame):
                widget.refresh()
                return
            widget = widget.master

    def _add_field(self, fld: FieldSpec, default: Any, parent: ctk.CTkFrame | None = None) -> None:
        parent = parent or self
        row = _next_grid_row(parent)

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
            out_name = fld.output_name or str(fld.default)
            suffix = Path(out_name).suffix
            default_ext = suffix if suffix else ".xlsx"
            if default_ext == ".csv":
                filetypes = [("CSV", "*.csv"), ("Alle Dateien", "*.*")]
            elif default_ext == ".html":
                filetypes = [("HTML", "*.html"), ("Alle Dateien", "*.*")]
            else:
                filetypes = [("Excel", "*.xlsx"), ("Alle Dateien", "*.*")]
            path = filedialog.asksaveasfilename(
                title=fld.label,
                defaultextension=default_ext,
                initialfile=initial.split("/")[-1] if initial else "",
                filetypes=filetypes,
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

        suggested = str(
            default_output_path(
                input_path,
                output_field.output_name,
                default_output=output_field.default,
            )
        )
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
