"""
Streamlit-based GUI editor for the timetable input JSON consumed by `timetable_solver.py`.

Why Streamlit?
- Avoids Tk/Tcl runtime issues on macOS
- Runs as a local web app: `streamlit run timetable_web_gui.py`

This editor maps 1:1 to the JSON schema used by the solver.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st


SEMESTERS: Tuple[str, ...] = ("S1", "S2")


def _parse_csv_list(s: str) -> List[str]:
    parts = [(p or "").strip() for p in (s or "").split(",")]
    return [p for p in parts if p]


def _csv(items: List[str]) -> str:
    return ", ".join(items)


def new_data() -> Dict[str, Any]:
    return {
        "constraints": {
            # omit min_classes_per_week by default (user can set it)
            "max_periods_per_day_by_tag": {},
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


def _validate_for_save(data: Dict[str, Any]) -> None:
    cal = data.get("calendar", {}) or {}
    days = cal.get("days", [])
    periods = cal.get("periods", [])
    if not isinstance(days, list) or not days:
        raise ValueError("calendar.days must be a non-empty array.")
    if not isinstance(periods, list) or not periods:
        raise ValueError("calendar.periods must be a non-empty array.")

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
            subjects = ((sem_obj or {}).get("subjects", []) or [])
            if not isinstance(subjects, list) or not subjects:
                raise ValueError(f"Class '{c.get('name')}' semester '{sem}' must have at least one subject.")
            for s in subjects:
                if not isinstance(s, dict):
                    raise ValueError(f"Invalid subject entry in class '{c.get('name')}' {sem}.")
                if not (s.get("name") and s.get("teacher")):
                    raise ValueError(f"Each subject must have name and teacher (class '{c.get('name')}' {sem}).")
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


@dataclass
class SubjectDraft:
    name: str
    teacher: str
    periods_per_week: int
    min_contiguous_periods: int = 1
    max_contiguous_periods: int = 1
    tags_csv: str = ""

    def to_json(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "name": self.name.strip(),
            "teacher": self.teacher.strip(),
            "periods_per_week": int(self.periods_per_week),
        }
        if int(self.min_contiguous_periods) != 1:
            out["min_contiguous_periods"] = int(self.min_contiguous_periods)
        if int(self.max_contiguous_periods) != int(self.min_contiguous_periods):
            out["max_contiguous_periods"] = int(self.max_contiguous_periods)
        tags = _parse_csv_list(self.tags_csv)
        if tags:
            out["tags"] = tags
        return out


def _get_state() -> Dict[str, Any]:
    if "data" not in st.session_state:
        st.session_state["data"] = new_data()
    return st.session_state["data"]


def _find_class(data: Dict[str, Any], class_name: str) -> Optional[Dict[str, Any]]:
    for c in data.get("classes", []) or []:
        if c.get("name") == class_name:
            return c
    return None


def main() -> None:
    st.set_page_config(page_title="Timetable Input Editor", layout="wide")
    st.title("Timetable Input Editor (no-Tk)")
    st.caption("Edits the JSON schema consumed by `timetable_solver.py` and exports a file like `timetable_input.sample.json`.")

    data = _get_state()

    with st.sidebar:
        st.header("File")
        uploaded = st.file_uploader("Open JSON", type=["json"])
        if uploaded is not None:
            try:
                loaded = json.loads(uploaded.getvalue().decode("utf-8"))
                if not isinstance(loaded, dict):
                    raise ValueError("Root JSON must be an object.")
                st.session_state["data"] = loaded
                data = st.session_state["data"]
                st.success("Loaded JSON into editor.")
            except Exception as e:
                st.error(f"Failed to load JSON: {e}")

        if st.button("New (reset)"):
            st.session_state["data"] = new_data()
            data = st.session_state["data"]
            st.success("Reset to new template.")

        st.divider()
        st.subheader("Export")
        try:
            _validate_for_save(data)
            payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            st.download_button(
                "Download JSON",
                data=payload.encode("utf-8"),
                file_name="timetable_input.json",
                mime="application/json",
            )
            st.caption("Tip: save this file and run the solver with `--input`.")
        except Exception as e:
            st.warning(f"Fix validation issues to enable download: {e}")

    tab_cal, tab_constraints, tab_classes, tab_preview = st.tabs(["Calendar", "Constraints", "Classes & Subjects", "Preview JSON"])

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
                st.success("Set global min_classes_per_week.")
            if st.button("Clear global min_classes_per_week"):
                constraints.pop("min_classes_per_week", None)
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
                    st.success(f"Set override for {sel_cls}.")
            with c2:
                if st.button("Clear override") and sel_cls != "(select)":
                    if "min_classes_per_week_by_class" in constraints and sel_cls in constraints["min_classes_per_week_by_class"]:
                        del constraints["min_classes_per_week_by_class"][sel_cls]
                        if not constraints["min_classes_per_week_by_class"]:
                            constraints.pop("min_classes_per_week_by_class", None)
                        st.success(f"Cleared override for {sel_cls}.")

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
                    st.success(f"Set tag limit for '{tag_name.strip()}'.")

        if by_tag:
            st.table([{"tag": k, "max_per_day": v} for k, v in sorted(by_tag.items())])
            del_tag = st.selectbox("Remove tag", options=["(select)"] + sorted(by_tag.keys()))
            if st.button("Remove selected tag") and del_tag != "(select)":
                del by_tag[del_tag]
                st.success(f"Removed '{del_tag}'.")

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
                    cobj: Dict[str, Any] = {"name": name, "semesters": {}}
                    _ensure_class_shape(cobj)
                    data["classes"].append(cobj)
                    st.success(f"Added class '{name}'.")

            if selected != "(none)":
                if st.button("Remove selected class"):
                    data["classes"] = [c for c in data["classes"] if c.get("name") != selected]
                    constraints = data.get("constraints", {}) or {}
                    by_class = constraints.get("min_classes_per_week_by_class", {}) or {}
                    if isinstance(by_class, dict) and selected in by_class:
                        del by_class[selected]
                        if not by_class:
                            constraints.pop("min_classes_per_week_by_class", None)
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
                        semesters["S1"] = {"subjects": []}
                    for sem_key, sem_obj in list(semesters.items()):
                        if isinstance(sem_obj, dict):
                            sem_obj.setdefault("subjects", [])

                    available = [s for s in SEMESTERS if s in semesters]
                    sem = st.radio("Semester", options=available, horizontal=True)
                    subjects = semesters[sem]["subjects"]

                    st.markdown(f"**Subjects for {selected} / {sem}**")
                    if subjects:
                        st.dataframe(subjects, use_container_width=True)
                    else:
                        st.warning("No subjects yet for this semester.")

                    st.divider()
                    st.write("Add subject")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        s_name = st.text_input("Subject name", value="", key=f"sname_{selected}_{sem}")
                        s_teacher = st.text_input("Teacher", value="", key=f"steacher_{selected}_{sem}")
                    with col2:
                        s_spw = st.number_input("Periods per week", min_value=1, step=1, value=1, key=f"ssp_{selected}_{sem}")
                        s_min = st.number_input("Min contiguous", min_value=1, step=1, value=1, key=f"smin_{selected}_{sem}")
                    with col3:
                        s_max = st.number_input("Max contiguous", min_value=1, step=1, value=1, key=f"smax_{selected}_{sem}")
                        s_tags = st.text_input("Tags (comma-separated)", value="", key=f"stags_{selected}_{sem}")

                    if st.button("Add subject", key=f"addsub_{selected}_{sem}"):
                        draft = SubjectDraft(
                            name=s_name,
                            teacher=s_teacher,
                            periods_per_week=int(s_spw),
                            min_contiguous_periods=int(s_min),
                            max_contiguous_periods=int(s_max),
                            tags_csv=s_tags,
                        )
                        subj = draft.to_json()
                        if not subj["name"] or not subj["teacher"]:
                            st.error("Subject name and teacher are required.")
                        elif any((x.get("name") == subj["name"]) for x in subjects):
                            st.error("Subject with that name already exists in this class/semester.")
                        elif subj.get("min_contiguous_periods", 1) > subj.get("max_contiguous_periods", 1):
                            st.error("Min contiguous cannot exceed max contiguous.")
                        else:
                            subjects.append(subj)
                            st.success(f"Added subject '{subj['name']}'.")

                    st.divider()
                    st.write("Remove subject")
                    sub_names = [s.get("name") for s in subjects if s.get("name")]
                    rem = st.selectbox("Subject", options=["(select)"] + sub_names, key=f"remsel_{selected}_{sem}")
                    if st.button("Remove selected subject", key=f"remsub_{selected}_{sem}") and rem != "(select)":
                        cobj["semesters"][sem]["subjects"] = [s for s in subjects if s.get("name") != rem]
                        st.success(f"Removed '{rem}'.")

    with tab_preview:
        st.subheader("Preview")
        st.code(json.dumps(data, indent=2, ensure_ascii=False), language="json")


if __name__ == "__main__":
    main()


