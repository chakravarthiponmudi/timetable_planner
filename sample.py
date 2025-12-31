from ortools.sat.python import cp_model

def main():
    print("[debug] Starting timetable solver...", flush=True)
    model = cp_model.CpModel()
    print("[debug] Created CpModel", flush=True)

    # Timeslots
    slots = ["Mon09", "Mon10", "Mon11"]
    S = range(len(slots))
    print(f"[debug] slots={slots} (count={len(slots)})", flush=True)

    # Lessons we need to schedule
    lessons = ["Math", "English", "Science"]
    L = range(len(lessons))
    print(f"[debug] lessons={lessons} (count={len(lessons)})", flush=True)

    # Decision variable: lesson_slot[i] = which slot lesson i is assigned to
    lesson_slot = [model.NewIntVar(0, len(slots) - 1, f"{lessons[i]}_slot") for i in L]
    print("[debug] Created decision variables:", flush=True)
    for i in L:
        print(f"  - {lesson_slot[i].Name()} in [0..{len(slots) - 1}]", flush=True)

    # Constraint 1: all lessons must be in different slots (no overlap)
    model.AddAllDifferent(lesson_slot)
    print("[debug] Added constraint: AddAllDifferent(lesson_slot)", flush=True)

    # Constraint 2: Math cannot be at Mon11
    model.Add(lesson_slot[lessons.index("Math")] != slots.index("Mon11"))
    print("[debug] Added constraint: Math != Mon11", flush=True)

    # Constraint 3: English must be at Mon10
    model.Add(lesson_slot[lessons.index("English")] == slots.index("Mon10"))
    print("[debug] Added constraint: English == Mon10", flush=True)

    # Solve
    solver = cp_model.CpSolver()
    # Helpful debug knobs: print solver progress + avoid hanging forever.
    solver.parameters.log_search_progress = True
    solver.parameters.max_time_in_seconds = 10.0
    print("[debug] Calling solver.Solve(model)...", flush=True)
    status = solver.Solve(model)
    print(f"[debug] Solve() returned status={solver.StatusName(status)}", flush=True)
    print(f"[debug] ObjectiveValue={solver.ObjectiveValue()} (no objective is expected here)", flush=True)
    print(f"[debug] WallTime={solver.WallTime():.3f}s Conflicts={solver.NumConflicts()} Branches={solver.NumBranches()}", flush=True)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("Timetable:")
        # Print per lesson
        for i in L:
            print(f"  {lessons[i]:7s} -> {slots[solver.Value(lesson_slot[i])]}")
    else:
        print("No feasible timetable found.")

if __name__ == "__main__":
    main()