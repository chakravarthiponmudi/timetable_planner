import argparse
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model


@dataclass(frozen=True)
class FixedSessionSpec:
    day: str
    period: str
    duration: Optional[int] = None


@dataclass(frozen=True)
class SubjectSpec:
    name: str
    teacher: str
    sessions_per_week: int
    min_contiguous_periods: int = 1
    max_contiguous_periods: int = 1
    tags: Tuple[str, ...] = ()
    allowed_starts: Tuple[Tuple[str, str], ...] = ()
    fixed_sessions: Tuple[FixedSessionSpec, ...] = ()


@dataclass(frozen=True)
class ClassSemesterSpec:
    class_name: str
    semester: str
    subjects: Tuple[SubjectSpec, ...]
    blocked_periods: Tuple[Tuple[str, str], ...] = ()


def _load_input(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_calendar(data: dict) -> Tuple[List[str], List[str]]:
    cal = data.get("calendar", {})
    days = cal.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri"])
    periods = cal.get("periods", ["P1", "P2", "P3", "P4", "P5"])
    if not days or not periods:
        raise ValueError("calendar.days and calendar.periods must be non-empty arrays")
    return list(days), list(periods)


def _get_min_classes_per_week_constraints(data: dict) -> Tuple[Optional[int], Dict[str, int]]:
    constraints = data.get("constraints", {}) or {}
    global_min = constraints.get("min_classes_per_week")
    by_class = constraints.get("min_classes_per_week_by_class", {}) or {}

    if global_min is not None and (not isinstance(global_min, int) or global_min < 0):
        raise ValueError("constraints.min_classes_per_week must be a non-negative int if provided")
    if not isinstance(by_class, dict):
        raise ValueError("constraints.min_classes_per_week_by_class must be an object/map if provided")
    for k, v in by_class.items():
        if not isinstance(k, str) or not k:
            raise ValueError("constraints.min_classes_per_week_by_class keys must be non-empty strings")
        if not isinstance(v, int) or v < 0:
            raise ValueError(f"constraints.min_classes_per_week_by_class['{k}'] must be a non-negative int")

    return global_min, dict(by_class)


def _get_max_sessions_per_day_by_tag_constraints(data: dict) -> Dict[str, int]:
    constraints = data.get("constraints", {}) or {}
    by_tag = constraints.get("max_sessions_per_day_by_tag", {}) or {}
    if not isinstance(by_tag, dict):
        raise ValueError("constraints.max_sessions_per_day_by_tag must be an object/map if provided")
    out: Dict[str, int] = {}
    for tag, limit in by_tag.items():
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError("constraints.max_sessions_per_day_by_tag keys must be non-empty strings")
        if not isinstance(limit, int) or limit < 0:
            raise ValueError(f"constraints.max_sessions_per_day_by_tag['{tag}'] must be a non-negative int")
        out[tag.strip()] = limit
    return out


def _extract_specs(data: dict, semester: str) -> Tuple[List[ClassSemesterSpec], List[str]]:
    classes = data.get("classes", [])
    if not isinstance(classes, list) or not classes:
        raise ValueError("input must contain a non-empty 'classes' array")

    out: List[ClassSemesterSpec] = []
    skipped: List[str] = []
    for c in classes:
        class_name = c.get("name")
        if not class_name:
            raise ValueError("each class must have a non-empty 'name'")
        semesters = c.get("semesters", {})
        sem = semesters.get(semester)
        # Support classes that have only one semester: skip classes that do not define the requested semester.
        if sem is None:
            skipped.append(class_name)
            continue
        blocked_periods = sem.get("blocked_periods", []) or []
        if not isinstance(blocked_periods, list):
            raise ValueError(f"class '{class_name}' semester '{semester}': blocked_periods must be an array if provided")
        cleaned_blocked: List[Tuple[str, str]] = []
        for bp in blocked_periods:
            if not isinstance(bp, dict):
                raise ValueError(
                    f"class '{class_name}' semester '{semester}': each blocked_periods entry must be an object"
                )
            day = bp.get("day")
            period = bp.get("period")
            if not isinstance(day, str) or not day.strip() or not isinstance(period, str) or not period.strip():
                raise ValueError(
                    f"class '{class_name}' semester '{semester}': each blocked_periods entry needs non-empty 'day' and 'period'"
                )
            cleaned_blocked.append((day.strip(), period.strip()))
        subjects = sem.get("subjects", [])
        if not isinstance(subjects, list) or not subjects:
            raise ValueError(f"class '{class_name}' semester '{semester}' must have non-empty 'subjects'")

        specs: List[SubjectSpec] = []
        for s in subjects:
            subj_name = s.get("name")
            teacher = s.get("teacher")
            spw = s.get("sessions_per_week")
            min_cp = s.get("min_contiguous_periods", 1)
            max_cp = s.get("max_contiguous_periods", min_cp)
            tags = s.get("tags", [])
            allowed_starts = s.get("allowed_starts", []) or []
            fixed_sessions = s.get("fixed_sessions", []) or []
            if not subj_name or not teacher:
                raise ValueError(
                    f"class '{class_name}' semester '{semester}': each subject needs 'name' and 'teacher'"
                )
            if not isinstance(spw, int) or spw <= 0:
                raise ValueError(
                    f"class '{class_name}' semester '{semester}' subject '{subj_name}': "
                    f"'sessions_per_week' must be a positive int"
                )
            if not isinstance(min_cp, int) or not isinstance(max_cp, int) or min_cp <= 0 or max_cp <= 0:
                raise ValueError(
                    f"class '{class_name}' semester '{semester}' subject '{subj_name}': "
                    f"'min_contiguous_periods'/'max_contiguous_periods' must be positive ints"
                )
            if min_cp > max_cp:
                raise ValueError(
                    f"class '{class_name}' semester '{semester}' subject '{subj_name}': "
                    f"min_contiguous_periods ({min_cp}) cannot exceed max_contiguous_periods ({max_cp})"
                )
            if tags is None:
                tags = []
            if not isinstance(tags, list):
                raise ValueError(
                    f"class '{class_name}' semester '{semester}' subject '{subj_name}': 'tags' must be an array if provided"
                )
            cleaned_tags: List[str] = []
            for tag in tags:
                if not isinstance(tag, str) or not tag.strip():
                    raise ValueError(
                        f"class '{class_name}' semester '{semester}' subject '{subj_name}': tags must be non-empty strings"
                    )
                cleaned_tags.append(tag.strip())

            if not isinstance(allowed_starts, list):
                raise ValueError(
                    f"class '{class_name}' semester '{semester}' subject '{subj_name}': 'allowed_starts' must be an array if provided"
                )
            cleaned_allowed_starts: List[Tuple[str, str]] = []
            for a in allowed_starts:
                if not isinstance(a, dict):
                    raise ValueError(
                        f"class '{class_name}' semester '{semester}' subject '{subj_name}': allowed_starts entries must be objects"
                    )
                day = a.get("day")
                period = a.get("period")
                if not isinstance(day, str) or not day.strip() or not isinstance(period, str) or not period.strip():
                    raise ValueError(
                        f"class '{class_name}' semester '{semester}' subject '{subj_name}': "
                        f"allowed_starts entries require non-empty 'day' and 'period'"
                    )
                cleaned_allowed_starts.append((day.strip(), period.strip()))

            if not isinstance(fixed_sessions, list):
                raise ValueError(
                    f"class '{class_name}' semester '{semester}' subject '{subj_name}': 'fixed_sessions' must be an array if provided"
                )
            cleaned_fixed: List[FixedSessionSpec] = []
            for fs in fixed_sessions:
                if not isinstance(fs, dict):
                    raise ValueError(
                        f"class '{class_name}' semester '{semester}' subject '{subj_name}': fixed_sessions entries must be objects"
                    )
                day = fs.get("day")
                period = fs.get("period")
                duration = fs.get("duration", None)
                if not isinstance(day, str) or not day.strip() or not isinstance(period, str) or not period.strip():
                    raise ValueError(
                        f"class '{class_name}' semester '{semester}' subject '{subj_name}': "
                        f"fixed_sessions entries require non-empty 'day' and 'period'"
                    )
                if duration is not None and (not isinstance(duration, int) or duration <= 0):
                    raise ValueError(
                        f"class '{class_name}' semester '{semester}' subject '{subj_name}': "
                        f"fixed_sessions.duration must be a positive int if provided"
                    )
                cleaned_fixed.append(FixedSessionSpec(day=day.strip(), period=period.strip(), duration=duration))
            specs.append(
                SubjectSpec(
                    name=subj_name,
                    teacher=teacher,
                    sessions_per_week=spw,
                    min_contiguous_periods=min_cp,
                    max_contiguous_periods=max_cp,
                    tags=tuple(cleaned_tags),
                    allowed_starts=tuple(cleaned_allowed_starts),
                    fixed_sessions=tuple(cleaned_fixed),
                )
            )

        out.append(
            ClassSemesterSpec(
                class_name=class_name,
                semester=semester,
                subjects=tuple(specs),
                blocked_periods=tuple(cleaned_blocked),
            )
        )

    return out, skipped


def solve_timetable(
    *,
    specs: List[ClassSemesterSpec],
    days: List[str],
    periods: List[str],
    min_classes_per_week: Optional[int],
    min_classes_per_week_by_class: Dict[str, int],
    max_sessions_per_day_by_tag: Dict[str, int],
    time_limit_s: float,
) -> Tuple[cp_model.CpSolver, int, dict]:
    model = cp_model.CpModel()

    num_days = len(days)
    num_periods = len(periods)
    num_slots = num_days * num_periods

    def slot_index(d: int, p: int) -> int:
        return d * num_periods + p

    # Block decision vars:
    # y[(class_name, subject_name, day, start_period, duration)] = 1 if a session starts there with that duration.
    y: Dict[Tuple[str, str, int, int, int], cp_model.IntVar] = {}

    # Occupancy vars per period:
    # occ[(class_name, day, period)] = 1 if the class has any session at that time.
    occ: Dict[Tuple[str, int, int], cp_model.IntVar] = {}

    # Subject occupancy per period (helps printing + teacher constraints):
    # occ_subj[(class_name, subject_name, day, period)] = 1 if that subject occupies that period for that class.
    occ_subj: Dict[Tuple[str, str, int, int], cp_model.IntVar] = {}

    subject_teacher: Dict[Tuple[str, str], str] = {}

    # Create vars
    for cs in specs:
        for d in range(num_days):
            for p in range(num_periods):
                occ[(cs.class_name, d, p)] = model.NewBoolVar(f"occ__{cs.class_name}__{d}__{p}")
        for subj in cs.subjects:
            subject_teacher[(cs.class_name, subj.name)] = subj.teacher
            for d in range(num_days):
                for p in range(num_periods):
                    occ_subj[(cs.class_name, subj.name, d, p)] = model.NewBoolVar(
                        f"occsubj__{cs.class_name}__{subj.name}__{d}__{p}"
                    )
            for d in range(num_days):
                for start in range(num_periods):
                    for dur in range(subj.min_contiguous_periods, subj.max_contiguous_periods + 1):
                        if start + dur <= num_periods:
                            y[(cs.class_name, subj.name, d, start, dur)] = model.NewBoolVar(
                                f"y__{cs.class_name}__{subj.name}__{d}__{start}__{dur}"
                            )

    # Sanity: ensure each class has enough slots for its required sessions
    for cs in specs:
        # Lower bound needed periods/week (each session consumes at least min_contiguous_periods).
        min_periods_needed = sum(subj.sessions_per_week * subj.min_contiguous_periods for subj in cs.subjects)
        if min_periods_needed > num_slots:
            raise ValueError(
                f"class '{cs.class_name}' semester '{cs.semester}' needs at least {min_periods_needed} periods/week "
                f"(based on sessions_per_week * min_contiguous_periods), but calendar only has {num_slots} slots/week"
            )
        for subj in cs.subjects:
            if subj.min_contiguous_periods > num_periods or subj.max_contiguous_periods > num_periods:
                raise ValueError(
                    f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                    f"contiguous periods cannot exceed periods/day ({num_periods})"
                )
            # Ensure there is at least one feasible start within a day.
            has_any = any(
                (start + dur <= num_periods)
                for start in range(num_periods)
                for dur in range(subj.min_contiguous_periods, subj.max_contiguous_periods + 1)
            )
            if not has_any:
                raise ValueError(
                    f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                    f"no feasible (start,duration) fits into a day"
                )

    # Optional constraint: enforce a minimum number of scheduled classes per week (global and/or per class).
    # Note: since each subject has an exact sessions_per_week, this constraint is a feasibility requirement
    # unless you later add variables that let OR-Tools choose counts.
    for cs in specs:
        required_min = min_classes_per_week_by_class.get(cs.class_name, min_classes_per_week)
        if required_min is None:
            continue
        if required_min > num_slots:
            raise ValueError(
                f"class '{cs.class_name}' minimum classes/week is {required_min}, but calendar only has {num_slots} slots/week"
            )
        total_periods_scheduled = sum(
            occ[(cs.class_name, d, p)] for d in range(num_days) for p in range(num_periods)
        )
        model.Add(total_periods_scheduled >= required_min)

    # Fixed class-level blocked periods: nothing can be scheduled in these slots for that class.
    # This works for both 1-period lectures and multi-period practical blocks.
    day_to_idx = {day: i for i, day in enumerate(days)}
    period_to_idx = {period: i for i, period in enumerate(periods)}
    for cs in specs:
        for day_name, period_name in cs.blocked_periods:
            if day_name not in day_to_idx:
                raise ValueError(
                    f"class '{cs.class_name}' semester '{cs.semester}': blocked_periods day '{day_name}' is not in calendar.days"
                )
            if period_name not in period_to_idx:
                raise ValueError(
                    f"class '{cs.class_name}' semester '{cs.semester}': blocked_periods period '{period_name}' is not in calendar.periods"
                )
            d = day_to_idx[day_name]
            p = period_to_idx[period_name]
            model.Add(occ[(cs.class_name, d, p)] == 0)

    # Constraint: each subject gets exactly sessions_per_week sessions (count sessions/blocks, not periods)
    for cs in specs:
        for subj in cs.subjects:
            model.Add(
                sum(
                    y[(cs.class_name, subj.name, d, start, dur)]
                    for d in range(num_days)
                    for start in range(num_periods)
                    for dur in range(subj.min_contiguous_periods, subj.max_contiguous_periods + 1)
                    if (cs.class_name, subj.name, d, start, dur) in y
                )
                == subj.sessions_per_week
            )

    # Optional subject-level allowed start slots (restrict when a session may start)
    for cs in specs:
        for subj in cs.subjects:
            if not subj.allowed_starts:
                continue
            allowed_pairs: List[Tuple[int, int]] = []
            for day_name, period_name in subj.allowed_starts:
                if day_name not in day_to_idx:
                    raise ValueError(
                        f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                        f"allowed_starts day '{day_name}' is not in calendar.days"
                    )
                if period_name not in period_to_idx:
                    raise ValueError(
                        f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                        f"allowed_starts period '{period_name}' is not in calendar.periods"
                    )
                allowed_pairs.append((day_to_idx[day_name], period_to_idx[period_name]))
            allowed_set = set(allowed_pairs)

            for d in range(num_days):
                for start in range(num_periods):
                    if (d, start) in allowed_set:
                        continue
                    for dur in range(subj.min_contiguous_periods, subj.max_contiguous_periods + 1):
                        key = (cs.class_name, subj.name, d, start, dur)
                        if key in y:
                            model.Add(y[key] == 0)

    # Optional subject-level fixed sessions (pin some sessions to a specific weekday/period; duration optional)
    for cs in specs:
        for subj in cs.subjects:
            if not subj.fixed_sessions:
                continue
            for fs in subj.fixed_sessions:
                if fs.day not in day_to_idx:
                    raise ValueError(
                        f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                        f"fixed_sessions day '{fs.day}' is not in calendar.days"
                    )
                if fs.period not in period_to_idx:
                    raise ValueError(
                        f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                        f"fixed_sessions period '{fs.period}' is not in calendar.periods"
                    )
                d = day_to_idx[fs.day]
                start = period_to_idx[fs.period]

                if fs.duration is not None:
                    dur = fs.duration
                    if dur < subj.min_contiguous_periods or dur > subj.max_contiguous_periods:
                        raise ValueError(
                            f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                            f"fixed_sessions duration {dur} must be within [{subj.min_contiguous_periods}, {subj.max_contiguous_periods}]"
                        )
                    if start + dur > num_periods:
                        raise ValueError(
                            f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                            f"fixed_sessions ({fs.day} {fs.period}) with duration {dur} does not fit in the day"
                        )
                    key = (cs.class_name, subj.name, d, start, dur)
                    if key not in y:
                        raise ValueError(
                            f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                            f"fixed_sessions ({fs.day} {fs.period}, dur={dur}) is not a valid start/duration"
                        )
                    model.Add(y[key] == 1)
                else:
                    # Duration not specified: force "a session starts here" with any allowed duration.
                    candidates = []
                    for dur in range(subj.min_contiguous_periods, subj.max_contiguous_periods + 1):
                        key = (cs.class_name, subj.name, d, start, dur)
                        if key in y:
                            candidates.append(y[key])
                    if not candidates:
                        raise ValueError(
                            f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                            f"fixed_sessions ({fs.day} {fs.period}) has no feasible duration"
                        )
                    model.Add(sum(candidates) == 1)

    # Optional constraint: limit number of sessions per day by subject "tag".
    # Example: {"practical": 1} => no more than one practical session per class per day.
    if max_sessions_per_day_by_tag:
        for cs in specs:
            subjects_by_tag: Dict[str, List[SubjectSpec]] = {}
            for subj in cs.subjects:
                for tag in subj.tags:
                    subjects_by_tag.setdefault(tag, []).append(subj)

            for tag, limit in max_sessions_per_day_by_tag.items():
                if limit is None:
                    continue
                tagged_subjects = subjects_by_tag.get(tag, [])
                if not tagged_subjects:
                    continue
                for d in range(num_days):
                    model.Add(
                        sum(
                            y[(cs.class_name, subj.name, d, start, dur)]
                            for subj in tagged_subjects
                            for start in range(num_periods)
                            for dur in range(subj.min_contiguous_periods, subj.max_contiguous_periods + 1)
                            if (cs.class_name, subj.name, d, start, dur) in y
                        )
                        <= limit
                    )

    # Link occ_subj and y (subject occupies periods covered by its chosen blocks)
    for cs in specs:
        for subj in cs.subjects:
            for d in range(num_days):
                for p in range(num_periods):
                    covering_starts = []
                    for start in range(num_periods):
                        for dur in range(subj.min_contiguous_periods, subj.max_contiguous_periods + 1):
                            if (cs.class_name, subj.name, d, start, dur) not in y:
                                continue
                            if start <= p < start + dur:
                                covering_starts.append(y[(cs.class_name, subj.name, d, start, dur)])
                    # Because a subject's sessions cannot overlap themselves on the same class/day/period,
                    # occ_subj equals the sum of all blocks that cover this period (should be 0 or 1).
                    if covering_starts:
                        model.Add(occ_subj[(cs.class_name, subj.name, d, p)] == sum(covering_starts))
                    else:
                        model.Add(occ_subj[(cs.class_name, subj.name, d, p)] == 0)

    # Constraint: at most one subject per class per period (class non-overlap), and link occ
    for cs in specs:
        subj_names = [subj.name for subj in cs.subjects]
        for d in range(num_days):
            for p in range(num_periods):
                model.Add(sum(occ_subj[(cs.class_name, subj_name, d, p)] for subj_name in subj_names) <= 1)
                model.Add(occ[(cs.class_name, d, p)] == sum(occ_subj[(cs.class_name, subj_name, d, p)] for subj_name in subj_names))

    # Constraint: a teacher cannot teach two classes at the same time
    teachers = sorted({subj.teacher for cs in specs for subj in cs.subjects})
    for t in teachers:
        for d in range(num_days):
            for p in range(num_periods):
                model.Add(
                    sum(
                        occ_subj[(cs.class_name, subj.name, d, p)]
                        for cs in specs
                        for subj in cs.subjects
                        if subj.teacher == t
                    )
                    <= 1
                )

    # Soft constraint: discourage having the same subject twice on the same day for a class.
    # We do this by counting (sessions_per_day - 1)+ as "excess" and minimizing it.
    penalties: List[cp_model.IntVar] = []
    for cs in specs:
        for subj in cs.subjects:
            for d in range(num_days):
                day_count = model.NewIntVar(0, num_periods, f"day_count__{cs.class_name}__{subj.name}__{d}")
                model.Add(
                    day_count
                    == sum(
                        y[(cs.class_name, subj.name, d, start, dur)]
                        for start in range(num_periods)
                        for dur in range(subj.min_contiguous_periods, subj.max_contiguous_periods + 1)
                        if (cs.class_name, subj.name, d, start, dur) in y
                    )
                )
                excess = model.NewIntVar(0, num_periods, f"excess__{cs.class_name}__{subj.name}__{d}")
                # excess >= day_count - 1; excess >= 0
                model.Add(excess >= day_count - 1)
                model.Add(excess >= 0)
                penalties.append(excess)

    model.Minimize(sum(penalties))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    status = solver.Solve(model)

    meta = {
        "num_days": num_days,
        "num_periods": num_periods,
        "num_slots": num_slots,
        "teachers": teachers,
        "status": solver.StatusName(status),
        "objective_value": solver.ObjectiveValue() if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None,
    }
    return solver, status, {"y": y, "occ": occ, "occ_subj": occ_subj, "subject_teacher": subject_teacher, "meta": meta}


def _format_class_timetable(
    *,
    class_name: str,
    subjects: List[str],
    days: List[str],
    periods: List[str],
    solver: cp_model.CpSolver,
    occ_subj: Dict[Tuple[str, str, int, int], cp_model.IntVar],
    subject_teacher: Dict[Tuple[str, str], str],
) -> str:
    num_periods = len(periods)

    def slot_index(d: int, p: int) -> int:
        return d * num_periods + p

    # Build grid: rows=days, cols=periods
    grid: List[List[str]] = []
    for d in range(len(days)):
        row: List[str] = []
        for p in range(len(periods)):
            cell = "-"
            for subj in subjects:
                if solver.Value(occ_subj[(class_name, subj, d, p)]) == 1:
                    cell = f"{subj}({subject_teacher[(class_name, subj)]})"
                    break
            row.append(cell)
        grid.append(row)

    # Pretty print as aligned columns
    col_widths = [max(len(periods[i]), max(len(grid[r][i]) for r in range(len(days)))) for i in range(len(periods))]
    day_width = max(len("Day"), max(len(d) for d in days))

    lines: List[str] = []
    lines.append(f"Class: {class_name}")
    header = " " * (day_width + 2) + "  ".join(periods[i].ljust(col_widths[i]) for i in range(len(periods)))
    lines.append(header)
    for d, day in enumerate(days):
        lines.append(day.ljust(day_width) + "  " + "  ".join(grid[d][i].ljust(col_widths[i]) for i in range(len(periods))))
    return "\n".join(lines)


def _format_teacher_timetable(
    *,
    teacher: str,
    specs: List[ClassSemesterSpec],
    days: List[str],
    periods: List[str],
    solver: cp_model.CpSolver,
    occ_subj: Dict[Tuple[str, str, int, int], cp_model.IntVar],
    subject_teacher: Dict[Tuple[str, str], str],
) -> str:
    num_periods = len(periods)

    def slot_index(d: int, p: int) -> int:
        return d * num_periods + p

    class_subjects: Dict[str, List[str]] = {cs.class_name: [s.name for s in cs.subjects] for cs in specs}

    grid: List[List[str]] = []
    for d in range(len(days)):
        row: List[str] = []
        for p in range(len(periods)):
            cell = "-"
            for cs in specs:
                for subj in class_subjects[cs.class_name]:
                    if subject_teacher[(cs.class_name, subj)] != teacher:
                        continue
                    if solver.Value(occ_subj[(cs.class_name, subj, d, p)]) == 1:
                        cell = f"{cs.class_name}:{subj}"
                        break
                if cell != "-":
                    break
            row.append(cell)
        grid.append(row)

    col_widths = [max(len(periods[i]), max(len(grid[r][i]) for r in range(len(days)))) for i in range(len(periods))]
    day_width = max(len("Day"), max(len(d) for d in days))

    lines: List[str] = []
    lines.append(f"Teacher: {teacher}")
    header = " " * (day_width + 2) + "  ".join(periods[i].ljust(col_widths[i]) for i in range(len(periods)))
    lines.append(header)
    for d, day in enumerate(days):
        lines.append(day.ljust(day_width) + "  " + "  ".join(grid[d][i].ljust(col_widths[i]) for i in range(len(periods))))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="College timetable generator using Google OR-Tools (CP-SAT).")
    parser.add_argument("--input", required=True, help="Path to input JSON file.")
    parser.add_argument("--semester", required=True, help="Semester key in JSON, e.g. 'S1' or 'S2'.")
    parser.add_argument("--time_limit_s", type=float, default=10.0, help="CP-SAT time limit in seconds.")
    parser.add_argument("--print_teachers", action="store_true", help="Also print timetable per teacher.")
    args = parser.parse_args()

    data = _load_input(args.input)
    days, periods = _get_calendar(data)
    min_classes_per_week, min_classes_per_week_by_class = _get_min_classes_per_week_constraints(data)
    max_sessions_per_day_by_tag = _get_max_sessions_per_day_by_tag_constraints(data)
    specs, skipped = _extract_specs(data, args.semester)
    if skipped:
        print(f"Note: skipping classes without semester '{args.semester}': {', '.join(skipped)}")
    if not specs:
        print(f"No classes found with semester '{args.semester}'. Nothing to solve.")
        return

    solver, status, ctx = solve_timetable(
        specs=specs,
        days=days,
        periods=periods,
        min_classes_per_week=min_classes_per_week,
        min_classes_per_week_by_class=min_classes_per_week_by_class,
        max_sessions_per_day_by_tag=max_sessions_per_day_by_tag,
        time_limit_s=args.time_limit_s,
    )

    print(f"Status: {ctx['meta']['status']}")
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("No feasible timetable found. Try increasing slots/week or reducing sessions, or increase time limit.")
        return
    print(f"Objective (lower is better): {ctx['meta']['objective_value']}")
    print()

    # Print class timetables
    for cs in specs:
        subjects = [s.name for s in cs.subjects]
        print(_format_class_timetable(
            class_name=cs.class_name,
            subjects=subjects,
            days=days,
            periods=periods,
            solver=solver,
            occ_subj=ctx["occ_subj"],
            subject_teacher=ctx["subject_teacher"],
        ))
        print()

    if args.print_teachers:
        for teacher in ctx["meta"]["teachers"]:
            print(_format_teacher_timetable(
                teacher=teacher,
                specs=specs,
                days=days,
                periods=periods,
                solver=solver,
                occ_subj=ctx["occ_subj"],
                subject_teacher=ctx["subject_teacher"],
            ))
            print()


if __name__ == "__main__":
    main()


