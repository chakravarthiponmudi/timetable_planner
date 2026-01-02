"""
Streamlit-based GUI editor for the timetable input JSON consumed by `timetable_solver.py`.

Why Streamlit?
- Avoids Tk/Tcl runtime issues on macOS
- Runs as a local web app: `streamlit run timetable_web_gui.py`

This editor maps 1:1 to the JSON schema used by the solver.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import hashlib
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from timetable_schema import TimetableInput


SEMESTERS: Tuple[str, ...] = ("S1", "S2")


def _parse_csv_list(s: str) -> List[str]:
    parts = [(p or "").strip() for p in (s or "").split(",")]
    return [p for p in parts if p]


def _csv(items: List[str]) -> str:
    return ", ".join(items)


def new_data() -> Dict[str, Any]:
    return {
        "constraints": {
            "max_periods_per_day_by_tag": {},
            "min_classes_per_week_by_class": {},
        },
        "calendar": {"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "periods": ["P1", "P2", "P3", "P4", "P5"]},
        "classes": [],
    }


def _ensure_class_shape(c: Dict[str, Any]) -> None:
    c.setdefault("semesters", {})
    # Do NOT auto-create both semesters. The solver supports one-semester classes by omitting the other semester.
    # Ensure any existing semesters have a subjects array.
    semesters = c.get("semesters", {}) or {}
    if isinstance(semesters, dict):
        for sem, sem_obj in semesters.items():
            if isinstance(sem_obj, dict):
                sem_obj.setdefault("subjects", [])
                sem_obj.setdefault("blocked_periods", [])


def _subject_names(subjects: List[Dict[str, Any]]) -> List[str]:
    return [s.get("name") for s in subjects if isinstance(s, dict) and s.get("name")]


def _find_subject(subjects: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    for s in subjects:
        if s.get("name") == name:
            return s
    return None


def _normalize_tags_csv(tags_csv: str) -> List[str]:
    return _parse_csv_list(tags_csv or "")


def _fixed_sessions_editor(
    *,
    key_prefix: str,
    current: List[Dict[str, Any]],
    days: List[str],
    periods: List[str],
) -> List[Dict[str, Any]]:
    st.caption("Fixed sessions: day optional; period required; duration optional.")
    rows = []
    for fs in current or []:
        if isinstance(fs, dict):
            rows.append({"day": fs.get("day", ""), "period": fs.get("period", ""), "duration": fs.get("duration", "")})
    # If empty, seed a blank row so Streamlit can render the columns for editing.
    if not rows:
        rows = [{"day": "", "period": "", "duration": ""}]
    edited = st.data_editor(
        rows,
        num_rows="dynamic",
        use_container_width=True,
        key=f"{key_prefix}__fixed",
        column_config={
            "day": st.column_config.SelectboxColumn("day (optional)", options=[""] + list(days)),
            "period": st.column_config.SelectboxColumn("period*", options=[""] + list(periods)),
            "duration": st.column_config.NumberColumn("duration (optional)", min_value=1, step=1),
        },
    )
    out: List[Dict[str, Any]] = []
    for r in edited or []:
        day = (r.get("day") or "").strip()
        period = (r.get("period") or "").strip()
        duration = r.get("duration")
        if not period:
            continue
        fs: Dict[str, Any] = {"period": period}
        if day:
            fs["day"] = day
        if isinstance(duration, int) and duration > 0:
            fs["duration"] = int(duration)
        out.append(fs)
    return out


def _allowed_starts_editor(
    *,
    key_prefix: str,
    current: List[Dict[str, Any]],
    days: List[str],
    periods: List[str],
) -> List[Dict[str, Any]]:
    st.caption("Allowed starts: if non-empty, subject sessions may only start at these day/period pairs.")
    rows = []
    for a in current or []:
        if isinstance(a, dict):
            rows.append({"day": a.get("day", ""), "period": a.get("period", "")})
    # If empty, seed a blank row so Streamlit can render the columns for editing.
    if not rows:
        rows = [{"day": "", "period": ""}]
    edited = st.data_editor(
        rows,
        num_rows="dynamic",
        use_container_width=True,
        key=f"{key_prefix}__allowed",
        column_config={
            "day": st.column_config.SelectboxColumn("day*", options=[""] + list(days)),
            "period": st.column_config.SelectboxColumn("period*", options=[""] + list(periods)),
        },
    )
    out: List[Dict[str, Any]] = []
    for r in edited or []:
        day = (r.get("day") or "").strip()
        period = (r.get("period") or "").strip()
        if not day or not period:
            continue
        out.append({"day": day, "period": period})
    return out


def _blocked_periods_editor(
    *,
    key_prefix: str,
    current: List[Dict[str, Any]],
    days: List[str],
    periods: List[str],
) -> List[Dict[str, Any]]:
    st.caption("Blocked periods: disallow any class in these day/period slots.")
    rows = []
    for bp in current or []:
        if isinstance(bp, dict):
            rows.append({"day": bp.get("day", ""), "period": bp.get("period", "")})
    edited = st.data_editor(
        rows,
        num_rows="dynamic",
        use_container_width=True,
        key=f"{key_prefix}__blocked",
        column_config={
            "day": st.column_config.SelectboxColumn("day*", options=list(days)),
            "period": st.column_config.SelectboxColumn("period*", options=list(periods)),
        },
    )
    out: List[Dict[str, Any]] = []
    for r in edited or []:
        day = (r.get("day") or "").strip()
        period = (r.get("period") or "").strip()
        if not day or not period:
            continue
        out.append({"day": day, "period": period})
    return out


def _validate_for_save(data: Dict[str, Any]) -> None:
    cal = data.get("calendar", {}) or {}
    days = cal.get("days", [])
    periods = cal.get("periods", [])
    if not isinstance(days, list) or not days:
        raise ValueError("calendar.days must be a non-empty array.")
    if not isinstance(periods, list) or not periods:
        raise ValueError("calendar.periods must be a non-empty array.")

    day_set = {d for d in days if isinstance(d, str)}
    period_set = {p for p in periods if isinstance(p, str)}

    classes = data.get("classes", [])
    if not isinstance(classes, list) or not classes:
        raise ValueError("You must define at least one class.")

    names = [c.get("name") for c in classes]
    if any((not isinstance(n, str) or not n.strip()) for n in names):
        raise ValueError("Each class must have a non-empty name.")
    if len({n.strip() for n in names}) != len(names):
        raise ValueError("Class names must be unique.")

    for c in classes:
        _ensure_class_shape(c)
        semesters = c.get("semesters", {}) or {}
        if not isinstance(semesters, dict) or not semesters:
            raise ValueError(f"Class '{c.get('name')}' must define at least one semester.")

        for sem, sem_obj in semesters.items():
            if not isinstance(sem, str) or not sem.strip():
                raise ValueError(f"Class '{c.get('name')}' has an invalid semester key.")
            if sem not in SEMESTERS:
                raise ValueError(f"Unsupported semester key '{sem}' in class '{c.get('name')}'. Use one of: {', '.join(SEMESTERS)}.")
            subjects = ((sem_obj or {}).get("subjects", []) or [])
            if not isinstance(subjects, list) or not subjects:
                raise ValueError(f"Class '{c.get('name')}' semester '{sem}' must have at least one subject.")

            blocked = (sem_obj or {}).get("blocked_periods", []) or []
            if not isinstance(blocked, list):
                raise ValueError(f"Class '{c.get('name')}' semester '{sem}': blocked_periods must be an array.")
            for bp in blocked:
                if not isinstance(bp, dict):
                    raise ValueError(f"Class '{c.get('name')}' semester '{sem}': blocked_periods entries must be objects.")
                day = bp.get("day")
                period = bp.get("period")
                if not isinstance(day, str) or not day.strip() or not isinstance(period, str) or not period.strip():
                    raise ValueError(f"Class '{c.get('name')}' semester '{sem}': blocked_periods require day+period.")
                if day not in day_set:
                    raise ValueError(f"Class '{c.get('name')}' semester '{sem}': blocked_periods day '{day}' not in calendar.days.")
                if period not in period_set:
                    raise ValueError(f"Class '{c.get('name')}' semester '{sem}': blocked_periods period '{period}' not in calendar.periods.")

            for s in subjects:
                if not isinstance(s, dict):
                    raise ValueError(f"Invalid subject entry in class '{c.get('name')}' {sem}.")
                teachers_list = s.get("teachers", []) or []
                if not (s.get("name") and isinstance(teachers_list, list) and any(isinstance(x, str) and x.strip() for x in teachers_list)):
                    raise ValueError(f"Each subject must have name and at least one teacher in 'teachers' (class '{c.get('name')}' {sem}).")
                ppw = s.get("periods_per_week", s.get("sessions_per_week"))
                if not isinstance(ppw, int) or ppw <= 0:
                    raise ValueError(
                        f"periods_per_week must be a positive int for subject '{s.get('name')}' (class '{c.get('name')}' {sem})."
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

                fixed = s.get("fixed_sessions", []) or []
                if not isinstance(fixed, list):
                    raise ValueError(f"Subject '{s.get('name')}' (class '{c.get('name')}' {sem}): fixed_sessions must be an array.")
                for fs in fixed:
                    if not isinstance(fs, dict):
                        raise ValueError(f"Subject '{s.get('name')}' (class '{c.get('name')}' {sem}): fixed_sessions entries must be objects.")
                    period = fs.get("period")
                    day = fs.get("day", None)
                    dur = fs.get("duration", None)
                    if not isinstance(period, str) or not period.strip():
                        raise ValueError(f"Subject '{s.get('name')}' (class '{c.get('name')}' {sem}): fixed_sessions.period is required.")
                    if period not in period_set:
                        raise ValueError(f"Subject '{s.get('name')}' (class '{c.get('name')}' {sem}): fixed_sessions.period '{period}' not in calendar.periods.")
                    if day is not None:
                        if not isinstance(day, str) or not day.strip():
                            raise ValueError(f"Subject '{s.get('name')}' (class '{c.get('name')}' {sem}): fixed_sessions.day must be non-empty if provided.")
                        if day not in day_set:
                            raise ValueError(f"Subject '{s.get('name')}' (class '{c.get('name')}' {sem}): fixed_sessions.day '{day}' not in calendar.days.")
                    if dur is not None and (not isinstance(dur, int) or dur <= 0):
                        raise ValueError(f"Subject '{s.get('name')}' (class '{c.get('name')}' {sem}): fixed_sessions.duration must be a positive int if provided.")

                allowed = s.get("allowed_starts", []) or []
                if not isinstance(allowed, list):
                    raise ValueError(f"Subject '{s.get('name')}' (class '{c.get('name')}' {sem}): allowed_starts must be an array.")
                for a in allowed:
                    if not isinstance(a, dict):
                        raise ValueError(f"Subject '{s.get('name')}' (class '{c.get('name')}' {sem}): allowed_starts entries must be objects.")
                    day = a.get("day")
                    period = a.get("period")
                    if not isinstance(day, str) or not day.strip() or not isinstance(period, str) or not period.strip():
                        raise ValueError(f"Subject '{s.get('name')}' (class '{c.get('name')}' {sem}): allowed_starts require day+period.")
                    if day not in day_set:
                        raise ValueError(f"Subject '{s.get('name')}' (class '{c.get('name')}' {sem}): allowed_starts day '{day}' not in calendar.days.")
                    if period not in period_set:
                        raise ValueError(f"Subject '{s.get('name')}' (class '{c.get('name')}' {sem}): allowed_starts period '{period}' not in calendar.periods.")


## SubjectDraft removed; UI now supports full edit/update and writes the final schema directly.


def _get_state() -> Dict[str, Any]:
    if "data" not in st.session_state:
        st.session_state["data"] = new_data()
    if "dirty" not in st.session_state:
        st.session_state["dirty"] = False
    if "save_path" not in st.session_state:
        # Default to timetable_input.json if it exists (this is the "editable output" users typically expect).
        # Otherwise fall back to the sample file if present.
        if os.path.exists("timetable_input.json"):
            st.session_state["save_path"] = "timetable_input.json"
        elif os.path.exists("timetable_input.sample.json"):
            st.session_state["save_path"] = "timetable_input.sample.json"
        else:
            st.session_state["save_path"] = "timetable_input.json"
    if "uploaded_sig" not in st.session_state:
        st.session_state["uploaded_sig"] = None
    return st.session_state["data"]


def _autosave_to_disk(data: Dict[str, Any], *, path_override: Optional[str] = None) -> None:
    """
    Always-save behavior: whenever the user clicks a mutating action (Save subject, Apply calendar, etc.),
    we validate and write to the configured save_path.
    """
    path = str(path_override or st.session_state.get("save_path") or "").strip()
    if not path:
        st.error("Save path is empty. Set 'Save path' in the sidebar before editing.")
        return
    try:
        # Use the shared schema for validation and for producing a normalized JSON payload.
        ti = TimetableInput.model_validate(data)
        ti.validate_references()
        payload = json.dumps(ti.to_json_dict(), indent=2, ensure_ascii=False) + "\n"
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload)
        st.session_state["dirty"] = False
        st.success(f"Saved to: {path}")
    except Exception as e:
        st.session_state["dirty"] = True
        st.error(f"Could not save (validation failed): {e}")


def _project_root() -> str:
    # Best-effort: directory where this script lives.
    return os.path.dirname(os.path.abspath(__file__))


def _venv_python() -> str:
    """
    Prefer the repo-local .venv python to match the user's expectation.
    Fall back to current interpreter if .venv isn't present.
    """
    root = _project_root()
    cand = os.path.join(root, ".venv", "bin", "python3")
    if os.path.exists(cand):
        return cand
    cand = os.path.join(root, ".venv", "bin", "python")
    if os.path.exists(cand):
        return cand
    return sys.executable


def _run_solver_cmd(
    *,
    input_path: str,
    semester: str,
    print_teachers: bool,
    time_limit_s: float,
    output_format: str = "text",
) -> Dict[str, Any]:
    root = _project_root()
    py = _venv_python()
    cmd: List[str] = [
        py,
        os.path.join(root, "timetable_solver.py"),
        "--input",
        input_path,
        "--semester",
        semester,
        "--time_limit_s",
        str(float(time_limit_s)),
        "--output_format",
        str(output_format),
    ]
    if print_teachers:
        cmd.append("--print_teachers")

    # Run from project root so relative save_path like timetable_input.json works.
    res = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
    )
    return {
        "cmd": cmd,
        "returncode": res.returncode,
        "stdout": res.stdout or "",
        "stderr": res.stderr or "",
        "python": py,
        "cwd": root,
        "output_format": str(output_format),
    }


def _find_class(data: Dict[str, Any], class_name: str) -> Optional[Dict[str, Any]]:
    for c in data.get("classes", []) or []:
        if c.get("name") == class_name:
            return c
    return None


def _teacher_names(data: Dict[str, Any]) -> List[str]:
    return [t.get("name") for t in (data.get("teachers", []) or []) if isinstance(t, dict) and t.get("name")]


def _find_teacher(data: Dict[str, Any], teacher_name: str) -> Optional[Dict[str, Any]]:
    for t in (data.get("teachers", []) or []):
        if isinstance(t, dict) and t.get("name") == teacher_name:
            return t
    return None


def main() -> None:
    st.set_page_config(page_title="Timetable Input Editor", layout="wide")
    st.title("Timetable Input Editor")
    st.caption("Edits the JSON schema consumed by `timetable_solver.py` and exports a file like `timetable_input.sample.json`.")

    data = _get_state()

    with st.sidebar:
        st.header("File")
        uploaded = st.file_uploader("Open JSON", type=["json"], key="open_json")
        if uploaded is not None:
            # IMPORTANT: Streamlit reruns the script on every interaction, and file_uploader keeps its value.
            # If we blindly reload on every rerun, we wipe user edits and reset dirty back to false.
            # So we only load when the uploaded file content changes.
            raw = uploaded.getvalue()
            sig = (getattr(uploaded, "name", None), len(raw), hashlib.sha256(raw).hexdigest())
            if st.session_state.get("uploaded_sig") != sig:
                try:
                    loaded = json.loads(raw.decode("utf-8"))
                    if not isinstance(loaded, dict):
                        raise ValueError("Root JSON must be an object.")
                    st.session_state["data"] = loaded
                    data = st.session_state["data"]
                    st.session_state["dirty"] = False
                    st.session_state["uploaded_sig"] = sig
                    # Best-effort: default save path to uploaded file name (saved in current working directory).
                    if getattr(uploaded, "name", None):
                        st.session_state["save_path"] = str(uploaded.name)
                    st.success("Loaded JSON into editor.")
                except Exception as e:
                    st.error(f"Failed to load JSON: {e}")

        if st.button("New (reset)"):
            st.session_state["data"] = new_data()
            data = st.session_state["data"]
            st.session_state["dirty"] = True
            st.session_state["uploaded_sig"] = None
            st.success("Reset to new template.")

        st.divider()
        st.subheader("Save / Export")
        try:
            ti_preview = TimetableInput.model_validate(data)
            ti_preview.validate_references()
            payload = json.dumps(ti_preview.to_json_dict(), indent=2, ensure_ascii=False) + "\n"

            st.text_input("Save path (server-side)", key="save_path", help="Example: timetable_input.json")
            st.caption(f"Currently saving to: `{st.session_state.get('save_path')}`")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Save now"):
                    _autosave_to_disk(data)
            with c2:
                st.write("Dirty: " + ("YES" if st.session_state.get("dirty") else "no"))

            st.download_button(
                "Download JSON",
                data=payload.encode("utf-8"),
                file_name=os.path.basename(str(st.session_state.get("save_path") or "timetable_input.json")),
                mime="application/json",
            )
            st.caption("Tip: save this file and run the solver with `--input`.")
        except Exception as e:
            st.warning(f"Fix validation issues to enable download: {e}")

    tab_cal, tab_constraints, tab_teachers, tab_classes, tab_preview = st.tabs(
        ["Calendar", "Constraints", "Teachers", "Classes & Subjects", "Preview JSON"]
    )

    with tab_cal:
        st.subheader("Calendar")
        cal = data.setdefault("calendar", {})
        days = list(cal.get("days") or [])
        periods = list(cal.get("periods") or [])

        col1, col2 = st.columns(2)
        with col1:
            days_csv = st.text_input("Days (comma-separated)", value=_csv(days))
        with col2:
            periods_csv = st.text_input("Periods (comma-separated)", value=_csv(periods))

        if st.button("Apply calendar changes"):
            cal["days"] = _parse_csv_list(days_csv)
            cal["periods"] = _parse_csv_list(periods_csv)
            st.session_state["dirty"] = True
            st.success("Calendar updated.")

    with tab_constraints:
        st.subheader("Constraints")
        constraints = data.setdefault("constraints", {})

        col1, col2 = st.columns(2)
        with col1:
            gmin = constraints.get("min_classes_per_week")
            gmin_val = st.number_input(
                "Min classes per week (global; set to 0 to allow 0, leave blank by clearing via button below)",
                min_value=0,
                step=1,
                value=int(gmin) if isinstance(gmin, int) else 0,
            )
            if st.button("Set global min_classes_per_week"):
                constraints["min_classes_per_week"] = int(gmin_val)
                st.session_state["dirty"] = True
                st.success("Set global min_classes_per_week.")
            if st.button("Clear global min_classes_per_week"):
                constraints.pop("min_classes_per_week", None)
                st.session_state["dirty"] = True
                st.success("Cleared global min_classes_per_week.")

        with col2:
            st.write("Per-class override: `constraints.min_classes_per_week_by_class`")
            by_class = constraints.get("min_classes_per_week_by_class", {}) or {}
            if not isinstance(by_class, dict):
                by_class = {}
                constraints["min_classes_per_week_by_class"] = by_class

            class_names = [c.get("name") for c in (data.get("classes") or []) if c.get("name")]
            sel_cls = st.selectbox("Class", options=["(select)"] + class_names)
            override_val = st.number_input("Override min/week (non-negative)", min_value=0, step=1, value=0)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Apply override") and sel_cls != "(select)":
                    constraints.setdefault("min_classes_per_week_by_class", {})
                    constraints["min_classes_per_week_by_class"][sel_cls] = int(override_val)
                    st.session_state["dirty"] = True
                    st.success(f"Set override for {sel_cls}.")
            with c2:
                if st.button("Clear override") and sel_cls != "(select)":
                    if "min_classes_per_week_by_class" in constraints and sel_cls in constraints["min_classes_per_week_by_class"]:
                        del constraints["min_classes_per_week_by_class"][sel_cls]
                        if not constraints["min_classes_per_week_by_class"]:
                            constraints.pop("min_classes_per_week_by_class", None)
                        st.session_state["dirty"] = True
                        st.success(f"Cleared override for {sel_cls}.")

        st.divider()
        st.write("Teacher max periods per week (global): `constraints.teacher_max_periods_per_week`")
        tmax = constraints.get("teacher_max_periods_per_week", None)
        tmax_enabled = st.checkbox("Enable global teacher max/week", value=(tmax is not None), key="tmax_en")
        tmax_val = st.number_input(
            "Teacher max periods/week",
            min_value=0,
            step=1,
            value=int(tmax) if isinstance(tmax, int) else 16,
            key="tmax_val",
            disabled=not tmax_enabled,
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Apply teacher max/week"):
                constraints["teacher_max_periods_per_week"] = int(tmax_val) if tmax_enabled else None
                if constraints.get("teacher_max_periods_per_week") is None:
                    constraints.pop("teacher_max_periods_per_week", None)
                st.session_state["dirty"] = True
                st.success("Updated global teacher max/week.")
        with c2:
            if st.button("Clear teacher max/week"):
                constraints.pop("teacher_max_periods_per_week", None)
                st.session_state["dirty"] = True
                st.success("Cleared global teacher max/week.")

        st.divider()
        st.write("Max periods per day by tag: `constraints.max_periods_per_day_by_tag`")
        by_tag = constraints.get("max_periods_per_day_by_tag", constraints.get("max_sessions_per_day_by_tag", {})) or {}
        if not isinstance(by_tag, dict):
            by_tag = {}
            constraints["max_periods_per_day_by_tag"] = by_tag

        tag_col1, tag_col2, tag_col3 = st.columns([2, 1, 1])
        with tag_col1:
            tag_name = st.text_input("Tag", value="")
        with tag_col2:
            tag_limit = st.number_input("Max/day", min_value=0, step=1, value=1)
        with tag_col3:
            if st.button("Add/Update tag limit"):
                if not tag_name.strip():
                    st.error("Tag cannot be empty.")
                else:
                    by_tag[tag_name.strip()] = int(tag_limit)
                    st.session_state["dirty"] = True
                    st.success(f"Set tag limit for '{tag_name.strip()}'.")

        if by_tag:
            st.table([{"tag": k, "max_per_day": v} for k, v in sorted(by_tag.items())])
            del_tag = st.selectbox("Remove tag", options=["(select)"] + sorted(by_tag.keys()))
            if st.button("Remove selected tag") and del_tag != "(select)":
                del by_tag[del_tag]
                st.session_state["dirty"] = True
                st.success(f"Removed '{del_tag}'.")

    with tab_teachers:
        st.subheader("Teachers")
        data.setdefault("teachers", [])
        cal_days = list((data.get("calendar", {}) or {}).get("days") or [])
        cal_periods = list((data.get("calendar", {}) or {}).get("periods") or [])

        left, right = st.columns([1, 2], gap="large")
        with left:
            st.write("Teachers")
            existing_teachers = _teacher_names(data)
            selected_t = st.selectbox("Select teacher", options=["(none)"] + existing_teachers, key="teacher_sel")

            st.write("Add teacher")
            new_t_name = st.text_input("New teacher name", value="", key="new_teacher_name")
            if st.button("Add teacher", key="add_teacher_btn"):
                name = (new_t_name or "").strip()
                if not name:
                    st.error("Teacher name required.")
                elif name in existing_teachers:
                    st.error("Teacher already exists.")
                else:
                    data["teachers"].append(
                        {"name": name, "max_periods_per_week": None, "preferred_periods": [], "unavailable_periods": []}
                    )
                    st.session_state["dirty"] = True
                    st.success(f"Added teacher '{name}'.")

            if selected_t != "(none)":
                if st.button("Remove selected teacher", key="remove_teacher_btn"):
                    data["teachers"] = [t for t in data["teachers"] if t.get("name") != selected_t]
                    st.session_state["dirty"] = True
                    st.success(f"Removed teacher '{selected_t}'.")

        with right:
            if selected_t == "(none)":
                st.info("Select a teacher to edit constraints.")
            else:
                t_obj = _find_teacher(data, selected_t)
                if not t_obj:
                    st.warning("Selected teacher not found (state changed).")
                else:
                    editor_key = f"teacher__{selected_t}"
                    st.markdown(f"**Teacher constraints: {selected_t}**")

                    max_ppw = t_obj.get("max_periods_per_week", None)
                    max_enabled = st.checkbox(
                        "Enable max periods per week",
                        value=(max_ppw is not None),
                        key=f"{editor_key}__max_en",
                    )
                    max_val = st.number_input(
                        "Max periods per week",
                        min_value=0,
                        step=1,
                        value=int(max_ppw) if isinstance(max_ppw, int) else 0,
                        key=f"{editor_key}__max_val",
                        disabled=not max_enabled,
                    )

                    preferred = list(t_obj.get("preferred_periods", []) or [])
                    preferred_new = st.multiselect(
                        "Preferred periods (soft preference)",
                        options=list(cal_periods),
                        default=[p for p in preferred if p in cal_periods],
                        key=f"{editor_key}__pref",
                        help="If set, scheduling this teacher outside these periods is penalized (soft).",
                    )

                    unavail_new = _blocked_periods_editor(
                        key_prefix=f"{editor_key}__unavail",
                        current=list(t_obj.get("unavailable_periods", []) or []),
                        days=cal_days,
                        periods=cal_periods,
                    )

                    if st.button("Apply teacher changes", key=f"{editor_key}__apply"):
                        t_obj["max_periods_per_week"] = int(max_val) if max_enabled else None
                        t_obj["preferred_periods"] = list(preferred_new)
                        t_obj["unavailable_periods"] = list(unavail_new)
                        st.session_state["dirty"] = True
                        st.success("Teacher constraints updated.")

    with tab_classes:
        st.subheader("Classes & Subjects")
        data.setdefault("classes", [])

        left, right = st.columns([1, 2], gap="large")
        with left:
            st.write("Classes")
            existing = [c.get("name") for c in data["classes"] if c.get("name")]
            selected = st.selectbox("Select class", options=["(none)"] + existing)

            st.write("Add class")
            new_name = st.text_input("New class name", value="")
            if st.button("Add class"):
                name = new_name.strip()
                if not name:
                    st.error("Class name required.")
                elif name in existing:
                    st.error("Class already exists.")
                else:
                    cobj: Dict[str, Any] = {"name": name, "semesters": {"S1": {"subjects": [], "blocked_periods": []}}}
                    data["classes"].append(cobj)
                    st.session_state["dirty"] = True
                    st.success(f"Added class '{name}'.")

            if selected != "(none)":
                st.write("Rename selected class")
                rename_to = st.text_input("New name", value=selected, key="rename_class_to")
                if st.button("Rename class"):
                    newn = (rename_to or "").strip()
                    if not newn:
                        st.error("New class name cannot be empty.")
                    elif newn != selected and newn in existing:
                        st.error("A class with that name already exists.")
                    else:
                        cobj = _find_class(data, selected)
                        if cobj:
                            cobj["name"] = newn
                        constraints = data.get("constraints", {}) or {}
                        by_class = constraints.get("min_classes_per_week_by_class", {}) or {}
                        if isinstance(by_class, dict) and selected in by_class and newn != selected:
                            by_class[newn] = by_class.pop(selected)
                        st.session_state["dirty"] = True
                        st.success(f"Renamed class '{selected}' -> '{newn}'.")

                if st.button("Remove selected class"):
                    data["classes"] = [c for c in data["classes"] if c.get("name") != selected]
                    constraints = data.get("constraints", {}) or {}
                    by_class = constraints.get("min_classes_per_week_by_class", {}) or {}
                    if isinstance(by_class, dict) and selected in by_class:
                        del by_class[selected]
                        if not by_class:
                            constraints.pop("min_classes_per_week_by_class", None)
                    st.session_state["dirty"] = True
                    st.success(f"Removed class '{selected}'.")

        with right:
            if selected == "(none)":
                st.info("Select a class to manage subjects.")
            else:
                cobj = _find_class(data, selected)
                if not cobj:
                    st.warning("Selected class not found (state changed).")
                else:
                    _ensure_class_shape(cobj)
                    semesters = cobj.setdefault("semesters", {})
                    # Ensure at least S1 exists so the user can add subjects.
                    if not semesters:
                        semesters["S1"] = {"subjects": [], "blocked_periods": []}
                    for sem_key, sem_obj in list(semesters.items()):
                        if isinstance(sem_obj, dict):
                            sem_obj.setdefault("subjects", [])
                            sem_obj.setdefault("blocked_periods", [])

                    st.markdown("**Semesters enabled for this class**")
                    s1_enabled = st.checkbox("Enable S1", value=("S1" in semesters), key=f"sem_s1_{selected}")
                    s2_enabled = st.checkbox("Enable S2", value=("S2" in semesters), key=f"sem_s2_{selected}")
                    if st.button("Apply semester enable/disable", key=f"apply_sem_{selected}"):
                        if s1_enabled and "S1" not in semesters:
                            semesters["S1"] = {"subjects": [], "blocked_periods": []}
                        if (not s1_enabled) and "S1" in semesters:
                            del semesters["S1"]
                        if s2_enabled and "S2" not in semesters:
                            semesters["S2"] = {"subjects": [], "blocked_periods": []}
                        if (not s2_enabled) and "S2" in semesters:
                            del semesters["S2"]
                        st.session_state["dirty"] = True
                        st.success("Updated semesters for this class.")

                    available = [s for s in SEMESTERS if s in semesters]
                    if not available:
                        st.warning("This class has no semesters enabled. Enable at least one semester.")
                        return
                    sem = st.radio("Semester", options=available, horizontal=True)
                    sem_obj = semesters[sem]
                    subjects = sem_obj["subjects"]

                    st.markdown(f"**Subjects for {selected} / {sem}**")
                    if subjects:
                        st.dataframe(subjects, use_container_width=True)
                    else:
                        st.warning("No subjects yet for this semester.")

                    st.divider()
                    st.markdown(f"**Blocked periods for {selected} / {sem}**")
                    cal_days = list((data.get('calendar', {}) or {}).get('days') or [])
                    cal_periods = list((data.get('calendar', {}) or {}).get('periods') or [])
                    blocked_new = _blocked_periods_editor(
                        key_prefix=f"{selected}__{sem}",
                        current=sem_obj.get("blocked_periods", []) or [],
                        days=cal_days,
                        periods=cal_periods,
                    )
                    if st.button("Apply blocked periods", key=f"apply_blocked_{selected}_{sem}"):
                        sem_obj["blocked_periods"] = blocked_new
                        st.session_state["dirty"] = True
                        st.success("Blocked periods updated.")

                    st.divider()
                    st.markdown("**Add / Edit subject**")
                    sub_names = _subject_names(subjects)
                    mode = st.radio("Mode", options=["Add", "Edit"], horizontal=True, key=f"mode_{selected}_{sem}")
                    edit_name: Optional[str] = None
                    if mode == "Edit":
                        if not sub_names:
                            st.info("No subjects to edit yet. Add one first.")
                        else:
                            edit_name = st.selectbox("Select subject", options=sub_names, key=f"edit_sel_{selected}_{sem}")
                    existing_subj = _find_subject(subjects, edit_name) if edit_name else None
                    # IMPORTANT: Streamlit widget keys must be stable.
                    # If we key the fixed/allowed editors off the "Subject name" textbox, then typing/renaming
                    # causes Streamlit to recreate the widget and the user loses edits.
                    editor_key_base = f"{selected}__{sem}__{mode}__{edit_name or 'NEW'}"
                    # Also key the main edit widgets off the selected subject; otherwise Streamlit will preserve
                    # a previous subject's values and it looks like "editing" loads the wrong subject.
                    form_key_base = editor_key_base

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        s_name = st.text_input(
                            "Subject name*",
                            value=(existing_subj.get("name") if existing_subj else ""),
                            key=f"sname__{form_key_base}",
                        )
                        existing_teachers_list = existing_subj.get("teachers") if existing_subj else None
                        if not existing_teachers_list and existing_subj and existing_subj.get("teacher"):
                            existing_teachers_list = [existing_subj.get("teacher")]
                        s_teachers_csv = st.text_input(
                            "Teachers (comma-separated)*",
                            value=", ".join(existing_teachers_list or []) if existing_subj else "",
                            key=f"steachers__{form_key_base}",
                            help="Use multiple teachers for shared teaching. Combine with 'Teaching mode' below.",
                        )
                        s_teach_mode = st.selectbox(
                            "Teaching mode",
                            options=["any_of", "all_of"],
                            index=0
                            if not existing_subj
                            else (1 if (existing_subj.get("teaching_mode") == "all_of") else 0),
                            key=f"steachmode__{form_key_base}",
                            help="any_of = OR (one of the listed teachers will be assigned per period). all_of = AND (all listed teachers teach together).",
                        )
                    with col2:
                        s_ppw = st.number_input(
                            "Periods per week*",
                            min_value=1,
                            step=1,
                            value=int(existing_subj.get("periods_per_week", 1)) if existing_subj else 1,
                            key=f"sppw__{form_key_base}",
                        )
                        s_min = st.number_input(
                            "Min contiguous",
                            min_value=1,
                            step=1,
                            value=int(existing_subj.get("min_contiguous_periods", 1)) if existing_subj else 1,
                            key=f"smin__{form_key_base}",
                        )
                    with col3:
                        s_max = st.number_input(
                            "Max contiguous",
                            min_value=1,
                            step=1,
                            value=int(existing_subj.get("max_contiguous_periods", int(existing_subj.get("min_contiguous_periods", 1))))
                            if existing_subj
                            else 1,
                            key=f"smax__{form_key_base}",
                        )
                        s_tags = st.text_input(
                            "Tags (comma-separated)",
                            value=", ".join(existing_subj.get("tags", [])) if existing_subj else "",
                            key=f"stags__{form_key_base}",
                        )

                    fixed_out = _fixed_sessions_editor(
                        key_prefix=editor_key_base,
                        current=list(existing_subj.get("fixed_sessions", [])) if existing_subj else [],
                        days=cal_days,
                        periods=cal_periods,
                    )
                    allowed_out = _allowed_starts_editor(
                        key_prefix=editor_key_base,
                        current=list(existing_subj.get("allowed_starts", [])) if existing_subj else [],
                        days=cal_days,
                        periods=cal_periods,
                    )

                    if st.button("Save subject", key=f"save_{selected}_{sem}_{mode}"):
                        name = (s_name or "").strip()
                        teachers_list = _normalize_tags_csv(s_teachers_csv)  # reuse CSV parser (comma split + trim)
                        if not name or not teachers_list:
                            st.error("Subject name and at least one teacher are required.")
                        elif int(s_min) > int(s_max):
                            st.error("Min contiguous cannot exceed max contiguous.")
                        else:
                            subj_obj: Dict[str, Any] = {
                                "name": name,
                                "teachers": teachers_list,
                                "teaching_mode": str(s_teach_mode or "any_of"),
                                "periods_per_week": int(s_ppw),
                            }
                            if int(s_min) != 1:
                                subj_obj["min_contiguous_periods"] = int(s_min)
                            if int(s_max) != int(s_min):
                                subj_obj["max_contiguous_periods"] = int(s_max)
                            tags_list = _normalize_tags_csv(s_tags)
                            if tags_list:
                                subj_obj["tags"] = tags_list
                            if fixed_out:
                                subj_obj["fixed_sessions"] = fixed_out
                            if allowed_out:
                                subj_obj["allowed_starts"] = allowed_out

                            if mode == "Add":
                                if name in sub_names:
                                    st.error("Subject with that name already exists in this class/semester.")
                                else:
                                    subjects.append(subj_obj)
                                    st.session_state["dirty"] = True
                                    st.success(f"Added subject '{name}'.")
                            else:
                                if not existing_subj:
                                    st.error("No subject selected to edit.")
                                else:
                                    current_name = str(existing_subj.get("name") or "")
                                    other_names = {n for n in sub_names if n != current_name}
                                    if name in other_names:
                                        st.error("Another subject with that name already exists in this class/semester.")
                                        return
                                    existing_subj.clear()
                                    existing_subj.update(subj_obj)
                                    st.session_state["dirty"] = True
                                    st.success(f"Updated subject '{name}'.")

                    st.divider()
                    st.write("Remove subject")
                    sub_names = _subject_names(subjects)
                    rem = st.selectbox("Subject", options=["(select)"] + sub_names, key=f"remsel_{selected}_{sem}")
                    if st.button("Remove selected subject", key=f"remsub_{selected}_{sem}") and rem != "(select)":
                        cobj["semesters"][sem]["subjects"] = [s for s in subjects if s.get("name") != rem]
                        st.session_state["dirty"] = True
                        st.success(f"Removed '{rem}'.")

    with tab_preview:
        st.subheader("Preview")
        st.code(json.dumps(data, indent=2, ensure_ascii=False), language="json")

    # -----------------------------
    # Run solver (bottom)
    # -----------------------------
    st.divider()
    st.subheader("Run solver")
    st.caption("Runs `timetable_solver.py` using the repo-local `.venv` if available, and shows the output below.")

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        run_semester = st.selectbox("Semester", options=list(SEMESTERS), index=0, key="run_semester")
    with c2:
        run_print_teachers = st.checkbox("Print teacher timetables", value=True, key="run_print_teachers")
    with c3:
        run_time_limit = st.number_input("Time limit (seconds)", min_value=1.0, step=1.0, value=10.0, key="run_time_limit")

    run_output_format = st.selectbox("Output format", options=["text", "html"], index=0, key="run_output_format")

    # Default input path is the active save_path (what the UI is saving to).
    default_input_path = str(st.session_state.get("save_path") or "").strip()
    run_input_path = st.text_input("Input JSON path", value=default_input_path, key="run_input_path")

    if "last_run" not in st.session_state:
        st.session_state["last_run"] = None

    if st.button("Run timetable solver", type="primary"):
        if st.session_state.get("dirty"):
            st.warning(
                "You have unsaved changes. The solver will run using the file on disk (it will NOT include in-memory edits).",
                icon="⚠️",
            )
        with st.spinner("Running solver..."):
            result = _run_solver_cmd(
                input_path=run_input_path,
                semester=str(run_semester),
                print_teachers=bool(run_print_teachers),
                time_limit_s=float(run_time_limit),
                output_format=str(run_output_format),
            )
        st.session_state["last_run"] = result

    last = st.session_state.get("last_run")
    if last:
        st.markdown("**Run details**")
        st.write(f"Python: `{last['python']}`")
        st.write(f"CWD: `{last['cwd']}`")
        st.write("Command:")
        st.code(" ".join(last["cmd"]), language="bash")
        st.write(f"Exit code: `{last['returncode']}`")

        if last.get("stdout"):
            st.markdown("**STDOUT**")
            if last.get("output_format") == "html":
                try:
                    import streamlit.components.v1 as components  # type: ignore

                    components.html(last["stdout"], height=800, scrolling=True)
                except Exception:
                    st.code(last["stdout"], language="html")
            else:
                st.code(last["stdout"], language="text")
        if last.get("stderr"):
            st.markdown("**STDERR**")
            st.code(last["stderr"], language="text")


if __name__ == "__main__":
    main()


