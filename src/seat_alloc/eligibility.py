"""Determine the ordered list of (choice, category) slots a student can try.

Given a student, their pre-computed ranks, and the category-priority CSV,
this module produces the full proposal list the allocator iterates over.
"""

from __future__ import annotations

from dataclasses import dataclass

from .category_priority import CategoryPriority
from .models import (
    Choice,
    Gender,
    Horizontal,
    SeatSlot,
    Student,
    SupernumeraryKind,
)


@dataclass(frozen=True, slots=True)
class CandidateSlot:
    """One position in a student's ordered proposal list."""
    application_no: str
    preference_order: int
    institute_code: str
    program_code: str
    category: str
    rank: int


def _student_matches_category(student: Student, category: str) -> bool:
    """Check if the student's attributes allow them to sit in this category."""
    if category in ("TFWS", "KM", "FOREIGN_OCI", "WORKING_PROF", "PM_USPY"):
        return True  # supernumerary eligibility checked separately

    parts = category.split("-")
    horizontal = None
    if len(parts) >= 2 and parts[-1] in ("WOMEN", "PWD", "EXS"):
        horizontal = parts[-1]

    if horizontal == "WOMEN" and student.gender != Gender.FEMALE:
        return False
    if horizontal == "PWD" and not student.is_pwd:
        return False
    if horizontal == "EXS" and student.exs_code is None:
        return False

    if "TSP" in parts and not student.is_tsp_area_resident:
        return False

    return True


def build_candidate_slots(
    student: Student,
    choices: list[Choice],
    rank_map: dict[str, int],
    priority: CategoryPriority,
    *,
    supernumerary_categories: list[str] | None = None,
) -> list[CandidateSlot]:
    """Build the choice-first ordered proposal list for one student.

    Parameters
    ----------
    student:
        The student record.
    choices:
        The student's sorted preference list.
    rank_map:
        ``{category_token: rank}`` for this student (from ``ranks.csv``).
    priority:
        The configurable category-priority order.
    supernumerary_categories:
        If provided, restrict to only these supernumerary category tokens.
        Used when running TFWS / KM rounds that only fill supernumerary seats.
    """
    vert = student.vertical_category.value
    raw_order = priority.get_priority(vert)

    if supernumerary_categories is not None:
        effective_cats = [
            c for c in supernumerary_categories
            if c in rank_map and _student_matches_category(student, c)
        ]
    else:
        effective_cats = [
            c for c in raw_order
            if c in rank_map and _student_matches_category(student, c)
        ]

    slots: list[CandidateSlot] = []
    for choice in choices:
        for cat in effective_cats:
            slots.append(CandidateSlot(
                application_no=student.application_no,
                preference_order=choice.preference_order,
                institute_code=choice.institute_code,
                program_code=choice.program_code,
                category=cat,
                rank=rank_map[cat],
            ))
    return slots


def build_all_candidate_slots(
    students: list[Student],
    choice_index: dict[str, list[Choice]],
    rank_index: dict[str, dict[str, int]],
    priority: CategoryPriority,
    *,
    supernumerary_categories: list[str] | None = None,
    student_filter: callable | None = None,
) -> dict[str, list[CandidateSlot]]:
    """Build candidate slots for all students.

    Returns ``{application_no: [CandidateSlot, ...]}``.
    """
    result: dict[str, list[CandidateSlot]] = {}
    for student in students:
        if student_filter and not student_filter(student):
            continue
        choices = choice_index.get(student.application_no, [])
        rank_map = rank_index.get(student.application_no, {})
        if not choices or not rank_map:
            continue
        slots = build_candidate_slots(
            student, choices, rank_map, priority,
            supernumerary_categories=supernumerary_categories,
        )
        if slots:
            result[student.application_no] = slots
    return result
