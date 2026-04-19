"""Choice-first Gale-Shapley seat allocator with progressive horizontal merging.

The allocator iterates:

    for each choice  →  for each category (in priority order)

A bounded-heap per SeatSlot tracks the best ``capacity`` occupants by rank.
Displaced students re-enter the proposal queue from their next untried slot.

After a round the caller may *merge* unfilled horizontal sub-quota seats
into their parent vertical bucket (e.g. ``SC-WOMEN → SC``) and re-run.
Supernumerary seats are NEVER merged.
"""

from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass, field

from .eligibility import CandidateSlot
from .models import (
    Allocation,
    Horizontal,
    SeatSlot,
    StateQuota,
    Vertical,
)


# ---------------------------------------------------------------------------
# Seat-bucket runtime state
# ---------------------------------------------------------------------------

@dataclass
class BucketState:
    """Runtime state for a single SeatSlot during allocation."""
    slot: SeatSlot
    capacity: int
    occupants: list[tuple[int, str]] = field(default_factory=list)

    @property
    def is_full(self) -> bool:
        return len(self.occupants) >= self.capacity

    @property
    def worst_rank(self) -> int | None:
        if not self.occupants:
            return None
        return self.occupants[0][0]

    def try_place(self, rank: int, app_no: str) -> tuple[bool, str | None]:
        """Try to place a student.

        Returns ``(True, None)`` if placed without displacement,
        ``(True, displaced_app_no)`` if placed and someone was bumped,
        ``(False, None)`` if rejected.
        """
        if not self.is_full:
            heapq.heappush(self.occupants, (-rank, app_no))  # max-heap via negation
            return True, None
        worst_neg_rank, worst_app = self.occupants[0]
        worst_rank = -worst_neg_rank
        if rank < worst_rank:
            heapq.heapreplace(self.occupants, (-rank, app_no))
            return True, worst_app
        return False, None

    def remove(self, app_no: str) -> bool:
        """Remove a specific student (used in upward movement)."""
        for i, (neg_r, a) in enumerate(self.occupants):
            if a == app_no:
                self.occupants.pop(i)
                heapq.heapify(self.occupants)
                return True
        return False

    def allocated_set(self) -> set[str]:
        return {a for _, a in self.occupants}


# ---------------------------------------------------------------------------
# Bucket-key helpers
# ---------------------------------------------------------------------------

def _bucket_key(inst: str, prog: str, cat: str, slot: SeatSlot) -> tuple:
    """Build a lookup key that matches a CandidateSlot's category to a SeatSlot."""
    return (inst, prog, cat)


def _slot_category_token(slot: SeatSlot) -> str:
    """Build the category token for a SeatSlot, matching ranks.csv tokens."""
    return slot.category_token()


def _build_bucket_index(
    slots: list[SeatSlot],
) -> dict[tuple[str, str, str], list[BucketState]]:
    """Index SeatSlots by (institute_code, program_code, category_token).

    Multiple SeatSlots may share a token when seat_type / state_quota differ;
    each gets its own BucketState.
    """
    index: dict[tuple[str, str, str], list[BucketState]] = defaultdict(list)
    for slot in slots:
        cat = _slot_category_token(slot)
        key = (slot.institute_code, slot.program_code, cat)
        index[key].append(BucketState(slot=slot, capacity=slot.capacity))
    return dict(index)


# ---------------------------------------------------------------------------
# Single-round allocator
# ---------------------------------------------------------------------------

@dataclass
class AllocationResult:
    """Output of a single-round allocation."""
    placements: dict[str, tuple[BucketState, int]]
    unplaced: set[str]
    bucket_states: dict[tuple[str, str, str], list[BucketState]]
    log: list[str] = field(default_factory=list)


