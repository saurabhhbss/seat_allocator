"""Multi-round driver with progressive horizontal merging.

Implements the full REAP round schedule:
- TFWS rounds (separate supernumerary, non-mergeable)
- Special categories (KM/PwD/EXS/ORS) — Pass 1 → merge WOMEN
- Upward for special — Pass 2 → merge PWD/EXS
- Rajasthan State main and upward — on fully merged matrix
- Internal sliding (delegated to internal_sliding module)
- Direct + Management (delegated to special_round module)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .allocator import (
    AllocationResult,
    allocate_round,
    merge_horizontal,
    merge_ors_to_rsq,
    placements_to_allocations,
)
from .category_priority import CategoryPriority
from .eligibility import build_all_candidate_slots
from .models import (
    Allocation,
    Choice,
    Decision,
    Rank,
    ReportingStatus,
    RoundConfig,
    RoundMode,
    SeatSlot,
    Student,
    SupernumeraryKind,
)


@dataclass
class RoundResult:
    """Outcome of a single round."""
    round_no: int
    name: str
    mode: RoundMode
    allocations: list[Allocation]
    unplaced: set[str]
    seat_slots: list[SeatSlot]
    merge_events: list[str] = field(default_factory=list)


@dataclass
class SimulationState:
    """Mutable state that persists across rounds."""
    students: list[Student]
    choices: dict[str, list[Choice]]
    ranks: dict[str, dict[str, int]]
    seat_slots: list[SeatSlot]
    priority: CategoryPriority
    current_allocations: dict[str, Allocation] = field(default_factory=dict)
    round_results: list[RoundResult] = field(default_factory=list)
    student_map: dict[str, Student] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.student_map = {s.application_no: s for s in self.students}


# ---------------------------------------------------------------------------
# Student filters for different round types
# ---------------------------------------------------------------------------

def _tfws_filter(student: Student) -> bool:
    return student.is_tfws_eligible


def _special_filter(student: Student) -> bool:
    return (
        student.is_kashmiri_migrant
        or student.is_pwd
        or student.exs_code is not None
        or not student.is_rajasthan_domicile
    )


def _rajasthan_filter(student: Student) -> bool:
    return student.is_rajasthan_domicile


def _reported_or_conditional(student: Student) -> bool:
    return student.reporting_status in (
        ReportingStatus.REPORTED,
        ReportingStatus.CONDITIONALLY_REPORTED,
        ReportingStatus.SPECIAL_CONDITIONALLY_REPORTED,
    )


def _get_filter(eligible_filter: str) -> Callable[[Student], bool] | None:
    """Parse the eligible_filter expression into a callable."""
    mapping: dict[str, Callable[[Student], bool]] = {
        "all": lambda s: True,
        "is_tfws_eligible": _tfws_filter,
        "is_km OR is_pwd OR exs_code IS NOT NULL OR is_ors": _special_filter,
        "is_rajasthan_domicile": _rajasthan_filter,
    }
    f = eligible_filter.strip().lower()
    for key, fn in mapping.items():
        if f == key.lower():
            return fn
    return None


# ---------------------------------------------------------------------------
# Round execution
# ---------------------------------------------------------------------------

def _get_supernumerary_slots(seat_slots: list[SeatSlot]) -> list[SeatSlot]:
    return [s for s in seat_slots if s.is_supernumerary]


def _get_non_supernumerary_slots(seat_slots: list[SeatSlot]) -> list[SeatSlot]:
    return [s for s in seat_slots if not s.is_supernumerary]


def _already_allotted_students(state: SimulationState) -> set[str]:
    return set(state.current_allocations.keys())


def run_round(
    state: SimulationState,
    round_cfg: RoundConfig,
) -> RoundResult:
    """Execute a single round and update state."""
    mode = round_cfg.mode
    round_no = round_cfg.round_no

    if mode == RoundMode.MOCK:
        return _run_fresh(state, round_cfg, commit=False)
    elif mode == RoundMode.FRESH:
        return _run_fresh(state, round_cfg, commit=True)
    elif mode == RoundMode.UPWARD:
        return _run_upward(state, round_cfg)
    elif mode == RoundMode.SLIDING:
        return RoundResult(
            round_no=round_no, name=round_cfg.name,
            mode=mode, allocations=[], unplaced=set(),
            seat_slots=state.seat_slots,
            merge_events=["Internal sliding handled by internal_sliding module"],
        )
    elif mode == RoundMode.SPOT:
        return RoundResult(
            round_no=round_no, name=round_cfg.name,
            mode=mode, allocations=[], unplaced=set(),
            seat_slots=state.seat_slots,
            merge_events=["Spot/direct admission handled by special_round module"],
        )
    else:
        raise ValueError(f"Unknown round mode: {mode}")


def _run_fresh(
    state: SimulationState,
    round_cfg: RoundConfig,
    *,
    commit: bool = True,
) -> RoundResult:
    """Run a fresh allocation round."""
    student_filter = _get_filter(round_cfg.eligible_filter)
    is_tfws = round_cfg.rank_list == "tfws"

    already_allotted = _already_allotted_students(state)

    def combined_filter(s: Student) -> bool:
        if s.application_no in already_allotted:
            return False
        if round_cfg.requires_reported and not _reported_or_conditional(s):
            return False
        if student_filter and not student_filter(s):
            return False
        return True

    if is_tfws:
        active_slots = [
            s for s in state.seat_slots
            if s.is_supernumerary and s.supernumerary_kind == SupernumeraryKind.TFWS
        ]
        supernumerary_cats = ["TFWS"]
    elif round_cfg.eligible_filter.lower().startswith("is_km"):
        active_slots = state.seat_slots
        supernumerary_cats = None
    else:
        active_slots = _get_non_supernumerary_slots(state.seat_slots)
        supernumerary_cats = None

    candidate_slots = build_all_candidate_slots(
        state.students, state.choices, state.ranks, state.priority,
        supernumerary_categories=supernumerary_cats,
        student_filter=combined_filter,
    )

    result = allocate_round(candidate_slots, active_slots)
    allocations = placements_to_allocations(result, round_cfg.round_no)

    merge_events: list[str] = []
    merge_after = round_cfg.merge_after.strip().upper()

    if merge_after == "WOMEN" and commit:
        state.seat_slots = merge_horizontal(
            state.seat_slots, result.bucket_states, {"WOMEN"},
        )
        merge_events.append("Merged unfilled WOMEN seats into parent verticals")

    if merge_after in ("PWD", "PWD_EXS", "PWD,EXS") and commit:
        state.seat_slots = merge_horizontal(
            state.seat_slots, result.bucket_states, {"PWD", "EXS", "EXS_GIRLS"},
        )
        merge_events.append("Merged unfilled PWD/EXS seats into parent verticals")

    if merge_after == "ORS" and commit:
        state.seat_slots = merge_ors_to_rsq(state.seat_slots, result.bucket_states)
        merge_events.append("Merged unfilled ORS seats into RSQ GEN")

    if commit:
        for alloc in allocations:
            state.current_allocations[alloc.application_no] = alloc
            if alloc.application_no in state.student_map:
                state.student_map[alloc.application_no].reporting_status = (
                    ReportingStatus.PENDING
                )

    rr = RoundResult(
        round_no=round_cfg.round_no,
        name=round_cfg.name,
        mode=round_cfg.mode,
        allocations=allocations,
        unplaced=result.unplaced,
        seat_slots=list(state.seat_slots),
        merge_events=merge_events,
    )
    if commit:
        state.round_results.append(rr)
    return rr


def _run_upward(
    state: SimulationState,
    round_cfg: RoundConfig,
) -> RoundResult:
    """Run an upward-movement round.

    Only re-runs students who are currently allotted and
    reported/conditionally-reported, checking only preferences
    *higher* than their current allotment.
    """
    eligible: dict[str, list] = {}

    for app_no, current_alloc in state.current_allocations.items():
        student = state.student_map.get(app_no)
        if student is None:
            continue
        if not _reported_or_conditional(student):
            continue
        if student.decision == Decision.FREEZE:
            continue

        current_pref = None
        for ch in state.choices.get(app_no, []):
            if (ch.institute_code == current_alloc.institute_code
                    and ch.program_code == current_alloc.program_code):
                current_pref = ch.preference_order
                break

        if current_pref is None:
            continue

        higher_choices = [
            ch for ch in state.choices.get(app_no, [])
            if ch.preference_order < current_pref
        ]
        if not higher_choices:
            continue

        rank_map = state.ranks.get(app_no, {})
        from .eligibility import build_candidate_slots
        slots = build_candidate_slots(
            student, higher_choices, rank_map, state.priority,
        )
        if slots:
            eligible[app_no] = slots

    if not eligible:
        rr = RoundResult(
            round_no=round_cfg.round_no, name=round_cfg.name,
            mode=round_cfg.mode, allocations=[], unplaced=set(),
            seat_slots=state.seat_slots,
        )
        state.round_results.append(rr)
        return rr

    result = allocate_round(eligible, state.seat_slots)
    allocations = placements_to_allocations(result, round_cfg.round_no)

    upgraded: list[Allocation] = []
    for alloc in allocations:
        app_no = alloc.application_no
        old_alloc = state.current_allocations.get(app_no)
        if old_alloc is None:
            continue

        old_pref = None
        new_pref = None
        for ch in state.choices.get(app_no, []):
            if (ch.institute_code == old_alloc.institute_code
                    and ch.program_code == old_alloc.program_code):
                old_pref = ch.preference_order
            if (ch.institute_code == alloc.institute_code
                    and ch.program_code == alloc.program_code):
                new_pref = ch.preference_order

        if new_pref is not None and old_pref is not None and new_pref < old_pref:
            state.current_allocations[app_no] = alloc
            upgraded.append(alloc)

    merge_events: list[str] = []
    merge_after = round_cfg.merge_after.strip().upper()
    if merge_after == "WOMEN":
        state.seat_slots = merge_horizontal(
            state.seat_slots, result.bucket_states, {"WOMEN"},
        )
        merge_events.append("Merged unfilled WOMEN seats into parent verticals")
    if merge_after in ("PWD", "PWD_EXS", "PWD,EXS"):
        state.seat_slots = merge_horizontal(
            state.seat_slots, result.bucket_states, {"PWD", "EXS", "EXS_GIRLS"},
        )
        merge_events.append("Merged unfilled PWD/EXS seats into parent verticals")

    rr = RoundResult(
        round_no=round_cfg.round_no, name=round_cfg.name,
        mode=round_cfg.mode, allocations=upgraded, unplaced=set(),
        seat_slots=list(state.seat_slots),
        merge_events=merge_events,
    )
    state.round_results.append(rr)
    return rr


# ---------------------------------------------------------------------------
# Full simulation
# ---------------------------------------------------------------------------

def run_simulation(
    students: list[Student],
    choices: dict[str, list[Choice]],
    ranks: dict[str, dict[str, int]],
    seat_slots: list[SeatSlot],
    priority: CategoryPriority,
    round_configs: list[RoundConfig],
) -> SimulationState:
    """Run the full multi-round simulation.

    Returns the final ``SimulationState`` containing all round results.
    """
    state = SimulationState(
        students=students,
        choices=choices,
        ranks=ranks,
        seat_slots=seat_slots,
        priority=priority,
    )

    for rc in sorted(round_configs, key=lambda r: r.round_no):
        run_round(state, rc)

    return state
