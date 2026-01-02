import argparse
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import html

from ortools.sat.python import cp_model

from timetable_schema import TimetableInput


@dataclass(frozen=True)
class FixedSessionSpec:
    period: str
    day: Optional[str] = None
    duration: Optional[int] = None


@dataclass(frozen=True)
class SubjectSpec:
    name: str
    teachers: Tuple[str, ...]
    periods_per_week: int
    teaching_mode: str = "any_of"  # "any_of" or "all_of"
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


def _get_max_periods_per_day_by_tag_constraints(data: dict) -> Dict[str, int]:
    # Backward-compatible reader: prefer the new period-based key, but accept the old one too.
    # New: constraints.max_periods_per_day_by_tag  (period-count, based on occ_subj)
    # Old: constraints.max_sessions_per_day_by_tag (session/block-count, based on y starts)
    # We return a dict of tag->limit in PERIODS. If the old key is used, we still treat the limit as PERIODS
    # (so users don't accidentally configure "sessions" thinking they're periods).
    constraints = data.get("constraints", {}) or {}
    by_tag = constraints.get("max_periods_per_day_by_tag", None)
    if by_tag is None:
        by_tag = constraints.get("max_sessions_per_day_by_tag", {}) or {}
    if not isinstance(by_tag, dict):
        raise ValueError("constraints.max_periods_per_day_by_tag must be an object/map if provided")
    out: Dict[str, int] = {}
    for tag, limit in by_tag.items():
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError("constraints.max_periods_per_day_by_tag keys must be non-empty strings")
        if not isinstance(limit, int) or limit < 0:
            raise ValueError(f"constraints.max_periods_per_day_by_tag['{tag}'] must be a non-negative int")
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
            ppw = s.get("periods_per_week")
            spw = s.get("sessions_per_week")  # backward-compat (see below)
            min_cp = s.get("min_contiguous_periods", 1)
            max_cp = s.get("max_contiguous_periods", min_cp)
            tags = s.get("tags", [])
            allowed_starts = s.get("allowed_starts", []) or []
            fixed_sessions = s.get("fixed_sessions", []) or []
            if not subj_name or not teacher:
                raise ValueError(
                    f"class '{class_name}' semester '{semester}': each subject needs 'name' and 'teacher'"
                )
            # periods_per_week is the primary unit. For backward-compat:
            # - if periods_per_week is missing and sessions_per_week is present, allow it only for 1-period lectures
            #   (min=max=1), where sessions == periods.
            if ppw is None and spw is not None:
                if min_cp == 1 and max_cp == 1:
                    ppw = spw
                else:
                    raise ValueError(
                        f"class '{class_name}' semester '{semester}' subject '{subj_name}': "
                        f"use 'periods_per_week' (not 'sessions_per_week') for multi-period blocks"
                    )
            if not isinstance(ppw, int) or ppw <= 0:
                raise ValueError(
                    f"class '{class_name}' semester '{semester}' subject '{subj_name}': "
                    f"'periods_per_week' must be a positive int"
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
                period = fs.get("period")
                day = fs.get("day", None)
                duration = fs.get("duration", None)
                if not isinstance(period, str) or not period.strip():
                    raise ValueError(
                        f"class '{class_name}' semester '{semester}' subject '{subj_name}': "
                        f"fixed_sessions entries require non-empty 'period' (day is optional)"
                    )
                if day is not None and (not isinstance(day, str) or not day.strip()):
                    raise ValueError(
                        f"class '{class_name}' semester '{semester}' subject '{subj_name}': "
                        f"fixed_sessions.day must be a non-empty string if provided"
                    )
                if duration is not None and (not isinstance(duration, int) or duration <= 0):
                    raise ValueError(
                        f"class '{class_name}' semester '{semester}' subject '{subj_name}': "
                        f"fixed_sessions.duration must be a positive int if provided"
                    )
                cleaned_fixed.append(
                    FixedSessionSpec(
                        day=day.strip() if isinstance(day, str) else None,
                        period=period.strip(),
                        duration=duration,
                    )
                )
            specs.append(
                SubjectSpec(
                    name=subj_name,
                    teacher=teacher,
                    periods_per_week=ppw,
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


def _compute_required_periods_by_class(specs: List[ClassSemesterSpec]) -> Dict[str, int]:
    return {cs.class_name: sum(s.periods_per_week for s in cs.subjects) for cs in specs}


def _compute_required_periods_by_teacher(specs: List[ClassSemesterSpec]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for cs in specs:
        for subj in cs.subjects:
            # Only definite load can be computed pre-solve:
            # - all_of: each listed teacher participates in every period
            # - any_of: teacher assignment is a choice, so we cannot attribute periods to individual teachers here
            mode = (subj.teaching_mode or "any_of").lower()
            if mode == "all_of":
                for t in subj.teachers:
                    out[t] = out.get(t, 0) + subj.periods_per_week
    return out


def _compute_required_tag_periods_by_class(
    specs: List[ClassSemesterSpec],
    tag: str,
) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for cs in specs:
        tot = 0
        for subj in cs.subjects:
            if tag in subj.tags:
                tot += subj.periods_per_week
        out[cs.class_name] = tot
    return out


def _precheck_and_explain_obvious_infeasibility(
    *,
    specs: List[ClassSemesterSpec],
    num_days: int,
    num_periods: int,
    min_classes_per_week: Optional[int],
    min_classes_per_week_by_class: Dict[str, int],
    max_periods_per_day_by_tag: Dict[str, int],
    teacher_max_periods_per_week: Dict[str, int],
) -> List[str]:
    """
    Returns a list of human-readable infeasibility reasons. Empty list => no obvious contradiction found.
    These are necessary (but not sufficient) feasibility checks.
    """
    reasons: List[str] = []
    num_slots = num_days * num_periods

    # 1) Class weekly periods cannot exceed available slots.
    required_by_class = _compute_required_periods_by_class(specs)
    for cls, req in sorted(required_by_class.items()):
        if req > num_slots:
            reasons.append(
                f"Class '{cls}' requires {req} total periods/week (sum of periods_per_week), "
                f"but calendar only has {num_slots} slots/week."
            )

    # 2) min_classes_per_week cannot exceed required periods (since the model fixes total scheduled periods).
    for cs in specs:
        req_periods = required_by_class.get(cs.class_name, 0)
        required_min = min_classes_per_week_by_class.get(cs.class_name, min_classes_per_week)
        if required_min is None:
            continue
        if required_min > req_periods:
            reasons.append(
                f"Constraint min_classes_per_week fails for class '{cs.class_name}': "
                f"minimum is {required_min}, but this class only schedules {req_periods} periods/week (fixed by periods_per_week)."
            )
        if required_min > num_slots:
            reasons.append(
                f"Constraint min_classes_per_week fails for class '{cs.class_name}': "
                f"minimum is {required_min}, but calendar only has {num_slots} slots/week."
            )

    # 3) Teacher weekly load checks:
    # We can only compute *definite* per-teacher load for co-teaching (all_of).
    # For any_of, teacher assignment is a choice, so we skip strict per-teacher requirements here.
    required_by_teacher_definite = _compute_required_periods_by_teacher(specs)
    for teacher, req in sorted(required_by_teacher_definite.items()):
        if req > num_slots:
            reasons.append(
                f"Teacher '{teacher}' requires at least {req} periods/week due to co-teaching (all_of), "
                f"but can teach at most {num_slots} periods/week due to teacher no-overlap."
            )
        tmax = teacher_max_periods_per_week.get(teacher)
        if tmax is not None and req > tmax:
            reasons.append(
                f"Teacher '{teacher}' requires at least {req} periods/week due to co-teaching (all_of), "
                f"but teacher max_periods_per_week is {tmax}."
            )

    # 4) Tag daily limit necessary check: total tagged periods/week <= limit_per_day * num_days
    for tag, per_day_limit in sorted(max_periods_per_day_by_tag.items()):
        if per_day_limit < 0:
            continue
        req_by_class = _compute_required_tag_periods_by_class(specs, tag)
        for cls, req in sorted(req_by_class.items()):
            if req > per_day_limit * num_days:
                reasons.append(
                    f"Constraint max_periods_per_day_by_tag['{tag}'] fails for class '{cls}': "
                    f"needs {req} '{tag}' periods/week, but limit {per_day_limit}/day over {num_days} days allows only {per_day_limit * num_days}/week."
                )

    return reasons


def solve_timetable(
    *,
    specs: List[ClassSemesterSpec],
    days: List[str],
    periods: List[str],
    min_classes_per_week: Optional[int],
    min_classes_per_week_by_class: Dict[str, int],
    max_periods_per_day_by_tag: Dict[str, int],
    teacher_max_periods_per_week: Dict[str, int],
    teacher_unavailable_periods: Dict[str, List[Tuple[str, str]]],
    teacher_preferred_periods: Dict[str, List[str]],
    time_limit_s: float,
    enable_placement_constraints: bool = True,
    enable_tag_limits: bool = True,
    enable_min_classes_per_week: bool = True,
    enable_teacher_constraints: bool = True,
    enable_teacher_preferences: bool = True,
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

    subject_teachers: Dict[Tuple[str, str], Tuple[str, ...]] = {}
    subject_teaching_mode: Dict[Tuple[str, str], str] = {}

    # Teacher occupancy per (class, subject, teacher, day, period)
    occ_subj_teacher: Dict[Tuple[str, str, str, int, int], cp_model.IntVar] = {}

    # Create vars
    for cs in specs:
        for d in range(num_days):
            for p in range(num_periods):
                occ[(cs.class_name, d, p)] = model.NewBoolVar(f"occ__{cs.class_name}__{d}__{p}")
        for subj in cs.subjects:
            subject_teachers[(cs.class_name, subj.name)] = tuple(subj.teachers)
            subject_teaching_mode[(cs.class_name, subj.name)] = (subj.teaching_mode or "any_of").lower()
            for d in range(num_days):
                for p in range(num_periods):
                    occ_subj[(cs.class_name, subj.name, d, p)] = model.NewBoolVar(
                        f"occsubj__{cs.class_name}__{subj.name}__{d}__{p}"
                    )
                    for t in subj.teachers:
                        occ_subj_teacher[(cs.class_name, subj.name, t, d, p)] = model.NewBoolVar(
                            f"occsubjteach__{cs.class_name}__{subj.name}__{t}__{d}__{p}"
                        )
            for d in range(num_days):
                for start in range(num_periods):
                    for dur in range(subj.min_contiguous_periods, subj.max_contiguous_periods + 1):
                        if start + dur <= num_periods:
                            y[(cs.class_name, subj.name, d, start, dur)] = model.NewBoolVar(
                                f"y__{cs.class_name}__{subj.name}__{d}__{start}__{dur}"
                            )

    # Sanity: ensure each class has enough slots for its required load
    for cs in specs:
        # Exact periods needed/week now come directly from periods_per_week.
        total_periods_needed = sum(subj.periods_per_week for subj in cs.subjects)
        if total_periods_needed > num_slots:
            raise ValueError(
                f"class '{cs.class_name}' semester '{cs.semester}' needs {total_periods_needed} periods/week "
                f"(based on periods_per_week), but calendar only has {num_slots} slots/week"
            )
        for subj in cs.subjects:
            if subj.min_contiguous_periods > num_periods or subj.max_contiguous_periods > num_periods:
                raise ValueError(
                    f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                    f"contiguous periods cannot exceed periods/day ({num_periods})"
                )
            if subj.periods_per_week < subj.min_contiguous_periods:
                raise ValueError(
                    f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                    f"periods_per_week ({subj.periods_per_week}) must be >= min_contiguous_periods ({subj.min_contiguous_periods})"
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
    if enable_min_classes_per_week:
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
    if enable_placement_constraints:
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

    # Constraint: each subject gets exactly periods_per_week periods (counting occupied periods).
    for cs in specs:
        for subj in cs.subjects:
            model.Add(
                sum(
                    dur * y[(cs.class_name, subj.name, d, start, dur)]
                    for d in range(num_days)
                    for start in range(num_periods)
                    for dur in range(subj.min_contiguous_periods, subj.max_contiguous_periods + 1)
                    if (cs.class_name, subj.name, d, start, dur) in y
                )
                == subj.periods_per_week
            )

    # Optional subject-level allowed start slots (restrict when a session may start)
    if enable_placement_constraints:
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
    if enable_placement_constraints:
        for cs in specs:
            for subj in cs.subjects:
                if not subj.fixed_sessions:
                    continue
                for fs in subj.fixed_sessions:
                    if fs.period not in period_to_idx:
                        raise ValueError(
                            f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                            f"fixed_sessions period '{fs.period}' is not in calendar.periods"
                        )
                    start = period_to_idx[fs.period]
                    days_to_consider: List[int]
                    if fs.day is None:
                        # Day omitted => allow any day, but force the fixed start to happen on exactly one day.
                        days_to_consider = list(range(num_days))
                    else:
                        if fs.day not in day_to_idx:
                            raise ValueError(
                                f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                                f"fixed_sessions day '{fs.day}' is not in calendar.days"
                            )
                        days_to_consider = [day_to_idx[fs.day]]

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
                                f"fixed_sessions ({fs.day or '*'} {fs.period}) with duration {dur} does not fit in the day"
                            )
                        candidates = []
                        for d in days_to_consider:
                            key = (cs.class_name, subj.name, d, start, dur)
                            if key in y:
                                candidates.append(y[key])
                        if not candidates:
                            raise ValueError(
                                f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                                f"fixed_sessions ({fs.day or '*'} {fs.period}, dur={dur}) is not a valid start/duration"
                            )
                        model.Add(sum(candidates) == 1)
                    else:
                        # Duration not specified: force "a session starts here" with any allowed duration.
                        candidates = []
                        for d in days_to_consider:
                            for dur in range(subj.min_contiguous_periods, subj.max_contiguous_periods + 1):
                                key = (cs.class_name, subj.name, d, start, dur)
                                if key in y:
                                    candidates.append(y[key])
                        if not candidates:
                            raise ValueError(
                                f"class '{cs.class_name}' semester '{cs.semester}' subject '{subj.name}': "
                                f"fixed_sessions ({fs.day or '*'} {fs.period}) has no feasible duration"
                            )
                        model.Add(sum(candidates) == 1)

    # Optional constraint: limit number of PERIODS per day by subject "tag".
    # Example: {"practical": 3} => at most 3 practical periods per class per day (usually implies <=1 practical block/day).
    if enable_tag_limits and max_periods_per_day_by_tag:
        for cs in specs:
            subjects_by_tag: Dict[str, List[SubjectSpec]] = {}
            for subj in cs.subjects:
                for tag in subj.tags:
                    subjects_by_tag.setdefault(tag, []).append(subj)

            for tag, limit in max_periods_per_day_by_tag.items():
                if limit is None:
                    continue
                tagged_subjects = subjects_by_tag.get(tag, [])
                if not tagged_subjects:
                    continue
                for d in range(num_days):
                    model.Add(
                        sum(
                            occ_subj[(cs.class_name, subj.name, d, p)]
                            for subj in tagged_subjects
                            for p in range(num_periods)
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

    # Link teacher occupancy vars to subject occupancy vars
    for cs in specs:
        for subj in cs.subjects:
            mode = (subj.teaching_mode or "any_of").lower()
            for d in range(num_days):
                for p in range(num_periods):
                    tvars = [occ_subj_teacher[(cs.class_name, subj.name, t, d, p)] for t in subj.teachers]
                    if mode == "all_of":
                        for tv in tvars:
                            model.Add(tv == occ_subj[(cs.class_name, subj.name, d, p)])
                    else:
                        # any_of: exactly one teacher if the subject occupies this slot; none if not occupied
                        model.Add(sum(tvars) == occ_subj[(cs.class_name, subj.name, d, p)])

    # Constraint: a teacher cannot teach two classes at the same time
    teachers = sorted({t for cs in specs for subj in cs.subjects for t in subj.teachers})
    for t in teachers:
        for d in range(num_days):
            for p in range(num_periods):
                model.Add(
                    sum(
                        occ_subj_teacher[(cs.class_name, subj.name, t, d, p)]
                        for cs in specs
                        for subj in cs.subjects
                        if t in subj.teachers
                    )
                    <= 1
                )

    # Teacher-level hard constraints: max periods/week and unavailable periods
    if enable_teacher_constraints:
        for t in teachers:
            tmax = teacher_max_periods_per_week.get(t)
            if tmax is not None:
                model.Add(
                    sum(
                        occ_subj_teacher[(cs.class_name, subj.name, t, d, p)]
                        for cs in specs
                        for subj in cs.subjects
                        for d in range(num_days)
                        for p in range(num_periods)
                        if t in subj.teachers
                    )
                    <= int(tmax)
                )

            unavail = teacher_unavailable_periods.get(t, []) or []
            if unavail:
                for day_name, period_name in unavail:
                    if day_name not in day_to_idx:
                        raise ValueError(f"teacher '{t}': unavailable_periods day '{day_name}' is not in calendar.days")
                    if period_name not in period_to_idx:
                        raise ValueError(f"teacher '{t}': unavailable_periods period '{period_name}' is not in calendar.periods")
                    d = day_to_idx[day_name]
                    p = period_to_idx[period_name]
                    model.Add(
                        sum(
                            occ_subj_teacher[(cs.class_name, subj.name, t, d, p)]
                            for cs in specs
                            for subj in cs.subjects
                            if t in subj.teachers
                        )
                        == 0
                    )

    # Soft constraint: discourage having the same subject start twice on the same day for a class.
    # This keeps lectures typically <=1/day; for practicals it also discourages multiple blocks/day.
    # We count "starts per day" and penalize anything beyond 1.
    penalties_subject_daily_starts: List[cp_model.IntVar] = []
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
                penalties_subject_daily_starts.append(excess)

    # Soft constraint: teacher period preference (penalize periods outside preferred_periods, if provided)
    penalties_teacher_preference: List[cp_model.IntVar] = []
    if enable_teacher_preferences:
        for t in teachers:
            preferred = teacher_preferred_periods.get(t, []) or []
            if not preferred:
                continue
            preferred_set = set(preferred)
            for p_name in preferred_set:
                if p_name not in period_to_idx:
                    raise ValueError(f"teacher '{t}': preferred_period '{p_name}' is not in calendar.periods")
            for d in range(num_days):
                for p in range(num_periods):
                    if periods[p] in preferred_set:
                        continue
                    # teacher_occ is 1 if this teacher teaches any class in this slot (already <=1 due to no-overlap)
                    teacher_occ = model.NewBoolVar(f"tocc__{t}__{d}__{p}")
                    model.Add(
                        teacher_occ
                        == sum(
                            occ_subj_teacher[(cs.class_name, subj.name, t, d, p)]
                            for cs in specs
                            for subj in cs.subjects
                            if t in subj.teachers
                        )
                    )
                    penalties_teacher_preference.append(teacher_occ)

    # Weighted objective: prioritize subject daily start minimization, then teacher preferences.
    w_subject_daily = 10
    w_teacher_pref = 1
    model.Minimize(w_subject_daily * sum(penalties_subject_daily_starts) + w_teacher_pref * sum(penalties_teacher_preference))

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
    return solver, status, {
        "y": y,
        "occ": occ,
        "occ_subj": occ_subj,
        "occ_subj_teacher": occ_subj_teacher,
        "subject_teachers": subject_teachers,
        "subject_teaching_mode": subject_teaching_mode,
        "meta": meta,
    }


def diagnose_infeasible(
    *,
    specs: List[ClassSemesterSpec],
    days: List[str],
    periods: List[str],
    min_classes_per_week: Optional[int],
    min_classes_per_week_by_class: Dict[str, int],
    max_periods_per_day_by_tag: Dict[str, int],
    teacher_max_periods_per_week: Dict[str, int],
    teacher_unavailable_periods: Dict[str, List[Tuple[str, str]]],
    teacher_preferred_periods: Dict[str, List[str]],
    time_limit_s: float,
) -> List[str]:
    """
    Best-effort diagnosis by toggling optional constraint groups and re-solving.
    Returns lines of explanation to print to the user.
    """
    lines: List[str] = []
    num_days = len(days)
    num_periods = len(periods)

    # Always run quick necessary-condition checks first.
    pre = _precheck_and_explain_obvious_infeasibility(
        specs=specs,
        num_days=num_days,
        num_periods=num_periods,
        min_classes_per_week=min_classes_per_week,
        min_classes_per_week_by_class=min_classes_per_week_by_class,
        max_periods_per_day_by_tag=max_periods_per_day_by_tag,
        teacher_max_periods_per_week=teacher_max_periods_per_week,
    )
    if pre:
        lines.append("Obvious infeasibility detected (necessary-condition checks):")
        lines.extend([f"- {x}" for x in pre])
        return lines

    # Baseline: without placement constraints, without tag limits, without min-classes constraint.
    solver0, st0, _ctx0 = solve_timetable(
        specs=specs,
        days=days,
        periods=periods,
        min_classes_per_week=min_classes_per_week,
        min_classes_per_week_by_class=min_classes_per_week_by_class,
        max_periods_per_day_by_tag=max_periods_per_day_by_tag,
        teacher_max_periods_per_week=teacher_max_periods_per_week,
        teacher_unavailable_periods=teacher_unavailable_periods,
        teacher_preferred_periods=teacher_preferred_periods,
        time_limit_s=time_limit_s,
        enable_placement_constraints=False,
        enable_tag_limits=False,
        enable_min_classes_per_week=False,
        enable_teacher_constraints=False,
        enable_teacher_preferences=False,
    )
    if st0 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        lines.append(
            "Model is infeasible even with placement constraints (fixed_sessions/allowed_starts/blocked_periods), "
            "tag limits, and min_classes_per_week all disabled."
        )
        lines.append("Likely causes:")
        lines.append("- Teacher overload (total periods/week) or class overload")
        lines.append("- Periods/day too small for required contiguous blocks")
        lines.append("- Conflicting fixed durations vs periods_per_week (e.g., only 2 periods/week but fixed 3-period block)")
        lines.append(f"(Solver status: {solver0.StatusName(st0)})")
        return lines

    # Add min_classes_per_week
    if min_classes_per_week is not None or (min_classes_per_week_by_class or {}):
        solver1, st1, _ctx1 = solve_timetable(
            specs=specs,
            days=days,
            periods=periods,
            min_classes_per_week=min_classes_per_week,
            min_classes_per_week_by_class=min_classes_per_week_by_class,
            max_periods_per_day_by_tag=max_periods_per_day_by_tag,
            teacher_max_periods_per_week=teacher_max_periods_per_week,
            teacher_unavailable_periods=teacher_unavailable_periods,
            teacher_preferred_periods=teacher_preferred_periods,
            time_limit_s=time_limit_s,
            enable_placement_constraints=False,
            enable_tag_limits=False,
            enable_min_classes_per_week=True,
            enable_teacher_constraints=False,
            enable_teacher_preferences=False,
        )
        if st1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            lines.append("Infeasible when enabling constraint group: min_classes_per_week.")
            lines.append("Hint: For each class, min_classes_per_week must be <= total periods_per_week (sum across subjects).")
            return lines

    # Add tag limits
    if max_periods_per_day_by_tag:
        solver2, st2, _ctx2 = solve_timetable(
            specs=specs,
            days=days,
            periods=periods,
            min_classes_per_week=min_classes_per_week,
            min_classes_per_week_by_class=min_classes_per_week_by_class,
            max_periods_per_day_by_tag=max_periods_per_day_by_tag,
            teacher_max_periods_per_week=teacher_max_periods_per_week,
            teacher_unavailable_periods=teacher_unavailable_periods,
            teacher_preferred_periods=teacher_preferred_periods,
            time_limit_s=time_limit_s,
            enable_placement_constraints=False,
            enable_tag_limits=True,
            enable_min_classes_per_week=False,
            enable_teacher_constraints=False,
            enable_teacher_preferences=False,
        )
        if st2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            lines.append("Infeasible when enabling constraint group: max_periods_per_day_by_tag.")
            lines.append("Hint: total tagged periods/week must be <= limit_per_day * num_days for each class.")
            return lines

    # Add placement constraints last (most common source of conflicts)
    solver3, st3, _ctx3 = solve_timetable(
        specs=specs,
        days=days,
        periods=periods,
        min_classes_per_week=min_classes_per_week,
        min_classes_per_week_by_class=min_classes_per_week_by_class,
        max_periods_per_day_by_tag=max_periods_per_day_by_tag,
        teacher_max_periods_per_week=teacher_max_periods_per_week,
        teacher_unavailable_periods=teacher_unavailable_periods,
        teacher_preferred_periods=teacher_preferred_periods,
        time_limit_s=time_limit_s,
        enable_placement_constraints=True,
        enable_tag_limits=False,
        enable_min_classes_per_week=False,
        enable_teacher_constraints=False,
        enable_teacher_preferences=False,
    )
    if st3 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        lines.append("Infeasible when enabling constraint group: placement constraints.")
        lines.append("This includes: fixed_sessions, allowed_starts, blocked_periods (class).")
        lines.append("Hint: check for conflicts like:")
        lines.append("- Two classes fixing the same teacher to the same day/period")
        lines.append("- A fixed_session landing in a blocked_period")
        lines.append("- allowed_starts too restrictive to fit required periods_per_week")
        return lines

    lines.append(
        "Could not isolate a single failing constraint group; infeasibility likely comes from interactions "
        "between multiple groups (e.g., placement + tag limits + teacher clashes)."
    )
    lines.append("Try temporarily removing fixed_sessions/allowed_starts or loosening tag limits to find the conflict.")
    return lines


def _format_class_timetable(
    *,
    class_name: str,
    subjects: List[str],
    days: List[str],
    periods: List[str],
    solver: cp_model.CpSolver,
    occ_subj: Dict[Tuple[str, str, int, int], cp_model.IntVar],
    occ_subj_teacher: Dict[Tuple[str, str, str, int, int], cp_model.IntVar],
    subject_teachers: Dict[Tuple[str, str], Tuple[str, ...]],
    subject_teaching_mode: Dict[Tuple[str, str], str],
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
                    mode = (subject_teaching_mode.get((class_name, subj)) or "any_of").lower()
                    tlist = list(subject_teachers.get((class_name, subj)) or ())
                    if mode == "all_of":
                        cell = f"{subj}({'+'.join(tlist)})" if tlist else f"{subj}(?)"
                    else:
                        chosen = "?"
                        for t in tlist:
                            if solver.Value(occ_subj_teacher[(class_name, subj, t, d, p)]) == 1:
                                chosen = t
                                break
                        cell = f"{subj}({chosen})"
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
    occ_subj_teacher: Dict[Tuple[str, str, str, int, int], cp_model.IntVar],
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
                    key = (cs.class_name, subj, teacher, d, p)
                    if key not in occ_subj_teacher:
                        continue
                    if solver.Value(occ_subj_teacher[key]) == 1:
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


def _format_class_timetable_html(
    *,
    class_name: str,
    subjects: List[str],
    days: List[str],
    periods: List[str],
    solver: cp_model.CpSolver,
    occ_subj: Dict[Tuple[str, str, int, int], cp_model.IntVar],
    occ_subj_teacher: Dict[Tuple[str, str, str, int, int], cp_model.IntVar],
    subject_teachers: Dict[Tuple[str, str], Tuple[str, ...]],
    subject_teaching_mode: Dict[Tuple[str, str], str],
) -> str:
    # Build grid: rows=days, cols=periods
    rows: List[List[str]] = []
    for d in range(len(days)):
        row: List[str] = []
        for p in range(len(periods)):
            cell = "-"
            for subj in subjects:
                if solver.Value(occ_subj[(class_name, subj, d, p)]) == 1:
                    mode = (subject_teaching_mode.get((class_name, subj)) or "any_of").lower()
                    tlist = list(subject_teachers.get((class_name, subj)) or ())
                    if mode == "all_of":
                        cell = f"{subj} ({' + '.join(tlist)})" if tlist else f"{subj} (?)"
                    else:
                        chosen = "?"
                        for t in tlist:
                            if solver.Value(occ_subj_teacher[(class_name, subj, t, d, p)]) == 1:
                                chosen = t
                                break
                        cell = f"{subj} ({chosen})"
                    break
            row.append(cell)
        rows.append(row)

    out: List[str] = []
    out.append(f"<h3>Class: {html.escape(class_name)}</h3>")
    out.append('<table class="tt">')
    out.append("<thead><tr><th>Day</th>")
    for per in periods:
        out.append(f"<th>{html.escape(per)}</th>")
    out.append("</tr></thead>")
    out.append("<tbody>")
    for d, day in enumerate(days):
        out.append("<tr>")
        out.append(f"<th>{html.escape(day)}</th>")
        for p in range(len(periods)):
            out.append(f"<td>{html.escape(rows[d][p])}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def _format_teacher_timetable_html(
    *,
    teacher: str,
    specs: List[ClassSemesterSpec],
    days: List[str],
    periods: List[str],
    solver: cp_model.CpSolver,
    occ_subj: Dict[Tuple[str, str, int, int], cp_model.IntVar],
    occ_subj_teacher: Dict[Tuple[str, str, str, int, int], cp_model.IntVar],
) -> str:
    class_subjects: Dict[str, List[str]] = {cs.class_name: [s.name for s in cs.subjects] for cs in specs}

    rows: List[List[str]] = []
    for d in range(len(days)):
        row: List[str] = []
        for p in range(len(periods)):
            cell = "-"
            for cs in specs:
                for subj in class_subjects[cs.class_name]:
                    key = (cs.class_name, subj, teacher, d, p)
                    if key not in occ_subj_teacher:
                        continue
                    if solver.Value(occ_subj_teacher[key]) == 1:
                        cell = f"{cs.class_name}: {subj}"
                        break
                if cell != "-":
                    break
            row.append(cell)
        rows.append(row)

    out: List[str] = []
    out.append(f"<h3>Teacher: {html.escape(teacher)}</h3>")
    out.append('<table class="tt">')
    out.append("<thead><tr><th>Day</th>")
    for per in periods:
        out.append(f"<th>{html.escape(per)}</th>")
    out.append("</tr></thead>")
    out.append("<tbody>")
    for d, day in enumerate(days):
        out.append("<tr>")
        out.append(f"<th>{html.escape(day)}</th>")
        for p in range(len(periods)):
            out.append(f"<td>{html.escape(rows[d][p])}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def _wrap_html_document(body: str) -> str:
    # Lightweight styling so it can be embedded or used standalone.
    style = """
<style>
.tt { border-collapse: collapse; width: 100%; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; font-size: 13px; }
.tt th, .tt td { border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }
.tt thead th { background: #f6f7f9; }
.tt tbody th { background: #fbfbfc; text-align: left; white-space: nowrap; }
</style>
""".strip()
    return "\n".join([style, body])


def _compute_teacher_allocation_periods(
    *,
    solver: cp_model.CpSolver,
    occ_subj_teacher: Dict[Tuple[str, str, str, int, int], cp_model.IntVar],
) -> Tuple[Dict[str, Dict[Tuple[str, str], int]], Dict[str, int]]:
    """
    Returns:
      - per_teacher[(teacher)][(class_name, subject_name)] = periods_scheduled
      - totals[(teacher)] = total periods/week
    """
    per_teacher: Dict[str, Dict[Tuple[str, str], int]] = {}
    totals: Dict[str, int] = {}
    for (cls, subj, teacher, d, p), var in occ_subj_teacher.items():
        if solver.Value(var) != 1:
            continue
        per_teacher.setdefault(teacher, {})
        per_teacher[teacher][(cls, subj)] = per_teacher[teacher].get((cls, subj), 0) + 1
        totals[teacher] = totals.get(teacher, 0) + 1
    return per_teacher, totals


def _format_teacher_allocation_text(
    *,
    per_teacher: Dict[str, Dict[Tuple[str, str], int]],
    totals: Dict[str, int],
) -> str:
    lines: List[str] = []
    lines.append("Teacher allocation summary (periods/week)")
    lines.append("")
    teachers = sorted(set(per_teacher.keys()) | set(totals.keys()))
    for t in teachers:
        lines.append(f"Teacher: {t}  |  Total periods/week: {totals.get(t, 0)}")
        rows = sorted(per_teacher.get(t, {}).items(), key=lambda kv: (kv[0][0], kv[0][1]))
        if not rows:
            lines.append("  (no assigned periods)")
            lines.append("")
            continue
        # simple aligned columns
        c1w = max(len("Class"), max(len(cls) for (cls, _), _n in rows))
        c2w = max(len("Subject"), max(len(subj) for (_cls, subj), _n in rows))
        lines.append("  " + "Class".ljust(c1w) + "  " + "Subject".ljust(c2w) + "  " + "Periods")
        for (cls, subj), n in rows:
            lines.append("  " + cls.ljust(c1w) + "  " + subj.ljust(c2w) + "  " + str(n))
        lines.append("")
    return "\n".join(lines)


def _format_teacher_allocation_html(
    *,
    per_teacher: Dict[str, Dict[Tuple[str, str], int]],
    totals: Dict[str, int],
) -> str:
    out: List[str] = []
    out.append("<h2>Teacher allocation summary (periods/week)</h2>")
    teachers = sorted(set(per_teacher.keys()) | set(totals.keys()))
    for t in teachers:
        out.append(f"<h3>Teacher: {html.escape(t)} &nbsp;|&nbsp; Total periods/week: <code>{totals.get(t, 0)}</code></h3>")
        rows = sorted(per_teacher.get(t, {}).items(), key=lambda kv: (kv[0][0], kv[0][1]))
        if not rows:
            out.append("<p><em>No assigned periods.</em></p>")
            continue
        out.append('<table class="tt">')
        out.append("<thead><tr><th>Class</th><th>Subject</th><th>Periods</th></tr></thead>")
        out.append("<tbody>")
        for (cls, subj), n in rows:
            out.append(
                "<tr>"
                f"<td>{html.escape(cls)}</td>"
                f"<td>{html.escape(subj)}</td>"
                f"<td>{n}</td>"
                "</tr>"
            )
        out.append("</tbody></table>")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="College timetable generator using Google OR-Tools (CP-SAT).")
    parser.add_argument("--input", required=True, help="Path to input JSON file.")
    parser.add_argument("--semester", required=True, help="Semester key in JSON, e.g. 'S1' or 'S2'.")
    parser.add_argument("--time_limit_s", type=float, default=10.0, help="CP-SAT time limit in seconds.")
    parser.add_argument("--print_teachers", action="store_true", help="Also print timetable per teacher.")
    parser.add_argument(
        "--output_format",
        choices=["text", "html"],
        default="text",
        help="Output format. 'html' prints HTML tables (embed-friendly). Default: text.",
    )
    args = parser.parse_args()

    # Shared schema validation (used by both CLI + GUI)
    ti = TimetableInput.load_file(args.input)
    days = ti.calendar.days
    periods = ti.calendar.periods
    min_classes_per_week = ti.constraints.min_classes_per_week
    min_classes_per_week_by_class = ti.constraints.min_classes_per_week_by_class
    max_periods_per_day_by_tag = ti.constraints.max_periods_per_day_by_tag
    global_teacher_max = getattr(ti.constraints, "teacher_max_periods_per_week", None)

    teacher_max_periods_per_week: Dict[str, int] = {}
    teacher_unavailable_periods: Dict[str, List[Tuple[str, str]]] = {}
    teacher_preferred_periods: Dict[str, List[str]] = {}
    for t in (getattr(ti, "teachers", []) or []):
        if t.max_periods_per_week is not None:
            teacher_max_periods_per_week[t.name] = int(t.max_periods_per_week)
        if t.unavailable_periods:
            teacher_unavailable_periods[t.name] = [(dp.day, dp.period) for dp in t.unavailable_periods]
        if t.preferred_periods:
            teacher_preferred_periods[t.name] = list(t.preferred_periods)

    # Apply global teacher max/week to all teachers, unless overridden per-teacher.
    if global_teacher_max is not None:
        # Collect every teacher mentioned in subjects for this semester.
        all_teachers: set[str] = set()
        for c in ti.classes:
            sem = c.semesters.get(args.semester)  # type: ignore[arg-type]
            if sem is None:
                continue
            for s in sem.subjects:
                for nm in (s.teachers or []):
                    all_teachers.add(nm)
        for tname in all_teachers:
            teacher_max_periods_per_week.setdefault(tname, int(global_teacher_max))

    # Build solver specs for the requested semester; skip classes missing that semester.
    specs: List[ClassSemesterSpec] = []
    skipped: List[str] = []
    for c in ti.classes:
        sem = c.semesters.get(args.semester)  # type: ignore[arg-type]
        if sem is None:
            skipped.append(c.name)
            continue
        subjects = tuple(
            SubjectSpec(
                name=s.name,
                teachers=tuple(s.teachers or ([s.teacher] if s.teacher else [])),
                teaching_mode=str(getattr(s, "teaching_mode", "any_of") or "any_of"),
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
                semester=args.semester,
                subjects=subjects,
                blocked_periods=tuple((bp.day, bp.period) for bp in sem.blocked_periods),
            )
        )

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
        max_periods_per_day_by_tag=max_periods_per_day_by_tag,
        teacher_max_periods_per_week=teacher_max_periods_per_week,
        teacher_unavailable_periods=teacher_unavailable_periods,
        teacher_preferred_periods=teacher_preferred_periods,
        time_limit_s=args.time_limit_s,
    )

    if args.output_format == "html":
        parts: List[str] = []
        parts.append(f"<h2>Status: {html.escape(str(ctx['meta']['status']))}</h2>")
    else:
        print(f"Status: {ctx['meta']['status']}")
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if args.output_format == "html":
            parts.append("<p><strong>No feasible timetable found.</strong></p>")
            diag = diagnose_infeasible(
                specs=specs,
                days=days,
                periods=periods,
                min_classes_per_week=min_classes_per_week,
                min_classes_per_week_by_class=min_classes_per_week_by_class,
                max_periods_per_day_by_tag=max_periods_per_day_by_tag,
                teacher_max_periods_per_week=teacher_max_periods_per_week,
                teacher_unavailable_periods=teacher_unavailable_periods,
                teacher_preferred_periods=teacher_preferred_periods,
                time_limit_s=min(5.0, float(args.time_limit_s)),
            )
            if diag:
                parts.append("<ul>")
                for line in diag:
                    parts.append(f"<li>{html.escape(line)}</li>")
                parts.append("</ul>")
            print(_wrap_html_document("\n".join(parts)))
        else:
            print("No feasible timetable found.")
            print()
            for line in diagnose_infeasible(
                specs=specs,
                days=days,
                periods=periods,
                min_classes_per_week=min_classes_per_week,
                min_classes_per_week_by_class=min_classes_per_week_by_class,
                max_periods_per_day_by_tag=max_periods_per_day_by_tag,
                teacher_max_periods_per_week=teacher_max_periods_per_week,
                teacher_unavailable_periods=teacher_unavailable_periods,
                teacher_preferred_periods=teacher_preferred_periods,
                time_limit_s=min(5.0, float(args.time_limit_s)),
            ):
                print(line)
        return
    if args.output_format == "html":
        parts.append(f"<p>Objective (lower is better): <code>{html.escape(str(ctx['meta']['objective_value']))}</code></p>")
    else:
        print(f"Objective (lower is better): {ctx['meta']['objective_value']}")
        print()

    # Print class timetables
    if args.output_format == "html":
        for cs in specs:
            subjects = [s.name for s in cs.subjects]
            parts.append(
                _format_class_timetable_html(
                    class_name=cs.class_name,
                    subjects=subjects,
                    days=days,
                    periods=periods,
                    solver=solver,
                    occ_subj=ctx["occ_subj"],
                    occ_subj_teacher=ctx["occ_subj_teacher"],
                    subject_teachers=ctx["subject_teachers"],
                    subject_teaching_mode=ctx["subject_teaching_mode"],
                )
            )
        if args.print_teachers:
            for teacher in ctx["meta"]["teachers"]:
                parts.append(
                    _format_teacher_timetable_html(
                        teacher=teacher,
                        specs=specs,
                        days=days,
                        periods=periods,
                        solver=solver,
                        occ_subj=ctx["occ_subj"],
                        occ_subj_teacher=ctx["occ_subj_teacher"],
                    )
                )
        # Teacher allocation summary (periods)
        per_teacher, totals = _compute_teacher_allocation_periods(
            solver=solver,
            occ_subj_teacher=ctx["occ_subj_teacher"],
        )
        parts.append(_format_teacher_allocation_html(per_teacher=per_teacher, totals=totals))
        print(_wrap_html_document("\n\n".join(parts)))
        return
    else:
        for cs in specs:
            subjects = [s.name for s in cs.subjects]
            print(_format_class_timetable(
                class_name=cs.class_name,
                subjects=subjects,
                days=days,
                periods=periods,
                solver=solver,
                occ_subj=ctx["occ_subj"],
                occ_subj_teacher=ctx["occ_subj_teacher"],
                subject_teachers=ctx["subject_teachers"],
                subject_teaching_mode=ctx["subject_teaching_mode"],
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
                occ_subj_teacher=ctx["occ_subj_teacher"],
            ))
            print()

    # Teacher allocation summary (periods)
    per_teacher, totals = _compute_teacher_allocation_periods(
        solver=solver,
        occ_subj_teacher=ctx["occ_subj_teacher"],
    )
    print(_format_teacher_allocation_text(per_teacher=per_teacher, totals=totals))


if __name__ == "__main__":
    main()