def allocate_round(
    candidate_slots: dict[str, list[CandidateSlot]],
    seat_slots: list[SeatSlot],
    *,
    existing_placements: dict[str, tuple[str, str, str]] | None = None,
) -> AllocationResult:
    """Run a single Gale-Shapley allocation pass.

    Parameters
    ----------
    candidate_slots:
        ``{app_no: [CandidateSlot ...]}`` — pre-built ordered proposal lists.
    seat_slots:
        The ``SeatSlot`` rows defining available capacity.
    existing_placements:
        ``{app_no: (inst, prog, category)}`` for students already placed
        (e.g. from a previous round with FREEZE).  They occupy capacity but
        don't re-propose.

    Returns
    -------
    AllocationResult with placements and bucket states.
    """
    bucket_index = _build_bucket_index(seat_slots)

    if existing_placements:
        for app_no, (inst, prog, cat) in existing_placements.items():
            key = (inst, prog, cat)
            buckets = bucket_index.get(key, [])
            for bs in buckets:
                if not bs.is_full:
                    heapq.heappush(bs.occupants, (0, app_no))  # rank 0 = highest
                    break

    proposal_ptr: dict[str, int] = {app: 0 for app in candidate_slots}
    placements: dict[str, tuple[BucketState, int]] = {}
    placed: set[str] = set(existing_placements or {})

    queue = list(candidate_slots.keys())

    max_iterations = sum(len(v) for v in candidate_slots.values()) * 2 + len(queue)
    iteration = 0

    while queue and iteration < max_iterations:
        iteration += 1
        app_no = queue.pop(0)

        if app_no in placed:
            continue

        slots = candidate_slots.get(app_no, [])
        ptr = proposal_ptr.get(app_no, 0)

        allocated = False
        while ptr < len(slots):
            cs = slots[ptr]
            ptr += 1
            proposal_ptr[app_no] = ptr

            key = (cs.institute_code, cs.program_code, cs.category)
            buckets = bucket_index.get(key, [])

            for bs in buckets:
                success, displaced = bs.try_place(cs.rank, cs.application_no)
                if not success:
                    continue
                placements[app_no] = (bs, cs.rank)
                placed.add(app_no)
                if displaced is not None and displaced != app_no:
                    placed.discard(displaced)
                    if displaced in placements:
                        del placements[displaced]
                    queue.append(displaced)
                allocated = True
                break

            if allocated:
                break

    unplaced = set(candidate_slots.keys()) - placed
    return AllocationResult(
        placements=placements,
        unplaced=unplaced,
        bucket_states=bucket_index,
    )


# ---------------------------------------------------------------------------
# Horizontal merging
# ---------------------------------------------------------------------------

def merge_horizontal(
    seat_slots: list[SeatSlot],
    bucket_states: dict[tuple[str, str, str], list[BucketState]],
    horizontals_to_merge: set[str],
) -> list[SeatSlot]:
    """Merge unfilled horizontal sub-quota seats into their parent vertical.

    Returns a new list of SeatSlots with updated capacities.
    Supernumerary slots are never touched.

    Parameters
    ----------
    seat_slots:
        Current seat slot definitions.
    bucket_states:
        Bucket states from the last allocation pass (to check occupancy).
    horizontals_to_merge:
        Set of horizontal tokens to merge, e.g. ``{"WOMEN"}`` or ``{"PWD", "EXS"}``.
    """
    parent_extra: dict[tuple, int] = defaultdict(int)
    new_slots: list[SeatSlot] = []

    for slot in seat_slots:
        if slot.is_supernumerary:
            new_slots.append(slot)
            continue

        cat = _slot_category_token(slot)
        key = (slot.institute_code, slot.program_code, cat)
        buckets = bucket_states.get(key, [])

        h_name = slot.horizontal.value if slot.horizontal else None
        if h_name in horizontals_to_merge:
            filled = 0
            for bs in buckets:
                if bs.slot.bucket_key == slot.bucket_key:
                    filled = len(bs.occupants)
                    break
            unfilled = max(0, slot.capacity - filled)
            if unfilled > 0:
                parent_key = (
                    slot.institute_code,
                    slot.program_code,
                    slot.seat_type,
                    slot.state_quota,
                    slot.vertical,
                    slot.tsp_subquota,
                )
                parent_extra[parent_key] += unfilled
            new_slots.append(SeatSlot(
                institute_code=slot.institute_code,
                program_code=slot.program_code,
                seat_type=slot.seat_type,
                state_quota=slot.state_quota,
                vertical=slot.vertical,
                horizontal=slot.horizontal,
                tsp_subquota=slot.tsp_subquota,
                capacity=filled,
                is_supernumerary=slot.is_supernumerary,
                supernumerary_kind=slot.supernumerary_kind,
            ))
        else:
            new_slots.append(slot)

    for slot_idx, slot in enumerate(new_slots):
        if slot.is_supernumerary or slot.horizontal is not None:
            continue
        parent_key = (
            slot.institute_code,
            slot.program_code,
            slot.seat_type,
            slot.state_quota,
            slot.vertical,
            slot.tsp_subquota,
        )
        extra = parent_extra.get(parent_key, 0)
        if extra > 0:
            new_slots[slot_idx] = SeatSlot(
                institute_code=slot.institute_code,
                program_code=slot.program_code,
                seat_type=slot.seat_type,
                state_quota=slot.state_quota,
                vertical=slot.vertical,
                horizontal=None,
                tsp_subquota=slot.tsp_subquota,
                capacity=slot.capacity + extra,
                is_supernumerary=slot.is_supernumerary,
                supernumerary_kind=slot.supernumerary_kind,
            )
            parent_extra[parent_key] = 0

    return new_slots


