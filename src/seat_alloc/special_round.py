"""Direct admission + management quota (Round 10 / final round).

After internal sliding, remaining vacant seats are filled via
institute-level direct admission.  In private colleges, the 15%
management quota seats are also filled.
"""

from __future__ import annotations

from .allocator import allocate_round, placements_to_allocations
from .category_priority import CategoryPriority
from .eligibility import build_all_candidate_slots
from .models import (
    Allocation,
    SeatSlot,
    Student,
)
from .rounds import SimulationState


def run_direct_admission(
    state: SimulationState,
    round_no: int,
) -> list[Allocation]:
    """Fill residual vacant seats via direct admission.

    Eligible: any student not currently allotted (or who has withdrawn).
    Runs against all non-supernumerary vacant capacity.
    """
    already_allotted = set(state.current_allocations.keys())

    def _filter(s: Student) -> bool:
        return s.application_no not in already_allotted

    candidate_slots = build_all_candidate_slots(
        state.students, state.choices, state.ranks, state.priority,
        student_filter=_filter,
    )

    if not candidate_slots:
        return []

    vacant_slots = [
        s for s in state.seat_slots
        if not s.is_supernumerary and s.capacity > 0
    ]

    result = allocate_round(candidate_slots, vacant_slots)
    allocs = placements_to_allocations(result, round_no)

    for alloc in allocs:
        state.current_allocations[alloc.application_no] = alloc

    return allocs


def run_management_quota(
    state: SimulationState,
    round_no: int,
    management_slots: list[SeatSlot],
) -> list[Allocation]:
    """Fill 15% management quota seats in private colleges.

    ``management_slots`` should be SeatSlots representing the management
    quota capacity (typically derived from ``round(approved_intake * 0.15)``).
    """
    already_allotted = set(state.current_allocations.keys())

    def _filter(s: Student) -> bool:
        return s.application_no not in already_allotted

    candidate_slots = build_all_candidate_slots(
        state.students, state.choices, state.ranks, state.priority,
        student_filter=_filter,
    )

    if not candidate_slots or not management_slots:
        return []

    result = allocate_round(candidate_slots, management_slots)
    allocs = placements_to_allocations(result, round_no)

    for alloc in allocs:
        state.current_allocations[alloc.application_no] = alloc

    return allocs
