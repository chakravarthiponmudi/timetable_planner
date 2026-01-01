## Time Table Scheduler (OR-Tools)

This repo contains a simple **college timetable generator** built with **Google OR-Tools CP-SAT**.

### What it supports (currently)

- Multiple classes (e.g., `BSc_I`, `BSc_II`, `BSc_III`, `MSc_I`, `MSc_II`)
- Two semesters per class (`S1`, `S2`) — you solve **one semester at a time**
- Weekly load per subject in **periods** (`periods_per_week`)
- Practical/lab blocks with **contiguous periods** (e.g., 2–3 periods continuous)
- Teacher collision constraint: **a teacher cannot teach two classes in the same slot**
- No room constraints (as requested)
 - Optional minimum classes-per-week constraint

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run (using the included sample input)

Solve Semester 1:

```bash
python timetable_solver.py --input timetable_input.sample.json --semester S1
```

Solve Semester 2:

```bash
python timetable_solver.py --input timetable_input.sample.json --semester S2
```

Note: if a class does not define the requested semester (e.g. it only has `S1`), it will be **skipped** for that run.

Optional: also print timetables per teacher:

```bash
python timetable_solver.py --input timetable_input.sample.json --semester S1 --print_teachers
```

### GUI editor (Tkinter)

You can create/edit the input JSON using a simple GUI that maps 1:1 to the schema expected by `timetable_solver.py`.

Run:

```bash
python3 timetable_gui.py
```

Open an existing JSON on startup:

```bash
python3 timetable_gui.py --open timetable_input.sample.json
```

Then use **File → Save / Save As** to write a JSON file in the same shape as `timetable_input.sample.json`.

### GUI editor (recommended): Streamlit (no Tk)

If you can’t use Tkinter on your machine, run the Streamlit editor instead:

```bash
source .venv/bin/activate
streamlit run timetable_web_gui.py
```

This opens a local browser UI where you can **load/edit** the timetable JSON and **download** an output file.

### Troubleshooting (macOS): Tkinter aborts on `tk.Tk()`

If you see an abort like:

- `macOS ... required, have instead ...`
- and/or a crash report mentioning `TkpInit` / `Tk.framework`

This is usually caused by the **Apple Command Line Tools Python** (`/Library/Developer/CommandLineTools/...`) using the **system Tk 8.5**, which can abort during Tk initialization on some macOS builds.

**Fix (recommended): use a different Python distribution (python.org or Homebrew) and recreate `.venv`.**

1) Install a newer Python (example: python.org Python 3.12/3.13) and ensure it’s first on PATH.
2) Recreate the venv from that Python:

```bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3) Verify Tk can create a root window:

```bash
python3 -c "import tkinter as tk; r=tk.Tk(); r.withdraw(); r.destroy(); print('Tk root OK')"
```

### Troubleshooting (macOS): `ModuleNotFoundError: No module named '_tkinter'`

If you see:

- `ModuleNotFoundError: No module named '_tkinter'`

then your current Python build was compiled **without Tk support**. This can happen with some Homebrew Python setups.

**Fix options:**

- **Recommended**: install the official **python.org** macOS Python (it bundles a working Tk), then recreate `.venv` from that interpreter.
- **Alternative (advanced)**: build Python via `pyenv` against Homebrew `tcl-tk`, then recreate `.venv`.

Either way, `pip install` will not fix `_tkinter` because it’s a compiled module that must be present in the Python build.

### Input format (JSON)

See `timetable_input.sample.json`.

At a minimum:

- `calendar.days`: `["Mon", "Tue", ...]`
- `calendar.periods`: `["P1", "P2", ...]`
- `classes[].name`
- `classes[].semesters.S1.subjects[]` and `classes[].semesters.S2.subjects[]`
  - `name` (subject name)
  - `teacher` (teacher/prof name)
  - `periods_per_week` (positive integer)
  - `min_contiguous_periods` (optional, default `1`)
  - `max_contiguous_periods` (optional, default `min_contiguous_periods`)

Optional constraints:

- `constraints.min_classes_per_week`: non-negative int, applies to all classes
- `constraints.min_classes_per_week_by_class`: map of class name -> non-negative int (overrides global for those classes)
- `constraints.max_periods_per_day_by_tag`: map of tag -> non-negative int (limits how many *periods* with that tag can occur per class per day)

Optional subject fields:

- `tags`: array of strings (e.g. `["practical"]`)
- `allowed_starts`: array of `{ "day": "Mon", "period": "P2" }` objects (restricts which day/period a session may start)
- `fixed_sessions`: array of `{ "day": "Mon", "period": "P2", "duration": 1 }` objects
  - If `duration` is omitted, the solver will force a session to start there with any duration in `[min_contiguous_periods, max_contiguous_periods]`.
  - If `day` is omitted, the solver will force a session to start at that `period` on **exactly one** day of the week.

Optional class/semester fields:

- `blocked_periods`: array of `{ "day": "Tue", "period": "P1" }` objects (disallows any class in that slot)


