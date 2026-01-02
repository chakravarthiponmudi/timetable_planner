from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

SemesterKey = Literal["S1", "S2"]


class DayPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: str
    period: str

    @field_validator("day", "period")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("must be a non-empty string")
        return v


class FixedSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # day is optional
    day: Optional[str] = None
    period: str
    duration: Optional[int] = None

    @field_validator("day")
    @classmethod
    def _day_non_empty_if_present(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = (v or "").strip()
        if not v:
            raise ValueError("must be a non-empty string if provided")
        return v

    @field_validator("period")
    @classmethod
    def _period_non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("must be a non-empty string")
        return v

    @field_validator("duration")
    @classmethod
    def _duration_positive_if_present(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        if not isinstance(v, int) or v <= 0:
            raise ValueError("must be a positive integer if provided")
        return v


class Subject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    teacher: str
    periods_per_week: int
    min_contiguous_periods: int = 1
    max_contiguous_periods: int = 1
    tags: List[str] = Field(default_factory=list)
    allowed_starts: List[DayPeriod] = Field(default_factory=list)
    fixed_sessions: List[FixedSession] = Field(default_factory=list)

    @field_validator("name", "teacher")
    @classmethod
    def _non_empty_str(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("must be a non-empty string")
        return v

    @field_validator("periods_per_week")
    @classmethod
    def _ppw_positive(cls, v: int) -> int:
        if not isinstance(v, int) or v <= 0:
            raise ValueError("must be a positive integer")
        return v

    @field_validator("min_contiguous_periods", "max_contiguous_periods")
    @classmethod
    def _contig_positive(cls, v: int) -> int:
        if not isinstance(v, int) or v <= 0:
            raise ValueError("must be a positive integer")
        return v

    @field_validator("tags")
    @classmethod
    def _tags_clean(cls, v: List[str]) -> List[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("must be an array of strings")
        out: List[str] = []
        for t in v:
            if not isinstance(t, str) or not t.strip():
                raise ValueError("tags must be non-empty strings")
            out.append(t.strip())
        return out

    @model_validator(mode="after")
    def _contig_bounds(self) -> "Subject":
        if self.min_contiguous_periods > self.max_contiguous_periods:
            raise ValueError("min_contiguous_periods cannot exceed max_contiguous_periods")
        if self.periods_per_week < self.min_contiguous_periods:
            raise ValueError("periods_per_week must be >= min_contiguous_periods")
        return self


class Semester(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: List[Subject]
    blocked_periods: List[DayPeriod] = Field(default_factory=list)

    @model_validator(mode="after")
    def _subjects_non_empty(self) -> "Semester":
        if not self.subjects:
            raise ValueError("must have at least one subject")
        # subject names unique within semester
        names = [s.name for s in self.subjects]
        if len(set(names)) != len(names):
            raise ValueError("subject names must be unique within a class+semester")
        return self


class ClassConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    semesters: Dict[SemesterKey, Semester]

    @field_validator("name")
    @classmethod
    def _class_name_non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("must be a non-empty string")
        return v

    @model_validator(mode="after")
    def _at_least_one_semester(self) -> "ClassConfig":
        if not self.semesters:
            raise ValueError("must define at least one semester")
        return self


class Calendar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: List[str] = Field(default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri"])
    periods: List[str] = Field(default_factory=lambda: ["P1", "P2", "P3", "P4", "P5"])

    @field_validator("days", "periods")
    @classmethod
    def _non_empty_list(cls, v: List[str]) -> List[str]:
        if not isinstance(v, list) or not v:
            raise ValueError("must be a non-empty array of strings")
        out: List[str] = []
        for x in v:
            if not isinstance(x, str) or not x.strip():
                raise ValueError("items must be non-empty strings")
            out.append(x.strip())
        return out


class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_classes_per_week: Optional[int] = None
    min_classes_per_week_by_class: Dict[str, int] = Field(default_factory=dict)
    max_periods_per_day_by_tag: Dict[str, int] = Field(default_factory=dict)

    @field_validator("min_classes_per_week")
    @classmethod
    def _min_nonneg(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        if not isinstance(v, int) or v < 0:
            raise ValueError("must be a non-negative integer")
        return v

    @field_validator("min_classes_per_week_by_class", "max_periods_per_day_by_tag")
    @classmethod
    def _map_nonneg_ints(cls, v: Dict[str, int]) -> Dict[str, int]:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("must be an object/map")
        out: Dict[str, int] = {}
        for k, vv in v.items():
            if not isinstance(k, str) or not k.strip():
                raise ValueError("keys must be non-empty strings")
            if not isinstance(vv, int) or vv < 0:
                raise ValueError("values must be non-negative integers")
            out[k.strip()] = int(vv)
        return out


class TimetableInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    constraints: Constraints = Field(default_factory=Constraints)
    calendar: Calendar = Field(default_factory=Calendar)
    classes: List[ClassConfig]

    @model_validator(mode="after")
    def _unique_class_names(self) -> "TimetableInput":
        names = [c.name for c in self.classes]
        if len(set(names)) != len(names):
            raise ValueError("class names must be unique")
        return self

    def validate_references(self) -> None:
        """
        Cross-field validation that depends on calendar.days/periods.
        Raises ValidationError-like ValueError messages.
        """
        day_set = set(self.calendar.days)
        period_set = set(self.calendar.periods)

        for c in self.classes:
            for sem_key, sem in c.semesters.items():
                for bp in sem.blocked_periods:
                    if bp.day not in day_set:
                        raise ValueError(f"class '{c.name}' {sem_key}: blocked_periods.day '{bp.day}' not in calendar.days")
                    if bp.period not in period_set:
                        raise ValueError(f"class '{c.name}' {sem_key}: blocked_periods.period '{bp.period}' not in calendar.periods")

                for subj in sem.subjects:
                    for a in subj.allowed_starts:
                        if a.day not in day_set:
                            raise ValueError(
                                f"class '{c.name}' {sem_key} subject '{subj.name}': allowed_starts.day '{a.day}' not in calendar.days"
                            )
                        if a.period not in period_set:
                            raise ValueError(
                                f"class '{c.name}' {sem_key} subject '{subj.name}': allowed_starts.period '{a.period}' not in calendar.periods"
                            )
                    for fs in subj.fixed_sessions:
                        if fs.day is not None and fs.day not in day_set:
                            raise ValueError(
                                f"class '{c.name}' {sem_key} subject '{subj.name}': fixed_sessions.day '{fs.day}' not in calendar.days"
                            )
                        if fs.period not in period_set:
                            raise ValueError(
                                f"class '{c.name}' {sem_key} subject '{subj.name}': fixed_sessions.period '{fs.period}' not in calendar.periods"
                            )

    @classmethod
    def load_file(cls, path: str | Path) -> "TimetableInput":
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        try:
            obj = cls.model_validate(data)
        except ValidationError as e:
            # Re-raise with a cleaner message for CLI usage
            raise ValueError(str(e)) from e
        obj.validate_references()
        return obj

    def to_json_dict(self) -> Dict[str, Any]:  # type: ignore[name-defined]
        # Keep output close to the input shape (omit Nones where possible)
        return self.model_dump(exclude_none=True)

    def save_file(self, path: str | Path) -> None:
        p = Path(path)
        p.write_text(json.dumps(self.to_json_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


