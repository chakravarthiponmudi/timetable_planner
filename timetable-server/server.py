import json
from pathlib import Path
from typing import Dict, List, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from ortools.sat.python import cp_model

from payloads.timetable_schema import TimetableInput
from service.timetable_solver import (
    ClassSemesterSpec,
    FixedSessionSpec,
    SubjectSpec,
    diagnose_infeasible,
    solve_timetable,
    _format_class_timetable_html,
    _format_teacher_allocation_html,
    _compute_teacher_allocation_periods,
    _wrap_html_document,
)

app = FastAPI()

# Allow requests from the Next.js development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/app_initial_data")
async def get_app_initial_data():
    """Returns the initial app data from the timetable_input.sample.json file."""
    # The server is run from the `timetable-server` directory.
    # The sample file is in the parent directory.
    sample_file_path = Path("metadata/base_template.json")
    if not sample_file_path.is_file():
        raise HTTPException(status_code=404, detail=f"base_template not found at {sample_file_path}")
    with sample_file_path.open(encoding="utf-8") as f:
        return json.load(f)


@app.post("/solve/{semester}")
async def solve_timetable_endpoint(semester: str, request: TimetableInput):
    ti = request
    days = ti.calendar.days
    periods = ti.calendar.periods
    min_classes_per_week = ti.constraints.min_classes_per_week
    min_classes_per_week_by_class = ti.constraints.min_classes_per_week_by_class
    max_periods_per_day_by_tag = ti.constraints.max_periods_per_day_by_tag
    global_teacher_max = getattr(ti.constraints, "teacher_max_periods_per_week", None)

    teacher_max_periods_per_week: Dict[str, int] = {}
    teacher_unavailable_periods: Dict[str, List[Tuple[str, str]]] = {}
    teacher_preferred_periods: Dict[str, List[str]] = {}
    for t in getattr(ti, "teachers", []) or []:
        if t.max_periods_per_week is not None:
            teacher_max_periods_per_week[t.name] = int(t.max_periods_per_week)
        if t.unavailable_periods:
            teacher_unavailable_periods[t.name] = [(dp.day, dp.period) for dp in t.unavailable_periods]
        if t.preferred_periods:
            teacher_preferred_periods[t.name] = list(t.preferred_periods)

    if global_teacher_max is not None:
        all_teachers: set[str] = set()
        for c in ti.classes:
            sem = c.semesters.get(semester)
            if sem is None:
                continue
            for s in sem.subjects:
                for nm in s.teachers or []:
                    all_teachers.add(nm)
        for tname in all_teachers:
            teacher_max_periods_per_week.setdefault(tname, int(global_teacher_max))

    specs: List[ClassSemesterSpec] = []
    for c in ti.classes:
        sem = c.semesters.get(semester)
        if sem is None:
            continue
        subjects = tuple(
            SubjectSpec(
                name=s.name,
                teachers=tuple(s.teachers or ([s.teacher] if s.teacher else [])),
                teaching_mode=str(getattr(s, "teaching_mode", "any_of") or "any_of"),
                teacher_share_min_percent=tuple(
                    (tname, int(pct))
                    for tname, pct in (getattr(s, "teacher_share_min_percent", {}) or {}).items()
                ),
                periods_per_week=s.periods_per_week,
                min_contiguous_periods=s.min_contiguous_periods,
                max_contiguous_periods=s.max_contiguous_periods,
                tags=tuple(s.tags),
                allowed_starts=tuple((dp.day, dp.period) for dp in s.allowed_starts),
                fixed_sessions=tuple(
                    FixedSessionSpec(
                        day=fs.day,
                        period=fs.period,
                        duration=fs.duration,
                    )
                    for fs in s.fixed_sessions
                ),
            )
            for s in sem.subjects
        )
        specs.append(
            ClassSemesterSpec(
                class_name=c.name,
                semester=semester,
                subjects=subjects,
                blocked_periods=tuple((bp.day, bp.period, bp.reason or "") for bp in sem.blocked_periods),
            )
        )

    if not specs:
        raise HTTPException(status_code=400, detail=f"No classes found with semester '{semester}'. Nothing to solve.")

    solver, status, ctx = solve_timetable(
        specs=specs,
        days=days,
        periods=periods,
        min_classes_per_week=min_classes_per_week,
        min_classes_per_week_by_class=min_classes_per_week_by_class,
        max_periods_per_day_by_tag=max_periods_per_day_by_tag,
        teacher_max_periods_per_week=teacher_max_periods_per_week,
        teacher_unavailable_periods=teacher_unavailable_periods,
        teacher_preferred_periods=teacher_preferred_periods,
        time_limit_s=10.0,
    )

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        diagnostics = diagnose_infeasible(
            specs=specs,
            days=days,
            periods=periods,
            min_classes_per_week=min_classes_per_week,
            min_classes_per_week_by_class=min_classes_per_week_by_class,
            max_periods_per_day_by_tag=max_periods_per_day_by_tag,
            teacher_max_periods_per_week=teacher_max_periods_per_week,
            teacher_unavailable_periods=teacher_unavailable_periods,
            teacher_preferred_periods=teacher_preferred_periods,
            time_limit_s=5.0,
        )
        raise HTTPException(status_code=400, detail={"message": "Infeasible", "diagnostics": diagnostics})

    parts: List[str] = []
    for cs in specs:
        parts.append(
            _format_class_timetable_html(
                spec=cs,
                days=days,
                periods=periods,
                solver=solver,
                occ_subj=ctx["occ_subj"],
                occ_subj_teacher=ctx["occ_subj_teacher"],
                subject_teachers=ctx["subject_teachers"],
                subject_teaching_mode=ctx["subject_teaching_mode"],
            )
        )

    per_teacher, totals = _compute_teacher_allocation_periods(
        solver=solver,
        occ_subj_teacher=ctx["occ_subj_teacher"],
    )
    parts.append(_format_teacher_allocation_html(per_teacher=per_teacher, totals=totals))

    return {"status": ctx["meta"]["status"], "objective_value": ctx["meta"]["objective_value"], "html": _wrap_html_document("\n\n".join(parts))}