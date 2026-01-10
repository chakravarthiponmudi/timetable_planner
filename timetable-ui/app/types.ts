export type DayPeriod = { day: string; period: string };
export type BlockedPeriod = { day: string; period: string; reason?: string };
export type FixedSession = { day?: string; period: string; duration?: number };

export type Subject = {
  name: string;
  teacher?: string;
  teachers: string[];
  teaching_mode: "any_of" | "all_of";
  teacher_share_min_percent?: Record<string, number>;
  periods_per_week: number;
  min_contiguous_periods: number;
  max_contiguous_periods: number;
  tags: string[];
  allowed_starts: DayPeriod[];
  fixed_sessions: FixedSession[];
};

export type Semester = {
  subjects: Subject[];
  blocked_periods: BlockedPeriod[];
};

export type ClassConfig = {
  name: string;
  semesters: Partial<Record<"S1" | "S2", Semester>>;
};

export type TeacherConfig = {
  name: string;
  max_periods_per_week?: number | null;
  unavailable_periods: DayPeriod[];
  preferred_periods: string[];
};

export type Constraints = {
  min_classes_per_week?: number | null;
  min_classes_per_week_by_class?: Record<string, number>;
  max_periods_per_day_by_tag?: Record<string, number>;
  teacher_max_periods_per_week?: number | null;
};

export type Calendar = {
  days: string[];
  periods: string[];
};

export type TimetableInput = {
  constraints: Constraints;
  calendar: Calendar;
  teachers: TeacherConfig[];
  classes: ClassConfig[];
};
