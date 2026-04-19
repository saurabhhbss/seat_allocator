"""Internal sliding — institute-level branch change with REAP sub-order.

Per Section 14 of the REAP-2026 booklet, the sub-order is:

1. TFWS inter-branch sliding among TFWS-reported candidates.
2. Vacant TFWS seats offered to eligible candidates within the same branch.
3. Remaining TFWS vacancies handled per step 6.
4. KM/ORS inter-branch sliding among KM/ORS-reported candidates.
5. Vacant KM/ORS seats converted to General open for Rajasthan candidates.
6. All-category sliding for remaining reported candidates on corresponding
   category vacancies (GEN/EWS/OBC/MBC/SC/ST/TSP + remaining TFWS).
"""

from __future__ import annotations

from collections import defaultdict

from .allocator import (
    AllocationResult,
    BucketState,
    allocate_round,
    placements_to_allocations,
)
from .category_priority import CategoryPriority
from .eligibility import build_candidate_slots
from .models import (
    Allocation,
    Choice,
    ReportingStatus,
    SeatSlot,
    Student,
    SupernumeraryKind,
)
from .rounds import SimulationState


def _institute_programs(
    seat_slots: list[SeatSlot],
) -> dict[str, set[str]]:
    """Map institute_code → {program_codes}."""
    mapping: dict[str, set[str]] = defaultdict(set)
    for s in seat_slots:
        mapping[s.institute_code].add(s.program_code)
    return dict(mapping)


def _slots_for_institute(
    seat_slots: list[SeatSlot], inst_code: str,
) -> list[SeatSlot]:
    return [s for s in seat_slots if s.institute_code == inst_code]


def _is_reported(student: Student) -> bool:
    return student.reporting_status in (
        ReportingStatus.REPORTED,
        ReportingStatus.CONDITIONALLY_REPORTED,
    )


def run_internal_sliding(
    state: SimulationState,
    round_no: int,
) -> list[Allocation]:
    """Execute internal sliding for all institutes and return new allocations."""
    all_new_allocs: list[Allocation] = []

    inst_progs = _institute_programs(state.seat_slots)

    for inst_code in inst_progs:
        inst_slots = _slots_for_institute(state.seat_slots, inst_code)

        reported_at_inst: dict[str, Student] = {}
        for app_no, alloc in state.current_allocations.items():
            if alloc.institute_code != inst_code:
                continue
            student = state.student_map.get(app_no)
            if student and _is_reported(student):
                reported_at_inst[app_no] = student

        if not reported_at_inst:
            continue

        branch_choices = _build_sliding_choices(
            reported_at_inst, inst_code, inst_progs[inst_code], state,
        )

        # Step 1: TFWS inter-branch sliding
        tfws_students = {
            app: s for app, s in reported_at_inst.items()
            if state.current_allocations[app].supernumerary_kind == SupernumeraryKind.TFWS
        }
        tfws_slots = [s for s in inst_slots if s.supernumerary_kind == SupernumeraryKind.TFWS]
        if tfws_students and tfws_slots:
            new = _mini_slide(
                tfws_students, branch_choices, state, tfws_slots,
                round_no, supernumerary_cats=["TFWS"],
            )
            all_new_allocs.extend(new)

        # Step 4: KM/ORS inter-branch sliding
        km_ors_students = {
            app: s for app, s in reported_at_inst.items()
            if state.current_allocations[app].supernumerary_kind == SupernumeraryKind.KM
            or (state.current_allocations[app].state_quota is not None
                and state.current_allocations[app].state_quota.value == "ORS")
        }
        km_ors_slots = [
            s for s in inst_slots
            if s.supernumerary_kind == SupernumeraryKind.KM
            or (s.state_quota is not None and s.state_quota.value == "ORS")
        ]
        if km_ors_students and km_ors_slots:
            new = _mini_slide(
                km_ors_students, branch_choices, state, km_ors_slots,
                round_no,
            )
            all_new_allocs.extend(new)

        # Step 6: All-category sliding
        all_reported = {
            app: s for app, s in reported_at_inst.items()
            if app not in {a.application_no for a in all_new_allocs}
        }
        remaining_slots = [
            s for s in inst_slots if not s.is_supernumerary
        ]
        if all_reported and remaining_slots:
            new = _mini_slide(
                all_reported, branch_choices, state, remaining_slots,
                round_no,
            )
            all_new_allocs.extend(new)

    return all_new_allocs


def _build_sliding_choices(
    students: dict[str, Student],
    inst_code: str,
    programs: set[str],
    state: SimulationState,
) -> dict[str, list[Choice]]:
    """Build per-student branch preferences within a single institute.

    Uses their original choice list filtered to the same institute,
    only keeping programs ranked higher than their current allocation.
    """
    result: dict[str, list[Choice]] = {}
    for app_no, student in students.items():
        current = state.current_allocations.get(app_no)
        if not current:
            continue

        original_choices = state.choices.get(app_no, [])

        current_pref = None
        for ch in original_choices:
            if (ch.institute_code == inst_code
                    and ch.program_code == current.program_code):
                current_pref = ch.preference_order
                break

        higher = []
        for ch in original_choices:
            if ch.institute_code != inst_code:
                continue
            if current_pref is not None and ch.preference_order >= current_pref:
                continue
            higher.append(Choice(
                application_no=app_no,
                preference_order=ch.preference_order,
                institute_code=ch.institute_code,
                program_code=ch.program_code,
            ))

        if higher:
            higher.sort(key=lambda c: c.preference_order)
            result[app_no] = higher

    return result


def _mini_slide(
    students: dict[str, Student],
    branch_choices: dict[str, list[Choice]],
    state: SimulationState,
    available_slots: list[SeatSlot],
    round_no: int,
    *,
    supernumerary_cats: list[str] | None = None,
) -> list[Allocation]:
    """Run a mini Gale-Shapley pass for a sliding sub-step."""
    from .eligibility import build_all_candidate_slots

    filtered_choices = {
        app: chs for app, chs in branch_choices.items()
        if app in students
    }

    candidate_slots = build_all_candidate_slots(
        list(students.values()),
        filtered_choices,
        state.ranks,
        state.priority,
        supernumerary_categories=supernumerary_cats,
    )

    if not candidate_slots:
        return []

    result = allocate_round(candidate_slots, available_slots)
    allocs = placements_to_allocations(result, round_no)

    upgraded: list[Allocation] = []
    for alloc in allocs:
        old = state.current_allocations.get(alloc.application_no)
        if old is None:
            continue

        old_choices = state.choices.get(alloc.application_no, [])
        old_pref = new_pref = None
        for ch in old_choices:
            if (ch.institute_code == old.institute_code
                    and ch.program_code == old.program_code):
                old_pref = ch.preference_order
            if (ch.institute_code == alloc.institute_code
                    and ch.program_code == alloc.program_code):
                new_pref = ch.preference_order

        if new_pref is not None and old_pref is not None and new_pref < old_pref:
            state.current_allocations[alloc.application_no] = alloc
            upgraded.append(alloc)

    return upgraded
