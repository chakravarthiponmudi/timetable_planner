"""
Tkinter GUI editor for the timetable input JSON consumed by `timetable_solver.py`.

Schema (high-level):
{
  "constraints": {
    "min_classes_per_week": int?,
    "min_classes_per_week_by_class": { "<class_name>": int }?,
    "max_sessions_per_day_by_tag": { "<tag>": int }?
  },
  "calendar": { "days": [str], "periods": [str] },
  "classes": [
    {
      "name": str,
      "semesters": {
        "S1": { "subjects": [ ... ] },
        "S2": { "subjects": [ ... ] }
      }
    }
  ]
}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


SEMESTERS: Tuple[str, ...] = ("S1", "S2")


def _safe_int(s: str) -> Optional[int]:
    s = (s or "").strip()
    if s == "":
        return None
    return int(s)


def _parse_csv_list(s: str) -> List[str]:
    # Split by comma, trim, drop empties, preserve order.
    parts = [(p or "").strip() for p in (s or "").split(",")]
    return [p for p in parts if p]


def _format_csv_list(items: List[str]) -> str:
    return ", ".join(items)


@dataclass
class SubjectRow:
    name: str
    teacher: str
    sessions_per_week: int
    min_contiguous_periods: int = 1
    max_contiguous_periods: int = 1
    tags: List[str] = None  # type: ignore[assignment]

    def to_json(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "name": self.name,
            "teacher": self.teacher,
            "sessions_per_week": int(self.sessions_per_week),
        }
        if int(self.min_contiguous_periods) != 1:
            out["min_contiguous_periods"] = int(self.min_contiguous_periods)
        if int(self.max_contiguous_periods) != int(self.min_contiguous_periods):
            out["max_contiguous_periods"] = int(self.max_contiguous_periods)
        tags = [t.strip() for t in (self.tags or []) if (t or "").strip()]
        if tags:
            out["tags"] = tags
        return out

    @staticmethod
    def from_json(d: Dict[str, Any]) -> "SubjectRow":
        return SubjectRow(
            name=str(d.get("name") or ""),
            teacher=str(d.get("teacher") or ""),
            sessions_per_week=int(d.get("sessions_per_week") or 0),
            min_contiguous_periods=int(d.get("min_contiguous_periods") or 1),
            max_contiguous_periods=int(d.get("max_contiguous_periods") or (d.get("min_contiguous_periods") or 1)),
            tags=list(d.get("tags") or []),
        )


class SubjectDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, *, title: str, initial: Optional[SubjectRow] = None) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.result: Optional[SubjectRow] = None

        initial = initial or SubjectRow(name="", teacher="", sessions_per_week=1, min_contiguous_periods=1, max_contiguous_periods=1, tags=[])

        frm = ttk.Frame(self, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")

        self.var_name = tk.StringVar(value=initial.name)
        self.var_teacher = tk.StringVar(value=initial.teacher)
        self.var_spw = tk.StringVar(value=str(initial.sessions_per_week))
        self.var_min_cp = tk.StringVar(value=str(initial.min_contiguous_periods))
        self.var_max_cp = tk.StringVar(value=str(initial.max_contiguous_periods))
        self.var_tags = tk.StringVar(value=_format_csv_list(list(initial.tags or [])))

        def add_row(r: int, label: str, var: tk.StringVar) -> None:
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=4)
            ttk.Entry(frm, textvariable=var, width=40).grid(row=r, column=1, sticky="ew", pady=4)

        add_row(0, "Subject name*", self.var_name)
        add_row(1, "Teacher*", self.var_teacher)
        add_row(2, "Sessions per week*", self.var_spw)
        add_row(3, "Min contiguous periods", self.var_min_cp)
        add_row(4, "Max contiguous periods", self.var_max_cp)
        add_row(5, "Tags (comma-separated)", self.var_tags)

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Cancel", command=self._on_cancel).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btns, text="OK", command=self._on_ok).grid(row=0, column=1)

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_ok())

        self.transient(master)
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _on_ok(self) -> None:
        try:
            name = (self.var_name.get() or "").strip()
            teacher = (self.var_teacher.get() or "").strip()
            if not name:
                raise ValueError("Subject name is required.")
            if not teacher:
                raise ValueError("Teacher is required.")
            spw = int((self.var_spw.get() or "").strip())
            if spw <= 0:
                raise ValueError("Sessions per week must be a positive integer.")
            min_cp = int((self.var_min_cp.get() or "1").strip())
            max_cp = int((self.var_max_cp.get() or str(min_cp)).strip())
            if min_cp <= 0 or max_cp <= 0:
                raise ValueError("Contiguous periods must be positive integers.")
            if min_cp > max_cp:
                raise ValueError("Min contiguous periods cannot exceed max contiguous periods.")
            tags = _parse_csv_list(self.var_tags.get())
            self.result = SubjectRow(
                name=name,
                teacher=teacher,
                sessions_per_week=spw,
                min_contiguous_periods=min_cp,
                max_contiguous_periods=max_cp,
                tags=tags,
            )
            self.destroy()
        except Exception as e:
            messagebox.showerror("Invalid subject", str(e), parent=self)


class TagLimitDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, *, title: str, initial: Optional[Tuple[str, int]] = None) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.result: Optional[Tuple[str, int]] = None

        tag0, lim0 = initial if initial is not None else ("", 1)
        self.var_tag = tk.StringVar(value=tag0)
        self.var_limit = tk.StringVar(value=str(lim0))

        frm = ttk.Frame(self, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="Tag*").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(frm, textvariable=self.var_tag, width=30).grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(frm, text="Max sessions/day*").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(frm, textvariable=self.var_limit, width=30).grid(row=1, column=1, sticky="ew", pady=4)

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Cancel", command=self._on_cancel).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btns, text="OK", command=self._on_ok).grid(row=0, column=1)

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_ok())

        self.transient(master)
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _on_ok(self) -> None:
        try:
            tag = (self.var_tag.get() or "").strip()
            if not tag:
                raise ValueError("Tag is required.")
            limit = int((self.var_limit.get() or "").strip())
            if limit < 0:
                raise ValueError("Max sessions/day must be a non-negative integer.")
            self.result = (tag, limit)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Invalid tag constraint", str(e), parent=self)


class TimetableEditorApp(tk.Tk):
    def __init__(self, *, open_path: Optional[str] = None) -> None:
        super().__init__()
        self.title("Timetable Input Editor")
        self.minsize(980, 640)

        self._current_path: Optional[str] = None
        self._dirty = False
        self._last_selected_class_name: Optional[str] = None

        self._data: Dict[str, Any] = self._new_data()

        self._build_menu()
        self._build_ui()

        if open_path:
            try:
                self.load_json(open_path)
            except Exception as e:
                messagebox.showerror("Failed to open", str(e), parent=self)

    def _new_data(self) -> Dict[str, Any]:
        return {
            "constraints": {
                "min_classes_per_week": 0,
                "max_sessions_per_day_by_tag": {},
            },
            "calendar": {"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "periods": ["P1", "P2", "P3", "P4", "P5"]},
            "classes": [],
        }

    def _set_dirty(self, dirty: bool = True) -> None:
        self._dirty = dirty
        suffix = "*" if self._dirty else ""
        base = "Timetable Input Editor"
        if self._current_path:
            base = f"{base} — {os.path.basename(self._current_path)}"
        self.title(base + suffix)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        filem = tk.Menu(menubar, tearoff=0)
        filem.add_command(label="New", command=self.on_new)
        filem.add_command(label="Open…", command=self.on_open)
        filem.add_separator()
        filem.add_command(label="Save", command=self.on_save)
        filem.add_command(label="Save As…", command=self.on_save_as)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.on_exit)
        menubar.add_cascade(label="File", menu=filem)
        self.config(menu=menubar)

        self.protocol("WM_DELETE_WINDOW", self.on_exit)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True)

        # Calendar tab
        self.tab_calendar = ttk.Frame(nb, padding=12)
        nb.add(self.tab_calendar, text="Calendar")
        self.var_days = tk.StringVar(value=_format_csv_list(self._data["calendar"]["days"]))
        self.var_periods = tk.StringVar(value=_format_csv_list(self._data["calendar"]["periods"]))

        ttk.Label(self.tab_calendar, text="Days (comma-separated)*").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(self.tab_calendar, textvariable=self.var_days, width=80).grid(row=1, column=0, sticky="ew", pady=(0, 12))

        ttk.Label(self.tab_calendar, text="Periods (comma-separated)*").grid(row=2, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(self.tab_calendar, textvariable=self.var_periods, width=80).grid(row=3, column=0, sticky="ew", pady=(0, 12))

        self.tab_calendar.columnconfigure(0, weight=1)

        ttk.Button(self.tab_calendar, text="Apply Calendar Changes", command=self.on_apply_calendar).grid(
            row=4, column=0, sticky="w"
        )

        # Constraints tab
        self.tab_constraints = ttk.Frame(nb, padding=12)
        nb.add(self.tab_constraints, text="Constraints")

        self.var_min_classes_global = tk.StringVar(
            value=str((self._data.get("constraints", {}) or {}).get("min_classes_per_week", ""))
        )

        ttk.Label(self.tab_constraints, text="Min classes per week (global; blank to omit)").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        ttk.Entry(self.tab_constraints, textvariable=self.var_min_classes_global, width=20).grid(
            row=1, column=0, sticky="w", pady=(0, 12)
        )

        ttk.Separator(self.tab_constraints).grid(row=2, column=0, sticky="ew", pady=8)

        ttk.Label(self.tab_constraints, text="Max sessions per day by tag").grid(row=3, column=0, sticky="w", pady=(0, 6))

        self.tags_tree = ttk.Treeview(self.tab_constraints, columns=("tag", "limit"), show="headings", height=10)
        self.tags_tree.heading("tag", text="Tag")
        self.tags_tree.heading("limit", text="Max/day")
        self.tags_tree.column("tag", width=260, anchor="w")
        self.tags_tree.column("limit", width=120, anchor="center")
        self.tags_tree.grid(row=4, column=0, sticky="nsew")

        tag_btns = ttk.Frame(self.tab_constraints)
        tag_btns.grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Button(tag_btns, text="Add Tag Limit", command=self.on_add_tag_limit).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(tag_btns, text="Edit", command=self.on_edit_tag_limit).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(tag_btns, text="Remove", command=self.on_remove_tag_limit).grid(row=0, column=2)

        ttk.Button(self.tab_constraints, text="Apply Constraints Changes", command=self.on_apply_constraints).grid(
            row=6, column=0, sticky="w", pady=(12, 0)
        )

        self.tab_constraints.columnconfigure(0, weight=1)
        self.tab_constraints.rowconfigure(4, weight=1)

        # Classes tab
        self.tab_classes = ttk.Frame(nb, padding=12)
        nb.add(self.tab_classes, text="Classes & Subjects")

        left = ttk.Frame(self.tab_classes)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 12))

        ttk.Label(left, text="Classes").grid(row=0, column=0, sticky="w")
        self.classes_list = tk.Listbox(left, height=18, width=28)
        self.classes_list.grid(row=1, column=0, sticky="nsw", pady=(6, 8))
        self.classes_list.bind("<<ListboxSelect>>", lambda _e: self._on_class_selection_changed())

        class_btns = ttk.Frame(left)
        class_btns.grid(row=2, column=0, sticky="w")
        ttk.Button(class_btns, text="Add", command=self.on_add_class).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(class_btns, text="Rename", command=self.on_rename_class).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(class_btns, text="Remove", command=self.on_remove_class).grid(row=0, column=2)

        right = ttk.Frame(self.tab_classes)
        right.grid(row=0, column=1, sticky="nsew")
        self.tab_classes.columnconfigure(1, weight=1)
        self.tab_classes.rowconfigure(0, weight=1)

        # Selected class details (including per-class min override constraint)
        details = ttk.LabelFrame(right, text="Selected class", padding=10)
        details.pack(fill="x", padx=0, pady=(0, 10))

        self.var_selected_class_name = tk.StringVar(value="-")
        self.var_min_classes_by_class = tk.StringVar(value="")

        ttk.Label(details, text="Name:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Label(details, textvariable=self.var_selected_class_name).grid(row=0, column=1, sticky="w", pady=2)

        ttk.Label(details, text="Min classes/week override (blank = use global)").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 2)
        )
        ttk.Entry(details, textvariable=self.var_min_classes_by_class, width=20).grid(
            row=2, column=0, sticky="w", pady=(0, 2)
        )
        ttk.Button(details, text="Apply to this class", command=self.on_apply_min_by_class).grid(
            row=2, column=1, sticky="w", padx=(12, 0)
        )
        details.columnconfigure(1, weight=1)

        self.sem_nb = ttk.Notebook(right)
        self.sem_nb.pack(fill="both", expand=True)

        self.subject_trees: Dict[str, ttk.Treeview] = {}
        for sem in SEMESTERS:
            frame = ttk.Frame(self.sem_nb, padding=8)
            self.sem_nb.add(frame, text=sem)
            tree = ttk.Treeview(
                frame,
                columns=("name", "teacher", "spw", "mincp", "maxcp", "tags"),
                show="headings",
                height=14,
            )
            tree.heading("name", text="Subject")
            tree.heading("teacher", text="Teacher")
            tree.heading("spw", text="Sessions/wk")
            tree.heading("mincp", text="Min contig")
            tree.heading("maxcp", text="Max contig")
            tree.heading("tags", text="Tags")
            tree.column("name", width=220, anchor="w")
            tree.column("teacher", width=180, anchor="w")
            tree.column("spw", width=90, anchor="center")
            tree.column("mincp", width=90, anchor="center")
            tree.column("maxcp", width=90, anchor="center")
            tree.column("tags", width=220, anchor="w")
            tree.grid(row=0, column=0, sticky="nsew")
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)

            btns = ttk.Frame(frame)
            btns.grid(row=1, column=0, sticky="w", pady=(8, 0))
            ttk.Button(btns, text="Add Subject", command=lambda s=sem: self.on_add_subject(s)).grid(
                row=0, column=0, padx=(0, 8)
            )
            ttk.Button(btns, text="Edit", command=lambda s=sem: self.on_edit_subject(s)).grid(
                row=0, column=1, padx=(0, 8)
            )
            ttk.Button(btns, text="Remove", command=lambda s=sem: self.on_remove_subject(s)).grid(row=0, column=2)

            self.subject_trees[sem] = tree

        # Initial paint
        self._refresh_all_from_data()

    # -----------------------------
    # File actions
    # -----------------------------
    def on_new(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        self._data = self._new_data()
        self._current_path = None
        self._refresh_all_from_data()
        self._set_dirty(False)

    def on_open(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        path = filedialog.askopenfilename(
            parent=self,
            title="Open timetable JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.load_json(path)
        except Exception as e:
            messagebox.showerror("Failed to open", str(e), parent=self)

    def on_save(self) -> None:
        if self._current_path:
            try:
                self.save_json(self._current_path)
                self._set_dirty(False)
            except Exception as e:
                messagebox.showerror("Save failed", str(e), parent=self)
        else:
            self.on_save_as()

    def on_save_as(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save timetable JSON as",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.save_json(path)
            self._current_path = path
            self._set_dirty(False)
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)

    def on_exit(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        self.destroy()

    def _confirm_discard_if_dirty(self) -> bool:
        if not self._dirty:
            return True
        return messagebox.askyesno("Unsaved changes", "You have unsaved changes. Discard them?", parent=self)

    # -----------------------------
    # Data IO
    # -----------------------------
    def load_json(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._validate_loaded_shape(data)
        self._data = data
        self._current_path = path
        self._refresh_all_from_data()
        self._set_dirty(False)

    def save_json(self, path: str) -> None:
        # Pull from UI into data and validate
        self.on_apply_calendar(silent=True)
        self.on_apply_constraints(silent=True)
        self._validate_for_save(self._data)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def _validate_loaded_shape(self, data: Any) -> None:
        if not isinstance(data, dict):
            raise ValueError("Root JSON must be an object.")
        if "calendar" not in data or not isinstance(data["calendar"], dict):
            raise ValueError("JSON must contain 'calendar' object.")
        cal = data["calendar"]
        if not isinstance(cal.get("days"), list) or not cal.get("days"):
            raise ValueError("'calendar.days' must be a non-empty array.")
        if not isinstance(cal.get("periods"), list) or not cal.get("periods"):
            raise ValueError("'calendar.periods' must be a non-empty array.")
        if "classes" not in data or not isinstance(data["classes"], list):
            raise ValueError("JSON must contain 'classes' array.")

        # Light validation; full validation is done on save.

    def _validate_for_save(self, data: Dict[str, Any]) -> None:
        cal = data.get("calendar", {})
        days = cal.get("days", [])
        periods = cal.get("periods", [])
        if not isinstance(days, list) or not days:
            raise ValueError("calendar.days must be a non-empty array.")
        if not isinstance(periods, list) or not periods:
            raise ValueError("calendar.periods must be a non-empty array.")

        classes = data.get("classes", [])
        if not isinstance(classes, list) or not classes:
            raise ValueError("You must define at least one class.")

        # Ensure unique class names
        names = [c.get("name") for c in classes]
        if any((not isinstance(n, str) or not n.strip()) for n in names):
            raise ValueError("Each class must have a non-empty name.")
        if len({n.strip() for n in names}) != len(names):
            raise ValueError("Class names must be unique.")

        for c in classes:
            semesters = c.get("semesters", {})
            if not isinstance(semesters, dict):
                raise ValueError(f"Class '{c.get('name')}' semesters must be an object.")
            for sem in SEMESTERS:
                if sem not in semesters:
                    raise ValueError(f"Class '{c.get('name')}' must define semester '{sem}'.")
                sem_obj = semesters.get(sem, {})
                subjects = sem_obj.get("subjects", [])
                if not isinstance(subjects, list) or not subjects:
                    raise ValueError(f"Class '{c.get('name')}' semester '{sem}' must have at least one subject.")
                for s in subjects:
                    if not isinstance(s, dict):
                        raise ValueError(f"Invalid subject entry in class '{c.get('name')}' {sem}.")
                    if not (s.get("name") and s.get("teacher")):
                        raise ValueError(f"Each subject must have name and teacher (class '{c.get('name')}' {sem}).")
                    spw = s.get("sessions_per_week")
                    if not isinstance(spw, int) or spw <= 0:
                        raise ValueError(
                            f"sessions_per_week must be a positive int for subject '{s.get('name')}' (class '{c.get('name')}' {sem})."
                        )
                    min_cp = int(s.get("min_contiguous_periods", 1))
                    max_cp = int(s.get("max_contiguous_periods", min_cp))
                    if min_cp <= 0 or max_cp <= 0 or min_cp > max_cp:
                        raise ValueError(
                            f"Invalid contiguous period bounds for subject '{s.get('name')}' (class '{c.get('name')}' {sem})."
                        )
                    if min_cp > len(periods) or max_cp > len(periods):
                        raise ValueError(
                            f"Subject '{s.get('name')}' in class '{c.get('name')}' {sem} has contiguous periods > periods/day."
                        )

    # -----------------------------
    # Refresh UI from data
    # -----------------------------
    def _refresh_all_from_data(self) -> None:
        # Calendar
        cal = self._data.get("calendar", {}) or {}
        self.var_days.set(_format_csv_list(list(cal.get("days") or [])))
        self.var_periods.set(_format_csv_list(list(cal.get("periods") or [])))

        # Constraints
        constraints = self._data.get("constraints", {}) or {}
        gmin = constraints.get("min_classes_per_week", "")
        self.var_min_classes_global.set("" if gmin is None else str(gmin))

        self._refresh_tag_limits_tree()
        self._refresh_classes_list()
        self._refresh_subjects_view()
        self._refresh_selected_class_details()

        self._set_dirty(False)

    def _refresh_tag_limits_tree(self) -> None:
        for iid in self.tags_tree.get_children():
            self.tags_tree.delete(iid)
        constraints = self._data.get("constraints", {}) or {}
        by_tag = constraints.get("max_sessions_per_day_by_tag", {}) or {}
        if isinstance(by_tag, dict):
            for tag in sorted(by_tag.keys()):
                self.tags_tree.insert("", "end", values=(tag, by_tag[tag]))

    def _refresh_classes_list(self) -> None:
        self.classes_list.delete(0, tk.END)
        for c in self._data.get("classes", []) or []:
            self.classes_list.insert(tk.END, c.get("name", ""))

    def _selected_class_index(self) -> Optional[int]:
        sel = self.classes_list.curselection()
        if not sel:
            return None
        return int(sel[0])

    def _get_selected_class(self) -> Optional[Dict[str, Any]]:
        idx = self._selected_class_index()
        if idx is None:
            return None
        classes = self._data.get("classes", []) or []
        if idx < 0 or idx >= len(classes):
            return None
        return classes[idx]

    def _refresh_subjects_view(self) -> None:
        # Clear trees
        for sem in SEMESTERS:
            tree = self.subject_trees[sem]
            for iid in tree.get_children():
                tree.delete(iid)

        c = self._get_selected_class()
        if not c:
            self._last_selected_class_name = None
            self._refresh_selected_class_details()
            return
        self._last_selected_class_name = str(c.get("name") or "")
        semesters = c.get("semesters", {}) or {}
        for sem in SEMESTERS:
            subjects = ((semesters.get(sem, {}) or {}).get("subjects", []) or [])
            tree = self.subject_trees[sem]
            for s in subjects:
                row = SubjectRow.from_json(s)
                tree.insert(
                    "",
                    "end",
                    values=(
                        row.name,
                        row.teacher,
                        row.sessions_per_week,
                        row.min_contiguous_periods,
                        row.max_contiguous_periods,
                        _format_csv_list(list(row.tags or [])),
                    ),
                )

        self._refresh_selected_class_details()

    def _on_class_selection_changed(self) -> None:
        # Keep views in sync whenever selection changes.
        self._refresh_subjects_view()

    def _refresh_selected_class_details(self) -> None:
        c = self._get_selected_class()
        if not c:
            self.var_selected_class_name.set("-")
            self.var_min_classes_by_class.set("")
            return
        name = str(c.get("name") or "")
        self.var_selected_class_name.set(name or "-")

        constraints = self._data.get("constraints", {}) or {}
        by_class = constraints.get("min_classes_per_week_by_class", {}) or {}
        if isinstance(by_class, dict) and name in by_class:
            self.var_min_classes_by_class.set(str(by_class.get(name)))
        else:
            self.var_min_classes_by_class.set("")

    def on_apply_min_by_class(self) -> None:
        c = self._get_selected_class()
        if not c:
            messagebox.showwarning("Apply override", "Select a class first.", parent=self)
            return
        name = str(c.get("name") or "").strip()
        if not name:
            messagebox.showerror("Apply override", "Selected class has no name.", parent=self)
            return

        raw = (self.var_min_classes_by_class.get() or "").strip()
        constraints = self._data.setdefault("constraints", {})
        by_class = constraints.setdefault("min_classes_per_week_by_class", {})
        if not isinstance(by_class, dict):
            constraints["min_classes_per_week_by_class"] = {}
            by_class = constraints["min_classes_per_week_by_class"]

        if raw == "":
            if name in by_class:
                del by_class[name]
        else:
            try:
                val = int(raw)
            except Exception:
                messagebox.showerror("Invalid value", "Override must be a non-negative integer (or blank).", parent=self)
                return
            if val < 0:
                messagebox.showerror("Invalid value", "Override must be a non-negative integer (or blank).", parent=self)
                return
            by_class[name] = val

        # If the map is now empty, remove it to keep output tidy.
        if isinstance(by_class, dict) and not by_class:
            constraints.pop("min_classes_per_week_by_class", None)

        self._set_dirty(True)
        messagebox.showinfo("Applied", f"Saved min-classes/week override for '{name}'.", parent=self)

    # -----------------------------
    # Calendar actions
    # -----------------------------
    def on_apply_calendar(self, silent: bool = False) -> None:
        try:
            days = _parse_csv_list(self.var_days.get())
            periods = _parse_csv_list(self.var_periods.get())
            if not days:
                raise ValueError("Days cannot be empty.")
            if not periods:
                raise ValueError("Periods cannot be empty.")
            self._data.setdefault("calendar", {})
            self._data["calendar"]["days"] = days
            self._data["calendar"]["periods"] = periods
            self._set_dirty(True)
            if not silent:
                messagebox.showinfo("Calendar updated", "Calendar values applied.", parent=self)
        except Exception as e:
            if silent:
                raise
            messagebox.showerror("Invalid calendar", str(e), parent=self)

    # -----------------------------
    # Constraints actions
    # -----------------------------
    def on_add_tag_limit(self) -> None:
        dlg = TagLimitDialog(self, title="Add tag limit")
        if dlg.result is None:
            return
        tag, limit = dlg.result
        constraints = self._data.setdefault("constraints", {})
        by_tag = constraints.setdefault("max_sessions_per_day_by_tag", {})
        if not isinstance(by_tag, dict):
            constraints["max_sessions_per_day_by_tag"] = {}
            by_tag = constraints["max_sessions_per_day_by_tag"]
        by_tag[tag] = limit
        self._refresh_tag_limits_tree()
        self._set_dirty(True)

    def _selected_tag_iid(self) -> Optional[str]:
        sel = self.tags_tree.selection()
        if not sel:
            return None
        return sel[0]

    def on_edit_tag_limit(self) -> None:
        iid = self._selected_tag_iid()
        if iid is None:
            messagebox.showwarning("Edit tag limit", "Select a tag constraint first.", parent=self)
            return
        tag, limit = self.tags_tree.item(iid, "values")
        dlg = TagLimitDialog(self, title="Edit tag limit", initial=(str(tag), int(limit)))
        if dlg.result is None:
            return
        new_tag, new_limit = dlg.result
        constraints = self._data.setdefault("constraints", {})
        by_tag = constraints.setdefault("max_sessions_per_day_by_tag", {})
        if not isinstance(by_tag, dict):
            constraints["max_sessions_per_day_by_tag"] = {}
            by_tag = constraints["max_sessions_per_day_by_tag"]
        # If tag renamed, remove old.
        if new_tag != tag and str(tag) in by_tag:
            del by_tag[str(tag)]
        by_tag[new_tag] = new_limit
        self._refresh_tag_limits_tree()
        self._set_dirty(True)

    def on_remove_tag_limit(self) -> None:
        iid = self._selected_tag_iid()
        if iid is None:
            messagebox.showwarning("Remove tag limit", "Select a tag constraint first.", parent=self)
            return
        tag, _limit = self.tags_tree.item(iid, "values")
        if not messagebox.askyesno("Remove tag limit", f"Remove tag constraint '{tag}'?", parent=self):
            return
        constraints = self._data.setdefault("constraints", {})
        by_tag = constraints.setdefault("max_sessions_per_day_by_tag", {})
        if isinstance(by_tag, dict) and str(tag) in by_tag:
            del by_tag[str(tag)]
        self._refresh_tag_limits_tree()
        self._set_dirty(True)

    def on_apply_constraints(self, silent: bool = False) -> None:
        try:
            constraints = self._data.setdefault("constraints", {})

            # Global min_classes_per_week
            raw = (self.var_min_classes_global.get() or "").strip()
            if raw == "":
                constraints.pop("min_classes_per_week", None)
            else:
                val = int(raw)
                if val < 0:
                    raise ValueError("min_classes_per_week must be a non-negative integer (or blank).")
                constraints["min_classes_per_week"] = val

            # Ensure max_sessions_per_day_by_tag exists
            if "max_sessions_per_day_by_tag" not in constraints or not isinstance(
                constraints.get("max_sessions_per_day_by_tag"), dict
            ):
                constraints["max_sessions_per_day_by_tag"] = {}

            self._set_dirty(True)
            if not silent:
                messagebox.showinfo("Constraints updated", "Constraint values applied.", parent=self)
        except Exception as e:
            if silent:
                raise
            messagebox.showerror("Invalid constraints", str(e), parent=self)

    # -----------------------------
    # Class actions
    # -----------------------------
    def on_add_class(self) -> None:
        name = simple_prompt(self, title="Add class", prompt="Class name*")
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showerror("Invalid class", "Class name is required.", parent=self)
            return
        if any((c.get("name") == name) for c in (self._data.get("classes") or [])):
            messagebox.showerror("Invalid class", f"Class '{name}' already exists.", parent=self)
            return

        cobj: Dict[str, Any] = {"name": name, "semesters": {}}
        for sem in SEMESTERS:
            cobj["semesters"][sem] = {"subjects": []}
        self._data.setdefault("classes", []).append(cobj)
        self._refresh_classes_list()
        # Select new class
        self.classes_list.selection_clear(0, tk.END)
        self.classes_list.selection_set(tk.END)
        self._refresh_subjects_view()
        self._set_dirty(True)

    def on_rename_class(self) -> None:
        idx = self._selected_class_index()
        c = self._get_selected_class()
        if idx is None or c is None:
            messagebox.showwarning("Rename class", "Select a class first.", parent=self)
            return
        old = str(c.get("name") or "")
        name = simple_prompt(self, title="Rename class", prompt="New class name*", initial=old)
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showerror("Invalid class", "Class name is required.", parent=self)
            return
        if name != old and any((cc.get("name") == name) for cc in (self._data.get("classes") or [])):
            messagebox.showerror("Invalid class", f"Class '{name}' already exists.", parent=self)
            return
        c["name"] = name

        # If constraints has min_classes_per_week_by_class keyed by old name, migrate key.
        constraints = self._data.get("constraints", {}) or {}
        by_class = constraints.get("min_classes_per_week_by_class", {}) or {}
        if isinstance(by_class, dict) and old in by_class and name != old:
            by_class[name] = by_class.pop(old)

        self._refresh_classes_list()
        self.classes_list.selection_clear(0, tk.END)
        self.classes_list.selection_set(idx)
        self._set_dirty(True)

    def on_remove_class(self) -> None:
        idx = self._selected_class_index()
        c = self._get_selected_class()
        if idx is None or c is None:
            messagebox.showwarning("Remove class", "Select a class first.", parent=self)
            return
        name = str(c.get("name") or "")
        if not messagebox.askyesno("Remove class", f"Remove class '{name}'?", parent=self):
            return
        classes = self._data.get("classes", []) or []
        del classes[idx]

        # Remove by-class constraint if present.
        constraints = self._data.get("constraints", {}) or {}
        by_class = constraints.get("min_classes_per_week_by_class", {}) or {}
        if isinstance(by_class, dict) and name in by_class:
            del by_class[name]

        self._refresh_classes_list()
        self._refresh_subjects_view()
        self._set_dirty(True)

    # -----------------------------
    # Subject actions
    # -----------------------------
    def _selected_subject_index(self, sem: str) -> Optional[int]:
        tree = self.subject_trees[sem]
        sel = tree.selection()
        if not sel:
            return None
        return tree.index(sel[0])

    def on_add_subject(self, sem: str) -> None:
        c = self._get_selected_class()
        if not c:
            messagebox.showwarning("Add subject", "Select a class first.", parent=self)
            return
        dlg = SubjectDialog(self, title=f"Add subject ({sem})")
        if dlg.result is None:
            return
        srow = dlg.result
        semesters = c.setdefault("semesters", {})
        sem_obj = semesters.setdefault(sem, {"subjects": []})
        subjects = sem_obj.setdefault("subjects", [])
        if any((subj.get("name") == srow.name) for subj in subjects):
            messagebox.showerror("Duplicate subject", f"Subject '{srow.name}' already exists in {c.get('name')} {sem}.", parent=self)
            return
        subjects.append(srow.to_json())
        self._refresh_subjects_view()
        self._set_dirty(True)

    def on_edit_subject(self, sem: str) -> None:
        c = self._get_selected_class()
        if not c:
            messagebox.showwarning("Edit subject", "Select a class first.", parent=self)
            return
        idx = self._selected_subject_index(sem)
        if idx is None:
            messagebox.showwarning("Edit subject", "Select a subject first.", parent=self)
            return
        subjects = ((c.get("semesters", {}).get(sem, {}) or {}).get("subjects", []) or [])
        if idx < 0 or idx >= len(subjects):
            return
        existing = subjects[idx]
        dlg = SubjectDialog(self, title=f"Edit subject ({sem})", initial=SubjectRow.from_json(existing))
        if dlg.result is None:
            return
        updated = dlg.result.to_json()

        # Ensure unique by name within class+semester
        new_name = updated.get("name")
        for j, subj in enumerate(subjects):
            if j == idx:
                continue
            if subj.get("name") == new_name:
                messagebox.showerror(
                    "Duplicate subject",
                    f"Subject '{new_name}' already exists in {c.get('name')} {sem}.",
                    parent=self,
                )
                return
        subjects[idx] = updated
        self._refresh_subjects_view()
        self._set_dirty(True)

    def on_remove_subject(self, sem: str) -> None:
        c = self._get_selected_class()
        if not c:
            messagebox.showwarning("Remove subject", "Select a class first.", parent=self)
            return
        idx = self._selected_subject_index(sem)
        if idx is None:
            messagebox.showwarning("Remove subject", "Select a subject first.", parent=self)
            return
        subjects = ((c.get("semesters", {}).get(sem, {}) or {}).get("subjects", []) or [])
        if idx < 0 or idx >= len(subjects):
            return
        name = str(subjects[idx].get("name") or "")
        if not messagebox.askyesno("Remove subject", f"Remove subject '{name}' from {c.get('name')} {sem}?", parent=self):
            return
        del subjects[idx]
        self._refresh_subjects_view()
        self._set_dirty(True)


def simple_prompt(master: tk.Misc, *, title: str, prompt: str, initial: str = "") -> Optional[str]:
    dlg = tk.Toplevel(master)
    dlg.title(title)
    dlg.resizable(False, False)
    dlg.transient(master)
    dlg.grab_set()

    var = tk.StringVar(value=initial)

    frm = ttk.Frame(dlg, padding=12)
    frm.grid(row=0, column=0, sticky="nsew")
    ttk.Label(frm, text=prompt).grid(row=0, column=0, sticky="w", pady=(0, 6))
    ent = ttk.Entry(frm, textvariable=var, width=40)
    ent.grid(row=1, column=0, sticky="ew")
    ent.focus_set()
    ent.selection_range(0, tk.END)

    out: Dict[str, Optional[str]] = {"val": None}

    def ok() -> None:
        out["val"] = var.get()
        dlg.destroy()

    def cancel() -> None:
        out["val"] = None
        dlg.destroy()

    btns = ttk.Frame(frm)
    btns.grid(row=2, column=0, sticky="e", pady=(10, 0))
    ttk.Button(btns, text="Cancel", command=cancel).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(btns, text="OK", command=ok).grid(row=0, column=1)

    dlg.bind("<Escape>", lambda _e: cancel())
    dlg.bind("<Return>", lambda _e: ok())

    master.wait_window(dlg)
    return out["val"]


def main() -> None:
    parser = argparse.ArgumentParser(description="GUI editor for timetable_input JSON used by timetable_solver.py")
    parser.add_argument("--open", dest="open_path", default=None, help="Open an existing JSON on startup.")
    parser.add_argument(
        "--diagnose-tk",
        action="store_true",
        help="Print Tk/Tcl diagnostics and attempt to create/destroy a root window, then exit.",
    )
    args = parser.parse_args()

    if args.diagnose_tk:
        print(f"executable: {sys.executable}")
        print(f"version:    {sys.version.replace(os.linesep, ' ')}")
        print(f"tkinter:    imported OK")
        print(f"TclVersion: {getattr(tk, 'TclVersion', None)}")
        print(f"TkVersion:  {getattr(tk, 'TkVersion', None)}")
        try:
            root = tk.Tk()
            root.withdraw()
            root.update_idletasks()
            root.destroy()
            print("Tk():       root window create/destroy OK")
        except Exception as e:
            print(f"Tk():       FAILED: {e!r}")
            raise
        return

    app = TimetableEditorApp(open_path=args.open_path)
    app.mainloop()


if __name__ == "__main__":
    main()


