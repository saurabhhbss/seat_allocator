"""Sports Quota pre-round allocation.

SQ candidates (is_sports_category_a=True) are allocated first by msqa rank,
consuming seats from their vertical category RSQ pool.  Their allocations are
recorded with round_no=0 and seat capacities are reduced before Round 1 runs.
"""

from __future__ import annotations

from .models import Allocation, RoundMode, SeatSlot, StateQuota, Student


def run_sports_quota_round(state) -> None:
    """Allocate SQ students in-place, writing to state.current_allocations.

    Modifies state.seat_slots capacities directly.
    SQ students cannot be displaced once placed.
    Appends a RoundResult (round_no=0) to state.round_results so allocations
    appear in the standard round-by-round report.
    """
    from .rounds import RoundResult

    sq_students: list[Student] = [
        s for s in state.students if s.is_sports_category_a
    ]
    if not sq_students:
        return

    sq_allocations: list[Allocation] = []

    # Sort by SQ rank (lower = higher priority)
    def _sq_rank(s: Student) -> int:
        return state.ranks.get(s.application_no, {}).get("SQ", 999_999)

    sq_students.sort(key=_sq_rank)

    # Build a quick lookup: (institute, program, vertical, state_quota) -> SeatSlot
    # We only look at non-supernumerary RSQ slots with no horizontal sub-quota
    slot_index: dict[tuple, SeatSlot] = {}
    for slot in state.seat_slots:
        if (
            not slot.is_supernumerary
            and slot.state_quota == StateQuota.RSQ
            and slot.horizontal is None
        ):
            key = (
                slot.institute_code,
                slot.program_code,
                slot.vertical,
                slot.seat_type,
            )
            # Keep track — there may be multiple tsp_subquota variants; prefer NON_TSP
            if key not in slot_index or slot.tsp_subquota is None:
                slot_index[key] = slot

    for student in sq_students:
        if student.application_no in state.current_allocations:
            continue

        choices = state.choices.get(student.application_no, [])
        choices_sorted = sorted(choices, key=lambda c: c.preference_order)

        for choice in choices_sorted:
            placed = False
            # Try all seat_type variants (GAS first, then SFS)
            for stype_pref in ("GAS", "SFS", None):
                for slot in state.seat_slots:
                    if slot.institute_code != choice.institute_code:
                        continue
                    if slot.program_code != choice.program_code:
                        continue
                    if slot.is_supernumerary:
                        continue
                    if slot.state_quota != StateQuota.RSQ:
                        continue
                    if slot.horizontal is not None:
                        continue
                    if slot.vertical and slot.vertical.value != student.vertical_category.value:
                        continue
                    if stype_pref and slot.seat_type and slot.seat_type.value != stype_pref:
                        continue
                    if slot.capacity <= 0:
                        continue

                    # Place the student
                    slot.capacity -= 1
                    alloc = Allocation(
                        round_no=0,
                        application_no=student.application_no,
                        institute_code=slot.institute_code,
                        program_code=slot.program_code,
                        seat_type=slot.seat_type,
                        state_quota=slot.state_quota,
                        vertical=slot.vertical,
                        horizontal=slot.horizontal,
                        tsp_subquota=slot.tsp_subquota,
                        supernumerary_kind=slot.supernumerary_kind,
                    )
                    state.current_allocations[student.application_no] = alloc
                    sq_allocations.append(alloc)
                    placed = True
                    break
                if placed:
                    break
            if placed:
                break

    unplaced = {
        s.application_no for s in sq_students
        if s.application_no not in state.current_allocations
    }
    state.round_results.append(RoundResult(
        round_no=0,
        name="Sports Quota",
        mode=RoundMode.FRESH,
        allocations=sq_allocations,
        unplaced=unplaced,
        seat_slots=state.seat_slots,
    ))