def merge_ors_to_rsq(
    seat_slots: list[SeatSlot],
    bucket_states: dict[tuple[str, str, str], list[BucketState]],
) -> list[SeatSlot]:
    """Merge unfilled ORS seats into RSQ GEN (Section 4.D)."""
    gen_extra: dict[tuple, int] = defaultdict(int)
    new_slots: list[SeatSlot] = []

    for slot in seat_slots:
        if slot.is_supernumerary:
            new_slots.append(slot)
            continue
        if slot.state_quota != StateQuota.ORS:
            new_slots.append(slot)
            continue

        cat = _slot_category_token(slot)
        key = (slot.institute_code, slot.program_code, cat)
        buckets = bucket_states.get(key, [])
        filled = 0
        for bs in buckets:
            if bs.slot.bucket_key == slot.bucket_key:
                filled = len(bs.occupants)
                break
        unfilled = max(0, slot.capacity - filled)
        if unfilled > 0:
            gen_key = (slot.institute_code, slot.program_code, slot.seat_type)
            gen_extra[gen_key] += unfilled
        new_slots.append(SeatSlot(
            institute_code=slot.institute_code,
            program_code=slot.program_code,
            seat_type=slot.seat_type,
            state_quota=slot.state_quota,
            vertical=slot.vertical,
            horizontal=slot.horizontal,
            tsp_subquota=slot.tsp_subquota,
            capacity=filled,
            is_supernumerary=slot.is_supernumerary,
            supernumerary_kind=slot.supernumerary_kind,
        ))

    for slot_idx, slot in enumerate(new_slots):
        if slot.is_supernumerary or slot.horizontal is not None:
            continue
        if slot.state_quota != StateQuota.RSQ or slot.vertical != Vertical.GEN:
            continue
        gen_key = (slot.institute_code, slot.program_code, slot.seat_type)
        extra = gen_extra.get(gen_key, 0)
        if extra > 0:
            new_slots[slot_idx] = SeatSlot(
                institute_code=slot.institute_code,
                program_code=slot.program_code,
                seat_type=slot.seat_type,
                state_quota=slot.state_quota,
                vertical=slot.vertical,
                horizontal=None,
                tsp_subquota=slot.tsp_subquota,
                capacity=slot.capacity + extra,
                is_supernumerary=slot.is_supernumerary,
                supernumerary_kind=slot.supernumerary_kind,
            )
            gen_extra[gen_key] = 0

    return new_slots


# ---------------------------------------------------------------------------
# Helpers for extracting results
# ---------------------------------------------------------------------------

def placements_to_allocations(
    result: AllocationResult,
    round_no: int,
) -> list[Allocation]:
    """Convert allocator placements into Allocation records."""
    allocs: list[Allocation] = []
    for app_no, (bs, rank) in result.placements.items():
        slot = bs.slot
        allocs.append(Allocation(
            round_no=round_no,
            application_no=app_no,
            institute_code=slot.institute_code,
            program_code=slot.program_code,
            seat_type=slot.seat_type,
            state_quota=slot.state_quota,
            vertical=slot.vertical,
            horizontal=slot.horizontal,
            tsp_subquota=slot.tsp_subquota,
            supernumerary_kind=slot.supernumerary_kind,
        ))
    return allocs
